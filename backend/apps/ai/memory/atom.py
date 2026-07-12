"""记忆原子模型 — 细粒度、时间感知的长期记忆单元

参考: astrbot_plugin_livingmemory-master/core/models/memory_atom.py
适配: feinaLive 直播场景，扩展游戏/观众/主播类型
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AtomType(str, Enum):
    # === 游戏知识 (跨局保留，构建知识图谱) ===
    GAME_MECHANIC = "game_mechanic"       # 游戏机制规律 (如"遗物X配合遗物Y很强")
    GAME_LORE = "game_lore"               # 游戏背景知识

    # === 观众记忆 (跨局保留，照搬 LivingMemory) ===
    VIEWER_PREFERENCE = "viewer_preference"  # 观众偏好
    VIEWER_FACT = "viewer_fact"              # 观众事实
    VIEWER_RELATION = "viewer_relation"      # 观众关系

    # === 主播记忆 (跨局保留) ===
    HOST_PERSONALITY = "host_personality"    # 主播人设事实
    EPISODIC = "episodic"                    # 一般互动事件
    FACTUAL = "factual"                      # 一般事实

    # 通用
    UNKNOWN = "unknown"


class DecayType(str, Enum):
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    STEP = "step"


class AtomStatus(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    ARCHIVED = "archived"
    EXPIRED = "expired"
    FORGOTTEN = "forgotten"


def compute_decay_score(
    decay_type: DecayType | str,
    ttl_days: float,
    days_since: float,
) -> float:
    """计算时间衰减分数 (0-1)"""
    effective_ttl = max(1.0, ttl_days)
    days_since = max(0.0, days_since)
    decay_value = getattr(decay_type, "value", str(decay_type))

    if decay_value == DecayType.LINEAR.value:
        return max(0.0, 1.0 - days_since / effective_ttl)
    if decay_value == DecayType.STEP.value:
        return 1.0 if days_since <= effective_ttl else 0.05

    # 指数衰减
    half_life = effective_ttl / 2.0
    return math.exp(-math.log(2) * days_since / max(0.5, half_life))


# 各类型的 TTL 和衰减配置
_ATOM_TTL_CONFIG: dict[AtomType, dict[str, Any]] = {
    AtomType.GAME_MECHANIC: {"base_ttl": 180, "decay_type": DecayType.EXPONENTIAL},
    AtomType.GAME_LORE: {"base_ttl": 365, "decay_type": DecayType.EXPONENTIAL},
    AtomType.VIEWER_PREFERENCE: {"base_ttl": 60, "decay_type": DecayType.EXPONENTIAL},
    AtomType.VIEWER_FACT: {"base_ttl": 90, "decay_type": DecayType.LINEAR},
    AtomType.VIEWER_RELATION: {"base_ttl": 90, "decay_type": DecayType.LINEAR},
    AtomType.HOST_PERSONALITY: {"base_ttl": 365, "decay_type": DecayType.EXPONENTIAL},
    AtomType.EPISODIC: {"base_ttl": 7, "decay_type": DecayType.EXPONENTIAL},
    AtomType.FACTUAL: {"base_ttl": 180, "decay_type": DecayType.EXPONENTIAL},
    AtomType.UNKNOWN: {"base_ttl": 30, "decay_type": DecayType.EXPONENTIAL},
}


@dataclass(slots=True)
class MemoryAtom:
    """细粒度、时间感知的长期记忆原子"""

    # 身份
    source_group_id: str | None = None
    atom_type: AtomType = AtomType.UNKNOWN

    # 内容
    content: str = ""
    entities: list[str] = field(default_factory=list)
    importance: float = 0.5
    confidence: float = 0.7

    # 时间
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    last_reinforced_at: float | None = None
    event_time: float | None = None
    ttl_days: float = 30.0
    expires_at: float = 0.0

    # 生命周期
    status: AtomStatus = AtomStatus.ACTIVE
    reinforcement_count: int = 0
    decay_type: DecayType = DecayType.EXPONENTIAL

    # 作用域
    game_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    # 内部 ID，插入后设置
    atom_id: int = 0

    def compute_temporal_score(self, reference_time: float | None = None) -> float:
        """计算时间衰减分数 (0-1)"""
        if reference_time is None:
            reference_time = time.time()
        # Retrieval must not make a memory immortal. Only new supporting
        # evidence or an explicit reinforcement resets the decay anchor.
        anchor = self.last_reinforced_at or self.created_at
        days_since = max(0.0, (reference_time - anchor) / 86400.0)
        return compute_decay_score(self.decay_type, self.ttl_days, days_since)

    def is_expired(self, reference_time: float | None = None) -> bool:
        """检查是否已过期"""
        if reference_time is None:
            reference_time = time.time()
        return reference_time >= self.expires_at


def compute_ttl(
    atom_type: AtomType,
    importance: float = 0.5,
    reinforcement_count: int = 0,
    event_time: float | None = None,
) -> tuple[float, DecayType]:
    """计算 TTL (天) 和衰减类型"""
    cfg = _ATOM_TTL_CONFIG.get(atom_type, _ATOM_TTL_CONFIG[AtomType.UNKNOWN])
    base_ttl = float(cfg["base_ttl"])
    decay_type = DecayType(cfg["decay_type"])

    importance_factor = 0.5 + max(0.0, min(1.0, importance))
    reinforcement_factor = 1.0 + min(0.5, reinforcement_count * 0.1)
    ttl = base_ttl * importance_factor * reinforcement_factor

    return max(1.0, ttl), decay_type


__all__ = [
    "MemoryAtom",
    "AtomType",
    "DecayType",
    "AtomStatus",
    "compute_decay_score",
    "compute_ttl",
]
