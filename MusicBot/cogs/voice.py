from typing import cast, TypedDict, Literal

import discord
from discord.ext.commands import Cog

from yandex_music import Track, ClientAsync

from MusicBot.cogs.utils.voice_extension import VoiceExtension, generate_player_embed
from MusicBot.cogs.utils.player import Player
from MusicBot.cogs.utils.misc import QueueView, generate_queue_embed

def setup(bot: discord.Bot):
    bot.add_cog(Voice(bot))

class Voice(Cog, VoiceExtension):

    voice = discord.SlashCommandGroup("voice", "Команды, связанные с голосовым каналом.")
    queue = discord.SlashCommandGroup("queue", "Команды, связанные с очередью треков.")
    track = discord.SlashCommandGroup("track", "Команды, связанные с треками в голосовом канале.")

    def __init__(self, bot: discord.Bot):
        VoiceExtension.__init__(self, bot)
        self.bot = bot
        MessageVotes = TypedDict('MessageVotes', {'positive_votes': set[int], 'negative_votes': set[int], 'total_members': int, 'action': Literal['next']})
        self.vote_messages: dict[int, dict[int, MessageVotes]] = {}

    @Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        gid = member.guild.id
        guild = self.db.get_guild(gid)

        if after.channel:
            channel = cast(discord.VoiceChannel, after.channel)
        else:
            channel = cast(discord.VoiceChannel, before.channel)

        if not channel:
            return

        discord_guild = await self.bot.fetch_guild(gid)
        vc = cast((discord.VoiceClient | None), discord.utils.get(self.bot.voice_clients, guild=discord_guild))

        if len(channel.members) == 1 and vc:
            self.db.clear_history(gid)
            self.db.update(gid, {'current_track': None, 'is_stopped': True})
            vc.stop()
        if len(channel.members) > 2 and not guild['always_allow_menu']:
            current_player = self.db.get_current_player(gid)
            if current_player is not None:
                self.db.update(gid, {'current_player': None, 'repeat': False, 'shuffle': False})
                try:
                    message = await channel.fetch_message(current_player)
                    await message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
                await channel.send("Текущий плеер отключён, так как в канале больше одного человека.", delete_after=15)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if not self.bot.user or not payload.member:
            return
        
        bot_id = self.bot.user.id
        if payload.user_id == bot_id:
            return

        channel = cast(discord.VoiceChannel, self.bot.get_channel(payload.channel_id))
        if not channel:
            return

        message = await channel.fetch_message(payload.message_id)
        if not message or message.author.id != bot_id:
            return

        if not self.users_db.get_ym_token(payload.user_id):
            await message.remove_reaction(payload.emoji, payload.member)
            await channel.send("Для участия в голосовании необходимо авторизоваться через /account login.", delete_after=15)
            return
        
        guild_id = payload.guild_id
        if guild_id not in self.vote_messages:
            return

        if payload.message_id not in self.vote_messages[guild_id]:
            return

        vote_data = self.vote_messages[guild_id][payload.message_id]
        if payload.emoji.name == '✅':
            vote_data['positive_votes'].add(payload.user_id)
        elif payload.emoji.name == '❌':
            vote_data['negative_votes'].add(payload.user_id)

        total_members = len(channel.members)
        if total_members <= 5:
            required_votes = 2
        elif total_members <= 10:
            required_votes = 4
        elif total_members <= 15:
            required_votes = 6
        else:
            required_votes = 9
        
        if len(vote_data['positive_votes']) >= required_votes:
            if vote_data['action'] == 'next':
                self.db.update(guild_id, {'is_stopped': False})
                title = await self.next_track(payload)
                await message.clear_reactions()
                if title is not None:
                    await message.edit(content=f"Сейчас играет: **{title}**!", delete_after=15)
                del self.vote_messages[guild_id][payload.message_id]
        elif len(vote_data['negative_votes']) >= required_votes:
            channel = cast(discord.VoiceChannel, self.bot.get_channel(payload.channel_id))
            message = await channel.fetch_message(payload.message_id)
            await message.clear_reactions()
            await message.edit(content='Запрос был отклонён.', delete_after=15)
            del self.vote_messages[guild_id][payload.message_id]

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if not self.bot.user:
            return
        
        guild_id = payload.guild_id
        if guild_id not in self.vote_messages:
            return

        if payload.message_id not in self.vote_messages[guild_id]:
            return

        channel = cast(discord.VoiceChannel, self.bot.get_channel(payload.channel_id))
        if not channel:
            return

        message = await channel.fetch_message(payload.message_id)
        if not message or message.author.id != self.bot.user.id:
            return

        vote_data = self.vote_messages[guild_id][payload.message_id]
        if payload.emoji.name == '✔️':
            vote_data['positive_votes'].discard(payload.user_id)
        elif payload.emoji.name == '❌':
            vote_data['negative_votes'].discard(payload.user_id)
    
    @voice.command(name="menu", description="Создать меню проигрывателя. Доступно только если вы единственный в голосовом канале.")
    async def menu(self, ctx: discord.ApplicationContext) -> None:
        if not await self.voice_check(ctx):
            return

        guild = self.db.get_guild(ctx.guild.id)
        channel = cast(discord.VoiceChannel, ctx.channel)
        embed = None

        if len(channel.members) > 2 and not guild['always_allow_menu']:
            await ctx.respond("Вы не единственный в голосовом канале.", ephemeral=True)
            return

        if guild['current_track']:
            embed = await generate_player_embed(
                Track.de_json(
                    guild['current_track'],
                    client=ClientAsync()  # type: ignore  # Async client can be used here.
                    )
                )
            vc = await self.get_voice_client(ctx)
            if vc and vc.is_paused():
                embed.set_footer(text='Приостановлено')
            else:
                embed.remove_footer()

        if guild['current_player']:
            message = await ctx.fetch_message(guild['current_player'])
            await message.delete()

        interaction = cast(discord.Interaction, await ctx.respond(view=Player(ctx), embed=embed, delete_after=3600))
        response = await interaction.original_response()
        self.db.update(ctx.guild.id, {'current_player': response.id})

    @voice.command(name="join", description="Подключиться к голосовому каналу, в котором вы сейчас находитесь.")
    async def join(self, ctx: discord.ApplicationContext) -> None:
        member = cast(discord.Member, ctx.author)
        vc = await self.get_voice_client(ctx)
        if not member.guild_permissions.manage_channels:
            response_message = "❌ У вас нет прав для выполнения этой команды."
        elif vc and vc.is_playing():
            response_message = "❌ Бот уже находится в голосовом канале. Выключите его с помощью команды /voice leave."
        elif isinstance(ctx.channel, discord.VoiceChannel):
            await ctx.channel.connect(timeout=15)
            response_message = "Подключение успешно!"
        else:
            response_message = "❌ Вы должны отправить команду в голосовом канале."

        await ctx.respond(response_message, delete_after=15, ephemeral=True)

    @voice.command(description="Заставить бота покинуть голосовой канал.")
    async def leave(self, ctx: discord.ApplicationContext) -> None:
        member = cast(discord.Member, ctx.author)
        if not member.guild_permissions.manage_channels:
            await ctx.respond("❌ У вас нет прав для выполнения этой команды.", delete_after=15, ephemeral=True)
            return
        
        vc = await self.get_voice_client(ctx)
        if await self.voice_check(ctx) and vc:
            await self.stop_playing(ctx)
            self.db.clear_history(ctx.guild.id)
            await vc.disconnect(force=True)
            await ctx.respond("Отключение успешно!", delete_after=15, ephemeral=True)

    @queue.command(description="Очистить очередь треков и историю прослушивания.")
    async def clear(self, ctx: discord.ApplicationContext) -> None:
        member = cast(discord.Member, ctx.author)
        channel = cast(discord.VoiceChannel, ctx.channel)
        if len(channel.members) > 2 and not member.guild_permissions.manage_channels:
            await ctx.respond("❌ У вас нет прав для выполнения этой команды.", delete_after=15, ephemeral=True)
        elif await self.voice_check(ctx) and (len(channel.members) == 2 or member.guild_permissions.manage_channels):
            self.db.clear_history(ctx.guild.id)
            await ctx.respond("Очередь и история сброшены.", delete_after=15, ephemeral=True)

    @queue.command(description="Получить очередь треков.")
    async def get(self, ctx: discord.ApplicationContext) -> None:
        if not await self.voice_check(ctx):
            return
        tracks = self.db.get_tracks_list(ctx.guild.id, 'next')
        self.users_db.update(ctx.user.id, {'queue_page': 0})
        embed = generate_queue_embed(0, tracks)
        await ctx.respond(embed=embed, view=QueueView(ctx), ephemeral=True)

    @track.command(description="Приостановить текущий трек.")
    async def pause(self, ctx: discord.ApplicationContext) -> None:
        member = cast(discord.Member, ctx.author)
        channel = cast(discord.VoiceChannel, ctx.channel)
        if len(channel.members) > 2 and not member.guild_permissions.manage_channels:
            await ctx.respond("❌ Вы не можете остановить воспроизведение, пока в канале находятся другие пользователи.", delete_after=15, ephemeral=True)
        elif await self.voice_check(ctx) and (vc := await self.get_voice_client(ctx)) is not None:
            if not vc.is_paused():
                vc.pause()
                player = self.db.get_current_player(ctx.guild.id)
                if player:
                    await self.update_player_embed(ctx, player)
                await ctx.respond("Воспроизведение приостановлено.", delete_after=15, ephemeral=True)
            else:
                await ctx.respond("Воспроизведение уже приостановлено.", delete_after=15, ephemeral=True)

    @track.command(description="Возобновить текущий трек.")
    async def resume(self, ctx: discord.ApplicationContext) -> None:
        member = cast(discord.Member, ctx.author)
        channel = cast(discord.VoiceChannel, ctx.channel)
        if len(channel.members) > 2 and not member.guild_permissions.manage_channels:
            await ctx.respond("❌ Вы не можете остановить воспроизведение, пока в канале находятся другие пользователи.", delete_after=15, ephemeral=True)
        elif await self.voice_check(ctx) and (vc := await self.get_voice_client(ctx)) is not None:
            if vc.is_paused():
                vc.resume()
                player = self.db.get_current_player(ctx.guild.id)
                if player:
                    await self.update_player_embed(ctx, player)
                await ctx.respond("Воспроизведение восстановлено.", delete_after=15, ephemeral=True)
            else:
                await ctx.respond("Воспроизведение не на паузе.", delete_after=15, ephemeral=True)

    @track.command(description="Прервать проигрывание, удалить историю, очередь и текущий плеер.")
    async def stop(self, ctx: discord.ApplicationContext) -> None:
        member = cast(discord.Member, ctx.author)
        channel = cast(discord.VoiceChannel, ctx.channel)
        if len(channel.members) > 2 and not member.guild_permissions.manage_channels:
            await ctx.respond("❌ Вы не можете остановить воспроизведение, пока в канале находятся другие пользователи.", delete_after=15, ephemeral=True)
        elif await self.voice_check(ctx):
            self.db.clear_history(ctx.guild.id)
            await self.stop_playing(ctx)
            current_player = self.db.get_current_player(ctx.guild.id)
            if current_player is not None:
                try:
                    message = await ctx.fetch_message(current_player)
                    await message.delete()
                except discord.DiscordException:
                    pass
            self.db.update(ctx.guild.id, {'current_player': None, 'repeat': False, 'shuffle': False})
            await ctx.respond("Воспроизведение остановлено.", delete_after=15, ephemeral=True)

    @track.command(description="Переключиться на следующую песню в очереди.")
    async def next(self, ctx: discord.ApplicationContext) -> None:
        if not await self.voice_check(ctx):
            return
        gid = ctx.guild.id
        tracks_list = self.db.get_tracks_list(gid, 'next')
        if not tracks_list:
            await ctx.respond("❌ Нет песенен в очереди.", delete_after=15, ephemeral=True)
            return

        member = cast(discord.Member, ctx.author)
        channel = cast(discord.VoiceChannel, ctx.channel)
        if self.db.get_track(gid, 'current') and len(channel.members) > 2 and not member.guild_permissions.manage_channels:
            message = cast(discord.Interaction, await ctx.respond(f"{ctx.user.mention} хочет пропустить текущий трек.\n\nВыполнить переход?", delete_after=30))
            response = await message.original_response()
            await response.add_reaction('✅')
            await response.add_reaction('❌')
            self.vote_messages[ctx.guild.id] = {
                response.id: {
                    'positive_votes': set(),
                    'negative_votes': set(),
                    'total_members': len(channel.members),
                    'action': 'next'
                }
            }
        else:
            self.db.update(gid, {'is_stopped': False})
            title = await self.next_track(ctx)
            if title is not None:
                await ctx.respond(f"Сейчас играет: **{title}**!", delete_after=15)
            else:
                await ctx.respond(f"Нет треков в очереди.", delete_after=15, ephemeral=True)

    @track.command(description="Добавить трек в избранное или убрать, если он уже там.")
    async def like(self, ctx: discord.ApplicationContext) -> None:
        if await self.voice_check(ctx):
            vc = await self.get_voice_client(ctx)
            if not vc or not vc.is_playing:
                await ctx.respond("Нет воспроизводимого трека.", delete_after=15, ephemeral=True)
            result = await self.like_track(ctx)
            if not result:
                await ctx.respond("❌ Операция не удалась.", delete_after=15, ephemeral=True)
            elif result == 'TRACK REMOVED':
                await ctx.respond("Трек был удалён из избранного.", delete_after=15, ephemeral=True)
            else:
                await ctx.respond(f"Трек **{result}** был добавлен в избранное.", delete_after=15, ephemeral=True)
