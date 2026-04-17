"""用户记忆模块 - 用户画像、对话历史、定期摘要"""

from apps.ai.memory.user_profile import (
    UserProfile,
    get_user_profile,
    clear_user_profile,
    get_all_profiles,
    get_active_users,
    save_all_profiles,
    init_user_profiles,
)
from apps.ai.memory.summarizer import (
    generate_user_memory_summary,
    summarize_if_needed,
    trigger_summary_if_needed,
)

__all__ = [
    "UserProfile",
    "get_user_profile",
    "clear_user_profile",
    "get_all_profiles",
    "get_active_users",
    "save_all_profiles",
    "init_user_profiles",
    "generate_user_memory_summary",
    "summarize_if_needed",
    "trigger_summary_if_needed",
]
