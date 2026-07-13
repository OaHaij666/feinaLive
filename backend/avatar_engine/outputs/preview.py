from __future__ import annotations

import threading
import time

import cv2
import numpy as np


class PreviewSink:
    name = "preview"

    def __init__(self, frame_rate: int = 10, quality: int = 80) -> None:
        self._interval = 1.0 / max(frame_rate, 1)
        self._quality = quality
        self._lock = threading.Lock()
        self._latest: bytes | None = None
        self._last_encoded_at = 0.0
        self._running = False

    def start(self, width: int, height: int) -> None:
        self._running = True

    def send(self, frame: np.ndarray) -> None:
        now = time.monotonic()
        if not self._running or now - self._last_encoded_at < self._interval:
            return
        ok, encoded = cv2.imencode(
            ".webp",
            frame,
            [cv2.IMWRITE_WEBP_QUALITY, self._quality],
        )
        if not ok:
            return
        with self._lock:
            self._latest = encoded.tobytes()
            self._last_encoded_at = now

    def latest(self) -> bytes | None:
        with self._lock:
            return self._latest

    def close(self) -> None:
        self._running = False
        with self._lock:
            self._latest = None

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "running": self._running,
                "has_frame": self._latest is not None,
                "last_frame_at": self._last_encoded_at,
            }
