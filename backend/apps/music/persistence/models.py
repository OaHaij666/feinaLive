from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.db import Base


class MusicTrackDB(Base):
    __tablename__ = "music_tracks"
    __table_args__ = (UniqueConstraint("provider", "source_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(500))
    artists_json: Mapped[str] = mapped_column(Text, default="[]")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    cover_url: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class MusicClassificationDB(Base):
    __tablename__ = "music_classifications"
    __table_args__ = (UniqueConstraint("provider", "source_id", "fingerprint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(160), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    decision_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class MusicLibraryEntryDB(Base):
    __tablename__ = "music_library_entries"

    track_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("music_tracks.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class MusicRequestDB(Base):
    __tablename__ = "music_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    requested_by: Mapped[str] = mapped_column(String(160), index=True)
    query: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(160), default="")
    track_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    error_code: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)


class MusicQueueEntryDB(Base):
    __tablename__ = "music_queue_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("music_tracks.id"), index=True)
    requested_by: Mapped[str] = mapped_column(String(160), index=True)
    request_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(30), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    requested_at: Mapped[datetime] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_reason: Mapped[str] = mapped_column(Text, default="")


class MusicPlaybackSettingDB(Base):
    __tablename__ = "music_playback_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    volume: Mapped[float] = mapped_column(Float, default=1.0)
    ducking_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class MusicPlayHistoryDB(Base):
    __tablename__ = "music_play_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    queue_entry_id: Mapped[str] = mapped_column(String(36), index=True)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("music_tracks.id"), index=True)
    requested_by: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_reason: Mapped[str] = mapped_column(Text, default="")
