import asyncio
import logging
from typing import Any, Literal, cast

from yandex_music import Track, TrackShort, ClientAsync

import discord
from discord import Interaction, ApplicationContext, RawReactionActionEvent

from MusicBot.cogs.utils import generate_item_embed
from MusicBot.database import VoiceGuildsDatabase, BaseUsersDatabase

class VoiceExtension:

    def __init__(self, bot: discord.Bot | None) -> None:
        self.bot = bot
        self.db = VoiceGuildsDatabase()
        self.users_db = BaseUsersDatabase()

    async def update_menu_embed(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, player_mid: int) -> bool:
        """Update current player message by its id. Return True if updated, False if not.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            player_mid (int): Id of the player message. There can only be only one player in the guild.

        Returns:
           bool: True if updated, False if not.
        """
        from MusicBot.ui import MenuView
        logging.debug(
            f"Updating player embed using " +
            "interaction context" if isinstance(ctx, Interaction) else
            "application context" if isinstance(ctx, ApplicationContext) else
            "raw reaction context"
        )

        gid = ctx.guild_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.guild.id if ctx.guild else None
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None

        if not gid or not uid:
            logging.warning("Guild ID or User ID not found in context inside 'update_player_embed'")
            return False

        player = await self.get_menu_message(ctx, player_mid)
        if not player:
            return False
        
        token = self.users_db.get_ym_token(uid)
        if not token:
            logging.debug(f"No token found for user {uid}")
            return False

        current_track = self.db.get_track(gid, 'current')
        if not current_track:
            logging.debug("No current track found")
            return False

        track = cast(Track, Track.de_json(
            current_track,
            client=ClientAsync(token)  # type: ignore  # Async client can be used here.
        ))
        embed = await generate_item_embed(track)

        if isinstance(ctx, Interaction) and ctx.message and ctx.message.id == player_mid:
            # If interaction from player buttons
            await ctx.edit(embed=embed, view=await MenuView(ctx).init())
        else:
            # If interaction from other buttons or commands. They should have their own response.
            await player.edit(embed=embed, view=await MenuView(ctx).init())

        return True

    async def get_menu_message(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, player_mid: int) -> discord.Message | None:
        """Fetch the player message by its id. Return the message if found, None if not.
        Reset `current_player` field in the database if not found.

        Args:
            ctx (ApplicationContext | Interaction): Context.
            player_mid (int): Id of the player message.

        Returns:
            discord.Message | None: Player message or None.
        """
        logging.debug(f"Fetching player message {player_mid}...")
        
        if not ctx.guild_id:
            logging.warning("Guild ID not found in context")
            return None
        
        try:
            if isinstance(ctx, Interaction):
                player = ctx.client.get_message(player_mid)
            elif isinstance(ctx, RawReactionActionEvent):
                if not self.bot:
                    raise ValueError("Bot instance is not set.")
                player = self.bot.get_message(player_mid)
            elif isinstance(ctx, ApplicationContext):
                player = await ctx.fetch_message(player_mid)
            else:
                raise ValueError(f"Invalid context type: '{type(ctx).__name__}'.")
        except discord.DiscordException as e:
            logging.debug(f"Failed to get player message: {e}")
            self.db.update(ctx.guild_id, {'current_player': None})
            return None
        
        if player:
            logging.debug(f"Player message found")
        else:
            logging.debug("Player message not found. Resetting current_player field.")
            self.db.update(ctx.guild_id, {'current_player': None})

        return player

    async def voice_check(self, ctx: ApplicationContext | Interaction) -> bool:
        """Check if bot can perform voice tasks and respond if failed.

        Args:
            ctx (discord.ApplicationContext): Command context.

        Returns:
            bool: Check result.
        """
        if not ctx.user:
            logging.warning("User not found in context inside 'voice_check'")
            return False

        token = self.users_db.get_ym_token(ctx.user.id)
        if not token:
            logging.debug(f"No token found for user {ctx.user.id}")
            await ctx.respond("❌ Необходимо указать свой токен доступа с помощью команды /login.", delete_after=15, ephemeral=True)
            return False

        channel = ctx.channel
        if not isinstance(channel, discord.VoiceChannel):
            logging.debug("User is not in a voice channel")
            await ctx.respond("❌ Вы должны отправить команду в голосовом канале.", delete_after=15, ephemeral=True)
            return False

        if isinstance(ctx, Interaction):
            channels = ctx.client.voice_clients
        else:
            channels = ctx.bot.voice_clients
        voice_chat = discord.utils.get(channels, guild=ctx.guild)
        if not voice_chat:
            logging.debug("Voice client not found")
            await ctx.respond("❌ Добавьте бота в голосовой канал при помощи команды /voice join.", delete_after=15, ephemeral=True)
            return False
        
        logging.debug("Voice requirements met")
        return True

    async def get_voice_client(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent) -> discord.VoiceClient | None:
        """Return voice client for the given guild id. Return None if not present.

        Args:
            ctx (ApplicationContext | Interaction): Command context.

        Returns:
            discord.VoiceClient | None: Voice client or None.
        """
        if isinstance(ctx, Interaction):
            voice_chat = discord.utils.get(ctx.client.voice_clients, guild=ctx.guild)
        elif isinstance(ctx, RawReactionActionEvent):
            if not self.bot:
                raise ValueError("Bot instance is not set.")
            if not ctx.guild_id:
                logging.warning("Guild ID not found in context inside get_voice_client")
                return None
            voice_chat = discord.utils.get(self.bot.voice_clients, guild=await self.bot.fetch_guild(ctx.guild_id))
        elif isinstance(ctx, ApplicationContext):
            voice_chat = discord.utils.get(ctx.bot.voice_clients, guild=ctx.guild)
        else:
            raise ValueError(f"Invalid context type: '{type(ctx).__name__}'.")

        if voice_chat:
            logging.debug("Voice client found")
        else:
            logging.debug("Voice client not found")

        return cast((discord.VoiceClient | None), voice_chat)

    async def play_track(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        track: Track,
        vc: discord.VoiceClient | None = None
    ) -> str | None:
        """Download ``track`` by its id and play it in the voice channel. Return track title on success.
        If sound is already playing, add track id to the queue. There's no response to the context.

        Args:
            ctx (ApplicationContext | Interaction): Context
            track (Track): Track to play.
            vc (discord.VoiceClient | None): Voice client.

        Returns:
            str | None: Song title or None.
        """
        gid = ctx.guild_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.guild.id if ctx.guild else None
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None
        if not gid or not uid:
            logging.warning("Guild ID or User ID not found in context inside 'play_track'")
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

        guild = self.db.get_guild(gid)
        await track.download_async(f'music/{gid}.mp3')
        song = discord.FFmpegPCMAudio(f'music/{gid}.mp3', options='-vn -filter:a "volume=0.15"')

        vc.play(song, after=lambda exc: asyncio.run_coroutine_threadsafe(self.next_track(ctx, after=True), loop))
        logging.info(f"Playing track '{track.title}'")

        self.db.set_current_track(gid, track)
        self.db.update(gid, {'is_stopped': False})

        player = guild['current_player']
        if player is not None:
            await self.update_menu_embed(ctx, player)

        return track.title

    async def stop_playing(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent, vc: discord.VoiceClient | None = None) -> None:

        gid = ctx.guild_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.guild.id if ctx.guild else None
        if not gid:
            logging.warning("Guild ID not found in context")
            return

        if not vc:
            vc = await self.get_voice_client(ctx)
        if vc:
            logging.debug("Stopping playback")
            self.db.update(gid, {'current_track': None, 'is_stopped': True})
            vc.stop()


    async def next_track(
        self,
        ctx: ApplicationContext | Interaction | RawReactionActionEvent,
        vc: discord.VoiceClient | None = None,
        *,
        after: bool = False
    ) -> str | None:
        """Switch to the next track in the queue. Return track title on success.
        Doesn't change track if stopped. Stop playing if tracks list is empty.

        Args:
            ctx (ApplicationContext | Interaction): Context
            vc (discord.VoiceClient, optional): Voice client.
            after (bool, optional): Whether the function is being called by the after callback. Defaults to False.

        Returns:
            str | None: Track title or None.
        """
        gid = ctx.guild_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.guild.id if ctx.guild else None
        uid = ctx.user_id if isinstance(ctx, discord.RawReactionActionEvent) else ctx.user.id if ctx.user else None
        if not gid or not uid:
            logging.warning("Guild ID or User ID not found in context inside 'next_track'")
            return None

        guild = self.db.get_guild(gid)
        token = self.users_db.get_ym_token(uid)
        if not token:
            logging.debug(f"No token found for user {uid}")
            return None

        if guild['is_stopped']:
            logging.debug("Playback is stopped, skipping...")
            return None

        if not vc:
            vc = await self.get_voice_client(ctx)
            if not vc:  # Silently return if bot got kicked
                return None

        if guild['repeat'] and after:
            logging.debug("Repeating current track")
            next_track = guild['current_track']
        elif guild['shuffle']:
            logging.debug("Shuffling tracks")
            next_track = self.db.get_random_track(gid)
        else:
            logging.debug("Getting next track")
            next_track = self.db.get_track(gid, 'next')

        if guild['current_track'] and guild['current_player'] and not guild['repeat']:
            logging.debug("Adding current track to history")
            self.db.modify_track(gid, guild['current_track'], 'previous', 'insert')

        if next_track:
            ym_track = Track.de_json(
                next_track,
                client=ClientAsync(token)  # type: ignore  # Async client can be used here.
            )
            await self.stop_playing(ctx, vc)
            title = await self.play_track(
                ctx,
                ym_track,  # type: ignore  # de_json should always work here.
                vc
            )

            if after and not guild['current_player'] and not isinstance(ctx, discord.RawReactionActionEvent):
                await ctx.respond(f"Сейчас играет: **{title}**!", delete_after=15)

            return title

        logging.info("No next track found")
        self.db.update(gid, {'is_stopped': True, 'current_track': None})
        return None

    async def prev_track(self, ctx: ApplicationContext | Interaction) -> str | None:
        """Switch to the previous track in the queue. Repeat curren the song if no previous tracks.
        Return track title on success.

        Args:
            ctx (ApplicationContext | Interaction): Context.

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
            logging.debug(f"No token found for user {ctx.user.id}")
            return None

        if prev_track:
            logging.debug("Previous track found")
            track: dict[str, Any] | None = prev_track
        elif current_track:
            logging.debug("No previous track found. Repeating current track")
            track = self.db.get_track(gid, 'current')
        else:
            logging.debug("No previous or current track found")
            track = None

        if track:
            ym_track = Track.de_json(
                track,
                client=ClientAsync(token)  # type: ignore  # Async client can be used here.
            )
            await self.stop_playing(ctx)
            return await self.play_track(
                ctx,
                ym_track  # type: ignore  # de_json should always work here.
            )

        return None

    async def get_likes(self, ctx: ApplicationContext | Interaction | RawReactionActionEvent) -> list[TrackShort] | None:
        """Get liked tracks. Return list of tracks on success.
           Return None if no token found.
        
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
        if not current_track or not token:
            logging.debug("Current track or token not found")
            return None

        client = await ClientAsync(token).init()
        likes = await client.users_likes_tracks()
        if not likes:
            logging.debug("No likes found")
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
            logging.warning("Guild or User not found in context inside 'like_track'")
            return None

        current_track = self.db.get_track(ctx.guild.id, 'current')
        token = self.users_db.get_ym_token(ctx.user.id)
        if not current_track or not token:
            logging.debug("Current track or token not found")
            return None

        client = await ClientAsync(token).init()
        likes = await self.get_likes(ctx)
        if not likes:
            return None

        ym_track = cast(Track, Track.de_json(
            current_track,
            client=client  # type: ignore  # Async client can be used here.
            )
        )
        if str(ym_track.id) not in [str(track.id) for track in likes]:
            logging.debug("Track not found in likes. Adding...")
            await ym_track.like_async()
            return ym_track.title
        else:
            logging.debug("Track found in likes. Removing...")
            if not client.me or not client.me.account or not client.me.account.uid:
                logging.debug("Client account not found")
                return None
            await client.users_likes_tracks_remove(ym_track.id, client.me.account.uid)
            return 'TRACK REMOVED'