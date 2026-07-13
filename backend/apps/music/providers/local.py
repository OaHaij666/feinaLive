from __future__ import annotations

import asyncio
import base64
import binascii
import mimetypes
import time
from pathlib import Path

from mutagen import File as MutagenFile

from apps.music.models import AudioStream, ProviderSearchResult, Track
from apps.music.providers.base import ProviderTrustPolicy

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"}


class LocalMusicProvider:
    id = "local"
    trust_policy = ProviderTrustPolicy.NATIVE_MUSIC

    def __init__(self, directories: list[str], *, cache_seconds: float = 60.0) -> None:
        self._roots = [Path(value).expanduser().resolve() for value in directories if value.strip()]
        self._cache_seconds = cache_seconds
        self._cache: list[ProviderSearchResult] = []
        self._cache_at = 0.0
        self._lock = asyncio.Lock()

    async def search(self, query: str, limit: int = 10) -> list[ProviderSearchResult]:
        catalog = await self._catalog()
        normalized = query.casefold().strip()
        if not normalized:
            return catalog[:limit]
        terms = [term for term in normalized.split() if term]
        ranked: list[tuple[int, ProviderSearchResult]] = []
        for item in catalog:
            text = f"{item.title} {item.artist}".casefold()
            score = sum(2 if term in item.title.casefold() else 1 for term in terms if term in text)
            if score:
                ranked.append((score, item))
        ranked.sort(key=lambda value: (-value[0], value[1].title.casefold()))
        return [item for _, item in ranked[:limit]]

    async def inspect(self, source_id: str) -> Track:
        path = self._resolve_source(source_id)
        return await asyncio.to_thread(self._track_from_path, path, source_id)

    async def resolve_stream(self, source_id: str) -> AudioStream:
        path = self._resolve_source(source_id)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return AudioStream(local_path=str(path), media_type=media_type)

    async def _catalog(self) -> list[ProviderSearchResult]:
        async with self._lock:
            if self._cache_at and time.monotonic() - self._cache_at < self._cache_seconds:
                return list(self._cache)
            self._cache = await asyncio.to_thread(self._scan)
            self._cache_at = time.monotonic()
            return list(self._cache)

    def _scan(self) -> list[ProviderSearchResult]:
        results: list[ProviderSearchResult] = []
        for root_index, root in enumerate(self._roots):
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.casefold() not in SUPPORTED_EXTENSIONS:
                    continue
                source_id = self._encode_source(root_index, path.relative_to(root))
                try:
                    track = self._track_from_path(path, source_id)
                except Exception:
                    continue
                results.append(
                    ProviderSearchResult(
                        source_id=source_id,
                        title=track.title,
                        artist=" / ".join(track.artists),
                        duration_seconds=track.duration_seconds,
                        cover_url=track.cover_url,
                    )
                )
        results.sort(key=lambda item: (item.artist.casefold(), item.title.casefold()))
        return results

    def _track_from_path(self, path: Path, source_id: str) -> Track:
        audio = MutagenFile(path, easy=True)
        if audio is None or not getattr(audio, "info", None):
            raise ValueError(f"Unsupported or unreadable audio file: {path.name}")
        tags = audio.tags or {}
        title = _first_tag(tags, "title") or path.stem
        artists = _tag_values(tags, "artist") or ["未知艺术家"]
        album = _first_tag(tags, "album")
        return Track(
            provider=self.id,
            source_id=source_id,
            title=title,
            artists=artists,
            duration_seconds=max(1, round(float(audio.info.length))),
            metadata={
                "album": album,
                "filename": path.name,
                "extension": path.suffix.casefold(),
            },
        )

    def _resolve_source(self, source_id: str) -> Path:
        try:
            root_value, encoded = source_id.split(":", 1)
            root_index = int(root_value)
            if root_index < 0:
                raise ValueError("Root index must be non-negative")
            relative = Path(
                base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
            )
            root = self._roots[root_index]
        except (ValueError, IndexError, UnicodeDecodeError, binascii.Error) as exc:
            raise ValueError("Invalid local music source id") from exc
        path = (root / relative).resolve()
        if path == root or root not in path.parents:
            raise ValueError("Local music path escaped its configured root")
        if not path.is_file() or path.suffix.casefold() not in SUPPORTED_EXTENSIONS:
            raise FileNotFoundError("Local music file is unavailable")
        return path

    @staticmethod
    def _encode_source(root_index: int, relative: Path) -> str:
        encoded = base64.urlsafe_b64encode(relative.as_posix().encode("utf-8")).decode("ascii")
        return f"{root_index}:{encoded.rstrip('=')}"


def _tag_values(tags, key: str) -> list[str]:
    value = tags.get(key) or []
    if isinstance(value, str):
        value = [value]
    return [str(item).strip() for item in value if str(item).strip()]


def _first_tag(tags, key: str) -> str:
    values = _tag_values(tags, key)
    return values[0] if values else ""
