"""Dense operations dashboard for starting and observing feinaLive."""

from __future__ import annotations

import os
from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QProcess, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFont, QTextCursor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from launcher.control import OperationsConsole
from launcher.health import HealthResult, evaluate_health
from launcher.models import ModuleSpec, build_specs, executable
from launcher.processes import ProcessController, clean_output

STATE_LABELS = {
    "unknown": "等待检查",
    "starting": "正在启动",
    "running": "进程运行",
    "stopping": "正在停止",
    "stopped": "已停止",
    "offline": "未连接",
    "healthy": "运行正常",
    "degraded": "部分降级",
    "idle": "待机",
    "error": "错误",
}


class ModuleCard(QFrame):
    start_requested = Signal(str)
    restart_requested = Signal(str)
    stop_requested = Signal(str)

    def __init__(self, spec: ModuleSpec, parent=None) -> None:
        super().__init__(parent)
        self.spec = spec
        self.setObjectName("moduleCard")
        self.setProperty("state", "unknown")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)

        top = QHBoxLayout()
        self.dot = QFrame()
        self.dot.setObjectName("statusDot")
        self.dot.setFixedSize(10, 10)
        title = QLabel(spec.name)
        title.setObjectName("moduleTitle")
        top.addWidget(self.dot)
        top.addWidget(title, 1)
        self.state_label = QLabel(STATE_LABELS["unknown"])
        self.state_label.setObjectName("stateLabel")
        top.addWidget(self.state_label)
        layout.addLayout(top)

        description = QLabel(spec.description)
        description.setObjectName("moduleDescription")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.detail = QLabel(spec.health_url.replace("http://", ""))
        self.detail.setObjectName("moduleDetail")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        if spec.managed:
            self.start_button = self._button("启动", lambda: self.start_requested.emit(spec.id))
            self.restart_button = self._button("重启", lambda: self.restart_requested.emit(spec.id))
            self.stop_button = self._button("停止", lambda: self.stop_requested.emit(spec.id))
            actions.addWidget(self.start_button)
            actions.addWidget(self.restart_button)
            actions.addWidget(self.stop_button)
        else:
            self.start_button = self.restart_button = self.stop_button = None
        if spec.open_url:
            actions.addWidget(
                self._button("打开", lambda: QDesktopServices.openUrl(QUrl(spec.open_url)))
            )
        actions.addStretch(1)
        layout.addLayout(actions)

    def _button(self, text: str, callback) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumHeight(32)
        button.clicked.connect(callback)
        return button

    def set_state(self, state: str, label: str = "", detail: str = "") -> None:
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)
        self.state_label.setText(label or STATE_LABELS.get(state, state))
        if detail:
            self.detail.setText(detail)
        if self.start_button:
            running = state in {"starting", "running", "healthy", "degraded", "idle"}
            self.start_button.setEnabled(not running)
            self.restart_button.setEnabled(running)
            self.stop_button.setEnabled(running)


class LauncherWindow(QMainWindow):
    def __init__(self, root: Path, autostart: bool = True) -> None:
        super().__init__()
        self.root = root
        self.specs = build_specs(root)
        self.spec_by_id = {spec.id: spec for spec in self.specs}
        self.cards: dict[str, ModuleCard] = {}
        self.process_states: dict[str, str] = {}
        self.health_states: dict[str, HealthResult] = {}
        self.log_records: deque[tuple[str, str, str, str]] = deque(maxlen=5000)
        self.settings = QSettings("feinaLive", "Launcher")
        self.theme = str(self.settings.value("theme", "dark"))
        self.network = QNetworkAccessManager(self)
        self.pending_health: set[str] = set()
        self.processes = ProcessController(self.specs, root, self)
        self.setup_process: QProcess | None = None
        self.setup_stage = ""
        self._build_ui()
        self._connect_signals()
        self._open_log_file()
        self._restore_window()

        self.health_timer = QTimer(self)
        self.health_timer.setInterval(2000)
        self.health_timer.timeout.connect(self.check_health)
        self.health_timer.start()
        QTimer.singleShot(50, self.check_health)
        if autostart:
            QTimer.singleShot(450, self.start_all)

    def _build_ui(self) -> None:
        self.setWindowTitle("FeinaLive Control Center")
        self.setMinimumSize(1050, 700)
        self.resize(1320, 840)
        self.main_tabs = QTabWidget()
        self.main_tabs.setObjectName("mainTabs")
        self.setCentralWidget(self.main_tabs)
        self.theme_button = QPushButton()
        self._update_theme_button()
        self.theme_button.clicked.connect(self.toggle_theme)
        self.main_tabs.setCornerWidget(self.theme_button, Qt.Corner.TopRightCorner)
        root_widget = QWidget()
        root_widget.setObjectName("appRoot")
        self.main_tabs.addTab(root_widget, "运行中心")
        outer = QVBoxLayout(root_widget)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        header = QHBoxLayout()
        heading_box = QVBoxLayout()
        heading = QLabel("FeinaLive Control Center")
        heading.setObjectName("heading")
        subtitle = QLabel("本地直播运行栈 · 进程、健康检查与集中日志")
        subtitle.setObjectName("subtitle")
        heading_box.addWidget(heading)
        heading_box.addWidget(subtitle)
        header.addLayout(heading_box)
        header.addStretch(1)
        self.summary_label = QLabel("正在检查模块…")
        self.summary_label.setObjectName("summary")
        header.addWidget(self.summary_label)
        self.start_all_button = QPushButton("启动全部")
        self.start_all_button.setObjectName("primaryButton")
        self.stop_all_button = QPushButton("停止全部")
        self.live_button = QPushButton("打开直播端")
        for button in (
            self.start_all_button,
            self.stop_all_button,
            self.live_button,
        ):
            button.setMinimumHeight(40)
            header.addWidget(button)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Vertical)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        cards_widget = QWidget()
        cards_layout = QGridLayout(cards_widget)
        cards_layout.setContentsMargins(0, 2, 0, 4)
        cards_layout.setHorizontalSpacing(10)
        cards_layout.setVerticalSpacing(10)
        for index, spec in enumerate(self.specs):
            card = ModuleCard(spec)
            card.start_requested.connect(self.processes.start)
            card.restart_requested.connect(self.processes.restart)
            card.stop_requested.connect(self.processes.stop)
            self.cards[spec.id] = card
            cards_layout.addWidget(card, index // 3, index % 3)
        for column in range(3):
            cards_layout.setColumnStretch(column, 1)
        scroll.setWidget(cards_widget)
        splitter.addWidget(scroll)

        log_panel = QFrame()
        log_panel.setObjectName("logPanel")
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(12, 10, 12, 10)
        tools = QHBoxLayout()
        log_title = QLabel("实时日志")
        log_title.setObjectName("panelTitle")
        tools.addWidget(log_title)
        self.log_filter = QComboBox()
        self.log_filter.addItem("全部模块", "all")
        for spec in self.specs:
            self.log_filter.addItem(spec.name, spec.id)
        self.log_filter.addItem("启动准备", "frontend-setup")
        self.log_search = QLineEdit()
        self.log_search.setPlaceholderText("搜索日志")
        self.log_search.setClearButtonEnabled(True)
        self.auto_scroll = QCheckBox("自动滚动")
        self.auto_scroll.setChecked(True)
        clear_button = QPushButton("清空显示")
        clear_button.clicked.connect(self._clear_log_view)
        tools.addWidget(self.log_filter)
        tools.addWidget(self.log_search, 1)
        tools.addWidget(self.auto_scroll)
        tools.addWidget(clear_button)
        log_layout.addLayout(tools)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.document().setMaximumBlockCount(5000)
        font = QFont("Cascadia Mono")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(9)
        self.log_view.setFont(font)
        log_layout.addWidget(self.log_view)
        splitter.addWidget(log_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([430, 330])
        outer.addWidget(splitter, 1)
        self.main_tabs.addTab(OperationsConsole(), "FEINA LIVE · 运营控制台")
        self.setStyleSheet(self._stylesheet(self.theme))

    def _connect_signals(self) -> None:
        self.processes.log_received.connect(self.append_log)
        self.processes.state_changed.connect(self.on_process_state)
        self.start_all_button.clicked.connect(self.start_all)
        self.stop_all_button.clicked.connect(self.stop_all)
        self.live_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("http://127.0.0.1:8088/"))
        )
        self.log_filter.currentIndexChanged.connect(self.render_logs)
        self.log_search.textChanged.connect(self.render_logs)

    def start_all(self) -> None:
        self.append_log("launcher", "system", "开始启动 feinaLive 运行栈")
        if self.spec_by_id["bifrost"].managed:
            self.processes.start("bifrost")
        else:
            self.append_log(
                "bifrost",
                "system",
                "Bifrost 由外部管理；设置 BIFROST_START_COMMAND 后可由启动器托管",
            )
        self.processes.start("speech")
        self._ensure_frontend_then_start_backend()

    def stop_all(self) -> None:
        self.append_log("launcher", "system", "正在停止启动器托管的模块")
        for module_id in ("backend", "speech", "bifrost"):
            if self.spec_by_id[module_id].managed:
                self.processes.stop(module_id)

    def _ensure_frontend_then_start_backend(self) -> None:
        live_index = self.root / "fronted" / "dist" / "live" / "index.html"
        if live_index.exists():
            QTimer.singleShot(600, lambda: self.processes.start("backend"))
            return
        self.append_log("frontend-setup", "system", "前端生产构建不存在，开始首次准备")
        if not (self.root / "fronted" / "node_modules").exists():
            self._run_frontend_setup("install")
        else:
            self._run_frontend_setup("build")

    def _run_frontend_setup(self, stage: str) -> None:
        if self.setup_process and self.setup_process.state() != QProcess.ProcessState.NotRunning:
            return
        self.setup_stage = stage
        process = QProcess(self)
        process.setProgram(executable("npm.cmd" if os.name == "nt" else "npm"))
        process.setArguments(["install"] if stage == "install" else ["run", "build"])
        process.setWorkingDirectory(str(self.root / "fronted"))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_setup_output)
        process.finished.connect(self._setup_finished)
        self.setup_process = process
        process.start()

    def _read_setup_output(self) -> None:
        if not self.setup_process:
            return
        text = clean_output(
            bytes(self.setup_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        )
        for line in text.splitlines():
            if line.strip():
                self.append_log("frontend-setup", "info", line)

    def _setup_finished(self, code: int) -> None:
        if code != 0:
            self.append_log("frontend-setup", "error", f"前端 {self.setup_stage} 失败，代码 {code}")
            return
        if self.setup_stage == "install":
            self._run_frontend_setup("build")
        else:
            self.append_log("frontend-setup", "system", "前端构建完成")
            self.processes.start("backend")

    def check_health(self) -> None:
        for spec in self.specs:
            if spec.id in self.pending_health:
                continue
            request = QNetworkRequest(QUrl(spec.health_url))
            request.setTransferTimeout(1400)
            reply = self.network.get(request)
            reply.setProperty("module_id", spec.id)
            reply.finished.connect(lambda rep=reply: self._health_finished(rep))
            self.pending_health.add(spec.id)

    def _health_finished(self, reply: QNetworkReply) -> None:
        module_id = str(reply.property("module_id"))
        self.pending_health.discard(module_id)
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
        body = bytes(reply.readAll())
        spec = self.spec_by_id[module_id]
        result = evaluate_health(spec.health_kind, int(status), body)
        if reply.error() != QNetworkReply.NetworkError.NoError and not status:
            result = HealthResult("offline", "未连接", reply.errorString())
        self.health_states[module_id] = result
        self._apply_module_state(module_id)
        reply.deleteLater()
        self._update_summary()

    def on_process_state(self, module_id: str, state: str) -> None:
        self.process_states[module_id] = state
        self._apply_module_state(module_id)
        self._update_summary()

    def _apply_module_state(self, module_id: str) -> None:
        health = self.health_states.get(module_id)
        process_state = self.process_states.get(module_id, "unknown")
        if health and health.state != "offline":
            self.cards[module_id].set_state(health.state, health.label, health.detail)
        elif process_state in {"starting", "running", "stopping", "error"}:
            detail = (
                "等待健康检查" if process_state in {"starting", "running"} else "进程状态已变化"
            )
            self.cards[module_id].set_state(process_state, detail=detail)
        elif health:
            self.cards[module_id].set_state(health.state, health.label, health.detail)
        else:
            self.cards[module_id].set_state(process_state)

    def _update_summary(self) -> None:
        states = [result.state for result in self.health_states.values()]
        healthy = sum(state == "healthy" for state in states)
        degraded = sum(state in {"degraded", "error"} for state in states)
        self.summary_label.setText(f"在线 {healthy}/{len(self.specs)} · 异常 {degraded}")

    def append_log(self, module_id: str, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        module_name = (
            self.spec_by_id.get(module_id).name if module_id in self.spec_by_id else module_id
        )
        record = (timestamp, module_id, level, message)
        self.log_records.append(record)
        line = f"{timestamp}  [{module_name}]  {message}"
        if self.log_file:
            self.log_file.write(line + "\n")
            self.log_file.flush()
        if self._log_matches(record):
            self.log_view.appendPlainText(line)
            if self.auto_scroll.isChecked():
                self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def _log_matches(self, record: tuple[str, str, str, str]) -> bool:
        _, module_id, _, message = record
        selected = self.log_filter.currentData() if hasattr(self, "log_filter") else "all"
        query = self.log_search.text().strip().lower() if hasattr(self, "log_search") else ""
        return (selected == "all" or selected == module_id) and (
            not query or query in message.lower()
        )

    def render_logs(self) -> None:
        self.log_view.clear()
        for timestamp, module_id, level, message in self.log_records:
            record = (timestamp, module_id, level, message)
            if not self._log_matches(record):
                continue
            module_name = (
                self.spec_by_id.get(module_id).name if module_id in self.spec_by_id else module_id
            )
            self.log_view.appendPlainText(f"{timestamp}  [{module_name}]  {message}")
        if self.auto_scroll.isChecked():
            self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def _clear_log_view(self) -> None:
        self.log_records.clear()
        self.log_view.clear()

    def _open_log_file(self) -> None:
        try:
            log_dir = self.root / "launcher" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / f"session-{datetime.now():%Y%m%d-%H%M%S}.log"
            self.log_file = path.open("a", encoding="utf-8")
        except OSError:
            self.log_file = None

    def _restore_window(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def toggle_theme(self) -> None:
        self.theme = "light" if self.theme == "dark" else "dark"
        self.setStyleSheet(self._stylesheet(self.theme))
        self._update_theme_button()

    def _update_theme_button(self) -> None:
        self.theme_button.setText("亮色" if self.theme == "dark" else "暗色")
        self.theme_button.setToolTip(f"切换到{'亮色' if self.theme == 'dark' else '暗色'}主题")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        running = any(self.processes.is_running(spec.id) for spec in self.specs if spec.managed)
        if running:
            answer = QMessageBox.question(
                self,
                "退出 FeinaLive",
                "退出会停止由本窗口启动的模块。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.health_timer.stop()
        self.processes.stop_all_sync()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("theme", self.theme)
        if self.log_file:
            self.log_file.close()
        event.accept()

    @staticmethod
    def _stylesheet(theme: str) -> str:
        if theme == "light":
            return """
        QWidget { color: #172033; background: #f4f6fb; }
        QWidget#appRoot { background: #f4f6fb; color: #172033; }
        QLabel#heading { font-size: 24px; font-weight: 700; color: #172033; }
        QLabel#subtitle, QLabel#moduleDescription, QLabel#moduleDetail, QLabel#mutedText { color: #64748b; }
        QLabel#subtitle { font-size: 12px; }
        QLabel#summary { padding: 8px 12px; border: 1px solid #d7dce6; border-radius: 8px; color: #475569; background: #ffffff; }
        QLabel#pageTitle { font-size: 18px; font-weight: 700; color: #172033; }
        QLabel#formHeading { padding-top: 12px; font-weight: 700; color: #5b21b6; }
        QFrame#moduleCard, QGroupBox { border: 1px solid #dce1eb; border-radius: 10px; background: #ffffff; }
        QGroupBox { margin-top: 12px; padding: 14px 10px 10px; font-weight: 650; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        QFrame#moduleCard:hover { border-color: #a8b0c0; }
        QLabel#moduleTitle { font-weight: 650; color: #172033; }
        QLabel#moduleDescription { font-size: 12px; }
        QLabel#moduleDetail { font-size: 11px; font-family: "Cascadia Mono"; }
        QLabel#stateLabel { font-size: 11px; font-weight: 600; color: #475569; }
        QFrame#statusDot { border-radius: 5px; background: #94a3b8; }
        QFrame#moduleCard[state="healthy"] QFrame#statusDot { background: #16a34a; }
        QFrame#moduleCard[state="degraded"] QFrame#statusDot, QFrame#moduleCard[state="idle"] QFrame#statusDot { background: #d97706; }
        QFrame#moduleCard[state="error"] QFrame#statusDot { background: #dc2626; }
        QFrame#moduleCard[state="starting"] QFrame#statusDot, QFrame#moduleCard[state="running"] QFrame#statusDot { background: #0284c7; }
        QFrame#logPanel { border: 1px solid #dce1eb; border-radius: 10px; background: #ffffff; }
        QLabel#panelTitle { font-size: 14px; font-weight: 650; }
        QPushButton { min-height: 34px; padding: 0 12px; border: 1px solid #cfd5e2; border-radius: 7px; color: #334155; background: #ffffff; }
        QPushButton:hover { border-color: #a78bfa; background: #f3f0ff; }
        QPushButton:focus, QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border: 2px solid #7c3aed; }
        QPushButton:disabled { color: #94a3b8; background: #eef1f6; }
        QPushButton#primaryButton { border-color: #6d28d9; color: #ffffff; background: #7c3aed; font-weight: 700; }
        QPushButton#primaryButton:hover { background: #6d28d9; }
        QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { min-height: 34px; padding: 0 9px; border: 1px solid #cfd5e2; border-radius: 7px; color: #172033; background: #ffffff; selection-background-color: #7c3aed; }
        QPlainTextEdit { border: 1px solid #dce1eb; border-radius: 7px; color: #334155; background: #ffffff; selection-background-color: #7c3aed; }
        QFrame#logPanel QPlainTextEdit { background: #eef1f6; }
        QListWidget { border: 1px solid #dce1eb; border-radius: 8px; background: #ffffff; outline: 0; }
        QListWidget::item { min-height: 38px; padding: 0 10px; }
        QListWidget::item:selected { color: #5b21b6; background: #ede9fe; }
        QTabWidget::pane { border: 1px solid #dce1eb; background: #f8f9fd; }
        QTabBar::tab { min-height: 38px; padding: 0 18px; color: #596579; background: #eef1f6; border: 1px solid #dce1eb; }
        QTabBar::tab:selected { color: #5b21b6; background: #ffffff; border-bottom: 2px solid #7c3aed; }
        QScrollArea { background: transparent; }
        QScrollBar:vertical { width: 10px; background: #eef1f6; }
        QScrollBar::handle:vertical { min-height: 30px; border-radius: 5px; background: #a8b0c0; }
        QSplitter::handle { height: 5px; background: #f4f6fb; }
        """
        return """
        QWidget { color: #f8fafc; background: #020617; }
        QWidget#appRoot { background: #020617; color: #f8fafc; }
        QLabel#heading { font-size: 24px; font-weight: 700; color: #f8fafc; }
        QLabel#subtitle, QLabel#moduleDescription, QLabel#moduleDetail, QLabel#mutedText { color: #94a3b8; }
        QLabel#subtitle { font-size: 12px; }
        QLabel#summary { padding: 8px 12px; border: 1px solid #334155; border-radius: 8px; color: #cbd5e1; background: #0f172a; }
        QLabel#pageTitle { font-size: 18px; font-weight: 700; color: #f8fafc; }
        QLabel#formHeading { padding-top: 12px; font-weight: 700; color: #c4b5fd; }
        QFrame#moduleCard, QGroupBox { border: 1px solid #334155; border-radius: 10px; background: #0f172a; }
        QGroupBox { margin-top: 12px; padding: 14px 10px 10px; font-weight: 650; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        QFrame#moduleCard:hover { border-color: #475569; }
        QLabel#moduleTitle { font-weight: 650; color: #f8fafc; }
        QLabel#moduleDescription { font-size: 12px; }
        QLabel#moduleDetail { font-size: 11px; font-family: "Cascadia Mono"; }
        QLabel#stateLabel { font-size: 11px; font-weight: 600; color: #cbd5e1; }
        QFrame#statusDot { border-radius: 5px; background: #64748b; }
        QFrame#moduleCard[state="healthy"] QFrame#statusDot { background: #22c55e; }
        QFrame#moduleCard[state="degraded"] QFrame#statusDot, QFrame#moduleCard[state="idle"] QFrame#statusDot { background: #f59e0b; }
        QFrame#moduleCard[state="error"] QFrame#statusDot { background: #ef4444; }
        QFrame#moduleCard[state="starting"] QFrame#statusDot, QFrame#moduleCard[state="running"] QFrame#statusDot { background: #38bdf8; }
        QFrame#logPanel { border: 1px solid #334155; border-radius: 10px; background: #0f172a; }
        QLabel#panelTitle { font-size: 14px; font-weight: 650; }
        QPushButton { min-height: 32px; padding: 0 12px; border: 1px solid #475569; border-radius: 7px; color: #e2e8f0; background: #1e293b; }
        QPushButton:hover { border-color: #64748b; background: #334155; }
        QPushButton:focus { border: 2px solid #38bdf8; }
        QPushButton:disabled { color: #64748b; background: #111827; }
        QPushButton#primaryButton { border-color: #16a34a; color: #052e16; background: #22c55e; font-weight: 700; }
        QPushButton#primaryButton:hover { background: #4ade80; }
        QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { min-height: 34px; padding: 0 9px; border: 1px solid #334155; border-radius: 7px; color: #e2e8f0; background: #111827; selection-background-color: #2563eb; }
        QComboBox:focus, QLineEdit:focus, QPlainTextEdit:focus { border: 2px solid #38bdf8; }
        QComboBox QAbstractItemView { color: #e2e8f0; background: #111827; selection-background-color: #334155; }
        QPlainTextEdit { border: 1px solid #334155; border-radius: 7px; color: #cbd5e1; background: #050a14; selection-background-color: #1d4ed8; }
        QFrame#logPanel QPlainTextEdit { border: 0; }
        QListWidget { border: 1px solid #334155; border-radius: 8px; background: #0f172a; outline: 0; }
        QListWidget::item { min-height: 38px; padding: 0 10px; }
        QListWidget::item:selected { color: #ede9fe; background: #312e81; }
        QTabWidget::pane { border: 1px solid #334155; background: #020617; }
        QTabBar::tab { min-height: 38px; padding: 0 18px; color: #94a3b8; background: #0f172a; border: 1px solid #334155; }
        QTabBar::tab:selected { color: #f8fafc; background: #1e293b; border-bottom: 2px solid #8b5cf6; }
        QScrollArea { background: transparent; }
        QScrollBar:vertical { width: 10px; background: #0f172a; }
        QScrollBar::handle:vertical { min-height: 30px; border-radius: 5px; background: #475569; }
        QSplitter::handle { height: 5px; background: #020617; }
        """
