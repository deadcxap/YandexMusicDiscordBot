from typing import TypedDict, Literal, Any

class MessageVotes(TypedDict):
    positive_votes: list[int]
    negative_votes: list[int]
    total_members: int
    action: Literal['next', 'add_track', 'add_album', 'add_artist', 'add_playlist']
    vote_content: dict[str, Any] | list[dict[str, Any]] | None

class Guild(TypedDict, total=False):
    next_tracks: list[dict[str, Any]]
    previous_tracks: list[dict[str, Any]]
    current_track: dict[str, Any] | None
    current_player: int | None
    is_stopped: bool
    allow_explicit: bool
    always_allow_menu: bool
    vote_next_track: bool
    vote_add_track: bool
    vote_add_album: bool
    vote_add_artist: bool
    vote_add_playlist: bool
    shuffle: bool
    repeat: bool
    votes: dict[str, MessageVotes]

class ExplicitGuild(TypedDict):
    _id: int
    next_tracks: list[dict[str, Any]]
    previous_tracks: list[dict[str, Any]]
    current_track: dict[str, Any] | None
    current_player: int | None
    is_stopped: bool  # Prevents the `after` callback of play_track
    allow_explicit: bool
    always_allow_menu: bool
    vote_next_track: bool
    vote_add_track: bool
    vote_add_album: bool
    vote_add_artist: bool
    vote_add_playlist: bool
    shuffle: bool
    repeat: bool
    votes: dict[str, MessageVotes]