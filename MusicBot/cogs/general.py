import logging
from typing import Literal, cast
from asyncio import gather

import discord
from discord.ext.commands import Cog

import yandex_music
import yandex_music.exceptions
from yandex_music import ClientAsync as YMClient
from yandex_music import Track, Album, Artist, Playlist

from MusicBot.database import BaseUsersDatabase, BaseGuildsDatabase

from MusicBot.ui import ListenView, MyPlaylists, generate_playlists_embed
from MusicBot.cogs.utils.embeds import generate_item_embed

def setup(bot):
    bot.add_cog(General(bot))

async def get_search_suggestions(ctx: discord.AutocompleteContext) -> list[str]:
    if not ctx.interaction.user or not ctx.value:
        return []
    
    users_db = BaseUsersDatabase()
    token = users_db.get_ym_token(ctx.interaction.user.id)
    if not token:
        return ['❌ Укажите токен через /account login.']

    try:
        client = await YMClient(token).init()
    except yandex_music.exceptions.UnauthorizedError:
        logging.info(f"User {ctx.interaction.user.id} provided invalid token")
        return ['❌ Недействительный токен.']
    
    content_type = ctx.options['тип']
    search = await client.search(ctx.value)
    if not search:
        logging.warning(f"Failed to search for '{ctx.value}' for user {ctx.interaction.user.id}")
        return ["❌ Что-то пошло не так. Повторите попытку позже"]
    
    res = []
    logging.debug(f"Searching for '{ctx.value}' for user {ctx.interaction.user.id}")
    
    if content_type == 'Трек' and search.tracks:
        for item in search.tracks.results:
            res.append(f"{item.title} {f"({item.version})" if item.version else ''} - {", ".join(item.artists_name())}")
    elif content_type == 'Альбом' and search.albums:
        for item in search.albums.results:
            res.append(f"{item.title} - {", ".join(item.artists_name())}")
    elif content_type == 'Артист' and search.artists:
        for item in search.artists.results:
            res.append(f"{item.name}")
    elif content_type == 'Плейлист' and search.playlists:
        for item in search.playlists.results:
            res.append(f"{item.title}")
    elif content_type == "Свой плейлист":
        if not client.me or not client.me.account or not client.me.account.uid:
            logging.warning(f"Failed to get playlists for user {ctx.interaction.user.id}")
            return ["❌ Что-то пошло не так. Повторите попытку позже"]
        
        playlists_list = await client.users_playlists_list(client.me.account.uid)
        res = [playlist.title if playlist.title else 'Без названия' for playlist in playlists_list]

    return res

class General(Cog):
    
    def __init__(self, bot: discord.Bot):
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
        logging.info(f"Help command invoked by {ctx.user.id} for command '{command}'")

        response_message = None
        embed = discord.Embed(
            title='Помощь',
            color=0xfed42b
        )
        embed.set_author(name='YandexMusic')
        embed.description = '__Использование__\n'

        if command == 'all':
            embed.description = (
                "Этот бот позволяет слушать музыку из вашего аккаунта Yandex Music.\n"
                "Зарегистрируйте свой токен с помощью /login. Его можно получить [здесь](https://github.com/MarshalX/yandex-music-api/discussions/513).\n"
                "Для получения помощи по конкретной команде, введите /help <команда>.\n\n"
                "**Для дополнительной помощи, присоединяйтесь к [серверу любителей Яндекс Музыки](https://discord.gg/gkmFDaPMeC).**"
            )

            embed.add_field(
                name='__Основные команды__',
                value="""`account`
                `find`
                `help`
                `like`
                `queue`
                `settings`
                `track`
                `voice`"""
            )

            embed.set_footer(text='©️ Bananchiki')
        elif command == 'account':
            embed.description += (
                "Ввести токен от Яндекс Музыки. Его можно получить [здесь](https://github.com/MarshalX/yandex-music-api/discussions/513).\n"
                "```/account login <token>```\n"
                "Удалить токен из базы данных бота.\n```/account remove```\n"
                "Получить ваши плейлисты. Чтобы добавить плейлист в очередь, используйте команду /find.\n```/account playlists```\n"
                "Получить плейлист «Мне нравится».\n```/account likes```\n"
            )
        elif command == 'find':
            embed.description += (
                "Вывести информацию о треке (по умолчанию), альбоме, авторе или плейлисте. Позволяет добавить музыку в очередь. "
                "В названии можно уточнить автора или версию. Возвращается лучшее совпадение.\n```/find <название> <тип>```"
            )
        elif command == 'help':
            embed.description += (
                "Вывести список всех команд.\n```/help```\n"
                "Получить информацию о конкретной команде.\n```/help <команда>```"
            )
        elif command == 'like':
            embed.description += (
                "Добавить трек в плейлист «Мне нравится». Пользовательские треки из этого плейлиста игнорируются.\n```/like```"
            )
        elif command == 'queue':
            embed.description += (
                "Получить очередь треков. По 15 элементов на страницу.\n```/queue get```\n"
                "Очистить очередь треков и историю прослушивания. Доступно только если вы единственный в голосовом канале "
                "или имеете разрешение управления каналом.\n```/queue clear```\n"
            )
        elif command == 'settings':
            embed.description += (
                "Получить текущие настройки.\n```/settings show```\n"
                "Разрешить или запретить воспроизведение Explicit треков и альбомов. Если автор или плейлист содержат Explicit треки, убираются кнопки для доступа к ним.\n```/settings explicit```\n"
                "Разрешить или запретить создание меню проигрывателя, когда в канале больше одного человека.\n```/settings menu```\n"
                "Разрешить или запретить голосование.\n```/settings vote <тип голосования>```\n"
                "`Примечание`: Только пользователи с разрешением управления каналом могут менять настройки."
            )
        elif command == 'track':
            embed.description += (
                "`Примечание`: Если вы один в голосовом канале или имеете разрешение управления каналом, голосование не начинается.\n\n"
                "Переключиться на следующий трек в очереди. \n```/track next```\n"
                "Приостановить текущий трек.\n ```/track pause```\n"
                "Возобновить текущий трек.\n ```/track resume```\n"
                "Прервать проигрывание, удалить историю, очередь и текущий плеер.\n ```/track stop```"
            )
        elif command == 'voice':
            embed.description += (
                "Присоединить бота в голосовой канал. Требует разрешения управления каналом.\n ```/voice join```\n"
                "Заставить бота покинуть голосовой канал. Требует разрешения управления каналом.\n ```/voice leave```\n"
                "Создать меню проигрывателя. Доступность зависит от настроек сервера. По умолчанию работает только когда в канале один человек.\n```/voice menu```"
            )
        else:
            response_message = '❌ Неизвестная команда.'
            embed = None

        await ctx.respond(response_message, embed=embed, ephemeral=True)
    
    @account.command(description="Ввести токен от Яндекс Музыки.")
    @discord.option("token", type=discord.SlashCommandOptionType.string, description="Токен.")
    async def login(self, ctx: discord.ApplicationContext, token: str) -> None:
        logging.info(f"Login command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        try:
            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            logging.info(f"Invalid token provided by user {ctx.author.id}")
            await ctx.respond('❌ Недействительный токен.', delete_after=15, ephemeral=True)
            return
        about = cast(yandex_music.Status, client.me).to_dict()
        uid = ctx.author.id

        self.users_db.update(uid, {'ym_token': token})
        logging.info(f"Token saved for user {ctx.author.id}")
        await ctx.respond(f'Привет, {about['account']['first_name']}!', delete_after=15, ephemeral=True)
    
    @account.command(description="Удалить токен из датабазы бота.")
    async def remove(self, ctx: discord.ApplicationContext) -> None:
        logging.info(f"Remove command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        self.users_db.update(ctx.user.id, {'ym_token': None})
        await ctx.respond(f'Токен был удалён.', delete_after=15, ephemeral=True)

    @account.command(description="Получить плейлист «Мне нравится»")
    async def likes(self, ctx: discord.ApplicationContext) -> None:
        logging.info(f"Likes command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        token = self.users_db.get_ym_token(ctx.user.id)
        if not token:
            logging.info(f"No token found for user {ctx.user.id}")
            await ctx.respond('❌ Необходимо указать свой токен доступа с помощью команды /login.', delete_after=15, ephemeral=True)
            return
        client = await YMClient(token).init()
        if not client.me or not client.me.account or not client.me.account.uid:
            logging.warning(f"Failed to fetch user info for user {ctx.user.id}")
            await ctx.respond('❌ Что-то пошло не так. Повторите попытку позже.', delete_after=15, ephemeral=True)
            return
        likes = await client.users_likes_tracks()
        if likes is None:
            logging.info(f"Failed to fetch likes for user {ctx.user.id}")
            await ctx.respond('❌ Что-то пошло не так. Повторите попытку позже.', delete_after=15, ephemeral=True)
            return
        elif not likes:
            logging.info(f"Empty likes for user {ctx.user.id}")
            await ctx.respond('❌ У вас нет треков в плейлисте «Мне нравится».', delete_after=15, ephemeral=True)
            return
        
        real_tracks = await gather(*[track_short.fetch_track_async() for track_short in likes.tracks], return_exceptions=True)
        tracks = [track for track in real_tracks if not isinstance(track, BaseException)]  # Can't fetch user tracks
        embed = await generate_item_embed(tracks)
        logging.info(f"Successfully fetched likes for user {ctx.user.id}")
        await ctx.respond(embed=embed, view=ListenView(tracks))
    
    @account.command(description="Получить ваши плейлисты.")
    async def playlists(self, ctx: discord.ApplicationContext) -> None:
        logging.info(f"Playlists command invoked by user {ctx.user.id} in guild {ctx.guild_id}")

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
        embed = generate_playlists_embed(0, playlists)

        logging.info(f"Successfully fetched playlists for user {ctx.user.id}")
        await ctx.respond(embed=embed, view=MyPlaylists(ctx), ephemeral=True)

    discord.Option
    @discord.slash_command(description="Найти контент и отправить информацию о нём. Возвращается лучшее совпадение.")
    @discord.option(
        "тип",
        parameter_name='content_type',
        description="Тип контента для поиска.",
        type=discord.SlashCommandOptionType.string,
        choices=['Трек', 'Альбом', 'Артист', 'Плейлист', 'Свой плейлист'],
    )
    @discord.option(
        "запрос",
        parameter_name='name',
        description="Название контента для поиска (По умолчанию трек).",
        type=discord.SlashCommandOptionType.string,
        autocomplete=discord.utils.basic_autocomplete(get_search_suggestions)
    )
    async def find(
        self,
        ctx: discord.ApplicationContext,
        content_type: Literal['Трек', 'Альбом', 'Артист', 'Плейлист', 'Свой плейлист'],
        name: str
    ) -> None:
        logging.info(f"Find command invoked by user {ctx.user.id} in guild {ctx.guild_id} for '{content_type}' with name '{name}'")

        guild = self.db.get_guild(ctx.guild_id)
        token = self.users_db.get_ym_token(ctx.user.id)
        if not token:
            logging.info(f"No token found for user {ctx.user.id}")
            await ctx.respond("❌ Необходимо указать свой токен доступа с помощью команды /login.", delete_after=15, ephemeral=True)
            return

        try:
            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            logging.info(f"User {ctx.user.id} provided invalid token")
            await ctx.respond("❌ Недействительный токен. Если это не так, попробуйте ещё раз.", delete_after=15, ephemeral=True)
            return

        if content_type == 'Свой плейлист':
            if not client.me or not client.me.account or not client.me.account.uid:
                logging.warning(f"Failed to get user info for user {ctx.user.id}")
                await ctx.respond("❌ Не удалось получить информацию о пользователе.", delete_after=15, ephemeral=True)
                return

            playlists = await client.users_playlists_list(client.me.account.uid)
            result = next((playlist for playlist in playlists if playlist.title == name), None)
            if not result:
                logging.info(f"User {ctx.user.id} playlist '{name}' not found")
                await ctx.respond("❌ Плейлист не найден.", delete_after=15, ephemeral=True)
                return
            
            tracks = await result.fetch_tracks_async()
            if not tracks:
                logging.info(f"User {ctx.user.id} playlist '{name}' is empty")
                await ctx.respond("❌ Плейлист пуст.", delete_after=15, ephemeral=True)
                return
            
            for track_short in tracks:
                track = cast(Track, track_short.track)
                if (track.explicit or track.content_warning) and not guild['allow_explicit']:
                    logging.info(f"User {ctx.user.id} playlist '{name}' contains explicit content and is not allowed on this server")
                    await ctx.respond("❌ Explicit контент запрещён на этом сервере.", delete_after=15, ephemeral=True)
                    return
            
            embed = await generate_item_embed(result)
            view = ListenView(result)
        else:
            result = await client.search(name, True)
        
            if not result:
                logging.warning(f"Failed to search for '{name}' for user {ctx.user.id}")
                await ctx.respond("❌ Что-то пошло не так. Повторите попытку позже.", delete_after=15, ephemeral=True)
                return

            if content_type == 'Трек':
                content = result.tracks
            elif content_type == 'Альбом':
                content = result.albums
            elif content_type == 'Артист':
                content = result.artists
            elif content_type == 'Плейлист':
                content = result.playlists

            if not content:
                logging.info(f"User {ctx.user.id} search for '{name}' returned no results")
                await ctx.respond("❌ По запросу ничего не найдено.", delete_after=15, ephemeral=True)
                return
            content = content.results[0]

            embed = await generate_item_embed(content)
            view = ListenView(content)

            if isinstance(content, (Track, Album)) and (content.explicit or content.content_warning) and not guild['allow_explicit']:
                logging.info(f"User {ctx.user.id} search for '{name}' returned explicit content and is not allowed on this server")
                await ctx.respond("❌ Explicit контент запрещён на этом сервере.", delete_after=15, ephemeral=True)
                return
            elif isinstance(content, Artist):
                tracks = await content.get_tracks_async()
                if not tracks:
                    logging.info(f"User {ctx.user.id} search for '{name}' returned no tracks")
                    await ctx.respond("❌ Треки от этого исполнителя не найдены.", delete_after=15, ephemeral=True)
                    return
                for track in tracks:
                    if (track.explicit or track.content_warning) and not guild['allow_explicit']:
                        logging.info(f"User {ctx.user.id} search for '{name}' returned explicit content and is not allowed on this server")
                        view = None
                        embed.set_footer(text="Воспроизведение недоступно, так как у автора присутствуют Explicit треки")
                        break
            elif isinstance(content, Playlist):
                tracks = await content.fetch_tracks_async()
                if not tracks:
                    logging.info(f"User {ctx.user.id} search for '{name}' returned no tracks")
                    await ctx.respond("❌ Пустой плейлист.", delete_after=15, ephemeral=True)
                    return
                for track_short in content.tracks:
                    track = cast(Track, track_short.track)
                    if (track.explicit or track.content_warning) and not guild['allow_explicit']:
                        logging.info(f"User {ctx.user.id} search for '{name}' returned explicit content and is not allowed on this server")
                        view = None
                        embed.set_footer(text="Воспроизведение недоступно, так как у автора присутствуют Explicit треки")
                        break
        
        logging.info(f"Successfully generated '{content_type}' message for user {ctx.author.id}")
        await ctx.respond(embed=embed, view=view)

