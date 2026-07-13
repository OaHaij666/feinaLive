from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_dll_handles: list[Any] = []
_configured = False


def configure_windows_runtime() -> None:
    """Discover GPU runtime DLLs without pinning the machine to one CUDA version."""

    global _configured
    if _configured or os.name != "nt":
        return
    candidates: list[Path] = []
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    candidates.extend(
        [
            site_packages / "nvidia" / "cudnn" / "bin",
            site_packages / "torch" / "lib",
        ]
    )
    cuda_path = os.getenv("CUDA_PATH")
    if cuda_path:
        candidates.append(Path(cuda_path) / "bin")
    cuda_root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA GPU Computing Toolkit" / "CUDA"
    if cuda_root.exists():
        candidates.extend(path / "bin" for path in sorted(cuda_root.glob("v*"), reverse=True))

    existing = [path.resolve() for path in candidates if path.exists()]
    if existing:
        current_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join([*(str(path) for path in existing), current_path])
        if hasattr(os, "add_dll_directory"):
            for path in existing:
                try:
                    _dll_handles.append(os.add_dll_directory(str(path)))
                except OSError:
                    pass
    _configured = True
