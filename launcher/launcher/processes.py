"""Managed child-process lifecycle and log capture."""

from __future__ import annotations

import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from launcher.models import ModuleSpec

ANSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def clean_output(value: str) -> str:
    return ANSI_PATTERN.sub("", value).replace("\r\n", "\n").replace("\r", "\n")


class ProcessController(QObject):
    log_received = Signal(str, str, str)
    state_changed = Signal(str, str)

    def __init__(
        self, specs: list[ModuleSpec], root: Path, parent=None, language: str = "zh"
    ) -> None:
        super().__init__(parent)
        self.root = root
        self.language = language
        self.specs = {spec.id: spec for spec in specs}
        self.processes: dict[str, QProcess] = {}
        self.pending_restarts: set[str] = set()

    def is_running(self, module_id: str) -> bool:
        process = self.processes.get(module_id)
        return process is not None and process.state() != QProcess.ProcessState.NotRunning

    def configure_command(self, module_id: str, command: str) -> ModuleSpec:
        spec = replace(
            self.specs[module_id],
            managed=True,
            program=os.environ.get("COMSPEC", "cmd.exe"),
            arguments=("/d", "/s", "/c", command),
            working_directory=self.root,
        )
        self.specs[module_id] = spec
        return spec

    def start(self, module_id: str) -> None:
        spec = self.specs[module_id]
        if not spec.managed or self.is_running(module_id):
            return
        process = QProcess(self)
        process.setProgram(spec.program)
        process.setArguments(list(spec.arguments))
        if spec.working_directory:
            process.setWorkingDirectory(str(spec.working_directory))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUTF8", "1")
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("NO_COLOR", "1")
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(
            lambda mid=module_id, proc=process: self._read(mid, proc, False)
        )
        process.readyReadStandardError.connect(
            lambda mid=module_id, proc=process: self._read(mid, proc, True)
        )
        process.started.connect(lambda mid=module_id: self._started(mid))
        process.errorOccurred.connect(lambda error, mid=module_id: self._error(mid, str(error)))
        process.finished.connect(
            lambda code, status, mid=module_id: self._finished(mid, code, status)
        )
        self.processes[module_id] = process
        self.state_changed.emit(module_id, "starting")
        prefix = "Starting" if self.language == "en" else "启动"
        self.log_received.emit(
            module_id, "system", f"{prefix}: {spec.program} {' '.join(spec.arguments)}"
        )
        process.start()

    def restart(self, module_id: str) -> None:
        if self.is_running(module_id):
            self.stop(module_id, restart=True)
        else:
            self.start(module_id)

    def stop(self, module_id: str, restart: bool = False) -> None:
        process = self.processes.get(module_id)
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            if restart:
                self.start(module_id)
            return
        pid = int(process.processId())
        if restart:
            self.pending_restarts.add(module_id)
        self.state_changed.emit(module_id, "stopping")
        if module_id == "backend":
            self._stop_nginx()
            graceful = self._request_backend_shutdown()
        else:
            graceful = False
        if not graceful:
            process.terminate()

        def force_stop() -> None:
            if process.state() != QProcess.ProcessState.NotRunning:
                self._kill_tree(pid)
                process.kill()

        QTimer.singleShot(6000 if graceful else 1500, force_stop)

    def stop_all_sync(self) -> None:
        self._stop_nginx()
        for module_id, process in list(self.processes.items()):
            if process.state() == QProcess.ProcessState.NotRunning:
                continue
            pid = int(process.processId())
            graceful = module_id == "backend" and self._request_backend_shutdown()
            if not graceful:
                process.terminate()
            if not process.waitForFinished(5000 if graceful else 900):
                self._kill_tree(pid)
                process.kill()
                process.waitForFinished(500)
            self.state_changed.emit(module_id, "stopped")

    def _read(self, module_id: str, process: QProcess, stderr: bool) -> None:
        raw = process.readAllStandardError() if stderr else process.readAllStandardOutput()
        text = clean_output(bytes(raw).decode("utf-8", errors="replace"))
        level = "error" if stderr else "info"
        for line in text.splitlines():
            if line.strip():
                self.log_received.emit(module_id, level, line)

    def _started(self, module_id: str) -> None:
        self.state_changed.emit(module_id, "running")
        message = (
            "Process started; waiting for health check"
            if self.language == "en"
            else "进程已启动，等待健康检查"
        )
        self.log_received.emit(module_id, "system", message)

    def _error(self, module_id: str, error: str) -> None:
        self.state_changed.emit(module_id, "error")
        prefix = "Process error" if self.language == "en" else "进程错误"
        self.log_received.emit(module_id, "error", f"{prefix}: {error}")

    def _finished(self, module_id: str, code: int, status) -> None:
        self.state_changed.emit(module_id, "stopped" if code == 0 else "error")
        message = (
            f"Process exited with code {code}, status {status.name}"
            if self.language == "en"
            else f"进程已退出，代码 {code}，状态 {status.name}"
        )
        self.log_received.emit(module_id, "system", message)
        if module_id in self.pending_restarts:
            self.pending_restarts.discard(module_id)
            QTimer.singleShot(350, lambda: self.start(module_id))

    def _request_backend_shutdown(self) -> bool:
        try:
            request = urllib.request.Request(
                "http://127.0.0.1:9191/system/shutdown",
                data=b"",
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=1.0) as response:
                accepted = response.status == 202
            if accepted:
                message = (
                    "Requested graceful backend shutdown"
                    if self.language == "en"
                    else "已请求后端优雅退出"
                )
                self.log_received.emit("backend", "system", message)
            return accepted
        except (OSError, urllib.error.URLError):
            return False

    def _stop_nginx(self) -> None:
        nginx_dir = self.root / "nginx-rtmp-win32"
        executable = nginx_dir / "nginx.exe"
        if not executable.exists():
            return
        try:
            subprocess.run(
                [str(executable), "-s", "stop"],
                cwd=str(nginx_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    @staticmethod
    def _kill_tree(pid: int) -> None:
        if pid <= 0:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
