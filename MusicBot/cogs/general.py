from typing import cast
from asyncio import gather

import discord
from discord.ext.commands import Cog

import yandex_music
import yandex_music.exceptions
from yandex_music import ClientAsync as YMClient
from yandex_music import Track, Album, Artist, Playlist

from MusicBot.database import BaseUsersDatabase, BaseGuildsDatabase
from MusicBot.cogs.utils.find import (
    process_album, process_track, process_artist, process_playlist,
    ListenAlbum, ListenTrack, ListenArtist, ListenPlaylist, ListenLikesPlaylist
)
from MusicBot.cogs.utils.misc import MyPlaylists, generate_playlist_embed, generate_likes_embed

def setup(bot):
    bot.add_cog(General(bot))

class General(Cog):
    
    def __init__(self, bot):
        self.bot = bot
        self.db = BaseGuildsDatabase()
        self.users_db = BaseUsersDatabase()
    
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
                `account`
                `find`
                `help`
                `like`
                `queue`
                `settings`
                `track`
                `voice`
                """
            )

            embed.set_author(name='YandexMusic')
            embed.set_footer(text='©️ Bananchiki')
        elif command == 'account':
            embed.description += ("Ввести токен от Яндекс Музыки. Его можно получить [здесь](https://github.com/MarshalX/yandex-music-api/discussions/513).\n"
                                "```/account login <token>```\n"
                                "Удалить токен из датабазы бота.\n```/account remove```\n"
                                "Получить ваши плейлисты. Чтобы добавить плейлист в очередь, используйте команду /find.\n```/account playlists```\n"
                                "Получить плейлист «Мне нравится». \n```/account likes```\n")
        elif command == 'find':
            embed.description += ("Вывести информацию о треке (по умолчанию), альбоме, авторе или плейлисте. Позволяет добавить музыку в очередь. "
                                "В названии можно уточнить автора или версию. Возвращается лучшее совпадение.\n```/find <название> <тип>```")
        elif command == 'help':
            embed.description += ("Вывести список всех команд.\n```/help```\n"
                                "Получить информацию о конкретной команде.\n```/help <команда>```")
        elif command == 'like':
            embed.description += "Добавить трек в плейлист «Мне нравится». Пользовательские треки из этого плейлиста игнорируются.\n```/like```"
        elif command == 'queue':
            embed.description += ("Получить очередь треков. По 15 элементов на страницу.\n```/queue get```\n"
                                "Очистить очередь треков и историю прослушивания. Доступно только если вы единственный в голосовом канале"
                                "или имеете разрешение управления каналом.\n```/queue clear```\n")
        elif command == 'settings':
            embed.description += ("Получить текущие настройки.\n```/settings show```\n"
                                  "Разрешить или запретить воспроизведение Explicit треков и альбомов. Если автор или плейлист содержат Explicit треки, убираются кнопки для доступа к ним.\n```/settings explicit```\n"
                                  "Разрешить или запретить создание меню проигрывателя, даже если в канале больше одного человека.\n```/settings menu```\n"
                                  "Разрешить или запретить голосование.\n```/settings vote <тип голосования>```\n"
                                  "`Примечание`: Только пользователи с разрешением управления каналом могут менять настройки.")
        elif command == 'track':
            embed.description += ("`Примечание`: Если вы один в голосовом канале или имеете разрешение управления каналом, голосование не начинается.\n\n"
                                "Переключиться на следующий трек в очереди. \n```/track next```\n"
                                "Приостановить текущий трек.\n ```/track pause```\n"
                                "Возобновить текущий трек.\n ```/track resume```\n"
                                "Прервать проигрывание, удалить историю, очередь и текущий плеер.\n ```/track stop```")
        elif command == 'voice':
            embed.description += ("Присоединить бота в голосовой канал. Требует разрешения управления каналом.\n ```/voice join```\n"
                                "Заставить бота покинуть голосовой канал. Требует разрешения управления каналом.\n ```/voice leave```\n"
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

        self.users_db.update(uid, {'ym_token': token})
        await ctx.respond(f'Привет, {about['account']['first_name']}!', delete_after=15, ephemeral=True)
    
    @account.command(description="Удалить токен из датабазы бота.")
    async def remove(self, ctx: discord.ApplicationContext) -> None:
        self.users_db.update(ctx.user.id, {'ym_token': None})
        await ctx.respond(f'Токен был удалён.', delete_after=15, ephemeral=True)

    @account.command(description="Получить плейлист «Мне нравится»")
    async def likes(self, ctx: discord.ApplicationContext) -> None:
        token = self.users_db.get_ym_token(ctx.user.id)
        if not token:
            await ctx.respond('❌ Необходимо указать свой токен доступа с помощью команды /login.', delete_after=15, ephemeral=True)
            return
        client = await YMClient(token).init()
        if not client.me or not client.me.account or not client.me.account.uid:
            await ctx.respond('❌ Что-то пошло не так. Повторите попытку позже.', delete_after=15, ephemeral=True)
            return
        likes = await client.users_likes_tracks()
        if not likes:
            await ctx.respond('❌ Что-то пошло не так. Повторите попытку позже.', delete_after=15, ephemeral=True)
            return
        
        real_tracks = await gather(*[track_short.fetch_track_async() for track_short in likes.tracks], return_exceptions=True)
        tracks = [track for track in real_tracks if not isinstance(track, BaseException)]  # Can't fetch user tracks
        embed = generate_likes_embed(tracks)
        await ctx.respond(embed=embed, view=ListenLikesPlaylist(tracks))
    
    @account.command(description="Получить ваши плейлисты.")
    async def playlists(self, ctx: discord.ApplicationContext) -> None:
        token = self.users_db.get_ym_token(ctx.user.id)
        if not token:
            await ctx.respond('❌ Необходимо указать свой токен доступа с помощью команды /login.', delete_after=15, ephemeral=True)
            return
        client = await YMClient(token).init()
        if not client.me or not client.me.account or not client.me.account.uid:
            await ctx.respond('❌ Что-то пошло не так. Повторите попытку позже.', delete_after=15, ephemeral=True)
            return
        playlists_list = await client.users_playlists_list(client.me.account.uid)
        playlists: list[tuple[str, int]] = [
            (playlist.title if playlist.title else 'Без названия', playlist.track_count if playlist.track_count else 0) for playlist in playlists_list
        ]
        self.users_db.update(ctx.user.id, {'playlists': playlists, 'playlists_page': 0})
        embed = generate_playlist_embed(0, playlists)
        await ctx.respond(embed=embed, view=MyPlaylists(ctx), ephemeral=True)
    
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
        choices=['Artist', 'Album', 'Track', 'Playlist', 'User Playlist'],
        default='Track'
    )
    async def find(
        self,
        ctx: discord.ApplicationContext,
        name: str,
        content_type: str = 'Track'
    ) -> None:
        if content_type not in ['Artist', 'Album', 'Track', 'Playlist', 'User Playlist']:
            await ctx.respond("❌ Недопустимый тип.", delete_after=15, ephemeral=True)
            return
        
        guild = self.db.get_guild(ctx.guild_id)
        token = self.users_db.get_ym_token(ctx.user.id)
        if not token:
            await ctx.respond("❌ Необходимо указать свой токен доступа с помощью команды /login.", delete_after=15, ephemeral=True)
            return

        try:
            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            await ctx.respond("❌ Недействительный токен. Если это не так, попробуйте ещё раз.", delete_after=15, ephemeral=True)
            return

        if content_type == 'User Playlist':
            if not client.me or not client.me.account or not client.me.account.uid:
                await ctx.respond("❌ Не удалось получить информацию о пользователе.", delete_after=15, ephemeral=True)
                return

            playlists = await client.users_playlists_list(client.me.account.uid)
            result = next((playlist for playlist in playlists if playlist.title == name), None)
            if not result:
                await ctx.respond("❌ Плейлист не найден.", delete_after=15, ephemeral=True)
                return
            
            tracks = await result.fetch_tracks_async()
            if not tracks:
                await ctx.respond("❌ Плейлист пуст.", delete_after=15, ephemeral=True)
                return
            
            for track_short in tracks:
                track = cast(Track, track_short.track)
                if (track.explicit or track.content_warning) and not guild['allow_explicit']:
                    await ctx.respond("❌ Explicit контент запрещён на этом сервере.", delete_after=15, ephemeral=True)
                    return
            
            embed = await process_playlist(result)
            await ctx.respond(embed=embed, view=ListenPlaylist(result))
        else:
            result = await client.search(name, True)
        
            if not result:
                await ctx.respond("❌ Что-то пошло не так. Повторите попытку позже", delete_after=15, ephemeral=True)
                return

            content_map = {
                'Album': (result.albums, process_album, ListenAlbum),
                'Track': (result.tracks, process_track, ListenTrack),
                'Artist': (result.artists, process_artist, ListenArtist),
                'Playlist': (result.playlists, process_playlist, ListenPlaylist)
            }

            if content_type in content_map:
                content: Album | Track | Artist | Playlist = content_map[content_type][0].results[0]
                embed: discord.Embed = await content_map[content_type][1](content)
                view = content_map[content_type][2](content)
                
                if isinstance(content, (Track, Album)) and (content.explicit or content.content_warning) and not guild['allow_explicit']:
                    await ctx.respond("❌ Explicit контент запрещён на этом сервере.", delete_after=15, ephemeral=True)
                    return
                elif isinstance(content, Artist):
                    tracks = await content.get_tracks_async()
                    if not tracks:
                        await ctx.respond("❌ Треки от этого исполнителя не найдены.", delete_after=15, ephemeral=True)
                        return
                    for track in tracks:
                        if (track.explicit or track.content_warning) and not guild['allow_explicit']:
                            view = None
                            embed.set_footer(text="Воспроизведение недоступно, так как у автора присутствуют Explicit треки")
                            break
                elif isinstance(content, Playlist):
                    tracks = await content.fetch_tracks_async()
                    if not tracks:
                        await ctx.respond("❌ Треки в этом плейлисте не найдены.", delete_after=15, ephemeral=True)
                        return
                    for track_short in content.tracks:
                        track = cast(Track, track_short.track)
                        if (track.explicit or track.content_warning) and not guild['allow_explicit']:
                            view = None
                            embed.set_footer(text="Воспроизведение недоступно, так как у автора присутствуют Explicit треки")
                            break
                
                await ctx.respond(embed=embed, view=view)
            else:
                await ctx.respond("❌ По запросу ничего не найдено.", delete_after=15, ephemeral=True)
