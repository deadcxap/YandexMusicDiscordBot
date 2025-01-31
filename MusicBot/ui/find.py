import logging
from typing import Any, Literal, cast

import discord
from yandex_music import Track, Album, Artist, Playlist

from discord.ui import View, Button, Item
from discord import ButtonStyle, Interaction

from MusicBot.cogs.utils.voice_extension import VoiceExtension

class PlayButton(Button, VoiceExtension):
    def __init__(self, item: Track | Album | Artist | Playlist | list[Track], **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
        self.item = item

    async def callback(self, interaction: Interaction) -> None:
        logging.debug(f"Callback triggered for type: '{type(self.item).__name__}'")

        if not interaction.guild:
            logging.warning("No guild found in PlayButton callback")
            return
        
        if not await self.voice_check(interaction):
            logging.debug("Voice check failed in PlayButton callback")
            return

        gid = interaction.guild.id
        guild = self.db.get_guild(gid)
        channel = cast(discord.VoiceChannel, interaction.channel)
        member = cast(discord.Member, interaction.user)
        action: Literal['add_track', 'add_album', 'add_artist', 'add_playlist']

        if isinstance(self.item, Track):
            tracks = [self.item]
            action = 'add_track'
            vote_message = f"{member.mention} хочет добавить трек **{self.item.title}** в очередь.\n\n Голосуйте за добавление."
            response_message = f"Трек **{self.item.title}** был добавлен в очередь."

        elif isinstance(self.item, Album):
            album = await self.item.with_tracks_async()
            if not album or not album.volumes:
                logging.debug("Failed to fetch album tracks in PlayButton callback")
                await interaction.respond("Не удалось получить треки альбома.", ephemeral=True)
                return

            tracks = [track for volume in album.volumes for track in volume]
            action = 'add_album'
            vote_message = f"{member.mention} хочет добавить альбом **{self.item.title}** в очередь.\n\n Голосуйте за добавление."
            response_message = f"Альбом **{self.item.title}** был добавлен в очередь."

        elif isinstance(self.item, Artist):
            artist_tracks = await self.item.get_tracks_async()
            if not artist_tracks:
                logging.debug("Failed to fetch artist tracks in PlayButton callback")
                await interaction.respond("Не удалось получить треки артиста.", ephemeral=True)
                return

            tracks = artist_tracks.tracks.copy()
            action = 'add_artist'
            vote_message = f"{member.mention} хочет добавить треки от **{self.item.name}** в очередь.\n\n Голосуйте за добавление."
            response_message = f"Песни артиста **{self.item.name}** были добавлены в очередь."

        elif isinstance(self.item, Playlist):
            short_tracks = await self.item.fetch_tracks_async()
            if not short_tracks:
                logging.debug("Failed to fetch playlist tracks in PlayButton callback")
                await interaction.respond("❌ Не удалось получить треки из плейлиста.", delete_after=15)
                return

            tracks = [cast(Track, short_track.track) for short_track in short_tracks]
            action = 'add_playlist'
            vote_message = f"{member.mention} хочет добавить плейлист **{self.item.title}** в очередь.\n\n Голосуйте за добавление."
            response_message = f"Плейлист **{self.item.title}** был добавлен в очередь."

        elif isinstance(self.item, list):
            tracks = self.item.copy()
            if not tracks:
                logging.debug("Empty tracks list in PlayButton callback")
                await interaction.respond("❌ Не удалось получить треки.", delete_after=15)
                return

            action = 'add_playlist'
            vote_message = f"{member.mention} хочет добавить плейлист **** в очередь.\n\n Голосуйте за добавление."
            response_message = f"Плейлист **«Мне нравится»** был добавлен в очередь."

        else:
            raise ValueError(f"Unknown item type: '{type(self.item).__name__}'")

        if guild.get(f'vote_{action}') and len(channel.members) > 2 and not member.guild_permissions.manage_channels:
            logging.debug(f"Starting vote for '{action}' (from PlayButton callback)")

            message = cast(discord.Interaction, await interaction.respond(vote_message, delete_after=30))
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
                    'action': action,
                    'vote_content': [track.to_dict() for track in tracks]
                }
            )
        else:
            logging.debug(f"Skipping vote for '{action}' (from PlayButton callback)")

            if guild['current_track'] is not None:
                self.db.modify_track(gid, tracks, 'next', 'extend')
            else:
                track = tracks.pop(0)
                self.db.modify_track(gid, tracks, 'next', 'extend')
                await self.play_track(interaction, track)
                response_message = f"Сейчас играет: **{track.title}**!"
            
            current_menu = None
            if guild['current_menu']:
                current_menu = await self.get_menu_message(interaction, guild['current_menu'])

            if current_menu and interaction.message:
                logging.debug(f"Deleting interaction message {interaction.message.id}: current player {current_menu.id} found")
                await interaction.message.delete()
            else:
                await interaction.respond(response_message, delete_after=15)

class MyVibeButton(Button, VoiceExtension):
    def __init__(self, item: Track | Album | Artist | Playlist | list[Track], *args, **kwargs):
        Button.__init__(self, *args, **kwargs)
        VoiceExtension.__init__(self, None)
        self.item = item
    
    async def callback(self, interaction: discord.Interaction):
        logging.debug(f"[VIBE] Button callback for '{type(self.item).__name__}'")
        if not await self.voice_check(interaction):
            return

        gid = interaction.guild_id
        if not gid:
            logging.warning(f"[VIBE] Guild ID is None in button callback")
            return

        guild = self.db.get_guild(gid)
        channel = cast(discord.VoiceChannel, interaction.channel)

        if len(channel.members) > 2 and not guild['always_allow_menu']:
            logging.info(f"[VIBE] Button callback declined: other members are present in the voice channel")
            await interaction.respond("❌ Вы не единственный в голосовом канале.", ephemeral=True)
            return

        track_type_map: dict[Any, Literal['track', 'album', 'artist', 'playlist', 'user']] = {
            Track: 'track', Album: 'album', Artist: 'artist', Playlist: 'playlist', list: 'user'
        }  # NOTE: Likes playlist should have its own entry instead of 'user:onyourwave'

        await self.send_menu_message(interaction)
        await self.update_vibe(
            interaction,
            track_type_map[type(self.item)],
            cast(int, self.item.uid) if isinstance(self.item, Playlist) else cast(int | str, self.item.id) if not isinstance(self.item, list) else 'onyourwave'
        )

class ListenView(View):
    def __init__(self, item: Track | Album | Artist | Playlist | list[Track], *items: Item, timeout: float | None = 360, disable_on_timeout: bool = True):
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        logging.debug(f"Creating view for type: '{type(item).__name__}'")

        if isinstance(item, Track):
            link_app = f"yandexmusic://album/{item.albums[0].id}/track/{item.id}"
            link_web = f"https://music.yandex.ru/album/{item.albums[0].id}/track/{item.id}"
        elif isinstance(item, Album):
            link_app = f"yandexmusic://album/{item.id}"
            link_web = f"https://music.yandex.ru/album/{item.id}"
        elif isinstance(item, Artist):
            link_app = f"yandexmusic://artist/{item.id}"
            link_web = f"https://music.yandex.ru/artist/{item.id}"
        elif isinstance(item, Playlist):
            link_app = f"yandexmusic://playlist/{item.playlist_uuid}"
            link_web = f"https://music.yandex.ru/playlist/{item.playlist_uuid}"
        elif isinstance(item, list):  # Can't open other person's likes
            self.add_item(PlayButton(item, label="Слушать в голосовом канале", style=ButtonStyle.gray))
            return

        self.button1: Button = Button(label="Слушать в приложении", style=ButtonStyle.gray, url=link_app, row=0)
        self.button2: Button = Button(label="Слушать в браузере", style=ButtonStyle.gray, url=link_web, row=0)
        self.button3: PlayButton = PlayButton(item, label="Слушать в голосовом канале", style=ButtonStyle.gray, row=0)
        self.button4: MyVibeButton = MyVibeButton(item, label="Моя Волна", style=ButtonStyle.gray, emoji="🌊", row=1)

        if item.available:
            # self.add_item(self.button1)  # Discord doesn't allow well formed URLs in buttons for some reason.
            self.add_item(self.button2)
            self.add_item(self.button3)
            self.add_item(self.button4)
