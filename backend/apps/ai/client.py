"""AI调用模块 - 通过 LiteLLM 统一接入 OpenAI-compatible LLM。"""

import logging
from dataclasses import dataclass, field
from typing import Any

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
    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        default_model: str = "",
        disable_thinking: bool | None = None,
    ):
        self._api_url = (api_url or config.llm_api_url).rstrip("/")
        self._api_key = api_key or config.llm_api_key
        self._default_model = default_model or config.llm_model
        self._disable_thinking = disable_thinking
        self._provider = config.llm_provider

    async def close(self):
        """保持旧接口兼容；LiteLLM 自行管理底层连接。"""
        return None

    @property
    def available(self) -> bool:
        return bool(self._api_key and self._default_model)

    def _resolve_params(self, request: ChatRequest) -> dict:
        params = {
            "model": request.model or self._default_model,
            "temperature": request.temperature if request.temperature is not None else config.llm_temperature,
            "top_p": request.top_p if request.top_p is not None else config.llm_top_p,
            "max_tokens": request.max_tokens if request.max_tokens is not None else config.llm_max_tokens,
        }
        if request.json_format:
            params["response_format"] = {"type": "json_object"}
        should_disable = request.disable_thinking
        if should_disable is None:
            should_disable = self._disable_thinking if self._disable_thinking is not None else config.llm_disable_thinking
        if should_disable:
            params["thinking"] = {"type": "disabled"}
        return params

    def _build_payload(self, request: ChatRequest, stream: bool) -> dict:
        params = self._resolve_params(request)
        payload = {
            "model": params["model"],
            "messages": [
                {"role": m.role, "content": m.content}
                for m in request.messages
            ],
            "temperature": params["temperature"],
            "top_p": params["top_p"],
            "max_tokens": params["max_tokens"],
            "stream": stream,
            "drop_params": True,  # 自动丢弃模型不支持的参数（如 deepseek 不支持 thinking）
            **request.extra,
        }
        if self._api_key:
            payload["api_key"] = self._api_key
        if self._api_url:
            payload["api_base"] = self._api_url
        if self._provider and "/" not in params["model"]:
            payload["custom_llm_provider"] = self._provider
        if "response_format" in params:
            payload["response_format"] = params["response_format"]
        if "thinking" in params:
            payload["thinking"] = params["thinking"]
        if request.tools:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
        return payload

    async def chat(self, request: ChatRequest) -> ChatResponse | None:
        if not self.available:
            logger.warning("AI配置不完整，跳过调用")
            return None
        try:
            from litellm import acompletion

            response = await acompletion(**self._build_payload(request, stream=False))
            return self._parse_response(self._to_dict(response))
        except Exception as e:
            logger.error(f"AI请求失败: {e}")
            return None

    async def chat_stream(self, request: ChatRequest):
        if not self.available:
            logger.warning("AI配置不完整，跳过调用")
            return
        try:
            from litellm import acompletion

            stream = await acompletion(**self._build_payload(request, stream=True))
            async for chunk in stream:
                data = self._to_dict(chunk)
                choices = data.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {}) or {}
                content = delta.get("content")
                if content:
                    yield content
        except Exception as e:
            logger.error(f"AI流式请求失败: {e}")

    @staticmethod
    def _to_dict(response: Any) -> dict:
        if isinstance(response, dict):
            return response
        if hasattr(response, "model_dump"):
            return response.model_dump()
        if hasattr(response, "dict"):
            return response.dict()
        return {}

    @staticmethod
    def _parse_response(data: dict) -> ChatResponse:
        choices = data.get("choices", [])
        content = ""
        finish_reason = ""
        tool_calls: list[dict] = []
        if choices:
            msg = choices[0].get("message", {}) or {}
            content = msg.get("content", "") or ""
            tool_calls = msg.get("tool_calls", []) or []
            if not content:
                rc = msg.get("reasoning_content", "")
                if rc:
                    content = rc
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
        request = ChatRequest(
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_content),
            ],
            **kwargs,
        )
        resp = await self.chat(request)
        return resp.content if resp else None


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
