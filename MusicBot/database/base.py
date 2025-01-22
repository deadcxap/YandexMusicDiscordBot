"""This documents initialises databse and contains methods to access it."""

from typing import cast

from pymongo import MongoClient
from pymongo.collection import Collection

from .user import User, ExplicitUser
from .guild import Guild, ExplicitGuild, MessageVotes

client: MongoClient = MongoClient("mongodb://localhost:27017/")
users: Collection[ExplicitUser] = client.YandexMusicBot.users
guilds: Collection[ExplicitGuild] = client.YandexMusicBot.guilds

class BaseUsersDatabase:

    def create_record(self, uid: int) -> None:
        """Create user database record.

        Args:
            uid (int): User id.
        """
        uid = uid
        users.insert_one(ExplicitUser(
            _id=uid,
            ym_token=None,
            playlists=[],
            playlists_page=0,
            queue_page=0
        ))

    def update(self, uid: int, data: User) -> None:
        """Update user record.

        Args:
            uid (int): User id.
            data (dict[Any, Any]): Updated data.
        """
        self.get_user(uid)
        users.update_one({'_id': uid}, {"$set": data})

    def get_user(self, uid: int) -> ExplicitUser:
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
        user =  cast(ExplicitUser, user)
        existing_fields = user.keys()
        fields: User = User(
            ym_token=None,
            playlists=[],
            playlists_page=0,
            queue_page=0
        )
        for field, default_value in fields.items():
            if field not in existing_fields and field != '_id':
                user[field] = default_value
                users.update_one({'_id': uid}, {"$set": {field: default_value}})
        
        return user

    def get_ym_token(self, uid: int) -> str | None:
        user = users.find_one({'_id': uid})
        if not user:
            self.create_record(uid)
            user = users.find_one({'_id': uid})
        return cast(ExplicitUser, user)['ym_token']

class BaseGuildsDatabase:
    
    def create_record(self, gid: int) -> None:
        """Create guild database record.

        Args:
            gid (int): Guild id.
        """
        guilds.insert_one(ExplicitGuild(
            _id=gid,
            next_tracks=[],
            previous_tracks=[],
            current_track=None,
            current_player=None,
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
            votes={}
        ))

    def update(self, gid: int, data: Guild) -> None:
        """Update guild record.

        Args:
            gid (int): Guild id.
            data (dict[Any, Any]): Updated data.
        """
        self.get_guild(gid)
        guilds.update_one({'_id': gid}, {"$set": data})

    def get_guild(self, gid: int) -> ExplicitGuild:
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
        
        guild = cast(ExplicitGuild, guild)
        existing_fields = guild.keys()
        fields = Guild(
            next_tracks=[],
            previous_tracks=[],
            current_track=None,
            current_player=None,
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
            votes={}
        )
        for field, default_value in fields.items():
            if field not in existing_fields and field != '_id':
                guild[field] = default_value
                guilds.update_one({'_id': gid}, {"$set": {field: default_value}})
        
        return guild
        
    def update_vote(self, gid: int, mid: int, data: MessageVotes) -> None:
        """Update vote for a message in a guild.
        
        Args:
            gid (int): Guild id.
            mid (int): Message id.
            vote (bool): Vote value.
        """
        guild = self.get_guild(gid)
        guild['votes'][str(mid)] = data
        guilds.update_one({'_id': gid}, {"$set": {'votes': guild['votes']}})