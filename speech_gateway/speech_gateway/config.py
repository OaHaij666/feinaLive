"""Environment-only gateway configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _csv(name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, "").split(",") if item.strip())


@dataclass(frozen=True)
class GatewayConfig:
    api_key: str = os.getenv("SPEECH_GATEWAY_API_KEY", "").strip()
    default_provider: str = os.getenv("SPEECH_DEFAULT_PROVIDER", "edge").strip()
    fallback_providers: tuple[str, ...] = _csv("SPEECH_FALLBACK_PROVIDERS")


config = GatewayConfig()
