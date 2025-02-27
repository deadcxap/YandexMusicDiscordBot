from math import ceil
from typing import Self, Any

from discord.ui import View, Button, Item
from discord import ApplicationContext, ButtonStyle, Interaction, Embed, HTTPException

from MusicBot.cogs.utils.voice_extension import VoiceExtension

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
        if duration:
            duration_m = duration // 60000
            duration_s = ceil(duration / 1000) - duration_m * 60
            embed.add_field(name=f"{i} - {track['title']} - {duration_m}:{duration_s:02d}", value="", inline=False)
    return embed

class QueueNextButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)

    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user or not interaction.guild:
            return

        user = await self.users_db.get_user(interaction.user.id)
        page = user['queue_page'] + 1
        await self.users_db.update(interaction.user.id, {'queue_page': page})
        tracks = await self.db.get_tracks_list(interaction.guild.id, 'next')
        embed = generate_queue_embed(page, tracks)
        await interaction.edit(embed=embed, view=await QueueView(interaction).init())

class QueuePrevButton(Button, VoiceExtension):
    def __init__(self, **kwargs):
        Button.__init__(self, **kwargs)
        VoiceExtension.__init__(self, None)

    async def callback(self, interaction: Interaction) -> None:
        if not interaction.user or not interaction.guild:
            return

        user = await self.users_db.get_user(interaction.user.id)
        page = user['queue_page'] - 1
        await self.users_db.update(interaction.user.id, {'queue_page': page})
        tracks = await self.db.get_tracks_list(interaction.guild.id, 'next')
        embed = generate_queue_embed(page, tracks)
        await interaction.edit(embed=embed, view=await QueueView(interaction).init())

class QueueView(View, VoiceExtension):
    def __init__(self, ctx: ApplicationContext | Interaction, *items: Item, timeout: float | None = 360, disable_on_timeout: bool = False):
        View.__init__(self, *items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        VoiceExtension.__init__(self, None)

        self.ctx = ctx
        self.next_button = QueueNextButton(style=ButtonStyle.primary, emoji='▶️')
        self.prev_button = QueuePrevButton(style=ButtonStyle.primary, emoji='◀️')

    async def init(self) -> Self:
        if not self.ctx.user or not self.ctx.guild:
            return self

        tracks = await self.db.get_tracks_list(self.ctx.guild.id, 'next')
        user = await self.users_db.get_user(self.ctx.user.id)

        count = 15 * user['queue_page']

        if not tracks[count + 15:]:
            self.next_button.disabled = True
        if not tracks[:count]:
            self.prev_button.disabled = True

        self.add_item(self.prev_button)
        self.add_item(self.next_button)

        return self

    async def on_timeout(self) -> None:
        try:
            await super().on_timeout()
        except HTTPException:
            pass
        self.stop()