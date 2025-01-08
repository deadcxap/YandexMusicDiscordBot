from typing import TypedDict

class Guild(TypedDict):
    allow_explicit: bool
    allow_menu: bool

class ExplicitGuild(TypedDict):
    _id: str
    allow_explicit: bool
    allow_menu: bool