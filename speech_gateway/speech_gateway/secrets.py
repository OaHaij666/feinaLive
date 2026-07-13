"""OS-keyring storage for upstream provider credentials."""

from __future__ import annotations

import logging

import keyring

logger = logging.getLogger(__name__)
SERVICE_NAME = "feina-speech-gateway"


class GatewaySecretStore:
    def get(self, provider: str, field: str) -> str:
        try:
            return keyring.get_password(SERVICE_NAME, f"{provider}.{field}") or ""
        except Exception:
            logger.warning("Unable to read Gateway secret %s.%s", provider, field, exc_info=True)
            return ""

    def set(self, provider: str, field: str, value: str) -> None:
        key = f"{provider}.{field}"
        try:
            if value:
                keyring.set_password(SERVICE_NAME, key, value)
            else:
                try:
                    keyring.delete_password(SERVICE_NAME, key)
                except keyring.errors.PasswordDeleteError:
                    pass
        except Exception as exc:
            raise RuntimeError(f"Unable to store Gateway secret {key}") from exc


secret_store = GatewaySecretStore()
