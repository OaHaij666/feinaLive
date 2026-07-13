"""FastAPI 应用入口"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.agent.router import router as agent_router
from apps.ai.memory_router import router as memory_router
from apps.ai.router import router as ai_router
from apps.config import config
from apps.config_router import router as config_router
from apps.easyvtuber.router import router as easyvtuber_router
from apps.exceptions import AppException
from apps.live.bilibili.router import router as bilibili_router
from apps.music.router import router as music_router
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
    from apps.live.room_session import get_room_session_manager
    from apps.music.manager import get_music_manager

    music_manager = get_music_manager()
    await music_manager.initialize()

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

    def on_volume_change(volume: float):
        asyncio.create_task(music_manager.set_volume(volume))

    def on_pause_change(is_paused: bool):
        asyncio.create_task(music_manager.set_paused(is_paused))

    async def on_next_track():
        await music_manager.skip()

    async def on_remove_track():
        await music_manager.skip(remove_from_library=True)

    admin_handler.register_volume_change_callback(on_volume_change)
    admin_handler.register_pause_change_callback(on_pause_change)
    admin_handler.register_next_track_callback(lambda: asyncio.create_task(on_next_track()))
    admin_handler.register_remove_track_callback(lambda: asyncio.create_task(on_remove_track()))

    # 启动主播 Runtime（弹幕轮询 + 单一消息队列消费者）。
    from apps.ai.host_runtime import HostRuntime

    host_runtime = HostRuntime()
    await host_runtime.start()
    logger.info("主播 Runtime 启动成功（弹幕处理流水线就绪）")

    if config.bilibili_room_id > 0:
        try:
            await get_room_session_manager().activate(config.bilibili_room_id)
        except Exception as e:
            logger.error("Bilibili room startup failed: %s", e, exc_info=True)

    await start_nginx()

    from apps.agent.manager import get_agent_manager

    # Bind one immutable scenario snapshot for the lifetime of this process.
    agent_manager = get_agent_manager()
    if config.agent_enabled:

        def on_sleep_mute(state_dict: dict):
            if state_dict.get("is_sleeping"):
                agent_manager.mute()
            else:
                agent_manager.unmute()

        async def on_agent_change(enabled: bool):
            if enabled:
                if agent_manager.is_running:
                    return
                try:
                    healthy = await agent_manager.health_check()
                except RuntimeError as exc:
                    logger.error("启动场景配置无效: %s", exc)
                    return
                if not healthy:
                    logger.warning(f"场景能力不可用: {config.agent_mcp_url}，无法启动 Agent")
                    return
                await agent_manager.start()
                logger.info("Agent 已通过 /agent 1 启动")
            else:
                if not agent_manager.is_running:
                    return
                await agent_manager.stop()
                logger.info("Agent 已通过 /agent 0 停止")

        admin_handler.register_state_change_callback(on_sleep_mute)
        admin_handler.register_agent_change_callback(lambda e: asyncio.create_task(on_agent_change(e)))
        logger.info("AgentRuntime 已就绪（可通过 /agent 1 或 /agent/start 启动）")

    yield

    logger.info("Application shutting down...")
    await get_room_session_manager().stop()

    # Stop producers and consumers before their memory/output dependencies.
    from apps.agent.manager import get_agent_manager

    agent_manager = get_agent_manager()
    was_agent_running = agent_manager.is_running
    await agent_manager.shutdown()
    if was_agent_running:
        logger.info("AgentRuntime 已停止")

    await host_runtime.stop()
    await stop_summary_scheduler()
    await save_all_profiles()

    # 关闭记忆引擎
    try:
        from apps.ai.memory.engine import get_memory_engine
        engine = get_memory_engine()
        await engine.shutdown()
    except Exception as e:
        logger.warning(f"MemoryEngine shutdown error: {e}")

    await music_manager.shutdown()
    await easyvtuber_manager.stop()
    await stop_nginx()


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
app.include_router(music_router)
app.include_router(config_router, tags=["Config"])
app.include_router(ai_router, tags=["AI"])
app.include_router(memory_router, tags=["AI Memory"])
app.include_router(agent_router, tags=["Agent"])
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
