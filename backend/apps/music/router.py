"""音乐模块API路由"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from apps.music.models import (
    MusicItem,
    MusicQueueResponse,
    MusicLibraryItem,
    MusicLibraryResponse,
    QueueStats,
)
from apps.music.queue import get_music_queue
from apps.music.library import get_playlist_manager
from apps.music.up_videos import get_up_video_manager
from apps.music.client import BilibiliMusicClient

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/proxy/audio")
async def proxy_audio(url: str):
    headers = {
        "Referer": "https://www.bilibili.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            req = client.build_request("GET", url, headers=headers)
            response = await client.send(req, stream=True)
            return StreamingResponse(
                response.aiter_raw(),
                headers=dict(response.headers),
                media_type="audio/mp4",
            )
        except Exception as e:
            logger.error(f"代理音频失败: {e}")
            raise HTTPException(status_code=502, detail="音频代理失败")


@router.get("/queue", response_model=MusicQueueResponse)
async def get_queue():
    queue = get_music_queue()
    current = await queue.get_current()
    queue_list = await queue.get_queue()
    return MusicQueueResponse(
        current=current,
        queue=queue_list,
        total=len(queue_list),
    )


@router.get("/stats", response_model=QueueStats)
async def get_stats():
    queue = get_music_queue()
    return await queue.get_stats()


@router.get("/current")
async def get_current():
    queue = get_music_queue()
    current = await queue.get_current()
    if not current:
        raise HTTPException(status_code=404, detail="当前没有播放")
    return current


@router.post("/next")
async def play_next() -> Optional[MusicItem]:
    queue = get_music_queue()
    music_item = await queue.next()
    if not music_item:
        library = get_playlist_manager()
        picked = await library.random_pick()
        if picked:
            client = BilibiliMusicClient()
            full_item = await client.get_music_item(picked.bvid, "system")
            if full_item:
                await queue.add(full_item)
                music_item = await queue.next()
    return music_item


@router.post("/skip")
async def skip_current() -> Optional[MusicItem]:
    queue = get_music_queue()
    return await queue.skip()


@router.delete("/queue/{item_id}")
async def remove_from_queue(item_id: str):
    queue = get_music_queue()
    removed = await queue.remove(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="未找到该音乐项")
    return {"message": "已从队列移除"}


@router.delete("/queue")
async def clear_queue():
    queue = get_music_queue()
    count = await queue.clear()
    return {"message": f"已清空队列，共移除 {count} 首"}


@router.post("/add/{bvid}")
async def add_by_bvid(bvid: str, requestedBy: str = "admin"):
    client = BilibiliMusicClient()
    music_item = await client.get_music_item(bvid, requestedBy)
    if not music_item:
        raise HTTPException(status_code=404, detail="获取音乐失败，视频可能不存在")
    queue = get_music_queue()
    await queue.add(music_item)
    return music_item


@router.get("/history")
async def get_history():
    queue = get_music_queue()
    return await queue.get_history()


@router.get("/library", response_model=MusicLibraryResponse)
async def get_library():
    library = get_playlist_manager()
    return await library.get_all()


@router.post("/library/{bvid}")
async def add_to_library(bvid: str):
    library = get_playlist_manager()
    item = await library.add_from_bv(bvid)
    if not item:
        raise HTTPException(status_code=404, detail="获取视频信息失败")
    return item


@router.delete("/library/{bvid}")
async def remove_from_library(bvid: str):
    library = get_playlist_manager()
    removed = await library.remove(bvid)
    if not removed:
        raise HTTPException(status_code=404, detail="音乐库中不存在该BV号")
    return {"message": "已从音乐库移除"}


@router.patch("/library/{bvid}/enabled")
async def set_library_enabled(bvid: str, enabled: bool = True):
    library = get_playlist_manager()
    success = await library.set_enabled(bvid, enabled)
    if not success:
        raise HTTPException(status_code=404, detail="音乐库中不存在该BV号")
    return {"message": f"已设置 {bvid} 启用状态为 {enabled}"}


@router.post("/library/init")
async def init_library_with_default():
    library = get_playlist_manager()
    await library.initialize()
    return {"message": "音乐库初始化完成"}


@router.post("/up-videos/refresh")
async def refresh_up_videos():
    manager = get_up_video_manager()
    await manager._auto_refresh()
    return {"message": "UP主视频刷新完成"}


@router.get("/up-videos/search")
async def search_up_videos(keyword: str):
    manager = get_up_video_manager()
    await manager.ensure_fetched()
    results = await manager.search(keyword)
    return {
        "keyword": keyword,
        "count": len(results),
        "results": [
            {
                "bvid": v.bvid,
                "title": v.title,
                "upName": v.upName,
                "duration": v.duration,
                "coverUrl": v.coverUrl,
            }
            for v in results[:10]
        ]
    }
