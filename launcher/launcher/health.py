"""Health-response interpretation independent from the UI."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class HealthResult:
    state: str
    label: str
    detail: str


def evaluate_health(kind: str, status_code: int, body: bytes) -> HealthResult:
    if status_code <= 0:
        return HealthResult("offline", "未连接", "服务未响应")
    if status_code >= 500:
        return HealthResult("error", "错误", f"HTTP {status_code}")
    if status_code >= 400:
        if kind == "bifrost" and status_code in {401, 403}:
            return HealthResult("degraded", "在线·需鉴权", f"HTTP {status_code}")
        return HealthResult("degraded", "响应异常", f"HTTP {status_code}")

    try:
        payload = json.loads(body) if body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}

    if kind == "backend":
        status = str(payload.get("status", "healthy"))
        if status == "healthy":
            return HealthResult("healthy", "运行正常", "核心组件已就绪")
        return HealthResult("degraded", "部分降级", status)
    if kind == "gateway":
        providers = payload.get("providers", {})
        configured = sum(1 for item in providers.values() if item.get("configured"))
        return HealthResult("healthy", "运行正常", f"已加载 {configured} 个 provider")
    if kind == "avatar":
        state = str(payload.get("state", "unknown"))
        if state == "running":
            return HealthResult("healthy", "渲染中", "数字人输出已启动")
        if state == "failed":
            return HealthResult("error", "启动失败", str(payload.get("error", "未知错误")))
        return HealthResult("idle", "待机", state)
    if kind == "live":
        running = bool(payload.get("running"))
        return HealthResult(
            "healthy" if running else "idle",
            "已连接" if running else "未启用",
            str(payload.get("context", {}).get("platform", "等待直播平台")),
        )
    if kind == "agent":
        running = bool(payload.get("running"))
        return HealthResult(
            "healthy" if running else "idle",
            "运行中" if running else "休眠",
            str(payload.get("runtime_status", "等待场景")),
        )
    if kind == "bifrost":
        return HealthResult("healthy", "运行正常", "OpenAI-compatible API 可达")
    if kind == "external":
        return HealthResult("healthy", "已连接", "外部服务可达")
    return HealthResult("healthy", "可访问", f"HTTP {status_code}")
