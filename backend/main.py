"""FastAPI 应用入口"""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from apps.live.bilibili.router import router as bilibili_router
from apps.live.music.router import router as music_router
from apps.config_router import router as config_router
from apps.ai.router import router as ai_router
from apps.easyvtuber.router import router as easyvtuber_router
from apps.test_router import router as test_router
from apps.exceptions import AppException
from apps.config import config
from services.nginx_service import start_nginx, stop_nginx, get_nginx_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    from apps.live.music.queue import get_music_queue
    from apps.live.music.up_videos import get_up_video_manager
    from apps.live.music.library import get_playlist_manager
    from apps.live.music.client import BilibiliMusicClient
    from apps.easyvtuber import get_easyvtuber_manager
    from apps.ai.admin_commands import get_admin_handler
    from apps.ai.memory import init_user_profiles, save_all_profiles

    queue = get_music_queue()
    logger.info(f"Music queue initialized: max_history={queue._history.maxlen}, max_queue={queue._queue.maxlen}")

    up_manager = get_up_video_manager()
    await up_manager.initialize()

    await init_user_profiles()

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
        target_rooms = set()
        target_rooms.add("test_room")
        if config.bilibili_room_id > 0:
            target_rooms.add(str(config.bilibili_room_id))
        if config.default_room_id > 0:
            target_rooms.add(str(config.default_room_id))
        for room_id in target_rooms:
            try:
                await ws_manager.send_message(room_id, message)
            except Exception:
                pass

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

    await start_nginx()

    yield

    logger.info("Application shutting down...")
    await save_all_profiles()
    await queue.stop_auto_play()
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
app.include_router(music_router, prefix="/music", tags=["Music"])
app.include_router(config_router, tags=["Config"])
app.include_router(ai_router, tags=["AI"])
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
    return {"status": "healthy"}


@app.get("/stream/status")
async def stream_status():
    nginx = get_nginx_service()
    return {
        "nginx_running": nginx.is_running(),
        "urls": nginx.get_stream_urls() if nginx.is_running() else None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
