import asyncio

import pytest
from pydantic import ValidationError

from apps.avatar.runtime import AvatarRuntime
from apps.avatar.schemas import AvatarConfig
from avatar_engine.config import EngineConfig
from avatar_engine.pose import FacialPose, MotionPose, THAPoseMapper
from avatar_engine.runner import FeinaAvatarEngine
from avatar_engine.src.composite_input import broadcast_idle_motion


class FakeEngine:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.running = False
        self.stopped = False
        self.mouse = None
        self.audio = []
        self.speaking = []
        self.browser_motion = []

    def start(self) -> None:
        if self.fail:
            raise RuntimeError("renderer unavailable")
        self.running = True

    def stop(self) -> None:
        self.running = False
        self.stopped = True

    def set_mouse_position(self, x: float, y: float) -> None:
        self.mouse = (x, y)

    def set_audio_level(self, level: float) -> None:
        self.audio.append(level)

    def set_speaking(self, speaking: bool) -> None:
        self.speaking.append(speaking)

    def set_browser_motion(self, enabled: bool) -> None:
        self.browser_motion.append(enabled)

    def latest_preview(self) -> bytes | None:
        return b"preview" if self.running else None

    def status(self) -> dict:
        return {"running": self.running, "error": ""}


async def wait_for_state(runtime: AvatarRuntime, expected: str) -> None:
    for _ in range(50):
        if runtime.status()["state"] == expected:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"avatar state did not become {expected}: {runtime.status()}")


@pytest.mark.asyncio
async def test_avatar_runtime_supervises_engine_without_blocking_event_loop():
    engine = FakeEngine()
    runtime = AvatarRuntime(lambda settings: engine)
    await runtime.start(AvatarConfig())
    assert runtime.status()["state"] in {"starting", "running"}
    await wait_for_state(runtime, "running")
    assert runtime.latest_preview() == b"preview"

    await runtime.stop()
    assert engine.stopped
    assert runtime.status()["state"] == "stopped"


@pytest.mark.asyncio
async def test_broadcast_idle_motion_is_default_and_ignores_browser_face_mode():
    engine = FakeEngine()
    runtime = AvatarRuntime(lambda settings: engine)
    settings = AvatarConfig()
    assert settings.motion.source == "broadcast_idle"
    assert EngineConfig().motion_source == "broadcast_idle"

    await runtime.start(settings)
    await wait_for_state(runtime, "running")
    runtime.set_face_mode("mouse_tracking")
    runtime.set_face_mode("wandering")

    assert engine.browser_motion[-2:] == [False, False]
    await runtime.stop()


@pytest.mark.asyncio
async def test_hybrid_motion_switches_browser_control_at_runtime():
    engine = FakeEngine()
    runtime = AvatarRuntime(lambda settings: engine)
    settings = AvatarConfig(motion={"source": "hybrid"})

    await runtime.start(settings)
    await wait_for_state(runtime, "running")
    runtime.set_face_mode("mouse_tracking")
    runtime.set_face_mode("wandering")

    assert engine.browser_motion[-2:] == [True, False]
    await runtime.stop()


@pytest.mark.asyncio
async def test_avatar_runtime_rejects_stale_and_cross_reply_lip_packets():
    engine = FakeEngine()
    runtime = AvatarRuntime(lambda settings: engine)
    await runtime.start(AvatarConfig())
    await wait_for_state(runtime, "running")
    runtime.begin_lip_sync("reply-1")

    assert runtime.update_audio("reply-1", 0, 10.0, 0.4, True)
    assert not runtime.update_audio("reply-1", 0, 11.0, 0.8, True)
    assert not runtime.update_audio("reply-1", 1, 9.0, 0.8, True)
    assert not runtime.update_audio("reply-2", 1, 12.0, 0.8, True)
    assert engine.audio == [0.4]

    runtime.end_lip_sync("reply-1")
    assert engine.audio[-1] == 0.0
    assert engine.speaking[-1] is False
    await runtime.stop()


@pytest.mark.asyncio
async def test_avatar_runtime_reports_renderer_start_failure():
    engine = FakeEngine(fail=True)
    runtime = AvatarRuntime(lambda settings: engine)
    await runtime.start(AvatarConfig())
    await wait_for_state(runtime, "failed")
    assert "renderer unavailable" in runtime.status()["error"]
    assert engine.stopped
    await runtime.stop()


@pytest.mark.asyncio
async def test_avatar_runtime_reclaims_engine_after_runtime_failure():
    engine = FakeEngine()
    runtime = AvatarRuntime(lambda settings: engine)
    await runtime.start(AvatarConfig())
    await wait_for_state(runtime, "running")

    engine.running = False
    await wait_for_state(runtime, "failed")
    for _ in range(50):
        if engine.stopped:
            break
        await asyncio.sleep(0.01)

    assert engine.stopped
    assert "stopped unexpectedly" in runtime.status()["error"]
    await runtime.stop()


def test_avatar_config_maps_every_runtime_setting_to_engine_snapshot():
    settings = AvatarConfig.model_validate(
        {
            "renderer": {
                "model": "tha4_student",
                "backend": "tensorrt",
                "precision": "fp16",
                "interpolation": 4,
                "super_resolution": 2,
                "ram_cache_mb": 1024,
                "vram_cache_mb": 4096,
            },
            "outputs": {
                "spout": {"enabled": True, "name": "TestAvatar"},
                "preview": {"enabled": False},
            },
        }
    )
    snapshot = settings.to_engine_config()
    assert snapshot.model_version == "v4_student"
    assert snapshot.backend == "tensorrt"
    assert snapshot.precision == "fp16"
    assert snapshot.interpolation == 4
    assert snapshot.super_resolution == 2
    assert snapshot.spout_name == "TestAvatar"


def test_avatar_config_requires_at_least_one_output():
    with pytest.raises(ValidationError):
        AvatarConfig.model_validate(
            {
                "outputs": {
                    "spout": {"enabled": False},
                    "preview": {"enabled": False},
                }
            }
        )


def test_named_pose_channels_map_to_tha_contract():
    pose, position = THAPoseMapper.map(
        MotionPose(head_yaw=0.2, gaze_x=-0.3, offset_x=0.1),
        FacialPose(blink=0.5, mouth_open=0.8, eyebrow_raise=0.1),
    )
    assert pose.shape == (45,)
    assert pose[6] == pytest.approx(0.1)
    assert pose[14] == pytest.approx(0.5)
    assert pose[26] == pytest.approx(0.8)
    assert pose[38] == pytest.approx(-0.3)
    assert pose[40] == pytest.approx(0.2)
    assert position[0] == pytest.approx(0.1)


def test_broadcast_idle_motion_is_anchored_and_coordinates_eyes_with_head():
    samples = [broadcast_idle_motion(index / 10) for index in range(200)]
    assert all(sample.offset_x == 0.0 and sample.offset_y == 0.0 for sample in samples)
    assert max(abs(sample.head_yaw) for sample in samples) < 0.1
    assert max(abs(sample.head_pitch) for sample in samples) < 0.05
    assert max(abs(sample.head_roll) for sample in samples) < 0.03
    assert max(abs(sample.body_yaw or 0.0) for sample in samples) < 0.02
    assert max(abs(sample.body_roll or 0.0) for sample in samples) < 0.015
    assert all(sample.gaze_x * sample.head_yaw >= 0 for sample in samples)
    assert all(sample.gaze_y * sample.head_pitch >= 0 for sample in samples)


def test_pose_mapper_can_keep_body_sway_smaller_than_head_motion():
    pose, _ = THAPoseMapper.map(
        MotionPose(head_yaw=0.2, head_roll=0.1, body_yaw=0.02, body_roll=0.01),
        FacialPose(),
    )
    assert pose[40] == pytest.approx(0.2)
    assert pose[42] == pytest.approx(0.02)
    assert pose[43] == pytest.approx(0.01)


def test_avatar_engine_fails_when_either_worker_exits():
    class Worker:
        def __init__(self, alive: bool, reason: str = "") -> None:
            self.alive = alive
            self.reason = reason

        def is_alive(self) -> bool:
            return self.alive

        def failure_reason(self) -> str:
            return self.reason

    engine = FeinaAvatarEngine(EngineConfig())
    engine._input_process = Worker(False, "pose worker exploded")
    engine._infer_process = Worker(True)

    with pytest.raises(RuntimeError, match="pose worker exploded"):
        engine._ensure_workers_alive()

    engine._input_process = Worker(True)
    engine._infer_process = Worker(False)
    with pytest.raises(RuntimeError, match="renderer process exited"):
        engine._ensure_workers_alive()
