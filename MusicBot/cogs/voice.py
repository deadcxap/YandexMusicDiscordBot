from typing import cast

import discord
from discord.ext.commands import Cog

from yandex_music import Track, ClientAsync

from MusicBot.cogs.utils.voice import VoiceExtension, generate_player_embed
from MusicBot.cogs.utils.player import Player

def setup(bot: discord.Bot):
    bot.add_cog(Voice())

class Voice(Cog, VoiceExtension):
    
    voice = discord.SlashCommandGroup("voice", "Команды, связанные с голосовым каналом.")
    queue = discord.SlashCommandGroup("queue", "Команды, связанные с очередью треков.")
    track = discord.SlashCommandGroup("track", "Команды, связанные с текущим треком.")
    
    @voice.command(name="menu", description="Создать меню проигрывателя. Доступно только если вы единственный в голосовом канале.")
    async def menu(self, ctx: discord.ApplicationContext) -> None:
        if not await self.voice_check(ctx):
            return

        guild = self.db.get_guild(ctx.guild.id)
        embed = None

        if guild['current_track']:
            embed = await generate_player_embed(Track.de_json(guild['current_track'], client=ClientAsync()))  # type: ignore
            vc = self.get_voice_client(ctx)
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
        vc = self.get_voice_client(ctx)
        if vc and vc.is_playing():
            response_message = "❌ Бот уже находится в голосовом канале. Выключите его с помощью команды /voice leave."
        elif isinstance(ctx.channel, discord.VoiceChannel):
            await ctx.channel.connect(timeout=15)
            response_message = "Подключение успешно!"
        else:
            response_message = "❌ Вы должны отправить команду в голосовом канале."
        
        await ctx.respond(response_message, delete_after=15, ephemeral=True)
    
    @voice.command(description="Заставить бота покинуть голосовой канал.")
    async def leave(self, ctx: discord.ApplicationContext) -> None:
        vc = self.get_voice_client(ctx)
        if vc and await self.voice_check(ctx):
            self.stop_playing(ctx)
            self.db.clear_history(ctx.guild.id)
            await vc.disconnect(force=True)
            await ctx.respond("Отключение успешно!", delete_after=15, ephemeral=True)
    
    @queue.command(description="Очистить очередь треков и историю прослушивания.")
    async def clear(self, ctx: discord.ApplicationContext) -> None:
        if not await self.voice_check(ctx):
            return
        self.db.clear_history(ctx.guild.id)
        await ctx.respond("Очередь и история сброшены.", delete_after=15, ephemeral=True)
    
    @queue.command(description="Получить очередь треков.")
    async def get(self, ctx: discord.ApplicationContext) -> None:
        if not await self.voice_check(ctx):
            return
        tracks_list = self.db.get_tracks_list(ctx.guild.id, 'next')
        embed = discord.Embed(
            title='Список треков',
            color=discord.Color.dark_purple()
        )
        for i, track in enumerate(tracks_list, start=1):
            embed.add_field(name=f"{i} - {track.get('title')}", value="", inline=False)
            if i == 25:
                break
        await ctx.respond("", embed=embed, ephemeral=True)
    
    @track.command(description="Приостановить текущий трек.")
    async def pause(self, ctx: discord.ApplicationContext) -> None:
        vc = self.get_voice_client(ctx)
        if await self.voice_check(ctx) and vc is not None:
            if not vc.is_paused():
                self.pause_playing(ctx)
                await ctx.respond("Воспроизведение приостановлено.", delete_after=15, ephemeral=True)
            else:
                await ctx.respond("Воспроизведение уже приостановлено.", delete_after=15, ephemeral=True)
    
    @track.command(description="Возобновить текущий трек.")
    async def resume(self, ctx: discord.ApplicationContext) -> None:
        vc = self.get_voice_client(ctx)
        if await self.voice_check(ctx) and vc is not None:
            if vc.is_paused():
                self.resume_playing(ctx)
                await ctx.respond("Воспроизведение восстановлено.", delete_after=15, ephemeral=True)
            else:
                await ctx.respond("Воспроизведение не на паузе.", delete_after=15, ephemeral=True)
    
    @track.command(description="Прервать проигрывание, удалить историю, очередь и текущий плеер.")
    async def stop(self, ctx: discord.ApplicationContext) -> None:
        if await self.voice_check(ctx):
            self.db.clear_history(ctx.guild.id)
            self.stop_playing(ctx)
            current_player = self.db.get_guild(ctx.guild.id)['current_player']
            if current_player is not None:
                self.db.update(ctx.guild.id, {'current_player': None, 'repeat': False, 'shuffle': False})
                message = await ctx.fetch_message(current_player)
                await message.delete()
            await ctx.respond("Воспроизведение остановлено.", delete_after=15, ephemeral=True)
    
    @track.command(description="Переключиться на следующую песню в очереди.")
    async def next(self, ctx: discord.ApplicationContext) -> None:
        if await self.voice_check(ctx):
            gid = ctx.guild.id
            tracks_list = self.db.get_tracks_list(gid, 'next')
            if not tracks_list:
                await ctx.respond("Нет песенен в очереди.", delete_after=15, ephemeral=True)
                return
            self.db.update(gid, {'is_stopped': False})
            title = await self.next_track(ctx)
            if title is not None:
                await ctx.respond(f"Сейчас играет: **{title}**!", delete_after=15)
            else:
                await ctx.respond(f"Нет треков в очереди.", delete_after=15, ephemeral=True)
