"""feinaLive 记忆系统

单局记忆: SessionMemory (三层文本块，新游戏清空)
长期记忆: AtomStore (SQLite + FTS5，时间衰减)
知识图谱: GameKnowledgeGraph (按游戏ID独立存储)
用户画像: UserProfile (SQLAlchemy 持久化)
"""

from apps.ai.memory.atom import AtomStatus, AtomType, DecayType, MemoryAtom, compute_ttl
from apps.ai.memory.atom_store import AtomStore
from apps.ai.memory.engine import MemoryEngine, get_memory_engine, init_memory_engine
from apps.ai.memory.game_memory import GameMemoryAPI, GameMemoryContext, GameMemoryPolicy
from apps.ai.memory.graph_store import GameKnowledgeGraph
from apps.ai.memory.injector import MemoryInjector
from apps.ai.memory.lifecycle import AtomLifecycleManager
from apps.ai.memory.session_memory import SessionMemory
from apps.ai.memory.summarizer import (
    start_summary_scheduler,
    stop_summary_scheduler,
    trigger_summary_if_needed,
)
from apps.ai.memory.tools import get_memory_tools, handle_memory_tool_call
from apps.ai.memory.user_profile import (
    UserProfile,
    clear_user_profile,
    get_active_users,
    get_all_profiles,
    get_user_profile,
    init_user_profiles,
    save_all_profiles,
)

__all__ = [
    "AtomType",
    "AtomStatus",
    "DecayType",
    "MemoryAtom",
    "compute_ttl",
    "AtomStore",
    "SessionMemory",
    "GameKnowledgeGraph",
    "GameMemoryContext",
    "GameMemoryAPI",
    "GameMemoryPolicy",
    "MemoryEngine",
    "get_memory_engine",
    "init_memory_engine",
    "MemoryInjector",
    "AtomLifecycleManager",
    "get_memory_tools",
    "handle_memory_tool_call",
    "UserProfile",
    "get_user_profile",
    "get_all_profiles",
    "get_active_users",
    "clear_user_profile",
    "init_user_profiles",
    "save_all_profiles",
    "start_summary_scheduler",
    "stop_summary_scheduler",
    "trigger_summary_if_needed",
]
