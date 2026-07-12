from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from apps.agent.state import CapabilityCall, CapabilityResult, Observation

logger = logging.getLogger(__name__)


class Capability(ABC):
    source: str

    @abstractmethod
    async def definitions(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def owns(self, name: str) -> bool: ...

    @abstractmethod
    def is_readonly(self, name: str) -> bool: ...

    @abstractmethod
    async def execute(self, call: CapabilityCall) -> CapabilityResult: ...

    async def observe(self) -> Observation | None:
        return None

    async def health_check(self) -> bool:
        return True

    async def handle_terminal(self, observation: Observation) -> bool:
        return False

    async def close(self) -> None:
        return None


class CapabilityRouter:
    def __init__(self, capabilities: list[Capability]) -> None:
        self._capabilities = tuple(capabilities)

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return self._capabilities

    async def definitions(self) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        for capability in self._capabilities:
            definitions.extend(await capability.definitions())
        return definitions

    def resolve(self, name: str) -> Capability | None:
        return next((item for item in self._capabilities if item.owns(name)), None)

    def validate(self, call: CapabilityCall) -> CapabilityCall | None:
        owner = self.resolve(call.name)
        if owner is None:
            return None
        call.readonly = owner.is_readonly(call.name)
        return call

    async def execute(self, call: CapabilityCall) -> CapabilityResult:
        owner = self.resolve(call.name)
        if owner is None:
            return CapabilityResult(call=call, success=False, error="未注册的能力")
        return await owner.execute(call)

    async def observations(self, exclude_sources: set[str] | None = None) -> list[Observation]:
        observations: list[Observation] = []
        capabilities = [
            capability
            for capability in self._capabilities
            if not exclude_sources or capability.source not in exclude_sources
        ]
        results = await asyncio.gather(
            *(capability.observe() for capability in capabilities),
            return_exceptions=True,
        )
        for capability, item in zip(capabilities, results):
            if isinstance(item, asyncio.CancelledError):
                raise item
            if isinstance(item, BaseException):
                logger.warning("Capability observation failed: %s: %s", capability.source, item)
                observations.append(
                    Observation(
                        source=capability.source,
                        summary=f"{capability.source} 观察失败: {item}",
                        data={"error": str(item)},
                        actionable=False,
                    )
                )
                continue
            if item is not None:
                observations.append(item)
        return observations

    async def health_check(self) -> bool:
        checks = [await item.health_check() for item in self._capabilities]
        return all(checks)

    async def handle_terminal(self, observation: Observation) -> bool:
        handled = False
        for capability in self._capabilities:
            if capability.source == observation.source:
                handled = await capability.handle_terminal(observation) or handled
        return handled

    async def close(self) -> None:
        for capability in self._capabilities:
            await capability.close()
