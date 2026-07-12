from __future__ import annotations

from apps.agent.definition import ScenarioSpec
from apps.agent.mutual_context import MutualContext
from apps.agent.state import CapabilityResult, CommentaryRequest, Observation
from apps.ai.client import ChatMessage, ChatRequest, get_agent_ai_client
from apps.ai.prompt import get_host_system_prompt
from apps.config import config

COMMENTARY_COMPOSER_PROMPT = """你负责把 Agent 的简短解说请求写成主播最终要说的话。

【主播当前人设、表达习惯与长期上下文】
{host_context}

【双方近期共享动态】
{mutual_context}

【当前场景】
{scenario_name}

【Agent 解说请求】
事件：{event_summary}
原因：{reason}
证据：{evidence}
动作关联：{action_ref}

【当前可确认事实】
{facts}

只输出最终解说词。使用第一人称、自然口语，20—60 字；可以沿用上下文中的口癖。
禁止虚构尚未发生的结果；若事实里写明失败，必须如实表达。不要解释写作过程。"""


class CommentaryComposer:
    def __init__(self, scenario: ScenarioSpec, mutual_context: MutualContext) -> None:
        self._scenario = scenario
        self._mutual_context = mutual_context

    async def compose(
        self,
        request: CommentaryRequest,
        observations: list[Observation],
        results: list[CapabilityResult],
    ) -> str:
        ai = get_agent_ai_client()
        if not ai.available:
            return ""
        # The second pass is intentionally small: it receives compact evidence,
        # never the full tool catalog, full game state, or first-pass prompt.
        facts = [item.summary[:600] for item in observations[-1:]]
        facts.extend(
            f"{item.call.name}: {'成功' if item.success else '失败'} - "
            f"{str(item.output or item.error)[:500]}"
            for item in results[-2:]
        )
        prompt = COMMENTARY_COMPOSER_PROMPT.format(
            host_context=get_host_system_prompt(),
            mutual_context=await self._mutual_context.to_prompt_text(limit=6, max_chars=1800),
            scenario_name=self._scenario.display_name,
            event_summary=request.event_summary,
            reason=request.reason,
            evidence="、".join(request.evidence_refs) or "无额外引用",
            action_ref=request.action_ref or "无",
            facts="\n".join(f"- {item}" for item in facts) or "- 无额外事实",
        )
        response = await ai.chat(
            ChatRequest(
                messages=[
                    ChatMessage(role="system", content=prompt),
                    ChatMessage(role="user", content="输出最终解说词。"),
                ],
                model=config.agent_model,
                temperature=config.agent_temperature,
                max_tokens=min(160, config.agent_max_tokens),
                disable_thinking=config.agent_disable_thinking,
            )
        )
        return response.content.strip() if response and response.content else ""
