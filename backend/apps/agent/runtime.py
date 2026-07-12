from __future__ import annotations

import asyncio
import logging
import random
from enum import Enum

from apps.agent.capabilities.base import CapabilityRouter
from apps.agent.events import AgentEvent, EventInboxCapability
from apps.agent.graph import AgentGraph
from apps.agent.state import AgentRoute, AgentTurnOutcome
from apps.config import config

logger = logging.getLogger(__name__)


class AgentRuntimeStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    SLEEPING = "sleeping"
    STOPPING = "stopping"
    FAILED = "failed"


class AgentRuntime:
    """Long-lived scheduler. A graph invocation may end; the Agent does not."""

    def __init__(
        self,
        scenario_id: str,
        graph: AgentGraph,
        router: CapabilityRouter,
        events: EventInboxCapability,
        poll_when_waiting: bool = True,
    ) -> None:
        self.scenario_id = scenario_id
        self._graph = graph
        self._router = router
        self._events = events
        self._poll_when_waiting = poll_when_waiting
        self._status = AgentRuntimeStatus.STOPPED
        self._task: asyncio.Task[None] | None = None
        self._wake_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self.last_outcome: AgentTurnOutcome | None = None

    @property
    def status(self) -> AgentRuntimeStatus:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._status in {AgentRuntimeStatus.RUNNING, AgentRuntimeStatus.SLEEPING}

    @property
    def router(self) -> CapabilityRouter:
        return self._router

    async def start(self) -> None:
        async with self._lock:
            if self.is_running:
                return
            self._status = AgentRuntimeStatus.STARTING
            if not await self._router.health_check():
                self._status = AgentRuntimeStatus.FAILED
                raise RuntimeError("场景能力健康检查失败")
            self._task = asyncio.create_task(self._run_loop(), name=f"agent-runtime-{self.scenario_id}")
            self._status = AgentRuntimeStatus.RUNNING

    async def stop(self) -> None:
        async with self._lock:
            if self._status is AgentRuntimeStatus.STOPPED:
                return
            self._status = AgentRuntimeStatus.STOPPING
            self._wake_event.set()
            task = self._task
            self._task = None
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await self._graph.close()
            self._status = AgentRuntimeStatus.STOPPED

    async def close(self) -> None:
        await self.stop()
        await self._router.close()

    def wake(self) -> None:
        self._wake_event.set()

    async def publish(self, event: AgentEvent) -> None:
        await self._events.publish(event)
        self.wake()

    async def event_stats(self) -> dict[str, int]:
        return await self._events.stats()

    async def run_once(self) -> AgentTurnOutcome:
        outcome = await self._graph.run_turn()
        self.last_outcome = outcome
        return outcome

    async def _run_loop(self) -> None:
        while self._status not in {AgentRuntimeStatus.STOPPING, AgentRuntimeStatus.STOPPED}:
            try:
                # Clear before invocation. Events published during the graph
                # remain signalled and make the following wait return at once.
                self._wake_event.clear()
                self._status = AgentRuntimeStatus.RUNNING
                outcome = await self.run_once()
                if outcome.route in {AgentRoute.WAIT_EVENT, AgentRoute.GOAL_COMPLETED}:
                    wait_seconds = (
                        config.agent_poll_interval if self._poll_when_waiting else None
                    )
                    self._status = AgentRuntimeStatus.SLEEPING
                elif outcome.route is AgentRoute.SLEEP:
                    wait_seconds = config.agent_poll_interval
                    self._status = AgentRuntimeStatus.SLEEPING
                elif outcome.route in {AgentRoute.RETRY, AgentRoute.FAILED}:
                    wait_seconds = max(2.0, config.agent_poll_interval)
                else:
                    jitter = random.uniform(-config.agent_step_jitter, config.agent_step_jitter)
                    wait_seconds = max(0.2, config.agent_min_step_interval + jitter)
                try:
                    if wait_seconds is None:
                        await self._wake_event.wait()
                    else:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=wait_seconds)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("AgentRuntime scheduler failed")
                self._status = AgentRuntimeStatus.FAILED
                await asyncio.sleep(2)
