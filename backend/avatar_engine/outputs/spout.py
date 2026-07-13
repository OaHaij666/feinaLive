from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import numpy as np


class SpoutSink:
    name = "spout"

    def __init__(self, sender_name: str = "FeinaAvatar") -> None:
        self._sender_name = sender_name
        self._sender: Any | None = None
        self._error = ""
        self._dll_directory: Any | None = None

    def start(self, width: int, height: int) -> None:
        try:
            project_root = Path(__file__).resolve().parents[3]
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            if hasattr(os, "add_dll_directory"):
                self._dll_directory = os.add_dll_directory(str(project_root))
            from OpenGL.GL import GL_RGBA
            from PySpout import SpoutSender

            self._sender = SpoutSender(self._sender_name, width, height, GL_RGBA)
        except Exception as exc:
            self._error = str(exc)
            raise RuntimeError(f"Spout2 output unavailable: {exc}") from exc

    def send(self, frame: np.ndarray) -> None:
        if self._sender is None:
            return
        self._sender.send_image(frame, False)

    def close(self) -> None:
        sender = self._sender
        self._sender = None
        if sender is not None:
            for method_name in ("release_sender", "close"):
                method = getattr(sender, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
                    break
        if self._dll_directory is not None:
            self._dll_directory.close()
            self._dll_directory = None

    def status(self) -> dict[str, object]:
        return {
            "running": self._sender is not None,
            "name": self._sender_name,
            "error": self._error,
        }
