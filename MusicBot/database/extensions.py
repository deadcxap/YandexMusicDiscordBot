from random import randint
from typing import Any, Literal
from yandex_music import Track
from pymongo import UpdateOne, ReturnDocument
from pymongo.errors import DuplicateKeyError

from MusicBot.database import BaseGuildsDatabase, guilds

class VoiceGuildsDatabase(BaseGuildsDatabase):
    
    async def get_tracks_list(self, gid: int, list_type: Literal['next', 'previous']) -> list[dict[str, Any]]:
        if list_type not in ('next', 'previous'):
            raise ValueError("list_type must be either 'next' or 'previous'")
        projection = {f"{list_type}_tracks": 1}
        guild = await self.get_guild(gid, projection=projection)
        return guild.get(f"{list_type}_tracks", [])

    async def get_track(self, gid: int, list_type: Literal['next', 'previous', 'current']) -> dict[str, Any] | None:
        if list_type not in ('next', 'previous', 'current'):
            raise ValueError("list_type must be either 'next' or 'previous'")
        
        field = f'{list_type}_tracks'
        guild = await self.get_guild(gid, projection={'current_track': 1, field: 1})

        if list_type == 'current':
            return guild['current_track']
        
        result = await guilds.find_one_and_update(
            {'_id': gid},
            {'$pop': {field: -1}},
            projection={field: 1},
            return_document=ReturnDocument.BEFORE
        )

        res = result.get(field, []) if result else None

        if field == 'previous_tracks' and res:
            await guilds.find_one_and_update(
                {'_id': gid},
                {'$push': {'next_tracks': {'$each': [guild['current_track']], '$position': 0}}},
                projection={'next_tracks': 1}
            )

        return res[0] if res else None

    async def modify_track(
        self,
        gid: int,
        track: Track | dict[str, Any] | list[dict[str, Any]] | list[Track],
        list_type: Literal['next', 'previous'],
        operation: Literal['insert', 'append', 'extend', 'pop_start', 'pop_end']
    ) -> dict[str, Any] | None:
        field = f"{list_type}_tracks"
        track_data = self._normalize_track_data(track)
        
        operations = {
            'insert': {'$push': {field: {'$each': track_data, '$position': 0}}},
            'append': {'$push': {field: {'$each': track_data}}},
            'extend': {'$push': {field: {'$each': track_data}}},  # Same as append for consistency with python
            'pop_start': {'$pop': {field: -1}},
            'pop_end': {'$pop': {field: 1}}
        }

        update = operations[operation]
        try:
            await guilds.update_one(
                {'_id': gid},
                update,
                array_filters=None
            )
            return await self._get_popped_track(gid, field, operation)
        except DuplicateKeyError:
            await self._handle_duplicate_error(gid, field)
            return await self.modify_track(gid, track, list_type, operation)

    def _normalize_track_data(self, track: Track | dict | list) -> list[dict]:
        if not isinstance(track, list):
            track = [track]
            
        return [
            t.to_dict() if isinstance(t, Track) else t
            for t in track
        ]

    async def pop_random_track(self, gid: int, field: Literal['next', 'previous']) -> dict[str, Any] | None:
        tracks = await self.get_tracks_list(gid, field)
        track = tracks.pop(randint(0, len(tracks) - 1)) if tracks else None
        await self.update(gid, {f"{field}_tracks": tracks})
        return track

    async def get_current_menu(self, gid: int) -> int | None:
        guild = await self.get_guild(gid, projection={'current_menu': 1})
        return guild['current_menu']

    async def _get_popped_track(self, gid: int, field: str, operation: str) -> dict[str, Any] | None:
        if operation not in ('pop_start', 'pop_end', 'pop_random'):
            return None

        guild = await self.get_guild(gid, projection={field: 1})
        tracks = guild.get(field, [])

        if not tracks:
            return None

        if operation == 'pop_start':
            return tracks[0]
        elif operation == 'pop_end':
            return tracks[-1]
        elif operation == 'pop_random':
            return tracks[randint(0, len(tracks) - 1)]

        return None

    async def _handle_duplicate_error(self, gid: int, field: str) -> None:
        """Handle duplicate key errors by cleaning up the array."""
        guild = await self.get_guild(gid, projection={field: 1})
        tracks = guild.get(field, [])
        
        if not tracks:
            return

        # Remove duplicates while preserving order
        unique_tracks = []
        seen = set()
        for track in tracks:
            track_id = track.get('id')
            if track_id not in seen:
                seen.add(track_id)
                unique_tracks.append(track)

        await guilds.update_one(
            {'_id': gid},
            {'$set': {field: unique_tracks}}
        )

    async def set_current_track(self, gid: int, track: Track | dict[str, Any]) -> None:
        """Set the current track and update the previous tracks list."""
        if isinstance(track, Track):
            track = track.to_dict()

        await guilds.update_one(
            {'_id': gid},
            {'$set': {'current_track': track}}
        )

    async def clear_tracks(self, gid: int, list_type: Literal['next', 'previous']) -> None:
        """Clear the specified tracks list."""
        field = f"{list_type}_tracks"
        await guilds.update_one(
            {'_id': gid},
            {'$set': {field: []}}
        )

    async def shuffle_tracks(self, gid: int, list_type: Literal['next', 'previous']) -> None:
        """Shuffle the specified tracks list."""
        field = f"{list_type}_tracks"
        guild = await self.get_guild(gid, projection={field: 1})
        tracks = guild.get(field, [])

        if not tracks:
            return

        shuffled_tracks = tracks.copy()
        for i in range(len(shuffled_tracks) - 1, 0, -1):
            j = randint(0, i)
            shuffled_tracks[i], shuffled_tracks[j] = shuffled_tracks[j], shuffled_tracks[i]

        await guilds.update_one(
            {'_id': gid},
            {'$set': {field: shuffled_tracks}}
        )

    async def move_track(
        self,
        gid: int,
        from_list: Literal['next', 'previous'],
        to_list: Literal['next', 'previous'],
        track_index: int
    ) -> bool:
        """Move a track from one list to another."""
        from_field = f"{from_list}_tracks"
        to_field = f"{to_list}_tracks"
        
        if from_field not in ('next_tracks', 'previous_tracks') or to_field not in ('next_tracks', 'previous_tracks'):
            raise ValueError(f"Invalid list type: '{from_field}'")

        guild = await guilds.find_one(
            {'_id': gid},
            projection={from_field: 1, to_field: 1},
        )

        if not guild or not guild.get(from_field) or track_index >= len(guild[from_field]):
            return False

        track = guild[from_field].pop(track_index)
        updates = [
            UpdateOne(
                {'_id': gid},
                {'$set': {from_field: guild[from_field]}},
            ),
            UpdateOne(
                {'_id': gid},
                {'$push': {to_field: {'$each': [track], '$position': 0}}},
            )
        ]

        await guilds.bulk_write(updates)
        return True

    async def get_track_count(self, gid: int, list_type: Literal['next', 'previous']) -> int:
        """Get the count of tracks in the specified list."""
        field = f"{list_type}_tracks"
        guild = await self.get_guild(gid, projection={field: 1})
        return len(guild.get(field, []))

    async def set_current_menu(self, gid: int, menu_id: int | None) -> None:
        """Set the current menu message ID."""
        await guilds.update_one(
            {'_id': gid},
            {'$set': {'current_menu': menu_id}}
        )