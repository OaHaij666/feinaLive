"""Process-local inference options consumed by the vendored renderer.

FeinaAvatar is configured by the application schema, not command-line flags.
Keeping this small mutable snapshot avoids importing EasyVtuber's former CLI
parser inside FastAPI and still supports the vendored pose simplifier.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InferenceOptions:
    model_version: str = "v3"
    model_name: str = ""
    model_seperable: bool = False
    model_half: bool = False
    eyebrow: bool = True
    use_tensorrt: bool = False
    use_interpolation: bool = False
    interpolation_scale: int = 1
    interpolation_half: bool = False
    use_sr: bool = False
    sr_x4: bool = False
    sr_half: bool = False
    sr_a4k: bool = False
    max_ram_cache_len: float = 2.0
    max_gpu_cache_len: float = 2.0
    model_output_size: int = 512
    simplify: int = 1


args = InferenceOptions()
