"""用户记忆摘要 - 基于对话历史生成用户印象和长期记忆"""

import asyncio
import logging
from typing import Optional

from apps.ai.memory.user_profile import UserProfile

logger = logging.getLogger(__name__)
_summary_tasks: dict[str, asyncio.Task] = {}

MEMORY_SUMMARY_PROMPT = """请根据以下用户与AI主播的对话历史，更新用户印象和长期记忆。

【之前的用户印象】
{prev_impression}

【之前的长期记忆】
{prev_memory}

【本次对话历史】
{history}

请根据历史对话，在原有印象和记忆的基础上进行更新：
1. 【用户印象】（20字以内）
2. 【长期记忆】（尽量简短）

请按以下格式输出：
【用户印象】...
【长期记忆】..."""


async def generate_user_memory_summary(profile: UserProfile) -> Optional[tuple[str, str]]:
    from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
    from apps.config import config
    
    ai = get_ai_client()
    if not ai.available:
        logger.warning("AI不可用，无法生成用户摘要")
        return None

    history_lines = []
    for m in profile.recent_messages:
        prefix = "用户" if m["role"] == "user" else "主播"
        history_lines.append(f"{prefix}: {m['content']}")
    
    if not history_lines:
        return None
    
    history_text = "\n".join(history_lines)
    prompt = MEMORY_SUMMARY_PROMPT.format(
        prev_impression=profile.impression or "（暂无）",
        prev_memory=profile.long_term_memory or "（暂无）",
        history=history_text,
    )

    try:
        messages = [ChatMessage(role="user", content=prompt)]
        request = ChatRequest(
            messages=messages,
            model=config.llm_model,
            temperature=0.3,
            max_tokens=150,
        )
        response = await ai.chat(request)
        
        impression = ""
        long_term_memory = ""
        
        for line in response.content.split("\n"):
            line = line.strip()
            if line.startswith("【用户印象】"):
                impression = line[5:].strip()
            elif line.startswith("【长期记忆】"):
                long_term_memory = line[6:].strip()
        
        if not impression and not long_term_memory:
            logger.warning(f"用户 {profile.username} 摘要结果为空，跳过更新")
            return None

        logger.info(f"用户 {profile.username} 摘要生成成功 - 印象: {impression[:30]}...")
        return impression, long_term_memory
        
    except Exception as e:
        logger.error(f"生成用户摘要失败: {e}")
        return None


async def summarize_if_needed(profile: UserProfile) -> Optional[dict]:
    if not profile.should_summarize():
        return None

    summary = await generate_user_memory_summary(profile)
    if not summary:
        # 摘要失败/不可用时不推进游标，保留 recent_messages 供后续重试
        return None

    impression, long_term_memory = summary

    if impression:
        profile.update_impression(impression)
    if long_term_memory:
        profile.update_long_term_memory(long_term_memory)

    profile.recent_messages.clear()
    profile.mark_summarized()

    return {
        "impression": impression,
        "long_term_memory": long_term_memory,
    }


def trigger_summary_if_needed(profile: UserProfile) -> bool:
    """后台触发摘要，不阻塞主播回复链路。"""
    if not profile.should_summarize():
        return False

    existing = _summary_tasks.get(profile.user_id)
    if existing and not existing.done():
        return False

    async def _run():
        result = await summarize_if_needed(profile)
        if result:
            logger.info(f"用户 {profile.username} 后台记忆摘要完成")

    task = asyncio.create_task(_run())
    _summary_tasks[profile.user_id] = task

    def _cleanup(done_task: asyncio.Task):
        _summary_tasks.pop(profile.user_id, None)
        try:
            done_task.result()
        except Exception as e:
            logger.error(f"用户 {profile.username} 后台摘要任务异常: {e}")

    task.add_done_callback(_cleanup)
    return True


async def batch_summarize_active_users(hours: int = 24) -> int:
    from apps.ai.memory.user_profile import get_active_users

    active_users = get_active_users(hours)
    updated_count = 0

    for profile in active_users:
        if profile.should_summarize():
            result = await summarize_if_needed(profile)
            if result:
                updated_count += 1

    logger.info(f"批量摘要完成: 更新了 {updated_count} 个用户画像")
    return updated_count
