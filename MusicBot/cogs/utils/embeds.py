import logging
from typing import cast
from math import ceil
from os import getenv

import aiohttp
from io import BytesIO
from PIL import Image

from yandex_music import Track, Album, Artist, Playlist, Label
from discord import Embed

async def generate_item_embed(item: Track | Album | Artist | Playlist | list[Track], vibing: bool = False) -> Embed:
    """Generate item embed. list[Track] is used for likes. If vibing is True, add vibing image.

    Args:
        item (yandex_music.Track | yandex_music.Album | yandex_music.Artist | yandex_music.Playlist): Item to be processed.

    Returns:
        discord.Embed: Item embed.
    """
    logging.debug(f"[EMBEDS] Generating embed for type: '{type(item).__name__}'")

    if isinstance(item, Track):
        embed = await _generate_track_embed(item)
    elif isinstance(item, Album):
        embed = await _generate_album_embed(item)
    elif isinstance(item, Artist):
        embed = await _generate_artist_embed(item)
    elif isinstance(item, Playlist):
        embed = await _generate_playlist_embed(item)
    elif isinstance(item, list):
        embed = _generate_likes_embed(item)
    else:
        raise ValueError(f"Unknown item type: {type(item).__name__}")
    
    if vibing:
        embed.set_image(
            url="https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExaWN5dG50YWtxeDcwNnZpaDdqY3A3bHBsYXkyb29rdXoyajNjdWMxYiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/IilXmX8tjwfXgSwjBr/giphy.gif"
        )
    return embed

def _generate_likes_embed(tracks: list[Track]) -> Embed:
    track_count = len(tracks)
    cover_url = "https://avatars.yandex.net/get-music-user-playlist/11418140/favorit-playlist-cover.bb48fdb9b9f4/300x300"

    embed = Embed(
        title="Мне нравится",
        description="Треки, которые вам понравились.",
        color=0xce3a26,
    )
    embed.set_thumbnail(url=cover_url)

    duration = 0
    for track in tracks:
        if track.duration_ms:
            duration += track.duration_ms

    duration_m = duration // 60000
    duration_s = ceil(duration / 1000) - duration_m * 60
    if duration_s == 60:
        duration_m += 1
        duration_s = 0

    embed.add_field(name="Длительность", value=f"{duration_m}:{duration_s:02}")

    if track_count is not None:
        embed.add_field(name="Треки", value=str(track_count))

    return embed

async def _generate_track_embed(track: Track) -> Embed:
    title = cast(str, track.title)
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
    color = await _get_average_color_from_url(cover_url)

    if explicit:
        explicit_eid = getenv('EXPLICIT_EID')
        if not explicit_eid:
            raise ValueError('You must specify explicit emoji id in your enviroment (EXPLICIT_EID).')
        title += ' <:explicit:' + explicit_eid + '>'

    duration_m = duration // 60000
    duration_s = ceil(duration / 1000) - duration_m * 60
    if duration_s == 60:
        duration_m += 1
        duration_s = 0

    artist_url = f"https://music.yandex.ru/artist/{artist.id}"
    artist_cover = artist.cover
    if not artist_cover:
        artist_cover_url = artist.get_op_image_url()
    else:
        artist_cover_url = artist_cover.get_url()

    embed = Embed(
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

async def _generate_album_embed(album: Album) -> Embed:
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
    color = await _get_average_color_from_url(cover_url)

    if isinstance(album.labels[0], Label):
        labels = [cast(Label, label).name for label in album.labels]
    else:
        labels = [cast(str, label) for label in album.labels]

    if version:
        title += f' *{version}*'

    if explicit:
        explicit_eid = getenv('EXPLICIT_EID')
        if not explicit_eid:
            raise ValueError('You must specify explicit emoji id in your enviroment.')
        title += ' <:explicit:' + explicit_eid + '>'

    artist_url = f"https://music.yandex.ru/artist/{artist.id}"
    artist_cover = artist.cover
    if not artist_cover:
        artist_cover_url = artist.get_op_image_url()
    else:
        artist_cover_url = artist_cover.get_url()

    embed = Embed(
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
        if duration_s == 60:
            duration_m += 1
            duration_s = 0
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
        embed.set_footer(text=f"Альбом в данный момент недоступен.")

    return embed

async def _generate_artist_embed(artist: Artist) -> Embed:
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
    color = await _get_average_color_from_url(cover_url)

    embed = Embed(
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
    
async def _generate_playlist_embed(playlist: Playlist) -> Embed:
    title = cast(str, playlist.title)
    track_count = playlist.track_count
    avail = cast(bool, playlist.available)
    description = playlist.description_formatted
    year = playlist.created
    modified = playlist.modified
    duration = playlist.duration_ms
    likes_count = playlist.likes_count

    color = 0x000
    cover_url = None

    if playlist.cover and playlist.cover.uri:
        cover_url = f"https://{playlist.cover.uri.replace('%%', '400x400')}"
    else:
        tracks = await playlist.fetch_tracks_async()
        for i in range(len(tracks)):
            track = tracks[i].track
            if not track or not track.albums or not track.albums[0].cover_uri:
                continue

    if cover_url:
        color = await _get_average_color_from_url(cover_url)

    embed = Embed(
        title=title,
        description=description,
        color=color,
    )
    embed.set_thumbnail(url=cover_url)

    if year:
        embed.add_field(name="Год создания", value=str(year).split('-')[0])

    if modified:
        embed.add_field(name="Изменён", value=str(modified).split('-')[0])

    if duration:
        duration_m = duration // 60000
        duration_s = ceil(duration / 1000) - duration_m * 60
        if duration_s == 60:
            duration_m += 1
            duration_s = 0
        embed.add_field(name="Длительность", value=f"{duration_m}:{duration_s:02}")

    if track_count is not None:
        embed.add_field(name="Треки", value=str(track_count))

    if likes_count:
        embed.add_field(name="Лайки", value=str(likes_count))

    if not avail:
        embed.set_footer(text=f"Плейлист в данный момент недоступен.")

    return embed

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
    except Exception:
        return 0x000
