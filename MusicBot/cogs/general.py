from math import ceil
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
from MusicBot.cogs.utils.misc import MyPlalistsView, generate_playlist_embed

def setup(bot):
    bot.add_cog(General(bot))

class General(Cog):
    
    def __init__(self, bot):
        self.bot = bot
        self.db = BaseUsersDatabase()
    
    account = discord.SlashCommandGroup("account", "Команды, связанные с аккаунтом.")
    
    @discord.slash_command(description="Получить информацию о командах YandexMusic.")
    @discord.option(
        "command",
        description="Название команды.",
        type=discord.SlashCommandOptionType.string,
        default='all'
    )
    async def help(self, ctx: discord.ApplicationContext, command: str) -> None:
        response_message = None
        embed = discord.Embed(
            color=0xfed42b
        )
        embed.description = '__Использование__\n'
        embed.set_author(name='Помощь')

        if command == 'all':
            embed.description = ("Данный бот позволяет вам слушать музыку из вашего аккаунта Yandex Music.\n"
                                "Зарегистрируйте свой токен с помощью /login. Его можно получить [здесь](https://github.com/MarshalX/yandex-music-api/discussions/513).\n"
                                "Для получения помощи для конкретной команды, введите /help <команда>.\n\n"
                                "**Для доп. помощи, зайдите на [сервер любителей Яндекс Музыки](https://discord.gg/gkmFDaPMeC).**")
            embed.title = 'Помощь'

            embed.add_field(
                name='__Основные команды__',
                value="""
                `find`
                `help`
                `account`
                `queue`
                `track`
                `voice`
                """
            )

            embed.set_author(name='YandexMusic')
            embed.set_footer(text='©️ Bananchiki')
        elif command == 'find':
            embed.description += ("Вывести информацию о треке (по умолчанию), альбоме, авторе или плейлисте. Позволяет добавить музыку в очередь. "
                                "В названии можно уточнить автора или версию. Возвращается лучшее совпадение.\n```/find <название> <тип>```")
        elif command == 'help':
            embed.description += ("Вывести список всех команд.\n```/help```\n"
                                "Получить информацию о конкретной команде.\n```/help <команда>```")
        elif command == 'account':
            embed.description += ("Ввести токен от Яндекс Музыки. Его можно получить [здесь](https://github.com/MarshalX/yandex-music-api/discussions/513).\n"
                                "```/account login <token>```\n"
                                "Удалить токен из датабазы бота.\n```/account remove```")
        elif command == 'queue':
            embed.description += ("Получить очередь треков. По 15 элементов на страницу.\n```/queue get```\n"
                                "Очистить очередь треков и историю прослушивания. Требует согласия части слушателей.\n```/queue clear```\n"
                                "`Примечание`: Если вы один в голосовом канале или имеете роль администратора бота, голосование не требуется.")
        elif command == 'track':
            embed.description += ("`Примечание`: Следующие команды требуют согласия части слушателей. Если вы один в голосовом канале или имеете роль администратора бота, голосование не требуется.\n\n"
                                "Переключиться на следующий трек в очереди и добавить его в историю.\n```/track next```\n"
                                "Приостановить текущий трек.\n ```/track pause```\n"
                                "Возобновить текущий трек.\n ```/track resume```\n"
                                "Прервать проигрывание, удалить историю, очередь и текущий плеер.\n ```/track stop```")
        elif command == 'voice':
            embed.description += ("Присоединить бота в голосовой канал. Требует роли администратора.\n ```/voice join```\n"
                                "Заставить бота покинуть голосовой канал. Требует роли администратора.\n ```/voice leave```\n"
                                "Создать меню проигрывателя. Доступно только если вы единственный в голосовом канале.\n```/voice menu```")
        else:
            response_message = '❌ Неизвестная команда.'
            embed = None

        await ctx.respond(response_message, embed=embed, ephemeral=True)
    
    @account.command(description="Ввести токен от Яндекс Музыки.")
    @discord.option("token", type=discord.SlashCommandOptionType.string, description="Токен.")
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
    
    @account.command(description="Удалить токен из датабазы бота.")
    async def remove(self, ctx: discord.ApplicationContext) -> None:
        self.db.update(ctx.user.id, {'ym_token': None})
        await ctx.respond(f'Токен был удалён.', delete_after=15, ephemeral=True)

    @account.command(description="Получить плейлисты пользователя.")
    async def playlists(self, ctx: discord.ApplicationContext) -> None:
        token = self.db.get_ym_token(ctx.user.id)
        if not token:
            await ctx.respond('❌ Необходимо указать свой токен доступа с помощью команды /login.', delete_after=15, ephemeral=True)
            return
        client = await YMClient(token).init()
        if not client.me or not client.me.account or not client.me.account.uid:
            await ctx.respond('❌ Что-то пошло не так. Повторите попытку позже.', delete_after=15, ephemeral=True)
            return
        playlists_list = await client.users_playlists_list(client.me.account.uid)
        playlists: list[tuple[str, int]] = [(playlist.title, playlist.track_count) for playlist in playlists_list]  # type: ignore
        self.db.update(ctx.user.id, {'playlists': playlists, 'playlists_page': 0})
        embed = generate_playlist_embed(0, playlists)
        await ctx.respond(embed=embed, view=MyPlalistsView(ctx), ephemeral=True)
    
    @discord.slash_command(description="Найти контент и отправить информацию о нём. Возвращается лучшее совпадение.")
    @discord.option(
        "name",
        description="Название контента для поиска (По умолчанию трек).",
        type=discord.SlashCommandOptionType.string
    )
    @discord.option(
        "content_type",
        description="Тип искомого контента.",
        type=discord.SlashCommandOptionType.string,
        choices=['Artist', 'Album', 'Track', 'Playlist'],
        default='Track'
    )
    async def find(
        self,
        ctx: discord.ApplicationContext,
        name: str,
        content_type: str = 'Track'
    ) -> None:
        if content_type not in ['Artist', 'Album', 'Track', 'Playlist']:
            await ctx.respond("❌ Недопустимый тип.", delete_after=15, ephemeral=True)
            return
        content_type = content_type.lower()
        
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
