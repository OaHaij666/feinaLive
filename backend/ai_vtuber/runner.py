"""EasyVtuber 启动入口 - AI 主播虚拟摄像头输出"""

import os
_venv_root = os.path.join(os.path.dirname(__file__), '..', '.venv')
_cudnn_bin = os.path.join(_venv_root, 'Lib', 'site-packages', 'nvidia', 'cudnn', 'bin')
_torch_lib = os.path.join(_venv_root, 'Lib', 'site-packages', 'torch', 'lib')
_cuda_bin = r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin'
os.environ['PATH'] = _cudnn_bin + ';' + _torch_lib + ';' + _cuda_bin + ';' + os.environ.get('PATH', '')
try:
    os.add_dll_directory(_cudnn_bin)
    os.add_dll_directory(_torch_lib)
    os.add_dll_directory(_cuda_bin)
except (AttributeError, OSError):
    pass

try:
    import pyvirtualcam
except ImportError:
    pyvirtualcam = None

import asyncio
import logging
import sys
import time
from multiprocessing import shared_memory
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

EASYVTUBER_DIR = Path(__file__).parent
sys.path.insert(0, str(EASYVTUBER_DIR))
sys.path.insert(0, str(EASYVTUBER_DIR / "src"))

from src.args import args
from src.utils.preprocess import resize_to_512_center, apply_color_curves
from src.utils.shared_mem_guard import SharedMemoryGuard
from src.utils.timer_wait import wait_until
from src.utils.fps import FPS

logger = logging.getLogger(__name__)


class EasyVtuberRunner:
    def __init__(
        self,
        character: str = "lambda_00",
        input_type: str = "debug",
        frame_rate: int = 30,
    ):
        self.character = character
        self.input_type = input_type
        self.frame_rate = frame_rate

        self._input_image: np.ndarray | None = None
        self._pose_position_shm: shared_memory.SharedMemory | None = None
        self._input_process = None
        self._infer_process = None
        self._running = False
        self._virtual_cam = None

    def _load_character_image(self) -> np.ndarray:
        img_path = EASYVTUBER_DIR / "data" / "images" / f"{self.character}.png"
        if not img_path.exists():
            raise FileNotFoundError(f"角色图片不存在: {img_path}")

        img = Image.open(img_path)
        img = img.convert('RGBA')
        ow, oh = img.size
        for i, px in enumerate(img.getdata()):
            if px[3] <= 0:
                y = i // ow
                x = i % ow
                img.putpixel((x, y), (0, 0, 0, 0))

        if ow != 512 or oh != 512:
            img = resize_to_512_center(img)

        if getattr(args, 'alpha_clean', False):
            curves = {'a': [(60, 0), (200, 255)]}
            img = apply_color_curves(img, curves)

        input_image = np.array(img)
        input_image = cv2.cvtColor(input_image, cv2.COLOR_RGBA2BGRA)
        logger.info(f"角色图片加载完成: {self.character}")
        return input_image

    def _setup_args(self):
        args.character = self.character
        args.frame_rate_limit = self.frame_rate
        args.debug_input = self.input_type == "debug"
        args.cam_input = self.input_type == "webcam"
        args.mouse_input = self.input_type == "mouse"
        args.osf_input = self.input_type == "openseeface"
        args.audio_input = self.input_type == "audio"
        args.hybrid_input = self.input_type == "hybrid"

        args.model_version = "v3"
        args.model_seperable = False
        args.model_half = False
        args.eyebrow = True
        args.simplify = 0
        args.use_tensorrt = False
        args.use_interpolation = False
        args.interpolation_scale = 1
        args.use_sr = False
        args.output_virtual_cam = True
        args.output_debug = False
        args.alpha_split = False
        args.green_screen = True
        args.breath_cycle = 4.0
        args.blink_interval = 5.0

        if not args.debug_input and not args.cam_input and not args.mouse_input and not args.audio_input and not args.hybrid_input and args.osf_input is None:
            args.debug_input = True

    async def start(self):
        if self._running:
            logger.warning("EasyVtuber 已在运行")
            return

        self._setup_args()
        self._input_image = self._load_character_image()

        self._pose_position_shm = shared_memory.SharedMemory(
            create=True,
            size=(45 + 4) * 4
        )

        self._input_process = self._create_input_process()
        if self._input_process:
            self._input_process.daemon = True
            self._input_process.start()

        self._infer_process = self._create_infer_process()
        if self._infer_process:
            self._infer_process.daemon = True
            self._infer_process.start()

        self._running = True
        logger.info("EasyVtuber 启动完成，虚拟摄像头输出")

    def _create_input_process(self):
        if args.debug_input:
            from src.debug_input_client import DebugInputClientProcess
            return DebugInputClientProcess(self._pose_position_shm)
        elif args.cam_input:
            from src.face_mesh_client import FaceMeshClientProcess
            return FaceMeshClientProcess(self._pose_position_shm)
        elif args.mouse_input:
            from src.mouse_client import MouseClientProcess
            return MouseClientProcess(self._pose_position_shm)
        elif args.osf_input:
            from src.open_see_face_client import OSFClientProcess
            return OSFClientProcess(self._pose_position_shm)
        elif args.audio_input:
            from src.audio_client import AudioDrivenClientProcess
            return AudioDrivenClientProcess(self._pose_position_shm)
        elif args.hybrid_input:
            from src.hybrid_input_client import HybridInputClientProcess
            return HybridInputClientProcess(self._pose_position_shm)
        return None

    def _create_infer_process(self):
        from src.model_infer_client import ModelClientProcess
        input_fps = self._input_process.fps if self._input_process else None
        return ModelClientProcess(
            self._input_image,
            self._pose_position_shm,
            input_fps,
            output_debug=getattr(args, 'output_debug', False),
            output_virtual_cam=args.output_virtual_cam,
            alpha_split=args.alpha_split,
            green_screen=args.green_screen,
        )

    async def stop(self):
        if not self._running:
            return

        self._running = False

        if self._virtual_cam:
            self._virtual_cam.close()
            self._virtual_cam = None

        if self._input_process:
            self._input_process.terminate()

        if self._infer_process:
            self._infer_process.terminate()

        if self._pose_position_shm:
            self._pose_position_shm.close()
            self._pose_position_shm.unlink()

        logger.info("EasyVtuber 已停止")

    async def run_loop(self):
        if not self._infer_process:
            logger.error("推理进程未启动")
            return

        cam_width_scale = 2 if getattr(args, 'alpha_split', False) else 1
        ret_channels = 3 if getattr(args, 'output_virtual_cam', False) or getattr(args, 'output_debug', False) else 4

        ret_batch_shm_channels = [
            SharedMemoryGuard(self._infer_process.ret_shared_mem, ctrl_name=f"ret_shm_ctrl_batch_{i}")
            for i in range(getattr(args, 'interpolation_scale', 1))
        ]

        np_ret_shms = [
            np.ndarray(
                (getattr(args, 'model_output_size', 512),
                 cam_width_scale * getattr(args, 'model_output_size', 512),
                 ret_channels),
                dtype=np.uint8,
                buffer=self._infer_process.ret_shared_mem.buf[
                    i * cam_width_scale * getattr(args, 'model_output_size', 512) *
                    getattr(args, 'model_output_size', 512) * ret_channels:
                    (i + 1) * cam_width_scale * getattr(args, 'model_output_size', 512) *
                    getattr(args, 'model_output_size', 512) * ret_channels]
            )
            for i in range(getattr(args, 'interpolation_scale', 1))
        ]

        last_time: float = time.perf_counter()
        interval: float = 1.0 / self.frame_rate if self.frame_rate > 0 else 0.0
        n_frames = getattr(args, 'interpolation_scale', 1)

        if args.output_virtual_cam:
            if pyvirtualcam is None:
                logger.warning("pyvirtualcam 不可用，虚拟摄像头输出被禁用")
                args.output_virtual_cam = False
            else:
                self._virtual_cam = pyvirtualcam.Camera(
                    width=cam_width_scale * getattr(args, 'model_output_size', 512),
                    height=getattr(args, 'model_output_size', 512),
                    fps=self.frame_rate,
                    backend='obs',
                    fmt=pyvirtualcam.PixelFormat.RGB
                )
                logger.info(f"虚拟摄像头已启动: {self._virtual_cam.device}")

        logger.info("EasyVtuber 渲染循环启动")

        while self._running:
            self._infer_process.finish_event.wait()
            self._infer_process.finish_event.clear()

            for i in range(n_frames):
                ret_batch_shm_channels[i].acquire()

            for i in range(n_frames):
                target_send_time = last_time + i * (interval * n_frames / n_frames)
                if interval > 0:
                    wait_until(target_send_time)

                frame = np_ret_shms[i]

                if self._virtual_cam:
                    self._virtual_cam.send(frame)

                if interval > 0:
                    last_time += interval

                ret_batch_shm_channels[i].release()

            await asyncio.sleep(0.001)

    @property
    def is_running(self) -> bool:
        return self._running


_runner: EasyVtuberRunner | None = None


def get_easyvtuber_runner(
    character: str = "lambda_00",
    input_type: str = "debug",
    frame_rate: int = 30,
) -> EasyVtuberRunner:
    global _runner
    if _runner is None:
        _runner = EasyVtuberRunner(
            character=character,
            input_type=input_type,
            frame_rate=frame_rate,
        )
    return _runner


async def main():
    import argparse as ap

    parser = ap.ArgumentParser()
    parser.add_argument("--character", type=str, default="lambda_00")
    parser.add_argument("--input", type=str, default="debug", choices=["debug", "webcam", "mouse", "openseeface"])
    parser.add_argument("--frame-rate", type=int, default=30)
    cli_args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    runner = get_easyvtuber_runner(
        character=cli_args.character,
        input_type=cli_args.input,
        frame_rate=cli_args.frame_rate,
    )

    try:
        await runner.start()
        await runner.run_loop()
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    finally:
        await runner.stop()


if __name__ == "__main__":
    asyncio.run(main())
