"""EasyVtuber 集成模块 - 供 feinaLive 后端调用"""

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

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

EASYVTUBER_DIR = Path(__file__).parent.parent.parent / "ai_vtuber"


class EasyVtuberManager:
    def __init__(self):
        self._runner = None
        self._task: asyncio.Task | None = None
        self._started = False

    async def start(self):
        if self._started:
            logger.warning("EasyVtuber 已启动")
            return

        if not EASYVTUBER_DIR.exists():
            logger.error(f"EasyVtuber 目录不存在: {EASYVTUBER_DIR}")
            return

        sys.path.insert(0, str(EASYVTUBER_DIR))
        sys.path.insert(0, str(EASYVTUBER_DIR / "src"))

        try:
            from apps.config import config

            if not config.easyvtuber_enabled:
                logger.info("EasyVtuber 未启用")
                return

            from runner import get_easyvtuber_runner

            self._runner = get_easyvtuber_runner(
                character=config.easyvtuber_character,
                input_type=config.easyvtuber_input_type,
                ws_host=config.easyvtuber_ws_host,
                ws_port=config.easyvtuber_ws_port,
                frame_rate=config.easyvtuber_frame_rate,
            )

            await self._runner.start()
            self._task = asyncio.create_task(self._runner.run_loop())
            self._started = True
            logger.info("EasyVtuber 启动成功")

        except ImportError as e:
            logger.error(f"EasyVtuber 依赖未安装: {e}")
            logger.info("请运行: uv pip install -e '.[easyvtuber]'")
        except Exception as e:
            logger.error(f"EasyVtuber 启动失败: {e}")

    async def stop(self):
        if not self._started or not self._runner:
            return

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        await self._runner.stop()
        self._started = False
        logger.info("EasyVtuber 已停止")

    async def restart(self):
        await self.stop()
        await self.start()

    @property
    def is_running(self) -> bool:
        return self._started and self._runner is not None

    @property
    def client_count(self) -> int:
        if self._runner:
            return self._runner.client_count
        return 0

    def get_runner(self):
        return self._runner

    def get_input_process(self):
        if self._runner and hasattr(self._runner, '_input_process'):
            return self._runner._input_process
        return None

    def set_mouse_position(self, x: float, y: float):
        input_process = self.get_input_process()
        if input_process and hasattr(input_process, 'set_mouse_position'):
            input_process.set_mouse_position(x, y)

    def set_audio_level(self, level: float):
        input_process = self.get_input_process()
        if input_process and hasattr(input_process, 'set_audio_level'):
            input_process.set_audio_level(level)

    def set_speaking(self, speaking: bool):
        input_process = self.get_input_process()
        if input_process and hasattr(input_process, 'set_speaking'):
            input_process.set_speaking(speaking)


_manager: EasyVtuberManager | None = None


def get_easyvtuber_manager() -> EasyVtuberManager:
    global _manager
    if _manager is None:
        _manager = EasyVtuberManager()
    return _manager
