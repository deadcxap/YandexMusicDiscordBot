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

from MusicBot.ui import ListenView
from MusicBot.cogs.utils.embeds import generate_item_embed

users_db = BaseUsersDatabase()

def setup(bot):
    bot.add_cog(General(bot))

async def get_search_suggestions(ctx: discord.AutocompleteContext) -> list[str]:
    if not ctx.interaction.user or not ctx.value or len(ctx.value) < 2:
        return []

    token = await users_db.get_ym_token(ctx.interaction.user.id)
    if not token:
        logging.info(f"[GENERAL] User {ctx.interaction.user.id} has no token")
        return []

    try:
        client = await YMClient(token).init()
    except yandex_music.exceptions.UnauthorizedError:
        logging.info(f"[GENERAL] User {ctx.interaction.user.id} provided invalid token")
        return []
    
    content_type = ctx.options['тип']
    search = await client.search(ctx.value)
    if not search:
        logging.warning(f"[GENERAL] Failed to search for '{ctx.value}' for user {ctx.interaction.user.id}")
        return []
    
    res = []
    logging.debug(f"[GENERAL] Searching for '{ctx.value}' for user {ctx.interaction.user.id}")
    
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
        else:
            playlists_list = await client.users_playlists_list(client.me.account.uid)
            res = [playlist.title if playlist.title else 'Без названия' for playlist in playlists_list]

    return res[:100]

async def get_user_playlists_suggestions(ctx: discord.AutocompleteContext) -> list[str]:
    if not ctx.interaction.user or not ctx.value or len(ctx.value) < 2:
        return []

    token = await users_db.get_ym_token(ctx.interaction.user.id)
    if not token:
        logging.info(f"[GENERAL] User {ctx.interaction.user.id} has no token")
        return []

    try:
        client = await YMClient(token).init()
    except yandex_music.exceptions.UnauthorizedError:
        logging.info(f"[GENERAL] User {ctx.interaction.user.id} provided invalid token")
        return []
    
    playlists_list = await client.users_playlists_list()
    return [playlist.title if playlist.title else 'Без названия' for playlist in playlists_list]

class General(Cog):
    
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.db = BaseGuildsDatabase()
        self.users_db = users_db
    
    account = discord.SlashCommandGroup("account", "Команды, связанные с аккаунтом.")
    
    @discord.slash_command(description="Получить информацию о командах YandexMusic.")
    @discord.option(
        "command",
        description="Название команды.",
        type=discord.SlashCommandOptionType.string,
        default='all'
    )
    async def help(self, ctx: discord.ApplicationContext, command: str) -> None:
        logging.info(f"[GENERAL] Help command invoked by {ctx.user.id} for command '{command}'")

        response_message = None
        embed = discord.Embed(
            title='Помощь',
            color=0xfed42b
        )
        embed.set_author(name='YandexMusic')
        embed.description = '__Использование__\n'

        if command == 'all':
            embed.description = (
                "Этот бот позволяет слушать музыку из вашего аккаунта Яндекс Музыки.\n"
                "Зарегистрируйте свой токен с помощью /login. Его можно получить [здесь](https://github.com/MarshalX/yandex-music-api/discussions/513).\n"
                "Для получения помощи по конкретной команде, введите /help <команда>.\n"
                "Для изменения настроек необходимо иметь права управления каналами на сервере.\n\n"
                "Помните, что это **не замена Яндекс Музыки**, а лишь её дополнение. Не ожидайте безупречного звука.\n\n"
                "**Для дополнительной помощи, присоединяйтесь к [серверу любителей Яндекс Музыки](https://discord.gg/gkmFDaPMeC).**"
            )

            embed.add_field(
                name='__Основные команды__',
                value="""`account`
                `find`
                `help`
                `queue`
                `settings`
                `track`
                `voice`"""
            )

            embed.set_footer(text='©️ Bananchiki')
        elif command == 'account':
            embed.description += (
                "Ввести токен Яндекс Музыки. Его можно получить [здесь](https://github.com/MarshalX/yandex-music-api/discussions/513).\n"
                "```/account login <token>```\n"
                "Удалить токен из базы данных бота.\n```/account remove```\n"
                "Получить ваш плейлист.\n```/account playlist <название>```\n"
                "Получить плейлист «Мне нравится».\n```/account likes```\n"
                "Получить ваши рекомендации.\n```/account recommendations <тип>```\n"
            )
        elif command == 'find':
            embed.description += (
                "Вывести информацию о треке (по умолчанию), альбоме, авторе или плейлисте. Позволяет добавить музыку в очередь. "
                "В названии можно уточнить автора через «-». Возвращается лучшее совпадение.\n```/find <тип> <название>```"
            )
        elif command == 'help':
            embed.description += (
                "Вывести список всех команд.\n```/help```\n"
                "Получить информацию о конкретной команде.\n```/help <команда>```"
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
                "Разрешить или запретить голосование.\n```/settings vote <тип>```\n"
                "Разрешить или запретить отключение/подключение бота к каналу участникам без прав управления каналом.\n```/settings connect```\n"
                "`Примечание`: Только пользователи с разрешением управления каналом могут менять настройки."
            )
        elif command == 'track':
            embed.description += (
                "`Примечание`: Если вы один в голосовом канале или имеете разрешение управления каналом, голосование не начинается.\n\n"
                "Переключиться на следующий трек в очереди. \n```/track next```\n"
                "Приостановить текущий трек.\n```/track pause```\n"
                "Возобновить текущий трек.\n```/track resume```\n"
                "Прервать проигрывание, удалить историю, очередь и текущий плеер.\n ```/track stop```\n"
                "Добавить трек в плейлист «Мне нравится» или удалить его, если он уже там.\n```/track like```"
                "Запустить Мою Волну по текущему треку.\n```/track vibe```"
            )
        elif command == 'voice':
            embed.description += (
                "`Примечание`: Доступность меню и Моей Волны зависит от настроек сервера.\n\n"
                "Присоединить бота в голосовой канал. Требует разрешения управления каналом.\n```/voice join```\n"
                "Заставить бота покинуть голосовой канал. Требует разрешения управления каналом.\n ```/voice leave```\n"
                "Создать меню проигрывателя. По умолчанию работает только когда в канале один человек.\n```/voice menu```\n"
                "Запустить Мою Волну. По умолчанию работает только когда в канале один человек.\n```/vibe```"
            )
        else:
            response_message = '❌ Неизвестная команда.'
            embed = None

        await ctx.respond(response_message, embed=embed, ephemeral=True)
    
    @account.command(description="Ввести токен Яндекс Музыки.")
    @discord.option("token", type=discord.SlashCommandOptionType.string, description="Токен.")
    async def login(self, ctx: discord.ApplicationContext, token: str) -> None:
        logging.info(f"[GENERAL] Login command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        try:
            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            logging.info(f"[GENERAL] Invalid token provided by user {ctx.author.id}")
            await ctx.respond('❌ Недействительный токен.', delete_after=15, ephemeral=True)
            return
        about = cast(yandex_music.Status, client.me).to_dict()
        uid = ctx.author.id

        await self.users_db.update(uid, {'ym_token': token})
        logging.info(f"[GENERAL] Token saved for user {ctx.author.id}")
        await ctx.respond(f'Привет, {about['account']['first_name']}!', delete_after=15, ephemeral=True)
    
    @account.command(description="Удалить токен из базы данных бота.")
    async def remove(self, ctx: discord.ApplicationContext) -> None:
        logging.info(f"[GENERAL] Remove command invoked by user {ctx.author.id} in guild {ctx.guild.id}")
        await self.users_db.update(ctx.user.id, {'ym_token': None})
        await ctx.respond(f'Токен был удалён.', delete_after=15, ephemeral=True)

    @account.command(description="Получить плейлист «Мне нравится»")
    async def likes(self, ctx: discord.ApplicationContext) -> None:
        logging.info(f"[GENERAL] Likes command invoked by user {ctx.author.id} in guild {ctx.guild.id}")

        token = await self.users_db.get_ym_token(ctx.user.id)
        if not token:
            logging.info(f"[GENERAL] No token found for user {ctx.user.id}")
            await ctx.respond("❌ Укажите токен через /account login.", delete_after=15, ephemeral=True)
            return

        client = await YMClient(token).init()
        if not client.me or not client.me.account or not client.me.account.uid:
            logging.warning(f"Failed to fetch user info for user {ctx.user.id}")
            await ctx.respond('❌ Что-то пошло не так. Повторите попытку позже.', delete_after=15, ephemeral=True)
            return

        likes = await client.users_likes_tracks()
        if likes is None:
            logging.info(f"[GENERAL] Failed to fetch likes for user {ctx.user.id}")
            await ctx.respond('❌ Что-то пошло не так. Повторите попытку позже.', delete_after=15, ephemeral=True)
            return
        elif not likes:
            logging.info(f"[GENERAL] Empty likes for user {ctx.user.id}")
            await ctx.respond('❌ У вас нет треков в плейлисте «Мне нравится».', delete_after=15, ephemeral=True)
            return
        
        real_tracks = await gather(*[track_short.fetch_track_async() for track_short in likes.tracks], return_exceptions=True)
        tracks = [track for track in real_tracks if not isinstance(track, BaseException)]  # Can't fetch user tracks
        embed = await generate_item_embed(tracks)
        logging.info(f"[GENERAL] Successfully fetched likes for user {ctx.user.id}")
        await ctx.respond(embed=embed, view=ListenView(tracks))
    
    @account.command(description="Получить ваши рекомендации.")
    @discord.option(
        'тип',
        parameter_name='content_type',
        description="Вид рекомендаций.",
        type=discord.SlashCommandOptionType.string,
        choices=['Премьера', 'Плейлист дня', 'Дежавю']
    )
    async def recommendations(
        self,
        ctx: discord.ApplicationContext,
        content_type: Literal['Премьера', 'Плейлист дня', 'Дежавю']
    )-> None:
        # NOTE: Recommendations can be accessed by using /find, but it's more convenient to have it in separate command.
        logging.debug(f"[GENERAL] Recommendations command invoked by user {ctx.user.id} in guild {ctx.guild_id} for type '{content_type}'")

        guild = await self.db.get_guild(ctx.guild_id)
        token = await self.users_db.get_ym_token(ctx.user.id)
        if not token:
            await ctx.respond("❌ Укажите токен через /account login.", delete_after=15, ephemeral=True)
            return

        client = await YMClient(token).init()

        search = await client.search(content_type, False, 'playlist')
        if not search or not search.playlists:
            logging.info(f"[GENERAL] Failed to fetch recommendations for user {ctx.user.id}")
            await ctx.respond('❌ Что-то пошло не так. Повторите попытку позже.', delete_after=15, ephemeral=True)
            return

        playlist = search.playlists.results[0]
        if playlist is None:
            logging.info(f"[GENERAL] Failed to fetch recommendations for user {ctx.user.id}")
            await ctx.respond('❌ Что-то пошло не так. Повторите попытку позже.', delete_after=15, ephemeral=True)

        tracks = await playlist.fetch_tracks_async()
        if not tracks:
            logging.info(f"[GENERAL] User {ctx.user.id} search for '{content_type}' returned no tracks")
            await ctx.respond("❌ Пустой плейлист.", delete_after=15, ephemeral=True)
            return

        embed = await generate_item_embed(playlist)
        view = ListenView(playlist)
            
        for track_short in playlist.tracks:
            track = cast(Track, track_short.track)
            if (track.explicit or track.content_warning) and not guild['allow_explicit']:
                logging.info(f"[GENERAL] User {ctx.user.id} search for '{content_type}' returned explicit content and is not allowed on this server")
                embed.set_footer(text="Воспроизведение недоступно, так как в плейлисте присутствуют Explicit треки")
                view = None
                break

        await ctx.respond(embed=embed, view=view)

    @account.command(description="Получить ваш плейлист.")
    @discord.option(
        "запрос",
        parameter_name='name',
        description="Название плейлиста.",
        type=discord.SlashCommandOptionType.string,
        autocomplete=discord.utils.basic_autocomplete(get_user_playlists_suggestions)
    )
    async def playlist(self, ctx: discord.ApplicationContext, name: str) -> None:
        logging.info(f"[GENERAL] Playlists command invoked by user {ctx.user.id} in guild {ctx.guild_id}")

        guild = await self.db.get_guild(ctx.guild_id, projection={'allow_explicit': 1})
        token = await self.users_db.get_ym_token(ctx.user.id)
        if not token:
            logging.info(f"[GENERAL] No token found for user {ctx.user.id}")
            await ctx.respond("❌ Укажите токен через /account login.", delete_after=15, ephemeral=True)
            return

        try:
            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            logging.info(f"[GENERAL] User {ctx.user.id} provided invalid token")
            await ctx.respond("❌ Недействительный токен. Если это не так, попробуйте ещё раз.", delete_after=15, ephemeral=True)
            return

        playlists = await client.users_playlists_list()

        playlist = next((playlist for playlist in playlists if playlist.title == name), None)
        if not playlist:
            logging.info(f"[GENERAL] User {ctx.user.id} playlist '{name}' not found")
            await ctx.respond("❌ Плейлист не найден.", delete_after=15, ephemeral=True)
            return

        tracks = await playlist.fetch_tracks_async()
        if not tracks:
            logging.info(f"[GENERAL] User {ctx.user.id} playlist '{name}' is empty")
            await ctx.respond("❌ Плейлист пуст.", delete_after=15, ephemeral=True)
            return
    
        embed = await generate_item_embed(playlist)
        view = ListenView(playlist)
            
        for track_short in playlist.tracks:
            track = cast(Track, track_short.track)
            if (track.explicit or track.content_warning) and not guild['allow_explicit']:
                logging.info(f"[GENERAL] User {ctx.user.id} search for '{name}' returned explicit content and is not allowed on this server")
                embed.set_footer(text="Воспроизведение недоступно, так как в плейлисте присутствуют Explicit треки")
                view = None
                break

        await ctx.respond(embed=embed, view=view)

    @discord.slash_command(description="Найти контент и отправить информацию о нём. Возвращается лучшее совпадение.")
    @discord.option(
        "тип",
        parameter_name='content_type',
        description="Тип контента для поиска.",
        type=discord.SlashCommandOptionType.string,
        choices=['Трек', 'Альбом', 'Артист', 'Плейлист'],
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
        content_type: Literal['Трек', 'Альбом', 'Артист', 'Плейлист'],
        name: str
    ) -> None:
        # TODO: Improve explicit check by excluding bad tracks from the queue and not fully discard the artist/album/playlist.

        logging.info(f"[GENERAL] Find command invoked by user {ctx.user.id} in guild {ctx.guild_id} for '{content_type}' with name '{name}'")

        guild = await self.db.get_guild(ctx.guild_id, projection={'allow_explicit': 1})
        token = await self.users_db.get_ym_token(ctx.user.id)
        if not token:
            logging.info(f"[GENERAL] No token found for user {ctx.user.id}")
            await ctx.respond("❌ Укажите токен через /account login.", delete_after=15, ephemeral=True)
            return

        try:
            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            logging.info(f"[GENERAL] User {ctx.user.id} provided invalid token")
            await ctx.respond("❌ Недействительный токен. Если это не так, попробуйте ещё раз.", delete_after=15, ephemeral=True)
            return

        result = await client.search(name, nocorrect=True)
    
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
            logging.info(f"[GENERAL] User {ctx.user.id} search for '{name}' returned no results")
            await ctx.respond("❌ По запросу ничего не найдено.", delete_after=15, ephemeral=True)
            return
        content = content.results[0]

        embed = await generate_item_embed(content)
        view = ListenView(content)

        if isinstance(content, (Track, Album)) and (content.explicit or content.content_warning) and not guild['allow_explicit']:
            logging.info(f"[GENERAL] User {ctx.user.id} search for '{name}' returned explicit content and is not allowed on this server")
            await ctx.respond("❌ Explicit контент запрещён на этом сервере.", delete_after=15, ephemeral=True)
            return
        elif isinstance(content, Artist):
            tracks = await content.get_tracks_async()
            if not tracks:
                logging.info(f"[GENERAL] User {ctx.user.id} search for '{name}' returned no tracks")
                await ctx.respond("❌ Треки от этого исполнителя не найдены.", delete_after=15, ephemeral=True)
                return
            for track in tracks:
                if (track.explicit or track.content_warning) and not guild['allow_explicit']:
                    logging.info(f"[GENERAL] User {ctx.user.id} search for '{name}' returned explicit content and is not allowed on this server")
                    view = None
                    embed.set_footer(text="Воспроизведение недоступно, так как у автора присутствуют Explicit треки")
                    break
        elif isinstance(content, Playlist):
            tracks = await content.fetch_tracks_async()
            if not tracks:
                logging.info(f"[GENERAL] User {ctx.user.id} search for '{name}' returned no tracks")
                await ctx.respond("❌ Пустой плейлист.", delete_after=15, ephemeral=True)
                return
            for track_short in content.tracks:
                track = cast(Track, track_short.track)
                if (track.explicit or track.content_warning) and not guild['allow_explicit']:
                    logging.info(f"[GENERAL] User {ctx.user.id} search for '{name}' returned explicit content and is not allowed on this server")
                    view = None
                    embed.set_footer(text="Воспроизведение недоступно, так как в плейлисте присутствуют Explicit треки")
                    break
        
        logging.info(f"[GENERAL] Successfully generated '{content_type}' message for user {ctx.author.id}")
        await ctx.respond(embed=embed, view=view)
