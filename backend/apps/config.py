"""全局配置"""

import os
from pathlib import Path

import yaml

_CONFIG_DIR = Path(__file__).parent
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"


class Config:
    _instance: "Config | None" = None
    _data: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        if _CONFIG_FILE.exists():
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        else:
            self._data = {}

    @property
    def database_url(self) -> str:
        return os.getenv("DATABASE_URL") or self._data.get("database", {}).get("url", "")

    @property
    def bilibili_sessdata(self) -> str | None:
        return os.getenv("BILIBILI_SESSDATA") or self._data.get("bilibili", {}).get("sessdata")

    @property
    def trusted_ups(self) -> list[dict]:
        return self._data.get("trusted_ups", [])

    @property
    def incremental_days(self) -> int:
        return self._data.get("up_videos", {}).get("incremental_days", 5)

    @property
    def full_refresh_days(self) -> int:
        return self._data.get("up_videos", {}).get("full_refresh_days", 30)

    @property
    def default_playlist(self) -> list[dict]:
        return self._data.get("default_playlist", [])


config = Config()
