import aiohttp
import asyncio
from os import getenv
from math import ceil
from typing import Literal, cast
from io import BytesIO
from PIL import Image

from yandex_music import Track, ClientAsync

import discord
from discord import Interaction, ApplicationContext

from MusicBot.database import VoiceGuildsDatabase, BaseUsersDatabase

# This should be in find.py but recursive import is a thing
async def generate_player_embed(track: Track) -> discord.Embed:
    """Generate track embed for player.

    Args:
        track (yandex_music.Track): Track to be processed.

    Returns:
        discord.Embed: Track embed.
    """
    
    title = cast(str, track.title)  # casted types are always there, blame JS for that
    avail = cast(bool, track.available)
    artists = track.artists_name()
    albums = [cast(str, album.title) for album in track.albums]
    lyrics = cast(bool, track.lyrics_available)
    duration = cast(int, track.duration_ms)
    explicit = track.explicit or track.content_warning
    bg_video = track.background_video_uri
    metadata = track.meta_data
    year = track.albums[0].year
    artist = track.artists[0]

    cover_url = track.get_cover_url('400x400')
    color = await get_average_color_from_url(cover_url)

    if explicit:
        explicit_eid = getenv('EXPLICIT_EID')
        if not explicit_eid:
            raise ValueError('You must specify explicit emoji id in your enviroment.')
        title += ' <:explicit:' + explicit_eid + '>'

    duration_m = duration // 60000
    duration_s = ceil(duration / 1000) - duration_m * 60

    artist_url = f"https://music.yandex.ru/artist/{artist.id}"
    artist_cover = artist.cover
    if not artist_cover:
        artist_cover_url = artist.get_op_image_url()
    else:
        artist_cover_url = artist_cover.get_url()

    embed = discord.Embed(
        title=title,
        description=", ".join(albums),
        color=color,
    )
    embed.set_thumbnail(url=cover_url)
    embed.set_author(name=", ".join(artists), url=artist_url, icon_url=artist_cover_url)

    embed.add_field(name="Текст песни", value="Есть" if lyrics else "Нет")
    embed.add_field(name="Длительность", value=f"{duration_m}:{duration_s:02}")

    if year:
        embed.add_field(name="Год выпуска", value=str(year))

    if metadata:
        if metadata.year:
            embed.add_field(name="Год выхода", value=str(metadata.year))
    
        if metadata.number:
            embed.add_field(name="Позиция", value=str(metadata.number))
        
        if metadata.composer:
            embed.add_field(name="Композитор", value=metadata.composer)
        
        if metadata.version:
            embed.add_field(name="Версия", value=metadata.version)

    if bg_video:
        embed.add_field(name="Видеофон", value=f"[Ссылка]({bg_video})")

    if not avail:
        embed.set_footer(text=f"Трек в данный момент недоступен.")

    return embed

async def get_average_color_from_url(url: str) -> int:
    """Get image from url and calculate its average color to use in embeds.

    Args:
        url (str): Image url.

    Returns:
        int: RGB Hex code. 0x000 if failed.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                result = await response.read()

        img_file = Image.open(BytesIO(result))
        img = img_file.convert('RGB')
        width, height = img.size
        r_total, g_total, b_total = 0, 0, 0
        
        for y in range(height):
            for x in range(width):
                r, g, b = cast(tuple, img.getpixel((x, y)))
                r_total += r
                g_total += g
                b_total += b

        count = width * height
        r = r_total // count
        g = g_total // count
        b = b_total // count

        return (r << 16) + (g << 8) + b
    except Exception:
        return 0x000


class VoiceExtension:
    
    def __init__(self) -> None:
        self.db = VoiceGuildsDatabase()
        self.users_db = BaseUsersDatabase()

    async def update_player_embed(self, ctx: ApplicationContext | Interaction, player_mid: int) -> None:
        """Update current player message by its id.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            player_mid (int): Id of the player message. There can only be only one player in the guild.
        """
        
        if isinstance(ctx, Interaction):
            player = ctx.client.get_message(player_mid)
        else:
            player = await ctx.fetch_message(player_mid)
        
        if not player:
            return
        
        guild = ctx.guild
        user = ctx.user
        if guild and user:
            token = self.users_db.get_ym_token(user.id)
            current_track = self.db.get_track(guild.id, 'current')
            track = cast(Track, Track.de_json(current_track, client=ClientAsync(token)))   # type: ignore
            embed = await generate_player_embed(track)
            
            if isinstance(ctx, Interaction) and ctx.message and ctx.message.id == player_mid:
                # If interaction from player buttons
                await ctx.edit(embed=embed)
            else:
                # If interaction from other buttons. They should have their own response.
                await player.edit(embed=embed)
    
    async def voice_check(self, ctx: ApplicationContext | Interaction) -> bool:
        """Check if bot can perform voice tasks and respond if failed.

        Args:
            ctx (discord.ApplicationContext): Command context.

        Returns:
            bool: Check result.
        """
        if not ctx.user:
            return False
        
        token = self.users_db.get_ym_token(ctx.user.id)
        if not token:
            await ctx.respond("❌ Необходимо указать свой токен доступа с помощью команды /login.", delete_after=15, ephemeral=True)
            return False
        
        channel = ctx.channel
        if not isinstance(channel, discord.VoiceChannel):
            await ctx.respond("❌ Вы должны отправить команду в голосовом канале.", delete_after=15, ephemeral=True)
            return False
        
        if isinstance(ctx, Interaction):
            channels = ctx.client.voice_clients
        else:
            channels = ctx.bot.voice_clients
        voice_chat = discord.utils.get(channels, guild=ctx.guild)
        if not voice_chat:
            await ctx.respond("❌ Добавьте бота в голосовой канал при помощи команды /voice join.", delete_after=15, ephemeral=True)
            return False
        
        return True
    
    def get_voice_client(self, ctx: ApplicationContext | Interaction) -> discord.VoiceClient | None:
        """Return voice client for the given guild id. Return None if not present.

        Args:
            ctx (ApplicationContext | Interaction): Command context.

        Returns:
            discord.VoiceClient | None: Voice client or None.
        """
        
        if isinstance(ctx, Interaction):
            voice_chat = discord.utils.get(ctx.client.voice_clients, guild=ctx.guild)
        else:
            voice_chat = discord.utils.get(ctx.bot.voice_clients, guild=ctx.guild)
        
        return cast(discord.VoiceClient, voice_chat)
    
    async def play_track(self, ctx: ApplicationContext | Interaction, track: Track) -> str | None:
        """Download ``track`` by its id and play it in the voice channel. Return track title on success.
        If sound is already playing, add track id to the queue. There's no response to the context.

        Args:
            ctx (ApplicationContext | Interaction): Context
            track (Track): Track class with id and title specified.

        Returns:
            str | None: Song title or None.
        """
        if not ctx.guild:
            return None

        vc = self.get_voice_client(ctx)
        if not vc:
            return None
        
        if isinstance(ctx, Interaction):
            loop = ctx.client.loop
        else:
            loop = ctx.bot.loop
        
        gid = ctx.guild.id
        guild = self.db.get_guild(gid)
        await track.download_async(f'music/{ctx.guild.id}.mp3')
        song = discord.FFmpegPCMAudio(f'music/{ctx.guild.id}.mp3', options='-vn -filter:a "volume=0.15"')

        vc.play(song, after=lambda exc: asyncio.run_coroutine_threadsafe(self.next_track(ctx, after=True), loop))
        
        self.db.set_current_track(gid, track)
        self.db.update(gid, {'is_stopped': False})
        
        player = guild['current_player']
        if player is not None:
            await self.update_player_embed(ctx, player)
        
        return track.title

    def stop_playing(self, ctx: ApplicationContext | Interaction) -> None:
        if not ctx.guild:
            return

        vc = self.get_voice_client(ctx)
        if vc:
            self.db.update(ctx.guild.id, {'current_track': None, 'is_stopped': True})
            vc.stop()
        return
            
    async def next_track(self, ctx: ApplicationContext | Interaction, *, after: bool = False) -> str | None:
        """Switch to the next track in the queue. Return track title on success.
        Doesn't change track if stopped. Stop playing if tracks list is empty.

        Args:
            ctx (ApplicationContext | Interaction): Context
            after (bool, optional): Whether the function was called by the after callback. Defaults to False.

        Returns:
            str | None: Track title or None.
        """
        if not ctx.guild or not ctx.user:
            return None
        
        gid = ctx.guild.id
        guild = self.db.get_guild(gid)
        token = self.users_db.get_ym_token(ctx.user.id)
        if guild['is_stopped']:
            return None
    
        if not self.get_voice_client(ctx):  # Silently return if bot got kicked
            return None
        
        current_track = guild['current_track']
        ym_track = None
        
        if guild['repeat'] and after:
            return await self.repeat_current_track(ctx)
        elif guild['shuffle']:
            next_track = self.db.get_random_track(gid)
        else:
            next_track = self.db.get_track(gid, 'next')
        
        if current_track:
            self.db.modify_track(gid, current_track, 'previous', 'insert')
            
        if next_track:
            ym_track = Track.de_json(next_track, client=ClientAsync(token))  # type: ignore
            self.stop_playing(ctx)
            return await self.play_track(ctx, ym_track)  # type: ignore
        
        return None

    async def prev_track(self, ctx: ApplicationContext | Interaction) -> str | None:
        """Switch to the previous track in the queue. Repeat curren the song if no previous tracks.
        Return track title on success.

        Args:
            ctx (ApplicationContext | Interaction): Context.

        Returns:
            str | None: Track title or None.
        """

        if not ctx.guild or not ctx.user:
            return None
        
        gid = ctx.guild.id
        token = self.users_db.get_ym_token(ctx.user.id)
        current_track = self.db.get_track(gid, 'current')
        prev_track = self.db.get_track(gid, 'previous')
        
        title = None
        if prev_track:
            ym_track = Track.de_json(prev_track, client=ClientAsync(token))  # type: ignore
            self.stop_playing(ctx)
            title = await self.play_track(ctx, ym_track)  # type: ignore
        elif current_track:
            title = await self.repeat_current_track(ctx)
        
        return title
    
    async def repeat_current_track(self, ctx: ApplicationContext | Interaction) -> str | None:
        """Repeat current track. Return track title on success.

        Args:
            ctx (ApplicationContext | Interaction): Context

        Returns:
            str | None: Track title or None.
        """
        
        if not ctx.guild or not ctx.user:
            return None
        
        gid = ctx.guild.id
        token = self.users_db.get_ym_token(ctx.user.id)
        
        current_track = self.db.get_track(gid, 'current')
        if current_track:
            ym_track = Track.de_json(current_track, client=ClientAsync(token))  # type: ignore
            self.stop_playing(ctx)
            return await self.play_track(ctx, ym_track)  # type: ignore

        return None

    async def like_track(self, ctx: ApplicationContext | Interaction) -> str | Literal['TRACK REMOVED'] | None:
        """Like current track. Return track title on success.
        
        Args:
           ctx (ApplicationContext | Interaction): Context.
        
        Returns:
            str | None: Track title or None.
        """
        if not ctx.guild or not ctx.user:
            return None
        
        current_track = self.db.get_track(ctx.guild.id, 'current')
        token = self.users_db.get_ym_token(ctx.user.id)
        if not current_track or not token:
            return None

        client = await ClientAsync(token).init()
        likes = await client.users_likes_tracks()
        if not likes:
            return None

        ym_track = cast(Track, Track.de_json(current_track, client=client))  # type: ignore
        if ym_track.id not in [track.id for track in likes.tracks]:
            await ym_track.like_async()
            return ym_track.title
        else:
            await client.users_likes_tracks_remove(ym_track.id, client.me.account.uid)  # type: ignore
            return 'TRACK REMOVED'
        