"""AI主播大脑 - 提示词管理"""

import logging
from pathlib import Path
from typing import Optional

from apps.config import config

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

DEFAULT_HOST_PROMPT = """你是一个名叫菲娜的虚拟主播，正处于B站直播中。

【菲娜的性格特点】
- 说话像童话里的小女孩，用词温柔诗意
- 喜欢用"呀、呢、哦、唔、吧、吗"等语气词
- 自称"菲娜"
- 直播游玩“二重螺旋”这款游戏，游戏id叫“陈千千千千千语”

【菲娜的背景设定】
- 有一个叫"大魔法师"（也叫奥特赛德）的亲人，是说话最好听、最温柔的人
- 菲娜曾有妈妈，但妈妈已经不在了
- 菲娜喜欢蓝色，是天空和独角兽小姐鬃毛的颜色
- 菲娜喜欢蜂蜜吐司、热牛奶等甜食

【菲娜的说话风格】
- 句子较短，简洁而有韵律
- 喜欢把平常事物比喻成童话里的东西
- 回复前简要复述或概括用户弹幕内容（让观众知道这是在回复什么），但尽量避免完全一样地复读
- 回复控制在40字以内，像朋友聊天一样自然

【禁止事项】
- 不要重复用户说的话
- 不要说自己是AI或虚拟主播
- 不要一次回复过长
- 不要偏离童话感的人设
- 使用单纯的中文回复，回复不要加入动作描写，也不要有emoji类表情
- 如果遇到不会回答的问题可以说自己不知道，难以回答的问题可以拒绝回答""";


class PromptManager:
    _cache: dict[str, str] = {}

    @classmethod
    def get(cls, name: str) -> str:
        if name not in cls._cache:
            cls._cache[name] = cls._load(name)
        return cls._cache[name]

    @classmethod
    def _load(cls, name: str) -> str:
        prompt_file = PROMPTS_DIR / f"{name}.txt"
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8").strip()
        return DEFAULT_HOST_PROMPT

    @classmethod
    def reload(cls, name: Optional[str] = None) -> None:
        if name:
            cls._cache.pop(name, None)
        else:
            cls._cache.clear()

    @classmethod
    def list_available(cls) -> list[str]:
        if not PROMPTS_DIR.exists():
            return []
        return [f.stem for f in PROMPTS_DIR.glob("*.txt")]


def get_host_system_prompt() -> str:
    custom = config.llm_prompts.get("host_chat")
    if custom:
        return custom.strip()
    return PromptManager.get("host")


def build_chat_prompt(
    user_text: str,
    history_entries: list | None = None,
    system_prompt: str | None = None,
) -> list[dict]:
    system = system_prompt or get_host_system_prompt()
    messages = [{"role": "system", "content": system}]

    if history_entries:
        for entry in history_entries[-10:]:
            messages.append({"role": entry["role"], "content": entry["content"]})

    messages.append({"role": "user", "content": user_text})
    return messages
