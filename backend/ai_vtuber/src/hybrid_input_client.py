"""混合输入客户端 - 结合自动动画、鼠标追踪和TTS音频驱动"""

import math
import time
from multiprocessing import Process, Value, shared_memory

import numpy as np

from .utils.shared_mem_guard import SharedMemoryGuard
from .utils.timer_wait import wait_until

BREATH_CYCLE = 4.0
BLINK_INTERVAL_BASE = 4.0


class HybridInputClientProcess(Process):
    def __init__(self, pose_position_shm: shared_memory.SharedMemory):
        super().__init__()
        self.pose_position_shm = pose_position_shm
        self.fps = Value('f', 60.0)
        
        self._mouse_x = Value('f', 0.5)
        self._mouse_y = Value('f', 0.5)
        self._audio_level = Value('f', 0.0)
        self._is_speaking = Value('i', 0)

    def set_mouse_position(self, x: float, y: float):
        self._mouse_x.value = max(0.0, min(1.0, x))
        self._mouse_y.value = max(0.0, min(1.0, y))

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
        blink_interval = BLINK_INTERVAL_BASE
        is_blinking = False
        blink_duration = 0.25
        blink_start = 0.0
        
        head_slowness = 0.15
        prev_head_x = 0.0
        prev_head_y = 0.0
        
        while True:
            eyebrow_vector = [0.0] * 12
            mouth_eye_vector = [0.0] * 27
            pose_vector = [0.0] * 6
            position_vector = [0, 0, 0, 1]
            
            current_time = time.perf_counter()
            audio_level = self._audio_level.value
            is_speaking = self._is_speaking.value == 1
            mouse_x = self._mouse_x.value
            mouse_y = self._mouse_y.value
            
            breath_elapsed = (current_time - breath_start_time) % BREATH_CYCLE
            breath_value = np.sin(breath_elapsed / BREATH_CYCLE * np.pi)
            
            blink_timer += interval
            if not is_blinking and blink_timer >= blink_interval:
                is_blinking = True
                blink_start = current_time
                blink_timer = 0.0
                blink_interval = 3.0 + np.random.random() * 4.0
            
            blink_value = 0.0
            if is_blinking:
                blink_progress = (current_time - blink_start) / blink_duration
                if blink_progress >= 1.0:
                    is_blinking = False
                else:
                    blink_value = np.sin(blink_progress * np.pi)
            
            eyebrow_vector[6] = math.sin(current_time * 0.8) * 0.15
            eyebrow_vector[7] = math.sin(current_time * 0.8) * 0.15
            
            if is_speaking:
                mouth_open = audio_level * 0.7
                mouth_open += np.sin(current_time * 12) * 0.15 * audio_level
                mouth_eye_vector[2] = blink_value * 0.3 + mouth_open * 0.2
                mouth_eye_vector[3] = blink_value * 0.3 + mouth_open * 0.15
                mouth_eye_vector[14] = mouth_open
                
                eyebrow_vector[6] += audio_level * 0.08
                eyebrow_vector[7] += audio_level * 0.08
            else:
                mouth_eye_vector[2] = blink_value * 0.5 + math.sin(current_time * 2.5) * 0.08
                mouth_eye_vector[3] = blink_value * 0.5 + math.sin(current_time * 2.5) * 0.08
                mouth_eye_vector[14] = math.sin(current_time * 1.8) * 0.15
            
            eye_limit = [0.6, 0.4]
            head_eye_reduce = 0.5
            
            target_eye_x = (0.5 - mouse_x) * 2 * eye_limit[0]
            target_eye_y = (0.5 - mouse_y) * 2 * eye_limit[1]
            
            mouth_eye_vector[25] = target_eye_y + math.sin(current_time * 1.5) * 0.05
            mouth_eye_vector[26] = target_eye_x + math.sin(current_time * 2.0) * 0.1
            
            target_head_x = (0.5 - mouse_y) * 2 * 0.5
            target_head_y = (0.5 - mouse_x) * 2 * 0.5
            
            head_x = prev_head_x + (target_head_x - prev_head_x) * head_slowness
            head_y = prev_head_y + (target_head_y - prev_head_y) * head_slowness
            prev_head_x = head_x
            prev_head_y = head_y
            
            auto_head_x = math.sin(current_time * 0.4) * 0.33
            auto_head_y = math.sin(current_time * 0.5) * 0.33
            auto_head_z = math.sin(current_time * 0.3) * 0.11
            
            pose_vector[0] = head_x + auto_head_x
            pose_vector[1] = head_y + auto_head_y
            pose_vector[2] = auto_head_z
            pose_vector[3] = pose_vector[1]
            pose_vector[4] = pose_vector[2]
            pose_vector[5] = breath_value
            
            mouth_eye_vector[25] -= pose_vector[0] * eye_limit[1] * head_eye_reduce
            mouth_eye_vector[26] -= pose_vector[1] * eye_limit[0] * head_eye_reduce
            
            model_input_arr = eyebrow_vector
            model_input_arr.extend(mouth_eye_vector)
            model_input_arr.extend(pose_vector)
            
            position_vector[0] = math.sin(current_time * 0.3) * 0.03
            position_vector[1] = math.sin(current_time * 0.4) * 0.03
            position_vector[2] = 0
            position_vector[3] = 1
            
            with pose_position_shm_guard.lock():
                np_pose_shm[:] = np.array(model_input_arr, dtype=np.float32)
                np_position_shm[:] = np.array(position_vector, dtype=np.float32)
            
            wait_until(last_time + interval)
            last_time += interval
