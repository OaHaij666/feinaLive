from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from avatar_engine.config import EngineConfig, LipSyncConfig


class AvatarMotionConfig(BaseModel):
    source: Literal["autonomous", "browser", "hybrid", "broadcast_idle"] = "hybrid"
    allow_browser_control: bool = True


class AvatarLipSyncConfig(BaseModel):
    source: Literal["browser_audio", "disabled"] = "browser_audio"
    sensitivity: float = Field(default=3.0, ge=0.1, le=10.0)
    noise_gate: float = Field(default=0.015, ge=0.0, le=0.5)
    attack_ms: float = Field(default=35.0, ge=1.0, le=1000.0)
    release_ms: float = Field(default=90.0, ge=1.0, le=2000.0)


class AvatarRendererConfig(BaseModel):
    engine: Literal["feina_avatar"] = "feina_avatar"
    model: Literal["tha3", "tha4", "tha4_student"] = "tha3"
    backend: Literal["onnxruntime", "tensorrt"] = "onnxruntime"
    precision: Literal["fp32", "fp16"] = "fp32"
    separable: bool = False
    use_eyebrow: bool = True
    frame_rate: int = Field(default=30, ge=10, le=60)
    interpolation: Literal[1, 2, 4] = 1
    super_resolution: Literal[1, 2, 4] = 1
    ram_cache_mb: int = Field(default=2048, ge=0, le=32768)
    vram_cache_mb: int = Field(default=2048, ge=0, le=32768)


class AvatarSpoutConfig(BaseModel):
    enabled: bool = True
    name: str = Field(default="FeinaAvatar", min_length=1, max_length=64)


class AvatarPreviewConfig(BaseModel):
    enabled: bool = True
    frame_rate: int = Field(default=10, ge=1, le=30)
    quality: int = Field(default=80, ge=20, le=100)


class AvatarOutputsConfig(BaseModel):
    spout: AvatarSpoutConfig = Field(default_factory=AvatarSpoutConfig)
    preview: AvatarPreviewConfig = Field(default_factory=AvatarPreviewConfig)

    @model_validator(mode="after")
    def require_output(self):
        if not self.spout.enabled and not self.preview.enabled:
            raise ValueError("avatar requires at least one enabled output")
        return self


class AvatarConfig(BaseModel):
    enabled: bool = True
    character: str = Field(default="feina00", min_length=1)
    motion: AvatarMotionConfig = Field(default_factory=AvatarMotionConfig)
    lip_sync: AvatarLipSyncConfig = Field(default_factory=AvatarLipSyncConfig)
    renderer: AvatarRendererConfig = Field(default_factory=AvatarRendererConfig)
    outputs: AvatarOutputsConfig = Field(default_factory=AvatarOutputsConfig)

    def to_engine_config(self) -> EngineConfig:
        renderer = self.renderer
        return EngineConfig(
            character=self.character,
            motion_source=self.motion.source,
            model_family=renderer.model,
            backend=renderer.backend,
            precision=renderer.precision,
            separable=renderer.separable,
            use_eyebrow=renderer.use_eyebrow,
            frame_rate=renderer.frame_rate,
            interpolation=renderer.interpolation,
            super_resolution=renderer.super_resolution,
            ram_cache_mb=renderer.ram_cache_mb,
            vram_cache_mb=renderer.vram_cache_mb,
            spout_enabled=self.outputs.spout.enabled,
            spout_name=self.outputs.spout.name,
            preview_enabled=self.outputs.preview.enabled,
            preview_frame_rate=self.outputs.preview.frame_rate,
            preview_quality=self.outputs.preview.quality,
            lip_sync=LipSyncConfig(
                sensitivity=self.lip_sync.sensitivity,
                noise_gate=self.lip_sync.noise_gate,
                attack_ms=self.lip_sync.attack_ms,
                release_ms=self.lip_sync.release_ms,
            ),
        )
