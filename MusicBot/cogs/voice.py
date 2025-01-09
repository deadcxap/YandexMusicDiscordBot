import discord
from discord.ext.commands import Cog

from MusicBot.cogs.utils.voice import VoiceExtension
from MusicBot.cogs.utils.player import Player

def setup(bot: discord.Bot):
    bot.add_cog(Voice())

class Voice(Cog, VoiceExtension):
    
    toggle = discord.SlashCommandGroup("toggle", "Команды, связанные с переключением опций.", [1247100229535141899])
    voice = discord.SlashCommandGroup("voice", "Команды, связанные с голосовым каналом.", [1247100229535141899])
    queue = discord.SlashCommandGroup("queue", "Команды, связанные с очередью треков.", [1247100229535141899])
    track = discord.SlashCommandGroup("track", "Команды, связанные с текущим треком.", [1247100229535141899])
    
    async def voice_check(self, ctx: discord.ApplicationContext) -> bool:
        """Check if bot can perform voice tasks and respond if failed.

        Args:
            ctx (discord.ApplicationContext): Command context.

        Returns:
            bool: Check result.
        """
        channel = ctx.channel
        if not isinstance(channel, discord.VoiceChannel):
            await ctx.respond("Вы должны отправить команду в голосовом канале.", delete_after=15, ephemeral=True)
            return False
        
        channels = ctx.bot.voice_clients
        voice_chat = discord.utils.get(channels, guild=ctx.guild)
        if not voice_chat:
            await ctx.respond("Добавьте бота в голосовой канал при помощи команды /voice join.", delete_after=15, ephemeral=True)
            return False
        
        return True
    
    @toggle.command(name="menu", description="Toggle player menu. Available only if you're the only one in the vocie channel.")
    async def menu(self, ctx: discord.ApplicationContext) -> None:
        if self.voice_check:
            await ctx.respond("Меню", view=Player(ctx), ephemeral=True)
    
    @voice.command(name="join", description="Join the voice channel you're currently in.")
    async def join(self, ctx: discord.ApplicationContext) -> None:
        vc = self.get_voice_client(ctx)
        if vc is not None and vc.is_playing():
            await ctx.respond("Бот уже находится в голосовом канале. Выключите его с помощью команды /voice leave.", delete_after=15, ephemeral=True)
        elif ctx.channel is not None and isinstance(ctx.channel, discord.VoiceChannel):
            await ctx.channel.connect(timeout=15)
            await ctx.respond("Подключение успешно!", delete_after=15, ephemeral=True)
        else:
            await ctx.respond("Вы должны отправить команду в голосовом канале.", delete_after=15, ephemeral=True)
    
    @voice.command(description="Force the bot to leave the voice channel.")
    async def leave(self, ctx: discord.ApplicationContext) -> None:
        vc = self.get_voice_client(ctx)
        if await self.voice_check(ctx) and vc is not None:
            await vc.disconnect(force=True)
            await ctx.respond("Отключение успешно!", delete_after=15, ephemeral=True)
    
    @queue.command(description="Clear tracks queue.")
    async def clear(self, ctx: discord.ApplicationContext) -> None:
        self.clear_queue(ctx)
        await ctx.respond("Очередь сброшена.", delete_after=15, ephemeral=True)
    
    @queue.command(description="Get tracks queue.")
    async def get(self, ctx: discord.ApplicationContext) -> None:
        if await self.voice_check(ctx):
            guild = self.db.get_guild(ctx.guild.id)
            tracks_list = guild.get('tracks_list')
            embed = discord.Embed(
                title='Список треков',
                color=discord.Color.dark_purple()
            )
            for i, track in enumerate(tracks_list, start=1):
                embed.add_field(name=f"{i} - {track.get('title')}", value="", inline=False)
                if i == 25:
                    break
            await ctx.respond("", embed=embed, ephemeral=True)
    
    @track.command(description="Pause the current track.")
    async def pause(self, ctx: discord.ApplicationContext) -> None:
        vc = self.get_voice_client(ctx)
        if await self.voice_check(ctx) and vc is not None:
            if not vc.is_paused():
                self.pause_playing(ctx)
                await ctx.respond("Воспроизведение приостановлено.", delete_after=15, ephemeral=True)
            else:
                await ctx.respond("Воспроизведение уже приостановлено.", delete_after=15, ephemeral=True)
    
    @track.command(description="Resume the current track.")
    async def resume(self, ctx: discord.ApplicationContext) -> None:
        vc = self.get_voice_client(ctx)
        if await self.voice_check(ctx) and vc is not None:
            if vc.is_paused():
                self.resume_playing(ctx)
                await ctx.respond("Воспроизведение восстановлено.", delete_after=15, ephemeral=True)
            else:
                await ctx.respond("Воспроизведение не на паузе.", delete_after=15, ephemeral=True)
    
    @track.command(description="Stop the current track and clear the queue.")
    async def stop(self, ctx: discord.ApplicationContext) -> None:
        if await self.voice_check(ctx):
            self.clear_queue(ctx)
            self.stop_playing(ctx)
            await ctx.respond("Воспроизведение остановлено.", delete_after=15, ephemeral=True)
    
    @track.command(description="Switch to the next song in the queue.")
    async def next(self, ctx: discord.ApplicationContext) -> None:
        if await self.voice_check(ctx):
            gid = ctx.guild.id
            tracks_list = self.db.get_tracks_list(gid)
            if not tracks_list:
                await ctx.respond("Нет песенен в очереди.", delete_after=15, ephemeral=True)
                return
            self.db.update(gid, {'is_stopped': False})
            title = await self.next_track(ctx)
            if title is not None:
                await ctx.respond(f"Сейчас играет: **{title}**!", delete_after=15)
            else:
                await ctx.respond(f"Нет треков в очереди.", delete_after=15, ephemeral=True)
