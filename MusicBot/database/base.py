"""This documents initialises databse and contains methods to access it."""

from typing import Any, cast

from pymongo import MongoClient
from pymongo.collection import Collection

from MusicBot.database.user import User, ExplicitUser
from MusicBot.database.guild import Guild, ExplicitGuild

client: MongoClient = MongoClient("mongodb://localhost:27017/")
users: Collection[User] = client.YandexMusicBot.users
guilds: Collection[Guild] = client.YandexMusicBot.guilds

class BaseUsersDatabase:

    def create_record(self, uid: int) -> None:
        """Create user database record.

        Args:
            uid (int): User id.
        """
        uid = uid
        users.insert_one(ExplicitUser(
            _id=uid,
            ym_token=None
        ))

    def update(self, uid: int, data: User) -> None:
        """Update user record.

        Args:
            uid (int): User id.
            data (dict[Any, Any]): Updated data.
        """
        self.get_user(uid)
        users.update_one({'_id': uid}, {"$set": data})

    def get_user(self, uid: int) -> User:
        """Get user record from database. Create new entry if not present.

        Args:
            uid (int): User id.

        Returns:
            User: User record.
        """
        user = users.find_one({'_id': uid})
        if not user:
            self.create_record(uid)
            user = users.find_one({'_id': uid})
        return cast(User, user)

    def get_ym_token(self, uid: int) -> str | None:
        user = users.find_one({'_id': uid})
        if not user:
            self.create_record(uid)
            user = cast(User, users.find_one({'_id': uid}))
        return user['ym_token']

class BaseGuildsDatabase:
    
    def create_record(self, gid: int) -> None:
        """Create guild database record.

        Args:
            gid (int): Guild id.
        """
        guilds.insert_one(ExplicitGuild(
            _id=gid,
            tracks_list=[],
            previous_tracks_list=[],
            current_track=None,
            is_stopped=True,
            allow_explicit=True,
            allow_menu=True
        ))

    def update(self, gid: int, data: dict[Any, Any]) -> None:
        """Update guild record.

        Args:
            gid (int): Guild id.
            data (dict[Any, Any]): Updated data.
        """
        self.get_guild(gid)
        guilds.update_one({'_id': gid}, {"$set": data})

    def get_guild(self, gid: int) -> Guild:
        """Get guild record from database. Create new entry if not present.

        Args:
            uid (int): User id.

        Returns:
            Guild: Guild record.
        """
        guild = guilds.find_one({'_id': gid})
        if not guild:
            self.create_record(gid)
            guild = guilds.find_one({'_id': gid})
        return cast(Guild, guild)
