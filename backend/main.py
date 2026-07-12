"""FastAPI 应用入口"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.ai.game_router import router as game_router
from apps.ai.memory_router import router as memory_router
from apps.ai.router import router as ai_router
from apps.config import config
from apps.config_router import router as config_router
from apps.easyvtuber.router import router as easyvtuber_router
from apps.exceptions import AppException
from apps.live.bilibili.router import router as bilibili_router
from apps.live.music.router import router as music_router
from apps.test_router import router as test_router
from services.nginx_service import get_nginx_service, start_nginx, stop_nginx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    from apps.storage.secrets import migrate_legacy_secrets

    migrated_secrets = migrate_legacy_secrets(Path(__file__).parent / "config.yaml")
    if migrated_secrets:
        config._load()
        logger.info("Migrated %s legacy storage/security config entries", migrated_secrets)
    from apps.ai.admin_commands import get_admin_handler
    from apps.ai.memory import (
        init_user_profiles,
        save_all_profiles,
        start_summary_scheduler,
        stop_summary_scheduler,
    )
    from apps.ai.memory.engine import init_memory_engine
    from apps.easyvtuber import get_easyvtuber_manager
    from apps.live.music.client import BilibiliMusicClient
    from apps.live.music.library import get_playlist_manager
    from apps.live.music.queue import get_music_queue
    from apps.live.music.up_videos import get_up_video_manager
    from apps.live.room_session import get_room_session_manager

    queue = get_music_queue()
    logger.info(f"Music queue initialized: max_history={queue._history.maxlen}, max_queue={queue._queue.maxlen}")

    up_manager = get_up_video_manager()
    await up_manager.initialize()

    await init_user_profiles()

    # 初始化记忆引擎 (长期记忆 + 知识图谱)
    await init_memory_engine()
    start_summary_scheduler()
    logger.info("MemoryEngine initialized")

    easyvtuber_manager = get_easyvtuber_manager()
    await easyvtuber_manager.start()

    admin_handler = get_admin_handler()

    def on_face_mode_change(mode):
        easyvtuber_manager.set_face_mode(mode.value)

    admin_handler.register_face_mode_callback(on_face_mode_change)
    easyvtuber_manager.set_face_mode(admin_handler.get_state().face_mode.value)

    from core.websocket import manager as ws_manager

    async def broadcast_music_control(action: str, data: dict = None):
        message = {"type": "music_control", "data": {"action": action, **(data or {})}}
        context = get_room_session_manager().active_context
        if context is not None:
            message["context"] = context.to_dict()
            await ws_manager.send_message(context.room_id, message)

    def on_volume_change(volume: float):
        queue.set_volume(volume)
        asyncio.create_task(broadcast_music_control("volume", {"volume": volume}))

    def on_pause_change(is_paused: bool):
        if is_paused:
            asyncio.create_task(queue.stop_auto_play())
        else:
            asyncio.create_task(queue.start_auto_play())
        asyncio.create_task(broadcast_music_control("pause", {"is_paused": is_paused}))

    async def on_next_track():
        logger.info("[Next Track] 开始切换下一首")
        current = await queue.get_current()
        if current:
            logger.info(f"[Next Track] 当前播放: {current.title} (bvid={current.bvid})")
        skipped = await queue.skip()
        if skipped:
            logger.info(f"[Next Track] 已跳过: {skipped.title}")
        new_current = await queue.get_current()
        if new_current:
            logger.info(f"[Next Track] 即将播放: {new_current.title} (bvid={new_current.bvid}), audioUrl={'有' if new_current.audioUrl else '无'}")
        else:
            logger.info("[Next Track] 队列为空，尝试从播放列表随机选取")
            library = get_playlist_manager()
            picked = await library.random_pick()
            if picked:
                logger.info(f"[Next Track] 从播放列表选取: {picked.title} ({picked.bvid})")
                client = BilibiliMusicClient()
                full_item = await client.get_music_item_with_overrides(
                    picked.bvid, "system",
                    title=picked.title,
                    artist=picked.upName
                )
                if full_item:
                    await queue.add(full_item)
                    new_current = await queue.next()
                    if new_current:
                        logger.info(f"[Next Track] 随机选取成功，开始播放: {new_current.title}")
                    else:
                        logger.error("[Next Track] 随机选取后获取歌曲失败")
                else:
                    logger.error(f"[Next Track] 获取歌曲信息失败: {picked.bvid}")
            else:
                logger.info("[Next Track] 播放列表为空")
        await broadcast_music_control("next")

    async def on_remove_track():
        bvid = await queue.skip_and_disable_current()
        if bvid:
            library = get_playlist_manager()
            await library.set_enabled(bvid, False)
            logger.info(f"[Remove Track] 已禁用: {bvid}")
        new_current = await queue.get_current()
        if not new_current:
            logger.info("[Remove Track] 队列为空，尝试从播放列表随机选取")
            library = get_playlist_manager()
            picked = await library.random_pick()
            if picked:
                logger.info(f"[Remove Track] 从播放列表选取: {picked.title} ({picked.bvid})")
                client = BilibiliMusicClient()
                full_item = await client.get_music_item_with_overrides(
                    picked.bvid, "system",
                    title=picked.title,
                    artist=picked.upName
                )
                if full_item:
                    await queue.add(full_item)
                    new_current = await queue.next()
                    if new_current:
                        logger.info(f"[Remove Track] 随机选取成功，开始播放: {new_current.title}")
                else:
                    logger.error(f"[Remove Track] 获取歌曲信息失败: {picked.bvid}")
            else:
                logger.info("[Remove Track] 播放列表为空")
        await broadcast_music_control("rm")

    admin_handler.register_volume_change_callback(on_volume_change)
    admin_handler.register_pause_change_callback(on_pause_change)
    admin_handler.register_next_track_callback(lambda: asyncio.create_task(on_next_track()))
    admin_handler.register_remove_track_callback(lambda: asyncio.create_task(on_remove_track()))

    # 启动主播 Graph（弹幕轮询 + 消息队列消费），确保弹幕能走到 LLM
    from apps.ai.host_graph import HostGraph
    host_graph = HostGraph()
    await host_graph.start()
    logger.info("主播 Graph 启动成功（弹幕处理流水线就绪）")

    if config.bilibili_room_id > 0:
        try:
            await get_room_session_manager().activate(config.bilibili_room_id)
        except Exception as e:
            logger.error("Bilibili room startup failed: %s", e, exc_info=True)

    await start_nginx()

    if config.game_enabled:
        from apps.ai.game_manager import get_game_manager
        from apps.ai.mcp.games.registry import create_mcp_game
        game_manager = get_game_manager()

        def on_sleep_mute(state_dict: dict):
            if state_dict.get("is_sleeping"):
                game_manager.mute()
            else:
                game_manager.unmute()

        async def on_mcp_change(enabled: bool):
            if enabled:
                if game_manager.is_running:
                    return
                try:
                    adapter = create_mcp_game(
                        config.game_id,
                        mcp_url=config.game_mcp_url,
                        game_config=config.game_config,
                    )
                except ValueError as exc:
                    logger.error("游戏适配器配置无效: %s", exc)
                    return
                healthy = await adapter.health_check()
                if not healthy:
                    logger.warning(f"MCP 服务不可用: {config.game_mcp_url}，无法启动游戏AI")
                    return
                game_manager.configure_single_game(adapter)
                await game_manager.start()
                logger.info("游戏AI已通过 /mcp 1 启动")
            else:
                if not game_manager.is_running:
                    return
                await game_manager.stop()
                logger.info("游戏AI已通过 /mcp 0 停止")

        admin_handler.register_state_change_callback(on_sleep_mute)
        admin_handler.register_mcp_change_callback(lambda e: asyncio.create_task(on_mcp_change(e)))
        logger.info("游戏集成模块已就绪（可通过 /mcp 1 或 /game/start 启动）")

    yield

    logger.info("Application shutting down...")
    await get_room_session_manager().stop()
    await stop_summary_scheduler()
    await save_all_profiles()

    # 关闭记忆引擎
    try:
        from apps.ai.memory.engine import get_memory_engine
        engine = get_memory_engine()
        await engine.shutdown()
    except Exception as e:
        logger.warning(f"MemoryEngine shutdown error: {e}")

    await host_graph.stop()
    await queue.stop_auto_play()
    await easyvtuber_manager.stop()
    await stop_nginx()

    if config.game_enabled:
        from apps.ai.game_manager import get_game_manager
        game_manager = get_game_manager()
        if game_manager.is_running:
            await game_manager.stop()
            logger.info("游戏集成服务已停止")


app = FastAPI(
    title="feinaLive Backend",
    description="飞娜直播间后端服务",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bilibili_router, prefix="/bilibili", tags=["Bilibili"])
app.include_router(music_router, prefix="/music", tags=["Music"])
app.include_router(config_router, tags=["Config"])
app.include_router(ai_router, tags=["AI"])
app.include_router(memory_router, tags=["AI Memory"])
app.include_router(game_router, tags=["Game"])
app.include_router(easyvtuber_router, tags=["Avatar"])
app.include_router(test_router, tags=["Test"])

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    logger.error(f"AppException: {exc.message} (code={exc.code})")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "code": exc.code,
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "服务器内部错误",
            "code": "INTERNAL_ERROR",
        }
    )


@app.get("/")
async def root():
    return {"message": "feinaLive Backend API", "version": "0.1.0"}


@app.get("/health")
async def health():
    from apps.ai.messaging.queue import get_message_queue
    queue = get_message_queue()
    queue_stats = queue.get_stats()

    components = {"app": "healthy", "message_queue": "healthy"}
    if queue_stats.get("muted"):
        components["message_queue"] = "muted"

    overall = "healthy" if all(v in ("healthy", "muted") for v in components.values()) else "degraded"

    return {
        "status": overall,
        "components": components,
        "message_queue": queue_stats,
    }


@app.get("/stream/status")
async def stream_status():
    nginx = get_nginx_service()
    return {
        "nginx_running": nginx.is_running(),
        "urls": nginx.get_stream_urls() if nginx.is_running() else None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9191, access_log=False)
