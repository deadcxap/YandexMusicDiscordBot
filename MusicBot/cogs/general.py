from typing import cast

import discord
from discord.ext.commands import Cog

import yandex_music
import yandex_music.exceptions
from yandex_music import ClientAsync as YMClient

from MusicBot.database import BaseUsersDatabase
from MusicBot.cogs.utils.find import (
    proccess_album, process_track, process_artist,
    ListenAlbum, ListenTrack, ListenArtist
)

def setup(bot):
    bot.add_cog(General(bot))

class General(Cog):
    
    def __init__(self, bot):
        self.bot = bot
        self.db = BaseUsersDatabase()
    
    @discord.slash_command(description="Login to Yandex Music using access token.", guild_ids=[1247100229535141899])
    @discord.option("token", type=discord.SlashCommandOptionType.string)
    async def login(self, ctx: discord.ApplicationContext, token: str) -> None:
        try:
            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            await ctx.respond('❌ Недействительный токен.', delete_after=15, ephemeral=True)
            return
        about = cast(yandex_music.Status, client.me).to_dict()
        uid = ctx.author.id

        self.db.update(uid, {'ym_token': token})
        await ctx.respond(f'Привет, {about['account']['first_name']}!', delete_after=15, ephemeral=True)

    @discord.slash_command(description="Find the content type by its name and send info about it. The best match is returned.", guild_ids=[1247100229535141899])
    @discord.option(
        "name",
        description="Name of the content to find",
        type=discord.SlashCommandOptionType.string
    )
    @discord.option(
        "content_type",
        description="Type of the conent to find (artist, album, track, playlist).",
        type=discord.SlashCommandOptionType.string,
        default='track'
    )
    async def find(self, ctx: discord.ApplicationContext, name: str, content_type: str = 'track') -> None:
        if content_type not in ('artist', 'album', 'track', 'playlist'):
            await ctx.respond('❌ Недопустимый тип.')
            return
        
        token = self.db.get_ym_token(ctx.user.id)
        if not token:
            await ctx.respond('❌ Необходимо указать свой токен доступа с помощью комманды /login.', delete_after=15, ephemeral=True)
            return
        try:
            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            await ctx.respond('❌ Недействительный токен. Если это не так, попробуйте ещё раз.', delete_after=15, ephemeral=True)
            return
        
        result = await client.search(name, True, content_type)

        if content_type == 'album':
            album = result.albums.results[0]  # type: ignore
            embed = await proccess_album(album)
            await ctx.respond("", embed=embed, view=ListenAlbum(album), delete_after=360)
        elif content_type == 'track':
            track: yandex_music.Track = result.tracks.results[0]  # type: ignore
            album_id = cast(int, track.albums[0].id)
            embed = await process_track(track)
            await ctx.respond("", embed=embed, view=ListenTrack(track, album_id), delete_after=360)
        elif content_type == 'artist':
            artist = result.artists.results[0]  # type: ignore
            embed = await process_artist(artist)
            await ctx.respond("", embed=embed, view=ListenArtist(artist.id), delete_after=360)
