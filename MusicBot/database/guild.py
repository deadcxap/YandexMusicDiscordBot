from typing import TypedDict, Any

class Guild(TypedDict, total=False):
    next_tracks: list[dict[str, Any]]
    previous_tracks: list[dict[str, Any]]
    current_track: dict[str, Any] | None
    current_player: int | None
    is_stopped: bool
    allow_explicit: bool
    allow_menu: bool

class ExplicitGuild(TypedDict):
    _id: int
    next_tracks: list[dict[str, Any]]
    previous_tracks: list[dict[str, Any]]
    current_track: dict[str, Any] | None
    current_player: int | None
    is_stopped: bool  # Prevents the `after` callback of play_track
    allow_explicit: bool
    allow_menu: bool  # Is /toggle menu command available