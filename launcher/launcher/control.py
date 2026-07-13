"""Native operator-console pages backed by the local FastAPI control plane."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from PySide6.QtCore import QByteArray, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

API_ROOT = "http://127.0.0.1:9191"
Callback = Callable[[bool, Any, str], None]

SECTION_LABELS = {
    "live": "直播平台",
    "bilibili": "Bilibili",
    "douyin": "抖音",
    "host": "AI 主播",
    "llm": "通用模型",
    "tts": "语音路由",
    "agent": "Agent 场景",
    "avatar": "数字人",
    "ai": "记忆行为",
    "messaging": "消息调度",
    "music": "音乐策略",
    "storage": "数据存储",
    "announcement": "公告",
    "admin": "管理员",
    "embedding": "向量模型",
}


class ApiClient(QNetworkAccessManager):
    def send(
        self,
        method: str,
        path: str,
        payload: Any | None,
        callback: Callback,
    ) -> None:
        request = QNetworkRequest(QUrl(f"{API_ROOT}{path}"))
        request.setTransferTimeout(8000)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        body = (
            QByteArray(json.dumps(payload, ensure_ascii=False).encode())
            if payload is not None
            else QByteArray()
        )
        reply = self.sendCustomRequest(request, method.encode(), body)
        reply.finished.connect(lambda: self._finish(reply, callback))

    @staticmethod
    def _finish(reply: QNetworkReply, callback: Callback) -> None:
        status = int(reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0)
        raw = bytes(reply.readAll())
        try:
            data = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            data = raw.decode("utf-8", errors="replace")
        ok = 200 <= status < 300
        if ok:
            error = ""
        elif isinstance(data, dict):
            error = str(data.get("detail") or data.get("error") or reply.errorString())
        else:
            error = str(data or reply.errorString())
        callback(ok, data, error)
        reply.deleteLater()


class JsonView(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setPlaceholderText("等待后端数据…")

    def show_data(self, data: Any) -> None:
        self.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))


class ConfigPage(QWidget):
    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self.api = api
        self.data: dict[str, Any] = {}
        self.fields: dict[tuple[str, ...], tuple[QWidget, type]] = {}

        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        title = QLabel("持久配置")
        title.setObjectName("pageTitle")
        self.status = QLabel("尚未加载")
        self.status.setObjectName("mutedText")
        reload_button = QPushButton("重新加载")
        reload_button.clicked.connect(self.load)
        save_button = QPushButton("保存配置")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.save)
        toolbar.addWidget(title)
        toolbar.addWidget(self.status)
        toolbar.addStretch()
        toolbar.addWidget(reload_button)
        toolbar.addWidget(save_button)
        layout.addLayout(toolbar)

        content = QHBoxLayout()
        self.sections = QListWidget()
        self.sections.setFixedWidth(170)
        self.sections.currentRowChanged.connect(self._select_section)
        self.pages = QStackedWidget()
        content.addWidget(self.sections)
        content.addWidget(self.pages, 1)
        layout.addLayout(content, 1)
        self.load()

    def load(self) -> None:
        self.status.setText("加载中…")
        self.api.send("GET", "/config", None, self._loaded)

    def _loaded(self, ok: bool, data: Any, error: str) -> None:
        if not ok or not isinstance(data, dict):
            self.status.setText(f"加载失败：{error}")
            return
        self.data = data
        self._build_forms()
        self.status.setText("配置已同步")

    def _build_forms(self) -> None:
        while self.pages.count():
            widget = self.pages.widget(0)
            self.pages.removeWidget(widget)
            widget.deleteLater()
        self.sections.clear()
        self.fields.clear()
        for key, value in self.data.items():
            if key == "restart_required":
                continue
            self.sections.addItem(SECTION_LABELS.get(key, key))
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            page = QWidget()
            form = QFormLayout(page)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setContentsMargins(16, 14, 24, 20)
            if isinstance(value, dict):
                self._add_values(form, (key,), value)
            else:
                self._add_field(form, (key,), value)
            form.addRow(QWidget())
            scroll.setWidget(page)
            self.pages.addWidget(scroll)
        if self.sections.count():
            self.sections.setCurrentRow(0)

    def _add_values(self, form: QFormLayout, prefix: tuple[str, ...], values: dict) -> None:
        for key, value in values.items():
            path = (*prefix, key)
            if isinstance(value, dict) and (
                not value or all(not isinstance(v, (dict, list)) for v in value.values())
            ):
                self._add_field(form, path, value)
            elif isinstance(value, dict):
                heading = QLabel(key.replace("_", " ").title())
                heading.setObjectName("formHeading")
                form.addRow(heading)
                self._add_values(form, path, value)
            else:
                self._add_field(form, path, value)

    def _add_field(self, form: QFormLayout, path: tuple[str, ...], value: Any) -> None:
        label = path[-1].replace("_", " ").title()
        if isinstance(value, bool):
            widget: QWidget = QCheckBox()
            widget.setChecked(value)
        elif isinstance(value, int):
            widget = QSpinBox()
            widget.setRange(-2_000_000_000, 2_000_000_000)
            widget.setValue(value)
        elif isinstance(value, float):
            widget = QDoubleSpinBox()
            widget.setDecimals(4)
            widget.setRange(-1_000_000_000, 1_000_000_000)
            widget.setValue(value)
        elif isinstance(value, (list, dict)):
            widget = QPlainTextEdit(json.dumps(value, ensure_ascii=False, indent=2))
            widget.setMaximumHeight(110)
        else:
            widget = QLineEdit(str(value or ""))
            if path[-1] in {"api_key", "cookie", "sessdata"}:
                widget.setEchoMode(QLineEdit.EchoMode.Password)
        widget.setToolTip(".".join(path))
        self.fields[path] = (widget, type(value))
        form.addRow(label, widget)

    def _select_section(self, row: int) -> None:
        if row >= 0:
            self.pages.setCurrentIndex(row)

    def save(self) -> None:
        payload = copy.deepcopy(self.data)
        try:
            for path, (widget, value_type) in self.fields.items():
                value = self._widget_value(widget, value_type)
                target = payload
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "配置格式错误", str(exc))
            return
        self.status.setText("保存中…")
        self.api.send("PUT", "/config", payload, self._saved)

    @staticmethod
    def _widget_value(widget: QWidget, value_type: type) -> Any:
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QSpinBox):
            return widget.value()
        if isinstance(widget, QDoubleSpinBox):
            return widget.value()
        if isinstance(widget, QPlainTextEdit):
            return json.loads(widget.toPlainText())
        if isinstance(widget, QLineEdit):
            return widget.text()
        raise TypeError(f"不支持的配置控件：{value_type.__name__}")

    def _saved(self, ok: bool, data: Any, error: str) -> None:
        if not ok:
            self.status.setText(f"保存失败：{error}")
            return
        self.data = data
        restart = bool(data.get("restart_required")) if isinstance(data, dict) else False
        self.status.setText("已保存；需要重启生效" if restart else "已保存")
        self._build_forms()


class OperationsPage(QWidget):
    COMMANDS = [
        ("暂停 AI", "/sleep 1"),
        ("恢复 AI", "/sleep 0"),
        ("鼠标追踪", "/face 1"),
        ("自由漫步", "/face 0"),
        ("管理员接管", "/voice 1"),
        ("恢复 AI 主播", "/voice 0"),
        ("隐藏管理员弹幕", "/hide 1"),
        ("显示管理员弹幕", "/hide 0"),
    ]

    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self.api = api
        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        title = QLabel("直播运行操作")
        title.setObjectName("pageTitle")
        refresh = QPushButton("刷新状态")
        refresh.clicked.connect(self.refresh)
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(refresh)
        layout.addLayout(heading)

        command_box = QGroupBox("管理员指令")
        command_grid = QGridLayout(command_box)
        for index, (label, command) in enumerate(self.COMMANDS):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, value=command: self.command(value))
            command_grid.addWidget(button, index // 4, index % 4)
        layout.addWidget(command_box)

        test_box = QGroupBox("测试平台标准事件")
        test_form = QFormLayout(test_box)
        self.event_type = QComboBox()
        self.event_type.addItems(
            [
                "danmaku",
                "gift",
                "super_chat",
                "membership",
                "follow",
                "viewer_enter",
                "like",
                "room_stats",
                "live_ended",
            ]
        )
        self.user = QLineEdit("测试观众")
        self.user_id = QLineEdit("viewer")
        self.content = QLineEdit()
        self.gift_name = QLineEdit("小花花")
        self.gift_value = QDoubleSpinBox()
        self.gift_value.setRange(0, 1_000_000)
        self.gift_value.setSuffix(" 元")
        send = QPushButton("发送事件")
        send.setObjectName("primaryButton")
        send.clicked.connect(self.send_event)
        test_form.addRow("类型", self.event_type)
        test_form.addRow("用户", self.user)
        test_form.addRow("用户 ID", self.user_id)
        test_form.addRow("内容", self.content)
        test_form.addRow("礼物", self.gift_name)
        test_form.addRow("价值", self.gift_value)
        test_form.addRow(send)
        layout.addWidget(test_box)
        self.view = JsonView()
        layout.addWidget(self.view, 1)
        self.refresh()

    def refresh(self) -> None:
        self.api.send("GET", "/ai/admin/state", None, self._show)

    def command(self, command: str) -> None:
        self.api.send("POST", "/ai/admin/command", {"command": command}, self._show)

    def send_event(self) -> None:
        payload = {
            "type": self.event_type.currentText(),
            "user": self.user.text(),
            "user_id": self.user_id.text(),
            "content": self.content.text(),
            "gift_name": self.gift_name.text(),
            "gift_count": 1,
            "value_minor": round(self.gift_value.value() * 100),
            "stats": {},
        }
        self.api.send("POST", "/test/live/event", payload, self._show)

    def _show(self, ok: bool, data: Any, error: str) -> None:
        self.view.show_data(data if ok else {"error": error})


class SpeechPage(QWidget):
    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self.api = api
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        title = QLabel("Speech Gateway Provider")
        title.setObjectName("pageTitle")
        self.providers = QComboBox()
        self.providers.currentTextChanged.connect(self._select)
        reload_button = QPushButton("刷新")
        reload_button.clicked.connect(self.load)
        probe_button = QPushButton("连通测试")
        probe_button.clicked.connect(self.probe)
        save_button = QPushButton("保存 Provider")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.save)
        toolbar.addWidget(title)
        toolbar.addWidget(self.providers)
        toolbar.addStretch()
        toolbar.addWidget(reload_button)
        toolbar.addWidget(probe_button)
        toolbar.addWidget(save_button)
        layout.addLayout(toolbar)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Provider JSON 配置")
        layout.addWidget(self.editor, 2)
        route_bar = QHBoxLayout()
        route_bar.addWidget(QLabel("语音路由"))
        self.routes = QComboBox()
        self.routes.currentTextChanged.connect(self._select_route)
        save_route = QPushButton("保存路由")
        save_route.clicked.connect(self.save_route)
        route_bar.addWidget(self.routes)
        route_bar.addStretch()
        route_bar.addWidget(save_route)
        layout.addLayout(route_bar)
        self.route_editor = QPlainTextEdit()
        self.route_editor.setMaximumHeight(110)
        self.route_editor.setPlaceholderText('例如 {"primary": "edge", "fallback": []}')
        layout.addWidget(self.route_editor)
        self.result = JsonView()
        self.result.setMaximumHeight(180)
        layout.addWidget(self.result, 1)
        self.config: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        self.api.send("GET", "/speech-gateway/config", None, self._loaded)

    def _loaded(self, ok: bool, data: Any, error: str) -> None:
        if not ok or not isinstance(data, dict):
            self.result.show_data({"error": error})
            return
        self.config = data
        names = list(data.get("providers", {}))
        current = self.providers.currentText()
        route_names = list(data.get("routes", {}))
        current_route = self.routes.currentText()
        self.providers.blockSignals(True)
        self.providers.clear()
        self.providers.addItems(names)
        self.providers.setCurrentText(current if current in names else (names[0] if names else ""))
        self.providers.blockSignals(False)
        self._select(self.providers.currentText())
        self.routes.blockSignals(True)
        self.routes.clear()
        self.routes.addItems(route_names)
        self.routes.setCurrentText(
            current_route
            if current_route in route_names
            else (route_names[0] if route_names else "")
        )
        self.routes.blockSignals(False)
        self._select_route(self.routes.currentText())

    def _select(self, name: str) -> None:
        value = self.config.get("providers", {}).get(name, {})
        self.editor.setPlainText(json.dumps(value, ensure_ascii=False, indent=2))

    def save(self) -> None:
        name = self.providers.currentText()
        if not name:
            return
        try:
            payload = json.loads(self.editor.toPlainText())
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "JSON 格式错误", str(exc))
            return
        self.api.send("PUT", f"/speech-gateway/providers/{name}", payload, self._result)

    def _select_route(self, name: str) -> None:
        value = self.config.get("routes", {}).get(name, {})
        self.route_editor.setPlainText(json.dumps(value, ensure_ascii=False, indent=2))

    def save_route(self) -> None:
        name = self.routes.currentText()
        if not name:
            return
        try:
            payload = json.loads(self.route_editor.toPlainText())
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "JSON 格式错误", str(exc))
            return
        self.api.send("PUT", f"/speech-gateway/routes/{name}", payload, self._result)

    def probe(self) -> None:
        name = self.providers.currentText()
        if name:
            self.api.send("POST", f"/speech-gateway/providers/{name}/probe", None, self._result)

    def _result(self, ok: bool, data: Any, error: str) -> None:
        self.result.show_data(data if ok else {"error": error})
        if ok:
            self.load()


class MusicPage(QWidget):
    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self.api = api
        self.state: dict[str, Any] = {}
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        title = QLabel("音乐队列")
        title.setObjectName("pageTitle")
        self.query = QLineEdit()
        self.query.setPlaceholderText("歌曲名、BV 号或本地曲目")
        request = QPushButton("点歌")
        request.setObjectName("primaryButton")
        request.clicked.connect(self.request_song)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh)
        toolbar.addWidget(title)
        toolbar.addWidget(self.query, 1)
        toolbar.addWidget(request)
        toolbar.addWidget(refresh)
        layout.addLayout(toolbar)
        controls = QHBoxLayout()
        for label, callback in (
            ("暂停/继续", self.toggle_pause),
            ("切歌", self.skip),
            ("清空队列", self.clear),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        self.volume = QDoubleSpinBox()
        self.volume.setRange(0, 1)
        self.volume.setSingleStep(0.05)
        volume_button = QPushButton("设置音量")
        volume_button.clicked.connect(self.set_volume)
        self.ducking = QCheckBox("主播说话时自动压低")
        self.ducking.clicked.connect(self.set_ducking)
        controls.addWidget(self.volume)
        controls.addWidget(volume_button)
        controls.addWidget(self.ducking)
        controls.addStretch()
        layout.addLayout(controls)
        self.view = JsonView()
        layout.addWidget(self.view, 1)
        self.refresh()

    def refresh(self) -> None:
        self.api.send("GET", "/music/state", None, self._show)

    def request_song(self) -> None:
        if self.query.text().strip():
            self.api.send(
                "POST",
                "/music/requests",
                {"query": self.query.text().strip(), "requested_by": "desktop-console"},
                self._show,
            )

    def toggle_pause(self) -> None:
        self.api.send(
            "POST",
            "/music/commands/pause",
            {"paused": not bool(self.state.get("paused"))},
            self._show,
        )

    def skip(self) -> None:
        self.api.send("POST", "/music/commands/skip", None, self._show)

    def clear(self) -> None:
        self.api.send("DELETE", "/music/queue", None, self._show)

    def set_volume(self) -> None:
        self.api.send("POST", "/music/commands/volume", {"volume": self.volume.value()}, self._show)

    def set_ducking(self) -> None:
        self.api.send(
            "POST", "/music/commands/ducking", {"enabled": self.ducking.isChecked()}, self._show
        )

    def _show(self, ok: bool, data: Any, error: str) -> None:
        if ok and isinstance(data, dict):
            if "queue" in data:
                self.state = data
                self.volume.setValue(float(data.get("volume", 1)))
                self.ducking.setChecked(bool(data.get("ducking_enabled", True)))
            self.view.show_data(data)
        else:
            self.view.show_data({"error": error})


class InspectorPage(QWidget):
    def __init__(self, api: ApiClient, kind: str) -> None:
        super().__init__()
        self.api = api
        self.kind = kind
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        title = QLabel("Agent Runtime" if kind == "agent" else "记忆系统")
        title.setObjectName("pageTitle")
        toolbar.addWidget(title)
        toolbar.addStretch()
        actions = self._agent_actions() if kind == "agent" else self._memory_actions()
        for label, method, path, payload in actions:
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, m=method, p=path, b=payload: self.call(m, p, b))
            toolbar.addWidget(button)
        layout.addLayout(toolbar)
        if kind == "memory":
            search_row = QHBoxLayout()
            self.search = QLineEdit()
            self.search.setPlaceholderText("搜索原子记忆")
            search_button = QPushButton("搜索")
            search_button.clicked.connect(
                lambda: self.call(
                    "GET",
                    f"/ai/memory/atoms?keyword={quote(self.search.text())}&page_size=50",
                    None,
                )
            )
            recall_button = QPushButton("测试召回")
            recall_button.clicked.connect(
                lambda: self.call(
                    "POST", "/ai/memory/recall/test", {"query": self.search.text(), "k": 10}
                )
            )
            search_row.addWidget(self.search, 1)
            search_row.addWidget(search_button)
            search_row.addWidget(recall_button)
            layout.addLayout(search_row)
        self.view = JsonView()
        layout.addWidget(self.view, 1)
        self.refresh()

    @staticmethod
    def _agent_actions() -> list[tuple[str, str, str, Any]]:
        return [
            ("启动", "POST", "/agent/start", {}),
            ("停止", "POST", "/agent/stop", None),
            ("静音", "POST", "/agent/mute", None),
            ("解除静音", "POST", "/agent/unmute", None),
            ("共享上下文", "GET", "/agent/context", None),
            ("刷新", "GET", "/agent/status", None),
        ]

    @staticmethod
    def _memory_actions() -> list[tuple[str, str, str, Any]]:
        return [
            ("状态", "GET", "/ai/memory/stats", None),
            ("图概览", "GET", "/ai/memory/graph/overview", None),
            ("备份", "POST", "/ai/memory/backups", None),
            ("补齐向量", "POST", "/ai/memory/vector/backfill", None),
            ("重建向量", "POST", "/ai/memory/vector/rebuild", None),
        ]

    def refresh(self) -> None:
        self.call("GET", "/agent/status" if self.kind == "agent" else "/ai/memory/stats", None)

    def call(self, method: str, path: str, payload: Any) -> None:
        self.api.send(method, path, payload, self._show)

    def _show(self, ok: bool, data: Any, error: str) -> None:
        self.view.show_data(data if ok else {"error": error})


class OperationsConsole(QTabWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("operationsConsole")
        self.api = ApiClient(self)
        self.addTab(ConfigPage(self.api), "配置中心")
        self.addTab(OperationsPage(self.api), "直播操作")
        self.addTab(SpeechPage(self.api), "语音")
        self.addTab(MusicPage(self.api), "音乐")
        self.addTab(InspectorPage(self.api, "agent"), "Agent")
        self.addTab(InspectorPage(self.api, "memory"), "记忆")
