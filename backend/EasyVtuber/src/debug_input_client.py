from multiprocessing import Process, shared_memory, Value
import numpy as np
import time
import math
from .utils.timer_wait import wait_until
from .utils.shared_mem_guard import SharedMemoryGuard
from .args import args

class DebugInputClientProcess(Process):
    def __init__(self, pose_position_shm: shared_memory.SharedMemory):
        super().__init__()
        self.pose_position_shm = pose_position_shm
        self.fps = Value('f', 60.0)
        self._is_speaking = Value('i', 0)

    def set_speaking(self, speaking: bool):
        self._is_speaking.value = 1 if speaking else 0

    def run(self):
        last_time : float = time.perf_counter()
        interval : float = 1.0 / 60
        pose_position_shm_guard = SharedMemoryGuard(self.pose_position_shm, ctrl_name="pose_position_shm_ctrl")
        np_pose_shm = np.ndarray((45,), dtype=np.float32, buffer=self.pose_position_shm.buf[:45 * 4])
        np_position_shm = np.ndarray((4,), dtype=np.float32, buffer=self.pose_position_shm.buf[45 * 4:45 * 4 + 4 * 4])
        breath_start_time = time.perf_counter()
        blink_timer = 0.0
        blink_interval = args.blink_interval if hasattr(args, 'blink_interval') else 5.0
        is_blinking = False
        blink_duration = 0.15
        blink_start = 0.0
        blink_value = 1.0

        while True:
            eyebrow_vector = [0.0] * 12
            mouth_eye_vector = [0.0] * 27
            pose_vector = [0.0] * 6
            position_vector = [0, 0, 0, 1]

            breath_elapsed = (time.perf_counter() - breath_start_time) % args.breath_cycle
            breath_value = np.sin(breath_elapsed / args.breath_cycle * np.pi)

            blink_timer += 1.0 / 60
            if not is_blinking and blink_timer >= blink_interval:
                is_blinking = True
                blink_start = time.perf_counter()
                blink_timer = 0.0
            if is_blinking:
                blink_elapsed = time.perf_counter() - blink_start
                if blink_elapsed < blink_duration:
                    blink_value = max(0.0, 1.0 - blink_elapsed / (blink_duration * 0.3))
                else:
                    blink_value = max(0.0, (blink_elapsed - blink_duration) / (blink_duration * 0.7))
                    if blink_value >= 1.0:
                        blink_value = 1.0
                        is_blinking = False
                        blink_interval = args.blink_interval if hasattr(args, 'blink_interval') else 5.0
                        blink_timer = 0.0
            else:
                blink_value = 1.0

            is_speaking = self._is_speaking.value == 1

            if is_speaking:
                mouth_open = 0.4 + math.sin(time.perf_counter() * 12) * 0.15
                mouth_eye_vector[2] = blink_value * 0.3 + mouth_open * 0.2
                mouth_eye_vector[3] = blink_value * 0.3 + mouth_open * 0.15
                mouth_eye_vector[14] = mouth_open
                eyebrow_vector[6] = math.sin(time.perf_counter() * 1.1) + 0.08
                eyebrow_vector[7] = math.sin(time.perf_counter() * 1.1) + 0.08
            else:
                mouth_eye_vector[2] = blink_value * 0.5 + math.sin(time.perf_counter() * 2.5) * 0.08
                mouth_eye_vector[3] = blink_value * 0.5 + math.sin(time.perf_counter() * 2.5) * 0.08
                mouth_eye_vector[14] = math.sin(time.perf_counter() * 1.8) * 0.15
                eyebrow_vector[6] = math.sin(time.perf_counter() * 1.1)
                eyebrow_vector[7] = math.sin(time.perf_counter() * 1.1)

            mouth_eye_vector[25] = math.sin(time.perf_counter() * 2.2) * 0.2
            mouth_eye_vector[26] = math.sin(time.perf_counter() * 3.5) * 0.8

            pose_vector[0] = math.sin(time.perf_counter() * 1.1)
            pose_vector[1] = math.sin(time.perf_counter() * 1.2)
            pose_vector[2] = math.sin(time.perf_counter() * 1.5)
            pose_vector[3] = pose_vector[1]
            pose_vector[4] = pose_vector[2]
            pose_vector[5] = breath_value

            model_input_arr = eyebrow_vector
            model_input_arr.extend(mouth_eye_vector)
            model_input_arr.extend(pose_vector)

            position_vector[0] = math.sin(time.perf_counter() * 0.5) * 0.1
            position_vector[1] = math.sin(time.perf_counter() * 0.6) * 0.1
            position_vector[2] = math.sin(time.perf_counter() * 0.7) * 0.1
            position_vector[3] = 1

            with pose_position_shm_guard.lock():
                np_pose_shm[:] = np.array(model_input_arr, dtype=np.float32)
                np_position_shm[:] = np.array(position_vector, dtype=np.float32)
            wait_until(last_time + interval)
            last_time += interval
