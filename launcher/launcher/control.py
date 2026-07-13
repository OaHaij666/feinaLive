"""Native operator-console pages backed by the local FastAPI control plane."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from PySide6.QtCore import QByteArray, Qt, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractItemView,
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

from launcher.i18n import localize_widget_tree, translate

API_ROOT = "http://127.0.0.1:9191"
Callback = Callable[[bool, Any, str], None]

FIELD_LABELS = {
    "platform": "当前平台",
    "room_id": "房间号",
    "sessdata": "SESSDATA",
    "uid": "用户 UID",
    "web_rid": "直播间 Web RID",
    "cookie": "Cookie",
    "api_url": "API 地址",
    "api_key": "API 密钥",
    "model": "模型名称",
    "temperature": "温度",
    "top_p": "Top P",
    "max_tokens": "最大 Token",
    "disable_thinking": "关闭思考模式",
    "reply_interval": "回复间隔（秒）",
    "max_reply_length": "最大回复长度",
    "enabled": "启用",
    "scenario_id": "场景",
    "mcp_url": "MCP 地址",
    "gateway_url": "Gateway 地址",
    "response_format": "音频格式",
    "speed": "语速",
    "timeout_seconds": "超时（秒）",
    "dimensions": "向量维度",
    "user_graph_enabled": "用户图启用向量",
    "game_graph_enabled": "游戏图启用向量",
    "sqlite_path": "SQLite 文件",
    "chroma_path": "ChromaDB 目录",
    "chroma_collection": "向量集合",
    "announcement": "直播公告",
    "username": "管理员名称",
    "identities": "各平台管理员身份",
    "scenario_config": "场景专属配置",
    "local_directories": "本地音乐目录",
    "max_history_per_session": "每会话最大历史数",
    "summary_interval": "总结触发消息数",
    "summary_idle_seconds": "空闲总结等待（秒）",
    "summary_scan_interval_seconds": "总结扫描间隔（秒）",
    "max_recent_messages": "最近消息上限",
    "poll_interval_seconds": "记忆轮询间隔（秒）",
    "poll_interval": "Agent 轮询间隔（秒）",
    "memory_threshold": "记忆总结事件数",
    "memory_idle_seconds": "记忆空闲总结（秒）",
    "memory_scan_interval_seconds": "记忆扫描间隔（秒）",
    "memory_context_max_chars": "记忆上下文最大字符",
    "min_step_interval": "最小行动间隔（秒）",
    "step_jitter": "行动间隔抖动",
    "commentary_interval": "解说间隔（秒）",
    "min_commentary_interval": "最小解说间隔（秒）",
    "commentary_hold_timeout": "解说等待超时（秒）",
    "memory_eagerness": "记忆积极度",
    "queue_max_size": "队列容量",
    "host_history_maxlen": "主播共享历史上限",
    "action_history_maxlen": "行动历史上限",
    "danmaku_starvation_seconds": "弹幕饥饿保护（秒）",
    "danmaku_flood_threshold": "弹幕洪峰阈值",
    "danmaku_flood_window": "弹幕洪峰窗口（秒）",
    "gift_starvation_seconds": "礼物饥饿保护（秒）",
    "gift_flood_threshold": "礼物洪峰阈值",
    "gift_flood_window": "礼物洪峰窗口（秒）",
    "gift_value_highest": "最高优先级礼物价值",
    "gift_value_high": "高优先级礼物价值",
    "gift_value_normal": "普通礼物价值",
    "gift_value_low": "低优先级礼物价值",
    "user_cooldown_seconds": "用户冷却（秒）",
    "default_ttl_seconds": "消息默认有效期（秒）",
    "rate_limit_commentary": "解说最小间隔（秒）",
    "rate_limit_danmaku": "弹幕最小间隔（秒）",
    "rate_limit_gift": "礼物最小间隔（秒）",
    "default_provider": "默认音乐 Provider",
    "min_duration_seconds": "最短时长（秒）",
    "max_duration_seconds": "最长时长（秒）",
    "queue_capacity": "点歌队列容量",
    "per_user_limit": "每用户点歌上限",
    "allow_bare_bv": "允许直接输入 BV 号",
    "accept_score": "直接通过分数",
    "reject_score": "直接拒绝分数",
    "llm_min_confidence": "免 LLM 最低置信度",
    "search_candidates": "搜索候选数",
    "ducking_factor": "自动压低比例",
    "ducking_enabled": "启用自动压低",
    "character": "角色",
    "source": "输入来源",
    "allow_browser_control": "允许浏览器控制",
    "sensitivity": "口型灵敏度",
    "noise_gate": "噪声门限",
    "attack_ms": "口型启动时间（毫秒）",
    "release_ms": "口型释放时间（毫秒）",
    "engine": "渲染引擎",
    "backend": "推理后端",
    "precision": "计算精度",
    "separable": "启用可分离模型",
    "use_eyebrow": "启用眉毛控制",
    "frame_rate": "帧率",
    "interpolation": "插帧倍率",
    "super_resolution": "超分倍率",
    "ram_cache_mb": "内存缓存（MB）",
    "vram_cache_mb": "显存缓存（MB）",
    "name": "输出名称",
    "quality": "预览质量",
    "motion": "动作",
    "lip_sync": "口型同步",
    "renderer": "渲染器",
    "outputs": "输出",
    "spout": "Spout 输出",
    "preview": "预览",
    "provider": "提供者",
    "voice": "音色",
    "encoding": "音频编码",
    "speed_ratio": "语速倍率",
}

MODEL_FIELDS = {
    "api_url",
    "api_key",
    "model",
    "temperature",
    "top_p",
    "max_tokens",
    "disable_thinking",
}
AGENT_MODEL_FIELDS = {
    "api_url",
    "api_key",
    "model",
    "temperature",
    "max_tokens",
    "disable_thinking",
}
EMBEDDING_MODEL_FIELDS = {"api_url", "api_key", "model", "dimensions"}


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
    def __init__(self, api: ApiClient, language: str = "zh") -> None:
        super().__init__()
        self.api = api
        self.language = language
        self.data: dict[str, Any] = {}
        self.options: dict[str, Any] = {}
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
        localize_widget_tree(self, self.language)
        self.load()

    def load(self) -> None:
        self.status.setText(translate("加载中…", self.language))
        self.api.send("GET", "/config", None, self._loaded)

    def _loaded(self, ok: bool, data: Any, error: str) -> None:
        if not ok or not isinstance(data, dict):
            prefix = "Load failed" if self.language == "en" else "加载失败"
            self.status.setText(f"{prefix}: {error}")
            return
        self.data = data
        self.api.send("GET", "/config/options", None, self._options_loaded)

    def _options_loaded(self, ok: bool, data: Any, _error: str) -> None:
        self.options = data if ok and isinstance(data, dict) else {}
        self._build_forms()
        self.status.setText(translate("配置已同步", self.language))
        localize_widget_tree(self, self.language)

    def _build_forms(self) -> None:
        selected_row = max(0, self.sections.currentRow())
        while self.pages.count():
            widget = self.pages.widget(0)
            self.pages.removeWidget(widget)
            widget.deleteLater()
        self.sections.clear()
        self.fields.clear()
        builders = [
            ("直播平台", self._build_live_page),
            ("模型配置", self._build_models_page),
            ("主播与消息", self._build_host_page),
            ("语音与数字人", self._build_output_page),
            ("Agent 场景", self._build_agent_page),
            ("音乐策略", self._build_music_page),
            ("记忆与数据", self._build_memory_page),
            ("管理员与公告", self._build_admin_page),
        ]
        for label, builder in builders:
            self.sections.addItem(label)
            self.pages.addWidget(builder())
        self.sections.setCurrentRow(min(selected_row, self.sections.count() - 1))
        localize_widget_tree(self, self.language)

    def _page(self, title: str, description: str) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 24, 24)
        layout.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("configPageTitle")
        intro = QLabel(description)
        intro.setObjectName("mutedText")
        intro.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(intro)
        scroll.setWidget(page)
        return scroll, layout

    def _group(
        self, layout: QVBoxLayout, title: str, description: str = ""
    ) -> tuple[QGroupBox, QFormLayout]:
        box = QGroupBox(title)
        box_layout = QVBoxLayout(box)
        if description:
            hint = QLabel(description)
            hint.setObjectName("mutedText")
            hint.setWordWrap(True)
            box_layout.addWidget(hint)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        box_layout.addLayout(form)
        layout.addWidget(box)
        return box, form

    def _section_values(
        self,
        form: QFormLayout,
        section: str,
        *,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
    ) -> None:
        values = self.data.get(section, {})
        if not isinstance(values, dict):
            return
        for key, value in values.items():
            if include is not None and key not in include:
                continue
            if exclude is not None and key in exclude:
                continue
            self._add_field(form, (section, key), value)

    def _build_live_page(self) -> QScrollArea:
        scroll, layout = self._page(
            "直播平台",
            "同一时间只启用一个平台。选择后仅填写该平台需要的房间与身份凭据，修改后重启生效。",
        )
        _, selector_form = self._group(layout, "平台选择")
        platform = str(self.data.get("live", {}).get("platform", "bilibili"))
        selector = self._add_field(
            selector_form,
            ("live", "platform"),
            platform,
            choices=[("Bilibili", "bilibili"), ("抖音", "douyin"), ("内部测试平台", "test")],
        )
        bilibili_box, bilibili_form = self._group(
            layout, "Bilibili 接入", "SESSDATA 属于敏感凭据，保存后进入系统密钥库。"
        )
        self._section_values(bilibili_form, "bilibili")
        douyin_box, douyin_form = self._group(
            layout, "抖音接入", "Cookie 属于敏感凭据，保存后进入系统密钥库。"
        )
        self._section_values(douyin_form, "douyin")
        test_box, _ = self._group(
            layout, "内部测试平台", "不连接外部直播服务；标准弹幕和礼物从“直播操作”页发送。"
        )

        def show_platform(value: str) -> None:
            bilibili_box.setVisible(value == "bilibili")
            douyin_box.setVisible(value == "douyin")
            test_box.setVisible(value == "test")

        if isinstance(selector, QComboBox):
            selector.currentIndexChanged.connect(lambda: show_platform(str(selector.currentData())))
            show_platform(str(selector.currentData()))
        layout.addStretch()
        return scroll

    def _build_models_page(self) -> QScrollArea:
        scroll, layout = self._page(
            "模型配置",
            "所有 OpenAI-compatible 模型集中配置。Bifrost 负责实际供应商、路由和 fallback。",
        )
        _, host = self._group(layout, "主播生成模型", "负责最终主播回复和解说词生成。")
        self._section_values(host, "host", include=MODEL_FIELDS)
        _, general = self._group(layout, "通用分析模型", "负责抽取、总结、审核等后台任务。")
        self._section_values(general, "llm", include=MODEL_FIELDS)
        _, agent = self._group(layout, "Agent 决策模型", "负责场景观察、工具选择和行动规划。")
        self._section_values(agent, "agent", include=AGENT_MODEL_FIELDS)
        _, embedding = self._group(
            layout, "Embedding 模型", "为空时知识图谱召回自动使用关键词兜底。"
        )
        self._section_values(embedding, "embedding", include=EMBEDDING_MODEL_FIELDS)
        layout.addStretch()
        return scroll

    def _build_host_page(self) -> QScrollArea:
        scroll, layout = self._page(
            "主播与消息",
            "配置回复节奏、消息优先级、饥饿保护、洪峰控制和队列速率。",
        )
        _, host = self._group(layout, "主播回复节奏")
        self._section_values(host, "host", exclude=MODEL_FIELDS)
        _, messaging = self._group(layout, "消息调度")
        self._section_values(messaging, "messaging")
        layout.addStretch()
        return scroll

    def _build_output_page(self) -> QScrollArea:
        scroll, layout = self._page(
            "语音与数字人",
            "这里配置主播输出链路；具体 Speech Provider 与 fallback 在上方“语音”运行页维护。",
        )
        _, tts = self._group(layout, "语音路由")
        self._section_values(tts, "tts")
        _, avatar = self._group(layout, "FeinaAvatar", "角色、渲染器和输出方式修改后需要重启。")
        values = self.data.get("avatar", {})
        if isinstance(values, dict):
            self._add_values(avatar, ("avatar",), values)
        layout.addStretch()
        return scroll

    def _build_agent_page(self) -> QScrollArea:
        scroll, layout = self._page(
            "Agent 场景",
            "场景、MCP 和能力装配在进程启动时固定；此页不重复显示模型参数。",
        )
        _, agent = self._group(layout, "场景与运行参数")
        self._section_values(agent, "agent", exclude=AGENT_MODEL_FIELDS)
        layout.addStretch()
        return scroll

    def _build_music_page(self) -> QScrollArea:
        scroll, layout = self._page(
            "音乐策略",
            "配置 Provider 路由、队列容量、审核阈值、本地目录与自动压低。实时播放操作在“音乐”页。",
        )
        _, music = self._group(layout, "点歌与播放策略")
        self._section_values(music, "music")
        layout.addStretch()
        return scroll

    def _build_memory_page(self) -> QScrollArea:
        scroll, layout = self._page(
            "记忆与数据",
            "配置用户总结、游戏记忆、SQLite 权威数据和 ChromaDB 可重建向量索引。",
        )
        _, memory = self._group(layout, "用户记忆调度")
        self._section_values(memory, "ai")
        _, graph = self._group(layout, "知识图谱召回")
        self._section_values(
            graph,
            "embedding",
            include={"user_graph_enabled", "game_graph_enabled"},
        )
        _, storage = self._group(layout, "存储位置", "路径修改后重启生效。")
        self._section_values(storage, "storage")
        layout.addStretch()
        return scroll

    def _build_admin_page(self) -> QScrollArea:
        scroll, layout = self._page(
            "管理员与公告",
            "配置管理员显示名称、各平台身份映射和直播间公告。",
        )
        _, admin = self._group(layout, "管理员身份")
        self._section_values(admin, "admin")
        _, announcement = self._group(layout, "直播公告")
        if "announcement" in self.data:
            self._add_field(announcement, ("announcement",), self.data["announcement"])
        layout.addStretch()
        return scroll

    def _add_values(self, form: QFormLayout, prefix: tuple[str, ...], values: dict) -> None:
        for key, value in values.items():
            path = (*prefix, key)
            if isinstance(value, dict) and value:
                heading = QLabel(FIELD_LABELS.get(key, key.replace("_", " ").title()))
                heading.setObjectName("formHeading")
                form.addRow(heading)
                self._add_values(form, path, value)
            else:
                self._add_field(form, path, value)

    def _add_field(
        self,
        form: QFormLayout,
        path: tuple[str, ...],
        value: Any,
        choices: list[tuple[str, Any]] | None = None,
    ) -> QWidget:
        label = FIELD_LABELS.get(path[-1], path[-1].replace("_", " ").title())
        choices = choices or self._choices_for_path(path, value)
        if choices:
            widget: QWidget = QComboBox()
            for text, stored_value in choices:
                widget.addItem(text, stored_value)
            index = widget.findData(value)
            if path == ("tts", "voice"):
                widget.setEditable(True)
                if index < 0:
                    widget.setEditText(str(value or ""))
                else:
                    widget.setCurrentIndex(index)
            else:
                widget.setCurrentIndex(max(0, index))
        elif isinstance(value, bool):
            widget: QWidget = QCheckBox()
            widget.setChecked(value)
        elif isinstance(value, int):
            widget = QSpinBox()
            minimum, maximum, step, _ = self._numeric_range(path, value)
            widget.setRange(int(minimum), int(maximum))
            widget.setSingleStep(max(1, int(step)))
            widget.setValue(value)
        elif isinstance(value, float):
            widget = QDoubleSpinBox()
            minimum, maximum, step, decimals = self._numeric_range(path, value)
            widget.setDecimals(decimals)
            widget.setRange(float(minimum), float(maximum))
            widget.setSingleStep(float(step))
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
        return widget

    def _choices_for_path(self, path: tuple[str, ...], value: Any) -> list[tuple[str, Any]] | None:
        dynamic: list[tuple[str, Any]] = []
        if path == ("tts", "provider"):
            values = self.options.get("speech_providers") or ["edge", "volcano", "local"]
            dynamic = [(str(item), str(item)) for item in values]
        elif path == ("tts", "model"):
            values = self.options.get("speech_routes") or ["host_voice"]
            dynamic = [(str(item), str(item)) for item in values]
        elif path in {("tts", "response_format"), ("tts", "encoding")}:
            values = self.options.get("speech_formats") or ["mp3", "wav", "pcm", "ogg_opus"]
            dynamic = [(str(item).upper(), str(item)) for item in values]
        elif path == ("tts", "voice"):
            values = self.options.get("speech_voices") or [
                "zh-CN-XiaoxiaoNeural",
                "zh-CN-YunxiNeural",
                "default",
            ]
            dynamic = [(str(item), str(item)) for item in values]
        elif path == ("music", "default_provider"):
            values = ["auto", *(self.options.get("music_providers") or ["bilibili", "local"])]
            dynamic = [(str(item), str(item)) for item in dict.fromkeys(values)]
        elif path == ("agent", "scenario_id"):
            scenarios = self.options.get("agent_scenarios") or [
                {"label": "通用 MCP", "value": "generic_mcp"},
                {"label": "杀戮尖塔", "value": "slay_the_spire"},
                {"label": "事件驱动助手", "value": "event_assistant"},
            ]
            dynamic = [
                (str(item.get("label", item.get("value", ""))), str(item.get("value", "")))
                for item in scenarios
            ]
        elif path == ("avatar", "character"):
            values = self.options.get("avatar_characters") or ["feina00"]
            dynamic = [(str(item), str(item)) for item in values]
        if dynamic:
            if value not in {stored for _, stored in dynamic}:
                dynamic.append((str(value), value))
            return dynamic
        return self._static_choices_for_path(path)

    @staticmethod
    def _static_choices_for_path(path: tuple[str, ...]) -> list[tuple[str, Any]] | None:
        options: dict[tuple[str, ...], list[tuple[str, Any]]] = {
            ("avatar", "motion", "source"): [
                ("直播定点（轻微晃动）", "broadcast_idle"),
                ("混合", "hybrid"),
                ("自主动作", "autonomous"),
                ("浏览器控制", "browser"),
            ],
            ("avatar", "lip_sync", "source"): [
                ("浏览器音频", "browser_audio"),
                ("禁用口型", "disabled"),
            ],
            ("avatar", "renderer", "model"): [
                ("THA3", "tha3"),
                ("THA4", "tha4"),
                ("THA4 Student", "tha4_student"),
            ],
            ("avatar", "renderer", "backend"): [
                ("ONNX Runtime", "onnxruntime"),
                ("TensorRT", "tensorrt"),
            ],
            ("avatar", "renderer", "precision"): [("FP32", "fp32"), ("FP16", "fp16")],
            ("avatar", "renderer", "engine"): [("FeinaAvatar", "feina_avatar")],
            ("avatar", "renderer", "interpolation"): [("1×", 1), ("2×", 2), ("4×", 4)],
            ("avatar", "renderer", "super_resolution"): [("1×", 1), ("2×", 2), ("4×", 4)],
        }
        return options.get(path)

    @staticmethod
    def _numeric_range(
        path: tuple[str, ...], value: int | float
    ) -> tuple[float, float, float, int]:
        path_ranges: dict[tuple[str, ...], tuple[float, float, float, int]] = {
            ("avatar", "renderer", "frame_rate"): (10, 60, 1, 0),
            ("avatar", "outputs", "preview", "frame_rate"): (1, 30, 1, 0),
        }
        if path in path_ranges:
            return path_ranges[path]
        key = path[-1]
        ranges: dict[str, tuple[float, float, float, int]] = {
            "temperature": (0, 2, 0.05, 2),
            "top_p": (0, 1, 0.05, 2),
            "speed": (0.25, 4, 0.05, 2),
            "speed_ratio": (0.25, 4, 0.05, 2),
            "timeout_seconds": (1, 300, 1, 1),
            "llm_min_confidence": (0, 1, 0.05, 2),
            "ducking_factor": (0, 1, 0.05, 2),
            "sensitivity": (0.1, 10, 0.1, 2),
            "noise_gate": (0, 0.5, 0.005, 3),
            "attack_ms": (1, 1000, 5, 1),
            "release_ms": (1, 2000, 5, 1),
            "frame_rate": (1, 60, 1, 0),
            "quality": (20, 100, 1, 0),
            "ram_cache_mb": (0, 32768, 128, 0),
            "vram_cache_mb": (0, 32768, 128, 0),
            "accept_score": (0, 100, 1, 0),
            "reject_score": (-100, 0, 1, 0),
            "search_candidates": (1, 20, 1, 0),
            "queue_capacity": (1, 1000, 1, 0),
            "per_user_limit": (1, 100, 1, 0),
            "min_duration_seconds": (1, 86400, 1, 0),
            "max_duration_seconds": (1, 86400, 1, 0),
            "reply_interval": (1, 60, 1, 0),
            "max_reply_length": (50, 500, 10, 0),
            "max_tokens": (1, 100000, 100, 0),
        }
        if key in ranges:
            return ranges[key]
        if isinstance(value, int):
            return (0, 2_000_000_000, 1, 0)
        return (0, 1_000_000_000, 0.1, 4)

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
        self.status.setText(translate("保存中…", self.language))
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
        if isinstance(widget, QComboBox):
            return widget.currentText() if widget.isEditable() else widget.currentData()
        if isinstance(widget, QLineEdit):
            if value_type is type(None):
                return int(widget.text()) if widget.text().strip() else None
            return widget.text()
        raise TypeError(f"不支持的配置控件：{value_type.__name__}")

    def _saved(self, ok: bool, data: Any, error: str) -> None:
        if not ok:
            prefix = "Save failed" if self.language == "en" else "保存失败"
            self.status.setText(f"{prefix}: {error}")
            return
        self.data = data
        restart = bool(data.get("restart_required")) if isinstance(data, dict) else False
        message = "已保存；需要重启生效" if restart else "已保存"
        self.status.setText(translate(message, self.language))
        self._build_forms()
        localize_widget_tree(self, self.language)


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
        provider_box = QGroupBox("提供者配置")
        self.provider_form = QFormLayout(provider_box)
        self.provider_type = QComboBox()
        self.provider_type.currentTextChanged.connect(self._provider_type_changed)
        self.provider_enabled = QCheckBox("启用")
        self.provider_form.addRow("类型", self.provider_type)
        self.provider_form.addRow("状态", self.provider_enabled)
        layout.addWidget(provider_box, 2)
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
        self.schemas: dict[str, dict[str, Any]] = {}
        self.provider_fields: dict[str, tuple[QWidget, dict[str, Any]]] = {}
        self.load()

    def load(self) -> None:
        self.api.send("GET", "/speech-gateway/config", None, self._loaded)

    def _loaded(self, ok: bool, data: Any, error: str) -> None:
        if not ok or not isinstance(data, dict):
            self.result.show_data({"error": error})
            return
        self.config = data
        self.api.send("GET", "/speech-gateway/provider-schemas", None, self._schemas_loaded)

    def _schemas_loaded(self, ok: bool, data: Any, error: str) -> None:
        if not ok or not isinstance(data, dict):
            self.result.show_data({"error": error})
            return
        values = data.get("data", [])
        self.schemas = {
            str(item["type"]): item
            for item in values
            if isinstance(item, dict) and item.get("type")
        }
        names = list(self.config.get("providers", {}))
        current = self.providers.currentText()
        route_names = list(self.config.get("routes", {}))
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
        provider_type = str(value.get("type", ""))
        self.provider_type.blockSignals(True)
        self.provider_type.clear()
        for schema_type, schema in self.schemas.items():
            self.provider_type.addItem(str(schema.get("label", schema_type)), schema_type)
        index = self.provider_type.findData(provider_type)
        self.provider_type.setCurrentIndex(max(0, index))
        self.provider_type.blockSignals(False)
        self.provider_enabled.setChecked(bool(value.get("enabled", True)))
        self._build_provider_fields(provider_type, value.get("values", {}))

    def _provider_type_changed(self, _text: str = "") -> None:
        provider_type = str(self.provider_type.currentData() or "")
        self._build_provider_fields(provider_type, {})

    def _clear_provider_fields(self) -> None:
        while self.provider_form.rowCount() > 2:
            self.provider_form.removeRow(2)
        self.provider_fields.clear()

    def _build_provider_fields(self, provider_type: str, values: dict[str, Any]) -> None:
        self._clear_provider_fields()
        schema = self.schemas.get(provider_type, {})
        for field in schema.get("fields", []):
            key = str(field.get("key", ""))
            if not key:
                continue
            value = values.get(key, field.get("default", ""))
            field_type = str(field.get("type", "text"))
            if field_type == "boolean":
                widget: QWidget = QCheckBox()
                widget.setChecked(bool(value))
            elif field_type == "number":
                widget = QDoubleSpinBox()
                widget.setRange(
                    float(field.get("min", -1_000_000)),
                    float(field.get("max", 1_000_000)),
                )
                widget.setValue(float(value or 0))
            elif field_type == "select":
                widget = QComboBox()
                for option in field.get("options", []):
                    widget.addItem(str(option), option)
                index = widget.findData(value)
                widget.setCurrentIndex(max(0, index))
            elif field_type == "multiselect":
                widget = QListWidget()
                widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
                selected = set(value or [])
                for option in field.get("options", []):
                    widget.addItem(str(option))
                    item = widget.item(widget.count() - 1)
                    item.setData(Qt.ItemDataRole.UserRole, option)
                    item.setSelected(option in selected)
                widget.setMaximumHeight(90)
            else:
                widget = QLineEdit(str(value or ""))
                widget.setPlaceholderText(str(field.get("placeholder", "")))
                if field_type == "secret":
                    widget.setEchoMode(QLineEdit.EchoMode.Password)
            self.provider_form.addRow(str(field.get("label", key)), widget)
            self.provider_fields[key] = (widget, field)

    def save(self) -> None:
        name = self.providers.currentText()
        if not name:
            return
        values: dict[str, Any] = {}
        for key, (widget, field) in self.provider_fields.items():
            if isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
            elif isinstance(widget, QDoubleSpinBox):
                values[key] = widget.value()
            elif isinstance(widget, QComboBox):
                values[key] = widget.currentData()
            elif isinstance(widget, QListWidget):
                values[key] = [
                    item.data(Qt.ItemDataRole.UserRole) for item in widget.selectedItems()
                ]
            elif isinstance(widget, QLineEdit):
                values[key] = widget.text().strip()
            else:
                continue
            if field.get("required") and (
                values[key] is None or values[key] == "" or values[key] == []
            ):
                QMessageBox.warning(self, "缺少配置", f"请填写 {field.get('label', key)}")
                return
        payload = {
            "type": str(self.provider_type.currentData() or ""),
            "enabled": self.provider_enabled.isChecked(),
            "values": values,
        }
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
    def __init__(self, language: str = "zh", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("operationsConsole")
        self.language = language
        self.api = ApiClient(self)
        self.addTab(ConfigPage(self.api, language), "配置中心")
        self.addTab(OperationsPage(self.api), "直播操作")
        self.addTab(SpeechPage(self.api), "语音")
        self.addTab(MusicPage(self.api), "音乐")
        self.addTab(InspectorPage(self.api, "agent"), "Agent")
        self.addTab(InspectorPage(self.api, "memory"), "记忆")
        localize_widget_tree(self, language)

    def set_language(self, language: str) -> None:
        self.language = language
        config = self.widget(0)
        if isinstance(config, ConfigPage):
            config.language = language
        localize_widget_tree(self, language)
