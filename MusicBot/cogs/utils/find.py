from os import getenv
from math import ceil
from typing import cast

import discord
from yandex_music import Track, Album, Artist, Playlist, Label

from discord.ui import View, Button, Item
from discord import ButtonStyle, Interaction, Embed

from MusicBot.cogs.utils.voice_extension import VoiceExtension, get_average_color_from_url

class PlayTrackButton(Button, VoiceExtension):
    
    def __init__(self, track: Track, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
        self.track = track
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.guild or not await self.voice_check(interaction):
            return

        gid = interaction.guild.id
        guild = self.db.get_guild(gid)

        if guild['current_track']:
            self.db.modify_track(gid, self.track, 'next', 'append')
            response_message = f"Трек **{self.track.title}** был добавлен в очередь."
        else:
            await self.play_track(interaction, self.track)
            response_message = f"Сейчас играет: **{self.track.title}**!"

        if guild['current_player'] is not None and interaction.message:
            await interaction.message.delete()

        await interaction.respond(response_message, delete_after=15)

class PlayAlbumButton(Button, VoiceExtension):
    
    def __init__(self, album: Album, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
        self.album = album
        
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.guild or not await self.voice_check(interaction):
            return

        album = await self.album.with_tracks_async()
        if not album or not album.volumes:
            return

        gid = interaction.guild.id
        guild = self.db.get_guild(gid)

        tracks: list[Track] = [track for volume in album.volumes for track in volume]

        if guild['current_track'] is not None:
            self.db.modify_track(gid, tracks, 'next', 'extend')
            response_message = f"Альбом **{album.title}** был добавлен в очередь."
        else:
            track = tracks.pop(0)
            self.db.modify_track(gid, tracks, 'next', 'extend')
            await self.play_track(interaction, track)
            response_message = f"Сейчас играет: **{track.title}**!"

        if guild['current_player'] is not None and interaction.message:
            await interaction.message.delete()
        else:
            await interaction.respond(response_message, delete_after=15)

class PlayArtistButton(Button, VoiceExtension):
    def __init__(self, artist: Artist, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
        self.artist = artist
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.guild or not await self.voice_check(interaction):
            return

        artist_tracks = await self.artist.get_tracks_async(page_size=500)
        if not artist_tracks:
            return

        gid = interaction.guild.id
        guild = self.db.get_guild(gid)

        tracks: list[Track] = artist_tracks.tracks.copy()

        if guild['current_track'] is not None:
            self.db.modify_track(gid, tracks, 'next', 'extend')
            response_message = f"Песни артиста **{self.artist.name}** были добавлены в очередь."
        else:
            track = tracks.pop(0)
            self.db.modify_track(gid, tracks, 'next', 'extend')
            await self.play_track(interaction, track)
            response_message = f"Сейчас играет: **{track.title}**!"

        if guild['current_player'] is not None and interaction.message:
            await interaction.message.delete()

        await interaction.respond(response_message, delete_after=15)

class PlayPlaylistButton(Button, VoiceExtension):
    def __init__(self, playlist: Playlist, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
        self.playlist = playlist
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.guild or not await self.voice_check(interaction):
            return

        short_tracks = await self.playlist.fetch_tracks_async()
        if not short_tracks:
            await interaction.respond("Не удалось получить треки из плейлиста.", delete_after=15)
            return

        gid = interaction.guild.id
        guild = self.db.get_guild(gid)

        tracks: list[Track] = [cast(Track, short_track.track) for short_track in short_tracks]

        if guild['current_track'] is not None:
            self.db.modify_track(gid, tracks, 'next', 'extend')
            response_message = f"Плейлист **{self.playlist.title}** был добавлен в очередь."
        else:
            track = tracks.pop(0)
            self.db.modify_track(gid, tracks, 'next', 'extend')
            await self.play_track(interaction, track)
            response_message = f"Сейчас играет: **{self.playlist.title}**!"

        if guild['current_player'] is not None and interaction.message:
            await interaction.message.delete()

        await interaction.respond(response_message, delete_after=15)

class ListenTrack(View):
    
    def __init__(self, track: Track, album_id: int, *items: Item, timeout: float | None = None, disable_on_timeout: bool = False):
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        link_app = f"yandexmusic://album/{album_id}/track/{track.id}"
        link_web = f"https://music.yandex.ru/album/{album_id}/track/{track.id}"
        self.button1: Button = Button(label="Слушать в приложении", style=ButtonStyle.gray, url=link_app)
        self.button2: Button = Button(label="Слушать в браузере", style=ButtonStyle.gray, url=link_web)
        self.button3: PlayTrackButton = PlayTrackButton(track, label="Слушать в голосовом канале", style=ButtonStyle.gray)
        # self.add_item(self.button1)  # Discord doesn't allow well formed URLs in buttons for some reason.
        if track.available:
            self.add_item(self.button2)
            self.add_item(self.button3)
    
class ListenAlbum(View):
    
    def __init__(self, album: Album, *items: Item, timeout: float | None = None, disable_on_timeout: bool = False):
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        link_app = f"yandexmusic://album/{album.id}"
        link_web = f"https://music.yandex.ru/album/{album.id}"
        self.button1: Button = Button(label="Слушать в приложении", style=ButtonStyle.gray, url=link_app)
        self.button2: Button = Button(label="Слушать в браузере", style=ButtonStyle.gray, url=link_web)
        self.button3: PlayAlbumButton = PlayAlbumButton(album, label="Слушать в голосовом канале", style=ButtonStyle.gray)
        # self.add_item(self.button1)  # Discord doesn't allow well formed URLs in buttons for some reason.
        if album.available:
            self.add_item(self.button2)
            self.add_item(self.button3)

class ListenArtist(View):
    
    def __init__(self, artist: Artist, *items: Item, timeout: float | None = None, disable_on_timeout: bool = False):
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        link_app = f"yandexmusic://artist/{artist.id}"
        link_web = f"https://music.yandex.ru/artist/{artist.id}"
        self.button1: Button = Button(label="Слушать в приложении", style=ButtonStyle.gray, url=link_app)
        self.button2: Button = Button(label="Слушать в браузере", style=ButtonStyle.gray, url=link_web)
        self.button3: PlayArtistButton = PlayArtistButton(artist, label="Слушать в голосовом канале", style=ButtonStyle.gray)
        # self.add_item(self.button1)  # Discord doesn't allow well formed URLs in buttons for some reason.
        if artist.available:
            self.add_item(self.button2)
            self.add_item(self.button3)

class ListenPlaylist(View):
    def __init__(self, playlist: Playlist, *items: Item, timeout: float | None = None, disable_on_timeout: bool = False):
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        link_app = f"yandexmusic://playlist/{playlist.playlist_uuid}"
        link_web = f"https://music.yandex.ru/playlist/{playlist.playlist_uuid}"
        self.button1: Button = Button(label="Слушать в приложении", style=ButtonStyle.gray, url=link_app)
        self.button2: Button = Button(label="Слушать в браузере", style=ButtonStyle.gray, url=link_web)
        self.button3: PlayPlaylistButton = PlayPlaylistButton(playlist, label="Слушать в голосовом канале", style=ButtonStyle.gray)
        # self.add_item(self.button1)  # Discord doesn't allow well formed URLs in buttons for some reason.
        if playlist.available:
            self.add_item(self.button2)
            self.add_item(self.button3)

async def process_track(track: Track) -> Embed:
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
        explicit_eid = getenv('EXPLICIT_EID')
        if not explicit_eid:
            raise ValueError('You must specify explicit emoji id in your enviroment (EXPLICIT_EID).')
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

async def process_album(album: Album) -> Embed:
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
        embed.set_footer(text=f"Альбом в данный момент недоступен.")

    return embed

async def process_artist(artist: Artist) -> Embed:
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
    
async def process_playlist(playlist: Playlist) -> Embed:
    """Generate playlist embed.

    Args:
        playlist (yandex_music.Playlist): Playlist to process.

    Returns:
        discord.Embed: Playlist embed.
    """
    
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
            try:
                cover_url = f"https://{track.albums[0].cover_uri.replace('%%', '400x400')}"  # type: ignore  # Errors are being caught below.
                break
            except (TypeError, IndexError):
                continue

    if cover_url:
        color = await get_average_color_from_url(cover_url)

    embed = discord.Embed(
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
        embed.add_field(name="Длительность", value=f"{duration_m}:{duration_s:02}")

    if track_count is not None:
        embed.add_field(name="Треки", value=str(track_count))

    if likes_count:
        embed.add_field(name="Лайки", value=str(likes_count))

    if not avail:
        embed.set_footer(text=f"Плейлист в данный момент недоступен.")

    return embed