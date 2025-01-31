import asyncio
import logging
from typing import Any, Literal, cast
from time import time

import yandex_music.exceptions
from yandex_music import Track, TrackShort, ClientAsync as YMClient

import discord
from discord.ui import View
from discord import Interaction, ApplicationContext, RawReactionActionEvent

from MusicBot.cogs.utils import generate_item_embed
from MusicBot.database import VoiceGuildsDatabase, BaseUsersDatabase, ExplicitGuild

# TODO: RawReactionActionEvent is poorly supported.

menu_views: dict[int, View] = {}  # Store menu views and delete them when needed to prevent memory leaks for after callbacks.

class VoiceExtension:

    def __init__(self, bot: discord.Bot | None) -> None:
        self.bot = bot
        self.db = VoiceGuildsDatabase()
        self.users_db = BaseUsersDatabase()

    async def send_menu_message(self, ctx: ApplicationContext | Interaction) -> None:
        from MusicBot.ui import MenuView
        logging.info("[VC_EXT] Sending menu message")

        if not ctx.guild_id:
            logging.warning("[VC_EXT] Guild id not found in context inside 'create_menu'")
            return

        guild = self.db.get_guild(ctx.guild_id)
        embed = None

        if guild['current_track']:
            track = cast(Track, Track.de_json(
                guild['current_track'],
                client=YMClient()  # type: ignore  # Async client can be used here.
            ))
            embed = await generate_item_embed(track, guild['vibing'])
            vc = await self.get_voice_client(ctx)
            if vc and vc.is_paused():
                embed.set_footer(text='Приостановлено')
            else:
                embed.remove_footer()

        if guild['current_menu']:
            logging.info(f"[VC_EXT] Deleting old menu message {guild['current_menu']} in guild {ctx.guild_id}")
            message = await self.get_menu_message(ctx, guild['current_menu'])
            if message:
                await message.delete()

        if ctx.guild_id in menu_views:
            menu_views[ctx.guild_id].stop()
        menu_views[ctx.guild_id] = await MenuView(ctx).init()

        interaction = cast(discord.Interaction, await ctx.respond(view=menu_views[ctx.guild_id], embed=embed))
        response = await interaction.original_response()
        self.db.update(ctx.guild_id, {'current_menu': response.id})

        logging.info(f"[VC_EXT] New menu message {response.id} created in guild {ctx.guild_id}")
    
    async def get_menu_message(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, menu_mid: int) -> discord.Message | None:
        """Fetch the menu message by its id. Return the message if found, None if not.
        Reset `current_menu` field in the database if not found.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            menu_mid (int): Id of the menu message.

        Returns:
            discord.Message | None: Menu message or None.
        """
        logging.debug(f"[VC_EXT] Fetching menu message {menu_mid}...")
        
        if not ctx.guild_id:
            logging.warning("[VC_EXT] Guild ID not found in context")
            return None
        
        try:
            if isinstance(ctx, Interaction):
                menu = ctx.client.get_message(menu_mid)
            elif isinstance(ctx, RawReactionActionEvent):
                if not self.bot:
                    raise ValueError("Bot instance is not set.")
                menu = self.bot.get_message(menu_mid)
            elif isinstance(ctx, ApplicationContext):
                menu = await ctx.fetch_message(menu_mid)
            else:
                raise ValueError(f"Invalid context type: '{type(ctx).__name__}'.")
        except discord.DiscordException as e:
            logging.debug(f"[VC_EXT] Failed to get menu message: {e}")
            self.db.update(ctx.guild_id, {'current_menu': None})
            return None
        
        if menu:
            logging.debug("[VC_EXT] Menu message found")
        else:
            logging.debug("[VC_EXT] Menu message not found. Resetting current_menu field.")
            self.db.update(ctx.guild_id, {'current_menu': None})

        return menu
    
    async def update_menu_embed(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        menu_mid: int,
        button_callback: bool = False
    ) -> bool:
        """Update current menu message by its id. Return True if updated, False if not.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            menu_mid (int): Id of the menu message. There can only be only one menu in the guild.
            button_callback (bool, optional): If True, the interaction is a button interaction. Defaults to False.

        Returns:
           bool: True if updated, False if not.
        """
        from MusicBot.ui import MenuView
        logging.debug(
            f"[VC_EXT] Updating menu embed using " + (
            "interaction context" if isinstance(ctx, Interaction) else
            "application context" if isinstance(ctx, ApplicationContext) else
            "raw reaction context"
            )
        )

        gid = ctx.guild_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.guild.id if ctx.guild else None
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None

        if not gid or not uid:
            logging.warning("[VC_EXT] Guild ID or User ID not found in context inside 'update_menu_embed'")
            return False

        menu = await self.get_menu_message(ctx, menu_mid)
        if not menu:
            return False
        
        token = self.users_db.get_ym_token(uid)
        if not token:
            logging.debug(f"[VC_EXT] No token found for user {uid}")
            return False

        guild = self.db.get_guild(gid)
        current_track = guild['current_track']
        if not current_track:
            logging.debug("[VC_EXT] No current track found")
            return False

        track = cast(Track, Track.de_json(
            current_track,
            client=YMClient(token)  # type: ignore  # Async client can be used here.
        ))
        
        embed = await generate_item_embed(track, guild['vibing'])

        try:
            if gid in menu_views:
                menu_views[gid].stop()
            menu_views[gid] = await MenuView(ctx).init()
            if isinstance(ctx, Interaction) and button_callback:
                # If interaction from menu buttons
                await ctx.edit(embed=embed, view=menu_views[gid])
            else:
                # If interaction from other buttons or commands. They should have their own response.
                await menu.edit(embed=embed, view=menu_views[gid])
        except discord.NotFound:
            logging.warning("[VC_EXT] Menu message not found")
            if gid in menu_views:
                menu_views[gid].stop()
                del menu_views[gid]
            return False

        logging.debug("[VC_EXT] Menu embed updated")
        return True

    async def update_vibe(
        self,
        ctx: ApplicationContext | Interaction,
        type: Literal['track', 'album', 'artist', 'playlist', 'user'],
        id: str | int,
        *,
        update_settings: bool = False,
        button_callback: bool = False
    ) -> str | None:
        """Update vibe state. Return track title on success.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            type (Literal['track', 'album', 'artist', 'playlist', 'user']): Type of the item.
            id (str | int): ID of the item.
            button_callback (bool, optional): If the function is called from button callback. Defaults to False.

        Returns:
            str | None: Track title or None.
        """
        logging.info(f"[VC_EXT] Updating vibe for guild {ctx.guild_id} with type '{type}' and id '{id}'")
        
        gid = ctx.guild_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.guild.id if ctx.guild else None
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None
        if not uid or not gid:
            logging.warning("[VC_EXT] Guild ID or User ID not found in context inside 'vibe_update'")
            return None

        user = self.users_db.get_user(uid)
        if not user['ym_token']:
            logging.info(f"[VC_EXT] User {uid} has no YM token")
            await ctx.respond("❌ Укажите токен через /account login.", ephemeral=True)
            return

        client = await self.init_ym_client(ctx, user['ym_token'])
        if not client:
            return
        
        self.users_db.update(uid, {'vibe_type': type, 'vibe_id': id})
        guild = self.db.get_guild(gid)

        if not guild['vibing']:
            feedback = await client.rotor_station_feedback_radio_started(
                f"{type}:{id}",
                f"desktop-user-{client.me.account.uid}",  # type: ignore
                timestamp=time()
            )
            logging.debug(f"[VIBE] Radio started feedback: {feedback}")
            tracks = await client.rotor_station_tracks(f"{type}:{id}")
            self.db.update(gid, {'vibing': True})
        elif guild['current_track']:
            if update_settings:
                settings = user['vibe_settings']
                await client.rotor_station_settings2(
                    f"{type}:{id}",
                    mood_energy=settings['mood'],
                    diversity=settings['diversity'],
                    language=settings['lang']
                )
            tracks = await client.rotor_station_tracks(
                f"{type}:{id}",
                queue=guild['current_track']['id']
            )
        else:
            tracks = None

        if not tracks:
            logging.warning("[VIBE] Failed to get next vibe tracks")
            await ctx.respond("❌ Что-то пошло не так. Повторите попытку позже.", ephemeral=True)
            return
        
        logging.debug(f"[VIBE] Got next vibe tracks: {[track.track.title for track in tracks.sequence if track.track]}")
        self.users_db.update(uid, {'vibe_batch_id': tracks.batch_id})

        next_tracks = [cast(Track, track.track) for track in tracks.sequence]

        self.db.update(gid, {
            'next_tracks': [track.to_dict() for track in next_tracks[1:]],
            'current_viber_id': uid
        })
        await self.stop_playing(ctx)
        return await self.play_track(ctx, next_tracks[0], button_callback=button_callback)

    async def voice_check(self, ctx: ApplicationContext | Interaction) -> bool:
        """Check if bot can perform voice tasks and respond if failed.

        Args:
            ctx (discord.ApplicationContext): Command context.

        Returns:
            bool: Check result.
        """
        if not ctx.user or not ctx.guild:
            logging.warning("[VC_EXT] User or guild not found in context inside 'voice_check'")
            return False

        token = self.users_db.get_ym_token(ctx.user.id)
        if not token:
            logging.debug(f"[VC_EXT] No token found for user {ctx.user.id}")
            await ctx.respond("❌ Укажите токен через /account login.", delete_after=15, ephemeral=True)
            return False

        if not isinstance(ctx.channel, discord.VoiceChannel):
            logging.debug("[VC_EXT] User is not in a voice channel")
            await ctx.respond("❌ Вы должны отправить команду в голосовом канале.", delete_after=15, ephemeral=True)
            return False
        
        if ctx.user.id not in ctx.channel.voice_states:
            logging.debug("[VC_EXT] User is not connected to the voice channel")
            await ctx.respond("❌ Вы должны находиться в голосовом канале.", delete_after=15, ephemeral=True)
            return False

        voice_clients = ctx.client.voice_clients if isinstance(ctx, Interaction) else ctx.bot.voice_clients
        voice_chat = discord.utils.get(voice_clients, guild=ctx.guild)
        if not voice_chat:
            logging.debug("[VC_EXT] Voice client not found")
            await ctx.respond("❌ Добавьте бота в голосовой канал при помощи команды /voice join.", delete_after=15, ephemeral=True)
            return False
        
        guild = self.db.get_guild(ctx.guild.id)
        member = cast(discord.Member, ctx.user)
        if guild['vibing'] and ctx.user.id != guild['current_viber_id'] and not member.guild_permissions.manage_channels:
            logging.debug("[VIBE] Context user is not the current viber")
            await ctx.respond("❌ Вы не можете взаимодействовать с чужой волной!", delete_after=15, ephemeral=True)
            return False

        logging.debug("[VC_EXT] Voice requirements met")
        return True

    async def get_voice_client(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent) -> discord.VoiceClient | None:
        """Return voice client for the given guild id. Return None if not present.

        Args:
            ctx (ApplicationContext | Interaction): Command context.

        Returns:
            discord.VoiceClient | None: Voice client or None.
        """
        if isinstance(ctx, (Interaction, ApplicationContext)):
            voice_clients = ctx.client.voice_clients if isinstance(ctx, Interaction) else ctx.bot.voice_clients
            guild = ctx.guild
        elif isinstance(ctx, RawReactionActionEvent):
            if not self.bot:
                raise ValueError("Bot instance is not set.")
            if not ctx.guild_id:
                logging.warning("[VC_EXT] Guild ID not found in context inside get_voice_client")
                return None
            voice_clients = self.bot.voice_clients
            guild = await self.bot.fetch_guild(ctx.guild_id)
        else:
            raise ValueError(f"Invalid context type: '{type(ctx).__name__}'.")

        voice_chat = discord.utils.get(voice_clients, guild=guild)

        if voice_chat:
            logging.debug("[VC_EXT] Voice client found")
        else:
            logging.debug("[VC_EXT] Voice client not found")

        return cast(discord.VoiceClient | None, voice_chat)

    async def play_track(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        track: Track,
        *,
        vc: discord.VoiceClient | None = None,
        menu_message: discord.Message | None = None,
        button_callback: bool = False,
        retry: bool = False
    ) -> str | None:
        """Download ``track`` by its id and play it in the voice channel. Return track title on success.
        If sound is already playing, add track id to the queue. There's no response to the context.

        Args:
            ctx (ApplicationContext | Interaction): Context
            track (Track): Track to play.
            vc (discord.VoiceClient | None): Voice client.
            menu_message (discord.Message | None): Menu message.
            button_callback (bool): Whether the interaction is a button callback.
            retry (bool): Whether the function is called again.

        Returns:
            str | None: Song title or None.
        """
        from MusicBot.ui import MenuView

        gid = ctx.guild_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.guild.id if ctx.guild else None
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None
        if not gid or not uid:
            logging.warning("Guild ID or User ID not found in context")
            return None

        if not vc:
            vc = await self.get_voice_client(ctx)
            if not vc:
                return None

        if isinstance(ctx, Interaction):
            loop = ctx.client.loop
        elif isinstance(ctx, ApplicationContext):
            loop = ctx.bot.loop
        elif isinstance(ctx, RawReactionActionEvent):
            if not self.bot:
                raise ValueError("Bot is not set.")
            loop = self.bot.loop
        else:
            raise ValueError(f"Invalid context type: '{type(ctx).__name__}'.")

        self.db.update(gid, {'current_track': track.to_dict()})
        guild = self.db.get_guild(gid)

        try:
            await asyncio.gather(
                track.download_async(f'music/{gid}.mp3'),
                self._update_menu(ctx, guild, track, menu_message, button_callback)
            )
        except yandex_music.exceptions.TimedOutError:
            logging.warning(f"[VC_EXT] Timed out while downloading track '{track.title}'")
            if not isinstance(ctx, RawReactionActionEvent) and ctx.user and ctx.channel:
                channel = cast(discord.VoiceChannel, ctx.channel)
                if not retry:
                    return await self.play_track(ctx, track, vc=vc, button_callback=button_callback, retry=True)
                await channel.send(f"😔 Не удалось загрузить трек. Попробуйте сбросить меню.", delete_after=15)
            return None

        song = discord.FFmpegPCMAudio(f'music/{gid}.mp3', options='-vn -filter:a "volume=0.15"')
        vc.play(song, after=lambda exc: asyncio.run_coroutine_threadsafe(self.next_track(ctx, after=True), loop))
        logging.info(f"[VC_EXT] Playing track '{track.title}'")

        self.db.update(gid, {'is_stopped': False})
        
        if guild['vibing']:
            user = self.users_db.get_user(uid)
            feedback = await cast(YMClient, track.client).rotor_station_feedback_track_started(
                f"{user['vibe_type']}:{user['vibe_id']}",
                track.id,
                user['vibe_batch_id'],  # type: ignore  # wrong typehints
                time()
            )
            logging.debug(f"[VIBE] Track started feedback: {feedback}")

        return track.title

    async def stop_playing(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, vc: discord.VoiceClient | None = None) -> None:

        gid = ctx.guild_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.guild.id if ctx.guild else None
        if not gid:
            logging.warning("[VC_EXT] Guild ID not found in context")
            return

        if not vc:
            vc = await self.get_voice_client(ctx)
        if vc:
            logging.debug("[VC_EXT] Stopping playback")
            self.db.update(gid, {'current_track': None, 'is_stopped': True})
            vc.stop()

    async def next_track(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        vc: discord.VoiceClient | None = None,
        *,
        after: bool = False,
        button_callback: bool = False
    ) -> str | None:
        """Switch to the next track in the queue. Return track title on success.
        Doesn't change track if stopped. Stop playing if tracks list is empty.

        Args:
            ctx (ApplicationContext | Interaction): Context
            vc (discord.VoiceClient, optional): Voice client.
            after (bool, optional): Whether the function is being called by the after callback. Defaults to False.
            button_interaction (bool, optional): Whether the function is being called by a button interaction. Defaults to False.

        Returns:
            str | None: Track title or None.
        """
        from MusicBot.ui import MenuView

        gid = ctx.guild_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.guild.id if ctx.guild else None
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None
        menu_message = None

        if not gid or not uid:
            logging.warning("[VC_EXT] Guild ID or User ID not found in context inside 'next_track'")
            return None

        guild = self.db.get_guild(gid)
        user = self.users_db.get_user(uid)
        if not user['ym_token']:
            logging.debug(f"[VC_EXT] No token found for user {uid}")
            return None

        client = await self.init_ym_client(ctx, user['ym_token'])
        if not client:
            return None

        if guild['is_stopped'] and after:
            logging.debug("[VC_EXT] Playback is stopped, skipping after callback...")
            return None

        if not vc:
            vc = await self.get_voice_client(ctx)
            if not vc:  # Silently return if bot got kicked
                return None

        if after and guild['current_menu']:
            menu_message = await self.get_menu_message(ctx, guild['current_menu'])
            if menu_message:
                if gid in menu_views:
                    menu_views[gid].stop()
                menu_views[gid] = await MenuView(ctx).init(disable=True)
                await menu_message.edit(view=menu_views[gid])

        if guild['vibing'] and not isinstance(ctx, RawReactionActionEvent):
            if not user['vibe_type'] or not user['vibe_id']:
                logging.warning("[VIBE] No vibe type or id found")
                return None

            if guild['current_track']:
                if after:
                    feedback = await client.rotor_station_feedback_track_finished(
                        f'{user['vibe_type']}:{user['vibe_id']}',
                        guild['current_track']['id'],
                        guild['current_track']['duration_ms'] // 1000,
                        user['vibe_batch_id'],  # type: ignore  # Wrong typehints
                        time()
                    )
                    logging.debug(f"[VIBE] Finished track: {feedback}")
                else:
                    feedback = await client.rotor_station_feedback_skip(
                        f'{user['vibe_type']}:{user['vibe_id']}',
                        guild['current_track']['id'],
                        guild['current_track']['duration_ms'] // 1000,
                        user['vibe_batch_id'],  # type: ignore  # Wrong typehints
                        time()
                    )
                    logging.debug(f"[VIBE] Skipped track: {feedback}")
                    return await self.update_vibe(
                        ctx,
                        user['vibe_type'],
                        user['vibe_id'],
                        button_callback=button_callback
                    )

        if guild['repeat'] and after:
            logging.debug("[VC_EXT] Repeating current track")
            next_track = guild['current_track']
        elif guild['shuffle']:
            logging.debug("[VC_EXT] Shuffling tracks")
            next_track = self.db.get_random_track(gid)
        else:
            logging.debug("[VC_EXT] Getting next track")
            next_track = self.db.get_track(gid, 'next')

        if guild['current_track'] and guild['current_menu'] and not guild['repeat']:
            logging.debug("[VC_EXT] Adding current track to history")
            self.db.modify_track(gid, guild['current_track'], 'previous', 'insert')

        if next_track:
            ym_track = Track.de_json(
                next_track,
                client=client  # type: ignore  # Async client can be used here.
            )
            await self.stop_playing(ctx, vc)
            title = await self.play_track(
                ctx,
                ym_track,  # type: ignore  # de_json should always work here.
                vc=vc,
                menu_message=menu_message,
                button_callback=button_callback
            )

            if after and not guild['current_menu'] and not isinstance(ctx, discord.RawReactionActionEvent):
                await ctx.respond(f"Сейчас играет: **{title}**!", delete_after=15)

            return title

        elif guild['vibing'] and not isinstance(ctx, RawReactionActionEvent):
            logging.debug("[VIBE] No next track found, updating vibe")
            if not user['vibe_type'] or not user['vibe_id']:
                logging.warning("[VIBE] No vibe type or id found")
                return None

            return await self.update_vibe(
                ctx,
                user['vibe_type'],
                user['vibe_id'],
                button_callback=button_callback
            )

        logging.info("No next track found")
        self.db.update(gid, {'is_stopped': True, 'current_track': None})
        return None

    async def prev_track(self, ctx: ApplicationContext | Interaction, button_callback: bool = False) -> str | None:
        """Switch to the previous track in the queue. Repeat curren the song if no previous tracks.
        Return track title on success.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            button_callback (bool, optional): Whether the command was called by a button interaction. Defaults to False.

        Returns:
            str | None: Track title or None.
        """
        if not ctx.guild or not ctx.user:
            logging.warning("Guild or User not found in context inside 'prev_track'")
            return None

        gid = ctx.guild.id
        token = self.users_db.get_ym_token(ctx.user.id)
        current_track = self.db.get_track(gid, 'current')
        prev_track = self.db.get_track(gid, 'previous')

        if not token:
            logging.debug(f"[VC_EXT] No token found for user {ctx.user.id}")
            return None

        if prev_track:
            logging.debug("[VC_EXT] Previous track found")
            track: dict[str, Any] | None = prev_track
        elif current_track:
            logging.debug("[VC_EXT] No previous track found. Repeating current track")
            track = self.db.get_track(gid, 'current')
        else:
            logging.debug("[VC_EXT] No previous or current track found")
            track = None

        if track:
            ym_track = Track.de_json(
                track,
                client=YMClient(token)  # type: ignore  # Async client can be used here.
            )
            await self.stop_playing(ctx)
            return await self.play_track(
                ctx,
                ym_track,  # type: ignore  # de_json should always work here.
                button_callback=button_callback
            )

        return None

    async def get_likes(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent) -> list[TrackShort] | None:
        """Get liked tracks. Return list of tracks on success. Return None if no token found.

        Args:
           ctx (ApplicationContext | Interaction): Context.

        Returns:
           list[Track] | None: List of tracks or None.
        """

        gid = ctx.guild_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.guild.id if ctx.guild else None
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None
        if not gid or not uid:
            logging.warning("Guild ID or User ID not found in context inside 'play_track'")
            return None

        current_track = self.db.get_track(gid, 'current')
        token = self.users_db.get_ym_token(uid)
        if not token:
            logging.debug(f"[VC_EXT] No token found for user {uid}")
            return None
        if not current_track:
            logging.debug("[VC_EXT] Current track not found in 'get_likes'")
            return None

        client = await YMClient(token).init()
        likes = await client.users_likes_tracks()
        if not likes:
            logging.debug("[VC_EXT] No likes found")
            return None

        return likes.tracks

    async def like_track(self, ctx: ApplicationContext | Interaction) -> str | Literal['TRACK REMOVED'] | None:
        """Like current track. Return track title on success.

        Args:
           ctx (ApplicationContext | Interaction): Context.

        Returns:
            str | None: Track title or None.
        """
        if not ctx.guild or not ctx.user:
            logging.warning("[VC_EXT] Guild or User not found in context inside 'like_track'")
            return None

        current_track = self.db.get_track(ctx.guild.id, 'current')
        token = self.users_db.get_ym_token(ctx.user.id)
        if not current_track or not token:
            logging.debug("[VC_EXT] Current track or token not found in 'like_track'")
            return None

        client = await YMClient(token).init()
        likes = await self.get_likes(ctx)
        if not likes:
            return None

        ym_track = cast(Track, Track.de_json(
            current_track,
            client=client  # type: ignore  # Async client can be used here.
            )
        )
        if str(ym_track.id) not in [str(track.id) for track in likes]:
            logging.debug("[VC_EXT] Track not found in likes. Adding...")
            await ym_track.like_async()
            return ym_track.title
        else:
            logging.debug("[VC_EXT] Track found in likes. Removing...")
            if not client.me or not client.me.account or not client.me.account.uid:
                logging.debug("Client account not found")
                return None
            await client.users_likes_tracks_remove(ym_track.id, client.me.account.uid)
            return 'TRACK REMOVED'

    async def _retry_update_menu_embed(
        self,
        ctx: ApplicationContext | Interaction,
        menu_mid: int,
        button_callback: bool
    ) -> None:
        update = await self.update_menu_embed(ctx, menu_mid, button_callback)
        for _ in range(10):
            if update:
                break
            await asyncio.sleep(0.25)
            update = await self.update_menu_embed(ctx, menu_mid, button_callback)
    
    async def _update_menu(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        guild: ExplicitGuild,
        track: Track,
        menu_message: discord.Message | None,
        button_callback: bool
    ) -> None:
        from MusicBot.ui import MenuView
        gid = cast(int, ctx.guild_id)

        if guild['current_menu'] and not isinstance(ctx, RawReactionActionEvent):
            if menu_message:
                try:
                    if gid in menu_views:
                        menu_views[gid].stop()
                    menu_views[gid] = await MenuView(ctx).init()
                    await menu_message.edit(embed=await generate_item_embed(track, guild['vibing']), view=menu_views[gid])
                except discord.errors.NotFound:
                    logging.warning("[VC_EXT] Menu message not found. Using 'update_menu_embed' instead.")
                    await self._retry_update_menu_embed(ctx, guild['current_menu'], button_callback)
            else:
                await self._retry_update_menu_embed(ctx, guild['current_menu'], button_callback)

    async def init_ym_client(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, token: str | None = None) -> YMClient | None:
        """Initialize Yandex Music client. Return client on success. Return None if no token found and respond to the context.
        
        Args:
            ctx (ApplicationContext | Interaction): Context.
            token (str | None, optional): Token. Defaults to None.
        
        Returns:
            YMClient | None: Client or None.
        """
        
        if not token:
            uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None
            token = self.users_db.get_ym_token(uid) if uid else None

        if not token:
            logging.debug("No token found in 'init_ym_client'")
            if not isinstance(ctx, discord.RawReactionActionEvent):
                await ctx.respond("❌ Укажите токен через /account login.", delete_after=15, ephemeral=True)
            return None
        
        try:
            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            logging.debug("UnauthorizedError in 'init_ym_client'")
            if not isinstance(ctx, discord.RawReactionActionEvent):
                await ctx.respond("❌ Недействительный токен. Если это не так, попробуйте ещё раз.", delete_after=15, ephemeral=True)
            return None
        return client
