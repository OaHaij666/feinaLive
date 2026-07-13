from __future__ import annotations

import re

from apps.music.models import (
    ClassificationDecision,
    ClassificationVerdict,
    DecisionSource,
    Evidence,
    Track,
)

POSITIVE_TITLE = (
    "翻唱",
    "cover",
    "原创曲",
    "原创歌曲",
    "纯音乐",
    "纯享",
    "完整版",
    "official mv",
    "music video",
    "演奏",
    "单曲",
)
POSITIVE_TAGS = ("原创音乐", "翻唱", "纯音乐", "演奏", "mv", "音乐现场", "虚拟歌手")
NEGATIVE_TITLE = (
    "教程",
    "教学",
    "学会",
    "如何",
    "reaction",
    "解析",
    "评测",
    "访谈",
    "杂谈",
    "直播回放",
    "切片",
    "盘点",
    "推荐歌单",
    "音乐推荐",
)
NEGATIVE_DESCRIPTION = ("本期教程", "教你如何", "逐句解析", "reaction", "访谈节目")
MUSIC_CATEGORY_WORDS = ("音乐", "原创音乐", "翻唱", "演奏", "mv", "音乐现场", "虚拟歌手")
NON_MUSIC_CATEGORY_WORDS = ("知识", "游戏", "影视", "资讯", "科技", "生活", "娱乐")


class RuleMusicClassifier:
    def __init__(self, *, accept_score: int = 60, reject_score: int = -50) -> None:
        self._accept_score = accept_score
        self._reject_score = reject_score

    def classify(self, track: Track, query: str = "") -> ClassificationDecision:
        title = track.title.casefold()
        description = str(track.metadata.get("description") or "").casefold()
        tags = [str(tag).casefold() for tag in track.metadata.get("tags") or []]
        category = str(track.metadata.get("tname") or "").casefold()
        evidence: list[Evidence] = []

        if any(word in category for word in MUSIC_CATEGORY_WORDS):
            evidence.append(Evidence(code="MUSIC_CATEGORY", weight=35, value=category))
        elif any(word in category for word in NON_MUSIC_CATEGORY_WORDS):
            evidence.append(Evidence(code="NON_MUSIC_CATEGORY", weight=-25, value=category))

        positive_title = next((word for word in POSITIVE_TITLE if word in title), None)
        if positive_title:
            evidence.append(Evidence(code="MUSIC_TITLE", weight=15, value=positive_title))
        negative_title = next((word for word in NEGATIVE_TITLE if word in title), None)
        if negative_title:
            weight = -45 if negative_title in {"访谈", "杂谈", "直播回放", "切片"} else -35
            evidence.append(Evidence(code="NON_MUSIC_TITLE", weight=weight, value=negative_title))

        matching_tags = sorted({word for word in POSITIVE_TAGS if any(word in tag for tag in tags)})
        if matching_tags:
            evidence.append(Evidence(code="MUSIC_TAGS", weight=20, value=", ".join(matching_tags)))

        negative_description = next(
            (word for word in NEGATIVE_DESCRIPTION if word in description), None
        )
        if negative_description:
            evidence.append(
                Evidence(code="NON_MUSIC_DESCRIPTION", weight=-20, value=negative_description)
            )

        normalized_query = _normalize(query)
        normalized_title = _normalize(track.title)
        if normalized_query and len(normalized_query) >= 2:
            if normalized_query in normalized_title or normalized_title in normalized_query:
                evidence.append(Evidence(code="REQUEST_MATCH", weight=10, value=query))
            elif _token_overlap(normalized_query, normalized_title) < 0.25:
                evidence.append(Evidence(code="REQUEST_MISMATCH", weight=-20, value=query))

        score = max(-100, min(100, sum(item.weight for item in evidence)))
        has_positive = any(item.weight >= 20 for item in evidence)
        has_negative = any(item.weight <= -20 for item in evidence)
        has_conflict = has_positive and has_negative

        if score >= self._accept_score and not has_conflict:
            verdict = ClassificationVerdict.ACCEPT
        elif score <= self._reject_score and not has_conflict:
            verdict = ClassificationVerdict.REJECT
        else:
            verdict = ClassificationVerdict.REVIEW
        return ClassificationDecision(
            verdict=verdict,
            rule_score=score,
            has_conflict=has_conflict,
            source=DecisionSource.RULES,
            title=track.title,
            artists=track.artists,
            reason=_reason(verdict, score, has_conflict),
            evidence=evidence,
        )


def _normalize(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value.casefold())


def _token_overlap(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_pairs = {left[index : index + 2] for index in range(max(1, len(left) - 1))}
    right_pairs = {right[index : index + 2] for index in range(max(1, len(right) - 1))}
    return len(left_pairs & right_pairs) / max(1, len(left_pairs))


def _reason(verdict: ClassificationVerdict, score: int, conflict: bool) -> str:
    if conflict:
        return f"规则证据存在冲突（score={score}）"
    if verdict == ClassificationVerdict.ACCEPT:
        return f"音乐证据充分（score={score}）"
    if verdict == ClassificationVerdict.REJECT:
        return f"非音乐证据充分（score={score}）"
    return f"规则证据不足（score={score}）"
