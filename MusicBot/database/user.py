from typing import TypedDict, Literal

class User(TypedDict, total=False):
    ym_token: str | None
    playlists:  list[tuple[str, int]]
    playlists_page: int
    queue_page: int
    vibe_batch_id: str | None
    vibe_type: Literal['track', 'album', 'artist', 'playlist', 'user'] | None
    vibe_id: str | int | None

class ExplicitUser(TypedDict):
    _id: int
    ym_token: str | None
    playlists: list[tuple[str, int]]  # name / tracks count
    playlists_page: int
    queue_page: int
    vibe_batch_id: str | None
    vibe_type: Literal['track', 'album', 'artist', 'playlist', 'user'] | None
    vibe_id: str | int | None
