"""混合输入客户端 - 结合自动动画、鼠标追踪和TTS音频驱动"""

import math
import random
import time
from multiprocessing import Process, Value, shared_memory

import numpy as np

from .utils.shared_mem_guard import SharedMemoryGuard
from .utils.timer_wait import wait_until

BREATH_CYCLE = 4.0
BLINK_INTERVAL_BASE = 4.0


class NaturalRandomWalk:
    """自然随机漫步 - 模拟真实鼠标轨迹"""

    def __init__(self,
                 screen_width=1920,
                 screen_height=1080):

        self.x = screen_width / 2
        self.y = screen_height / 2
        self.vx = 0
        self.vy = 0
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.base_speed_min = 900
        self.base_speed_max = 1800
        self.inertia = 0.88
        self.jitter = 60

        self.dwell_timer = 0
        self.is_quick_click = False
        self.short_dwell_range = (0.2, 0.8)
        self.long_dwell_range = (2.0, 6.0)
        self.quick_click_prob_after_quick = 0.75

        self.bottom_weight = 0.5
        self.center_weight = 0.3

        self.target_x = self.x
        self.target_y = self.y
        self.target_reached = True
        self.current_speed = 800

    def _get_next_target(self):
        if self.is_quick_click and random.random() < self.quick_click_prob_after_quick:
            self.is_quick_click = True
            dwell_time = random.uniform(*self.short_dwell_range)
            self.current_speed = random.uniform(self.base_speed_min * 1.5, self.base_speed_max)
        else:
            self.is_quick_click = random.random() < 0.35
            dwell_time = random.uniform(*self.short_dwell_range) if self.is_quick_click else random.uniform(*self.long_dwell_range)
            self.current_speed = random.uniform(self.base_speed_min, self.base_speed_max * 0.8)

        self.dwell_timer = dwell_time

        if self.is_quick_click:
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(0.1, 0.4)
            self.target_x = self.x + dist * self.screen_width * math.cos(angle)
            self.target_y = self.y + dist * self.screen_height * math.sin(angle)
        else:
            rand = random.random()
            if rand < self.bottom_weight:
                self.target_x = random.uniform(0.1, 0.9) * self.screen_width
                self.target_y = random.uniform(0.5, 0.98) * self.screen_height
            elif rand < self.bottom_weight + self.center_weight:
                self.target_x = random.uniform(0.2, 0.8) * self.screen_width
                self.target_y = random.uniform(0.2, 0.8) * self.screen_height
            else:
                angle = random.uniform(0, 2 * math.pi)
                dist = random.uniform(0.3, 0.9)
                self.target_x = 0.5 + dist * math.cos(angle)
                self.target_y = 0.5 + dist * math.sin(angle)
                self.target_x *= self.screen_width
                self.target_y *= self.screen_height

        self.target_x = max(50, min(self.screen_width - 50, self.target_x))
        self.target_y = max(50, min(self.screen_height - 50, self.target_y))

    def update(self, dt):
        if self.target_reached:
            self.dwell_timer -= dt
            if self.dwell_timer <= 0:
                self._get_next_target()
                self.target_reached = False
        else:
            dx = self.target_x - self.x
            dy = self.target_y - self.y
            dist = math.sqrt(dx*dx + dy*dy)

            if dist < 5:
                self.target_reached = True
                self.x = self.target_x
                self.y = self.target_y
                self.vx = 0
                self.vy = 0
            else:
                dx, dy = dx/dist, dy/dist
                speed_factor = min(1.0, dist / 100)

                jitter_x = random.gauss(0, self.jitter * dt)
                jitter_y = random.gauss(0, self.jitter * dt)

                target_vx = dx * self.current_speed * speed_factor + jitter_x
                target_vy = dy * self.current_speed * speed_factor + jitter_y

                self.vx = self.vx * self.inertia + target_vx * (1 - self.inertia)
                self.vy = self.vy * self.inertia + target_vy * (1 - self.inertia)

                self.x += self.vx * dt
                self.y += self.vy * dt

        self.x = max(50, min(self.screen_width - 50, self.x))
        self.y = max(50, min(self.screen_height - 50, self.y))

        return self.x, self.y

    def get_as_ratio(self):
        x_ratio = (self.x / self.screen_width) * 2 - 1
        y_ratio = (self.y / self.screen_height) * 2 - 1
        return x_ratio, y_ratio


class HybridInputClientProcess(Process):
    def __init__(self, pose_position_shm: shared_memory.SharedMemory):
        super().__init__()
        self.pose_position_shm = pose_position_shm
        self.fps = Value('f', 60.0)

        self._mouse_x = Value('f', 0.5)
        self._mouse_y = Value('f', 0.5)
        self._audio_level = Value('f', 0.0)
        self._is_speaking = Value('i', 0)
        self._auto_mode = Value('i', 1)

    def set_mouse_position(self, x: float, y: float):
        self._mouse_x.value = max(0.0, min(1.0, x))
        self._mouse_y.value = max(0.0, min(1.0, y))

    def set_audio_level(self, level: float):
        self._audio_level.value = max(0.0, min(1.0, level))

    def set_speaking(self, speaking: bool):
        self._is_speaking.value = 1 if speaking else 0

    def set_auto_mode(self, enabled: bool):
        self._auto_mode.value = 1 if enabled else 0

    def run(self):
        last_time: float = time.perf_counter()
        interval: float = 1.0 / 60

        pose_position_shm_guard = SharedMemoryGuard(self.pose_position_shm, ctrl_name="pose_position_shm_ctrl")
        np_pose_shm = np.ndarray((45,), dtype=np.float32, buffer=self.pose_position_shm.buf[:45 * 4])
        np_position_shm = np.ndarray((4,), dtype=np.float32, buffer=self.pose_position_shm.buf[45 * 4:45 * 4 + 4 * 4])

        random_walk = NaturalRandomWalk(screen_width=1920, screen_height=1080)

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
            dt = current_time - last_time
            audio_level = self._audio_level.value
            is_speaking = self._is_speaking.value == 1
            auto_mode = self._auto_mode.value == 1

            if auto_mode:
                random_walk.update(interval)
                mouse_x, mouse_y = random_walk.get_as_ratio()
            else:
                mouse_x = self._mouse_x.value * 2 - 1
                mouse_y = self._mouse_y.value * 2 - 1

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

            if auto_mode:
                target_eye_x = mouse_x * eye_limit[0]
                target_eye_y = mouse_y * eye_limit[1]
            else:
                target_eye_x = (0.5 - self._mouse_x.value) * 2 * eye_limit[0]
                target_eye_y = (0.5 - self._mouse_y.value) * 2 * eye_limit[1]

            mouth_eye_vector[25] = target_eye_y + math.sin(current_time * 1.5) * 0.05
            mouth_eye_vector[26] = target_eye_x + math.sin(current_time * 2.0) * 0.1

            if auto_mode:
                target_head_x = mouse_y * 0.5
                target_head_y = mouse_x * 0.5
            else:
                target_head_x = (0.5 - self._mouse_y.value) * 2 * 0.5
                target_head_y = (0.5 - self._mouse_x.value) * 2 * 0.5

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
