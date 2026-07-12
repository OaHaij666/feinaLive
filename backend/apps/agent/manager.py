"""Process-bound AgentRuntime manager."""

from __future__ import annotations

import logging
from typing import Any

from apps.agent.capabilities.base import CapabilityRouter
from apps.agent.capabilities.registry import get_capability_registry
from apps.agent.commentary import CommentaryComposer
from apps.agent.events import AgentEvent
from apps.agent.graph import AgentGraph
from apps.agent.mutual_context import MutualContext, get_mutual_context
from apps.agent.runtime import AgentRuntime
from apps.agent.scenarios.registry import ScenarioRuntimeDefinition, create_scenario
from apps.ai.messaging.queue import get_message_queue
from apps.config import config

logger = logging.getLogger(__name__)


class AgentManager:
    """Own one immutable startup scenario and its long-running AgentRuntime."""

    def __init__(
        self,
        definition: ScenarioRuntimeDefinition | None = None,
        mutual_context: MutualContext | None = None,
    ) -> None:
        self._mutual_context = mutual_context or get_mutual_context()
        self._definition: ScenarioRuntimeDefinition | None = None
        self._runtime: AgentRuntime | None = None
        self._configuration_error = ""
        if definition is not None:
            self._bind_scenario(definition)

    @property
    def is_running(self) -> bool:
        return bool(self._runtime and self._runtime.is_running)

    @property
    def current_runtime(self) -> AgentRuntime | None:
        return self._runtime

    @property
    def startup_config(self) -> dict[str, Any]:
        return dict(self._definition.startup_config) if self._definition else {}

    @property
    def needs_restart(self) -> bool:
        if not self._definition:
            return True
        startup = self._definition.startup_config
        return any(
            (
                startup.get("scenario_id") != config.agent_scenario_id,
                startup.get("mcp_url") != config.agent_mcp_url,
                startup.get("scenario_config") != config.agent_scenario_config,
            )
        )

    def _bind_scenario(self, definition: ScenarioRuntimeDefinition) -> None:
        if self._definition is not None:
            raise RuntimeError("场景已在进程启动时绑定；修改配置后必须重启应用")
        self._definition = definition
        self._runtime = self._build_runtime(definition)
        logger.info("启动场景已绑定: %s", definition.spec.id)

    async def start(self) -> None:
        if self._runtime is None or self._definition is None:
            raise RuntimeError(self._configuration_error or "启动场景配置无效")
        if self.is_running:
            return
        from apps.ai.memory.engine import get_memory_engine

        engine = get_memory_engine()
        scope = self._definition.spec.memory_scope
        if self._definition.memory_policy is not None:
            engine.register_game_policy(scope, self._definition.memory_policy)
            await engine.select_game(scope)
            await engine.ensure_game_session(scope)
        await self._runtime.start()
        logger.info("AgentRuntime 启动: %s", self._definition.spec.id)

    async def stop(self) -> None:
        if self._runtime is None or self._definition is None:
            return
        if self._runtime.is_running:
            await self._runtime.stop()
        try:
            from apps.ai.memory.engine import get_memory_engine

            engine = get_memory_engine()
            scope = self._definition.spec.memory_scope
            if self._definition.memory_policy is not None:
                await engine.summarize_session_memory(game_id=scope, force=True)
                await engine.persist_session_snapshot(scope)
        except Exception:
            logger.exception("AgentRuntime 停止时刷新记忆失败")

    async def shutdown(self) -> None:
        await self.stop()
        if self._runtime is not None:
            await self._runtime.close()

    async def health_check(self) -> bool:
        if not self._runtime:
            return False
        return await self._runtime.router.health_check()

    async def publish_event(
        self,
        event_type: str,
        source: str,
        payload: dict[str, Any] | None = None,
    ) -> AgentEvent:
        if self._runtime is None:
            raise RuntimeError(self._configuration_error or "启动场景配置无效")
        if self._definition is None or "events" not in self._definition.spec.capabilities:
            raise RuntimeError("当前场景未启用 events Capability")
        event = AgentEvent(event_type=event_type, source=source, payload=dict(payload or {}))
        await self._runtime.publish(event)
        return event

    def mute(self) -> None:
        get_message_queue().mute()

    def unmute(self) -> None:
        get_message_queue().unmute()

    async def get_status(self) -> dict[str, Any]:
        scenario_id = self._definition.spec.id if self._definition else ""
        status = self._runtime.status.value if self._runtime else "unconfigured"
        return {
            "running": self.is_running,
            "runtime_status": status,
            "configured_scenario_id": scenario_id,
            "startup_config": self.startup_config,
            "restart_required": self.needs_restart,
            "configuration_error": self._configuration_error,
            "scenario": {"scenario_id": scenario_id, "running": self.is_running},
            "events": await self._runtime.event_stats() if self._runtime else {"pending": 0, "dropped": 0},
            "queue": get_message_queue().get_stats(),
        }

    def _build_runtime(self, definition: ScenarioRuntimeDefinition) -> AgentRuntime:
        spec = definition.spec
        assembly = get_capability_registry().build(
            spec,
            self._mutual_context,
            definition.capability_resources,
        )
        router = CapabilityRouter(assembly.router_capabilities)
        graph = AgentGraph(
            scenario=spec,
            capability_router=router,
            mutual_context=self._mutual_context,
            commentary=(CommentaryComposer(spec, self._mutual_context) if assembly.host_speech else None),
            host_speech=assembly.host_speech,
        )
        return AgentRuntime(
            spec.id,
            graph,
            router,
            assembly.events,
            poll_when_waiting="mcp" in spec.capabilities,
        )


_agent_manager: AgentManager | None = None


def get_agent_manager() -> AgentManager:
    global _agent_manager
    if _agent_manager is None:
        manager = AgentManager()
        try:
            manager._bind_scenario(
                create_scenario(
                    config.agent_scenario_id,
                    mcp_url=config.agent_mcp_url,
                    scenario_config=config.agent_scenario_config,
                )
            )
        except (TypeError, ValueError) as exc:
            manager._configuration_error = str(exc)
            logger.error("启动场景绑定失败: %s", exc)
        _agent_manager = manager
    return _agent_manager
