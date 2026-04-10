"""音乐模块数据模型"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MusicStatus(str, Enum):
    PENDING = "pending"
    PLAYING = "playing"
    COMPLETED = "completed"
    FAILED = "failed"


class MusicItem(BaseModel):
    id: str = Field(..., description="音乐项唯一ID")
    bvid: str = Field(..., description="B站视频BV号")
    title: str = Field(..., description="视频标题")
    upName: str = Field(..., description="UP主名称")
    upFace: Optional[str] = Field(None, description="UP主头像URL")
    duration: int = Field(..., description="视频时长(秒)")
    audioUrl: str = Field(..., description="音频直链")
    coverUrl: str = Field(..., description="视频封面URL")
    status: MusicStatus = Field(default=MusicStatus.PENDING, description="播放状态")
    requestedBy: str = Field(..., description="点歌用户")
    requestedAt: datetime = Field(default_factory=datetime.now, description="点歌时间")
    playedAt: Optional[datetime] = Field(None, description="开始播放时间")


class MusicQueueResponse(BaseModel):
    current: Optional[MusicItem] = Field(None, description="当前播放")
    queue: list[MusicItem] = Field(default_factory=list, description="播放队列")
    total: int = Field(0, description="队列总数")


class DanmakuInterceptResult(BaseModel):
    isMusicRequest: bool = Field(False, description="是否为点歌请求")
    musicItem: Optional[MusicItem] = Field(None, description="解析出的音乐项")
    rawText: str = Field(..., description="原始弹幕文本")
    error: Optional[str] = Field(None, description="错误信息")


class QueueStats(BaseModel):
    totalPlayed: int = Field(0, description="已播放总数")
    totalQueue: int = Field(0, description="当前队列数")
    current: Optional[MusicItem] = Field(None, description="当前播放")


class MusicLibraryItem(BaseModel):
    id: str = Field(..., description="音乐库项唯一ID")
    bvid: str = Field(..., description="B站视频BV号")
    title: str = Field(..., description="视频标题")
    upName: str = Field(..., description="UP主名称")
    upFace: Optional[str] = Field(None, description="UP主头像URL")
    duration: int = Field(..., description="视频时长(秒)")
    coverUrl: str = Field(..., description="视频封面URL")
    enabled: bool = Field(default=True, description="是否启用")


class MusicLibraryResponse(BaseModel):
    items: list[MusicLibraryItem] = Field(default_factory=list, description="音乐库列表")
    total: int = Field(0, description="音乐库总数")
