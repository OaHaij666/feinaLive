from __future__ import annotations

import logging
import threading
import time
from multiprocessing import shared_memory
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from avatar_engine.config import EngineConfig, apply_engine_config
from avatar_engine.outputs import PreviewSink, SpoutSink
from avatar_engine.outputs.base import FrameSink
from avatar_engine.src.composite_input import CompositePoseProcess
from avatar_engine.src.model_infer_client import ModelClientProcess
from avatar_engine.src.utils.preprocess import resize_to_512_center
from avatar_engine.src.utils.shared_mem_guard import SharedMemoryGuard
from avatar_engine.windows_runtime import configure_windows_runtime

logger = logging.getLogger(__name__)
ENGINE_DIR = Path(__file__).parent


class FeinaAvatarEngine:
    """Supervise pose/inference workers and fan rendered frames out to sinks."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self._pose_shm: shared_memory.SharedMemory | None = None
        self._input_process: CompositePoseProcess | None = None
        self._infer_process: ModelClientProcess | None = None
        self._output_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._error = ""
        self._frame_count = 0
        self._started_at = 0.0
        self._last_frame_at = 0.0
        self._sinks: list[FrameSink] = []
        self._preview: PreviewSink | None = None

    def start(self, timeout: float = 120.0) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._error = ""
        configure_windows_runtime()
        apply_engine_config(self.config)
        image = self._load_character_image()
        self._pose_shm = shared_memory.SharedMemory(create=True, size=49 * 4)
        np.ndarray((49,), dtype=np.float32, buffer=self._pose_shm.buf)[:] = 0

        self._input_process = CompositePoseProcess(self._pose_shm, self.config)
        self._infer_process = ModelClientProcess(
            image,
            self._pose_shm,
            runtime_config=self.config,
        )
        self._input_process.daemon = True
        self._infer_process.daemon = True
        self._input_process.start()
        self._infer_process.start()

        deadline = time.monotonic() + timeout
        while not self._infer_process.ready_event.wait(timeout=0.1):
            if self._stop_event.is_set():
                raise RuntimeError("avatar engine startup cancelled")
            self._ensure_workers_alive()
            if time.monotonic() >= deadline:
                raise TimeoutError("avatar renderer did not become ready before timeout")
        self._ensure_workers_alive()

        self._build_sinks()
        self._running = True
        self._started_at = time.time()
        self._output_thread = threading.Thread(
            target=self._render_loop,
            name="feina-avatar-output",
            daemon=True,
        )
        self._output_thread.start()
        logger.info("FeinaAvatar engine ready")

    def stop(self) -> None:
        self._stop_event.set()
        self._running = False
        infer = self._infer_process
        if infer is not None:
            infer.finish_event.set()
        output_thread = self._output_thread
        if output_thread and output_thread.is_alive():
            output_thread.join(timeout=3.0)

        for process in (self._input_process, self._infer_process):
            if process is None:
                continue
            if process.is_alive():
                process.terminate()
            process.join(timeout=5.0)
            if process.is_alive():
                process.kill()
                process.join(timeout=2.0)

        self._close_sinks()
        if infer is not None:
            infer.close_parent_resources()
        if self._input_process is not None:
            self._input_process.close_parent_resources()
        self._input_process = None
        self._infer_process = None
        self._output_thread = None

        pose_shm = self._pose_shm
        self._pose_shm = None
        if pose_shm is not None:
            try:
                pose_shm.close()
            finally:
                try:
                    pose_shm.unlink()
                except FileNotFoundError:
                    pass
        logger.info("FeinaAvatar engine stopped")

    def set_mouse_position(self, x: float, y: float) -> None:
        if self._input_process is not None:
            self._input_process.set_mouse_position(x, y)

    def set_audio_level(self, level: float) -> None:
        if self._input_process is not None:
            self._input_process.set_audio_level(level)

    def set_speaking(self, speaking: bool) -> None:
        if self._input_process is not None:
            self._input_process.set_speaking(speaking)

    def set_browser_motion(self, enabled: bool) -> None:
        if self._input_process is not None:
            self._input_process.set_browser_motion(enabled)

    def latest_preview(self) -> bytes | None:
        return self._preview.latest() if self._preview is not None else None

    def status(self) -> dict[str, Any]:
        now = time.time()
        elapsed = max(now - self._started_at, 0.001) if self._started_at else 0.0
        return {
            "running": self._running,
            "error": self._error,
            "input_alive": bool(self._input_process and self._input_process.is_alive()),
            "renderer_alive": bool(self._infer_process and self._infer_process.is_alive()),
            "output_alive": bool(self._output_thread and self._output_thread.is_alive()),
            "frames": self._frame_count,
            "average_fps": self._frame_count / elapsed if elapsed else 0.0,
            "last_frame_at": self._last_frame_at,
            "outputs": {sink.name: sink.status() for sink in self._sinks},
        }

    def _load_character_image(self) -> np.ndarray:
        image_path = ENGINE_DIR / "data" / "images" / f"{self.config.character}.png"
        if not image_path.exists():
            raise FileNotFoundError(f"avatar character image does not exist: {image_path}")
        image = Image.open(image_path).convert("RGBA")
        if image.size != (512, 512):
            image = resize_to_512_center(image)
        return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGBA2BGRA)

    def _build_sinks(self) -> None:
        self._sinks = []
        self._preview = None
        if self.config.spout_enabled:
            self._sinks.append(SpoutSink(self.config.spout_name))
        if self.config.preview_enabled:
            self._preview = PreviewSink(
                self.config.preview_frame_rate,
                self.config.preview_quality,
            )
            self._sinks.append(self._preview)
        if not self._sinks:
            raise RuntimeError("avatar renderer has no enabled frame output")

    def _render_loop(self) -> None:
        infer = self._infer_process
        if infer is None:
            return
        config = self.config
        guards = [
            SharedMemoryGuard(infer.ret_shared_mem, ctrl_name=f"feina_avatar_frame_{index}")
            for index in range(config.interpolation)
        ]
        frames = [
            np.ndarray(
                (config.output_size, config.output_size, 4),
                dtype=np.uint8,
                buffer=infer.ret_shared_mem.buf[
                    index * config.output_size * config.output_size * 4 :
                    (index + 1) * config.output_size * config.output_size * 4
                ],
            )
            for index in range(config.interpolation)
        ]
        next_frame_at = time.perf_counter()
        interval = 1.0 / max(config.frame_rate, 1)
        try:
            for sink in self._sinks:
                try:
                    sink.start(config.output_size, config.output_size)
                except Exception:
                    logger.exception("Avatar output %s could not start", sink.name)
            if not any(bool(sink.status().get("running")) for sink in self._sinks):
                raise RuntimeError("no avatar frame output could start")
            while not self._stop_event.is_set():
                self._ensure_workers_alive()
                if not infer.finish_event.wait(timeout=0.25):
                    continue
                infer.finish_event.clear()
                for index, guard in enumerate(guards):
                    if self._stop_event.is_set():
                        break
                    with guard.lock(timeout_ms=1000):
                        frame = frames[index].copy()
                    delay = next_frame_at - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                    for sink in self._sinks:
                        sink.send(frame)
                    self._frame_count += 1
                    self._last_frame_at = time.time()
                    next_frame_at = max(next_frame_at + interval, time.perf_counter())
        except Exception as exc:
            self._error = str(exc)
            self._running = False
            logger.exception("FeinaAvatar output loop failed")
        finally:
            for guard in guards:
                guard.close()
            self._close_sinks()

    def _ensure_workers_alive(self) -> None:
        workers = (
            ("input", self._input_process),
            ("renderer", self._infer_process),
        )
        for label, process in workers:
            if process is not None and not process.is_alive():
                reason = process.failure_reason()
                raise RuntimeError(reason or f"avatar {label} process exited unexpectedly")

    def _close_sinks(self) -> None:
        for sink in self._sinks:
            try:
                sink.close()
            except Exception:
                logger.exception("Failed to close avatar output %s", sink.name)


def get_feina_avatar_engine(config: EngineConfig) -> FeinaAvatarEngine:
    return FeinaAvatarEngine(config)
