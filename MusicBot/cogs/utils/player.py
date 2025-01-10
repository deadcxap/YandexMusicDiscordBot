from discord.ui import View, Button, Item
from discord import InteractionMessage, ButtonStyle, Interaction, ApplicationContext

from MusicBot.cogs.utils.voice import VoiceExtension

class PlayPauseButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self)
    
    async def callback(self, interaction: Interaction) -> None:
        if not await self.voice_check(interaction):
            return
        vc = self.get_voice_client(interaction)
        if vc is not None:
            if not vc.is_paused():
                vc.pause()
                message = interaction.message
                if not message:
                    return
                embed = message.embeds[0]
                embed.set_footer(text='Приостановлено')
                await interaction.edit(embed=embed)
            else:
                vc.resume()
                message = interaction.message
                if not message:
                    return
                embed = message.embeds[0]
                embed.remove_footer()
                await interaction.edit(embed=embed)

class NextTrackButton(Button, VoiceExtension):    
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self)
    
    async def callback(self, interaction: Interaction) -> None:
        if not await self.voice_check(interaction):
            return
        title = await self.next_track(interaction)
        if not title:
            await interaction.respond(f"Нет треков в очереди.", delete_after=15, ephemeral=True)

class PrevTrackButton(Button, VoiceExtension):    
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self)
    
    async def callback(self, interaction: Interaction) -> None:
        if not await self.voice_check(interaction):
            return
        title = await self.prev_track(interaction)
        if not title:
            await interaction.respond(f"Нет треков в истории.", delete_after=15, ephemeral=True)

class Player(View):
    
    def __init__(self, ctx: ApplicationContext, *items: Item, timeout: float | None = 3600, disable_on_timeout: bool = True):
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        
        self.ctx = ctx
        
        self.repeat_button = Button(style=ButtonStyle.secondary, emoji='🔂', row=0)
        self.shuffle_button = Button(style=ButtonStyle.secondary, emoji='🔀', row=0)
        self.play_pause_button = PlayPauseButton(style=ButtonStyle.primary, emoji='⏯', row=0)
        self.next_button = NextTrackButton(style=ButtonStyle.primary, emoji='⏭', row=0)
        self.prev_button = PrevTrackButton(style=ButtonStyle.primary, emoji='⏮', row=0)
        
        self.queue_button = Button(style=ButtonStyle.primary, emoji='📋', row=1)
        
        self.add_item(self.repeat_button)
        self.add_item(self.prev_button)
        self.add_item(self.play_pause_button)
        self.add_item(self.next_button)
        self.add_item(self.shuffle_button)
        