"""用户记忆摘要 - 基于对话历史生成用户印象和长期记忆"""

import logging
from typing import Optional

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.ai.memory.user_profile import UserProfile

logger = logging.getLogger(__name__)

MEMORY_SUMMARY_PROMPT = """请根据以下用户与AI主播的对话历史，完成两个任务：

1. 【用户印象】（20字以内）
   总结该用户的性格特点、兴趣爱好、与主播的互动风格

2. 【长期记忆】（50字以内）
   提炼该用户重要的背景信息、偏好、习惯等，帮助主播更好地了解和记住该用户

对话历史：
{history}

请按以下格式输出：
【用户印象】...
【长期记忆】..."""


async def generate_user_memory_summary(profile: UserProfile) -> tuple[str, str]:
    ai = get_ai_client()
    if not ai.available:
        logger.warning("AI不可用，无法生成用户摘要")
        return profile.impression, profile.long_term_memory

    history_lines = []
    for m in profile.recent_messages:
        prefix = "用户" if m["role"] == "user" else "主播"
        history_lines.append(f"{prefix}: {m['content']}")
    
    if not history_lines:
        return profile.impression, profile.long_term_memory
    
    history_text = "\n".join(history_lines)
    prompt = MEMORY_SUMMARY_PROMPT.format(history=history_text)

    try:
        messages = [ChatMessage(role="user", content=prompt)]
        request = ChatRequest(
            messages=messages,
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=150,
        )
        response = await ai.chat(request)
        
        impression = ""
        long_term_memory = ""
        
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("【用户印象】"):
                impression = line[5:].strip()
            elif line.startswith("【长期记忆】"):
                long_term_memory = line[6:].strip()
        
        logger.info(f"用户 {profile.username} 摘要生成成功 - 印象: {impression[:30]}...")
        return impression, long_term_memory
        
    except Exception as e:
        logger.error(f"生成用户摘要失败: {e}")
        return profile.impression, profile.long_term_memory


async def summarize_if_needed(profile: UserProfile) -> Optional[dict]:
    if not profile.should_summarize():
        return None

    impression, long_term_memory = await generate_user_memory_summary(profile)
    
    if impression:
        profile.update_impression(impression)
    if long_term_memory:
        profile.update_long_term_memory(long_term_memory)
    
    profile.mark_summarized()
    
    return {
        "impression": impression,
        "long_term_memory": long_term_memory,
    }


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
