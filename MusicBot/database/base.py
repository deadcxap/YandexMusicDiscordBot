from typing import Iterable, Any, cast
from pymongo import AsyncMongoClient, ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.results import UpdateResult

from .user import User, ExplicitUser
from .guild import Guild, ExplicitGuild, MessageVotes

client: AsyncMongoClient = AsyncMongoClient("mongodb://localhost:27017/")

db = client.YandexMusicBot
users: AsyncCollection[ExplicitUser] = db.users
guilds: AsyncCollection[ExplicitGuild] = db.guilds

class BaseUsersDatabase:
    DEFAULT_USER = User(
        ym_token=None,
        playlists=[],
        playlists_page=0,
        queue_page=0,
        vibe_batch_id=None,
        vibe_type=None,
        vibe_id=None,
        vibe_settings={
            'mood': 'all',
            'diversity': 'default',
            'lang': 'any'
        }
    )

    async def update(self, uid: int, data: User | dict[str, Any]) -> UpdateResult:
        return await users.update_one(
            {'_id': uid},
            {'$set': data},
            upsert=True
        )

    async def get_user(self, uid: int, projection: User | Iterable[str] | None = None) -> ExplicitUser:
        user = await users.find_one_and_update(
            {'_id': uid},
            {'$setOnInsert': self.DEFAULT_USER},
            return_document=ReturnDocument.AFTER,
            upsert=True,
            projection=projection
        )
        return cast(ExplicitUser, user)

    async def get_ym_token(self, uid: int) -> str | None:
        user = await users.find_one(
            {'_id': uid},
            projection={'ym_token': 1}
        )
        return cast(str | None, user.get('ym_token') if user else None)

    async def add_playlist(self, uid: int, playlist_data: dict) -> UpdateResult:
        return await users.update_one(
            {'_id': uid},
            {'$push': {'playlists': playlist_data}}
        )


class BaseGuildsDatabase:
    DEFAULT_GUILD = Guild(
        next_tracks=[],
        previous_tracks=[],
        current_track=None,
        current_menu=None,
        is_stopped=True,
        allow_explicit=True,
        always_allow_menu=False,
        vote_next_track=True,
        vote_add_track=True,
        vote_add_album=True,
        vote_add_artist=True,
        vote_add_playlist=True,
        shuffle=False,
        repeat=False,
        votes={},
        vibing=False,
        current_viber_id=None
    )

    async def update(self, gid: int, data: Guild | dict[str, Any]) -> UpdateResult:
        return await guilds.update_one(
            {'_id': gid},
            {'$set': data},
            upsert=True
        )

    async def get_guild(self, gid: int, projection: Guild | Iterable[str] | None = None) -> ExplicitGuild:
        guild = await guilds.find_one_and_update(
            {'_id': gid},
            {'$setOnInsert': self.DEFAULT_GUILD},
            return_document=ReturnDocument.AFTER,
            upsert=True,
            projection=projection
        )
        return cast(ExplicitGuild, guild)

    async def update_vote(self, gid: int, mid: int, data: MessageVotes) -> UpdateResult:
        return await guilds.update_one(
            {'_id': gid},
            {'$set': {f'votes.{mid}': data}}
        )

    async def clear_queue(self, gid: int) -> UpdateResult:
        return await guilds.update_one(
            {'_id': gid},
            {'$set': {'next_tracks': []}}
        )
