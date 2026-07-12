"""游戏集成管理器 - 管理游戏 Graph（HostGraph 在 main.py 中独立启动）"""

import logging

from apps.ai.game_graph import GameGraph
from apps.ai.mcp.adapter import MCPGameAdapter
from apps.ai.messaging.queue import get_message_queue
from apps.ai.shared_context import SharedContext, get_shared_context

logger = logging.getLogger(__name__)


class GameManager:
    def __init__(self, shared_context: SharedContext | None = None):
        self._shared_context = shared_context or get_shared_context()
        self._game_graph: GameGraph | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def configure_single_game(self, adapter: MCPGameAdapter) -> None:
        """Replace the configured game while stopped.

        The live product currently permits one active game integration at a time.
        """
        if self._running:
            raise RuntimeError("游戏运行中，不能切换当前游戏")
        self._game_graph = GameGraph(
            adapter=adapter,
            shared_context=self._shared_context,
        )
        logger.info("当前游戏配置: %s", adapter.game_id)

    async def start(self):
        if self._running:
            logger.warning("GameManager 已在运行")
            return

        if self._game_graph is None:
            raise RuntimeError("尚未配置游戏")
        await self._game_graph.start()
        self._running = self._game_graph.is_running
        logger.info("GameManager 启动: %s", self._running)

    async def stop(self):
        if self._game_graph is not None:
            await self._game_graph.stop()

        self._running = False
        logger.info("GameManager 停止")

    @property
    def current_graph(self) -> GameGraph | None:
        return self._game_graph

    def mute(self):
        get_message_queue().mute()

    def unmute(self):
        get_message_queue().unmute()

    def get_game_status(self) -> dict:
        from apps.ai.memory.engine import get_memory_engine

        graph = self._game_graph
        game_id = graph.game_id if graph else ""
        return {
            "running": self._running,
            "selected_game_id": get_memory_engine().selected_game_id,
            "configured_game_id": game_id,
            "game": {"game_id": game_id, "running": bool(graph and graph.is_running)},
            "queue": get_message_queue().get_stats(),
        }


_game_manager: GameManager | None = None


def get_game_manager() -> GameManager:
    global _game_manager
    if _game_manager is None:
        _game_manager = GameManager()
    return _game_manager
