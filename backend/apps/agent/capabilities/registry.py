from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from apps.agent.capabilities.base import Capability
from apps.agent.capabilities.host_speech import HostSpeechCapability
from apps.agent.capabilities.mcp import MCPCapability
from apps.agent.capabilities.memory import MemoryCapability
from apps.agent.definition import ScenarioSpec
from apps.agent.events import EventInboxCapability
from apps.agent.mutual_context import MutualContext


@dataclass(slots=True)
class CapabilityBuildContext:
    spec: ScenarioSpec
    mutual_context: MutualContext
    events: EventInboxCapability
    resources: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CapabilityAssembly:
    router_capabilities: list[Capability]
    events: EventInboxCapability
    host_speech: HostSpeechCapability | None = None


CapabilityBuilder = Callable[[CapabilityBuildContext], Capability | HostSpeechCapability]


class CapabilityRegistry:
    """Build only the capability sources declared by the immutable ScenarioSpec."""

    def __init__(self) -> None:
        self._builders: dict[str, CapabilityBuilder] = {}

    def register(self, source: str, builder: CapabilityBuilder) -> None:
        if source in self._builders:
            raise ValueError(f"capability builder already registered: {source}")
        self._builders[source] = builder

    def build(
        self,
        spec: ScenarioSpec,
        mutual_context: MutualContext,
        resources: dict[str, Any] | None = None,
    ) -> CapabilityAssembly:
        events = EventInboxCapability()
        context = CapabilityBuildContext(
            spec=spec,
            mutual_context=mutual_context,
            events=events,
            resources=dict(resources or {}),
        )
        capabilities: list[Capability] = []
        speech: HostSpeechCapability | None = None
        for source in spec.capabilities:
            builder = self._builders.get(source)
            if builder is None:
                raise ValueError(f"场景声明了未注册的 Capability: {source}")
            built = builder(context)
            if isinstance(built, HostSpeechCapability):
                if speech is not None:
                    raise ValueError("场景重复注册 host_speech")
                speech = built
            else:
                capabilities.append(built)
        return CapabilityAssembly(capabilities, events, speech)


def _require(context: CapabilityBuildContext, name: str) -> Any:
    if name not in context.resources:
        raise ValueError(f"Capability 缺少启动资源: {name}")
    return context.resources[name]


def create_default_capability_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register("events", lambda context: context.events)
    registry.register(
        "mcp",
        lambda context: MCPCapability(
            _require(context, "mcp_adapter"),
            context.mutual_context,
        ),
    )
    registry.register("memory", lambda context: MemoryCapability(context.spec.memory_scope))
    registry.register(
        "host_speech",
        lambda context: HostSpeechCapability(context.mutual_context),
    )
    return registry


_capability_registry: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    global _capability_registry
    if _capability_registry is None:
        _capability_registry = create_default_capability_registry()
    return _capability_registry
