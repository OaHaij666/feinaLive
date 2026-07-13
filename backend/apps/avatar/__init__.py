"""Project-owned digital avatar runtime and API."""

from pathlib import Path

from .runtime import AvatarRuntime, get_avatar_runtime

AVATAR_ENGINE_DIR = Path(__file__).resolve().parents[2] / "avatar_engine"

__all__ = ["AVATAR_ENGINE_DIR", "AvatarRuntime", "get_avatar_runtime"]
