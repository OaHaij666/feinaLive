"""OpenAI-compatible chat client backed by the external Bifrost Gateway."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from apps.config import config

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    role: str
    content: str | list[dict]


@dataclass
class ChatRequest:
    messages: list[ChatMessage]
    model: str = ""
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    json_format: bool = False
    disable_thinking: bool | None = None
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class ChatResponse:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = ""
    tool_calls: list[dict] = field(default_factory=list)


class AIClient:
    """Thin client for Bifrost's OpenAI-compatible `/v1` endpoint."""

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        default_model: str = "",
        disable_thinking: bool | None = None,
    ):
        self._api_url = (api_url or config.llm_api_url).rstrip("/")
        self._api_key = api_key or config.llm_api_key or ""
        self._default_model = default_model or config.llm_model
        self._disable_thinking = disable_thinking
        self._client: AsyncOpenAI | None = None

    @property
    def available(self) -> bool:
        return bool(self._api_url and self._default_model)

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self._api_url:
                raise RuntimeError("Bifrost Gateway API URL is not configured")
            self._client = AsyncOpenAI(
                base_url=self._api_url,
                # The SDK requires a value. Bifrost may run without client auth.
                api_key=self._api_key or "bifrost-local",
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _build_payload(self, request: ChatRequest) -> dict[str, Any]:
        should_disable = request.disable_thinking
        if should_disable is None:
            should_disable = (
                self._disable_thinking
                if self._disable_thinking is not None
                else config.llm_disable_thinking
            )

        payload: dict[str, Any] = {
            "model": request.model or self._default_model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": (
                request.temperature
                if request.temperature is not None
                else config.llm_temperature
            ),
            "top_p": request.top_p if request.top_p is not None else config.llm_top_p,
            "max_tokens": (
                request.max_tokens
                if request.max_tokens is not None
                else config.llm_max_tokens
            ),
        }
        if request.json_format:
            payload["response_format"] = {"type": "json_object"}
        if request.tools:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice

        extra_body = dict(request.extra)
        if should_disable:
            extra_body.setdefault("thinking", {"type": "disabled"})
        if extra_body:
            payload["extra_body"] = extra_body
        return payload

    async def chat(self, request: ChatRequest) -> ChatResponse | None:
        if not self.available:
            logger.warning("Bifrost Gateway 或模型未配置，跳过 AI 调用")
            return None
        try:
            response = await self._get_client().chat.completions.create(
                **self._build_payload(request)
            )
            return self._parse_response(response.model_dump())
        except Exception:
            logger.exception("Bifrost chat completion 请求失败")
            return None

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        if not self.available:
            logger.warning("Bifrost Gateway 或模型未配置，跳过 AI 流式调用")
            return
        try:
            stream = await self._get_client().chat.completions.create(
                **self._build_payload(request), stream=True
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception:
            logger.exception("Bifrost chat completion 流式请求失败")

    @staticmethod
    def _parse_response(data: dict) -> ChatResponse:
        choices = data.get("choices", [])
        content = ""
        finish_reason = ""
        tool_calls: list[dict] = []
        if choices:
            message = choices[0].get("message", {}) or {}
            content = message.get("content", "") or message.get("reasoning_content", "") or ""
            tool_calls = message.get("tool_calls", []) or []
            finish_reason = choices[0].get("finish_reason", "") or ""
        usage = data.get("usage", {}) or {}
        return ChatResponse(
            content=content,
            model=data.get("model", ""),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )

    async def simple_chat(self, system_prompt: str, user_content: str, **kwargs) -> str | None:
        response = await self.chat(
            ChatRequest(
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_content),
                ],
                **kwargs,
            )
        )
        return response.content if response else None


_ai_client: AIClient | None = None


def get_ai_client() -> AIClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client


_agent_ai_client: AIClient | None = None


def get_agent_ai_client() -> AIClient:
    global _agent_ai_client
    if _agent_ai_client is None:
        _agent_ai_client = AIClient(
            api_url=config.agent_api_url,
            api_key=config.agent_api_key or "",
            default_model=config.agent_model,
            disable_thinking=config.agent_disable_thinking,
        )
    return _agent_ai_client
