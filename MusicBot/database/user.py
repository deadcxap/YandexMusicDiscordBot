from typing import TypedDict

class User(TypedDict, total=False):
    ym_token: str | None
    playlists:  list[tuple[str, int]]
    playlists_page: int
    queue_page: int

class ExplicitUser(TypedDict):
    _id: int
    ym_token: str | None
    playlists: list[tuple[str, int]]  # name / tracks count
    playlists_page: int
    queue_page: int
