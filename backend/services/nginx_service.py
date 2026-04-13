"""Nginx RTMP 服务管理"""

import os
import subprocess
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

NGINX_DIR = Path(__file__).parent.parent.parent / "nginx-rtmp-win32"
NGINX_EXE = NGINX_DIR / "nginx.exe"
NGINX_CONF = NGINX_DIR / "conf" / "nginx.conf"
HLS_DIR = NGINX_DIR / "hls"

RTMP_URL = "rtmp://localhost:1935/live/stream"
HLS_URL = "http://localhost:8080/hls/stream.m3u8"
STAT_URL = "http://localhost:8080/stat"


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
            self._process = subprocess.Popen(
                [str(NGINX_EXE), "-c", str(NGINX_CONF)],
                cwd=str(NGINX_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._is_running = True
            logger.info("Nginx RTMP service started")
            return True
        except Exception as e:
            logger.error(f"Failed to start Nginx: {e}")
            return False

    def stop(self):
        if not self._is_running or self._process is None:
            logger.warning("Nginx is not running")
            return

        try:
            subprocess.Popen(
                [str(NGINX_EXE), "-s", "stop"],
                cwd=str(NGINX_DIR),
            )
            self._process.wait(timeout=5)
        except Exception as e:
            logger.error(f"Error stopping Nginx: {e}")
            try:
                self._process.kill()
            except Exception:
                pass
        finally:
            self._is_running = False
            self._process = None
            logger.info("Nginx RTMP service stopped")

    def is_running(self) -> bool:
        return self._is_running

    def get_stream_urls(self) -> dict:
        return {
            "rtmp_url": RTMP_URL,
            "hls_url": HLS_URL,
            "stat_url": STAT_URL,
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
        logger.info(f"RTMP stream available at: {RTMP_URL}")
        logger.info(f"HLS stream available at: {HLS_URL}")


async def stop_nginx():
    service = get_nginx_service()
    service.stop()
