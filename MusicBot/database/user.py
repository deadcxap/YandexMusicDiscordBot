from typing import TypedDict

class User(TypedDict):
    ym_token: str | None

class ExplicitUser(TypedDict):
    _id: int
    ym_token: str | None
