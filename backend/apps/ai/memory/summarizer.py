"""Batch viewer interactions into profile updates and atomic graph evidence."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from sqlalchemy import select

from apps.ai.memory.user_profile import SUMMARY_INTERVAL, UserProfile
from apps.db import (
    ViewerInteractionDB,
    ViewerSummaryBatchDB,
    async_session,
)

logger = logging.getLogger(__name__)

SUMMARY_BATCH_MESSAGES = 60
_summary_tasks: dict[str, asyncio.Task] = {}
_scheduler_task: asyncio.Task | None = None

MEMORY_SUMMARY_PROMPT = """请根据一批用户与 AI 主播的对话，更新用户印象并提取值得长期保存的原子事实。

【之前的用户印象】
{prev_impression}

【已有长期事实】
{prev_memory}

【本批对话】
{history}

要求：
1. 只保存关于用户的稳定偏好、可验证事实和关系，不保存普通寒暄或主播自己的话。
2. 可以输出 0~5 个互相独立、自包含的原子；不要重复已有长期事实。
3. type 只能是 viewer_preference、viewer_fact、viewer_relation。
4. relations 中主语指当前用户时统一写“用户”；predicate 使用简短稳定的英文关系名。
5. 即使没有新原子，也必须返回合法 JSON，并将 atoms 留空。

严格返回 JSON 对象，不要附加解释：
{{
  "impression": "20字以内的用户印象，没有变化则为空字符串",
  "atoms": [
    {{
      "content": "原子事实",
      "type": "viewer_preference",
      "importance": 0.0,
      "entities": ["实体"],
      "relations": [
        {{"subject": "用户", "predicate": "likes", "object": "实体", "stance": "supports"}}
      ]
    }}
  ]
}}
"""


def _parse_json_object(text: str) -> dict[str, Any] | None:
    payload = text.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        payload = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        logger.warning("用户记忆总结返回了无效 JSON: %s", text[:160])
        return None
    return parsed if isinstance(parsed, dict) else None


async def _pending_interactions(profile: UserProfile) -> list[ViewerInteractionDB]:
    await profile.flush()
    async with async_session() as session:
        return list(
            (
                await session.execute(
                    select(ViewerInteractionDB)
                    .where(
                        ViewerInteractionDB.user_id == profile.user_id,
                        ViewerInteractionDB.id
                        > profile.last_summarized_interaction_id,
                    )
                    .order_by(ViewerInteractionDB.id)
                    .limit(SUMMARY_BATCH_MESSAGES)
                )
            ).scalars().all()
        )


async def generate_user_memory_summary(
    profile: UserProfile, interactions: list[ViewerInteractionDB]
) -> dict[str, Any] | None:
    from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
    from apps.ai.memory.engine import get_memory_engine
    from apps.config import config

    ai = get_ai_client()
    if not ai.available or not interactions:
        return None

    existing = await get_memory_engine().store.search_fts(
        query="", limit=12, user_id=profile.user_id
    )
    history = "\n".join(
        f"{'用户' if item.role == 'user' else '主播'}: {item.content}"
        for item in interactions
    )
    prompt = MEMORY_SUMMARY_PROMPT.format(
        prev_impression=profile.impression or "（暂无）",
        prev_memory="\n".join(atom.content for atom in existing) or "（暂无）",
        history=history,
    )
    try:
        response = await ai.chat(
            ChatRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                model=config.llm_model,
                temperature=0.2,
                max_tokens=700,
                json_format=True,
            )
        )
        return _parse_json_object(response.content or "")
    except Exception:
        logger.exception("生成用户 %s 记忆总结失败", profile.user_id)
        return None


async def _get_or_create_batch_result(
    profile: UserProfile,
    interactions: list[ViewerInteractionDB],
    source_group_id: str,
) -> dict[str, Any] | None:
    async with async_session() as session:
        existing = await session.get(ViewerSummaryBatchDB, source_group_id)
        if existing:
            return _parse_json_object(existing.result_json)

    summary = await generate_user_memory_summary(profile, interactions)
    if summary is None:
        return None
    encoded = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    async with async_session() as session:
        existing = await session.get(ViewerSummaryBatchDB, source_group_id)
        if existing is None:
            session.add(
                ViewerSummaryBatchDB(
                    source_group_id=source_group_id,
                    user_id=profile.user_id,
                    first_interaction_id=interactions[0].id,
                    last_interaction_id=interactions[-1].id,
                    result_json=encoded,
                    created_at=time.time(),
                )
            )
            await session.commit()
            return summary
        return _parse_json_object(existing.result_json)

async def summarize_if_needed(
    profile: UserProfile, *, force: bool = False
) -> dict[str, Any] | None:
    interactions = await _pending_interactions(profile)
    if not interactions:
        return None

    user_turns = sum(item.role == "user" for item in interactions)
    if not force and user_turns < SUMMARY_INTERVAL:
        return None

    source_group_id = f"viewer-summary:{profile.user_id}:{interactions[0].id}-{interactions[-1].id}"
    summary = await _get_or_create_batch_result(
        profile, interactions, source_group_id
    )
    if summary is None:
        return None

    from apps.ai.memory.atom import AtomType, MemoryAtom
    from apps.ai.memory.engine import get_memory_engine

    allowed_types = {
        AtomType.VIEWER_PREFERENCE,
        AtomType.VIEWER_FACT,
        AtomType.VIEWER_RELATION,
    }
    atoms: list[MemoryAtom] = []
    atom_items = summary.get("atoms", [])
    if not isinstance(atom_items, list):
        atom_items = []
    for item in atom_items[:5]:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        try:
            atom_type = AtomType(str(item.get("type", "viewer_fact")))
        except ValueError:
            atom_type = AtomType.VIEWER_FACT
        if atom_type not in allowed_types:
            atom_type = AtomType.VIEWER_FACT
        relations = item.get("relations", [])
        try:
            importance = float(item.get("importance", 0.65))
        except (TypeError, ValueError):
            importance = 0.65
        atoms.append(
            MemoryAtom(
                source_group_id=source_group_id,
                atom_type=atom_type,
                content=content,
                entities=[
                    str(entity).strip()
                    for entity in item.get("entities", [])
                    if str(entity).strip()
                ],
                importance=min(1.0, max(0.0, importance)),
                confidence=0.75,
                user_id=profile.user_id,
                metadata={
                    "source": "viewer_interaction_summary",
                    "relations": relations if isinstance(relations, list) else [],
                },
            )
        )

    engine = get_memory_engine()
    existing_contents = await engine.store.source_group_contents(
        profile.user_id, source_group_id
    )
    pending_atoms: list[MemoryAtom] = []
    seen_contents = set(existing_contents)
    for atom in atoms:
        if atom.content not in seen_contents:
            pending_atoms.append(atom)
            seen_contents.add(atom.content)
    if pending_atoms:
        await engine.add_atoms(pending_atoms)

    impression = str(summary.get("impression", "")).strip()
    if impression:
        profile.impression = impression
    await profile.acknowledge_summary(interactions[-1].id, user_turns)
    return {
        "impression": impression,
        "atoms_created": len(pending_atoms),
        "interactions_processed": len(interactions),
    }


def trigger_summary_if_needed(profile: UserProfile, *, force: bool = False) -> bool:
    if not force and not profile.should_summarize():
        return False
    existing = _summary_tasks.get(profile.user_id)
    if existing and not existing.done():
        return False

    task = asyncio.create_task(summarize_if_needed(profile, force=force))
    _summary_tasks[profile.user_id] = task

    def _cleanup(done_task: asyncio.Task) -> None:
        _summary_tasks.pop(profile.user_id, None)
        try:
            done_task.result()
        except Exception:
            logger.exception("用户 %s 后台总结任务失败", profile.user_id)

    task.add_done_callback(_cleanup)
    return True


async def batch_summarize_active_users(hours: int = 24) -> int:
    from apps.ai.memory.user_profile import get_active_users

    updated = 0
    for profile in get_active_users(hours):
        if await summarize_if_needed(profile):
            updated += 1
    return updated


async def _summary_scheduler_loop() -> None:
    from apps.ai.memory.user_profile import get_all_profiles
    from apps.config import config

    while True:
        try:
            now = time.time()
            idle_seconds = max(1.0, config.ai_summary_idle_seconds)
            for profile in list(get_all_profiles().values()):
                if (
                    profile.interaction_count > profile.last_summary_count
                    and now - profile.last_interaction >= idle_seconds
                ):
                    trigger_summary_if_needed(profile, force=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("用户记忆定时总结扫描失败")
        await asyncio.sleep(max(5.0, config.ai_summary_scan_interval_seconds))


def start_summary_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_summary_scheduler_loop())


async def stop_summary_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    _scheduler_task = None
    running = [task for task in _summary_tasks.values() if not task.done()]
    if running:
        await asyncio.gather(*running, return_exceptions=True)


__all__ = [
    "batch_summarize_active_users",
    "generate_user_memory_summary",
    "start_summary_scheduler",
    "stop_summary_scheduler",
    "summarize_if_needed",
    "trigger_summary_if_needed",
]
