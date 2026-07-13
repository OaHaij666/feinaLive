"""YAML configuration with environment-only secret resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from speech_gateway.schemas import PROVIDER_SCHEMAS
from speech_gateway.secrets import secret_store


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    type: str
    enabled: bool = True
    base_url: str = ""
    api_key_env: str = ""
    default_voice: str = ""
    timeout_seconds: float = 60.0
    formats: tuple[str, ...] = ("mp3",)
    health_path: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def api_key(self) -> str:
        environment = os.getenv(self.api_key_env, "").strip() if self.api_key_env else ""
        return environment or self.secrets.get("api_key", "")


@dataclass(frozen=True)
class RouteConfig:
    name: str
    primary: str
    fallback: tuple[str, ...] = ()


@dataclass(frozen=True)
class GatewayConfig:
    api_key: str = ""
    default_provider: str = "edge"
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    routes: dict[str, RouteConfig] = field(default_factory=dict)
    circuit_failure_threshold: int = 3
    circuit_recovery_seconds: float = 30.0
    metrics_sample_size: int = 500


def _default_data() -> dict[str, Any]:
    return {
        "gateway": {
            "api_key_env": "SPEECH_GATEWAY_API_KEY",
            "default_provider": "edge",
            "circuit_failure_threshold": 3,
            "circuit_recovery_seconds": 30,
            "metrics_sample_size": 500,
        },
        "providers": {
            "edge": {
                "type": "edge",
                "default_voice": os.getenv("EDGE_DEFAULT_VOICE", "zh-CN-XiaoxiaoNeural"),
                "formats": ["mp3"],
            },
            "volcano": {
                "type": "volcano",
                "api_key_env": "VOLCANO_API_KEY",
                "default_voice": os.getenv("VOLCANO_DEFAULT_VOICE", ""),
                "formats": ["mp3", "pcm", "ogg_opus"],
                "options": {
                    "resource_id": os.getenv("VOLCANO_RESOURCE_ID", "seed-icl-2.0"),
                    "sample_rate": 24000,
                },
            },
            "local": {
                "type": "openai_compatible",
                "enabled": False,
                "base_url": "http://127.0.0.1:8000/v1",
                "default_voice": "default",
                "formats": ["mp3", "wav"],
                "health_path": "models",
            },
        },
        "routes": {
            "host_voice": {
                "primary": "volcano/seed-icl-2.0",
                "fallback": ["edge/edge-tts"],
            }
        },
    }


def _load_data(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _default_data()
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError("Speech Gateway config root must be an object")
    return loaded


def load_config(path: str | Path | None = None) -> GatewayConfig:
    configured_path = path or os.getenv("SPEECH_GATEWAY_CONFIG", "")
    target = Path(configured_path) if configured_path else Path(__file__).parents[1] / "config.yaml"
    data = _load_data(target)
    gateway = data.get("gateway", {}) or {}

    providers: dict[str, ProviderConfig] = {}
    for name, raw_value in (data.get("providers", {}) or {}).items():
        raw = raw_value or {}
        known = {
            "type",
            "enabled",
            "base_url",
            "api_key_env",
            "default_voice",
            "timeout_seconds",
            "formats",
            "health_path",
            "options",
        }
        options = dict(raw.get("options", {}) or {})
        options.update({key: value for key, value in raw.items() if key not in known})
        provider_type = str(raw.get("type", name))
        schema = PROVIDER_SCHEMAS.get(provider_type, {})
        secrets = {
            str(field["key"]): secret_store.get(str(name), str(field["key"]))
            for field in schema.get("fields", [])
            if field.get("type") == "secret"
        }
        providers[str(name)] = ProviderConfig(
            name=str(name),
            type=provider_type,
            enabled=bool(raw.get("enabled", True)),
            base_url=str(raw.get("base_url", "")).rstrip("/"),
            api_key_env=str(raw.get("api_key_env", "")),
            default_voice=str(raw.get("default_voice", "")),
            timeout_seconds=float(raw.get("timeout_seconds", 60.0)),
            formats=tuple(str(item) for item in raw.get("formats", ["mp3"])),
            health_path=str(raw.get("health_path", "")),
            options=options,
            secrets=secrets,
        )

    routes: dict[str, RouteConfig] = {}
    for name, raw_value in (data.get("routes", {}) or {}).items():
        raw = raw_value or {}
        routes[str(name)] = RouteConfig(
            name=str(name),
            primary=str(raw.get("primary", "")),
            fallback=tuple(str(item) for item in raw.get("fallback", [])),
        )

    api_key_env = str(gateway.get("api_key_env", "SPEECH_GATEWAY_API_KEY"))
    return GatewayConfig(
        api_key=os.getenv(api_key_env, "").strip(),
        default_provider=str(gateway.get("default_provider", "edge")),
        providers=providers,
        routes=routes,
        circuit_failure_threshold=max(1, int(gateway.get("circuit_failure_threshold", 3))),
        circuit_recovery_seconds=max(1.0, float(gateway.get("circuit_recovery_seconds", 30))),
        metrics_sample_size=max(10, int(gateway.get("metrics_sample_size", 500))),
    )


config = load_config()
