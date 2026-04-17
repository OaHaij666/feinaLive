"""AI调用模块 - 火山引擎 Doubao API 客户端"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

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
    disable_thinking: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class ChatResponse:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = ""


class AIClient:
    def __init__(self):
        self._api_url = config.llm_api_url.rstrip("/")
        self._api_key = config.llm_api_key
        self._default_model = config.llm_model

    @property
    def available(self) -> bool:
        return bool(self._api_url and self._api_key and self._default_model)

    def _resolve_params(self, request: ChatRequest) -> dict:
        params = {
            "model": request.model or self._default_model,
            "temperature": request.temperature if request.temperature is not None else config.llm_temperature,
            "top_p": request.top_p if request.top_p is not None else config.llm_top_p,
            "max_tokens": request.max_tokens if request.max_tokens is not None else config.llm_max_tokens,
        }
        if request.json_format:
            params["response_format"] = {"type": "json_object"}
        if request.disable_thinking or config.llm_disable_thinking:
            params["thinking"] = {"type": "disabled"}
        return params

    async def chat(self, request: ChatRequest) -> ChatResponse | None:
        if not self.available:
            logger.warning("AI配置不完整，跳过调用")
            return None
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
            "stream": request.stream,
            **request.extra,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            # 避免服务端返回 br 压缩，规避部分环境下 brotli 解码异常
            "Accept-Encoding": "identity",
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self._api_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                return self._parse_response(data)
        except httpx.HTTPStatusError as e:
            logger.error(f"AI请求HTTP错误 {e.response.status_code}: {e.response.text}")
            return None
        except httpx.DecodingError as e:
            logger.error(f"AI响应解码失败(可能为brotli压缩问题): {e}")
            return None
        except Exception as e:
            logger.error(f"AI请求失败: {e}")
            return None

    async def chat_stream(self, request: ChatRequest):
        if not self.available:
            logger.warning("AI配置不完整，跳过调用")
            return
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
            "stream": True,
        }
        if "response_format" in params:
            payload["response_format"] = params["response_format"]
        if "thinking" in params:
            payload["thinking"] = params["thinking"]
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            # 流式场景同样禁用压缩，避免 br 解码失败导致流中断
            "Accept-Encoding": "identity",
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{self._api_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            logger.error(f"AI流式请求失败: {e}")

    @staticmethod
    def _parse_response(data: dict) -> ChatResponse:
        choices = data.get("choices", [])
        content = ""
        finish_reason = ""
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            finish_reason = choices[0].get("finish_reason", "")
        usage = data.get("usage", {})
        return ChatResponse(
            content=content,
            model=data.get("model", ""),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            finish_reason=finish_reason,
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
