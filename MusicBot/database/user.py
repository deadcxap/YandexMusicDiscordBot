from typing import TypedDict

class TrackInfo(TypedDict):
    track_id: str
    title: str
    avail: bool
    artists: str
    albums: str
    duration: int
    explicit: bool
    bg_video: str | None

class User(TypedDict):
    ym_token: str | None
    tracks_list: list[TrackInfo]
    current_track: int | None
    is_stopped: bool

class ExplicitUser(TypedDict):
    _id: str
    ym_token: str | None
    tracks_list: list[TrackInfo]
    current_track: int | None
    is_stopped: bool  # Prevents callback of play_track
    
