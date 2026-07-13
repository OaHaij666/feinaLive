from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from py_mini_racer import MiniRacer

_SIGN_SCRIPT = Path(__file__).with_name("sign.js")
_PARAMS = (
    "live_id",
    "aid",
    "version_code",
    "webcast_sdk_version",
    "room_id",
    "sub_room_id",
    "sub_channel_id",
    "did_rule",
    "user_unique_id",
    "device_platform",
    "device_type",
    "ac",
    "identity",
)


def generate_signature(websocket_url: str) -> str:
    values = dict(parse_qsl(urlparse(websocket_url).query, keep_blank_values=True))
    canonical = ",".join(f"{key}={values.get(key, '')}" for key in _PARAMS)
    digest = hashlib.md5(canonical.encode(), usedforsecurity=False).hexdigest()
    runtime = MiniRacer()
    runtime.eval(_SIGN_SCRIPT.read_text(encoding="utf-8"))
    return str(runtime.call("get_sign", digest))
