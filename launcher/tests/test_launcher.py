import json

from launcher.health import evaluate_health
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
