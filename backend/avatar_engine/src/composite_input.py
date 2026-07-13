"""Composite autonomous/browser motion and browser-audio lip synchronization."""

from __future__ import annotations

import math
import queue
import random
import time
import traceback
from multiprocessing import Process, Queue, Value, shared_memory

import numpy as np

from avatar_engine.config import EngineConfig
from avatar_engine.pose import FacialPose, MotionPose, THAPoseMapper

from .utils.shared_mem_guard import SharedMemoryGuard
from .utils.timer_wait import wait_until


class NaturalMotion:
    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.target_x = 0.0
        self.target_y = 0.0
        self.next_target_at = 0.0

    def update(self, now: float, dt: float) -> tuple[float, float]:
        if now >= self.next_target_at:
            self.target_x = random.uniform(-0.75, 0.75)
            self.target_y = random.uniform(-0.65, 0.65)
            self.next_target_at = now + random.uniform(0.7, 4.0)
        blend = min(1.0, dt * 2.3)
        self.x += (self.target_x - self.x) * blend
        self.y += (self.target_y - self.y) * blend
        return self.x, self.y


class CompositePoseProcess(Process):
    """Own all pose channels so motion and lips never compete for shared memory."""

    def __init__(
        self,
        pose_position_shm: shared_memory.SharedMemory,
        config: EngineConfig,
    ) -> None:
        super().__init__()
        self.pose_position_shm = pose_position_shm
        self.config = config
        self.error_queue: Queue = Queue(maxsize=1)
        self._failure_cache = ""
        self._mouse_x = Value("f", 0.5)
        self._mouse_y = Value("f", 0.5)
        self._audio_level = Value("f", 0.0)
        self._is_speaking = Value("i", 0)
        self._browser_motion = Value(
            "i",
            1 if config.motion_source == "browser" else 0,
        )

    def set_mouse_position(self, x: float, y: float) -> None:
        self._mouse_x.value = max(0.0, min(1.0, x))
        self._mouse_y.value = max(0.0, min(1.0, y))

    def set_audio_level(self, level: float) -> None:
        self._audio_level.value = max(0.0, min(1.0, level))

    def set_speaking(self, speaking: bool) -> None:
        self._is_speaking.value = int(speaking)

    def set_browser_motion(self, enabled: bool) -> None:
        self._browser_motion.value = int(enabled)

    def run(self) -> None:
        try:
            self._run_pose_loop()
        except Exception:
            try:
                self.error_queue.put_nowait(traceback.format_exc())
            except queue.Full:
                pass

    def _run_pose_loop(self) -> None:
        interval = 1.0 / 60.0
        last_time = time.perf_counter()
        guard = SharedMemoryGuard(
            self.pose_position_shm,
            ctrl_name="feina_avatar_pose",
        )
        pose_view = np.ndarray(
            (45,),
            dtype=np.float32,
            buffer=self.pose_position_shm.buf[: 45 * 4],
        )
        position_view = np.ndarray(
            (4,),
            dtype=np.float32,
            buffer=self.pose_position_shm.buf[45 * 4 : 49 * 4],
        )
        natural = NaturalMotion()
        next_blink_at = last_time + random.uniform(3.0, 6.0)
        blink_started_at: float | None = None
        previous_head_x = 0.0
        previous_head_y = 0.0
        smoothed_mouth = 0.0

        try:
            while True:
                now = time.perf_counter()
                dt = max(0.001, min(now - last_time, 0.1))
                browser_motion = self._browser_motion.value == 1
                if browser_motion:
                    target_x = (0.5 - self._mouse_x.value) * 2
                    target_y = (0.5 - self._mouse_y.value) * 2
                else:
                    target_x, target_y = natural.update(now, dt)

                head_blend = min(1.0, dt * 8.0)
                previous_head_x += (target_y * 0.5 - previous_head_x) * head_blend
                previous_head_y += (target_x * 0.5 - previous_head_y) * head_blend

                if blink_started_at is None and now >= next_blink_at:
                    blink_started_at = now
                blink = 0.0
                if blink_started_at is not None:
                    progress = (now - blink_started_at) / 0.24
                    if progress >= 1.0:
                        blink_started_at = None
                        next_blink_at = now + random.uniform(3.0, 7.0)
                    else:
                        blink = math.sin(progress * math.pi)

                lip = self.config.lip_sync
                raw_level = self._audio_level.value if self._is_speaking.value else 0.0
                target_mouth = max(0.0, raw_level - lip.noise_gate) * lip.sensitivity
                target_mouth = min(target_mouth, 1.0)
                time_constant = lip.attack_ms if target_mouth > smoothed_mouth else lip.release_ms
                coefficient = 1.0 - math.exp(-dt / max(time_constant / 1000.0, 0.001))
                smoothed_mouth += (target_mouth - smoothed_mouth) * coefficient

                breathing = (math.sin(now * math.pi / 2.0) + 1.0) / 2.0
                motion = MotionPose(
                    head_pitch=previous_head_x + math.sin(now * 0.4) * 0.08,
                    head_yaw=previous_head_y + math.sin(now * 0.5) * 0.08,
                    head_roll=math.sin(now * 0.3) * 0.05,
                    gaze_x=target_x * 0.45 - previous_head_y * 0.25,
                    gaze_y=target_y * 0.35 - previous_head_x * 0.2,
                    breathing=breathing,
                    offset_x=math.sin(now * 0.3) * 0.025,
                    offset_y=math.sin(now * 0.4) * 0.025,
                )
                face = FacialPose(
                    blink=blink,
                    mouth_open=smoothed_mouth,
                    eyebrow_raise=0.04 + smoothed_mouth * 0.08,
                )
                pose, position = THAPoseMapper.map(motion, face)
                with guard.lock():
                    pose_view[:] = pose
                    position_view[:] = position

                wait_until(last_time + interval)
                last_time += interval
        finally:
            guard.close()

    def failure_reason(self) -> str:
        if self._failure_cache:
            return self._failure_cache
        try:
            self._failure_cache = str(self.error_queue.get_nowait())
        except queue.Empty:
            pass
        return self._failure_cache

    def close_parent_resources(self) -> None:
        self.error_queue.close()
