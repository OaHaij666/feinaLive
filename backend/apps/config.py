"""全局配置"""

import os
from pathlib import Path

import yaml

_CONFIG_DIR = Path(__file__).parent.parent
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

    @property
    def llm_api_url(self) -> str:
        return os.getenv("LLM_API_URL") or self._data.get("llm", {}).get("api_url", "")

    @property
    def llm_api_key(self) -> str | None:
        return os.getenv("LLM_API_KEY") or self._data.get("llm", {}).get("api_key")

    @property
    def llm_model(self) -> str:
        return os.getenv("LLM_MODEL") or self._data.get("llm", {}).get("model", "")

    @property
    def llm_temperature(self) -> float:
        return float(os.getenv("LLM_TEMPERATURE") or self._data.get("llm", {}).get("temperature", 0.1))

    @property
    def llm_top_p(self) -> float:
        return float(os.getenv("LLM_TOP_P") or self._data.get("llm", {}).get("top_p", 0.9))

    @property
    def llm_max_tokens(self) -> int:
        return int(os.getenv("LLM_MAX_TOKENS") or self._data.get("llm", {}).get("max_tokens", 200))

    @property
    def auto_collect_min_views(self) -> int:
        return self._data.get("llm", {}).get("auto_collect_min_views", 20000)

    @property
    def llm_disable_thinking(self) -> bool:
        return self._data.get("llm", {}).get("disable_thinking", True)

    @property
    def llm_prompts(self) -> dict[str, str]:
        return self._data.get("llm", {}).get("prompts", {})

    @property
    def tts_voice(self) -> str:
        return os.getenv("TTS_VOICE") or self._data.get("tts", {}).get("voice", "zh-CN-XiaoxiaoNeural")

    @property
    def host_reply_interval(self) -> int:
        return int(self._data.get("host", {}).get("reply_interval", 5))

    @property
    def host_max_reply_length(self) -> int:
        return int(self._data.get("host", {}).get("max_reply_length", 100))

    @property
    def host_model(self) -> str:
        return os.getenv("HOST_MODEL") or self._data.get("host", {}).get("model", "doubao-seed-character-251128")

    @property
    def host_temperature(self) -> float:
        return float(os.getenv("HOST_TEMPERATURE") or self._data.get("host", {}).get("temperature", 0.7))

    @property
    def host_top_p(self) -> float:
        return float(os.getenv("HOST_TOP_P") or self._data.get("host", {}).get("top_p", 0.9))

    @property
    def host_max_tokens(self) -> int:
        return int(os.getenv("HOST_MAX_TOKENS") or self._data.get("host", {}).get("max_tokens", 200))

    @property
    def easyvtuber_enabled(self) -> bool:
        return self._data.get("easyvtuber", {}).get("enabled", True)

    @property
    def easyvtuber_character(self) -> str:
        return self._data.get("easyvtuber", {}).get("character", "lambda_00")

    @property
    def easyvtuber_input_type(self) -> str:
        return self._data.get("easyvtuber", {}).get("input", {}).get("type", "debug")

    @property
    def easyvtuber_osf_address(self) -> str:
        return self._data.get("easyvtuber", {}).get("input", {}).get("osf_address", "127.0.0.1:11573")

    @property
    def easyvtuber_mouse_range(self) -> str:
        return self._data.get("easyvtuber", {}).get("input", {}).get("mouse_range", "0,0,1920,1080")

    @property
    def easyvtuber_model_version(self) -> str:
        return self._data.get("easyvtuber", {}).get("model", {}).get("version", "v3")

    @property
    def easyvtuber_model_precision(self) -> str:
        return self._data.get("easyvtuber", {}).get("model", {}).get("precision", "half")

    @property
    def easyvtuber_model_separable(self) -> bool:
        return self._data.get("easyvtuber", {}).get("model", {}).get("separable", True)

    @property
    def easyvtuber_use_tensorrt(self) -> bool:
        return self._data.get("easyvtuber", {}).get("model", {}).get("use_tensorrt", True)

    @property
    def easyvtuber_use_eyebrow(self) -> bool:
        return self._data.get("easyvtuber", {}).get("model", {}).get("use_eyebrow", True)

    @property
    def easyvtuber_frame_rate(self) -> int:
        return int(self._data.get("easyvtuber", {}).get("performance", {}).get("frame_rate", 30))

    @property
    def easyvtuber_interpolation(self) -> str:
        return self._data.get("easyvtuber", {}).get("performance", {}).get("interpolation", "x2")

    @property
    def easyvtuber_super_resolution(self) -> str:
        return self._data.get("easyvtuber", {}).get("performance", {}).get("super_resolution", "off")

    @property
    def easyvtuber_ram_cache(self) -> str:
        return self._data.get("easyvtuber", {}).get("performance", {}).get("ram_cache", "2gb")

    @property
    def easyvtuber_vram_cache(self) -> str:
        return self._data.get("easyvtuber", {}).get("performance", {}).get("vram_cache", "2gb")

    @property
    def easyvtuber_ws_enabled(self) -> bool:
        return self._data.get("easyvtuber", {}).get("output", {}).get("websocket", {}).get("enabled", True)

    @property
    def easyvtuber_ws_port(self) -> int:
        return int(self._data.get("easyvtuber", {}).get("output", {}).get("websocket", {}).get("port", 8765))

    @property
    def easyvtuber_ws_host(self) -> str:
        return self._data.get("easyvtuber", {}).get("output", {}).get("websocket", {}).get("host", "localhost")


config = Config()
