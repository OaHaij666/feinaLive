from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from apps.ai.client import AIClient
from apps.music.classification.llm import LLMMusicClassifier
from apps.music.classification.rules import RuleMusicClassifier
from apps.music.models import DecisionSource, Track


@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_deepseek_reviews_ambiguous_music_metadata():
    if os.getenv("RUN_MUSIC_LLM_TESTS") != "1":
        pytest.skip("set RUN_MUSIC_LLM_TESTS=1 to run the live LLM integration test")
    values = dotenv_values(Path(__file__).with_name(".env"))
    api_key = str(values.get("MUSIC_TEST_LLM_API_KEY") or "")
    if not api_key or api_key == "your_test_api_key":
        pytest.skip("backend/tests/.env does not contain a live test key")
    client = AIClient(
        api_url=str(values.get("MUSIC_TEST_LLM_API_URL") or ""),
        api_key=api_key,
        default_model=str(values.get("MUSIC_TEST_LLM_MODEL") or ""),
        disable_thinking=True,
    )
    track = Track(
        provider="bilibili",
        source_id="live-integration-test",
        title="三分钟学会《晴天》：后半段完整钢琴演奏",
        artists=["测试UP主"],
        duration_seconds=238,
        metadata={
            "tname": "演奏",
            "tags": ["钢琴", "演奏", "教学"],
            "description": "前半段讲解和弦，后半段提供完整演奏示范。",
        },
    )
    rules = RuleMusicClassifier().classify(track, query="晴天")
    result = await LLMMusicClassifier(min_confidence=0.75, client=client).classify(
        track,
        "晴天",
        rules,
    )
    assert result.source == DecisionSource.LLM
    assert result.confidence is not None and result.confidence > 0
    assert result.reason
