import logging
from typing import cast

import discord
from discord.ext.commands import Cog

from yandex_music import Track, ClientAsync

from MusicBot.cogs.utils.voice_extension import VoiceExtension
from MusicBot.cogs.utils.player import Player
from MusicBot.cogs.utils.misc import generate_queue_embed, generate_track_embed
from MusicBot.cogs.utils.views import QueueView

def setup(bot: discord.Bot):
    bot.add_cog(Voice(bot))

class Voice(Cog, VoiceExtension):

    voice = discord.SlashCommandGroup("voice", "Команды, связанные с голосовым каналом.")
    queue = discord.SlashCommandGroup("queue", "Команды, связанные с очередью треков.")
    track = discord.SlashCommandGroup("track", "Команды, связанные с треками в голосовом канале.")

    def __init__(self, bot: discord.Bot):
        VoiceExtension.__init__(self, bot)
        self.bot = bot

    @Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        logging.debug(f"Voice state update for member {member.id} in guild {member.guild.id}")
        gid = member.guild.id
        guild = self.db.get_guild(gid)

        channel = after.channel or before.channel
        if not channel:
            logging.debug(f"No channel found for member {member.id}")
            return

        discord_guild = await self.bot.fetch_guild(gid)
        vc = cast(discord.VoiceClient | None, discord.utils.get(self.bot.voice_clients, guild=discord_guild))

        if len(channel.members) == 1 and vc:
            logging.debug(f"Clearing history and stopping playback for guild {gid}")
            self.db.clear_history(gid)
            self.db.update(gid, {'current_track': None, 'is_stopped': True})
            vc.stop()
        elif len(channel.members) > 2 and not guild['always_allow_menu']:
            current_player = self.db.get_current_player(gid)
            if current_player:
                logging.debug(f"Disabling current player for guild {gid} due to multiple members")
                self.db.update(gid, {'current_player': None, 'repeat': False, 'shuffle': False})
                try:
                    message = await channel.fetch_message(current_player)
                    await message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
                await channel.send("Текущий плеер отключён, так как в канале больше одного человека.", delete_after=15)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        logging.debug(f"Reaction added by user {payload.user_id} in channel {payload.channel_id}")
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
        if not guild_id:
            return
        guild = self.db.get_guild(guild_id)
        votes = guild['votes']

        vote_data = votes[str(payload.message_id)]
        if payload.emoji.name == '✅':
            logging.debug(f"User {payload.user_id} voted positively for message {payload.message_id}")
            vote_data['positive_votes'].append(payload.user_id)
        elif payload.emoji.name == '❌':
            logging.debug(f"User {payload.user_id} voted negatively for message {payload.message_id}")
            vote_data['negative_votes'].append(payload.user_id)

        total_members = len(channel.members)
        required_votes = 2 if total_members <= 5 else 4 if total_members <= 10 else 6 if total_members <= 15 else 9
        if len(vote_data['positive_votes']) >= required_votes:
            logging.debug(f"Enough positive votes for message {payload.message_id}")
            if vote_data['action'] == 'next':
                logging.debug(f"Skipping track for message {payload.message_id}")
                self.db.update(guild_id, {'is_stopped': False})
                title = await self.next_track(payload)
                await message.clear_reactions()
                await message.edit(content=f"Сейчас играет: **{title}**!", delete_after=15)
                del votes[str(payload.message_id)]
            elif vote_data['action'] == 'add_track':
                logging.debug(f"Adding track for message {payload.message_id}")
                await message.clear_reactions()
                track = vote_data['vote_content']
                if not track:
                    logging.debug(f"Recieved empty vote context for message {payload.message_id}")
                    return
                self.db.update(guild_id, {'is_stopped': False})
                self.db.modify_track(guild_id, track, 'next', 'append')
                if guild['current_track']:
                    await message.edit(content=f"Трек был добавлен в очередь!", delete_after=15)
                else:
                    title = await self.next_track(payload)
                    await message.edit(content=f"Сейчас играет: **{title}**!", delete_after=15)
                del votes[str(payload.message_id)]
            elif vote_data['action'] in ('add_album', 'add_artist', 'add_playlist'):
                logging.debug(f"Performing '{vote_data['action']}' action for message {payload.message_id}")
                tracks = vote_data['vote_content']
                await message.clear_reactions()
                if not tracks:
                    logging.debug(f"Recieved empty vote context for message {payload.message_id}")
                    return
                self.db.update(guild_id, {'is_stopped': False})
                self.db.modify_track(guild_id, tracks, 'next', 'extend')
                if guild['current_track']:
                    await message.edit(content=f"Контент был добавлен в очередь!", delete_after=15)
                else:
                    title = await self.next_track(payload)
                    await message.edit(content=f"Сейчас играет: **{title}**!", delete_after=15)
                del votes[str(payload.message_id)]
        elif len(vote_data['negative_votes']) >= required_votes:
            logging.debug(f"Enough negative votes for message {payload.message_id}")
            await message.clear_reactions()
            await message.edit(content='Запрос был отклонён.', delete_after=15)
            del votes[str(payload.message_id)]
        
        self.db.update(guild_id, {'votes': votes})

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        logging.debug(f"Reaction removed by user {payload.user_id} in channel {payload.channel_id}")
        if not self.bot.user:
            return
        
        guild_id = payload.guild_id
        if not guild_id:
            return
        guild = self.db.get_guild(guild_id)
        votes = guild['votes']

        channel = cast(discord.VoiceChannel, self.bot.get_channel(payload.channel_id))
        if not channel:
            return

        message = await channel.fetch_message(payload.message_id)
        if not message or message.author.id != self.bot.user.id:
            return

        vote_data = votes[str(payload.message_id)]
        if payload.emoji.name == '✔️':
            logging.debug(f"User {payload.user_id} removed positive vote for message {payload.message_id}")
            del vote_data['positive_votes'][payload.user_id]
        elif payload.emoji.name == '❌':
            logging.debug(f"User {payload.user_id} removed negative vote for message {payload.message_id}")
            del vote_data['negative_votes'][payload.user_id]
        
        self.db.update(guild_id, {'votes': votes})
    
    @voice.command(name="menu", description="Создать меню проигрывателя. Доступно только если вы единственный в голосовом канале.")
    async def menu(self, ctx: discord.ApplicationContext) -> None:
        logging.debug(f"Menu command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        if not await self.voice_check(ctx):
            return

        guild = self.db.get_guild(ctx.guild.id)
        channel = cast(discord.VoiceChannel, ctx.channel)
        embed = None

        if len(channel.members) > 2 and not guild['always_allow_menu']:
            logging.debug(f"Action declined: other members are present in the voice channel")
            await ctx.respond("❌ Вы не единственный в голосовом канале.", ephemeral=True)
            return

        if guild['current_track']:
            embed = await generate_track_embed(
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
            logging.debug(f"Deleteing old player menu {guild['current_player']} in guild {ctx.guild.id}")
            message = await ctx.fetch_message(guild['current_player'])
            await message.delete()

        interaction = cast(discord.Interaction, await ctx.respond(view=Player(ctx), embed=embed, delete_after=3600))
        response = await interaction.original_response()
        self.db.update(ctx.guild.id, {'current_player': response.id})

    @voice.command(name="join", description="Подключиться к голосовому каналу, в котором вы сейчас находитесь.")
    async def join(self, ctx: discord.ApplicationContext) -> None:
        logging.debug(f"Join command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        member = cast(discord.Member, ctx.author)
        vc = await self.get_voice_client(ctx)
        if not member.guild_permissions.manage_channels:
            response_message = "❌ У вас нет прав для выполнения этой команды."
        elif vc and vc.is_connected():
            response_message = "❌ Бот уже находится в голосовом канале. Выключите его с помощью команды /voice leave."
        elif isinstance(ctx.channel, discord.VoiceChannel):
            await ctx.channel.connect(timeout=15)
            response_message = "Подключение успешно!"
        else:
            response_message = "❌ Вы должны отправить команду в голосовом канале."

        await ctx.respond(response_message, delete_after=15, ephemeral=True)

    @voice.command(description="Заставить бота покинуть голосовой канал.")
    async def leave(self, ctx: discord.ApplicationContext) -> None:
        logging.debug(f"Leave command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        member = cast(discord.Member, ctx.author)
        if not member.guild_permissions.manage_channels:
            await ctx.respond("❌ У вас нет прав для выполнения этой команды.", delete_after=15, ephemeral=True)
            return
        
        vc = await self.get_voice_client(ctx)
        if await self.voice_check(ctx) and vc:
            self.db.update(ctx.guild.id, {'current_track': None, 'is_stopped': True})
            self.db.clear_history(ctx.guild.id)
            vc.stop()
            await vc.disconnect(force=True)
            await ctx.respond("Отключение успешно!", delete_after=15, ephemeral=True)

    @queue.command(description="Очистить очередь треков и историю прослушивания.")
    async def clear(self, ctx: discord.ApplicationContext) -> None:
        logging.debug(f"Clear queue command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        member = cast(discord.Member, ctx.author)
        channel = cast(discord.VoiceChannel, ctx.channel)
        if len(channel.members) > 2 and not member.guild_permissions.manage_channels:
            await ctx.respond("❌ У вас нет прав для выполнения этой команды.", delete_after=15, ephemeral=True)
        elif await self.voice_check(ctx) and (len(channel.members) == 2 or member.guild_permissions.manage_channels):
            self.db.clear_history(ctx.guild.id)
            await ctx.respond("Очередь и история сброшены.", delete_after=15, ephemeral=True)

    @queue.command(description="Получить очередь треков.")
    async def get(self, ctx: discord.ApplicationContext) -> None:
        logging.debug(f"Get queue command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        if not await self.voice_check(ctx):
            return
        tracks = self.db.get_tracks_list(ctx.guild.id, 'next')
        self.users_db.update(ctx.user.id, {'queue_page': 0})
        embed = generate_queue_embed(0, tracks)
        await ctx.respond(embed=embed, view=QueueView(ctx), ephemeral=True)

    @track.command(description="Приостановить текущий трек.")
    async def pause(self, ctx: discord.ApplicationContext) -> None:
        logging.debug(f"Pause command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
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
        logging.debug(f"Resume command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
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
        logging.debug(f"Stop command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
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
        logging.debug(f"Next command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        if not await self.voice_check(ctx):
            return
        gid = ctx.guild.id
        guild = self.db.get_guild(gid)
        if not guild['next_tracks']:
            await ctx.respond("❌ Нет песенен в очереди.", delete_after=15, ephemeral=True)
            return

        member = cast(discord.Member, ctx.author)
        channel = cast(discord.VoiceChannel, ctx.channel)
        if guild['vote_next_track'] and len(channel.members) > 2 and not member.guild_permissions.manage_channels:
            message = cast(discord.Interaction, await ctx.respond(f"{member.mention} хочет пропустить текущий трек.\n\nВыполнить переход?", delete_after=30))
            response = await message.original_response()
            await response.add_reaction('✅')
            await response.add_reaction('❌')
            self.db.update_vote(
                gid,
                response.id,
                {
                    'positive_votes': list(),
                    'negative_votes': list(),
                    'total_members': len(channel.members),
                    'action': 'next',
                    'vote_content': None
                }
            )
        else:
            self.db.update(gid, {'is_stopped': False})
            title = await self.next_track(ctx)
            await ctx.respond(f"Сейчас играет: **{title}**!", delete_after=15)

    @track.command(description="Добавить трек в избранное или убрать, если он уже там.")
    async def like(self, ctx: discord.ApplicationContext) -> None:
        logging.debug(f"Like command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        if await self.voice_check(ctx):
            vc = await self.get_voice_client(ctx)
            if not vc or not vc.is_playing:
                logging.debug(f"No current track in {ctx.guild.id}")
                await ctx.respond("Нет воспроизводимого трека.", delete_after=15, ephemeral=True)
                return
            result = await self.like_track(ctx)
            if not result:
                await ctx.respond("❌ Операция не удалась.", delete_after=15, ephemeral=True)
            elif result == 'TRACK REMOVED':
                await ctx.respond("Трек был удалён из избранного.", delete_after=15, ephemeral=True)
            else:
                await ctx.respond(f"Трек **{result}** был добавлен в избранное.", delete_after=15, ephemeral=True)
