from discord.ui import View, Button, Item
from discord import ButtonStyle, Interaction, ApplicationContext

from MusicBot.cogs.utils.voice_extension import VoiceExtension

class ToggleRepeatButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self)
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.guild:
            return
        gid = interaction.guild.id
        guild = self.db.get_guild(gid)
        self.db.update(gid, {'repeat': not guild['repeat']})
        await interaction.edit(view=Player(interaction))

class ToggleShuffleButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self)
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.guild:
            return
        gid = interaction.guild.id
        guild = self.db.get_guild(gid)
        self.db.update(gid, {'shuffle': not guild['shuffle']})
        await interaction.edit(view=Player(interaction))

class PlayPauseButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self)
    
    async def callback(self, interaction: Interaction) -> None:
        if not await self.voice_check(interaction):
            return

        vc = self.get_voice_client(interaction)
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

class LikeButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self)
        
    async def callback(self, interaction: Interaction) -> None:
        if await self.voice_check(interaction):
            vc = self.get_voice_client(interaction)
            if not vc or not vc.is_playing:
                await interaction.respond("Нет воспроизводимого трека.", delete_after=15, ephemeral=True)
            result = await self.like_track(interaction)
            if not result:
                await interaction.respond("❌ Операция не удалась.", delete_after=15, ephemeral=True)
            elif result == 'TRACK REMOVED':
                await interaction.respond("Трек был удалён из избранного.", delete_after=15, ephemeral=True)
            else:
                await interaction.respond(f"Трек **{result}** был добавлен в избранное.", delete_after=15, ephemeral=True)

class Player(View, VoiceExtension):
    
    def __init__(self, ctx: ApplicationContext | Interaction, *items: Item, timeout: float | None = 3600, disable_on_timeout: bool = True):
        View.__init__(self, *items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        VoiceExtension.__init__(self)
        if not ctx.guild:
            return
        guild = self.db.get_guild(ctx.guild.id)
        
        self.repeat_button = ToggleRepeatButton(style=ButtonStyle.success if guild['repeat'] else ButtonStyle.secondary, emoji='🔂', row=0)
        self.shuffle_button = ToggleShuffleButton(style=ButtonStyle.success if guild['shuffle'] else ButtonStyle.secondary, emoji='🔀', row=0)
        self.play_pause_button = PlayPauseButton(style=ButtonStyle.primary, emoji='⏯', row=0)
        self.next_button = NextTrackButton(style=ButtonStyle.primary, emoji='⏭', row=0)
        self.prev_button = PrevTrackButton(style=ButtonStyle.primary, emoji='⏮', row=0)
        self.queue_button = Button(style=ButtonStyle.primary, emoji='📋', row=1)

        self.add_item(self.repeat_button)
        self.add_item(self.prev_button)
        self.add_item(self.play_pause_button)
        self.add_item(self.next_button)
        self.add_item(self.shuffle_button)
        