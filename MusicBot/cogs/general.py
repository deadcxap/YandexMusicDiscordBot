from typing import cast

import discord
from discord.ext.commands import Cog

import yandex_music
import yandex_music.exceptions
from yandex_music import ClientAsync as YMClient

from MusicBot.database import BaseUsersDatabase
from MusicBot.cogs.utils.find import (
    process_album, process_track, process_artist, process_playlist,
    ListenAlbum, ListenTrack, ListenArtist, ListenPlaylist
)

def setup(bot):
    bot.add_cog(General(bot))

class General(Cog):
    
    def __init__(self, bot):
        self.bot = bot
        self.db = BaseUsersDatabase()
    
    @discord.slash_command(description="Войти в Yandex Music с помощью токена.")
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

    @discord.slash_command(description="Найти контент и отправить информацию о нём. Возвращается лучшее совпадение.")
    @discord.option(
        "name",
        description="Название контента для поиска",
        type=discord.SlashCommandOptionType.string
    )
    @discord.option(
        "content_type",
        description="Тип искомого контента (artist, album, track, playlist).",
        type=discord.SlashCommandOptionType.string,
        default='track'
    )
    async def find(self, ctx: discord.ApplicationContext, name: str, content_type: str = 'track') -> None:
        if content_type not in ('artist', 'album', 'track', 'playlist'):
            await ctx.respond("❌ Недопустимый тип.", delete_after=15, ephemeral=True)
            return
        
        token = self.db.get_ym_token(ctx.user.id)
        if not token:
            await ctx.respond("❌ Необходимо указать свой токен доступа с помощью комманды /login.", delete_after=15, ephemeral=True)
            return
        try:
            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            await ctx.respond("❌ Недействительный токен. Если это не так, попробуйте ещё раз.", delete_after=15, ephemeral=True)
            return
        
        result = await client.search(name, True, content_type)
        
        if not result:
            await ctx.respond("❌ Что-то пошло не так. Повторите попытку позже", delete_after=15, ephemeral=True)
            return

        if content_type == 'album' and result.albums:
            album = result.albums.results[0]
            embed = await process_album(album)
            await ctx.respond(embed=embed, view=ListenAlbum(album))
        elif content_type == 'track' and result.tracks:
            track: yandex_music.Track = result.tracks.results[0]
            album_id = cast(int, track.albums[0].id)
            embed = await process_track(track)
            await ctx.respond(embed=embed, view=ListenTrack(track, album_id))
        elif content_type == 'artist' and result.artists:
            artist = result.artists.results[0]
            embed = await process_artist(artist)
            await ctx.respond(embed=embed, view=ListenArtist(artist))
        elif content_type == 'playlist' and result.playlists:
            playlist = result.playlists.results[0]
            embed = await process_playlist(playlist)
            await ctx.respond(embed=embed, view=ListenPlaylist(playlist))
        else:
            await ctx.respond("❌ По запросу ничего не найдено.", delete_after=15, ephemeral=True)
