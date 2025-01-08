from math import ceil
from typing import cast
from io import BytesIO

import aiohttp
import discord
import yandex_music
from PIL import Image

from discord.ui import View, Button, Item
from discord import ButtonStyle, Interaction

from MusicBot.cogs.utils.voice import VoiceExtension
from MusicBot.database.base import add_track, pop_track

class PlayTrackButton(Button, VoiceExtension):
    
    def __init__(
        self,
        track: yandex_music.Track,
        *,
        style: ButtonStyle = ButtonStyle.secondary,
        label: str | None = None,
        disabled: bool = False,
        custom_id: str | None = None,
        url: str | None = None,
        emoji: str | discord.Emoji | discord.PartialEmoji | None = None,
        sku_id: int | None = None,
        row: int | None = None
        ):
        Button.__init__(self, style=style, label=label, disabled=disabled, custom_id=custom_id, url=url, emoji=emoji, sku_id=sku_id, row=row)
        VoiceExtension.__init__(self)
        self.track = track
    
    async def callback(self, interaction: Interaction) -> None:
        if interaction.channel is None or not isinstance(interaction.channel, discord.VoiceChannel):
            await interaction.respond("Вы должны отправить команду в голосовом канале.", ephemeral=True)
            return
        title = await self.play_track(interaction, self.track)
        if title:
            await interaction.respond(f"Сейчас играет: **{title}**!", delete_after=15)

class PlayAlbumButton(Button, VoiceExtension):
    
    def __init__(
        self,
        album: yandex_music.Album,
        *,
        style: ButtonStyle = ButtonStyle.secondary,
        label: str | None = None,
        disabled: bool = False,
        custom_id: str | None = None,
        url: str | None = None,
        emoji: str | discord.Emoji | discord.PartialEmoji | None = None,
        sku_id: int | None = None,
        row: int | None = None
        ):
        Button.__init__(self, style=style, label=label, disabled=disabled, custom_id=custom_id, url=url, emoji=emoji, sku_id=sku_id, row=row)
        VoiceExtension.__init__(self)
        self.album = album
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user:
            return
        
        album = cast(yandex_music.Album, await self.album.with_tracks_async())
        if not album or not album.volumes:
            return
        
        for volume in album.volumes:
            for track in volume:
                add_track(interaction.user.id, track)

        track = pop_track(interaction.user.id)
        ym_track = yandex_music.Track(id=track['track_id'], title=track['title'], client=album.client)  # type: ignore
        title = await self.play_track(interaction, ym_track)
        if title:
            await interaction.respond(f"Сейчас играет: **{album.title}**!", delete_after=15)
        else:
            await interaction.respond("Добавьте бота в голосовой канал при помощи команды /voice join.", delete_after=15, ephemeral=True)
    
class ListenTrack(View):
    
    def __init__(self, track: yandex_music.Track, album_id: int, *items: Item, timeout: float | None = 3600, disable_on_timeout: bool = False):
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        link_app = f"yandexmusic://album/{album_id}/track/{track.id}"
        link_web = f"https://music.yandex.ru/album/{album_id}/track/{track.id}"
        self.button1 = Button(label="Слушать в приложении", style=ButtonStyle.gray, url=link_app)
        self.button2 = Button(label="Слушать в браузере", style=ButtonStyle.gray, url=link_web)
        self.button3 = PlayTrackButton(track, label="Слушать в голосовом канале", style=ButtonStyle.gray)
        # self.add_item(self.button1)  # Discord doesn't allow well formed URLs in buttons for some reason.
        self.add_item(self.button2)
        self.add_item(self.button3)
    
class ListenAlbum(View):
    
    def __init__(self, album: yandex_music.Album, *items: Item, timeout: float | None = 180, disable_on_timeout: bool = False):
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        link_app = f"yandexmusic://album/{album.id}"
        link_web = f"https://music.yandex.ru/album/{album.id}"
        self.button1 = Button(label="Слушать в приложении", style=ButtonStyle.gray, url=link_app)
        self.button2 = Button(label="Слушать в браузере", style=ButtonStyle.gray, url=link_web)
        self.button3 = PlayAlbumButton(album, label="Слушать в голосовом канале", style=ButtonStyle.gray)
        # self.add_item(self.button1)  # Discord doesn't allow well formed URLs in buttons for some reason.
        self.add_item(self.button2)
        self.add_item(self.button3)

class ListenArtist(View):
    
    def __init__(self, artist_id, *items: Item, timeout: float | None = 180, disable_on_timeout: bool = False):
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        link_app = f"yandexmusic://artist/{artist_id}"
        link_web = f"https://music.yandex.ru/artist/{artist_id}"
        self.button1 = Button(label="Слушать в приложении", style=ButtonStyle.gray, url=link_app)
        self.button2 = Button(label="Слушать в браузере", style=ButtonStyle.gray, url=link_web)
        # self.add_item(self.button1)  # Discord doesn't allow well formed URLs in buttons for some reason.
        self.add_item(self.button2)
    

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
                response = await response.read()

        img = Image.open(BytesIO(response))
        img = img.convert('RGB')
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

async def proccess_album(album: yandex_music.Album) -> discord.Embed:
    """Generate album embed.

    Args:
        album (yandex_music.Album): Album to process.

    Returns:
        discord.Embed: Album embed.
    """
    
    title = cast(str, album.title)
    track_count = album.track_count
    artists = album.artists_name()
    avail = cast(bool, album.available)
    description = album.short_description
    year = album.year
    version = album.version
    bests = album.bests
    duration = album.duration_ms
    explicit = album.explicit or album.content_warning
    likes_count = album.likes_count
    artist = album.artists[0]

    cover_url = album.get_cover_url('400x400')
    color = await get_average_color_from_url(cover_url)

    if isinstance(album.labels[0], yandex_music.Label):
        labels = [cast(yandex_music.Label, label).name for label in album.labels]
    else:
        labels = [cast(str, label) for label in album.labels]

    if version:
        title += f' *{version}*'

    if explicit:
        title += ' <:explicit:1325879701117472869>'

    artist_url = f"https://music.yandex.ru/artist/{artist.id}"
    artist_cover = artist.cover
    if not artist_cover:
        artist_cover_url = artist.get_op_image_url()
    else:
        artist_cover_url = artist_cover.get_url()

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
    )
    embed.set_thumbnail(url=cover_url)
    embed.set_author(name=", ".join(artists), url=artist_url, icon_url=artist_cover_url)

    if year:
        embed.add_field(name="Год выпуска", value=str(year))

    if duration:
        duration_m = duration // 60000
        duration_s = ceil(duration / 1000) - duration_m * 60
        embed.add_field(name="Длительность", value=f"{duration_m}:{duration_s:02}")

    if track_count is not None:
        if track_count > 1:
            embed.add_field(name="Треки", value=str(track_count))
        else:
            embed.add_field(name="Треки", value="Сингл")

    if likes_count:
        embed.add_field(name="Лайки", value=str(likes_count))

    if len(labels) > 1:
        embed.add_field(name="Лейблы", value=", ".join(labels))
    else:
        embed.add_field(name="Лейбл", value=", ".join(labels))

    if not avail:
        embed.set_footer(text=f"Трек в данный момент недоступен.")

    return embed

async def process_track(track: yandex_music.Track) -> discord.Embed:
    """Generate track embed.

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
        title += ' <:explicit:1325879701117472869>'

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

async def process_artist(artist: yandex_music.Artist) -> discord.Embed:
    """Generate artist embed.

    Args:
        artist (yandex_music.Artist): Artist to process.

    Returns:
        discord.Embed: Artist embed.
    """
    
    name = cast(str, artist.name)
    likes_count = artist.likes_count
    avail = cast(bool, artist.available)
    counts = artist.counts
    description = artist.description
    ratings = artist.ratings
    popular_tracks = artist.popular_tracks
    
    if not artist.cover:
        cover_url = artist.get_op_image_url('400x400')
    else:
        cover_url = artist.cover.get_url(size='400x400')
    color = await get_average_color_from_url(cover_url)
    
    embed = discord.Embed(
        title=name,
        description=description.text if description else None,
        color=color,
    )
    embed.set_thumbnail(url=cover_url)

    if likes_count:
        embed.add_field(name="Лайки", value=str(likes_count))
    
    # if ratings:
    #    embed.add_field(name="Слушателей за месяц", value=str(ratings.month))  # Wrong numbers?
    
    if counts:
        embed.add_field(name="Треки", value=str(counts.tracks))
    
        embed.add_field(name="Альбомы", value=str(counts.direct_albums))
    
    if artist.genres:
        genres = [genre.capitalize() for genre in artist.genres]
        if len(genres) > 1:
            embed.add_field(name="Жанры", value=", ".join(genres))
        else:
            embed.add_field(name="Жанр", value=", ".join(genres))
    
    if not avail:
        embed.set_footer(text=f"Артист в данный момент недоступен.")
    
    return embed