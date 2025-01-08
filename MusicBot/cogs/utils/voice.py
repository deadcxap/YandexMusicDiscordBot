
import asyncio
from typing import cast

from yandex_music import Track, ClientAsync

import discord
from discord import Interaction, ApplicationContext

from MusicBot.database.base import update, get_user, pop_track, add_track, set_current_track

class VoiceExtension:
    
    def clear_queue(self, ctx: ApplicationContext | Interaction):
        if ctx.user:
            update(ctx.user.id, {'tracks_list': []})

    def get_voice_client(self, ctx: ApplicationContext | Interaction) -> discord.VoiceClient | None:
        """Return voice client for the given guild id. Return None if not present.

        Args:
            ctx (ApplicationContext | Interaction): Command context.

        Returns:
            discord.VoiceClient | None: Voice client.
        """
        
        if isinstance(ctx, Interaction):
            voice_chat = discord.utils.get(ctx.client.voice_clients, guild=ctx.guild)
        else:
            voice_chat = discord.utils.get(ctx.bot.voice_clients, guild=ctx.guild)
        
        return cast(discord.VoiceClient, voice_chat)  

    async def play_track(self, ctx: ApplicationContext | Interaction, track: Track) -> str | None:
        """Download ``track`` by its id and play it in the voice channel. Return track title on success and don't respond.
        If sound is already playing, add track id to the queue and respond.

        Args:
            ctx (ApplicationContext | Interaction): Context
            track (Track): Track class with id and title specified.

        Returns:
            str | None: Song title or None.
        """
        if not ctx.user:
            return

        vc = self.get_voice_client(ctx)
        if not vc:
            await ctx.respond("Добавьте бота в голосовой канал при помощи команды /voice join.", delete_after=15, ephemeral=True)
            return
        
        if isinstance(ctx, Interaction):
            loop = ctx.client.loop
        else:
            loop = ctx.bot.loop
        
        uid = ctx.user.id
        user = get_user(uid)
        if user.get('current_track') is not None:
            add_track(uid, track)
            await ctx.respond(f"Трек **{track.title}** был добавлен в очередь.", delete_after=15)
        else:
            await track.download_async(f'music/{ctx.guild_id}.mp3')
            song = discord.FFmpegPCMAudio(f'music/{ctx.guild_id}.mp3', options='-vn -filter:a "volume=0.15"')

            vc.play(song, after=lambda exc: asyncio.run_coroutine_threadsafe(self.next_track(ctx), loop))
            
            set_current_track(uid)
            update(uid, {'is_stopped': False})
            return track.title

    def pause_playing(self, ctx: ApplicationContext | Interaction) -> None:
        if not ctx.user:
            return
        
        vc = self.get_voice_client(ctx)
        if vc:
            vc.pause()

    def resume_playing(self, ctx: ApplicationContext | Interaction) -> None:
        if not ctx.user:
            return
        
        vc = self.get_voice_client(ctx)
        if vc:
            vc.resume()

    def stop_playing(self, ctx: ApplicationContext | Interaction) -> None:
        if not ctx.user:
            return

        vc = self.get_voice_client(ctx)
        if vc:
            update(ctx.user.id, {'current_track': None, 'is_stopped': True})
            vc.stop()
            
    async def next_track(self, ctx: ApplicationContext | Interaction) -> str | None:
        """Switch to the next track in the queue. Return track title on success.
        Stop playing if tracks list is empty.

        Args:
            ctx (ApplicationContext | Interaction): Context

        Returns:
            str | None: Track title or None.
        """
        if not ctx.user:
            return
        
        uid = ctx.user.id
        user = get_user(uid)
        if user.get('is_stopped'):
            return
    
        if not self.get_voice_client(ctx):  # Silently return if bot got kicked
            return
        
        tracks_list = user.get('tracks_list')
        if tracks_list:
            track = pop_track(uid)
            ym_track = Track(id=track['track_id'], title=track['title'], client=ClientAsync(user.get('ym_token')))  # type: ignore
            self.stop_playing(ctx)
            return await self.play_track(ctx, ym_track)
        else:
            self.stop_playing(ctx)
