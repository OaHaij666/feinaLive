from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """Immutable instructions and policies for one process-bound scenario."""

    id: str
    display_name: str
    instructions: str
    capabilities: tuple[str, ...]
    memory_scope: str
    sandbox_policy: str = "none"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
