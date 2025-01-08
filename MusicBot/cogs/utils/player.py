from typing import cast

from discord.ui import View, Button, Item
from discord import ButtonStyle, Interaction, ApplicationContext

from MusicBot.cogs.utils.voice import VoiceExtension

class PlayPauseButton(Button, VoiceExtension):
    async def callback(self, interaction: Interaction) -> None:
        vc = self.get_voice_client(interaction)
        if vc is not None:
            if not vc.is_paused():
                self.pause_playing(interaction)
                await interaction.edit(content="Результат паузы.")
            else:
                self.resume_playing(interaction)
                await interaction.edit(content="Результат возобновления.")

class NextTrackButton(Button, VoiceExtension):
    async def callback(self, interaction: Interaction) -> None:
        await self.next_track(interaction)
        await interaction.edit(content='Результат переключения >.')

class Player(View):
    
    def __init__(self, ctx: ApplicationContext, *items: Item, timeout: float | None = 3600, disable_on_timeout: bool = False):
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        
        self.ctx = ctx
        
        self.repeat_button = Button(style=ButtonStyle.secondary, emoji='🔂', row=0)
        self.shuffle_button = Button(style=ButtonStyle.secondary, emoji='🔀', row=0)
        self.queue_button = Button(style=ButtonStyle.primary, emoji='📋', row=0)
        self.play_pause_button = PlayPauseButton(style=ButtonStyle.primary, emoji='⏯', row=0)
        self.next_button = NextTrackButton(style=ButtonStyle.primary, emoji='⏭', row=0)
        self.prev_button = Button(style=ButtonStyle.primary, emoji='⏮', row=0)
        
        self.add_item(self.repeat_button)
        self.add_item(self.prev_button)
        self.add_item(self.play_pause_button)
        self.add_item(self.next_button)
        self.add_item(self.shuffle_button)
        