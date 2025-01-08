"""This documents initialises databse and contains methods to access it."""

from typing import Any, cast

from pymongo import MongoClient
from pymongo.collection import Collection

from yandex_music import Track

from MusicBot.database.user import User, ExplicitUser, TrackInfo

client: MongoClient = MongoClient("mongodb://localhost:27017/")
users: Collection[User] = client.YandexMusicBot.users
        
def create_record(uid: int | str) -> None:
    """Create user database record.

    Args:
        uid (int | str): User id.
    """
    uid = str(uid)
    users.insert_one(ExplicitUser(
        _id=uid,
        ym_token=None,
        tracks_list=[],
        current_track=None,
        is_stopped=True
    ))

def update(uid: int | str, data: dict[Any, Any]) -> None:
    """Update user record.

    Args:
        uid (int | str): User id.
        data (dict[Any, Any]): Updated data.
    """
    get_user(uid)
    users.update_one({'_id': str(uid)}, {"$set": data})

def get_user(uid: int | str) -> User:
    """Get user record from database. Create new entry if not present.

    Args:
        uid (int | str): User id.

    Returns:
        User: User record.
    """
    user = users.find_one({'_id': str(uid)})
    if not user:
        create_record(uid)
        user = users.find_one({'_id': str(uid)})
    return cast(User, user)

def get_ym_token(uid: int | str) -> str | None:
    user = users.find_one({'_id': str(uid)})
    if not user:
        create_record(uid)
        user = cast(User, users.find_one({'_id': str(uid)}))
    return user['ym_token']

def get_tracks_list(uid: int | str) -> list[TrackInfo]:
    user = get_user(uid)
    return user.get('tracks_list')

def pop_track(uid: int | str) -> TrackInfo:
    tracks_list = get_tracks_list(uid)
    track = tracks_list.pop(0)
    update(uid, {'tracks_list': tracks_list})
    return track

def add_track(uid: int | str, track: Track | TrackInfo) -> None:
    tracks_list = get_tracks_list(uid)
    if isinstance(track, Track):
        track = TrackInfo(
            track_id=str(track.id),
            title=track.title,  # type: ignore
            avail=track.available,  # type: ignore
            artists=", ".join(track.artists_name()),
            albums=", ".join([album.title for album in track.albums]),  # type: ignore
            duration=track.duration_ms,  # type: ignore
            explicit=track.explicit or bool(track.content_warning),
            bg_video=track.background_video_uri
        )
    tracks_list.append(track)
    update(uid, {'tracks_list': tracks_list})

def set_current_track(uid: int | str) -> None:
    update(uid, {'current_track': str(uid)})