import os
_venv_root = os.path.join(os.path.dirname(__file__), '..', '..', '.venv')
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

import math
from multiprocessing import Process, Value, shared_memory, Event
import cv2
import numpy as np
import time
from .ezvtb_rt_interface import get_core
from .args import args
from .utils.shared_mem_guard import SharedMemoryGuard
from .utils.fps import FPS, Interval
from typing import List

class ModelClientProcess(Process):
    def __init__(self, input_image, pose_position_shm: shared_memory.SharedMemory , input_fps, output_debug=False, output_virtual_cam=False, alpha_split=False, green_screen=False):
        super().__init__()
        self.input_image = input_image
        self.pose_position_shm = pose_position_shm  # 45 floats for pose, 4 floats for position
        self._output_debug = output_debug
        self._output_virtual_cam = output_virtual_cam
        self._alpha_split = alpha_split
        self._green_screen = green_screen

        self.alpha_width_scale = 2 if self._alpha_split else 1
        self.ret_channels = 3 if self._output_virtual_cam or output_debug else 4
        self.ret_shape = (args.interpolation_scale, args.model_output_size, self.alpha_width_scale * args.model_output_size, self.ret_channels)
        self.ret_nbytes = self.alpha_width_scale * args.interpolation_scale * args.model_output_size * args.model_output_size * self.ret_channels # RGBA
        self.ret_shared_mem = shared_memory.SharedMemory(create=True, size=self.ret_nbytes)
        
        self.last_model_interval = Value('f', 0.0)
        self.average_model_interval = Value('f', 0.0)
        self.cache_hit_ratio = Value('f', 0.0)
        self.gpu_cache_hit_ratio = Value('f', 0.0)
        self.pipeline_fps_number = Value('f', 0.0)
        self.output_pipeline_fps = Value('f', 0.0)  # 由 main 进程更新，与 main print 一致
        self.input_fps = input_fps

        self.finish_event = Event()

    def run(self):
        import os as _os
        _venv_root = _os.path.join(_os.path.dirname(__file__), '..', '..', '.venv')
        _cudnn_bin = _os.path.join(_venv_root, 'Lib', 'site-packages', 'nvidia', 'cudnn', 'bin')
        _torch_lib = _os.path.join(_venv_root, 'Lib', 'site-packages', 'torch', 'lib')
        _cuda_bin = r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin'
        _os.environ['PATH'] = _cudnn_bin + ';' + _torch_lib + ';' + _cuda_bin + ';' + _os.environ.get('PATH', '')
        try:
            _os.add_dll_directory(_cudnn_bin)
            _os.add_dll_directory(_torch_lib)
            _os.add_dll_directory(_cuda_bin)
        except (AttributeError, OSError):
            pass

        args.output_debug = self._output_debug
        args.output_virtual_cam = self._output_virtual_cam
        args.alpha_split = self._alpha_split
        args.green_screen = self._green_screen

        import torch

        from .utils.pose_simplify import pose_simplify

        if getattr(args, 'mark_interpolated', False):
            _os.environ['EZVTB_MARK_INTERPOLATED'] = '1'
        pose_position_shm_guard = SharedMemoryGuard(self.pose_position_shm, ctrl_name="pose_position_shm_ctrl")
        np_pose_shm = np.ndarray((45,), dtype=np.float32, buffer=self.pose_position_shm.buf[:45 * 4])
        np_position_shm = np.ndarray((4,), dtype=np.float32, buffer=self.pose_position_shm.buf[45 * 4:45 * 4 + 4 * 4])
        
        ret_batch_shm_guard = [
            SharedMemoryGuard(self.ret_shared_mem, ctrl_name=f"ret_shm_ctrl_batch_{i}")
            for i in range(args.interpolation_scale)
        ]
        np_ret_shms = [
            np.ndarray((args.model_output_size, self.alpha_width_scale * args.model_output_size, self.ret_channels), dtype=np.uint8,
                        buffer=self.ret_shared_mem.buf[i * self.alpha_width_scale * args.model_output_size * args.model_output_size * self.ret_channels:
                                                       (i + 1) * self.alpha_width_scale * args.model_output_size * args.model_output_size * self.ret_channels])
            for i in range(args.interpolation_scale)
        ]

        model_infer_average_interval: Interval = Interval()
        pipeline_fps = FPS()

        # Use unified ezvtb_rt interface for both THA3 and THA4
        model = get_core(use_tensorrt=args.use_tensorrt,
                            model_version=args.model_version,
                            model_name=args.model_name,

                            model_seperable = args.model_seperable,
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
        model_infer_average_interval.start()
        model.inference([np.zeros((1, 45), dtype=np.float32)])  # Warm up
        model_infer_average_interval.stop()
        self.last_model_interval.value = model_infer_average_interval.last()

        last_pose = np.zeros((45,), dtype=np.float32)

        print("Model Inference Ready")
        while True:
            with pose_position_shm_guard.lock():
                np_pose = np_pose_shm.copy()
                np_position = np_position_shm.copy()

            input_poses = []
            increment = (np_pose - last_pose) / args.interpolation_scale
            for i in range(args.interpolation_scale):
                input_poses.append(pose_simplify(last_pose + increment * (i + 1)))
            last_pose = np_pose

            model_infer_average_interval.start()
            output_images = model.inference(input_poses)

            if args.max_ram_cache_len > 0:
                hits = model.cacher.hits
                miss = model.cacher.miss
                if args.use_sr:
                    hits += model.sr_cacher.hits
                    miss += model.sr_cacher.miss
                total = hits + miss
                self.cache_hit_ratio.value = (hits / total) if total > 0 else 0.0

            if args.use_tensorrt and args.max_gpu_cache_len > 0:
                hits = model.tha.cacher.hits
                miss = model.tha.cacher.miss
                total = hits + miss
                self.gpu_cache_hit_ratio.value = (hits / total) if total > 0 else 0.0

            output_images = self.post_process_ret(np_position, output_images)

            self.average_model_interval.value = model_infer_average_interval.stop()
            self.last_model_interval.value = model_infer_average_interval.last()

            self.pipeline_fps_number.value = pipeline_fps()
            for i in range(args.interpolation_scale):
                with ret_batch_shm_guard[i].lock(): # get pressure from main process if ret not consumed
                    np_ret_shms[i][:, :, :] = output_images[i]

            self.finish_event.set() # Back pressure main process loop if infer slow

    def post_process_ret(self, np_position: np.ndarray, output_images: np.ndarray) -> List[np.ndarray]:
        k_scale = 1
        rotate_angle = 0
        dx = 0
        dy = 0

        rm = cv2.getRotationMatrix2D((output_images[0].shape[1] / 2, output_images[0].shape[0] / 2), rotate_angle, k_scale)
        rm[0, 2] += dx + output_images[0].shape[1] / 2 - output_images[0].shape[1] / 2
        rm[1, 2] += dy + output_images[0].shape[0] / 2 - output_images[0].shape[0] / 2

        ret = []
        for i in range(output_images.shape[0]):
            bgra_image = output_images[i]
            bgra_image = cv2.warpAffine(
                bgra_image,
                rm,
                (bgra_image.shape[1], bgra_image.shape[0]))

            if args.output_debug:
                # 与 main.py 输出格式一致
                y = 16
                cv2.putText(bgra_image, 'INFER/S: {:.4f}'.format(self.pipeline_fps_number.value), (0, y), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                y += 16
                cv2.putText(bgra_image, 'INPUT/S: {:.4f}'.format(self.input_fps.value), (0, y), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                y += 16
                cv2.putText(bgra_image, 'OUTPUT/S: {:.4f}'.format(self.output_pipeline_fps.value), (0, y), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                y += 16
                cv2.putText(bgra_image, 'CALC: {:.2f} ms'.format(self.average_model_interval.value * 1000), (0, y), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                y += 16
                if args.max_ram_cache_len > 0:
                    cv2.putText(bgra_image, 'MEM CACHE: {:.2f}%'.format(self.cache_hit_ratio.value * 100), (0, y), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                    y += 16
                if args.max_gpu_cache_len > 0:
                    cv2.putText(bgra_image, 'GPU CACHE: {:.2f}%'.format(self.gpu_cache_hit_ratio.value * 100), (0, y), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                
            if args.alpha_split:
                rgba_image = cv2.cvtColor(bgra_image, cv2.COLOR_BGRA2RGBA)
                alpha_channel = rgba_image[:, :, 3]
                rgb_channels = rgba_image[:,:,:3]
                alpha_image = cv2.cvtColor(alpha_channel, cv2.COLOR_GRAY2RGB)
                rgb_channels = cv2.hconcat([rgb_channels, alpha_image])

            if args.output_debug:
                if args.alpha_split:
                    bgr_channels = cv2.cvtColor(rgb_channels, cv2.COLOR_RGB2BGR)
                else:
                    bgr_channels = cv2.cvtColor(bgra_image, cv2.COLOR_BGRA2BGR)
                ret.append(bgr_channels)
            elif args.output_virtual_cam:
                if getattr(args, 'green_screen', False):
                    rgb = cv2.cvtColor(bgra_image, cv2.COLOR_BGRA2RGB)
                    a = bgra_image[:, :, 3]
                    mask = (a > 0)[:, :, np.newaxis]
                    green = np.array([0, 255, 0], dtype=np.uint8)
                    rgb = np.where(mask, rgb, green)
                elif not args.alpha_split:
                    rgb = cv2.cvtColor(bgra_image, cv2.COLOR_BGRA2RGB)
                ret.append(rgb)
            else:
                rgba_image = cv2.cvtColor(bgra_image, cv2.COLOR_BGRA2RGBA)
                ret.append(rgba_image)
        return ret
    
if __name__ == "__main__":
    pass