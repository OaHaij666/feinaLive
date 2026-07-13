from __future__ import annotations

import re
from uuid import uuid4

from apps.config import config
from apps.music.manager import get_music_manager
from apps.music.models import MusicRequest, MusicRequestResult
from apps.music.providers.bilibili import BilibiliMusicProvider

REQUEST_PATTERN = re.compile(r"^(?:点歌|来一首)\s*(.*)$", re.IGNORECASE)
PLAY_PATTERN = re.compile(r"^播放\s+(.+)$", re.IGNORECASE)


def parse_music_request(text: str, user: str, *, request_id: str = "") -> MusicRequest | None:
    stripped = text.strip()
    match = REQUEST_PATTERN.match(stripped) or PLAY_PATTERN.match(stripped)
    explicit = bool(match)
    payload = match.group(1).strip() if match else stripped
    source_id = BilibiliMusicProvider.extract_source_id(payload)
    if not explicit and not (config.music_allow_bare_bv and source_id):
        return None
    if not payload:
        return None
    query = payload.replace(source_id, "").strip() if source_id else payload
    return MusicRequest(
        query=query or source_id or "",
        requested_by=user,
        request_id=request_id or str(uuid4()),
        provider=config.music_default_provider,
        direct_source_id=source_id,
    )


async def process_music_danmaku(
    text: str, user: str, *, request_id: str = ""
) -> MusicRequestResult | None:
    request = parse_music_request(text, user, request_id=request_id)
    if request is None:
        return None
    if not request.query and not request.direct_source_id:
        return MusicRequestResult(
            accepted=False,
            error_code="MISSING_QUERY",
            error="请在点歌指令后提供歌名或 BV 号",
        )
    return await get_music_manager().submit(request)
