"""管理员指令系统

支持指令:
- /sleep 1|0   - 暂停/恢复AI主播回复弹幕
- /face 1|0   - 切换AI数字人模式: 1=鼠标追踪, 0=漫步
- /voice 1|0  - 切换模式: 1=管理员接管, 0=AI主播
- /hide 1|0   - 管理员弹幕显示控制: 1=隐藏, 0=显示
- /sound 0-10 - 设置音乐音量
- /next      - 播放下一首歌
- /pause 1|0 - 暂停/恢复播放: 1=暂停, 0=恢复
- /rm        - 移除当前歌曲并跳到下一首
- /add_music BV号 - 发送BV号给LLM精炼后加入预备歌单
- /help       - 显示所有指令及当前状态
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from apps.config import config

logger = logging.getLogger(__name__)


class FaceMode(Enum):
    WANDERING = "wandering"
    MOUSE_TRACKING = "mouse_tracking"


@dataclass
class AdminState:
    is_sleeping: bool = False
    face_mode: FaceMode = FaceMode.WANDERING
    is_voice_mode: bool = False
    is_hide_admin: bool = False
    volume: float = 1.0
    is_paused: bool = False


@dataclass
class CommandResult:
    success: bool
    message: str
    command: str
    new_state: Optional[dict] = None


class AdminCommandHandler:
    ADMIN_COMMANDS = ["sleep", "face", "voice", "hide", "sound", "next", "pause", "rm", "add_music", "help"]
    COMMAND_PATTERN = re.compile(r"^/(\w+)\s*(\S*)$")

    def __init__(self):
        self._state = AdminState()
        self._face_mode_callbacks: list[Callable[[FaceMode], None]] = []
        self._state_change_callbacks: list[Callable[[dict], None]] = []
        self._volume_change_callbacks: list[Callable[[float], None]] = []
        self._pause_change_callbacks: list[Callable[[bool], None]] = []
        self._next_track_callbacks: list[Callable[[], None]] = []
        self._remove_track_callbacks: list[Callable[[], None]] = []

    def register_face_mode_callback(self, callback: Callable[[FaceMode], None]):
        self._face_mode_callbacks.append(callback)

    def register_state_change_callback(self, callback: Callable[[dict], None]):
        self._state_change_callbacks.append(callback)

    def notify_face_mode_change(self, mode: FaceMode):
        for cb in self._face_mode_callbacks:
            try:
                cb(mode)
            except Exception as e:
                logger.error(f"face_mode callback error: {e}")

    def notify_state_change(self):
        state_dict = self.get_state_dict()
        for cb in self._state_change_callbacks:
            try:
                cb(state_dict)
            except Exception as e:
                logger.error(f"state_change callback error: {e}")

    def register_volume_change_callback(self, callback: Callable[[float], None]):
        self._volume_change_callbacks.append(callback)

    def notify_volume_change(self, volume: float):
        for cb in self._volume_change_callbacks:
            try:
                cb(volume)
            except Exception as e:
                logger.error(f"volume_change callback error: {e}")

    def register_pause_change_callback(self, callback: Callable[[bool], None]):
        self._pause_change_callbacks.append(callback)

    def notify_pause_change(self, is_paused: bool):
        for cb in self._pause_change_callbacks:
            try:
                cb(is_paused)
            except Exception as e:
                logger.error(f"pause_change callback error: {e}")

    def register_next_track_callback(self, callback: Callable[[], None]):
        self._next_track_callbacks.append(callback)

    def notify_next_track(self):
        for cb in self._next_track_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"next_track callback error: {e}")

    def register_remove_track_callback(self, callback: Callable[[], None]):
        self._remove_track_callbacks.append(callback)

    def notify_remove_track(self):
        for cb in self._remove_track_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"remove_track callback error: {e}")

    def is_admin(self, uid: int) -> bool:
        return uid == config.admin_uid

    def is_admin_by_username(self, username: str) -> bool:
        return username == config.admin_username

    def parse_command(self, content: str) -> tuple[Optional[str], Optional[str]]:
        match = self.COMMAND_PATTERN.match(content.strip())
        if match:
            return match.group(1), match.group(2)
        return None, None

    def is_admin_command(self, content: str) -> bool:
        cmd, _ = self.parse_command(content)
        return cmd in self.ADMIN_COMMANDS

    def sync_handle(self, uid: int, username: str, content: str) -> Optional[CommandResult]:
        if not self.is_admin(uid) and not self.is_admin_by_username(username):
            return None

        cmd, value = self.parse_command(content)
        if not cmd:
            return None

        if cmd == "sleep":
            return self._handle_sleep(value)
        elif cmd == "face":
            return self._handle_face(value)
        elif cmd == "voice":
            return self._handle_voice(value)
        elif cmd == "hide":
            return self._handle_hide(value)
        elif cmd == "sound":
            return self._handle_sound(value)
        elif cmd == "next":
            return self._handle_next()
        elif cmd == "pause":
            return self._handle_pause(value)
        elif cmd == "rm":
            return self._handle_rm()
        elif cmd == "add_music":
            return None
        elif cmd == "help":
            return self._handle_help()
        else:
            return None

    async def handle(self, uid: int, username: str, content: str) -> Optional[CommandResult]:
        if not self.is_admin(uid) and not self.is_admin_by_username(username):
            return None

        cmd, value = self.parse_command(content)
        if not cmd:
            return None

        if cmd == "sleep":
            return self._handle_sleep(value)
        elif cmd == "face":
            return self._handle_face(value)
        elif cmd == "voice":
            return self._handle_voice(value)
        elif cmd == "hide":
            return self._handle_hide(value)
        elif cmd == "sound":
            return self._handle_sound(value)
        elif cmd == "next":
            return self._handle_next()
        elif cmd == "pause":
            return self._handle_pause(value)
        elif cmd == "rm":
            return self._handle_rm()
        elif cmd == "add_music":
            return await self._handle_add_music(value)
        elif cmd == "help":
            return self._handle_help()
        else:
            return None

    def _handle_sleep(self, value: Optional[str]) -> CommandResult:
        if value not in ["0", "1"]:
            return CommandResult(
                success=False,
                message="用法: /sleep 1(暂停) 或 /sleep 0(恢复)",
                command="/sleep"
            )

        is_sleep = value == "1"
        self._state.is_sleeping = is_sleep
        self.notify_state_change()

        message = "AI主播已暂停回复" if is_sleep else "AI主播已恢复回复"
        logger.info(f"Admin command: sleep {value} -> {message}")

        return CommandResult(
            success=True,
            message=message,
            command="/sleep",
            new_state=self.get_state_dict()
        )

    def _handle_face(self, value: Optional[str]) -> CommandResult:
        if value not in ["0", "1"]:
            return CommandResult(
                success=False,
                message="用法: /face 1(鼠标追踪) 或 /face 0(漫步)",
                command="/face"
            )

        is_mouse_tracking = value == "1"
        new_mode = FaceMode.MOUSE_TRACKING if is_mouse_tracking else FaceMode.WANDERING
        self._state.face_mode = new_mode
        self.notify_face_mode_change(new_mode)
        self.notify_state_change()

        message = "数字人切换为鼠标追踪模式" if is_mouse_tracking else "数字人切换为漫步模式"
        logger.info(f"Admin command: face {value} -> {message}")

        return CommandResult(
            success=True,
            message=message,
            command="/face",
            new_state=self.get_state_dict()
        )

    def _handle_voice(self, value: Optional[str]) -> CommandResult:
        if value not in ["0", "1"]:
            return CommandResult(
                success=False,
                message="用法: /voice 1(接管模式) 或 /voice 0(AI主播)",
                command="/voice"
            )

        is_voice = value == "1"
        self._state.is_voice_mode = is_voice
        self.notify_state_change()

        message = "已切换到管理员接管模式" if is_voice else "已切换到AI主播模式"
        logger.info(f"Admin command: voice {value} -> {message}")

        return CommandResult(
            success=True,
            message=message,
            command="/voice",
            new_state=self.get_state_dict()
        )

    def _handle_hide(self, value: Optional[str]) -> CommandResult:
        if value not in ["0", "1"]:
            return CommandResult(
                success=False,
                message="用法: /hide 1(隐藏) 或 /hide 0(显示)",
                command="/hide"
            )

        is_hide = value == "1"
        self._state.is_hide_admin = is_hide
        self.notify_state_change()

        message = "管理员弹幕已隐藏" if is_hide else "管理员弹幕已显示"
        logger.info(f"Admin command: hide {value} -> {message}")

        return CommandResult(
            success=True,
            message=message,
            command="/hide",
            new_state=self.get_state_dict()
        )

    def _handle_sound(self, value: Optional[str]) -> CommandResult:
        if not value:
            return CommandResult(
                success=False,
                message="用法: /sound 0-10 (设置音量为0-10)",
                command="/sound"
            )
        try:
            vol = int(value)
            if vol < 0 or vol > 10:
                return CommandResult(
                    success=False,
                    message="用法: /sound 0-10 (设置音量为0-10)",
                    command="/sound"
                )
            self._state.volume = vol / 10.0
            self.notify_volume_change(self._state.volume)
            self.notify_state_change()
            message = f"音量已设置为 {vol}/10"
            logger.info(f"Admin command: sound {vol} -> {message}")
            return CommandResult(
                success=True,
                message=message,
                command="/sound",
                new_state=self.get_state_dict()
            )
        except ValueError:
            return CommandResult(
                success=False,
                message="用法: /sound 0-10 (设置音量为0-10)",
                command="/sound"
            )

    def _handle_next(self) -> CommandResult:
        self.notify_next_track()
        self.notify_state_change()
        message = "正在播放下一首"
        logger.info("Admin command: /next")
        return CommandResult(
            success=True,
            message=message,
            command="/next",
            new_state=self.get_state_dict()
        )

    def _handle_pause(self, value: Optional[str]) -> CommandResult:
        if value not in ["0", "1"]:
            return CommandResult(
                success=False,
                message="用法: /pause 1(暂停) 或 /pause 0(恢复)",
                command="/pause"
            )
        is_pause = value == "1"
        self._state.is_paused = is_pause
        self.notify_pause_change(is_pause)
        self.notify_state_change()
        message = "已暂停播放" if is_pause else "已恢复播放"
        logger.info(f"Admin command: pause {value} -> {message}")
        return CommandResult(
            success=True,
            message=message,
            command="/pause",
            new_state=self.get_state_dict()
        )

    def _handle_rm(self) -> CommandResult:
        self.notify_remove_track()
        self.notify_state_change()
        message = "已移除当前歌曲并跳到下一首"
        logger.info("Admin command: /rm")
        return CommandResult(
            success=True,
            message=message,
            command="/rm",
            new_state=self.get_state_dict()
        )

    async def _handle_add_music(self, bvid: Optional[str]) -> CommandResult:
        if not bvid:
            return CommandResult(
                success=False,
                message="用法: /add_music BV号 (例如: /add_music BV1xx41117dM)",
                command="/add_music"
            )
        if not bvid.startswith("BV"):
            return CommandResult(
                success=False,
                message="无效的BV号，BV号应以BV开头",
                command="/add_music"
            )
        from apps.live.music.llm_verify import get_llm_verifier
        from apps.live.music.library import get_playlist_manager
        verifier = get_llm_verifier()
        library = get_playlist_manager()
        logger.info(f"Admin command: /add_music {bvid} - 正在发送给LLM验证")
        result = await verifier.verify(bvid)
        if not result:
            return CommandResult(
                success=False,
                message=f"LLM验证失败，可能是视频时长不符合要求(需60秒-8分钟)或获取视频信息失败",
                command="/add_music"
            )
        if not result.is_music:
            return CommandResult(
                success=False,
                message=f"LLM判定非音乐视频，原因: {result.reason}",
                command="/add_music"
            )
        item = await library.add(
            bvid=bvid,
            title=result.song_name,
            artist=result.artist,
        )
        if item:
            message = f"已加入预备歌单: {result.song_name} - {result.artist}"
            logger.info(f"Admin command: /add_music {bvid} -> {message}")
            return CommandResult(
                success=True,
                message=message,
                command="/add_music",
                new_state=self.get_state_dict()
            )
        return CommandResult(
            success=False,
            message="添加失败，可能已存在或数据库错误",
            command="/add_music"
        )

    def _handle_help(self) -> CommandResult:
        state = self.get_state()
        help_text = """【管理员指令列表】
/sleep 1 - 暂停AI回复
/sleep 0 - 恢复AI回复
/face 1 - 鼠标追踪模式
/face 0 - 漫步模式
/voice 1 - 接管模式
/voice 0 - AI主播模式
/hide 1 - 隐藏管理员弹幕
/hide 0 - 显示管理员弹幕

【当前状态】
AI回复: {}
数字人模式: {}
弹幕模式: {}
管理员弹幕: {}
音乐音量: {}/10
播放状态: {}""".format(
            "已暂停" if state.is_sleeping else "正常",
            "鼠标追踪" if state.face_mode == FaceMode.MOUSE_TRACKING else "漫步",
            "接管模式" if state.is_voice_mode else "AI主播",
            "隐藏" if state.is_hide_admin else "显示",
            int(state.volume * 10),
            "已暂停" if state.is_paused else "播放中"
        )
        return CommandResult(
            success=True,
            message=help_text,
            command="/help",
            new_state=self.get_state_dict()
        )

    def get_state(self) -> AdminState:
        return self._state

    def get_state_dict(self) -> dict:
        return {
            "is_sleeping": self._state.is_sleeping,
            "face_mode": self._state.face_mode.value,
            "is_voice_mode": self._state.is_voice_mode,
            "is_hide_admin": self._state.is_hide_admin,
            "volume": self._state.volume,
            "is_paused": self._state.is_paused,
        }

    def should_filter_admin_danmaku(self, uid: int, username: str) -> bool:
        if not self._state.is_hide_admin:
            return False
        return self.is_admin(uid) or self.is_admin_by_username(username)

    def should_process_danmaku(self, uid: int, username: str) -> bool:
        if self._state.is_sleeping:
            return False
        if self._state.is_voice_mode and not (self.is_admin(uid) or self.is_admin_by_username(username)):
            return False
        return True

    def is_voice_mode(self, uid: int, username: str) -> bool:
        if not self._state.is_voice_mode:
            return False
        return self.is_admin(uid) or self.is_admin_by_username(username)


_admin_handler: Optional[AdminCommandHandler] = None


def get_admin_handler() -> AdminCommandHandler:
    global _admin_handler
    if _admin_handler is None:
        _admin_handler = AdminCommandHandler()
    return _admin_handler
