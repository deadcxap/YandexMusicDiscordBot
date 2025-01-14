from math import ceil
from typing import Any

from discord.ui import View, Button, Item
from discord import ButtonStyle, Interaction, ApplicationContext, Embed

from MusicBot.cogs.utils.voice import VoiceExtension

def generate_playlist_embed(page: int, playlists: list[tuple[str, int]]) -> Embed:
    count = 15 * page
    length = len(playlists)
    embed = Embed(
        title=f"Всего плейлистов: {length}",
        color=0xfed42b
    )
    embed.set_author(name="Ваши плейлисты")
    embed.set_footer(text=f"Страница {page + 1} из {ceil(length / 10)}")
    for playlist in playlists[count:count + 10]:
        embed.add_field(name=playlist[0], value=f"{playlist[1]} треков", inline=False)
    return embed

def generate_queue_embed(page: int, tracks_list: list[dict[str, Any]]) -> Embed:
    count = 15 * page
    length = len(tracks_list)
    embed = Embed(
        title=f"Всего: {length}",
        color=0xfed42b,
    )
    embed.set_author(name="Очередь треков")
    embed.set_footer(text=f"Страница {page + 1} из {ceil(length / 15)}")
    for i, track in enumerate(tracks_list[count:count + 15], start=1 + count):
        duration = track['duration_ms']
        duration_m = duration // 60000
        duration_s = ceil(duration / 1000) - duration_m * 60
        embed.add_field(name=f"{i} - {track['title']} - {duration_m}:{duration_s:02d}", value="", inline=False)
    return embed

class MPNextButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self)
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user:
            return
        user = self.users_db.get_user(interaction.user.id)
        page = user['playlists_page'] + 1
        self.users_db.update(interaction.user.id, {'playlists_page': page})
        embed = generate_playlist_embed(page, user['playlists'])
        await interaction.edit(embed=embed, view=MyPlalistsView(interaction))

class MPPrevButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self)
    
    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user:
            return
        user = self.users_db.get_user(interaction.user.id)
        page = user['playlists_page'] - 1
        self.users_db.update(interaction.user.id, {'playlists_page': page})
        embed = generate_playlist_embed(page, user['playlists'])
        await interaction.edit(embed=embed, view=MyPlalistsView(interaction))

class MyPlalistsView(View, VoiceExtension):
    def __init__(self, ctx: ApplicationContext | Interaction, *items: Item, timeout: float | None = 3600, disable_on_timeout: bool = True):
        View.__init__(self, *items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        VoiceExtension.__init__(self)
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
        VoiceExtension.__init__(self)
    
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
        VoiceExtension.__init__(self)
    
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
        VoiceExtension.__init__(self)
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