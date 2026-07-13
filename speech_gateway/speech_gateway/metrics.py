"""Bounded in-memory operational metrics."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percentile))
    return round(ordered[index], 4)


@dataclass
class ProviderMetrics:
    sample_size: int
    requests: int = 0
    successes: int = 0
    failures: int = 0
    fallbacks: int = 0
    errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    latency_ms: deque[float] = field(init=False)
    rtf: deque[float] = field(init=False)

    def __post_init__(self) -> None:
        self.latency_ms = deque(maxlen=self.sample_size)
        self.rtf = deque(maxlen=self.sample_size)

    def snapshot(self) -> dict:
        latency = list(self.latency_ms)
        rtf_values = list(self.rtf)
        return {
            "requests": self.requests,
            "successes": self.successes,
            "failures": self.failures,
            "fallbacks": self.fallbacks,
            "success_rate": round(self.successes / self.requests, 4) if self.requests else None,
            "latency_ms": {
                "p50": _percentile(latency, 0.50),
                "p95": _percentile(latency, 0.95),
            },
            "rtf": {
                "p50": _percentile(rtf_values, 0.50),
                "p95": _percentile(rtf_values, 0.95),
            },
            "errors": dict(self.errors),
        }


class MetricsStore:
    def __init__(self, sample_size: int) -> None:
        self.sample_size = sample_size
        self._providers: dict[str, ProviderMetrics] = {}

    def provider(self, name: str) -> ProviderMetrics:
        if name not in self._providers:
            self._providers[name] = ProviderMetrics(self.sample_size)
        return self._providers[name]

    def snapshot(self) -> dict[str, dict]:
        return {name: metrics.snapshot() for name, metrics in self._providers.items()}

    def prometheus(self) -> str:
        lines = []
        for name, metrics in self._providers.items():
            labels = f'provider="{name}"'
            lines.extend(
                [
                    f"speech_gateway_requests_total{{{labels}}} {metrics.requests}",
                    f"speech_gateway_successes_total{{{labels}}} {metrics.successes}",
                    f"speech_gateway_failures_total{{{labels}}} {metrics.failures}",
                    f"speech_gateway_fallbacks_total{{{labels}}} {metrics.fallbacks}",
                ]
            )
        return "\n".join(lines) + ("\n" if lines else "")
