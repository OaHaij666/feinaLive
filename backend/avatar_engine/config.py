from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LipSyncConfig:
    sensitivity: float = 3.0
    noise_gate: float = 0.015
    attack_ms: float = 35.0
    release_ms: float = 90.0


@dataclass(frozen=True)
class EngineConfig:
    character: str = "feina00"
    motion_source: str = "autonomous"
    model_family: str = "tha3"
    backend: str = "onnxruntime"
    precision: str = "fp32"
    separable: bool = False
    use_eyebrow: bool = True
    frame_rate: int = 30
    interpolation: int = 1
    super_resolution: int = 1
    ram_cache_mb: int = 2048
    vram_cache_mb: int = 2048
    spout_enabled: bool = True
    spout_name: str = "FeinaAvatar"
    preview_enabled: bool = True
    preview_frame_rate: int = 10
    preview_quality: int = 80
    lip_sync: LipSyncConfig = field(default_factory=LipSyncConfig)

    @property
    def model_version(self) -> str:
        return {
            "tha3": "v3",
            "tha4": "v4",
            "tha4_student": "v4_student",
        }[self.model_family]

    @property
    def output_size(self) -> int:
        return 1024 if self.super_resolution > 1 else 512


def apply_engine_config(config: EngineConfig) -> None:
    """Populate the vendored inference module's process-local argument object."""

    from .src.args import args

    args.model_version = config.model_version
    args.model_seperable = config.separable
    args.model_half = config.precision == "fp16"
    args.eyebrow = config.use_eyebrow
    args.use_tensorrt = config.backend == "tensorrt"
    args.use_interpolation = config.interpolation > 1
    args.interpolation_scale = config.interpolation
    args.interpolation_half = config.precision == "fp16"
    args.use_sr = config.super_resolution > 1
    args.sr_x4 = config.super_resolution == 4
    args.sr_half = config.precision == "fp16"
    args.sr_a4k = False
    args.max_ram_cache_len = config.ram_cache_mb / 1024
    args.max_gpu_cache_len = config.vram_cache_mb / 1024
    args.model_output_size = config.output_size
    args.simplify = 1
