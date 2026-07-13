"""Nginx RTMP 服务管理"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

NGINX_DIR = Path(__file__).parent.parent.parent / "nginx-rtmp-win32"
NGINX_EXE = NGINX_DIR / "nginx.exe"
NGINX_CONF = NGINX_DIR / "conf" / "nginx.conf"
HLS_DIR = NGINX_DIR / "hls"

HTTP_PORT = 8088
CONSOLE_PORT = 8089
HLS_URL = f"http://localhost:{HTTP_PORT}/hls/stream.m3u8"
LIVE_FRONTEND_URL = f"http://localhost:{HTTP_PORT}"
CONSOLE_URL = f"http://localhost:{CONSOLE_PORT}"


class NginxService:
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._is_running = False

    def _ensure_hls_dir(self):
        HLS_DIR.mkdir(parents=True, exist_ok=True)

    def start(self) -> bool:
        if self._is_running:
            logger.warning("Nginx is already running")
            return True

        if not NGINX_EXE.exists():
            logger.error(f"Nginx executable not found: {NGINX_EXE}")
            return False

        self._ensure_hls_dir()

        try:
            pid_file = NGINX_DIR / "logs" / "nginx.pid"
            if pid_file.exists():
                try:
                    existing_pid = int(pid_file.read_text(encoding="utf-8").strip())
                    if existing_pid > 0:
                        os.kill(existing_pid, 0)
                        subprocess.run(
                            [str(NGINX_EXE), "-s", "reload", "-c", str(NGINX_CONF)],
                            cwd=str(NGINX_DIR),
                            check=True,
                            capture_output=True,
                        )
                        self._is_running = True
                        logger.info("Reloaded existing Nginx process pid=%s", existing_pid)
                        return True
                except (OSError, ValueError, subprocess.SubprocessError):
                    logger.warning("Stale Nginx pid file found; starting a new process")
            self._process = subprocess.Popen(
                [str(NGINX_EXE), "-c", str(NGINX_CONF)],
                cwd=str(NGINX_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._is_running = True
            logger.info("Nginx HTTP proxy started")
            return True
        except Exception as e:
            logger.error(f"Failed to start Nginx: {e}")
            return False

    def stop(self):
        if not self._is_running:
            logger.warning("Nginx is not running")
            return

        try:
            subprocess.Popen(
                [str(NGINX_EXE), "-s", "stop"],
                cwd=str(NGINX_DIR),
            )
            if self._process is not None:
                self._process.wait(timeout=5)
        except Exception as e:
            logger.error(f"Error stopping Nginx: {e}")
            try:
                if self._process is not None:
                    self._process.kill()
            except Exception:
                pass
        finally:
            self._is_running = False
            self._process = None
            logger.info("Nginx HTTP proxy stopped")

    def is_running(self) -> bool:
        return self._is_running

    def get_stream_urls(self) -> dict:
        return {
            "hls_url": HLS_URL,
            "frontend_url": LIVE_FRONTEND_URL,
            "live_frontend_url": LIVE_FRONTEND_URL,
            "console_url": CONSOLE_URL,
        }


_nginx_service: Optional[NginxService] = None


def get_nginx_service() -> NginxService:
    global _nginx_service
    if _nginx_service is None:
        _nginx_service = NginxService()
    return _nginx_service


async def start_nginx():
    service = get_nginx_service()
    if service.start():
        logger.info(f"Live frontend available at: {LIVE_FRONTEND_URL}")
        logger.info(f"Control console available at: {CONSOLE_URL}")
        logger.info(f"HLS stream available at: {HLS_URL}")


async def stop_nginx():
    service = get_nginx_service()
    service.stop()
