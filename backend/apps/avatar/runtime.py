from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Protocol

from apps.config import config

from .schemas import AvatarConfig

logger = logging.getLogger(__name__)


class AvatarEngine(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def set_mouse_position(self, x: float, y: float) -> None: ...

    def set_audio_level(self, level: float) -> None: ...

    def set_speaking(self, speaking: bool) -> None: ...

    def set_browser_motion(self, enabled: bool) -> None: ...

    def latest_preview(self) -> bytes | None: ...

    def status(self) -> dict: ...


EngineFactory = Callable[[AvatarConfig], AvatarEngine]


def _default_engine_factory(settings: AvatarConfig) -> AvatarEngine:
    from avatar_engine.runner import FeinaAvatarEngine

    return FeinaAvatarEngine(settings.to_engine_config())


class AvatarRuntime:
    def __init__(self, engine_factory: EngineFactory | None = None) -> None:
        self._engine_factory = engine_factory or _default_engine_factory
        self._lock = asyncio.Lock()
        self._settings = AvatarConfig()
        self._engine: AvatarEngine | None = None
        self._boot_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._state = "stopped"
        self._error = ""
        self._browser_motion = False
        self._active_reply_id = ""
        self._last_audio_seq = -1
        self._last_audio_time_ms = -1.0
        self._last_audio_received_at = 0.0

    @property
    def settings(self) -> AvatarConfig:
        return self._settings

    @property
    def is_running(self) -> bool:
        return self._state == "running"

    async def start(self, settings: AvatarConfig | None = None) -> None:
        async with self._lock:
            if self._state in {"starting", "running"}:
                return
            self._settings = settings or AvatarConfig.model_validate(config.avatar_config)
            self._error = ""
            self._browser_motion = self._settings.motion.source == "browser"
            if not self._settings.enabled:
                self._state = "disabled"
                return
            self._state = "starting"
            self._engine = self._engine_factory(self._settings)
            self._boot_task = asyncio.create_task(
                self._boot_engine(self._engine),
                name="avatar-engine-boot",
            )
            self._watchdog_task = asyncio.create_task(
                self._watchdog(),
                name="avatar-runtime-watchdog",
            )

    async def stop(self) -> None:
        async with self._lock:
            engine = self._engine
            boot_task = self._boot_task
            watchdog = self._watchdog_task
            self._engine = None
            self._boot_task = None
            self._watchdog_task = None
            self._state = "stopping" if engine is not None else "stopped"
            self._reset_lip_state()
        if watchdog:
            watchdog.cancel()
            await asyncio.gather(watchdog, return_exceptions=True)
        if engine is not None:
            await asyncio.to_thread(engine.stop)
        if boot_task and boot_task is not asyncio.current_task():
            await asyncio.gather(boot_task, return_exceptions=True)
        self._state = "stopped"

    def set_face_mode(self, mode: str) -> None:
        source = self._settings.motion.source
        if source == "browser":
            self._browser_motion = True
        elif source == "hybrid":
            self._browser_motion = (
                mode == "mouse_tracking" and self._settings.motion.allow_browser_control
            )
        else:
            self._browser_motion = False
        if self._engine is not None:
            self._engine.set_browser_motion(self._browser_motion)

    def set_mouse_position(self, x: float, y: float) -> None:
        if self.is_running and self._browser_motion and self._engine is not None:
            self._engine.set_mouse_position(x, y)

    def begin_lip_sync(self, reply_id: str) -> None:
        if not reply_id or self._settings.lip_sync.source == "disabled":
            return
        self._active_reply_id = reply_id
        self._last_audio_seq = -1
        self._last_audio_time_ms = -1.0
        self._last_audio_received_at = time.monotonic()

    def update_audio(
        self,
        reply_id: str,
        seq: int,
        audio_time_ms: float,
        level: float,
        speaking: bool,
    ) -> bool:
        if (
            not self.is_running
            or reply_id != self._active_reply_id
            or seq <= self._last_audio_seq
            or audio_time_ms < self._last_audio_time_ms
            or self._engine is None
        ):
            return False
        self._last_audio_seq = seq
        self._last_audio_time_ms = audio_time_ms
        self._last_audio_received_at = time.monotonic()
        self._engine.set_audio_level(max(0.0, min(float(level), 1.0)))
        self._engine.set_speaking(bool(speaking))
        return True

    def end_lip_sync(self, reply_id: str) -> None:
        if reply_id != self._active_reply_id:
            return
        if self._engine is not None:
            self._engine.set_audio_level(0.0)
            self._engine.set_speaking(False)
        self._reset_lip_state()

    def latest_preview(self) -> bytes | None:
        return self._engine.latest_preview() if self._engine is not None else None

    def status(self) -> dict:
        engine_status = self._engine.status() if self._engine is not None else {}
        return {
            "state": self._state,
            "running": self.is_running,
            "error": self._error or engine_status.get("error", ""),
            "character": self._settings.character,
            "renderer": self._settings.renderer.model_dump(mode="json"),
            "motion": {
                **self._settings.motion.model_dump(mode="json"),
                "browser_active": self._browser_motion,
            },
            "lip_sync": {
                "source": self._settings.lip_sync.source,
                "active_reply_id": self._active_reply_id,
            },
            "engine": engine_status,
        }

    async def _boot_engine(self, engine: AvatarEngine) -> None:
        try:
            await asyncio.to_thread(engine.start)
            if self._engine is not engine or self._state != "starting":
                await asyncio.to_thread(engine.stop)
                return
            engine.set_browser_motion(self._browser_motion)
            self._state = "running"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._error = str(exc)
            logger.exception("Avatar engine startup failed")
            await asyncio.to_thread(engine.stop)
            self._state = "failed"

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(0.1)
            engine = self._engine
            if self._state in {"disabled", "failed", "stopped"}:
                return
            if self._state == "running" and engine is not None:
                engine_status = engine.status()
                if not engine_status.get("running", False):
                    self._error = str(
                        engine_status.get("error") or "avatar engine stopped unexpectedly"
                    )
                    self._state = "failed"
                    self._reset_lip_state()
                    await asyncio.to_thread(engine.stop)
                    return
            if (
                self._active_reply_id
                and self._last_audio_received_at
                and time.monotonic() - self._last_audio_received_at > 0.35
                and engine is not None
            ):
                engine.set_audio_level(0.0)
                engine.set_speaking(False)
                self._last_audio_received_at = 0.0

    def _reset_lip_state(self) -> None:
        self._active_reply_id = ""
        self._last_audio_seq = -1
        self._last_audio_time_ms = -1.0
        self._last_audio_received_at = 0.0


_runtime: AvatarRuntime | None = None


def get_avatar_runtime() -> AvatarRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AvatarRuntime()
    return _runtime


def reset_avatar_runtime(runtime: AvatarRuntime | None = None) -> AvatarRuntime:
    global _runtime
    _runtime = runtime or AvatarRuntime()
    return _runtime
