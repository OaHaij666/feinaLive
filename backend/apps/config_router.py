"""配置管理 API"""

import logging
import os
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, model_validator

from apps.avatar.schemas import AvatarConfig
from apps.config import config
from apps.storage.secrets import secret_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])

CONFIG_FILE = Path(__file__).parent.parent / "config.yaml"


# ---- Pydantic 模型 ----

class BilibiliConfig(BaseModel):
    room_id: int = 0
    sessdata: str = ""
    uid: int = 0


class DouyinConfig(BaseModel):
    web_rid: str = ""
    cookie: str = ""


class LiveConfig(BaseModel):
    platform: str = "bilibili"

    @model_validator(mode="after")
    def validate_platform(self):
        if self.platform not in {"bilibili", "douyin", "test"}:
            raise ValueError("直播平台只支持 bilibili、douyin 或 test")
        return self


class HostConfig(BaseModel):
    reply_interval: int = 5
    max_reply_length: int = 100
    api_url: str = ""
    api_key: str = ""
    model: str = "doubao-seed-character-251128"
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 200
    disable_thinking: bool = True


class LLMConfig(BaseModel):
    api_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.1
    top_p: float = 0.9
    max_tokens: int = 200
    disable_thinking: bool = True


class TTSConfig(BaseModel):
    provider: str = "volcano"
    voice: str = "zh-CN-XiaoxiaoNeural"
    encoding: str = "wav"
    speed_ratio: float = 1.0


class VolcanoConfig(BaseModel):
    appid: str = ""
    access_token: str = ""
    speaker_id: str = ""


class AgentConfig(BaseModel):
    enabled: bool = False
    scenario_id: str = "slay_the_spire"
    mcp_url: str = "http://127.0.0.1:8080"
    api_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.4
    max_tokens: int = 500
    disable_thinking: bool = True
    poll_interval: float = 1.0
    memory_threshold: int = 30
    memory_idle_seconds: float = 120.0
    memory_scan_interval_seconds: float = 30.0
    memory_context_max_chars: int = 12000
    min_step_interval: float = 3.0
    step_jitter: float = 0.5
    commentary_interval: float = 30.0
    min_commentary_interval: float = 15.0
    commentary_hold_timeout: float = 20.0
    memory_eagerness: int = 3
    queue_max_size: int = 20
    host_history_maxlen: int = 50
    action_history_maxlen: int = 30
    scenario_config: dict[str, object] = Field(default_factory=dict)


class AIConfig(BaseModel):
    max_history_per_session: int = 16
    summary_interval: int = 10
    summary_idle_seconds: float = 300.0
    summary_scan_interval_seconds: float = 60.0
    max_recent_messages: int = 16
    poll_interval_seconds: float = 10.0


class MessagingRateLimitsConfig(BaseModel):
    commentary: float = 4.0
    danmaku: float = 3.0
    gift: float = 10.0


class MessagingConfig(BaseModel):
    danmaku_starvation_seconds: float = 30.0
    danmaku_flood_threshold: int = 5
    danmaku_flood_window: float = 20.0
    gift_starvation_seconds: float = 60.0
    gift_flood_threshold: int = 3
    gift_flood_window: float = 30.0
    gift_value_highest: int = 10000
    gift_value_high: int = 5000
    gift_value_normal: int = 1000
    gift_value_low: int = 100
    user_cooldown_seconds: float = 3.0
    default_ttl_seconds: float = 30.0
    rate_limit_commentary: float = 4.0
    rate_limit_danmaku: float = 3.0
    rate_limit_gift: float = 10.0


class MusicConfigModel(BaseModel):
    default_provider: str = "auto"
    min_duration_seconds: int = Field(default=60, ge=1, le=86400)
    max_duration_seconds: int = Field(default=480, ge=1, le=86400)
    queue_capacity: int = Field(default=5, ge=1, le=1000)
    per_user_limit: int = Field(default=2, ge=1, le=100)
    allow_bare_bv: bool = False
    accept_score: int = Field(default=60, ge=0, le=100)
    reject_score: int = Field(default=-50, ge=-100, le=0)
    llm_min_confidence: float = Field(default=0.75, ge=0, le=1)
    search_candidates: int = Field(default=5, ge=1, le=20)
    ducking_factor: float = Field(default=0.2, ge=0, le=1)
    ducking_enabled: bool = True
    local_directories: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.min_duration_seconds >= self.max_duration_seconds:
            raise ValueError("music.min_duration_seconds 必须小于 max_duration_seconds")
        return self


class StorageConfig(BaseModel):
    sqlite_path: str = "data/feinalive.db"
    chroma_path: str = "data/chroma"
    chroma_collection: str = "memory_atoms"


class AdminConfig(BaseModel):
    username: str = "RongR0Ng"
    identities: dict[str, str] = Field(default_factory=dict)


class EmbeddingConfig(BaseModel):
    model: str = ""
    api_url: str = ""
    api_key: str = ""
    dimensions: int | None = None
    user_graph_enabled: bool = True
    game_graph_enabled: bool = True


class FullConfig(BaseModel):
    live: LiveConfig = LiveConfig()
    bilibili: BilibiliConfig = BilibiliConfig()
    douyin: DouyinConfig = DouyinConfig()
    host: HostConfig = HostConfig()
    llm: LLMConfig = LLMConfig()
    tts: TTSConfig = TTSConfig()
    volcano: VolcanoConfig = VolcanoConfig()
    agent: AgentConfig = AgentConfig()
    avatar: AvatarConfig = AvatarConfig()
    ai: AIConfig = AIConfig()
    messaging: MessagingConfig = MessagingConfig()
    music: MusicConfigModel = MusicConfigModel()
    storage: StorageConfig = StorageConfig()
    announcement: str = ""
    admin: AdminConfig = AdminConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    restart_required: bool = False


# ---- 辅助: masked 返回 ----

def _mask_sensitive(value: str) -> str:
    """敏感字段仅返回前4后4字符，中间用 * 替代"""
    if not value or len(value) <= 8:
        return "****"
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


# ---- GET /config ----

@router.get("", response_model=FullConfig)
async def get_full_config():
    from apps.agent.manager import get_agent_manager

    return FullConfig(
        restart_required=get_agent_manager().needs_restart,
        live=LiveConfig(
            platform=config.live_platform,
        ),
        bilibili=BilibiliConfig(
            room_id=config.bilibili_room_id,
            sessdata=_mask_sensitive(config.bilibili_sessdata or ""),
            uid=config.bilibili_uid,
        ),
        douyin=DouyinConfig(
            web_rid=config.douyin_web_rid,
            cookie=_mask_sensitive(config.douyin_cookie or ""),
        ),
        host=HostConfig(
            reply_interval=config.host_reply_interval,
            max_reply_length=config.host_max_reply_length,
            api_url=config.host_api_url,
            api_key=_mask_sensitive(config.host_api_key or ""),
            model=config.host_model,
            temperature=config.host_temperature,
            top_p=config.host_top_p,
            max_tokens=config.host_max_tokens,
            disable_thinking=config.llm_disable_thinking,
        ),
        llm=LLMConfig(
            api_url=config.llm_api_url,
            api_key=_mask_sensitive(config.llm_api_key or ""),
            model=config.llm_model,
            temperature=config.llm_temperature,
            top_p=config.llm_top_p,
            max_tokens=config.llm_max_tokens,
            disable_thinking=config.llm_disable_thinking,
        ),
        tts=TTSConfig(
            provider=config.tts_provider,
            voice=config.tts_voice,
            encoding=config.tts_encoding,
            speed_ratio=config.tts_speed_ratio,
        ),
        volcano=VolcanoConfig(
            appid=config.volcano_appid,
            access_token=_mask_sensitive(config.volcano_access_token or ""),
            speaker_id=config.volcano_speaker_id,
        ),
        agent=AgentConfig(
            enabled=config.agent_enabled,
            scenario_id=config.agent_scenario_id,
            mcp_url=config.agent_mcp_url,
            api_url=config.agent_api_url,
            api_key=_mask_sensitive(config.agent_api_key or ""),
            model=config.agent_model,
            temperature=config.agent_temperature,
            max_tokens=config.agent_max_tokens,
            disable_thinking=config.agent_disable_thinking,
            poll_interval=config.agent_poll_interval,
            memory_threshold=config.agent_memory_threshold,
            memory_idle_seconds=config.agent_memory_idle_seconds,
            memory_scan_interval_seconds=config.agent_memory_scan_interval_seconds,
            memory_context_max_chars=config.agent_memory_context_max_chars,
            min_step_interval=config.agent_min_step_interval,
            step_jitter=config.agent_step_jitter,
            commentary_interval=config.agent_commentary_interval,
            min_commentary_interval=config.agent_min_commentary_interval,
            commentary_hold_timeout=config.agent_commentary_hold_timeout,
            memory_eagerness=config.agent_memory_eagerness,
            queue_max_size=config.agent_queue_max_size,
            host_history_maxlen=config.agent_host_history_maxlen,
            action_history_maxlen=config.agent_action_history_maxlen,
            scenario_config=config.agent_scenario_config,
        ),
        avatar=AvatarConfig.model_validate(config.avatar_config),
        ai=AIConfig(
            max_history_per_session=config.ai_max_history_per_session,
            summary_interval=config.ai_summary_interval,
            summary_idle_seconds=config.ai_summary_idle_seconds,
            summary_scan_interval_seconds=config.ai_summary_scan_interval_seconds,
            max_recent_messages=config.ai_max_recent_messages,
            poll_interval_seconds=config.ai_poll_interval_seconds,
        ),
        messaging=MessagingConfig(
            danmaku_starvation_seconds=config.messaging_danmaku_starvation_seconds,
            danmaku_flood_threshold=config.messaging_danmaku_flood_threshold,
            danmaku_flood_window=config.messaging_danmaku_flood_window,
            gift_starvation_seconds=config.messaging_gift_starvation_seconds,
            gift_flood_threshold=config.messaging_gift_flood_threshold,
            gift_flood_window=config.messaging_gift_flood_window,
            gift_value_highest=config.messaging_gift_value_highest,
            gift_value_high=config.messaging_gift_value_high,
            gift_value_normal=config.messaging_gift_value_normal,
            gift_value_low=config.messaging_gift_value_low,
            user_cooldown_seconds=config.messaging_user_cooldown_seconds,
            default_ttl_seconds=config.messaging_default_ttl_seconds,
            rate_limit_commentary=config.messaging_rate_limit_commentary,
            rate_limit_danmaku=config.messaging_rate_limit_danmaku,
            rate_limit_gift=config.messaging_rate_limit_gift,
        ),
        music=MusicConfigModel(
            default_provider=config.music_default_provider,
            min_duration_seconds=config.music_min_duration_seconds,
            max_duration_seconds=config.music_max_duration_seconds,
            queue_capacity=config.music_queue_capacity,
            per_user_limit=config.music_per_user_limit,
            allow_bare_bv=config.music_allow_bare_bv,
            accept_score=config.music_accept_score,
            reject_score=config.music_reject_score,
            llm_min_confidence=config.music_llm_min_confidence,
            search_candidates=config.music_search_candidates,
            ducking_factor=config.music_ducking_factor,
            ducking_enabled=config.music_ducking_enabled,
            local_directories=config.music_local_directories,
        ),
        storage=StorageConfig(
            sqlite_path=config.app_db_path,
            chroma_path=config.chroma_path,
            chroma_collection=config.chroma_collection,
        ),
        announcement=config.announcement,
        admin=AdminConfig(
            username=config.admin_username,
            identities=config.admin_identities,
        ),
        embedding=EmbeddingConfig(
            model=config.embedding_model,
            api_url=config.embedding_api_url,
            api_key=_mask_sensitive(config.embedding_api_key or ""),
            dimensions=config.embedding_dimensions,
            user_graph_enabled=config.embedding_user_graph_enabled,
            game_graph_enabled=config.embedding_game_graph_enabled,
        ),
    )


# ---- PUT /config ----

SENSITIVE_KEYS = {
    "bilibili.sessdata",
    "douyin.cookie",
    "llm.api_key",
    "agent.api_key",
    "volcano.access_token",
    "host.api_key",
    "embedding.api_key",
}

MASKED_PATTERN = "****"


def _should_skip_sensitive(path: str, value: str) -> bool:
    """如果敏感字段值未修改（包含 **** 掩码），跳过更新"""
    if path in SENSITIVE_KEYS and MASKED_PATTERN in value:
        return True
    return False


def _deep_set(data: dict, keys: list[str], value):
    """按路径设置嵌套 dict 值"""
    current = data
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


def _deep_delete(data: dict, keys: list[str]) -> None:
    current = data
    for key in keys[:-1]:
        value = current.get(key)
        if not isinstance(value, dict):
            return
        current = value
    current.pop(keys[-1], None)


def _store_secret(data: dict, path: str, value: str) -> None:
    if MASKED_PATTERN in value:
        _deep_delete(data, path.split("."))
        return
    if value:
        if not secret_store.set(path, value):
            raise RuntimeError(f"无法写入系统密钥库: {path}")
    else:
        secret_store.delete(path)
    _deep_delete(data, path.split("."))


def _atomic_write_yaml(data: dict) -> None:
    temporary = CONFIG_FILE.with_suffix(".yaml.tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, default_flow_style=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, CONFIG_FILE)


@router.put("", response_model=FullConfig)
async def update_full_config(config_data: FullConfig, response: Response):
    try:
        old_live = (
            config.live_platform,
            config.live_room_id,
            config.bilibili_sessdata,
            config.douyin_cookie,
        )
        old_avatar = AvatarConfig.model_validate(config.avatar_config)
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        flat: dict[str, object] = {}

        flat["live.platform"] = config_data.live.platform
        _deep_delete(data, ["live", "test_mode"])
        _deep_delete(data, ["bilibili", "use_test_room"])

        # bilibili
        if config_data.bilibili:
            flat["bilibili.room_id"] = config_data.bilibili.room_id
            flat["bilibili.uid"] = config_data.bilibili.uid
            _store_secret(data, "bilibili.sessdata", config_data.bilibili.sessdata)

        flat["douyin.web_rid"] = config_data.douyin.web_rid.strip()
        _store_secret(data, "douyin.cookie", config_data.douyin.cookie)

        # host
        h = config_data.host
        flat["host.reply_interval"] = h.reply_interval
        flat["host.max_reply_length"] = h.max_reply_length
        flat["host.api_url"] = h.api_url
        _store_secret(data, "host.api_key", h.api_key)
        flat["host.model"] = h.model
        flat["host.temperature"] = h.temperature
        flat["host.top_p"] = h.top_p
        flat["host.max_tokens"] = h.max_tokens
        flat["llm.disable_thinking"] = h.disable_thinking

        # llm
        llm_config = config_data.llm
        flat["llm.api_url"] = llm_config.api_url
        _store_secret(data, "llm.api_key", llm_config.api_key)
        flat["llm.model"] = llm_config.model
        flat["llm.temperature"] = llm_config.temperature
        flat["llm.top_p"] = llm_config.top_p
        flat["llm.max_tokens"] = llm_config.max_tokens
        flat["llm.disable_thinking"] = llm_config.disable_thinking

        # tts
        t = config_data.tts
        flat["tts.provider"] = t.provider
        flat["tts.voice"] = t.voice
        flat["tts.encoding"] = t.encoding
        flat["tts.speed_ratio"] = t.speed_ratio

        # volcano
        v = config_data.volcano
        flat["volcano.appid"] = v.appid
        _store_secret(data, "volcano.access_token", v.access_token)
        flat["volcano.speaker_id"] = v.speaker_id

        # agent
        agent = config_data.agent
        from apps.agent.scenarios.registry import validate_scenario_config

        try:
            validated_scenario_config = validate_scenario_config(
                agent.scenario_id,
                agent.scenario_config,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        flat["agent.enabled"] = agent.enabled
        flat["agent.scenario_id"] = agent.scenario_id
        flat["agent.mcp_url"] = agent.mcp_url
        flat["agent.api_url"] = agent.api_url
        _store_secret(data, "agent.api_key", agent.api_key)
        flat["agent.model"] = agent.model
        flat["agent.temperature"] = agent.temperature
        flat["agent.max_tokens"] = agent.max_tokens
        flat["agent.disable_thinking"] = agent.disable_thinking
        flat["agent.poll_interval"] = agent.poll_interval
        flat["agent.memory_threshold"] = agent.memory_threshold
        flat["agent.memory_idle_seconds"] = agent.memory_idle_seconds
        flat["agent.memory_scan_interval_seconds"] = agent.memory_scan_interval_seconds
        flat["agent.memory_context_max_chars"] = agent.memory_context_max_chars
        flat["agent.min_step_interval"] = agent.min_step_interval
        flat["agent.step_jitter"] = agent.step_jitter
        flat["agent.commentary_interval"] = agent.commentary_interval
        flat["agent.min_commentary_interval"] = agent.min_commentary_interval
        flat["agent.commentary_hold_timeout"] = agent.commentary_hold_timeout
        flat["agent.memory_eagerness"] = agent.memory_eagerness
        flat["agent.queue_max_size"] = agent.queue_max_size
        flat["agent.host_history_maxlen"] = agent.host_history_maxlen
        flat["agent.action_history_maxlen"] = agent.action_history_maxlen
        flat["agent.scenario_config"] = validated_scenario_config

        data["avatar"] = config_data.avatar.model_dump(mode="json")

        # ai
        a = config_data.ai
        flat["ai.max_history_per_session"] = a.max_history_per_session
        flat["ai.summary_interval"] = a.summary_interval
        flat["ai.summary_idle_seconds"] = a.summary_idle_seconds
        flat["ai.summary_scan_interval_seconds"] = a.summary_scan_interval_seconds
        flat["ai.max_recent_messages"] = a.max_recent_messages
        flat["ai.poll_interval_seconds"] = a.poll_interval_seconds

        # messaging
        m = config_data.messaging
        flat["messaging.danmaku_starvation_seconds"] = m.danmaku_starvation_seconds
        flat["messaging.danmaku_flood_threshold"] = m.danmaku_flood_threshold
        flat["messaging.danmaku_flood_window"] = m.danmaku_flood_window
        flat["messaging.gift_starvation_seconds"] = m.gift_starvation_seconds
        flat["messaging.gift_flood_threshold"] = m.gift_flood_threshold
        flat["messaging.gift_flood_window"] = m.gift_flood_window
        flat["messaging.gift_value_highest"] = m.gift_value_highest
        flat["messaging.gift_value_high"] = m.gift_value_high
        flat["messaging.gift_value_normal"] = m.gift_value_normal
        flat["messaging.gift_value_low"] = m.gift_value_low
        flat["messaging.user_cooldown_seconds"] = m.user_cooldown_seconds
        flat["messaging.default_ttl_seconds"] = m.default_ttl_seconds
        flat["messaging.rate_limit_commentary"] = m.rate_limit_commentary
        flat["messaging.rate_limit_danmaku"] = m.rate_limit_danmaku
        flat["messaging.rate_limit_gift"] = m.rate_limit_gift

        # music
        mc = config_data.music
        flat["music.default_provider"] = mc.default_provider
        flat["music.min_duration_seconds"] = mc.min_duration_seconds
        flat["music.max_duration_seconds"] = mc.max_duration_seconds
        flat["music.queue_capacity"] = mc.queue_capacity
        flat["music.per_user_limit"] = mc.per_user_limit
        flat["music.allow_bare_bv"] = mc.allow_bare_bv
        flat["music.accept_score"] = mc.accept_score
        flat["music.reject_score"] = mc.reject_score
        flat["music.llm_min_confidence"] = mc.llm_min_confidence
        flat["music.search_candidates"] = mc.search_candidates
        flat["music.ducking_factor"] = mc.ducking_factor
        flat["music.ducking_enabled"] = mc.ducking_enabled
        flat["music.local_directories"] = mc.local_directories

        storage = config_data.storage
        flat["storage.sqlite_path"] = storage.sqlite_path
        flat["storage.chroma_path"] = storage.chroma_path
        flat["storage.chroma_collection"] = storage.chroma_collection

        # top-level lists
        data["announcement"] = config_data.announcement
        data["admin"] = config_data.admin.model_dump()

        # embedding
        e = config_data.embedding
        flat["embedding.provider"] = e.provider
        flat["embedding.model"] = e.model
        flat["embedding.api_url"] = e.api_url
        flat["embedding.user_graph_enabled"] = e.user_graph_enabled
        flat["embedding.game_graph_enabled"] = e.game_graph_enabled
        _store_secret(data, "embedding.api_key", e.api_key)
        if e.dimensions is not None:
            flat["embedding.dimensions"] = e.dimensions

        # 将 flat 键写入嵌套 dict
        for key, value in flat.items():
            parts = key.split(".")
            _deep_set(data, parts, value)

        _atomic_write_yaml(data)

        config._load()

        from apps.agent.manager import get_agent_manager

        restart_required = get_agent_manager().needs_restart
        live_changed = old_live != (
            config.live_platform,
            config.live_room_id,
            config.bilibili_sessdata,
            config.douyin_cookie,
        )
        avatar_changed = old_avatar != AvatarConfig.model_validate(config.avatar_config)
        restart_required = restart_required or live_changed or avatar_changed
        response.headers["X-Restart-Required"] = "true" if restart_required else "false"
        result = await get_full_config()
        result.restart_required = restart_required
        return result

    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新配置失败: {e}")


# ---- 独立 section 端点 ----

@router.get("/sections")
async def list_sections():
    """返回所有配置 section 的 key 和描述"""
    return {
        "sections": [
            {"key": "live", "label": "直播平台", "description": "Bilibili / 抖音直播接入"},
            {"key": "host", "label": "AI主播", "description": "主播回复参数和模型"},
            {"key": "llm", "label": "通用LLM", "description": "通用大语言模型配置"},
            {"key": "tts", "label": "语音合成", "description": "TTS 语音输出配置"},
            {"key": "volcano", "label": "火山引擎", "description": "火山引擎 TTS 凭证"},
            {"key": "agent", "label": "Agent", "description": "场景、能力与 Agent 行为参数"},
            {"key": "avatar", "label": "数字人", "description": "FeinaAvatar 动作、口型、渲染与输出"},
            {"key": "ai", "label": "AI行为", "description": "记忆、历史、轮询间隔"},
            {"key": "messaging", "label": "消息调度", "description": "优先级、队列、频率限制"},
            {"key": "music", "label": "音乐系统", "description": "Provider、点歌审核与播放参数"},
            {"key": "announcement", "label": "公告", "description": "直播间跑马灯公告"},
            {"key": "admin", "label": "管理员", "description": "管理员身份标识"},
            {"key": "embedding", "label": "向量模型", "description": "Embedding / 向量检索模型配置"},
        ]
    }


# ---- Avatar standalone endpoints ----

@router.get("/avatar", response_model=AvatarConfig)
async def get_avatar_config():
    return AvatarConfig.model_validate(config.avatar_config)


@router.put("/avatar", response_model=AvatarConfig)
async def update_avatar_config(config_data: AvatarConfig):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        data["avatar"] = config_data.model_dump(mode="json")

        _atomic_write_yaml(data)

        config._load()

        return config_data

    except Exception as e:
        logger.error(f"更新 Avatar 配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新配置失败: {e}")


@router.get("/avatar/characters")
async def list_characters():
    from apps.avatar import AVATAR_ENGINE_DIR

    images_dir = AVATAR_ENGINE_DIR / "data" / "images"
    characters = []

    if images_dir.exists():
        for f in sorted(images_dir.glob("*.png")):
            characters.append({
                "name": f.stem,
            })

    return {"characters": characters}


@router.post("/avatar/open-images")
async def open_images_folder():
    """打开数字人图片文件夹（仅 Windows）"""
    import subprocess

    from apps.avatar import AVATAR_ENGINE_DIR
    images_dir = AVATAR_ENGINE_DIR / "data" / "images"
    if not images_dir.exists():
        images_dir.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(["explorer", str(images_dir)])
    return {"success": True, "path": str(images_dir)}
