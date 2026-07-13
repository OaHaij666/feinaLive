"""Launcher module definitions."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    name: str
    description: str
    health_url: str
    managed: bool = False
    program: str = ""
    arguments: tuple[str, ...] = ()
    working_directory: Path | None = None
    open_url: str = ""
    health_kind: str = "http"
    autostart: bool = False


def executable(name: str) -> str:
    return shutil.which(name) or name


def build_specs(root: Path) -> list[ModuleSpec]:
    uv = executable("uv")
    bifrost_command = os.getenv("BIFROST_START_COMMAND", "").strip()
    bifrost_managed = bool(bifrost_command)
    bifrost_program = os.environ.get("COMSPEC", "cmd.exe") if bifrost_managed else ""
    bifrost_args = ("/d", "/s", "/c", bifrost_command) if bifrost_managed else ()

    return [
        ModuleSpec(
            id="bifrost",
            name="Bifrost LLM Gateway",
            description="模型路由、fallback 与上游供应商",
            health_url="http://127.0.0.1:8081/v1/models",
            managed=bifrost_managed,
            program=bifrost_program,
            arguments=bifrost_args,
            working_directory=root,
            health_kind="bifrost",
            autostart=bifrost_managed,
        ),
        ModuleSpec(
            id="speech",
            name="Speech Gateway",
            description="TTS provider、路由、熔断与指标",
            health_url="http://127.0.0.1:8091/health",
            managed=True,
            program=uv,
            arguments=("run", "python", "-m", "speech_gateway.main"),
            working_directory=root / "speech_gateway",
            health_kind="gateway",
            autostart=True,
        ),
        ModuleSpec(
            id="backend",
            name="feinaLive Backend",
            description="HostRuntime、平台、记忆与播放编排",
            health_url="http://127.0.0.1:9191/health",
            managed=True,
            program=uv,
            arguments=("run", "python", "main.py"),
            working_directory=root / "backend",
            health_kind="backend",
            autostart=True,
        ),
        ModuleSpec(
            id="mcp",
            name="场景 MCP",
            description="可选的游戏或 Computer Use 能力服务",
            health_url="http://127.0.0.1:8080/health",
            health_kind="external",
        ),
        ModuleSpec(
            id="nginx_live",
            name="直播展示端",
            description="Nginx 生产直播画面",
            health_url="http://127.0.0.1:8088/",
            open_url="http://127.0.0.1:8088/",
        ),
        ModuleSpec(
            id="nginx_console",
            name="运营控制台",
            description="Nginx 生产管理界面",
            health_url="http://127.0.0.1:8089/",
            open_url="http://127.0.0.1:8089/",
        ),
        ModuleSpec(
            id="avatar",
            name="FeinaAvatar",
            description="数字人推理、预览和 Spout 输出",
            health_url="http://127.0.0.1:9191/avatar/status",
            health_kind="avatar",
        ),
        ModuleSpec(
            id="live",
            name="直播平台 Runtime",
            description="唯一房间与统一直播事件入口",
            health_url="http://127.0.0.1:9191/live/state",
            health_kind="live",
        ),
        ModuleSpec(
            id="agent",
            name="Agent Runtime",
            description="场景能力、MCP 与解说请求",
            health_url="http://127.0.0.1:9191/agent/status",
            health_kind="agent",
        ),
    ]
