import logging
from typing import Self, cast

from discord.ui import View, Button, Item, Select
from discord import VoiceChannel, ButtonStyle, Interaction, ApplicationContext, RawReactionActionEvent, Embed, ComponentType, SelectOption

import yandex_music.exceptions
from yandex_music import Track, Playlist, ClientAsync as YMClient
from MusicBot.cogs.utils.voice_extension import VoiceExtension, menu_views

class ToggleRepeatButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        logging.info('[MENU] Repeat button callback...')
        if not await self.voice_check(interaction) or not interaction.guild:
            return
        gid = interaction.guild.id
        guild = self.db.get_guild(gid)
        self.db.update(gid, {'repeat': not guild['repeat']})

        if gid in menu_views:
            menu_views[gid].stop()
        menu_views[gid] = await MenuView(interaction).init()
        await interaction.edit(view=menu_views[gid])

class ToggleShuffleButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        logging.info('[MENU] Shuffle button callback...')
        if not await self.voice_check(interaction) or not interaction.guild:
            return
        gid = interaction.guild.id
        guild = self.db.get_guild(gid)
        self.db.update(gid, {'shuffle': not guild['shuffle']})

        if gid in menu_views:
            menu_views[gid].stop()
        menu_views[gid] = await MenuView(interaction).init()
        await interaction.edit(view=menu_views[gid])

class PlayPauseButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        logging.info('[MENU] Play/Pause button callback...')
        if not await self.voice_check(interaction):
            return

        vc = await self.get_voice_client(interaction)
        if not vc or not interaction.message:
            return

        embed = interaction.message.embeds[0]

        if vc.is_paused():
            vc.resume()
            embed.remove_footer()
        else:
            vc.pause()
            embed.set_footer(text='Приостановлено')

        await interaction.edit(embed=embed)

class NextTrackButton(Button, VoiceExtension):    
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        logging.info('[MENU] Next track button callback...')
        if not await self.voice_check(interaction):
            return
        title = await self.next_track(interaction, button_callback=True)
        if not title:
            await interaction.respond(f"Нет треков в очереди.", delete_after=15, ephemeral=True)

class PrevTrackButton(Button, VoiceExtension):    
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        logging.info('[MENU] Previous track button callback...')
        if not await self.voice_check(interaction):
            return
        title = await self.prev_track(interaction, button_callback=True)
        if not title:
            await interaction.respond(f"Нет треков в истории.", delete_after=15, ephemeral=True)

class LikeButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)

    async def callback(self, interaction: Interaction) -> None:
        logging.info('[MENU] Like button callback...')
        if not await self.voice_check(interaction):
            return

        if not interaction.guild:
            return
        gid = interaction.guild.id

        if not (vc := await self.get_voice_client(interaction)) or not vc.is_playing:
            await interaction.respond("❌ Нет воспроизводимого трека.", delete_after=15, ephemeral=True)

        await self.like_track(interaction)

        if gid in menu_views:
            menu_views[gid].stop()
        menu_views[gid] = await MenuView(interaction).init()
        await interaction.edit(view=menu_views[gid])

class DislikeButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)

    async def callback(self, interaction: Interaction) -> None:
        logging.info('[MENU] Dislike button callback...')
        if not await self.voice_check(interaction):
            return

        if not (vc := await self.get_voice_client(interaction)) or not vc.is_playing:
            await interaction.respond("❌ Нет воспроизводимого трека.", delete_after=15, ephemeral=True)

        res = await self.dislike_track(interaction)
        if res:
            logging.debug("[VC_EXT] Disliked track")
            await self.next_track(interaction, vc=vc, button_callback=True)
        else:
            logging.debug("[VC_EXT] Failed to dislike track")
            await interaction.respond("❌ Не удалось поставить дизлайк. Попробуйте позже.")

class LyricsButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
        
    async def callback(self, interaction: Interaction) -> None:
        logging.info('[MENU] Lyrics button callback...')

        if not await self.voice_check(interaction) or not interaction.guild_id or not interaction.user:
            return
        
        ym_token = self.users_db.get_ym_token(interaction.user.id)        
        current_track = self.db.get_track(interaction.guild_id, 'current')
        if not current_track or not ym_token:
            return

        track = cast(Track, Track.de_json(
            current_track,
            YMClient(ym_token),  # type: ignore  # Async client can be used here
        ))

        try:
            lyrics = await track.get_lyrics_async()
        except yandex_music.exceptions.NotFoundError:
            logging.debug('[MENU] Lyrics not found')
            await interaction.respond("❌ Текст песни не найден. Яндекс нам соврал (опять)!", delete_after=15, ephemeral=True)
            return

        if not lyrics:
            logging.debug('[MENU] Lyrics not found')
            return

        embed = Embed(
            title=track.title,
            description='**Текст песни**',
            color=0xfed42b,
        )
        text = await lyrics.fetch_lyrics_async()
        for subtext in text.split('\n\n'):
            embed.add_field(name='', value=subtext, inline=False)
        await interaction.respond(embed=embed, ephemeral=True)

class MyVibeButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        logging.info('[VIBE] My vibe button callback')
        if not await self.voice_check(interaction):
            return
        if not interaction.guild_id:
            logging.warning('[VIBE] No guild id in button callback')
            return

        track = self.db.get_track(interaction.guild_id, 'current')
        if track:
            logging.info(f"[MENU] Playing vibe for track '{track["id"]}'")
            await self.update_vibe(
                interaction,
                'track',
                track['id'],
                button_callback=True
            )
        else:
            logging.info('[VIBE] Playing on your wave')
            await self.update_vibe(
                interaction,
                'user',
                'onyourwave',
                button_callback=True
            )

class MyVibeSelect(Select, VoiceExtension):
    def __init__(self, *args,  **kwargs):
        super().__init__(*args, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        logging.info('[VIBE] My vibe select callback')
        if not interaction.user:
            logging.warning('[VIBE] No user in select callback')
            return
        
        custom_id = interaction.custom_id
        if custom_id not in ('diversity', 'mood', 'lang'):
            logging.warning(f'[VIBE] Unknown custom_id: {custom_id}')
            return

        data = interaction.data
        if not data or 'values' not in data:
            logging.warning('[VIBE] No data in select callback')
            return
        
        data_value = data['values'][0]
        if data_value not in (
            'fun', 'active', 'calm', 'sad', 'all',
            'favorite', 'popular', 'discover', 'default',
            'not-russian', 'russian', 'without-words', 'any'
        ):
            logging.warning(f'[VIBE] Unknown data_value: {data_value}')
            return

        logging.info(f"[VIBE] Settings option '{custom_id}' updated to {data_value}")
        self.users_db.update(interaction.user.id, {f'vibe_settings.{custom_id}': data_value})
        
        view = MyVibeSettingsView(interaction)
        view.disable_all_items()
        await interaction.edit(view=view)

        await self.update_vibe(interaction, 'user', 'onyourwave', update_settings=True)
        view.enable_all_items()
        await interaction.edit(view=view)

class MyVibeSettingsView(View, VoiceExtension):
    def __init__(self, interaction: Interaction, *items: Item, timeout: float | None = 360, disable_on_timeout: bool = True):
        View.__init__(self, *items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        VoiceExtension.__init__(self, None)

        if not interaction.user:
            logging.warning('[VIBE] No user in settings view')
            return

        settings = self.users_db.get_user(interaction.user.id)['vibe_settings']
        
        diversity_settings = settings['diversity']
        diversity = [
            SelectOption(label='Любое', value='default'),
            SelectOption(label='Любимое', value='favorite', default=diversity_settings == 'favorite'),
            SelectOption(label='Незнакомое', value='discover', default=diversity_settings == 'discover'),
            SelectOption(label='Популярное', value='popular', default=diversity_settings == 'popular')
        ]
        
        mood_settings = settings['mood']
        mood = [
            SelectOption(label='Любое', value='all'),
            SelectOption(label='Бодрое', value='active', default=mood_settings == 'active'),
            SelectOption(label='Весёлое', value='fun', default=mood_settings == 'fun'),
            SelectOption(label='Спокойное', value='calm', default=mood_settings == 'calm'),
            SelectOption(label='Грустное', value='sad', default=mood_settings == 'sad')
        ]
        
        lang_settings = settings['lang']
        lang = [
            SelectOption(label='Любое', value='any'),
            SelectOption(label='Русский', value='russian', default=lang_settings == 'russian'),
            SelectOption(label='Иностранный', value='not-russian', default=lang_settings == 'not-russian'),
            SelectOption(label='Без слов', value='without-words', default=lang_settings == 'without-words')
        ]

        feel_select = MyVibeSelect(
            ComponentType.string_select,
            placeholder='По характеру',
            options=diversity,
            row=0,
            custom_id='diversity'
        )
        mood_select = MyVibeSelect(
            ComponentType.string_select,
            placeholder='По настроению',
            options=mood,
            row=1,
            custom_id='mood'
        )
        lang_select = MyVibeSelect(
            ComponentType.string_select,
            placeholder='По языку',
            options=lang,
            row=2,
            custom_id='lang'
        )
        for select in [feel_select, mood_select, lang_select]:
            self.add_item(select)

class MyVibeSettingsButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        logging.info('[VIBE] My vibe settings button callback')
        if not await self.voice_check(interaction):
            return
        
        await interaction.respond('Настройки "Моей Волны"', view=MyVibeSettingsView(interaction), ephemeral=True)

class AddToPlaylistSelect(Select, VoiceExtension):
    def __init__(self, ym_client: YMClient, *args, **kwargs):
        super().__init__(*args, **kwargs)
        VoiceExtension.__init__(self, None)
        self.ym_client = ym_client
        
    async def callback(self, interaction: Interaction):
        if not interaction.data or not interaction.guild_id:
            return
        if not interaction.data or 'values' not in interaction.data:
            logging.warning('[MENU] No data in select callback')
            return

        data = interaction.data['values'][0].split(';')
        logging.debug(f"[MENU] Add to playlist select callback: {data}")

        playlist = cast(Playlist, await self.ym_client.users_playlists(kind=data[0], user_id=data[1]))
        current_track = self.db.get_track(interaction.guild_id, 'current')
        if not current_track:
            return

        try:
            res = await self.ym_client.users_playlists_insert_track(
                kind=f"{playlist.kind}",
                track_id=current_track['id'],
                album_id=current_track['albums'][0]['id'],
                revision=playlist.revision or 1,
                user_id=f"{playlist.uid}"
            )
        except yandex_music.exceptions.NetworkError:
            res = None

        # value=f"{playlist.kind or "-1"};{current_track['id']};{current_track['albums'][0]['id']};{playlist.revision};{playlist.uid}"

        if res:
            await interaction.respond('✅ Добавлено в плейлист', delete_after=15, ephemeral=True)
        else:
            await interaction.respond('❌ Что-то пошло не так. Попробуйте позже.', delete_after=15, ephemeral=True)

class AddToPlaylistButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction):
        if not await self.voice_check(interaction) or not interaction.guild_id:
            return

        client = await self.init_ym_client(interaction)
        if not client or not client.me or not client.me.account or not client.me.account.uid:
            await interaction.respond('❌ Что-то пошло не так. Попробуйте позже.', ephemeral=True)
            return

        if not (vc := await self.get_voice_client(interaction)) or not vc.is_playing:
            await interaction.respond("❌ Нет воспроизводимого трека.", delete_after=15, ephemeral=True)
            return

        view = View(
            AddToPlaylistSelect(
                client,
                ComponentType.string_select,
                placeholder='Выберите плейлист',
                options=[
                    SelectOption(
                        label=playlist.title or "Без названия",
                        value=f"{playlist.kind or "-1"};{playlist.uid}"
                    ) for playlist in await client.users_playlists_list(client.me.account.uid)
                ]
            )
        )

        await interaction.respond(view=view, ephemeral=True, delete_after=360)


class MenuView(View, VoiceExtension):
    
    def __init__(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, *items: Item, timeout: float | None = 3600, disable_on_timeout: bool = False):
        View.__init__(self, *items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        VoiceExtension.__init__(self, None)
        if not ctx.guild_id:
            return
        self.ctx = ctx
        self.guild = self.db.get_guild(ctx.guild_id)

        self.repeat_button = ToggleRepeatButton(style=ButtonStyle.success if self.guild['repeat'] else ButtonStyle.secondary, emoji='🔂', row=0)
        self.shuffle_button = ToggleShuffleButton(style=ButtonStyle.success if self.guild['shuffle'] else ButtonStyle.secondary, emoji='🔀', row=0)
        self.play_pause_button = PlayPauseButton(style=ButtonStyle.primary, emoji='⏯', row=0)
        self.next_button = NextTrackButton(style=ButtonStyle.primary, emoji='⏭', row=0)
        self.prev_button = PrevTrackButton(style=ButtonStyle.primary, emoji='⏮', row=0)
        
        self.like_button = LikeButton(style=ButtonStyle.secondary, emoji='❤️', row=1)
        self.dislike_button = DislikeButton(style=ButtonStyle.secondary, emoji='💔', row=1)
        self.lyrics_button = LyricsButton(style=ButtonStyle.secondary, emoji='📋', row=1)
        self.add_to_playlist_button = AddToPlaylistButton(style=ButtonStyle.secondary, emoji='📁', row=1)
        self.vibe_button = MyVibeButton(style=ButtonStyle.secondary, emoji='🌊', row=1)
        self.vibe_settings_button = MyVibeSettingsButton(style=ButtonStyle.success, emoji='🛠', row=1)
        
    async def init(self, *, disable: bool = False) -> Self:
        current_track = self.guild['current_track']
        likes = await self.get_likes(self.ctx)

        self.add_item(self.repeat_button)
        self.add_item(self.prev_button)
        self.add_item(self.play_pause_button)
        self.add_item(self.next_button)
        self.add_item(self.shuffle_button)
        
        if isinstance(self.ctx, RawReactionActionEvent) or len(cast(VoiceChannel, self.ctx.channel).members) > 2:
            self.like_button.disabled = True
        elif likes and current_track and str(current_track['id']) in [str(like.id) for like in likes]:
            self.like_button.style = ButtonStyle.success

        if not current_track or not current_track['lyrics_available']:
            self.lyrics_button.disabled = True

        self.add_item(self.like_button)
        self.add_item(self.dislike_button)
        self.add_item(self.lyrics_button)
        self.add_item(self.add_to_playlist_button)
        
        if self.guild['vibing']:
            self.add_item(self.vibe_settings_button)
        else:
            self.add_item(self.vibe_button)

        if disable:
            self.disable_all_items()

        return self

    async def on_timeout(self) -> None:
        logging.debug('Menu timed out...')
        if not self.ctx.guild_id:
            return
        
        if self.guild['current_menu']:
            await self.stop_playing(self.ctx)
            self.db.update(self.ctx.guild_id, {'current_menu': None, 'previous_tracks': [], 'vibing': False})
            message = await self.get_menu_message(self.ctx, self.guild['current_menu'])
            if message:
                await message.delete()
                logging.debug('Successfully deleted menu message')
            else:
                logging.debug('No menu message found')