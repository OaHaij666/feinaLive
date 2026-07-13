from __future__ import annotations

from typing import Protocol

import numpy as np


class FrameSink(Protocol):
    name: str

    def start(self, width: int, height: int) -> None: ...

    def send(self, frame: np.ndarray) -> None: ...

    def close(self) -> None: ...

    def status(self) -> dict[str, object]: ...
