"""数据库连接和表定义"""

import json
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from apps.config import config


engine = create_async_engine(config.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class UserProfileDB(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), default="")
    danmaku_count: Mapped[int] = mapped_column(Integer, default=0)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0)
    key_topics: Mapped[str] = mapped_column(Text, default="[]")
    impression: Mapped[str] = mapped_column(Text, default="")
    long_term_memory: Mapped[str] = mapped_column(Text, default="")
    recent_messages: Mapped[str] = mapped_column(Text, default="[]")
    last_danmaku: Mapped[str] = mapped_column(Text, default="")
    last_interaction: Mapped[float] = mapped_column(Integer, default=0)
    last_summary_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Integer, default=0)


class UpVideo(Base):
    __tablename__ = "up_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bvid: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    up_name: Mapped[str] = mapped_column(String(100))
    up_uid: Mapped[int] = mapped_column(BigInteger, index=True)
    duration: Mapped[int] = mapped_column(Integer, default=0)
    cover_url: Mapped[str] = mapped_column(String(500), default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class PlaylistItem(Base):
    __tablename__ = "playlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bvid: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    artist: Mapped[str] = mapped_column(String(100), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    async with async_session() as session:
        yield session


@asynccontextmanager
async def get_db_session():
    async with async_session() as session:
        yield session
