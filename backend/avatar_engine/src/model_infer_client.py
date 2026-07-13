from __future__ import annotations

import queue
import traceback
from multiprocessing import Event, Process, Queue, Value, shared_memory

import cv2
import numpy as np

from avatar_engine.config import EngineConfig, apply_engine_config
from avatar_engine.windows_runtime import configure_windows_runtime

from .args import args
from .utils.fps import FPS, Interval
from .utils.shared_mem_guard import SharedMemoryGuard


class ModelClientProcess(Process):
    def __init__(
        self,
        input_image: np.ndarray,
        pose_position_shm: shared_memory.SharedMemory,
        *,
        runtime_config: EngineConfig,
    ) -> None:
        super().__init__()
        self.input_image = input_image
        self.pose_position_shm = pose_position_shm
        self.runtime_config = runtime_config
        self.ret_shape = (
            runtime_config.interpolation,
            runtime_config.output_size,
            runtime_config.output_size,
            4,
        )
        self.ret_shared_mem = shared_memory.SharedMemory(
            create=True,
            size=int(np.prod(self.ret_shape)),
        )
        self.last_model_interval = Value("f", 0.0)
        self.average_model_interval = Value("f", 0.0)
        self.cache_hit_ratio = Value("f", 0.0)
        self.gpu_cache_hit_ratio = Value("f", 0.0)
        self.pipeline_fps_number = Value("f", 0.0)
        self.finish_event = Event()
        self.ready_event = Event()
        self.error_queue: Queue = Queue(maxsize=1)

    def run(self) -> None:
        try:
            self._run_renderer()
        except Exception:
            try:
                self.error_queue.put_nowait(traceback.format_exc())
            except queue.Full:
                pass

    def _run_renderer(self) -> None:
        configure_windows_runtime()
        apply_engine_config(self.runtime_config)
        from .ezvtb_rt_interface import get_core
        from .utils.pose_simplify import pose_simplify

        pose_guard = SharedMemoryGuard(
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
        frame_guards = [
            SharedMemoryGuard(
                self.ret_shared_mem,
                ctrl_name=f"feina_avatar_frame_{index}",
            )
            for index in range(self.runtime_config.interpolation)
        ]
        frame_size = self.runtime_config.output_size ** 2 * 4
        frames = [
            np.ndarray(
                (self.runtime_config.output_size, self.runtime_config.output_size, 4),
                dtype=np.uint8,
                buffer=self.ret_shared_mem.buf[index * frame_size : (index + 1) * frame_size],
            )
            for index in range(self.runtime_config.interpolation)
        ]

        model = get_core(
            use_tensorrt=args.use_tensorrt,
            model_version=args.model_version,
            model_name=args.model_name,
            model_seperable=args.model_seperable,
            model_half=args.model_half,
            model_cache_size=args.max_gpu_cache_len,
            model_use_eyebrow=args.eyebrow,
            use_interpolation=args.use_interpolation,
            interpolation_scale=args.interpolation_scale,
            interpolation_half=args.interpolation_half,
            cacher_ram_size=args.max_ram_cache_len,
            use_sr=args.use_sr,
            sr_half=args.sr_half,
            sr_x4=args.sr_x4,
            sr_a4k=args.sr_a4k,
        )
        model.setImage(self.input_image)
        model_interval = Interval()
        model_interval.start()
        model.inference([np.zeros((1, 45), dtype=np.float32)])
        model_interval.stop()
        self.last_model_interval.value = model_interval.last()
        self.ready_event.set()

        last_pose = np.zeros((45,), dtype=np.float32)
        pipeline_fps = FPS()
        while True:
            with pose_guard.lock():
                pose = pose_view.copy()
                position = position_view.copy()
            increment = (pose - last_pose) / self.runtime_config.interpolation
            input_poses = [
                pose_simplify(last_pose + increment * (index + 1))
                for index in range(self.runtime_config.interpolation)
            ]
            last_pose = pose

            model_interval.start()
            output_images = model.inference(input_poses)
            self.average_model_interval.value = model_interval.stop()
            self.last_model_interval.value = model_interval.last()
            self.pipeline_fps_number.value = pipeline_fps()
            output_images = self._post_process(position, output_images)

            for index, frame in enumerate(output_images):
                with frame_guards[index].lock():
                    frames[index][:] = frame
            self.finish_event.set()

    @staticmethod
    def _post_process(position: np.ndarray, output_images) -> list[np.ndarray]:
        scale = max(float(position[3]), 0.01)
        first = output_images[0]
        transform = cv2.getRotationMatrix2D(
            (first.shape[1] / 2, first.shape[0] / 2),
            0,
            scale,
        )
        transform[0, 2] += float(position[0]) * first.shape[1]
        transform[1, 2] += float(position[1]) * first.shape[0]
        frames: list[np.ndarray] = []
        for image in output_images:
            bgra = cv2.warpAffine(
                image,
                transform,
                (image.shape[1], image.shape[0]),
            )
            frames.append(cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA))
        return frames

    def failure_reason(self) -> str:
        try:
            return str(self.error_queue.get_nowait())
        except queue.Empty:
            return ""

    def close_parent_resources(self) -> None:
        try:
            self.ret_shared_mem.close()
        finally:
            try:
                self.ret_shared_mem.unlink()
            except FileNotFoundError:
                pass
        self.error_queue.close()
