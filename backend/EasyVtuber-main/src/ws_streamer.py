"""EasyVtuber WebSocket 帧推送模块"""

import asyncio
import base64
import logging
from typing import Callable

import cv2
import numpy as np
import websockets
from websockets.server import serve

logger = logging.getLogger(__name__)


class FrameStreamer:
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self._clients: set = set()
        self._server = None
        self._running = False
        self._latest_frame: np.ndarray | None = None
        self._frame_lock = asyncio.Lock()
        self._on_client_connect: Callable | None = None
        self._on_client_disconnect: Callable | None = None

    def set_on_client_connect(self, callback: Callable):
        self._on_client_connect = callback

    def set_on_client_disconnect(self, callback: Callable):
        self._on_client_disconnect = callback

    async def _handler(self, websocket, path):
        self._clients.add(websocket)
        client_addr = websocket.remote_address
        logger.info(f"WebSocket 客户端连接: {client_addr}, 当前连接数: {len(self._clients)}")
        
        if self._on_client_connect:
            await self._on_client_connect(websocket)
        
        try:
            async for message in websocket:
                if message == "ping":
                    await websocket.send("pong")
                elif message == "get_frame":
                    async with self._frame_lock:
                        if self._latest_frame is not None:
                            await self._send_frame(websocket, self._latest_frame)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info(f"WebSocket 客户端断开: {client_addr}, 当前连接数: {len(self._clients)}")
            
            if self._on_client_disconnect:
                await self._on_client_disconnect(websocket)

    async def _send_frame(self, websocket, frame: np.ndarray):
        if frame.shape[2] == 4:
            bgra_frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGRA)
            _, buffer = cv2.imencode('.png', bgra_frame)
        else:
            bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            _, buffer = cv2.imencode('.jpg', bgr_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        await websocket.send(frame_base64)

    async def broadcast_frame(self, frame: np.ndarray):
        async with self._frame_lock:
            self._latest_frame = frame.copy()
        
        if not self._clients:
            return
        
        if frame.shape[2] == 4:
            bgra_frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGRA)
            _, buffer = cv2.imencode('.png', bgra_frame)
        else:
            bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            _, buffer = cv2.imencode('.jpg', bgr_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        
        disconnected = set()
        for client in self._clients:
            try:
                await client.send(frame_base64)
            except Exception:
                disconnected.add(client)
        
        for client in disconnected:
            self._clients.discard(client)

    async def start(self):
        if self._running:
            return
        
        self._running = True
        self._server = await serve(
            self._handler,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=10,
        )
        logger.info(f"WebSocket 帧推送服务启动: ws://{self.host}:{self.port}")

    async def stop(self):
        if not self._running:
            return
        
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self._clients.clear()
        logger.info("WebSocket 帧推送服务已停止")

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def is_running(self) -> bool:
        return self._running


_frame_streamer: FrameStreamer | None = None


def get_frame_streamer(host: str = "localhost", port: int = 8765) -> FrameStreamer:
    global _frame_streamer
    if _frame_streamer is None:
        _frame_streamer = FrameStreamer(host=host, port=port)
    return _frame_streamer
