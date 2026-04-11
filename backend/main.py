"""FastAPI 应用入口"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from apps.bilibili.router import router as bilibili_router
from apps.music.router import router as music_router
from apps.config_router import router as config_router
from apps.exceptions import AppException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    from apps.music.queue import get_music_queue
    from apps.music.up_videos import get_up_video_manager
    from apps.easyvtuber import get_easyvtuber_manager
    
    queue = get_music_queue()
    logger.info(f"Music queue initialized: max_history={queue._history.maxlen}, max_queue={queue._queue.maxlen}")
    
    up_manager = get_up_video_manager()
    await up_manager.initialize()
    
    easyvtuber_manager = get_easyvtuber_manager()
    await easyvtuber_manager.start()
    
    yield
    
    logger.info("Application shutting down...")
    await queue.stop_auto_play()
    await easyvtuber_manager.stop()


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
