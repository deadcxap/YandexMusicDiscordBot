from typing import Any
from yandex_music import Track

from MusicBot.database.base import BaseGuildsDatabase

class VoiceGuildsDatabase(BaseGuildsDatabase):
    
    def get_previous_tracks_list(self, gid: int) -> list[dict[str, Any]]:
        guild = self.get_guild(gid)
        return guild.get('previous_tracks_list')
    
    def get_tracks_list(self, gid: int) -> list[dict[str, Any]]:
        guild = self.get_guild(gid)
        return guild.get('tracks_list')

    def pop_track(self, gid: int) -> dict[str, Any]:
        tracks_list = self.get_tracks_list(gid)
        track = tracks_list.pop(0)
        self.update(gid, {'tracks_list': tracks_list})
        return track

    def insert_track(self, gid: int, track: Track | dict[str, Any]) -> None:
        if isinstance(track, Track):
            track = track.to_dict(for_request=True)
        tracks_list = self.get_tracks_list(gid)
        tracks_list.insert(0, track)
        self.update(gid, {'tracks_list': tracks_list})
    
    def add_track(self, gid: int, track: Track) -> None:
        tracks_list = self.get_tracks_list(gid)
        tracks_list.append(track.to_dict(for_request=True))
        self.update(gid, {'tracks_list': tracks_list})

    def set_current_track(self, gid: int, track: Track) -> None:
        self.update(gid, {'current_track': track.to_dict(for_request=True)})
    
    def add_previous_track(self, gid: int, track: Track | dict[str, Any]) -> None:
        tracks_list = self.get_previous_tracks_list(gid)
        if isinstance(track, Track):
            track = track.to_dict(for_request=True)
        tracks_list.insert(0, track)
        if len(tracks_list) > 50:
            tracks_list.pop()
        self.update(gid, {'previous_tracks_list': tracks_list})
    
    def pop_previous_track(self, gid: int) -> dict[str, Any]:
        tracks_list = self.get_previous_tracks_list(gid)
        track = tracks_list.pop(0)
        self.update(gid, {'previous_tracks_list': tracks_list})
        return track