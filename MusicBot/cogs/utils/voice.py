
import asyncio
from typing import cast

from yandex_music import Track, ClientAsync

import discord
from discord import Interaction, ApplicationContext

from MusicBot.database import VoiceGuildsDatabase, BaseUsersDatabase

class VoiceExtension:
    
    def __init__(self) -> None:
        self.db = VoiceGuildsDatabase()
        self.users_db = BaseUsersDatabase()
    
    def clear_queue(self, ctx: ApplicationContext | Interaction):
        if ctx.guild:
            self.db.update(ctx.guild.id, {'tracks_list': []})

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
        if not ctx.guild:
            return

        vc = self.get_voice_client(ctx)
        if not vc:
            return
        
        if isinstance(ctx, Interaction):
            loop = ctx.client.loop
        else:
            loop = ctx.bot.loop
        
        gid = ctx.guild.id
        guild = self.db.get_guild(gid)
        if guild.get('current_track') is not None:
            self.db.add_track(gid, track)
            await ctx.respond(f"Трек **{track.title}** был добавлен в очередь.", delete_after=15)
        else:
            await track.download_async(f'music/{ctx.guild_id}.mp3')
            song = discord.FFmpegPCMAudio(f'music/{ctx.guild_id}.mp3', options='-vn -filter:a "volume=0.15"')

            vc.play(song, after=lambda exc: asyncio.run_coroutine_threadsafe(self.next_track(ctx), loop))
            
            self.db.set_current_track(gid, track)
            self.db.update(gid, {'is_stopped': False})
            return track.title

    def pause_playing(self, ctx: ApplicationContext | Interaction) -> None:
        vc = self.get_voice_client(ctx)
        if vc:
            vc.pause()

    def resume_playing(self, ctx: ApplicationContext | Interaction) -> None:
        vc = self.get_voice_client(ctx)
        if vc:
            vc.resume()

    def stop_playing(self, ctx: ApplicationContext | Interaction) -> None:
        if not ctx.guild:
            return

        vc = self.get_voice_client(ctx)
        if vc:
            self.db.update(ctx.guild.id, {'current_track': None, 'is_stopped': True})
            vc.stop()
            
    async def next_track(self, ctx: ApplicationContext | Interaction) -> str | None:
        """Switch to the next track in the queue. Return track title on success.
        Stop playing if tracks list is empty.

        Args:
            ctx (ApplicationContext | Interaction): Context

        Returns:
            str | None: Track title or None.
        """
        if not ctx.guild or not ctx.user:
            return
        
        gid = ctx.guild.id
        guild = self.db.get_guild(gid)
        token = self.users_db.get_ym_token(ctx.user.id)
        if guild.get('is_stopped'):
            return
    
        if not self.get_voice_client(ctx):  # Silently return if bot got kicked
            return
        
        current_track = guild.get('current_track')
        tracks_list = guild.get('tracks_list')
        if tracks_list and current_track:
            self.db.add_previous_track(gid, current_track)
            track = self.db.pop_track(gid)
            ym_track = Track.de_json(track, client=ClientAsync(token))  # type: ignore
            self.stop_playing(ctx)
            return await self.play_track(ctx, ym_track)  # type: ignore
        elif current_track:
            self.stop_playing(ctx)

    async def prev_track(self, ctx: ApplicationContext | Interaction) -> str | None:
        """Switch to the previous track in the queue. Repeat curren the song if no previous tracks.
        Return track title on success.

        Args:
            ctx (ApplicationContext | Interaction): Context.

        Returns:
            str | None: Track title or None.
        """

        if not ctx.guild or not ctx.user:
            return
        
        gid = ctx.guild.id
        guild = self.db.get_guild(gid)
        token = self.users_db.get_ym_token(ctx.user.id)
        current_track = guild.get('current_track')
        
        tracks_list = self.db.get_previous_tracks_list(gid)
        if tracks_list and current_track:
            self.db.insert_track(gid, current_track)
            track = self.db.pop_previous_track(gid)
            ym_track = Track.de_json(track, client=ClientAsync(token))  # type: ignore
            self.stop_playing(ctx)
            return await self.play_track(ctx, ym_track)  # type: ignore
        elif current_track:
            return await self.repeat_current_track(ctx)
    
    async def repeat_current_track(self, ctx: ApplicationContext | Interaction) -> str | None:
        """Repeat current track. Return track title on success.

        Args:
            ctx (ApplicationContext | Interaction): Context

        Returns:
            str | None: Track title or None.
        """
        
        if not ctx.guild or not ctx.user:
            return
        
        gid = ctx.guild.id
        guild = self.db.get_guild(gid)
        token = self.users_db.get_ym_token(ctx.user.id)
        
        current_track = guild.get('current_track')
        if current_track:
            ym_track = Track.de_json(current_track, client=ClientAsync(token))  # type: ignore
            self.stop_playing(ctx)
            return await self.play_track(ctx, ym_track)  # type: ignore
