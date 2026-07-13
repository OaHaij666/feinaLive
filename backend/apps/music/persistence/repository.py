from __future__ import annotations

import hashlib
import json
import random

from sqlalchemy import delete, select

from apps.db import get_db_session, init_db
from apps.music.models import ClassificationDecision, QueueEntry, QueueEntryStatus, Track
from apps.music.persistence.models import (
    MusicClassificationDB,
    MusicLibraryEntryDB,
    MusicPlaybackSettingDB,
    MusicPlayHistoryDB,
    MusicQueueEntryDB,
    MusicRequestDB,
    MusicTrackDB,
)


class MusicRepository:
    async def initialize(self) -> None:
        await init_db()

    @staticmethod
    def fingerprint(track: Track) -> str:
        value = json.dumps(
            {
                "title": track.title,
                "artists": track.artists,
                "duration": track.duration_seconds,
                "metadata": track.metadata,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    async def save_track(self, track: Track) -> Track:
        fingerprint = self.fingerprint(track)
        async with get_db_session() as session:
            result = await session.execute(
                select(MusicTrackDB).where(
                    MusicTrackDB.provider == track.provider,
                    MusicTrackDB.source_id == track.source_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = MusicTrackDB(id=track.id, provider=track.provider, source_id=track.source_id)
                session.add(row)
            else:
                track.id = row.id
            row.title = track.title
            row.artists_json = json.dumps(track.artists, ensure_ascii=False)
            row.duration_seconds = track.duration_seconds
            row.cover_url = track.cover_url
            row.metadata_json = json.dumps(track.metadata, ensure_ascii=False)
            row.fingerprint = fingerprint
            await session.commit()
        return track

    async def get_track(self, track_id: str) -> Track | None:
        async with get_db_session() as session:
            row = await session.get(MusicTrackDB, track_id)
            return _track_from_row(row) if row else None

    async def get_track_by_source(self, provider: str, source_id: str) -> Track | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(MusicTrackDB).where(
                    MusicTrackDB.provider == provider,
                    MusicTrackDB.source_id == source_id,
                )
            )
            row = result.scalar_one_or_none()
            return _track_from_row(row) if row else None

    async def get_classification(self, track: Track) -> ClassificationDecision | None:
        fingerprint = self.fingerprint(track)
        async with get_db_session() as session:
            result = await session.execute(
                select(MusicClassificationDB)
                .where(
                    MusicClassificationDB.provider == track.provider,
                    MusicClassificationDB.source_id == track.source_id,
                    MusicClassificationDB.fingerprint == fingerprint,
                )
                .order_by(MusicClassificationDB.manual.desc(), MusicClassificationDB.id.desc())
            )
            row = result.scalars().first()
            return ClassificationDecision.model_validate_json(row.decision_json) if row else None

    async def save_classification(
        self, track: Track, decision: ClassificationDecision, *, manual: bool = False
    ) -> None:
        fingerprint = self.fingerprint(track)
        async with get_db_session() as session:
            result = await session.execute(
                select(MusicClassificationDB).where(
                    MusicClassificationDB.provider == track.provider,
                    MusicClassificationDB.source_id == track.source_id,
                    MusicClassificationDB.fingerprint == fingerprint,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = MusicClassificationDB(
                    provider=track.provider,
                    source_id=track.source_id,
                    fingerprint=fingerprint,
                )
                session.add(row)
            row.decision_json = decision.model_dump_json()
            row.manual = manual
            await session.commit()

    async def add_library(self, track: Track, *, manually_approved: bool = True) -> None:
        track = await self.save_track(track)
        async with get_db_session() as session:
            row = await session.get(MusicLibraryEntryDB, track.id)
            if row is None:
                row = MusicLibraryEntryDB(track_id=track.id)
                session.add(row)
            row.enabled = True
            row.manually_approved = manually_approved
            await session.commit()

    async def set_library_enabled(self, track_id: str, enabled: bool) -> bool:
        async with get_db_session() as session:
            row = await session.get(MusicLibraryEntryDB, track_id)
            if row is None:
                return False
            row.enabled = enabled
            await session.commit()
            return True

    async def is_library_track(self, track: Track) -> bool:
        stored = await self.get_track_by_source(track.provider, track.source_id)
        if stored is None:
            return False
        async with get_db_session() as session:
            row = await session.get(MusicLibraryEntryDB, stored.id)
            return bool(row and row.enabled and row.manually_approved)

    async def list_library(self) -> list[Track]:
        async with get_db_session() as session:
            result = await session.execute(
                select(MusicTrackDB)
                .join(MusicLibraryEntryDB, MusicLibraryEntryDB.track_id == MusicTrackDB.id)
                .where(MusicLibraryEntryDB.enabled.is_(True))
                .order_by(MusicTrackDB.title)
            )
            return [_track_from_row(row) for row in result.scalars().all()]

    async def random_library_track(self) -> Track | None:
        tracks = await self.list_library()
        return random.choice(tracks) if tracks else None

    async def save_request(
        self,
        *,
        request_id: str,
        requested_by: str,
        query: str,
        provider: str,
        source_id: str,
        track_id: str | None,
        status: str,
        error_code: str = "",
    ) -> None:
        async with get_db_session() as session:
            row = await session.get(MusicRequestDB, request_id)
            if row is None:
                row = MusicRequestDB(
                    id=request_id,
                    requested_by=requested_by,
                    query=query,
                    provider=provider,
                )
                session.add(row)
            row.source_id = source_id
            row.track_id = track_id
            row.status = status
            row.error_code = error_code
            await session.commit()

    async def replace_runtime_state(
        self, current: QueueEntry | None, queue: list[QueueEntry], paused: bool, volume: float
    ) -> None:
        entries = ([current] if current else []) + queue
        for entry in entries:
            await self.save_track(entry.track)
        async with get_db_session() as session:
            await session.execute(delete(MusicQueueEntryDB))
            for position, entry in enumerate(entries):
                session.add(
                    MusicQueueEntryDB(
                        id=entry.id,
                        track_id=entry.track.id,
                        requested_by=entry.requested_by,
                        request_id=entry.request_id,
                        status=entry.status.value,
                        position=position,
                        requested_at=entry.requested_at,
                        started_at=entry.started_at,
                        finished_at=entry.finished_at,
                        failure_reason=entry.failure_reason,
                    )
                )
            setting = await session.get(MusicPlaybackSettingDB, 1)
            if setting is None:
                setting = MusicPlaybackSettingDB(id=1)
                session.add(setting)
            setting.paused = paused
            setting.volume = volume
            await session.commit()

    async def append_history(self, entry: QueueEntry) -> None:
        await self.save_track(entry.track)
        async with get_db_session() as session:
            exists = await session.execute(
                select(MusicPlayHistoryDB.id).where(
                    MusicPlayHistoryDB.queue_entry_id == entry.id
                )
            )
            if exists.scalar_one_or_none() is not None:
                return
            session.add(
                MusicPlayHistoryDB(
                    queue_entry_id=entry.id,
                    track_id=entry.track.id,
                    requested_by=entry.requested_by,
                    status=entry.status.value,
                    requested_at=entry.requested_at,
                    started_at=entry.started_at,
                    finished_at=entry.finished_at,
                    failure_reason=entry.failure_reason,
                )
            )
            await session.commit()

    async def load_runtime_state(self) -> tuple[QueueEntry | None, list[QueueEntry], bool, float]:
        async with get_db_session() as session:
            result = await session.execute(
                select(MusicQueueEntryDB, MusicTrackDB)
                .join(MusicTrackDB, MusicTrackDB.id == MusicQueueEntryDB.track_id)
                .order_by(MusicQueueEntryDB.position)
            )
            entries: list[QueueEntry] = []
            for queue_row, track_row in result.all():
                entries.append(
                    QueueEntry(
                        id=queue_row.id,
                        track=_track_from_row(track_row),
                        requested_by=queue_row.requested_by,
                        request_id=queue_row.request_id,
                        status=QueueEntryStatus(queue_row.status),
                        requested_at=queue_row.requested_at,
                        started_at=queue_row.started_at,
                        finished_at=queue_row.finished_at,
                        failure_reason=queue_row.failure_reason,
                    )
                )
            setting = await session.get(MusicPlaybackSettingDB, 1)
            paused = bool(setting.paused) if setting else False
            volume = float(setting.volume) if setting else 1.0
        current = entries[0] if entries and entries[0].status in {
            QueueEntryStatus.PLAYING,
            QueueEntryStatus.PAUSED,
        } else None
        queue = entries[1:] if current else entries
        return current, queue, paused, volume

    async def load_history(self, limit: int = 100) -> list[QueueEntry]:
        async with get_db_session() as session:
            result = await session.execute(
                select(MusicPlayHistoryDB, MusicTrackDB)
                .join(MusicTrackDB, MusicTrackDB.id == MusicPlayHistoryDB.track_id)
                .order_by(MusicPlayHistoryDB.id.desc())
                .limit(limit)
            )
            entries = [
                QueueEntry(
                    id=row.queue_entry_id,
                    track=_track_from_row(track),
                    requested_by=row.requested_by,
                    status=QueueEntryStatus(row.status),
                    requested_at=row.requested_at,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                    failure_reason=row.failure_reason,
                )
                for row, track in result.all()
            ]
        entries.reverse()
        return entries


def _track_from_row(row: MusicTrackDB) -> Track:
    return Track(
        id=row.id,
        provider=row.provider,
        source_id=row.source_id,
        title=row.title,
        artists=json.loads(row.artists_json or "[]"),
        duration_seconds=row.duration_seconds,
        cover_url=row.cover_url,
        metadata=json.loads(row.metadata_json or "{}"),
    )
