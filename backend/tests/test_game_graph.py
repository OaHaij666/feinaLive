"""测试 GameGraph 独立运行

用法: python -m tests.test_game_graph
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.ai.game_graph import GameGraph
from apps.ai.mcp.adapters.slay_the_spire import SlayTheSpireAdapter
from apps.ai.shared_context import get_shared_context
from apps.config import config

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    logger.info(f"MCP URL: {config.game_mcp_url}")
    logger.info(f"Game Model: {config.game_model}")
    logger.info(f"Poll Interval: {config.game_poll_interval}s")

    adapter = SlayTheSpireAdapter()
    
    logger.info("检查 MCP 服务健康状态...")
    healthy = await adapter.health_check()
    if not healthy:
        logger.error("MCP 服务不可用，请确保 MCP 服务已启动")
        logger.error("MCP 服务地址: " + config.game_mcp_url)
        return
    
    logger.info("MCP 服务正常")

    shared_context = get_shared_context()
    
    game_graph = GameGraph(
        adapter=adapter,
        shared_context=shared_context,
    )

    logger.info("启动 GameGraph...")
    await game_graph.start()

    logger.info("GameGraph 运行中，按 Ctrl+C 停止...")
    
    try:
        while game_graph.is_running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到停止信号...")
    
    await game_graph.stop()
    logger.info("测试结束")


if __name__ == "__main__":
    asyncio.run(main())
