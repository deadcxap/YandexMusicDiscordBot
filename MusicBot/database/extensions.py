from typing import Any
from yandex_music import Track

from MusicBot.database.base import BaseGuildsDatabase

class VoiceGuildsDatabase(BaseGuildsDatabase):
    
    def clear_queue(self, gid: int) -> None:
        self.update(gid, {'next_tracks_list': []})
    
    def clear_history(self, gid: int) -> None:
        self.update(gid, {'previous_tracks_list': []})
    
    def get_current_track(self, gid: int) -> dict[str, Any] | None:
        guild = self.get_guild(gid)
        return guild.get('current_track')
        
    def get_previous_tracks_list(self, gid: int) -> list[dict[str, Any]]:
        guild = self.get_guild(gid)
        return guild.get('previous_tracks_list')
    
    def get_next_tracks_list(self, gid: int) -> list[dict[str, Any]]:
        guild = self.get_guild(gid)
        return guild.get('next_tracks_list')

    def get_next_track(self, gid: int) -> dict[str, Any]:
        tracks_list = self.get_next_tracks_list(gid)
        track = tracks_list.pop(0)
        self.update(gid, {'next_tracks_list': tracks_list})
        return track

    def insert_track(self, gid: int, track: Track | dict[str, Any]) -> None:
        if isinstance(track, Track):
            track = track.to_dict()
        tracks_list = self.get_next_tracks_list(gid)
        tracks_list.insert(0, track)
        self.update(gid, {'next_tracks_list': tracks_list})
    
    def append_track(self, gid: int, track: Track) -> None:
        tracks_list = self.get_next_tracks_list(gid)
        tracks_list.append(track.to_dict())
        self.update(gid, {'next_tracks_list': tracks_list})

    def set_current_track(self, gid: int, track: Track) -> None:
        self.update(gid, {'current_track': track.to_dict()})
    
    def add_previous_track(self, gid: int, track: Track | dict[str, Any]) -> None:
        tracks_list = self.get_previous_tracks_list(gid)
        if isinstance(track, Track):
            track = track.to_dict()
        tracks_list.insert(0, track)
        if len(tracks_list) > 50:
            tracks_list.pop()
        self.update(gid, {'previous_tracks_list': tracks_list})
    
    def get_previous_track(self, gid: int) -> dict[str, Any] | None:
        tracks_list = self.get_previous_tracks_list(gid)
        if len(tracks_list) == 0:
            return
        track = tracks_list.pop(0)
        self.update(gid, {'previous_tracks_list': tracks_list})
        return track