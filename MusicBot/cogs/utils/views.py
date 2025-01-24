from discord.ui import View, Button, Item
from discord import ButtonStyle, Interaction, ApplicationContext

from MusicBot.cogs.utils.voice_extension import VoiceExtension
from MusicBot.cogs.utils.misc import generate_playlists_embed, generate_queue_embed

class MPNextButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user:
            return
        user = self.users_db.get_user(interaction.user.id)
        page = user['playlists_page'] + 1
        self.users_db.update(interaction.user.id, {'playlists_page': page})
        embed = generate_playlists_embed(page, user['playlists'])
        await interaction.edit(embed=embed, view=MyPlaylists(interaction))

class MPPrevButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user:
            return
        user = self.users_db.get_user(interaction.user.id)
        page = user['playlists_page'] - 1
        self.users_db.update(interaction.user.id, {'playlists_page': page})
        embed = generate_playlists_embed(page, user['playlists'])
        await interaction.edit(embed=embed, view=MyPlaylists(interaction))

class MyPlaylists(View, VoiceExtension):
    def __init__(self, ctx: ApplicationContext | Interaction, *items: Item, timeout: float | None = 3600, disable_on_timeout: bool = True):
        View.__init__(self, *items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        VoiceExtension.__init__(self, None)
        if not ctx.user:
            return
        user = self.users_db.get_user(ctx.user.id)
        count = 10 * user['playlists_page']

        next_button = MPNextButton(style=ButtonStyle.primary, emoji='▶️')
        prev_button = MPPrevButton(style=ButtonStyle.primary, emoji='◀️')

        if not user['playlists'][count + 10:]:
            next_button.disabled = True
        if not user['playlists'][:count]:
            prev_button.disabled = True

        self.add_item(prev_button)
        self.add_item(next_button)

class QNextButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user or not interaction.guild:
            return
        user = self.users_db.get_user(interaction.user.id)
        page = user['queue_page'] + 1
        self.users_db.update(interaction.user.id, {'queue_page': page})
        tracks = self.db.get_tracks_list(interaction.guild.id, 'next')
        embed = generate_queue_embed(page, tracks)
        await interaction.edit(embed=embed, view=QueueView(interaction))

class QPrevButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user or not interaction.guild:
            return
        user = self.users_db.get_user(interaction.user.id)
        page = user['queue_page'] - 1
        self.users_db.update(interaction.user.id, {'queue_page': page})
        tracks = self.db.get_tracks_list(interaction.guild.id, 'next')
        embed = generate_queue_embed(page, tracks)
        await interaction.edit(embed=embed, view=QueueView(interaction))

class QueueView(View, VoiceExtension):
    def __init__(self, ctx: ApplicationContext | Interaction, *items: Item, timeout: float | None = 3600, disable_on_timeout: bool = True):
        View.__init__(self, *items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        VoiceExtension.__init__(self, None)
        if not ctx.user or not ctx.guild:
            return

        tracks = self.db.get_tracks_list(ctx.guild.id, 'next')
        user = self.users_db.get_user(ctx.user.id)
        count = 15 * user['queue_page']

        next_button = QNextButton(style=ButtonStyle.primary, emoji='▶️')
        prev_button = QPrevButton(style=ButtonStyle.primary, emoji='◀️')

        if not tracks[count + 15:]:
            next_button.disabled = True
        if not tracks[:count]:
            prev_button.disabled = True

        self.add_item(prev_button)
        self.add_item(next_button)