"""Authoritative SQLite database and relational models."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
    func,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from apps.config import config
from apps.storage.migrations import prepare_database

engine = create_async_engine(config.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA busy_timeout = 10000")
    cursor.close()


class Base(DeclarativeBase):
    pass


class UserProfileDB(Base):
    """Current viewer profile; long-term facts live in memory atoms."""

    __tablename__ = "viewer_profiles"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), default="")
    danmaku_count: Mapped[int] = mapped_column(Integer, default=0)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0)
    key_topics: Mapped[str] = mapped_column(Text, default="[]")
    impression: Mapped[str] = mapped_column(Text, default="")
    last_danmaku: Mapped[str] = mapped_column(Text, default="")
    last_interaction: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    last_summary_count: Mapped[int] = mapped_column(Integer, default=0)
    last_summarized_interaction_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=0.0)


class ViewerInteractionDB(Base):
    __tablename__ = "viewer_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("viewer_profiles.user_id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)


class ViewerSummaryBatchDB(Base):
    """Durable LLM result used to make an interaction batch idempotent."""

    __tablename__ = "viewer_summary_batches"

    source_group_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("viewer_profiles.user_id", ondelete="CASCADE"), index=True
    )
    first_interaction_id: Mapped[int] = mapped_column(Integer)
    last_interaction_id: Mapped[int] = mapped_column(Integer)
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=0.0)


class TrustedUploaderDB(Base):
    __tablename__ = "trusted_uploaders"

    uid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class UpVideo(Base):
    __tablename__ = "up_video_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bvid: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    up_name: Mapped[str] = mapped_column(String(100))
    up_uid: Mapped[int] = mapped_column(BigInteger, index=True)
    duration: Mapped[int] = mapped_column(Integer, default=0)
    cover_url: Mapped[str] = mapped_column(String(500), default="")
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class PlaylistItem(Base):
    __tablename__ = "playlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bvid: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    artist: Mapped[str] = mapped_column(String(100), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


async def init_db() -> None:
    prepare_database(config.app_db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    async with async_session() as session:
        yield session


@asynccontextmanager
async def get_db_session():
    async with async_session() as session:
        yield session
