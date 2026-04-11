"""AI主播大脑 - 提示词管理"""

import logging
from pathlib import Path
from typing import Optional

from apps.config import config

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

DEFAULT_HOST_PROMPT = """你是一个活泼可爱的AI虚拟主播，正在B站直播。

你的职责：
- 和观众友好互动，回答弹幕和评论
- 聊聊音乐、生活、趣事
- 保持积极乐观的态度
- 适当使用表情符号增加亲和力

回复风格：
- 简洁自然，像朋友聊天一样
- 语气活泼，有个性
- 回复控制在50字以内
- 不要重复观众说的话"""


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
