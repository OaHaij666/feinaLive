"""游戏集成管理器 - 管理游戏 Graph（HostGraph 在 main.py 中独立启动）"""

import logging

from apps.ai.game_graph import GameGraph
from apps.ai.mcp.base_adapter import BaseGameAdapter
from apps.ai.messaging.queue import get_message_queue
from apps.ai.shared_context import SharedContext, get_shared_context

logger = logging.getLogger(__name__)


class GameManager:
    def __init__(self, shared_context: SharedContext | None = None):
        self._shared_context = shared_context or get_shared_context()
        self._game_graphs: dict[str, GameGraph] = {}
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def register_game(self, adapter: BaseGameAdapter):
        game_id = adapter.game_id
        if game_id in self._game_graphs:
            logger.warning(f"游戏 {game_id} 已注册，跳过")
            return

        graph = GameGraph(
            adapter=adapter,
            shared_context=self._shared_context,
        )
        self._game_graphs[game_id] = graph
        logger.info(f"游戏注册: {game_id}")

    def unregister_game(self, game_id: str):
        if game_id in self._game_graphs:
            del self._game_graphs[game_id]
            logger.info(f"游戏注销: {game_id}")

    async def start(self):
        if self._running:
            logger.warning("GameManager 已在运行")
            return

        for game_id, graph in self._game_graphs.items():
            await graph.start()

        self._running = True
        logger.info(f"GameManager 启动: {len(self._game_graphs)} 个游戏")

    async def stop(self):
        for game_id, graph in self._game_graphs.items():
            await graph.stop()

        self._running = False
        logger.info("GameManager 停止")

    def get_game_graphs(self) -> dict[str, GameGraph]:
        return dict(self._game_graphs)

    def mute(self):
        get_message_queue().mute()

    def unmute(self):
        get_message_queue().unmute()

    def get_game_status(self) -> dict:
        registered = list(self._game_graphs.keys())
        return {
            "running": self._running,
            "registered_games": registered,
            "games": {
                game_id: {
                    "running": graph.is_running,
                }
                for game_id, graph in self._game_graphs.items()
            },
            "queue": get_message_queue().get_stats(),
        }


_game_manager: GameManager | None = None


def get_game_manager() -> GameManager:
    global _game_manager
    if _game_manager is None:
        _game_manager = GameManager()
    return _game_manager
