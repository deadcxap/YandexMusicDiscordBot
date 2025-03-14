import asyncio
import logging
from typing import Any, Literal, cast

import yandex_music.exceptions
from yandex_music import ClientAsync as YMClient

import discord
from discord.ui import View
from discord import Interaction, ApplicationContext, RawReactionActionEvent

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
        logging.debug("[VC_EXT] Initializing Yandex Music client")

        if not token:
            uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None
            token = await self.users_db.get_ym_token(uid) if uid else None

        if not token:
            logging.debug("[VC_EXT] No token found")
            await self.send_response_message(ctx, "❌ Укажите токен через /account login.", delete_after=15, ephemeral=True)
            return None

        try:
            if token in self._ym_clients:
                client = self._ym_clients[token]
            
                await client.account_status()
                return client

            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            del self._ym_clients[token]
            await self.send_response_message(ctx, "❌ Недействительный токен. Обновите его с помощью /account login.", ephemeral=True, delete_after=15)
            return None

        self._ym_clients[token] = client
        return client
    
    async def send_response_message(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        content: str | None = None,
        *,
        delete_after: float | None = None,
        ephemeral: bool = False,
        view: discord.ui.View | None = None,
        embed: discord.Embed | None = None
    ) -> discord.Interaction | discord.WebhookMessage | discord.Message | None:
        """Send response message based on context type. self.bot must be set in order to use RawReactionActionEvent context type.
        RawReactionActionEvent can't be ephemeral.
        
        Args:
            ctx (ApplicationContext | Interaction | RawReactionActionEvent): Context.
            content (str): Message content to send.
            delete_after (float | None, optional): Time after which the message will be deleted. Defaults to None.
            ephemeral (bool, optional): Whether the message is ephemeral. Defaults to False.
            view (discord.ui.View | None, optional): Discord view. Defaults to None.
            embed (discord.Embed | None, optional): Discord embed. Defaults to None.
        
        Returns:
            (discord.InteractionMessage | discord.WebhookMessage | discord.Message | None): Message or None. Type depends on the context type.
        """
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
        logging.debug(f"[VC_EXT] Updating menu views dict for guild {ctx.guild_id}")
        from MusicBot.ui import MenuView
        
        if not ctx.guild_id:
            logging.warning("[VC_EXT] Guild not found")
            return

        if ctx.guild_id in self.menu_views:
            self.menu_views[ctx.guild_id].stop()
        
        self.menu_views[ctx.guild_id] = await MenuView(ctx).init(disable=disable)

    def _get_current_event_loop(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent) -> asyncio.AbstractEventLoop:
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