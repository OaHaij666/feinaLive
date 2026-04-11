"""EasyVtuber AI主播音频驱动输入客户端"""

import asyncio
import logging
import math
import time
from multiprocessing import Process, Value, shared_memory
from typing import Callable

import numpy as np

from .args import args
from .utils.shared_mem_guard import SharedMemoryGuard
from .utils.timer_wait import wait_until

logger = logging.getLogger(__name__)


class AudioDrivenClientProcess(Process):
    def __init__(self, pose_position_shm: shared_memory.SharedMemory):
        super().__init__()
        self.pose_position_shm = pose_position_shm
        self.fps = Value('f', 60.0)
        self._audio_level = Value('f', 0.0)
        self._is_speaking = Value('i', 0)
        self._expression_callback: Callable | None = None

    def set_audio_level(self, level: float):
        self._audio_level.value = max(0.0, min(1.0, level))

    def set_speaking(self, speaking: bool):
        self._is_speaking.value = 1 if speaking else 0

    def run(self):
        last_time: float = time.perf_counter()
        interval: float = 1.0 / 60
        pose_position_shm_guard = SharedMemoryGuard(self.pose_position_shm, ctrl_name="pose_position_shm_ctrl")
        np_pose_shm = np.ndarray((45,), dtype=np.float32, buffer=self.pose_position_shm.buf[:45 * 4])
        np_position_shm = np.ndarray((4,), dtype=np.float32, buffer=self.pose_position_shm.buf[45 * 4:45 * 4 + 4 * 4])

        breath_start_time = time.perf_counter()
        blink_timer = 0.0
        blink_interval = args.blink_interval if hasattr(args, 'blink_interval') else 5.0
        is_blinking = False
        blink_duration = 0.15
        blink_start = 0.0

        while True:
            eyebrow_vector = [0.0] * 12
            mouth_eye_vector = [0.0] * 27
            pose_vector = [0.0] * 6
            position_vector = [0, 0, 0, 1]

            audio_level = self._audio_level.value
            is_speaking = self._is_speaking.value == 1

            breath_elapsed = (time.perf_counter() - breath_start_time) % args.breath_cycle
            breath_value = np.sin(breath_elapsed / args.breath_cycle * np.pi)

            if is_speaking:
                mouth_open = audio_level * 0.8
                mouth_open += np.sin(time.perf_counter() * 15) * 0.1 * audio_level
                mouth_eye_vector[2] = mouth_open
                mouth_eye_vector[3] = mouth_open * 0.8
                mouth_eye_vector[14] = audio_level * 0.3
                mouth_eye_vector[25] = audio_level * 0.2
                mouth_eye_vector[26] = audio_level * 0.6
            else:
                mouth_eye_vector[2] = 0.0
                mouth_eye_vector[3] = 0.0
                mouth_eye_vector[14] = 0.0
                mouth_eye_vector[25] = 0.0
                mouth_eye_vector[26] = 0.0

            blink_timer += interval
            if not is_blinking and blink_timer >= blink_interval:
                is_blinking = True
                blink_start = time.perf_counter()
                blink_timer = 0.0
                blink_interval = 3.0 + np.random.random() * 4.0

            if is_blinking:
                blink_progress = (time.perf_counter() - blink_start) / blink_duration
                if blink_progress >= 1.0:
                    is_blinking = False
                    mouth_eye_vector[0] = 0.0
                    mouth_eye_vector[1] = 0.0
                else:
                    blink_value = np.sin(blink_progress * np.pi)
                    mouth_eye_vector[0] = blink_value
                    mouth_eye_vector[1] = blink_value

            pose_vector[0] = math.sin(time.perf_counter() * 0.3) * 0.1
            pose_vector[1] = math.sin(time.perf_counter() * 0.4) * 0.1
            pose_vector[2] = math.sin(time.perf_counter() * 0.2) * 0.05
            pose_vector[3] = pose_vector[1]
            pose_vector[4] = pose_vector[2]
            pose_vector[5] = breath_value

            eyebrow_vector[6] = math.sin(time.perf_counter() * 0.5) * 0.1
            eyebrow_vector[7] = math.sin(time.perf_counter() * 0.5) * 0.1

            if is_speaking:
                eyebrow_vector[6] += audio_level * 0.1
                eyebrow_vector[7] += audio_level * 0.1

            model_input_arr = eyebrow_vector
            model_input_arr.extend(mouth_eye_vector)
            model_input_arr.extend(pose_vector)

            position_vector[0] = math.sin(time.perf_counter() * 0.3) * 0.05
            position_vector[1] = math.sin(time.perf_counter() * 0.4) * 0.05
            position_vector[2] = 0
            position_vector[3] = 1

            with pose_position_shm_guard.lock():
                np_pose_shm[:] = np.array(model_input_arr, dtype=np.float32)
                np_position_shm[:] = np.array(position_vector, dtype=np.float32)

            wait_until(last_time + interval)
            last_time += interval


class AudioLevelAnalyzer:
    def __init__(self, client: AudioDrivenClientProcess):
        self._client = client
        self._smoothing = 0.3
        self._last_level = 0.0

    def analyze(self, audio_data: bytes) -> float:
        if len(audio_data) == 0:
            return 0.0

        samples = np.frombuffer(audio_data, dtype=np.int16)
        if len(samples) == 0:
            return 0.0

        rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
        level = rms / 32768.0
        level = min(1.0, level * 3.0)

        self._last_level = self._smoothing * level + (1 - self._smoothing) * self._last_level
        return self._last_level

    def update_client(self, audio_data: bytes, is_speaking: bool = True):
        level = self.analyze(audio_data)
        self._client.set_audio_level(level)
        self._client.set_speaking(is_speaking)
        return level
