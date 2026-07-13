"""Validated provider configuration persistence for the local control panel."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from speech_gateway.config import _default_data, _load_data, load_config
from speech_gateway.schemas import PROVIDER_SCHEMAS, schema_for
from speech_gateway.secrets import secret_store

MASKED = "****"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def config_path() -> Path:
    configured = os.getenv("SPEECH_GATEWAY_CONFIG", "")
    return Path(configured) if configured else Path(__file__).parents[1] / "config.yaml"


def provider_schemas() -> list[dict]:
    return [dict(schema) for schema in PROVIDER_SCHEMAS.values()]


def _field_value(provider, key: str):
    if key == "base_url":
        return provider.base_url
    if key == "default_voice":
        return provider.default_voice
    if key == "formats":
        return list(provider.formats)
    if key == "health_path":
        return provider.health_path
    if key == "timeout_seconds":
        return provider.timeout_seconds
    return provider.options.get(key)


def public_config() -> dict[str, Any]:
    settings = load_config(config_path())
    providers = {}
    for name, provider in settings.providers.items():
        schema = PROVIDER_SCHEMAS.get(provider.type, {"fields": []})
        values = {}
        for field in schema.get("fields", []):
            key = str(field["key"])
            if field.get("type") == "secret":
                environment_name = str(provider.options.get(f"{key}_env", ""))
                environment_value = os.getenv(environment_name, "") if environment_name else ""
                values[key] = (
                    MASKED
                    if provider.secrets.get(key)
                    or environment_value
                    or (key == "api_key" and provider.api_key)
                    else ""
                )
            else:
                value = _field_value(provider, key)
                values[key] = field.get("default") if value is None else value
        providers[name] = {
            "name": name,
            "type": provider.type,
            "enabled": provider.enabled,
            "values": values,
        }
    return {
        "providers": providers,
        "routes": {
            name: {"primary": route.primary, "fallback": list(route.fallback)}
            for name, route in settings.routes.items()
        },
    }


def update_provider(name: str, provider_type: str, enabled: bool, values: dict) -> None:
    if not _SAFE_NAME.fullmatch(name):
        raise ValueError("Provider name may only contain letters, numbers, '_' and '-'")
    schema = schema_for(provider_type)
    path = config_path()
    data = _load_data(path) if path.exists() else _default_data()
    providers = data.setdefault("providers", {})
    raw = dict(providers.get(name, {}) or {})
    raw["type"] = provider_type
    raw["enabled"] = enabled

    for field in schema.get("fields", []):
        key = str(field["key"])
        field_type = field.get("type")
        value = values.get(key, field.get("default"))
        if field_type == "secret":
            if isinstance(value, str) and MASKED not in value:
                secret_store.set(name, key, value.strip())
            continue
        if field.get("required") and (value is None or value == ""):
            raise ValueError(f"Provider field '{key}' is required")
        raw[key] = value

    providers[name] = raw
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)


def update_route(name: str, primary: str, fallback: list[str]) -> None:
    if not _SAFE_NAME.fullmatch(name):
        raise ValueError("Route name may only contain letters, numbers, '_' and '-'")
    targets = [primary, *fallback]
    if not primary or any("/" not in target for target in targets):
        raise ValueError("Every route target must use provider/model format")
    path = config_path()
    data = _load_data(path) if path.exists() else _default_data()
    routes = data.setdefault("routes", {})
    routes[name] = {
        "primary": primary,
        "fallback": list(dict.fromkeys(target for target in fallback if target != primary)),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)
