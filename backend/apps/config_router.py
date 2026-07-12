"""配置管理 API"""

import logging
import os
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
    use_test_room: bool = False


class HostConfig(BaseModel):
    room_id: int = 0
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
    auto_collect_min_views: int = 20000
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


class GameConfig(BaseModel):
    enabled: bool = False
    game_id: str = "slay_the_spire"
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
    game_history_maxlen: int = 30
    game_config: dict[str, object] = Field(default_factory=dict)


class EasyVtuberInputConfig(BaseModel):
    type: str = "debug"
    osf_address: str = "127.0.0.1:11573"
    mouse_range: str = "0,0,1920,1080"


class EasyVtuberModelConfig(BaseModel):
    version: str = "v3"
    precision: str = "half"
    separable: bool = True
    use_tensorrt: bool = True
    use_eyebrow: bool = True


class EasyVtuberPerformanceConfig(BaseModel):
    frame_rate: int = 30
    interpolation: str = "x2"
    super_resolution: str = "off"
    ram_cache: str = "2gb"
    vram_cache: str = "2gb"


class EasyVtuberWebSocketConfig(BaseModel):
    enabled: bool = True
    port: int = 8765
    host: str = "localhost"


class EasyVtuberOutputConfig(BaseModel):
    websocket: EasyVtuberWebSocketConfig = EasyVtuberWebSocketConfig()


class EasyVtuberConfig(BaseModel):
    enabled: bool = True
    character: str = "feina00"
    input: EasyVtuberInputConfig = EasyVtuberInputConfig()
    model: EasyVtuberModelConfig = EasyVtuberModelConfig()
    performance: EasyVtuberPerformanceConfig = EasyVtuberPerformanceConfig()
    output: EasyVtuberOutputConfig = EasyVtuberOutputConfig()


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
    verify_min_duration: int = 60
    verify_max_duration: int = 480
    verify_max_comments: int = 3


class StorageConfig(BaseModel):
    sqlite_path: str = "data/feinalive.db"
    chroma_path: str = "data/chroma"
    chroma_collection: str = "memory_atoms"


class AdminConfig(BaseModel):
    uid: int = 378810242
    username: str = "RongR0Ng"


class EmbeddingConfig(BaseModel):
    provider: str = "openai"
    model: str = ""
    api_url: str = ""
    api_key: str = ""
    dimensions: int | None = None
    user_graph_enabled: bool = True
    game_graph_enabled: bool = True


class FullConfig(BaseModel):
    bilibili: BilibiliConfig = BilibiliConfig()
    host: HostConfig = HostConfig()
    llm: LLMConfig = LLMConfig()
    tts: TTSConfig = TTSConfig()
    volcano: VolcanoConfig = VolcanoConfig()
    game: GameConfig = GameConfig()
    easyvtuber: EasyVtuberConfig = EasyVtuberConfig()
    ai: AIConfig = AIConfig()
    messaging: MessagingConfig = MessagingConfig()
    music_config: MusicConfigModel = MusicConfigModel()
    storage: StorageConfig = StorageConfig()
    announcement: str = ""
    admin: AdminConfig = AdminConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()


# ---- 辅助: masked 返回 ----

def _mask_sensitive(value: str) -> str:
    """敏感字段仅返回前4后4字符，中间用 * 替代"""
    if not value or len(value) <= 8:
        return "****"
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


# ---- GET /config ----

@router.get("", response_model=FullConfig)
async def get_full_config():
    return FullConfig(
        bilibili=BilibiliConfig(
            room_id=config.bilibili_room_id,
            sessdata=_mask_sensitive(config.bilibili_sessdata or ""),
            uid=config.bilibili_uid,
            use_test_room=config.bilibili_use_test_room,
        ),
        host=HostConfig(
            room_id=config.default_room_id,
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
            auto_collect_min_views=config.auto_collect_min_views,
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
        game=GameConfig(
            enabled=config.game_enabled,
            game_id=config.game_id,
            mcp_url=config.game_mcp_url,
            api_url=config.game_api_url,
            api_key=_mask_sensitive(config.game_api_key or ""),
            model=config.game_model,
            temperature=config.game_temperature,
            max_tokens=config.game_max_tokens,
            disable_thinking=config.game_disable_thinking,
            poll_interval=config.game_poll_interval,
            memory_threshold=config.game_memory_threshold,
            memory_idle_seconds=config.game_memory_idle_seconds,
            memory_scan_interval_seconds=config.game_memory_scan_interval_seconds,
            memory_context_max_chars=config.game_memory_context_max_chars,
            min_step_interval=config.game_min_step_interval,
            step_jitter=config.game_step_jitter,
            commentary_interval=config.game_commentary_interval,
            min_commentary_interval=config.game_min_commentary_interval,
            commentary_hold_timeout=config.game_commentary_hold_timeout,
            memory_eagerness=config.game_memory_eagerness,
            queue_max_size=config.game_queue_max_size,
            host_history_maxlen=config.game_host_history_maxlen,
            game_history_maxlen=config.game_game_history_maxlen,
            game_config=config.game_config,
        ),
        easyvtuber=EasyVtuberConfig(
            enabled=config.easyvtuber_enabled,
            character=config.easyvtuber_character,
            input=EasyVtuberInputConfig(
                type=config.easyvtuber_input_type,
                osf_address=config.easyvtuber_osf_address,
                mouse_range=config.easyvtuber_mouse_range,
            ),
            model=EasyVtuberModelConfig(
                version=config.easyvtuber_model_version,
                precision=config.easyvtuber_model_precision,
                separable=config.easyvtuber_model_separable,
                use_tensorrt=config.easyvtuber_use_tensorrt,
                use_eyebrow=config.easyvtuber_use_eyebrow,
            ),
            performance=EasyVtuberPerformanceConfig(
                frame_rate=config.easyvtuber_frame_rate,
                interpolation=config.easyvtuber_interpolation,
                super_resolution=config.easyvtuber_super_resolution,
                ram_cache=config.easyvtuber_ram_cache,
                vram_cache=config.easyvtuber_vram_cache,
            ),
            output=EasyVtuberOutputConfig(
                websocket=EasyVtuberWebSocketConfig(
                    enabled=config.easyvtuber_ws_enabled,
                    port=config.easyvtuber_ws_port,
                    host=config.easyvtuber_ws_host,
                )
            ),
        ),
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
        music_config=MusicConfigModel(
            verify_min_duration=config.music_verify_min_duration,
            verify_max_duration=config.music_verify_max_duration,
            verify_max_comments=config.music_verify_max_comments,
        ),
        storage=StorageConfig(
            sqlite_path=config.app_db_path,
            chroma_path=config.chroma_path,
            chroma_collection=config.chroma_collection,
        ),
        announcement=config.announcement,
        admin=AdminConfig(
            uid=config.admin_uid,
            username=config.admin_username,
        ),
        embedding=EmbeddingConfig(
            provider=config.embedding_provider,
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
    "llm.api_key",
    "game.api_key",
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
    if value and MASKED_PATTERN not in value and not secret_store.set(path, value):
        raise RuntimeError(f"无法写入系统密钥库: {path}")
    if not value or MASKED_PATTERN in value or secret_store.get(path):
        _deep_delete(data, path.split("."))


def _atomic_write_yaml(data: dict) -> None:
    temporary = CONFIG_FILE.with_suffix(".yaml.tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, default_flow_style=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, CONFIG_FILE)


@router.put("", response_model=FullConfig)
async def update_full_config(config_data: FullConfig):
    try:
        old_bilibili_room_id = config.bilibili_room_id
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        flat: dict[str, object] = {}

        # bilibili
        if config_data.bilibili:
            flat["bilibili.room_id"] = config_data.bilibili.room_id
            flat["bilibili.uid"] = config_data.bilibili.uid
            _store_secret(data, "bilibili.sessdata", config_data.bilibili.sessdata)
            flat["bilibili.use_test_room"] = config_data.bilibili.use_test_room

            from apps.ai.admin_commands import get_admin_handler
            admin = get_admin_handler()
            admin.set_test_room(config_data.bilibili.use_test_room)

        # host
        h = config_data.host
        flat["host.room_id"] = h.room_id
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
        flat["llm.auto_collect_min_views"] = llm_config.auto_collect_min_views
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

        # game
        g = config_data.game
        from apps.ai.mcp.games.registry import validate_game_config

        try:
            validated_game_config = validate_game_config(g.game_id, g.game_config)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        flat["game.enabled"] = g.enabled
        flat["game.game_id"] = g.game_id
        flat["game.mcp_url"] = g.mcp_url
        flat["game.api_url"] = g.api_url
        _store_secret(data, "game.api_key", g.api_key)
        flat["game.model"] = g.model
        flat["game.temperature"] = g.temperature
        flat["game.max_tokens"] = g.max_tokens
        flat["game.disable_thinking"] = g.disable_thinking
        flat["game.poll_interval"] = g.poll_interval
        flat["game.memory_threshold"] = g.memory_threshold
        flat["game.memory_idle_seconds"] = g.memory_idle_seconds
        flat["game.memory_scan_interval_seconds"] = g.memory_scan_interval_seconds
        flat["game.memory_context_max_chars"] = g.memory_context_max_chars
        flat["game.min_step_interval"] = g.min_step_interval
        flat["game.step_jitter"] = g.step_jitter
        flat["game.commentary_interval"] = g.commentary_interval
        flat["game.min_commentary_interval"] = g.min_commentary_interval
        flat["game.commentary_hold_timeout"] = g.commentary_hold_timeout
        flat["game.memory_eagerness"] = g.memory_eagerness
        flat["game.queue_max_size"] = g.queue_max_size
        flat["game.host_history_maxlen"] = g.host_history_maxlen
        flat["game.game_history_maxlen"] = g.game_history_maxlen
        flat["game.game_config"] = validated_game_config

        # easyvtuber
        ev = config_data.easyvtuber
        flat["easyvtuber.enabled"] = ev.enabled
        flat["easyvtuber.character"] = ev.character
        flat["easyvtuber.input.type"] = ev.input.type
        flat["easyvtuber.input.osf_address"] = ev.input.osf_address
        flat["easyvtuber.input.mouse_range"] = ev.input.mouse_range
        flat["easyvtuber.model.version"] = ev.model.version
        flat["easyvtuber.model.precision"] = ev.model.precision
        flat["easyvtuber.model.separable"] = ev.model.separable
        flat["easyvtuber.model.use_tensorrt"] = ev.model.use_tensorrt
        flat["easyvtuber.model.use_eyebrow"] = ev.model.use_eyebrow
        flat["easyvtuber.performance.frame_rate"] = ev.performance.frame_rate
        flat["easyvtuber.performance.interpolation"] = ev.performance.interpolation
        flat["easyvtuber.performance.super_resolution"] = ev.performance.super_resolution
        flat["easyvtuber.performance.ram_cache"] = ev.performance.ram_cache
        flat["easyvtuber.performance.vram_cache"] = ev.performance.vram_cache
        flat["easyvtuber.output.websocket.enabled"] = ev.output.websocket.enabled
        flat["easyvtuber.output.websocket.port"] = ev.output.websocket.port
        flat["easyvtuber.output.websocket.host"] = ev.output.websocket.host

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

        # music_config
        mc = config_data.music_config
        flat["music_config.verify_min_duration"] = mc.verify_min_duration
        flat["music_config.verify_max_duration"] = mc.verify_max_duration
        flat["music_config.verify_max_comments"] = mc.verify_max_comments

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

        from apps.live.room_session import get_room_session_manager

        room_sessions = get_room_session_manager()
        room_changed = config.bilibili_room_id != old_bilibili_room_id
        room_missing = (
            config.bilibili_room_id > 0
            and room_sessions.active_room_id != str(config.bilibili_room_id)
        )
        if room_changed or room_missing:
            from core.websocket import manager as websocket_manager

            if config.bilibili_room_id > 0:
                context = await room_sessions.activate(config.bilibili_room_id)
                await websocket_manager.disconnect_other_rooms(context.room_id)
            else:
                await room_sessions.stop()
                await websocket_manager.disconnect_other_rooms("")

        return await get_full_config()

    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新配置失败: {e}")


# ---- 独立 section 端点 ----

@router.get("/sections")
async def list_sections():
    """返回所有配置 section 的 key 和描述"""
    return {
        "sections": [
            {"key": "bilibili", "label": "B站直播", "description": "直播间 ID 和 SESSDATA"},
            {"key": "host", "label": "AI主播", "description": "主播回复参数和模型"},
            {"key": "llm", "label": "通用LLM", "description": "通用大语言模型配置"},
            {"key": "tts", "label": "语音合成", "description": "TTS 语音输出配置"},
            {"key": "volcano", "label": "火山引擎", "description": "火山引擎 TTS 凭证"},
            {"key": "game", "label": "游戏AI", "description": "游戏 AI 行为参数"},
            {"key": "easyvtuber", "label": "数字人", "description": "Live2D 渲染和输入配置"},
            {"key": "ai", "label": "AI行为", "description": "记忆、历史、轮询间隔"},
            {"key": "messaging", "label": "消息调度", "description": "优先级、队列、频率限制"},
            {"key": "music_config", "label": "音乐验证", "description": "点歌验证参数"},
            {"key": "up_videos", "label": "视频采集", "description": "UP主视频采集频率"},
            {"key": "announcement", "label": "公告", "description": "直播间跑马灯公告"},
            {"key": "admin", "label": "管理员", "description": "管理员身份标识"},
            {"key": "embedding", "label": "向量模型", "description": "Embedding / 向量检索模型配置"},
        ]
    }


# ---- EasyVtuber 独立端点 (保留兼容) ----

@router.get("/easyvtuber", response_model=EasyVtuberConfig)
async def get_easyvtuber_config():
    return EasyVtuberConfig(
        enabled=config.easyvtuber_enabled,
        character=config.easyvtuber_character,
        input=EasyVtuberInputConfig(
            type=config.easyvtuber_input_type,
            osf_address=config.easyvtuber_osf_address,
            mouse_range=config.easyvtuber_mouse_range,
        ),
        model=EasyVtuberModelConfig(
            version=config.easyvtuber_model_version,
            precision=config.easyvtuber_model_precision,
            separable=config.easyvtuber_model_separable,
            use_tensorrt=config.easyvtuber_use_tensorrt,
            use_eyebrow=config.easyvtuber_use_eyebrow,
        ),
        performance=EasyVtuberPerformanceConfig(
            frame_rate=config.easyvtuber_frame_rate,
            interpolation=config.easyvtuber_interpolation,
            super_resolution=config.easyvtuber_super_resolution,
            ram_cache=config.easyvtuber_ram_cache,
            vram_cache=config.easyvtuber_vram_cache,
        ),
        output=EasyVtuberOutputConfig(
            websocket=EasyVtuberWebSocketConfig(
                enabled=config.easyvtuber_ws_enabled,
                port=config.easyvtuber_ws_port,
                host=config.easyvtuber_ws_host,
            )
        ),
    )


@router.put("/easyvtuber", response_model=EasyVtuberConfig)
async def update_easyvtuber_config(config_data: EasyVtuberConfig):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        data["easyvtuber"] = config_data.model_dump()

        _atomic_write_yaml(data)

        config._load()

        return config_data

    except Exception as e:
        logger.error(f"更新 EasyVtuber 配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新配置失败: {e}")


@router.get("/easyvtuber/characters")
async def list_characters():
    from apps.easyvtuber import EASYVTUBER_DIR

    images_dir = EASYVTUBER_DIR / "data" / "images"
    characters = []

    if images_dir.exists():
        for f in sorted(images_dir.glob("*.png")):
            characters.append({
                "name": f.stem,
            })

    return {"characters": characters}


@router.post("/easyvtuber/open-images")
async def open_images_folder():
    """打开数字人图片文件夹（仅 Windows）"""
    import subprocess

    from apps.easyvtuber import EASYVTUBER_DIR
    images_dir = EASYVTUBER_DIR / "data" / "images"
    if not images_dir.exists():
        images_dir.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(["explorer", str(images_dir)])
    return {"success": True, "path": str(images_dir)}
