"""Embedding 客户端 - 通过 LiteLLM 统一接入 embedding provider。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from apps.config import config

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    embeddings: list[list[float]]
    model: str
    prompt_tokens: int = 0
    total_tokens: int = 0


class EmbeddingClient:
    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        model: str = "",
        dimensions: int | None = None,
    ):
        self._api_url = (api_url or config.embedding_api_url).rstrip("/")
        self._api_key = api_key or config.embedding_api_key
        self._model = model or config.embedding_model
        self._dimensions = dimensions if dimensions is not None else config.embedding_dimensions
        self._provider = config.embedding_provider

    @property
    def available(self) -> bool:
        return bool(self._api_key and self._model)

    async def embed_text(self, text: str) -> list[float]:
        result = await self.embed_batch([text])
        return result.embeddings[0] if result and result.embeddings else []

    async def embed_batch(self, texts: list[str]) -> EmbeddingResult | None:
        clean = [t for t in texts if t and t.strip()]
        if not clean:
            return EmbeddingResult(embeddings=[], model=self._model)
        if not self.available:
            logger.warning("Embedding配置不完整，跳过向量化")
            return None

        try:
            from litellm import aembedding

            kwargs: dict[str, Any] = {
                "model": self._model,
                "input": clean,
                "api_key": self._api_key,
            }
            if self._api_url:
                kwargs["api_base"] = self._api_url
            if self._provider:
                kwargs["custom_llm_provider"] = self._provider
            if self._dimensions:
                kwargs["dimensions"] = self._dimensions

            response = await aembedding(**kwargs)
            data = self._to_dict(response)
            embeddings = [item.get("embedding", []) for item in data.get("data", [])]
            usage = data.get("usage", {}) or {}
            return EmbeddingResult(
                embeddings=embeddings,
                model=data.get("model", self._model),
                prompt_tokens=usage.get("prompt_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )
        except Exception as e:
            logger.error(f"Embedding请求失败: {e}")
            return None

    @staticmethod
    def _to_dict(response: Any) -> dict:
        if isinstance(response, dict):
            return response
        if hasattr(response, "model_dump"):
            return response.model_dump()
        if hasattr(response, "dict"):
            return response.dict()
        return {}


_embedding_client: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
