"""全局配置"""

import os
from pathlib import Path

import yaml

from apps.storage.secrets import secret_store

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
        # feinaLive is a single-process desktop service.  Keep one authoritative
        # SQLite database instead of requiring a separately managed MySQL server.
        path = Path(self.app_db_path).resolve().as_posix()
        return f"sqlite+aiosqlite:///{path}"

    @property
    def app_db_path(self) -> str:
        configured = (
            os.getenv("FEINALIVE_DB_PATH")
            or self._data.get("storage", {}).get("sqlite_path")
            or self._data.get("memory", {}).get("db_path")
            or "data/feinalive.db"
        )
        path = Path(str(configured))
        return str(path if path.is_absolute() else (_CONFIG_DIR / path))

    @property
    def chroma_path(self) -> str:
        configured = os.getenv("CHROMA_PATH") or self._data.get("storage", {}).get(
            "chroma_path", "data/chroma"
        )
        path = Path(str(configured))
        return str(path if path.is_absolute() else (_CONFIG_DIR / path))

    @property
    def chroma_collection(self) -> str:
        return str(
            os.getenv("CHROMA_COLLECTION")
            or self._data.get("storage", {}).get("chroma_collection", "memory_atoms")
        )

    @property
    def bilibili_sessdata(self) -> str | None:
        return os.getenv("BILIBILI_SESSDATA") or secret_store.get("bilibili.sessdata")

    @property
    def bilibili_room_id(self) -> int:
        return int(os.getenv("BILIBILI_ROOM_ID") or self._data.get("bilibili", {}).get("room_id", 0))

    @property
    def bilibili_uid(self) -> int:
        return int(self._data.get("bilibili", {}).get("uid", 0))

    @property
    def live_platform(self) -> str:
        return str(self._data.get("live", {}).get("platform", "bilibili"))

    @property
    def live_room_id(self) -> str:
        if self.live_platform == "test":
            return "test"
        if self.live_platform == "douyin":
            return self.douyin_web_rid
        return str(self.bilibili_room_id) if self.bilibili_room_id > 0 else ""

    @property
    def douyin_web_rid(self) -> str:
        return str(
            os.getenv("DOUYIN_WEB_RID")
            or self._data.get("douyin", {}).get("web_rid", "")
        ).strip()

    @property
    def douyin_cookie(self) -> str | None:
        return os.getenv("DOUYIN_COOKIE") or secret_store.get("douyin.cookie")

    @property
    def llm_api_url(self) -> str:
        return os.getenv("LLM_API_URL") or self._data.get("llm", {}).get("api_url", "")

    @property
    def llm_api_key(self) -> str | None:
        return os.getenv("LLM_API_KEY") or secret_store.get("llm.api_key")

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
    def llm_disable_thinking(self) -> bool:
        return self._data.get("llm", {}).get("disable_thinking", True)

    @property
    def llm_prompts(self) -> dict[str, str]:
        return self._data.get("llm", {}).get("prompts", {})

    @property
    def embedding_model(self) -> str:
        return os.getenv("EMBEDDING_MODEL") or self._data.get("embedding", {}).get("model", "")

    @property
    def embedding_api_url(self) -> str:
        return os.getenv("EMBEDDING_API_URL") or self._data.get("embedding", {}).get("api_url", "") or self.llm_api_url

    @property
    def embedding_api_key(self) -> str | None:
        return os.getenv("EMBEDDING_API_KEY") or secret_store.get("embedding.api_key") or self.llm_api_key

    @property
    def embedding_dimensions(self) -> int | None:
        value = os.getenv("EMBEDDING_DIMENSIONS") or self._data.get("embedding", {}).get("dimensions")
        return int(value) if value else None

    @property
    def embedding_user_graph_enabled(self) -> bool:
        return bool(self._data.get("embedding", {}).get("user_graph_enabled", True))

    @property
    def embedding_game_graph_enabled(self) -> bool:
        return bool(self._data.get("embedding", {}).get("game_graph_enabled", True))

    @property
    def tts_voice(self) -> str:
        return os.getenv("TTS_VOICE") or self._data.get("tts", {}).get("voice", "zh-CN-XiaoxiaoNeural")

    @property
    def tts_gateway_url(self) -> str:
        return (
            os.getenv("TTS_GATEWAY_URL")
            or self._data.get("tts", {}).get("gateway_url", "http://127.0.0.1:8091/v1")
        )

    @property
    def tts_api_key(self) -> str | None:
        return os.getenv("TTS_API_KEY") or secret_store.get("tts.api_key")

    @property
    def tts_model(self) -> str:
        return os.getenv("TTS_MODEL") or self._data.get("tts", {}).get("model", "edge/edge-tts")

    @property
    def tts_response_format(self) -> str:
        return self._data.get("tts", {}).get("response_format", "mp3")

    @property
    def tts_speed(self) -> float:
        return float(self._data.get("tts", {}).get("speed", 1.0))

    @property
    def tts_timeout_seconds(self) -> float:
        return float(self._data.get("tts", {}).get("timeout_seconds", 60.0))

    @property
    def host_reply_interval(self) -> int:
        return int(self._data.get("host", {}).get("reply_interval", 5))

    @property
    def host_max_reply_length(self) -> int:
        return int(self._data.get("host", {}).get("max_reply_length", 100))

    @property
    def host_playback_timeout_seconds(self) -> float:
        return float(self._data.get("host", {}).get("playback_timeout_seconds", 90.0))

    @property
    def host_model(self) -> str:
        return os.getenv("HOST_MODEL") or self._data.get("host", {}).get("model", "")

    @property
    def host_api_url(self) -> str:
        return os.getenv("HOST_API_URL") or self._data.get("host", {}).get("api_url", "") or self.llm_api_url

    @property
    def host_api_key(self) -> str | None:
        return os.getenv("HOST_API_KEY") or secret_store.get("host.api_key") or self.llm_api_key

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
    def agent_model(self) -> str:
        return os.getenv("AGENT_MODEL") or self._data.get("agent", {}).get("model", "")

    @property
    def agent_temperature(self) -> float:
        return float(os.getenv("AGENT_TEMPERATURE") or self._data.get("agent", {}).get("temperature", 0.4))

    @property
    def agent_max_tokens(self) -> int:
        return int(os.getenv("AGENT_MAX_TOKENS") or self._data.get("agent", {}).get("max_tokens", 500))

    @property
    def agent_api_url(self) -> str:
        return os.getenv("AGENT_API_URL") or self._data.get("agent", {}).get("api_url", "")

    @property
    def agent_api_key(self) -> str | None:
        return os.getenv("AGENT_API_KEY") or secret_store.get("agent.api_key") or self.llm_api_key

    @property
    def agent_disable_thinking(self) -> bool:
        return self._data.get("agent", {}).get("disable_thinking", self.llm_disable_thinking)

    @property
    def agent_min_step_interval(self) -> float:
        return float(os.getenv("AGENT_MIN_STEP_INTERVAL") or self._data.get("agent", {}).get("min_step_interval", 3.0))

    @property
    def agent_step_jitter(self) -> float:
        return float(os.getenv("AGENT_STEP_JITTER") or self._data.get("agent", {}).get("step_jitter", 0.5))

    @property
    def agent_commentary_interval(self) -> float:
        return float(os.getenv("AGENT_COMMENTARY_INTERVAL") or self._data.get("agent", {}).get("commentary_interval", 30.0))

    @property
    def agent_commentary_hold_timeout(self) -> float:
        return float(os.getenv("AGENT_COMMENTARY_HOLD_TIMEOUT", "") or self._data.get("agent", {}).get("commentary_hold_timeout", 20.0))

    @property
    def agent_memory_eagerness(self) -> int:
        return int(os.getenv("AGENT_MEMORY_EAGERNESS") or self._data.get("agent", {}).get("memory_eagerness", 3))

    @property
    def announcement(self) -> str:
        return self._data.get("announcement", "直播间24小时随机刷新开播。AI主播是小笨蛋不要欺负她喵。白天基本上是无人直播间喵，夜间可能会真人代播。直播间指令：输入 点歌 歌名 或者 点歌 BVid进行点歌，推荐使用BV号点歌。输入/clear 清除AI对你的记忆。")

    @property
    def avatar_config(self) -> dict:
        value = self._data.get("avatar", {})
        return dict(value) if isinstance(value, dict) else {}

    @property
    def admin_username(self) -> str:
        return self._data.get("admin", {}).get("username", "RongR0Ng")

    @property
    def admin_identities(self) -> dict[str, str]:
        configured = self._data.get("admin", {}).get("identities", {})
        identities = {
            str(platform): str(user_id)
            for platform, user_id in configured.items()
            if str(user_id).strip()
        }
        return identities

    @property
    def agent_enabled(self) -> bool:
        return self._data.get("agent", {}).get("enabled", False)

    @property
    def agent_mcp_url(self) -> str:
        return os.getenv("AGENT_MCP_URL") or self._data.get("agent", {}).get("mcp_url", "http://127.0.0.1:8080")

    @property
    def agent_scenario_id(self) -> str:
        return str(self._data.get("agent", {}).get("scenario_id", "slay_the_spire"))

    @property
    def agent_scenario_config(self) -> dict:
        values = self._data.get("agent", {}).get("scenario_config", {})
        return dict(values) if isinstance(values, dict) else {}

    @property
    def agent_poll_interval(self) -> float:
        return float(self._data.get("agent", {}).get("poll_interval", 1.0))

    @property
    def agent_memory_threshold(self) -> int:
        return int(self._data.get("agent", {}).get("memory_threshold", 30))

    @property
    def agent_memory_idle_seconds(self) -> float:
        return float(self._data.get("agent", {}).get("memory_idle_seconds", 120.0))

    @property
    def agent_memory_scan_interval_seconds(self) -> float:
        return float(
            self._data.get("agent", {}).get("memory_scan_interval_seconds", 30.0)
        )

    @property
    def agent_memory_context_max_chars(self) -> int:
        return int(self._data.get("agent", {}).get("memory_context_max_chars", 12000))

    @property
    def agent_min_commentary_interval(self) -> float:
        return float(self._data.get("agent", {}).get("min_commentary_interval", 15.0))

    @property
    def agent_queue_max_size(self) -> int:
        return int(self._data.get("agent", {}).get("queue_max_size", 20))

    @property
    def agent_host_history_maxlen(self) -> int:
        return int(self._data.get("agent", {}).get("host_history_maxlen", 50))

    @property
    def agent_action_history_maxlen(self) -> int:
        return int(self._data.get("agent", {}).get("action_history_maxlen", 30))

    # ---- 消息调度 (messaging) ----

    @property
    def messaging_danmaku_starvation_seconds(self) -> float:
        return float(self._data.get("messaging", {}).get("danmaku_starvation_seconds", 30.0))

    @property
    def messaging_danmaku_flood_threshold(self) -> int:
        return int(self._data.get("messaging", {}).get("danmaku_flood_threshold", 5))

    @property
    def messaging_danmaku_flood_window(self) -> float:
        return float(self._data.get("messaging", {}).get("danmaku_flood_window", 20.0))

    @property
    def messaging_gift_starvation_seconds(self) -> float:
        return float(self._data.get("messaging", {}).get("gift_starvation_seconds", 60.0))

    @property
    def messaging_gift_flood_threshold(self) -> int:
        return int(self._data.get("messaging", {}).get("gift_flood_threshold", 3))

    @property
    def messaging_gift_flood_window(self) -> float:
        return float(self._data.get("messaging", {}).get("gift_flood_window", 30.0))

    @property
    def messaging_gift_value_highest(self) -> int:
        return int(self._data.get("messaging", {}).get("gift_value_highest", 10000))

    @property
    def messaging_gift_value_high(self) -> int:
        return int(self._data.get("messaging", {}).get("gift_value_high", 5000))

    @property
    def messaging_gift_value_normal(self) -> int:
        return int(self._data.get("messaging", {}).get("gift_value_normal", 1000))

    @property
    def messaging_gift_value_low(self) -> int:
        return int(self._data.get("messaging", {}).get("gift_value_low", 100))

    @property
    def messaging_user_cooldown_seconds(self) -> float:
        return float(self._data.get("messaging", {}).get("user_cooldown_seconds", 3.0))

    @property
    def messaging_default_ttl_seconds(self) -> float:
        return float(self._data.get("messaging", {}).get("default_ttl_seconds", 30.0))

    @property
    def messaging_rate_limit_commentary(self) -> float:
        return float(self._data.get("messaging", {}).get("rate_limit_commentary", 4.0))

    @property
    def messaging_rate_limit_danmaku(self) -> float:
        return float(self._data.get("messaging", {}).get("rate_limit_danmaku", 3.0))

    @property
    def messaging_rate_limit_gift(self) -> float:
        return float(self._data.get("messaging", {}).get("rate_limit_gift", 10.0))

    # ---- AI 行为 (ai) ----

    @property
    def ai_max_history_per_session(self) -> int:
        return int(self._data.get("ai", {}).get("max_history_per_session", 16))

    @property
    def ai_summary_interval(self) -> int:
        return int(self._data.get("ai", {}).get("summary_interval", 10))

    @property
    def ai_summary_idle_seconds(self) -> float:
        return float(self._data.get("ai", {}).get("summary_idle_seconds", 300.0))

    @property
    def ai_summary_scan_interval_seconds(self) -> float:
        return float(
            self._data.get("ai", {}).get("summary_scan_interval_seconds", 60.0)
        )

    @property
    def ai_max_recent_messages(self) -> int:
        return int(self._data.get("ai", {}).get("max_recent_messages", 16))

    @property
    def ai_poll_interval_seconds(self) -> float:
        return float(self._data.get("ai", {}).get("poll_interval_seconds", 10.0))

    # ---- Independent music runtime ----

    @property
    def music_default_provider(self) -> str:
        return str(self._data.get("music", {}).get("default_provider", "auto"))

    @property
    def music_min_duration_seconds(self) -> int:
        return int(self._data.get("music", {}).get("min_duration_seconds", 60))

    @property
    def music_max_duration_seconds(self) -> int:
        return int(self._data.get("music", {}).get("max_duration_seconds", 480))

    @property
    def music_queue_capacity(self) -> int:
        return int(self._data.get("music", {}).get("queue_capacity", 5))

    @property
    def music_per_user_limit(self) -> int:
        return int(self._data.get("music", {}).get("per_user_limit", 2))

    @property
    def music_allow_bare_bv(self) -> bool:
        return bool(self._data.get("music", {}).get("allow_bare_bv", False))

    @property
    def music_accept_score(self) -> int:
        return int(self._data.get("music", {}).get("accept_score", 60))

    @property
    def music_reject_score(self) -> int:
        return int(self._data.get("music", {}).get("reject_score", -50))

    @property
    def music_llm_min_confidence(self) -> float:
        return float(self._data.get("music", {}).get("llm_min_confidence", 0.75))

    @property
    def music_search_candidates(self) -> int:
        return int(self._data.get("music", {}).get("search_candidates", 5))

    @property
    def music_ducking_factor(self) -> float:
        return float(self._data.get("music", {}).get("ducking_factor", 0.2))

    @property
    def music_ducking_enabled(self) -> bool:
        return bool(self._data.get("music", {}).get("ducking_enabled", True))

    @property
    def music_local_directories(self) -> list[str]:
        return [str(value) for value in self._data.get("music", {}).get("local_directories", [])]

    # ---- 记忆系统 (memory) ----

    @property
    def memory_db_path(self) -> str:
        return os.getenv("MEMORY_DB_PATH") or self.app_db_path

    @property
    def memory_maintenance_interval_hours(self) -> float:
        return float(self._data.get("memory", {}).get("maintenance_interval_hours", 24.0))

    @property
    def memory_forget_delay_days(self) -> float:
        return float(self._data.get("memory", {}).get("forget_delay_days", 7.0))

    @property
    def memory_purge_delay_days(self) -> float:
        return float(self._data.get("memory", {}).get("purge_delay_days", 30.0))


config = Config()
