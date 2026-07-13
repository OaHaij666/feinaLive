"""OS credential-store access for runtime secrets."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import keyring
import yaml

logger = logging.getLogger(__name__)


class SecretStore:
    service_name = "feinaLive"

    def get(self, name: str) -> str | None:
        try:
            return keyring.get_password(self.service_name, name)
        except Exception:
            logger.warning("系统密钥库不可用，无法读取 %s", name)
            return None

    def set(self, name: str, value: str) -> bool:
        try:
            if value:
                keyring.set_password(self.service_name, name, value)
            else:
                self.delete(name)
            return True
        except Exception:
            logger.exception("系统密钥库不可用，无法保存 %s", name)
            return False

    def delete(self, name: str) -> None:
        try:
            keyring.delete_password(self.service_name, name)
        except keyring.errors.PasswordDeleteError:
            pass


secret_store = SecretStore()


def migrate_legacy_secrets(config_path: str | Path) -> int:
    """Move plaintext YAML secrets to the OS keyring without losing failures."""

    path = Path(config_path)
    if not path.exists():
        return 0
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    secret_paths = (
        "bilibili.sessdata",
        "douyin.cookie",
        "llm.api_key",
        "host.api_key",
        "agent.api_key",
        "embedding.api_key",
        "volcano.access_token",
    )
    migrated = 0
    for dotted in secret_paths:
        keys = dotted.split(".")
        current = data
        for key in keys[:-1]:
            current = current.get(key) if isinstance(current, dict) else None
            if not isinstance(current, dict):
                break
        else:
            value = current.get(keys[-1])
            if value and secret_store.set(dotted, str(value)):
                current.pop(keys[-1], None)
                migrated += 1
    if "database" in data:
        # The legacy MySQL URL commonly embeds a password and is no longer used.
        data.pop("database", None)
        migrated += 1
    if "storage" not in data:
        data["storage"] = {
            "sqlite_path": "data/feinalive.db",
            "chroma_path": "data/chroma",
            "chroma_collection": "memory_atoms",
        }
        migrated += 1
    if migrated:
        temporary = path.with_suffix(path.suffix + ".tmp")
        with open(temporary, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, allow_unicode=True, default_flow_style=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    return migrated

__all__ = ["SecretStore", "migrate_legacy_secrets", "secret_store"]
