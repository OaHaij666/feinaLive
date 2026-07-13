"""Independent music request, catalog, and playback domain."""

from apps.music.manager import MusicManager, get_music_manager

__all__ = ["MusicManager", "get_music_manager"]
