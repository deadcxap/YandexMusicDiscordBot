import asyncio
import aiofiles
import logging
import io
from typing import Any, Literal, cast

import yandex_music.exceptions
from yandex_music import Track, TrackShort, ClientAsync as YMClient

import discord
from discord.ui import View
from discord import Interaction, ApplicationContext, RawReactionActionEvent

from MusicBot.cogs.utils import generate_item_embed
from MusicBot.database import VoiceGuildsDatabase, BaseUsersDatabase, ExplicitGuild, ExplicitUser

menu_views: dict[int, View] = {}  # Store menu views and delete them when needed to prevent memory leaks for after callbacks.

class VoiceExtension:

    def __init__(self, bot: discord.Bot | None) -> None:
        self.bot = bot
        self.db = VoiceGuildsDatabase()
        self.users_db = BaseUsersDatabase()

    async def send_menu_message(self, ctx: ApplicationContext | Interaction, *, disable: bool = False) -> bool:
        """Send menu message to the channel and delete old menu message if exists. Return True if sent.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            disable (bool, optional): Disable menu message. Defaults to False.
        
        Returns:
            bool: True if sent, False if not.
        """
        logging.info(f"[VC_EXT] Sending menu message to channel {ctx.channel_id} in guild {ctx.guild_id}")

        if not ctx.guild_id:
            logging.warning("[VC_EXT] Guild id not found in context inside 'create_menu'")
            return False

        guild = await self.db.get_guild(ctx.guild_id, projection={'current_track': 1, 'current_menu': 1, 'vibing': 1})

        if guild['current_track']:
            if not (vc := await self.get_voice_client(ctx)):
                return False

            track = cast(Track, Track.de_json(
                guild['current_track'],
                client=YMClient()  # type: ignore
            ))
            embed = await generate_item_embed(track, guild['vibing'])

            if vc.is_paused():
                embed.set_footer(text='Приостановлено')
            else:
                embed.remove_footer()
        else:
            embed = None

        if guild['current_menu']:
            logging.info(f"[VC_EXT] Deleting old menu message {guild['current_menu']} in guild {ctx.guild_id}")
            message = await self.get_menu_message(ctx, guild['current_menu'])
            if message:
                await message.delete()

        await self._update_menu_views_dict(ctx, disable=disable)
        interaction = await ctx.respond(view=menu_views[ctx.guild_id], embed=embed)
        response = await interaction.original_response() if isinstance(interaction, discord.Interaction) else interaction
        await self.db.update(ctx.guild_id, {'current_menu': response.id})

        logging.info(f"[VC_EXT] New menu message {response.id} created in guild {ctx.guild_id}")
        return True
    
    async def get_menu_message(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, menu_mid: int) -> discord.Message | None:
        """Fetch the menu message by its id. Return the message if found.
        Reset `current_menu` field in the database if not found.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            menu_mid (int): Id of the menu message to fetch.

        Returns:
            (discord.Message | None): Menu message or None.
        """
        logging.debug(f"[VC_EXT] Fetching menu message {menu_mid} in guild {ctx.guild_id}")

        if not ctx.guild_id:
            logging.warning("[VC_EXT] Guild ID not found in context")
            return None

        try:
            if isinstance(ctx, ApplicationContext):
                menu = await ctx.fetch_message(menu_mid)
            elif isinstance(ctx, Interaction):
                menu = ctx.client.get_message(menu_mid)
            elif isinstance(ctx, RawReactionActionEvent):
                if not self.bot:
                    raise ValueError("Bot instance is not set.")
                menu = self.bot.get_message(menu_mid)
            else:
                raise ValueError(f"Invalid context type: '{type(ctx).__name__}'.")
        except discord.DiscordException as e:
            logging.debug(f"[VC_EXT] Failed to get menu message: {e}")
            await self.db.update(ctx.guild_id, {'current_menu': None})
            return None

        if menu:
            logging.debug(f"[VC_EXT] Menu message {menu_mid} successfully fetched")
        else:
            logging.debug(f"[VC_EXT] Menu message {menu_mid} not found in guild {ctx.guild_id}")
            await self.db.update(ctx.guild_id, {'current_menu': None})

        return menu
    
    async def update_menu_full(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        menu_mid: int | None = None,
        *,
        menu_message: discord.Message | None = None,
        button_callback: bool = False
    ) -> bool:
        """Update embed and view of the current menu message. Return True if updated.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            menu_mid (int): Id of the menu message to update. Defaults to None.
            menu_message (discord.Message | None): Message to update. If None, fetches menu from channel using `menu_mid`. Defaults to None.
            button_callback (bool, optional): Should be True if the function is being called from button callback. Defaults to False.

        Returns:
           bool: True if updated, False if not.
        """
        logging.debug(
            f"[VC_EXT] Updating menu embed using " + (
            "interaction context" if isinstance(ctx, Interaction) else
            "application context" if isinstance(ctx, ApplicationContext) else
            "raw reaction context"
            )
        )

        gid = ctx.guild_id
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None

        if not gid or not uid:
            logging.warning("[VC_EXT] Guild ID or User ID not found in context inside 'update_menu_embed'")
            return False

        guild = await self.db.get_guild(gid, projection={'vibing': 1, 'current_track': 1})

        if not menu_message:
            if not menu_mid:
                logging.warning("[VC_EXT] No menu message or menu message id provided")
                return False
            menu_message = await self.get_menu_message(ctx, menu_mid)

        if not menu_message:
            return False

        if not guild['current_track']:
            logging.debug("[VC_EXT] No current track found")
            return False

        track = cast(Track, Track.de_json(
            guild['current_track'],
            client=YMClient()  # type: ignore
        ))
        embed = await generate_item_embed(track, guild['vibing'])

        await self._update_menu_views_dict(ctx)
        try:
            if isinstance(ctx, Interaction) and button_callback:
                # If interaction from menu buttons
                await ctx.edit(embed=embed, view=menu_views[gid])
            else:
                # If interaction from other buttons or commands. They should have their own response.
                await menu_message.edit(embed=embed, view=menu_views[gid])
        except discord.NotFound:
            logging.warning("[VC_EXT] Menu message not found")
            return False

        logging.debug("[VC_EXT] Menu embed updated successfully")
        return True

    async def update_menu_view(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        guild: ExplicitGuild,
        *,
        menu_message: discord.Message | None = None,
        button_callback: bool = False,
        disable: bool = False
    ) -> bool:
        """Update the view of the menu message.

        Args:
            ctx (ApplicationContext | Interaction | RawReactionActionEvent): Context.
            guild (ExplicitGuild): Guild data.
            menu_message (discord.Message | None, optional): Menu message to update. Defaults to None.
            button_callback (bool, optional): If True, the interaction is from a button callback. Defaults to False.
            disable (bool, optional): Disable the view if True. Defaults to False.

        Returns:
            bool: True if the view was updated, False otherwise.
        """
        logging.debug("[VC_EXT] Updating menu view")

        if not guild['current_menu']:
            return False

        menu_message = await self.get_menu_message(ctx, guild['current_menu']) if not menu_message else menu_message
        if not menu_message:
            return False

        await self._update_menu_views_dict(ctx, disable=disable)
        try:
            if isinstance(ctx, Interaction) and button_callback:
                # If interaction from menu buttons
                await ctx.edit(view=menu_views[guild['_id']])
            else:
                # If interaction from other buttons or commands. They should have their own response.
                await menu_message.edit(view=menu_views[guild['_id']])
        except discord.NotFound:
            logging.warning("[VC_EXT] Menu message not found")
            return False

        logging.debug("[VC_EXT] Menu view updated successfully")
        return True
    
    async def update_vibe(
        self,
        ctx: ApplicationContext | Interaction,
        type: str,
        id: str | int,
        *,
        update_settings: bool = False
    ) -> bool:
        """Update vibe state or initialize it if not `guild['vibing']` and replace queue with next tracks.
        User's vibe has type `user` and id `onyourwave`.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            type (str): Type of the item.
            id (str | int): ID of the item.
            update_settings (bool, optional): Update vibe settings by sending feedack usind data from database. Defaults to False.

        Returns:
            bool: True if vibe was updated successfully. False otherwise.
        """
        logging.info(f"[VC_EXT] Updating vibe for guild {ctx.guild_id} with type '{type}' and id '{id}'")

        gid = ctx.guild_id
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None

        if not uid or not gid:
            logging.warning("[VC_EXT] Guild ID or User ID not found in context inside 'vibe_update'")
            return False

        user = await self.users_db.get_user(uid, projection={'ym_token': 1, 'vibe_settings': 1})
        guild = await self.db.get_guild(gid, projection={'vibing': 1, 'current_track': 1})
        client = await self.init_ym_client(ctx, user['ym_token'])

        if not client:
            return False

        if update_settings:
            logging.debug("[VIBE] Updating vibe settings")

            settings = user['vibe_settings']
            await client.rotor_station_settings2(
                f"{type}:{id}",
                mood_energy=settings['mood'],
                diversity=settings['diversity'],
                language=settings['lang']
            )

        if not guild['vibing']:
            feedback = await client.rotor_station_feedback_radio_started(
                f"{type}:{id}",
                f"desktop-user-{client.me.account.uid}",  # type: ignore  # That's made up, but it doesn't do much anyway.
            )

            if not feedback:
                logging.warning(f"[VIBE] Failed to start radio '{type}:{id}'")
                return False
            logging.debug(f"[VIBE] Successfully started radio '{type}:{id}'")

        if guild['current_track']:
            logging.debug("[VIBE] Getting next vibe tracks")

            # Current track here is either the track used to start vibe or the last vibe track played.
            # So we always set the current track as the last track in the queue.
            tracks = await client.rotor_station_tracks(
                f"{type}:{id}",
                queue=guild['current_track']['id']
            )
        else:
            tracks = await client.rotor_station_tracks(f"{type}:{id}")

        if not tracks:
            logging.warning("[VIBE] Failed to get next vibe tracks")
            return False
        
        next_tracks = [cast(Track, track.track) for track in tracks.sequence]
        logging.debug(f"[VIBE] Got next vibe tracks: {[track.title for track in next_tracks]}")

        await self.users_db.update(uid, {
            'vibe_type': type,
            'vibe_id': id,
            'vibe_batch_id': tracks.batch_id
        })
        await self.db.update(gid, {
            'next_tracks': [track.to_dict() for track in next_tracks],
            'current_viber_id': uid,
            'vibing': True
        })

        return True

    async def voice_check(self, ctx: ApplicationContext | Interaction, *, check_vibe_privilage: bool = False) -> bool:
        """Check if bot can perform voice tasks and respond if failed.

        Args:
            ctx (discord.ApplicationContext): Command context.
            check_vibe_privilage (bool, optional): Check if context user is the current viber. Defaults to False.

        Returns:
            bool: Check result.
        """
        if not ctx.user or not ctx.guild:
            logging.warning("[VC_EXT] User or guild not found in context inside 'voice_check'")
            await ctx.respond("❌ Что-то пошло не так. Попробуйте еще раз.", delete_after=15, ephemeral=True)
            return False

        if not await self.users_db.get_ym_token(ctx.user.id):
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
        if not discord.utils.get(voice_clients, guild=ctx.guild):
            logging.debug("[VC_EXT] Voice client not found")
            await ctx.respond("❌ Добавьте бота в голосовой канал при помощи команды /voice join.", delete_after=15, ephemeral=True)
            return False
        
        if check_vibe_privilage:
            guild = await self.db.get_guild(ctx.guild.id, projection={'current_viber_id': 1, 'vibing': 1})
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
            (discord.VoiceClient | None): Voice client or None.
        """
        if isinstance(ctx, (Interaction, ApplicationContext)):
            voice_clients = ctx.client.voice_clients if isinstance(ctx, Interaction) else ctx.bot.voice_clients
            guild = ctx.guild
        elif isinstance(ctx, RawReactionActionEvent):
            if not self.bot:
                raise ValueError("Bot instance is not set.")
            if not ctx.guild_id:
                logging.warning("[VC_EXT] Guild ID not found in context inside 'get_voice_client'")
                return None
            voice_clients = self.bot.voice_clients
            guild = await self.bot.fetch_guild(ctx.guild_id)
        else:
            raise ValueError(f"Invalid context type: '{type(ctx).__name__}'.")

        voice_client = discord.utils.get(voice_clients, guild=guild)

        if voice_client:
            logging.debug("[VC_EXT] Voice client found")
        else:
            logging.debug("[VC_EXT] Voice client not found")

        return cast(discord.VoiceClient | None, voice_client)

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
        Send feedback for vibe track playing if vibing. Should be called if voice requirements are met.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            track (Track): Track to play.
            vc (discord.VoiceClient | None): Voice client.
            menu_message (discord.Message | None): Menu message. If None, fetches menu from channel using message id from database. Defaults to None.
            button_callback (bool): Should be True if the function is being called from button callback. Defaults to False.
            retry (bool): Whether the function is called again.

        Returns:
            (str | None): Song title or None.
        """
        gid = ctx.guild_id
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None

        if not gid or not uid:
            logging.warning("Guild ID or User ID not found in context")
            return None

        guild = await self.db.get_guild(gid, projection={'current_menu': 1, 'vibing': 1, 'current_track': 1})
        vc = await self.get_voice_client(ctx) if not vc else vc

        if not vc:
            return None

        try:
            if not guild['current_track'] or track.id != guild['current_track']['id']:
                await self._download_track(gid, track)
        except yandex_music.exceptions.TimedOutError:
            logging.warning(f"[VC_EXT] Timed out while downloading track '{track.title}'")

            if not isinstance(ctx, RawReactionActionEvent) and ctx.channel:
                channel = cast(discord.VoiceChannel, ctx.channel)

                if not retry:
                    return await self.play_track(ctx, track, vc=vc, button_callback=button_callback, retry=True)

                await channel.send(f"😔 Не удалось загрузить трек. Попробуйте сбросить меню.", delete_after=15)
            return None

        async with aiofiles.open(f'music/{gid}.mp3', "rb") as f:
            track_bytes = io.BytesIO(await f.read())
            song = discord.FFmpegPCMAudio(track_bytes, pipe=True, options='-vn -b:a 64k -filter:a "volume=0.15"')

        await self.db.set_current_track(gid, track)

        if menu_message or guild['current_menu']:
            # Updating menu message before playing to prevent delay and avoid FFMPEG lags.
            await self.update_menu_full(ctx, guild['current_menu'], menu_message=menu_message, button_callback=button_callback)

        if not guild['vibing']:
            # Giving FFMPEG enough time to process the audio file
            await asyncio.sleep(1)

        loop = self._get_current_event_loop(ctx)
        vc.play(song, after=lambda exc: asyncio.run_coroutine_threadsafe(self.next_track(ctx, after=True), loop))

        logging.info(f"[VC_EXT] Playing track '{track.title}'")
        await self.db.update(gid, {'is_stopped': False})

        if guild['vibing']:
            await self._my_vibe_send_start_feedback(ctx, track, uid)

        return track.title

    async def stop_playing(
        self, ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        *,
        vc: discord.VoiceClient | None = None,
        full: bool = False
    ) -> bool:
        """Stop playing music in the voice channel. Required to play next one. Returns True on success.

        Args:
            ctx (ApplicationContext | Interaction | RawReactionActionEvent): Context.
            vc (discord.VoiceClient | None, optional): Voice client. Defaults to None.
            full (bool, optional): Full check includes menu deletion and vibe feedback. Defaults to False.
        
        Returns:
            bool: Whether the playback was stopped.
        """
        logging.debug("[VC_EXT] Stopping playback")

        gid = ctx.guild_id
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None

        if not gid or not uid:
            logging.warning("[VC_EXT] Guild ID not found in context")
            return False

        guild = await self.db.get_guild(gid, projection={'current_menu': 1, 'current_track': 1, 'vibing': 1})
        user = await self.users_db.get_user(uid, projection={'vibe_type': 1, 'vibe_id': 1, 'vibe_batch_id': 1, 'ym_token': 1})
        vc = await self.get_voice_client(ctx) if not vc else vc

        if not vc:
            return False

        await self.db.update(gid, {'current_track': None, 'is_stopped': True})
        vc.stop()

        if full:
            if not await self._full_stop(ctx, guild, gid):
                return False

            if guild['vibing'] and guild['current_track']:
                if not await self._my_vibe_send_stop_feedback(ctx, guild, user):
                    return False

        return True

    async def next_track(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        vc: discord.VoiceClient | None = None,
        *,
        after: bool = False,
        menu_message: discord.Message | None = None,
        button_callback: bool = False
    ) -> str | None:
        """Switch to the next track in the queue. Return track title on success. Performs all additional actions like updating menu and sending vibe feedback.
        Doesn't change track if stopped. Stop playing if tracks list is empty.

        Args:
            ctx (ApplicationContext | Interaction): Context
            vc (discord.VoiceClient, optional): Voice client.
            after (bool, optional): Whether the function is being called by the after callback. Defaults to False.
            menu_message (discord.Message | None): Menu message. If None, fetches menu from channel using message id from database. Defaults to None.
            button_interaction (bool, optional): Should be True if the function is being called from button callback. Defaults to False.

        Returns:
            (str | None): Track title or None.
        """
        logging.debug("[VC_EXT] Switching to next track")

        gid = ctx.guild_id
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None

        if not gid or not uid:
            logging.warning("[VC_EXT] Guild ID or User ID not found in context inside 'next_track'")
            return None

        guild = await self.db.get_guild(gid, projection={'shuffle': 1, 'repeat': 1, 'is_stopped': 1, 'current_menu': 1, 'vibing': 1, 'current_track': 1})
        user = await self.users_db.get_user(uid)
        client = await self.init_ym_client(ctx, user['ym_token'])
        vc = await self.get_voice_client(ctx) if not vc else vc

        if guild['is_stopped'] and after:
            logging.debug("[VC_EXT] Playback is stopped, skipping after callback...")
            return None

        if not client:
            return None

        if not vc:  # Silently return if bot got kicked
            logging.debug("[VC_EXT] Voice client not found in 'next_track'")
            return None

        if guild['current_track'] and guild['current_menu'] and not guild['repeat']:
            logging.debug("[VC_EXT] Adding current track to history")
            await self.db.modify_track(gid, guild['current_track'], 'previous', 'insert')

        if after and guild['current_menu']:
            await self.update_menu_view(ctx, guild, menu_message=menu_message, disable=True)

        if guild['vibing'] and guild['current_track'] and not isinstance(ctx, discord.RawReactionActionEvent):
            if not await self._send_next_vibe_feedback(ctx, guild, user, client, after=after):
                await ctx.respond("❌ Что-то пошло не так. Попробуйте снова.", ephemeral=True)
                return None

        if guild['repeat'] and after:
            logging.debug("[VC_EXT] Repeating current track")
            next_track = guild['current_track']
        elif guild['shuffle']:
            logging.debug("[VC_EXT] Getting random track from queue")
            next_track = await self.db.pop_random_track(gid, 'next')
        else:
            logging.debug("[VC_EXT] Getting next track from queue")
            next_track = await self.db.get_track(gid, 'next')
        
        if not next_track and guild['vibing'] and not isinstance(ctx, discord.RawReactionActionEvent):
            logging.debug("[VC_EXT] No next track found, generating new vibe")
            if not user['vibe_type'] or not user['vibe_id']:
                logging.warning("[VC_EXT] No vibe type or vibe id found in user data")
                return None

            await self.update_vibe(ctx, user['vibe_type'], user['vibe_id'])
            next_track = await self.db.get_track(gid, 'next')

        if next_track:
            title = await self._play_next_track(ctx, next_track, client=client, vc=vc, button_callback=button_callback)

            if after and not guild['current_menu']:
                if isinstance(ctx, discord.RawReactionActionEvent):
                    if not self.bot:
                        raise ValueError("Bot instance not found")

                    channel = cast(discord.VoiceChannel, self.bot.get_channel(ctx.channel_id))
                    await channel.send(f"Сейчас играет: **{title}**!", delete_after=15)
                else:
                    await ctx.respond(f"Сейчас играет: **{title}**!", delete_after=15)

            return title

        logging.info("[VC_EXT] No next track found")
        if after:
            await self.db.update(gid, {'is_stopped': True, 'current_track': None})

        return None

    async def prev_track(self, ctx: ApplicationContext | Interaction, button_callback: bool = False) -> str | None:
        """Switch to the previous track in the queue. Repeat current track if no previous one found.
        Return track title on success.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            button_callback (bool, optional): Whether the command was called by a button interaction. Defaults to False.

        Returns:
            (str | None): Track title or None.
        """
        if not ctx.guild or not ctx.user:
            logging.warning("Guild or User not found in context inside 'prev_track'")
            return None

        current_track = await self.db.get_track(ctx.guild.id, 'current')
        prev_track = await self.db.get_track(ctx.guild.id, 'previous')

        if prev_track:
            logging.debug("[VC_EXT] Previous track found")
            track = prev_track
        elif current_track:
            logging.debug("[VC_EXT] No previous track found. Repeating current track")
            track = current_track
        else:
            logging.debug("[VC_EXT] No previous or current track found")
            track = None

        if track:
            return await self._play_next_track(ctx, track, button_callback=button_callback)

        return None

    async def get_likes(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent) -> list[TrackShort] | None:
        """Get liked tracks. Return list of tracks on success. Return None if no token found.

        Args:
            ctx (ApplicationContext | Interaction): Context.

        Returns:
            (list[Track] | None): List of tracks or None.
        """
        gid = ctx.guild_id
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None

        if not gid or not uid:
            logging.warning("Guild ID or User ID not found in context inside 'play_track'")
            return None

        current_track = await self.db.get_track(gid, 'current')
        client = await self.init_ym_client(ctx, await self.users_db.get_ym_token(uid))

        if not current_track:
            logging.debug("[VC_EXT] Current track not found in 'get_likes'")
            return None

        if not client:
            return None

        likes = await client.users_likes_tracks()
        if not likes:
            logging.debug("[VC_EXT] No likes found")
            return None

        return likes.tracks

    async def react_track(
        self,
        ctx: ApplicationContext | Interaction,
        action: Literal['like', 'dislike']
    ) -> tuple[bool, Literal['added', 'removed'] | None]:
        """Like or dislike current track. Return track title on success.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            action (Literal['like', 'dislike']): Action to perform.

        Returns:
            (tuple[bool, Literal['added', 'removed'] | None]): Tuple with success status and action.
        """
        if not (gid := ctx.guild_id) or not ctx.user:
            logging.warning("[VC_EXT] Guild or User not found")
            return (False, None)

        current_track = await self.db.get_track(gid, 'current')
        client = await self.init_ym_client(ctx, await self.users_db.get_ym_token(ctx.user.id))

        if not current_track:
            logging.debug("[VC_EXT] Current track not found")
            return (False, None)

        if not client:
            return (False, None)

        if action == 'like':
            tracks = await client.users_likes_tracks()
            add_func = client.users_likes_tracks_add
            remove_func = client.users_likes_tracks_remove
        else:
            tracks = await client.users_dislikes_tracks()
            add_func = client.users_dislikes_tracks_add
            remove_func = client.users_dislikes_tracks_remove

        if not tracks:
            return (False, None)

        if str(current_track['id']) not in [str(track.id) for track in tracks]:
            logging.debug(f"[VC_EXT] Track not found in {action}s. Adding...")
            await add_func(current_track['id'])
            return (True, 'added')
        else:
            logging.debug(f"[VC_EXT] Track found in {action}s. Removing...")
            await remove_func(current_track['id'])
            return (True, 'removed')

    async def init_ym_client(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, token: str | None = None) -> YMClient | None:
        """Initialize Yandex Music client. Return client on success. Return None if no token found and respond to the context.
        
        Args:
            ctx (ApplicationContext | Interaction): Context.
            token (str | None, optional): Token. Fetched from database if not provided. Defaults to None.
        
        Returns:
            (YMClient | None): Client or None.
        """
        
        if not token:
            uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None
            token = await self.users_db.get_ym_token(uid) if uid else None

        if not token:
            logging.debug("No token found in 'init_ym_client'")
            if not isinstance(ctx, discord.RawReactionActionEvent):
                await ctx.respond("❌ Укажите токен через /account login.", delete_after=15, ephemeral=True)
            return None
        
        if not hasattr(self, '_ym_clients'):
            self._ym_clients = {}

        if token in self._ym_clients:
            return self._ym_clients[token]
        
        try:
            client = await YMClient(token).init()
        except yandex_music.exceptions.UnauthorizedError:
            logging.debug("UnauthorizedError in 'init_ym_client'")
            if not isinstance(ctx, discord.RawReactionActionEvent):
                await ctx.respond("❌ Недействительный токен. Если это не так, попробуйте ещё раз.", delete_after=15, ephemeral=True)
            return None

        self._ym_clients[token] = client
        return client
    
    async def _update_menu_views_dict(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        *,
        disable: bool = False
    ) -> None:
        """Update menu views in `menu_views` dict. This prevents creating multiple menu views for the same guild.
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

        if ctx.guild_id in menu_views:
            menu_views[ctx.guild_id].stop()
        
        menu_views[ctx.guild_id] = await MenuView(ctx).init(disable=disable)
    
    async def _download_track(self, gid: int, track: Track) -> None:
        """Download track to local storage. Return True on success.

        Args:
            gid (int): Guild ID.
            track (Track): Track to download.
        """
        try:
            await track.download_async(f'music/{gid}.mp3')
        except yandex_music.exceptions.TimedOutError:
            logging.warning(f"[VC_EXT] Timeout downloading {track.title}")
            raise
    
    async def _full_stop(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, guild: ExplicitGuild, gid: int) -> Literal[True]:
        """Stop all actions and delete menu. Return True on success.

        Args:
            ctx (ApplicationContext | Interaction | RawReactionActionEvent): Context.
            guild (ExplicitGuild): Guild.

        Returns:
            Literal[True]: Always returns True.
        """
        logging.debug("[VC_EXT] Performing full stop")

        if gid in menu_views:
            menu_views[gid].stop()
            del menu_views[gid]
        
        if guild['current_menu']:
            menu = await self.get_menu_message(ctx, guild['current_menu'])
            if menu:
                await menu.delete()

        await self.db.update(gid, {
            'current_menu': None, 'repeat': False, 'shuffle': False, 'previous_tracks': [], 'next_tracks': [], 'votes': {}, 'vibing': False
        })
        return True
    
    async def _my_vibe_send_start_feedback(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, track: Track, uid: int):
        """Send vibe start feedback to Yandex Music. Return True on success.

        Args:
            track (Track): Track.
            uid (int): User ID.
        
        Returns:
            bool: True on success, False otherwise.
        """
        user = await self.users_db.get_user(uid)
        client = await self.init_ym_client(ctx, user['ym_token']) if not track.client else track.client
        
        if not client:
            logging.warning(f"[VOICE] No YM client for user {uid}.")
            return False

        feedback = await client.rotor_station_feedback_track_started(
            f"{user['vibe_type']}:{user['vibe_id']}",
            track.id,
            user['vibe_batch_id']  # type: ignore  # Wrong typehints
        )
        logging.debug(f"[VIBE] Track started feedback: {feedback}")
        return True
    
    async def _my_vibe_send_stop_feedback(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        guild: ExplicitGuild,
        user: ExplicitUser
    ) -> bool:
        """Send vibe stop feedback to Yandex Music. Return True on success.
        
        Args:
            ctx (ApplicationContext | Interaction | RawReactionActionEvent): Context.
            guild (ExplicitGuild): Guild.
            user (ExplicitUser): User.
        
        Returns:
            bool: True on success, False otherwise.
        """
        logging.debug("[VC_EXT] Sending vibe stop feedback")

        if not user['ym_token']:
            logging.warning(f"[VOICE] No YM token for user {user['_id']}.")
            return False

        client = await self.init_ym_client(ctx, user['ym_token'])
        if not client:
            logging.info(f"[VOICE] Failed to init YM client for user {user['_id']}")
            if not isinstance(ctx, RawReactionActionEvent):
                await ctx.respond("❌ Что-то пошло не так. Попробуйте позже.", delete_after=15, ephemeral=True)
            return False

        track = guild['current_track']
        if not track:
            logging.info(f"[VOICE] No current track in guild {guild['_id']}")
            return False

        res = await client.rotor_station_feedback_track_finished(
            f"{user['vibe_type']}:{user['vibe_id']}",
            track['id'],
            track['duration_ms'] // 1000,
            user['vibe_batch_id']  # type: ignore  # Wrong typehints
        )
        logging.info(f"[VOICE] User {user['_id']} finished vibing with result: {res}")
        return True

    async def _send_next_vibe_feedback(
        self,
        ctx: ApplicationContext | Interaction,
        guild: ExplicitGuild,
        user: ExplicitUser,
        client: YMClient,
        *,
        after: bool
    ) -> bool:
        """Send vibe feedback to Yandex Music. If the track was skipped, call `update_vibe` to get next tracks.
        This is called when a user skips a track or when a track finishes and not when a user stops the player.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            guild (ExplicitGuild): Guild.
            user (ExplicitUser): User.
            client (YMClient): Yandex Music client.
            after (bool): Whether the track finished or was skipped. If True, the track finished.

        Returns:
            bool: True on success, False otherwise.
        """
        logging.debug(f"[VC_EXT] Sending vibe feedback, after: {after}")

        if not user['vibe_type'] or not user['vibe_id']:
            logging.warning("[VIBE] No vibe type or id found")
            return False

        if not guild['current_track']:
            logging.warning("[VIBE] No current track found")
            return False

        if after:
            feedback = await client.rotor_station_feedback_track_finished(
                f'{user['vibe_type']}:{user['vibe_id']}',
                guild['current_track']['id'],
                guild['current_track']['duration_ms'] // 1000,
                user['vibe_batch_id']  # type: ignore  # Wrong typehints
            )
            logging.debug(f"[VIBE] Finished track feeedback: {feedback}")
        else:
            feedback = await client.rotor_station_feedback_skip(
                f'{user['vibe_type']}:{user['vibe_id']}',
                guild['current_track']['id'],
                guild['current_track']['duration_ms'] // 1000,
                user['vibe_batch_id']  # type: ignore  # Wrong typehints
            )
            if not feedback:
                logging.warning("[VIBE] Failed to send vibe feedback")
                return False

            logging.debug(f"[VIBE] Skipped track feeedback: {feedback}")
            feedback = await self.update_vibe(
                ctx,
                user['vibe_type'],
                user['vibe_id']
            )

        return feedback

    async def _play_next_track(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        next_track: dict[str, Any],
        *,
        client: YMClient | None = None,
        vc: discord.VoiceClient | None = None,
        menu_message: discord.Message | None = None,
        button_callback: bool = False,
    ) -> str | None:
        """Play the `next_track` in the voice channel. Avoids additional button and vibe checks.

        Args:
            ctx (ApplicationContext | Interaction | RawReactionActionEvent): Context.
            next_track (dict[str, Any]): Next track to play.
            vc (discord.VoiceClient | None, optional): Voice client. Defaults to None.
            menu_message (discord.Message | None, optional): Menu message to update. Defaults to None.
            button_callback (bool, optional): Should be True if the function is being called from button callback. Defaults to False.

        Returns:
            str | None: Song title or None.
        """
        client = await self.init_ym_client(ctx) if not client else client

        if not client:
            return None

        if not vc:
            vc = await self.get_voice_client(ctx)

        if not await self.stop_playing(ctx, vc=vc):
            return None

        ym_track = cast(Track, Track.de_json(
            next_track,
            client=client  # type: ignore  # Async client can be used here.
        ))
        return await self.play_track(
            ctx,
            ym_track,
            vc=vc,
            menu_message=menu_message,
            button_callback=button_callback
        )

    def _get_current_event_loop(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent) -> asyncio.AbstractEventLoop:
        """Get the current event loop. If the context is a RawReactionActionEvent, get the loop from the bot.

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
