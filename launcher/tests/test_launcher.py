import json
from pathlib import Path

from launcher.control import ConfigPage
from launcher.health import evaluate_health
from launcher.i18n import translate
from launcher.models import build_specs
from launcher.processes import clean_output


def test_backend_health_reports_degraded_component_state():
    result = evaluate_health("backend", 200, json.dumps({"status": "degraded"}).encode())
    assert result.state == "degraded"


def test_runtime_health_distinguishes_idle_from_failure():
    result = evaluate_health("agent", 200, json.dumps({"running": False}).encode())
    assert result.state == "idle"


def test_bifrost_authentication_response_still_proves_process_is_online():
    result = evaluate_health("bifrost", 401, b"")
    assert result.state == "degraded"


def test_log_cleaner_removes_terminal_control_sequences():
    assert clean_output("\x1b[32mok\x1b[0m\r\n") == "ok\n"


def test_native_console_replaces_the_old_nginx_console_module():
    specs = build_specs(Path("C:/workspace/feinaLive"))
    module_ids = {spec.id for spec in specs}
    assert "nginx_live" in module_ids
    assert "nginx_console" not in module_ids
    controlled = {spec.id for spec in specs if spec.controllable}
    assert {
        "bifrost",
        "speech",
        "backend",
        "mcp",
        "nginx_live",
        "avatar",
        "live",
        "agent",
    } <= controlled


def test_desktop_i18n_switches_business_labels_both_ways():
    assert translate("每会话最大历史数", "en") == "Max history per session"
    assert translate("Max history per session", "zh") == "每会话最大历史数"
    assert translate("直播平台", "en") == "Live platform"
    assert translate("资源 ID", "en") == "Resource ID"
    assert translate("Volcano Engine Doubao Speech V3", "zh") == "火山引擎豆包语音 V3"


def test_avatar_motion_source_defaults_to_broadcast_idle_order():
    choices = ConfigPage._static_choices_for_path(("avatar", "motion", "source"))
    assert choices is not None
    assert [value for _, value in choices] == [
        "broadcast_idle",
        "hybrid",
        "autonomous",
        "browser",
    ]


def test_all_bounded_avatar_and_speech_values_have_ui_constraints():
    assert ConfigPage._static_choices_for_path(("avatar", "renderer", "backend"))
    assert ConfigPage._static_choices_for_path(("avatar", "renderer", "precision"))
    assert ConfigPage._static_choices_for_path(("avatar", "renderer", "interpolation"))
    assert ConfigPage._static_choices_for_path(("avatar", "lip_sync", "source"))
    assert ConfigPage._numeric_range(("tts", "speed_ratio"), -5.0)[:2] == (0.25, 4)
    assert ConfigPage._numeric_range(("music", "llm_min_confidence"), 0.75)[:2] == (0, 1)
    assert ConfigPage._numeric_range(("avatar", "renderer", "frame_rate"), 30)[:2] == (
        10,
        60,
    )
