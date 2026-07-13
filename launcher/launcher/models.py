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
    start_url: str = ""
    stop_url: str = ""
    command_env: str = ""

    @property
    def controllable(self) -> bool:
        return self.managed or bool(self.start_url and self.stop_url) or bool(self.command_env)


def executable(name: str) -> str:
    return shutil.which(name) or name


def build_specs(root: Path, command_overrides: dict[str, str] | None = None) -> list[ModuleSpec]:
    uv = executable("uv")
    overrides = command_overrides or {}
    bifrost_command = (
        os.getenv("BIFROST_START_COMMAND", "") or overrides.get("bifrost", "")
    ).strip()
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
            command_env="BIFROST_START_COMMAND",
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
            managed=bool((os.getenv("MCP_START_COMMAND", "") or overrides.get("mcp", "")).strip()),
            program=os.environ.get("COMSPEC", "cmd.exe"),
            arguments=(
                "/d",
                "/s",
                "/c",
                (os.getenv("MCP_START_COMMAND", "") or overrides.get("mcp", "")).strip(),
            ),
            working_directory=root,
            command_env="MCP_START_COMMAND",
        ),
        ModuleSpec(
            id="nginx_live",
            name="直播展示端",
            description="Nginx 生产直播画面",
            health_url="http://127.0.0.1:8088/",
            open_url="http://127.0.0.1:8088/",
            start_url="http://127.0.0.1:9191/stream/start",
            stop_url="http://127.0.0.1:9191/stream/stop",
        ),
        ModuleSpec(
            id="avatar",
            name="FeinaAvatar",
            description="数字人推理、预览和 Spout 输出",
            health_url="http://127.0.0.1:9191/avatar/status",
            health_kind="avatar",
            start_url="http://127.0.0.1:9191/avatar/start",
            stop_url="http://127.0.0.1:9191/avatar/stop",
        ),
        ModuleSpec(
            id="live",
            name="直播平台 Runtime",
            description="唯一房间与统一直播事件入口",
            health_url="http://127.0.0.1:9191/live/state",
            health_kind="live",
            start_url="http://127.0.0.1:9191/live/start",
            stop_url="http://127.0.0.1:9191/live/stop",
        ),
        ModuleSpec(
            id="agent",
            name="Agent Runtime",
            description="场景能力、MCP 与解说请求",
            health_url="http://127.0.0.1:9191/agent/status",
            health_kind="agent",
            start_url="http://127.0.0.1:9191/agent/start",
            stop_url="http://127.0.0.1:9191/agent/stop",
        ),
    ]
