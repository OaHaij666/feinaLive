import json
from pathlib import Path

from launcher.health import evaluate_health
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
    module_ids = {spec.id for spec in build_specs(Path("C:/workspace/feinaLive"))}
    assert "nginx_live" in module_ids
    assert "nginx_console" not in module_ids
