from random import randint
from typing import Any, Literal
from yandex_music import Track

from MusicBot.database import BaseGuildsDatabase

class VoiceGuildsDatabase(BaseGuildsDatabase):
    
    def get_tracks_list(self, gid: int, type: Literal['next', 'previous']) -> list[dict[str, Any]]:
        """Get tracks list with given type.

        Args:
            gid (int): Guild id.
            type (Literal['current', 'next', 'previous']): Track type.

        Returns:
            dict[str, Any] | None: Dictionary covertable to yandex_musci.Track or None
        """
        guild = self.get_guild(gid)
        if type == 'next':
            tracks = guild['next_tracks']
        elif type == 'previous':
            tracks = guild['previous_tracks']
        
        return tracks
    
    def get_track(self, gid: int, type: Literal['current', 'next', 'previous']) -> dict[str, Any] | None:
        """Get track with given type. Pop the track from list if `type` is 'next' or 'previous'.

        Args:
            gid (int): Guild id.
            type (Literal['current', 'next', 'previous']): Track type.

        Returns:
            dict[str, Any] | None: Dictionary covertable to yandex_musci.Track or None
        """
        guild = self.get_guild(gid)
        if type == 'current':
            track = guild['current_track']
        elif type == 'next':
            tracks = guild['next_tracks']
            if not tracks:
                return None
            track = tracks.pop(0)
            self.update(gid, {'next_tracks': tracks})
        elif type == 'previous':
            tracks = guild['previous_tracks']
            if not tracks:
                return None
            track = tracks.pop(0)
            current_track = guild['current_track']
            if current_track:
                self.modify_track(gid, current_track, 'next', 'insert')
            self.update(gid, {'previous_tracks': tracks})
        
        return track

    def modify_track(
        self, gid: int,
        track: Track | dict[str, Any] | list[dict[str, Any]] | list[Track],
        type: Literal['next', 'previous'],
        operation: Literal['insert', 'append', 'extend', 'pop_start', 'pop_end', 'pop_random']
    ) -> dict[str, Any] | None:
        """Perform operation of given type on tracks list of given type.

        Args:
            gid (int): Guild id.
            track (Track | dict[str, Any]): yandex_music.Track or a dictionary convertable to it.
            type (Literal['current', 'next', 'previous']): List type.
            operation (Literal['insert', 'append', 'pop_start', 'pop_end']): Operation type.

        Returns:
            dict[str, Any] | None: Dictionary convertable to yandex_music.Track or None.
        """
        guild = self.get_guild(gid)
        
        if type not in ('next', 'previous'):
            raise ValueError(f"Type must be either 'next' or 'previous', not '{type}'")
        explicit_type: Literal['next_tracks', 'previous_tracks'] = type + '_tracks'  # type: ignore[assignment]
        tracks = guild[explicit_type]
        pop_track = None
        
        if isinstance(track, list):
            tracks_list = []
            for _track in track:
                if isinstance(_track, Track):
                    tracks_list.append(_track.to_dict())
                else:
                    tracks_list.append(_track)
            
            if operation != 'extend':
                raise ValueError('Can only use extend operation on lists.')
            else:
                tracks.extend(tracks_list)
            self.update(gid, {explicit_type: tracks})  # type: ignore
        else:
            if isinstance(track, Track):
                track = track.to_dict()
            if operation == 'insert':
                if type == 'previous' and len(tracks) > 50:
                    tracks.pop()
                tracks.insert(0, track)
            elif operation == 'append':
                tracks.append(track)
            elif operation == 'pop_start':
                pop_track = tracks.pop(0)
            elif operation == 'pop_end':
                pop_track = tracks.pop(-1)
            elif operation == 'pop_random':
                pop_track = tracks.pop(randint(0, len(tracks)))
            elif operation == 'extend':
                raise ValueError('Can only use extend operation on lists.')
            else:
                raise ValueError(f"Unknown operation '{operation}'")

            self.update(gid, {explicit_type: tracks})  # type: ignore
        
        return pop_track

    def get_random_track(self, gid: int) -> dict[str, Any] | None:
        """Pop random track from the queue.

        Args:
            gid (int): Guild id.

        Returns:
            dict[str, Any] | None: Dictionary covertable to yandex_musci.Track or None
        """
        tracks = self.get_tracks_list(gid, 'next')
        if not tracks:
            return None
        track = tracks.pop(randint(0, len(tracks)))
        self.update(gid, {'next_tracks': tracks})
        return track
    
    def get_current_menu(self, gid: int) -> int | None:
        """Get current menu.
        
        Args:
            gid (int): Guild id.
        
        Returns: int | None: Menu message id or None if not present.
        """
        guild = self.get_guild(gid)
        return guild['current_menu']