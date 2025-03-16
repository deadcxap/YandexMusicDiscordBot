import asyncio
import logging
from typing import Any, Literal, cast

import yandex_music.exceptions
from yandex_music import ClientAsync as YMClient

import discord
from discord.ui import View
from discord import Interaction, ApplicationContext, RawReactionActionEvent, MISSING

from MusicBot.database import VoiceGuildsDatabase, BaseUsersDatabase

class BaseBot:
    
    menu_views: dict[int, View] = {}  # Store menu views and delete them when needed to prevent memory leaks for after callbacks.
    _ym_clients: dict[str, YMClient] = {}  # Store YM clients to prevent creating new ones for each command.
    
    def __init__(self, bot: discord.Bot | None) -> None:
        self.bot = bot
        self.db = VoiceGuildsDatabase()
        self.users_db = BaseUsersDatabase()
    
    async def init_ym_client(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        token: str | None = None
    ) -> YMClient | None:
        """Initialize Yandex Music client. Return client on success. Return None if no token found and respond to the context.
        
        Args:
            ctx (ApplicationContext | Interaction | RawReactionActionEvent): Context.
            token (str | None, optional): Token. Fetched from database if not provided. Defaults to None.
        
        Returns:
            (YMClient | None): Client or None.
        """
        logging.debug("[BASE_BOT] Initializing Yandex Music client")

        if not (token := await self.get_ym_token(ctx)):
            logging.debug("[BASE_BOT] No token found")
            await self.respond(ctx, "error", "Укажите токен через /account login.", delete_after=15, ephemeral=True)
            return None

        try:
            if token in self._ym_clients:
                client = self._ym_clients[token]
            
                await client.account_status()
                return client

            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            del self._ym_clients[token]
            await self.respond(ctx, "error", "Недействительный токен Yandex Music.", ephemeral=True, delete_after=15)
            return None

        self._ym_clients[token] = client
        return client
    
    async def get_ym_token(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent) -> str | None:
        """Get Yandex Music token from context. It's either individual or single."""
        
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None

        if not ctx.guild_id or not uid:
            logging.info("[VC_EXT] No guild id or user id found")
            return None

        guild = await self.db.get_guild(ctx.guild_id, projection={'single_token_uid': 1})
        
        if guild['single_token_uid']:
            return await self.users_db.get_ym_token(guild['single_token_uid'])
        else:
            return await self.users_db.get_ym_token(uid)
    
    async def respond(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        response_type: Literal['info', 'success', 'error'] | None = None,
        content: str | None = None,
        *,
        delete_after: float | None = None,
        ephemeral: bool = False,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
        **kwargs: Any
    ) -> discord.Interaction | discord.WebhookMessage | discord.Message | None:
        """Send response message based on context type. `self.bot` must be set in order to use RawReactionActionEvent context type.
        RawReactionActionEvent can't be ephemeral.
        
        Args:
            ctx (ApplicationContext | Interaction | RawReactionActionEvent): Context.
            content (str): Message content to send. If embed is not set, used as description.
            response_type (Literal['info', 'success', 'error'] | None, optional): Response type. Applies if embed is not specified.
            delete_after (float, optional): Time after which the message will be deleted. Defaults to None.
            ephemeral (bool, optional): Whether the message is ephemeral. Defaults to False.
            embed (discord.Embed, optional): Discord embed. Defaults to None.
            view (discord.ui.View, optional): Discord view. Defaults to None.
            kwargs: Additional arguments for embed generation. Applies if embed is not specified.
        
        Returns:
            (discord.InteractionMessage | discord.WebhookMessage | discord.Message | None): Message or None. Type depends on the context type.
        """
        
        if not embed and response_type:
            if content:
                kwargs['description'] = content
            embed = self.generate_response_embed(response_type, **kwargs)
            content = None
        
        if not isinstance(ctx, RawReactionActionEvent) and ctx.response.is_done():
            view = MISSING
        
        if not isinstance(ctx, RawReactionActionEvent):
            return await ctx.respond(content, delete_after=delete_after, ephemeral=ephemeral, view=view, embed=embed)
        elif self.bot:
            channel = self.bot.get_channel(ctx.channel_id)
            if isinstance(channel, (discord.abc.Messageable)):
                return await channel.send(content, delete_after=delete_after, view=view, embed=embed)  # type: ignore

        return None

    async def get_message_by_id(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        message_id: int
    ) -> discord.Message | None:
        """Get message by id based on context type. self.bot must be set in order to use RawReactionActionEvent context type.
        
        Args:
            ctx (ApplicationContext | Interaction | RawReactionActionEvent): Context.
            message_id (int): Message id.
        
        Returns:
            (discord.Message | None): Message or None.
        
        Raises:
            ValueError: Bot instance is not set.
            discord.DiscordException: Failed to get message.
        """
        try:
            if isinstance(ctx, ApplicationContext):
                return await ctx.fetch_message(message_id)
            elif isinstance(ctx, Interaction):
                return ctx.client.get_message(message_id)
            elif not self.bot:
                raise ValueError("Bot instance is not set.")
            else:
                return self.bot.get_message(message_id)
        except discord.DiscordException as e:
            logging.debug(f"[BASE_BOT] Failed to get message: {e}")
            raise
    
    async def get_discord_user_by_id(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, user_id: int) -> discord.User | None:
        if isinstance(ctx, ApplicationContext) and ctx.user:
            logging.debug(f"[BASE_BOT] Getting user {user_id} from ApplicationContext")
            return await ctx.bot.fetch_user(user_id)
        elif isinstance(ctx, Interaction):
            logging.debug(f"[BASE_BOT] Getting user {user_id} from Interaction")
            return await ctx.client.fetch_user(user_id)
        elif not self.bot:
            raise ValueError("Bot instance is not available")
        else:
            logging.debug(f"[BASE_BOT] Getting user {user_id} from bot instance")
            return await self.bot.fetch_user(user_id)
    
    async def get_viber_id_from_ctx(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent) -> int | None:
        if not ctx.guild_id:
            logging.warning("[BASE_BOT] Guild not found")
            return None

        guild = await self.db.get_guild(ctx.guild_id, projection={'current_viber_id': 1})

        if guild['current_viber_id']:
            return guild['current_viber_id']

        return ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None

    async def update_menu_views_dict(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        *,
        disable: bool = False
    ) -> None:
        """Genereate a new menu view and update the `menu_views` dict. This prevents creating multiple menu views for the same guild.
        Use guild id as a key to access menu view.

        Args:
            ctx (ApplicationContext | Interaction | RawReactionActionEvent): Context
            guild (ExplicitGuild): Guild.
            disable (bool, optional): Disable menu. Defaults to False.
        """
        logging.debug(f"[BASE_BOT] Updating menu views dict for guild {ctx.guild_id}")
        from MusicBot.ui import MenuView
        
        if not ctx.guild_id:
            logging.warning("[BASE_BOT] Guild not found")
            return

        if ctx.guild_id in self.menu_views:
            self.menu_views[ctx.guild_id].stop()
        
        self.menu_views[ctx.guild_id] = await MenuView(ctx).init(disable=disable)
    
    def generate_response_embed(
        self,
        embed_type: Literal['info', 'success', 'error'] = 'info',
        **kwargs: Any
    ) -> discord.Embed:
        
        embed = discord.Embed(**kwargs)
        embed.set_author(name='YandexMusic', icon_url="https://github.com/Lemon4ksan/YandexMusicDiscordBot/blob/main/assets/Logo.png?raw=true")

        if embed_type == 'info':
            embed.color = 0xfed42b
        elif embed_type == 'success':
            embed.set_author(name = "✅ Успех")
            embed.color = discord.Color.green()
        else:
            embed.set_author(name = "❌ Ошибка")
            embed.color = discord.Color.red()

        return embed
    
    def get_current_event_loop(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent) -> asyncio.AbstractEventLoop:
        """Get the current event loop. If the context is a RawReactionActionEvent, get the loop from the self.bot instance.

        Args:
            ctx (ApplicationContext | Interaction | RawReactionActionEvent): Context.

        Raises:
            TypeError: If the context is not a RawReactionActionEvent, ApplicationContext or Interaction.
            ValueError: If the context is a RawReactionActionEvent and the bot is not set.

        Returns:
            asyncio.AbstractEventLoop: Current event loop.
        """
        if isinstance(ctx, Interaction):
            return ctx.client.loop
        elif isinstance(ctx, ApplicationContext):
            return ctx.bot.loop
        elif isinstance(ctx, RawReactionActionEvent):
            if not self.bot:
                raise ValueError("Bot is not set.")
            return self.bot.loop
        else:
            raise TypeError(f"Invalid context type: '{type(ctx).__name__}'.")
