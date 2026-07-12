"""Game-agnostic memory lifecycle contracts exposed to adapters and APIs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

LayerName = Literal["core", "important", "recent"]
LayerRetention = Literal["reset", "carry"]
SessionMode = Literal["per_run", "continuous", "external"]


@dataclass(slots=True)
class GameMemoryPolicy:
    session_mode: SessionMode = "per_run"
    layer_retention: dict[LayerName, LayerRetention] = field(
        default_factory=lambda: {
            "core": "reset",
            "important": "reset",
            "recent": "reset",
        }
    )
    flush_on_session_end: bool = True
    summary_threshold: int = 30
    idle_summary_seconds: float = 120.0
    context_max_chars: int = 12000
    capture_action_results: bool = True
    capture_query_results: bool = True
    durable_memory_enabled: bool = True

    def __post_init__(self) -> None:
        if self.session_mode not in {"per_run", "continuous", "external"}:
            raise ValueError(f"无效 session_mode: {self.session_mode}")
        normalized: dict[LayerName, LayerRetention] = {}
        for layer in ("core", "important", "recent"):
            retention = self.layer_retention.get(layer, "reset")
            if retention not in {"reset", "carry"}:
                raise ValueError(f"无效层保留策略: {layer}={retention}")
            normalized[layer] = retention
        self.layer_retention = normalized
        self.summary_threshold = max(1, int(self.summary_threshold))
        self.idle_summary_seconds = max(1.0, float(self.idle_summary_seconds))
        self.context_max_chars = max(1000, int(self.context_max_chars))

    def retention_for(self, layer: LayerName) -> LayerRetention:
        return self.layer_retention.get(layer, "reset")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GameMemoryContext:
    game_id: str
    session_id: str
    core: str = ""
    important: str = ""
    recent: str = ""
    pending_events: list[dict[str, Any]] = field(default_factory=list)
    recalled_atoms: list[dict[str, Any]] = field(default_factory=list)
    graph_facts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GameMemoryAPI:
    """Game-scoped facade handed to adapters; it cannot write atoms or edges."""

    def __init__(self, engine: Any, game_id: str):
        self._engine = engine
        self.game_id = game_id

    @property
    def policy(self) -> GameMemoryPolicy:
        return self._engine.get_game_policy(self.game_id)

    async def record_event(
        self,
        *,
        event_type: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        result: Any = None,
        success: bool = True,
        external_event_id: str | None = None,
    ) -> Any:
        return await self._engine.record_mcp_event(
            self.game_id,
            event_type=event_type,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            success=success,
            external_event_id=external_event_id,
        )

    async def update_layer(
        self, layer: LayerName, content: str, *, source: str = "adapter"
    ) -> None:
        await self._engine.update_working_memory(self.game_id, layer, content, source=source)

    async def checkpoint(self, *, force: bool = False) -> bool:
        return await self._engine.summarize_session_memory(game_id=self.game_id, force=force)

    async def get_context(self, query: str = "") -> GameMemoryContext:
        return await self._engine.get_game_memory_context(self.game_id, query)

    async def get_status(self) -> dict[str, Any]:
        return await self._engine.get_game_session_status(self.game_id)

    async def close(
        self, *, reason: str = "adapter", final_event: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._engine.close_game_session(
            self.game_id, reason=reason, final_event=final_event
        )


__all__ = [
    "GameMemoryContext",
    "GameMemoryAPI",
    "GameMemoryPolicy",
    "LayerName",
    "LayerRetention",
    "SessionMode",
]
