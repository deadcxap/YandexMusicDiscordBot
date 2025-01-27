import logging
from typing import Self, cast

from discord.ui import View, Button, Item, Modal, Select
from discord import VoiceChannel, ButtonStyle, Interaction, ApplicationContext, RawReactionActionEvent, Embed, ComponentType, SelectOption

import yandex_music.exceptions
from yandex_music import Track, ClientAsync
from MusicBot.cogs.utils.voice_extension import VoiceExtension

class ToggleRepeatButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        logging.info('Repeat button callback...')
        if not interaction.guild:
            return
        gid = interaction.guild.id
        guild = self.db.get_guild(gid)
        self.db.update(gid, {'repeat': not guild['repeat']})
        await interaction.edit(view=await MenuView(interaction).init())

class ToggleShuffleButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        logging.info('Shuffle button callback...')
        if not interaction.guild:
            return
        gid = interaction.guild.id
        guild = self.db.get_guild(gid)
        self.db.update(gid, {'shuffle': not guild['shuffle']})
        await interaction.edit(view=await MenuView(interaction).init())

class PlayPauseButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        logging.info('Play/Pause button callback...')
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
        logging.info('Next track button callback...')
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
        logging.info('Previous track button callback...')
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
        logging.info('Like button callback...')
        if not await self.voice_check(interaction):
            return
        
        if not (vc := await self.get_voice_client(interaction)) or not vc.is_playing:
            await interaction.respond("❌ Нет воспроизводимого трека.", delete_after=15, ephemeral=True)

        await self.like_track(interaction)
        await interaction.edit(view=await MenuView(interaction).init())

class LyricsButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
        
    async def callback(self, interaction: Interaction) -> None:
        logging.info('Lyrics button callback...')

        if not await self.voice_check(interaction) or not interaction.guild_id or not interaction.user:
            return
        
        ym_token = self.users_db.get_ym_token(interaction.user.id)        
        current_track = self.db.get_track(interaction.guild_id, 'current')
        if not current_track or not ym_token:
            return

        track = cast(Track, Track.de_json(
            current_track,
            ClientAsync(ym_token),  # type: ignore  # Async client can be used here
        ))

        try:
            lyrics = await track.get_lyrics_async()
        except yandex_music.exceptions.NotFoundError:
            logging.debug('Lyrics not found')
            await interaction.respond("❌ Текст песни не найден. Яндекс нам соврал (опять)!", delete_after=15, ephemeral=True)
            return

        if not lyrics:
            logging.debug('Lyrics not found')
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
            logging.info(f"[VIBE] Playing vibe for track '{track["id"]}'")
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
        self.lyrics_button = LyricsButton(style=ButtonStyle.secondary, emoji='📋', row=1)
        self.vibe_button = MyVibeButton(style=ButtonStyle.secondary, emoji='🌊', row=1)
        
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
        self.add_item(self.lyrics_button)
        self.add_item(self.vibe_button)

        if disable:
            self.disable_all_items()

        return self

    async def on_timeout(self) -> None:
        logging.debug('Menu timed out...')
        if not self.ctx.guild_id:
            return
        
        if self.guild['current_menu']:
            self.db.update(self.ctx.guild_id, {'current_menu': None, 'previous_tracks': [], 'vibing': False})
            message = await self.get_menu_message(self.ctx, self.guild['current_menu'])
            if message:
                await message.delete()
                logging.debug('Successfully deleted menu message')
            else:
                logging.debug('No menu message found')