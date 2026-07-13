"""OS credential-store access for runtime secrets."""

from __future__ import annotations

import logging

import keyring

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

__all__ = ["SecretStore", "secret_store"]
