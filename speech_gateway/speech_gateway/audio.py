"""Best-effort duration inspection for performance metrics."""

from __future__ import annotations

from io import BytesIO

from mutagen import File as MutagenFile


def duration_ms(audio: bytes) -> int | None:
    try:
        parsed = MutagenFile(BytesIO(audio))
        if parsed is None or parsed.info is None:
            return None
        length = float(parsed.info.length)
        return round(length * 1000) if length > 0 else None
    except Exception:
        return None
