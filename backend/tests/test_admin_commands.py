"""管理员指令系统测试"""

import pytest

from apps.ai.admin_commands import (
    AdminCommandHandler,
    CommandResult,
    FaceMode,
)


@pytest.fixture
def handler():
    return AdminCommandHandler()


class TestAdminCommandHandler:
    def test_parse_sleep_command(self, handler):
        cmd, value = handler.parse_command("/sleep 1")
        assert cmd == "sleep"
        assert value == "1"

    def test_parse_face_command(self, handler):
        cmd, value = handler.parse_command("/face 0")
        assert cmd == "face"
        assert value == "0"

    def test_parse_voice_command(self, handler):
        cmd, value = handler.parse_command("/voice 1")
        assert cmd == "voice"
        assert value == "1"

    def test_parse_hide_command(self, handler):
        cmd, value = handler.parse_command("/hide 0")
        assert cmd == "hide"
        assert value == "0"

    def test_parse_invalid_command(self, handler):
        cmd, value = handler.parse_command("hello world")
        assert cmd is None
        assert value is None

    def test_parse_command_no_value(self, handler):
        cmd, value = handler.parse_command("/sleep")
        assert cmd == "sleep"
        assert value is None


class TestSleepCommand:
    def test_sleep_1_pauses_ai(self, handler):
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/sleep 1")
        assert result is not None
        assert result.success is True
        assert "暂停" in result.message
        assert handler.get_state().is_sleeping is True

    def test_sleep_0_resumes_ai(self, handler):
        handler._state.is_sleeping = True
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/sleep 0")
        assert result is not None
        assert result.success is True
        assert "恢复" in result.message
        assert handler.get_state().is_sleeping is False

    def test_sleep_no_value(self, handler):
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/sleep")
        assert result is not None
        assert result.success is False
        assert "用法" in result.message

    def test_sleep_invalid_value(self, handler):
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/sleep 2")
        assert result is not None
        assert result.success is False
        assert "用法" in result.message

    def test_sleep_non_admin_ignored(self, handler):
        result = handler.sync_handle(uid=123456, username="normal_user", content="/sleep 1")
        assert result is None


class TestFaceCommand:
    def test_face_1_mouse_tracking(self, handler):
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/face 1")
        assert result is not None
        assert result.success is True
        assert "鼠标追踪" in result.message
        assert handler.get_state().face_mode == FaceMode.MOUSE_TRACKING

    def test_face_0_wandering(self, handler):
        handler._state.face_mode = FaceMode.MOUSE_TRACKING
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/face 0")
        assert result is not None
        assert result.success is True
        assert "漫步" in result.message
        assert handler.get_state().face_mode == FaceMode.WANDERING

    def test_face_no_value(self, handler):
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/face")
        assert result is not None
        assert result.success is False
        assert "用法" in result.message

    def test_face_invalid_value(self, handler):
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/face 2")
        assert result is not None
        assert result.success is False
        assert "用法" in result.message


class TestVoiceCommand:
    def test_voice_1_admin_takeover(self, handler):
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/voice 1")
        assert result is not None
        assert result.success is True
        assert "接管模式" in result.message
        assert handler.get_state().is_voice_mode is True

    def test_voice_0_ai_host_mode(self, handler):
        handler._state.is_voice_mode = True
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/voice 0")
        assert result is not None
        assert result.success is True
        assert "AI主播" in result.message
        assert handler.get_state().is_voice_mode is False


class TestHideCommand:
    def test_hide_1_hides_admin_danmaku(self, handler):
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/hide 1")
        assert result is not None
        assert result.success is True
        assert "隐藏" in result.message
        assert handler.get_state().is_hide_admin is True

    def test_hide_0_shows_admin_danmaku(self, handler):
        handler._state.is_hide_admin = True
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/hide 0")
        assert result is not None
        assert result.success is True
        assert "显示" in result.message
        assert handler.get_state().is_hide_admin is False


class TestStateDict:
    def test_get_state_dict(self, handler):
        handler._state.is_sleeping = True
        handler._state.face_mode = FaceMode.MOUSE_TRACKING
        handler._state.is_voice_mode = True
        handler._state.is_hide_admin = False

        state_dict = handler.get_state_dict()
        assert state_dict["is_sleeping"] is True
        assert state_dict["face_mode"] == "mouse_tracking"
        assert state_dict["is_voice_mode"] is True
        assert state_dict["is_hide_admin"] is False


class TestShouldFilterAdminDanmaku:
    def test_hide_enabled_filters_admin(self, handler):
        handler._state.is_hide_admin = True
        assert handler.should_filter_admin_danmaku(uid=378810242, username="RongR0Ng") is True

    def test_hide_disabled_does_not_filter(self, handler):
        handler._state.is_hide_admin = False
        assert handler.should_filter_admin_danmaku(uid=378810242, username="RongR0Ng") is False

    def test_hide_enabled_does_not_filter_normal_user(self, handler):
        handler._state.is_hide_admin = True
        assert handler.should_filter_admin_danmaku(uid=999999, username="normal") is False


class TestShouldProcessDanmaku:
    def test_sleeping_blocks_danmaku(self, handler):
        handler._state.is_sleeping = True
        assert handler.should_process_danmaku(uid=123, username="user") is False

    def test_not_sleeping_allows_danmaku(self, handler):
        handler._state.is_sleeping = False
        assert handler.should_process_danmaku(uid=123, username="user") is True

    def test_voice_mode_blocks_non_admin(self, handler):
        handler._state.is_sleeping = False
        handler._state.is_voice_mode = True
        assert handler.should_process_danmaku(uid=123, username="user") is False

    def test_voice_mode_allows_admin(self, handler):
        handler._state.is_sleeping = False
        handler._state.is_voice_mode = True
        assert handler.should_process_danmaku(uid=378810242, username="RongR0Ng") is True


class TestIsVoiceMode:
    def test_voice_mode_with_admin(self, handler):
        handler._state.is_voice_mode = True
        assert handler.is_voice_mode(uid=378810242, username="RongR0Ng") is True

    def test_voice_mode_with_username(self, handler):
        handler._state.is_voice_mode = True
        assert handler.is_voice_mode(uid=0, username="RongR0Ng") is True

    def test_voice_mode_disabled(self, handler):
        handler._state.is_voice_mode = False
        assert handler.is_voice_mode(uid=378810242, username="RongR0Ng") is False

    def test_voice_mode_with_normal_user(self, handler):
        handler._state.is_voice_mode = True
        assert handler.is_voice_mode(uid=999999, username="normal") is False


class TestAdminByUsername:
    def test_admin_by_username_case_sensitive(self, handler):
        result = handler.sync_handle(uid=0, username="RongR0Ng", content="/sleep 1")
        assert result is not None
        assert result.success is True

    def test_admin_by_username_case_sensitive_rejected(self, handler):
        result = handler.sync_handle(uid=0, username="rongR0ng", content="/sleep 1")
        assert result is None


class TestHelpCommand:
    def test_help_returns_command_list(self, handler):
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/help")
        assert result is not None
        assert result.success is True
        assert "管理员指令列表" in result.message
        assert "/sleep" in result.message
        assert "/face" in result.message
        assert "/voice" in result.message
        assert "/hide" in result.message
        assert "当前状态" in result.message
        assert result.command == "/help"

    def test_help_shows_current_state(self, handler):
        handler._state.is_sleeping = True
        handler._state.face_mode = FaceMode.MOUSE_TRACKING
        handler._state.is_voice_mode = True
        handler._state.is_hide_admin = False

        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/help")
        assert "已暂停" in result.message
        assert "鼠标追踪" in result.message
        assert "接管模式" in result.message
        assert "显示" in result.message


class TestCommandResult:
    def test_command_result_structure(self, handler):
        result = handler.sync_handle(uid=378810242, username="RongR0Ng", content="/sleep 1")
        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.message is not None
        assert result.command == "/sleep"
        assert result.new_state is not None
        assert "is_sleeping" in result.new_state
