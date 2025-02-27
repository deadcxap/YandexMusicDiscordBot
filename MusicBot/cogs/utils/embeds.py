import logging
from functools import lru_cache
from typing import cast, Final
from math import ceil
from os import getenv

import aiohttp
from io import BytesIO
from PIL import Image

from yandex_music import Track, Album, Artist, Playlist, Label
from discord import Embed

explicit_eid: Final[str | None] = getenv('EXPLICIT_EID')
if not explicit_eid:
    raise ValueError('You must specify explicit emoji id in your enviroment (EXPLICIT_EID).')

async def generate_item_embed(item: Track | Album | Artist | Playlist | list[Track], vibing: bool = False) -> Embed:
    """Generate item embed. list[Track] is used for likes. If vibing is True, add vibing image.

    Args:
        item (Track | Album | Artist | Playlist | list[Track]): Item to be processed.
        vibing (bool, optional): Add vibing image. Defaults to False.

    Returns:
        discord.Embed: Item embed.
    """
    logging.debug(f"[EMBEDS] Generating embed for type: '{type(item).__name__}'")

    match item:
        case Track():
            embed = await _generate_track_embed(item)
        case Album():
            embed = await _generate_album_embed(item)
        case Artist():
            embed = await _generate_artist_embed(item)
        case Playlist():
            embed = await _generate_playlist_embed(item)
        case list():
            embed = _generate_likes_embed(item)
        case _:
            raise ValueError(f"Unknown item type: {type(item).__name__}")
    
    if vibing:
        embed.set_image(
            url="https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExaWN5dG50YWtxeDcwNnZpaDdqY3A3bHBsYXkyb29rdXoyajNjdWMxYiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/IilXmX8tjwfXgSwjBr/giphy.gif"
        )
    return embed

def _generate_likes_embed(tracks: list[Track]) -> Embed:
    cover_url = "https://avatars.yandex.net/get-music-user-playlist/11418140/favorit-playlist-cover.bb48fdb9b9f4/300x300"

    embed = Embed(
        title="Мне нравится",
        description="Треки, которые вам понравились.",
        color=0xce3a26
    )
    embed.set_thumbnail(url=cover_url)

    duration = 0
    for track in tracks:
        if track.duration_ms:
            duration += track.duration_ms

    embed.add_field(name="Длительность", value=_format_duration(duration))
    embed.add_field(name="Треки", value=str(len(tracks)))

    return embed

async def _generate_track_embed(track: Track) -> Embed:
    title = track.title
    albums = [cast(str, album.title) for album in track.albums]
    explicit = track.explicit or track.content_warning
    year = track.albums[0].year if track.albums else None
    artist = track.artists[0] if track.artists else None

    if track.cover_uri:
        cover_url = track.get_cover_url('400x400')
        color = await _get_average_color_from_url(cover_url)
    else:
        cover_url = None
        color = 0x000

    if explicit and title:
        title += ' <:explicit:' + explicit_eid + '>'

    if artist:
        artist_url = f"https://music.yandex.ru/artist/{artist.id}"
        artist_cover = artist.cover

        if not artist_cover and artist.op_image:
            artist_cover_url = artist.get_op_image_url()
        elif artist_cover:
            artist_cover_url = artist_cover.get_url()
        else:
            artist_cover_url = None
    else:
        artist_url = None
        artist_cover_url = None

    embed = Embed(
        title=title,
        description=", ".join(albums),
        color=color
    )
    embed.set_thumbnail(url=cover_url)
    embed.set_author(name=", ".join(track.artists_name()), url=artist_url, icon_url=artist_cover_url)

    embed.add_field(name="Текст песни", value="Есть" if track.lyrics_available else "Нет")
    
    if isinstance(track.duration_ms, int):
        embed.add_field(name="Длительность", value=_format_duration(track.duration_ms))

    if year:
        embed.add_field(name="Год выпуска", value=str(year))

    if track.background_video_uri:
        embed.add_field(name="Видеофон", value=f"[Ссылка]({track.background_video_uri})")

    if not (track.available or track.available_for_premium_users):
        embed.set_footer(text=f"Трек в данный момент недоступен.")

    return embed

async def _generate_album_embed(album: Album) -> Embed:
    title = album.title
    explicit = album.explicit or album.content_warning
    artist = album.artists[0]
    cover_url = album.get_cover_url('400x400')

    if isinstance(album.labels[0], Label):
        labels = [cast(Label, label).name for label in album.labels]
    else:
        labels = [cast(str, label) for label in album.labels]

    if album.version and title:
        title += f' *{album.version}*'

    if explicit and title:
        title += ' <:explicit:' + explicit_eid + '>'

    artist_url = f"https://music.yandex.ru/artist/{artist.id}"
    artist_cover = artist.cover

    if not artist_cover and artist.op_image:
        artist_cover_url = artist.get_op_image_url('400x400')
    elif artist_cover:
        artist_cover_url = artist_cover.get_url(size='400x400')
    else:
        artist_cover_url = None

    embed = Embed(
        title=title,
        description=album.short_description,
        color=await _get_average_color_from_url(cover_url)
    )
    embed.set_thumbnail(url=cover_url)
    embed.set_author(name=", ".join(album.artists_name()), url=artist_url, icon_url=artist_cover_url)

    if album.year:
        embed.add_field(name="Год выпуска", value=str(album.year))

    if isinstance(album.duration_ms, int):
        embed.add_field(name="Длительность", value=_format_duration(album.duration_ms))

    if album.track_count is not None:
        embed.add_field(name="Треки", value=str(album.track_count) if album.track_count > 1 else "Сингл")

    if album.likes_count is not None:
        embed.add_field(name="Лайки", value=str(album.likes_count))

    embed.add_field(name="Лейблы" if len(labels) > 1 else "Лейбл", value=", ".join(labels))

    if not (album.available or album.available_for_premium_users):
        embed.set_footer(text=f"Альбом в данный момент недоступен.")

    return embed

async def _generate_artist_embed(artist: Artist) -> Embed:
    if not artist.cover:
        cover_url = artist.get_op_image_url('400x400')
    else:
        cover_url = artist.cover.get_url(size='400x400')

    embed = Embed(
        title=artist.name,
        description=artist.description.text if artist.description else None,
        color=await _get_average_color_from_url(cover_url)
    )
    embed.set_thumbnail(url=cover_url)

    if artist.likes_count:
        embed.add_field(name="Лайки", value=str(artist.likes_count))

    # if ratings:
    #    embed.add_field(name="Слушателей за месяц", value=str(ratings.month))  # Wrong numbers

    if artist.counts:
        embed.add_field(name="Треки", value=str(artist.counts.tracks))
    
        embed.add_field(name="Альбомы", value=str(artist.counts.direct_albums))

    if artist.genres:
        genres = [genre.capitalize() for genre in artist.genres]
        if len(genres) > 1:
            embed.add_field(name="Жанры", value=", ".join(genres))
        else:
            embed.add_field(name="Жанр", value=", ".join(genres))

    if not artist.available or artist.reason:
        embed.set_footer(text=f"Артист в данный момент недоступен.")

    return embed
    
async def _generate_playlist_embed(playlist: Playlist) -> Embed:
    if playlist.cover and playlist.cover.uri:
        cover_url = f"https://{playlist.cover.uri.replace('%%', '400x400')}"
    else:
        tracks = await playlist.fetch_tracks_async()
        for track_short in tracks:
            track = track_short.track
            if track and track.albums and track.albums[0].cover_uri:
                cover_url = f"https://{track.albums[0].cover_uri.replace('%%', '400x400')}"
                break
        else:
            cover_url = None

    if cover_url:
        color = await _get_average_color_from_url(cover_url)
    else:
        color = 0x000

    embed = Embed(
        title=playlist.title,
        description=playlist.description,
        color=color
    )
    embed.set_thumbnail(url=cover_url)

    if playlist.created:
        embed.add_field(name="Год создания", value=str(playlist.created).split('-')[0])

    if playlist.modified:
        embed.add_field(name="Изменён", value=str(playlist.modified).split('-')[0])

    if playlist.duration_ms:
        embed.add_field(name="Длительность", value=_format_duration(playlist.duration_ms))

    if playlist.track_count is not None:
        embed.add_field(name="Треки", value=str(playlist.track_count))

    if playlist.likes_count:
        embed.add_field(name="Лайки", value=str(playlist.likes_count))

    if not playlist.available:
        embed.set_footer(text=f"Плейлист в данный момент недоступен.")

    return embed

@lru_cache()
async def _get_average_color_from_url(url: str) -> int:
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
    except (aiohttp.ClientError, IOError, ValueError):
        return 0x000

def _format_duration(duration_ms: int) -> str:
    duration_m = duration_ms // 60000
    duration_s = ceil(duration_ms / 1000) - duration_m * 60
    if duration_s == 60:
        duration_m += 1
        duration_s = 0
    return f"{duration_m}:{duration_s:02}"