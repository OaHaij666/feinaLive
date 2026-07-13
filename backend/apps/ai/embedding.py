"""Embedding client backed by the external Bifrost Gateway."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

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
        self._api_key = api_key or config.embedding_api_key or ""
        self._model = model or config.embedding_model
        self._dimensions = dimensions if dimensions is not None else config.embedding_dimensions
        self._client: AsyncOpenAI | None = None

    @property
    def available(self) -> bool:
        return bool(self._api_url and self._model)

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self._api_url:
                raise RuntimeError("Bifrost Gateway API URL is not configured")
            self._client = AsyncOpenAI(
                base_url=self._api_url,
                api_key=self._api_key or "bifrost-local",
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def embed_text(self, text: str) -> list[float]:
        result = await self.embed_batch([text])
        return result.embeddings[0] if result and result.embeddings else []

    async def embed_batch(self, texts: list[str]) -> EmbeddingResult | None:
        clean = [text for text in texts if text and text.strip()]
        if not clean:
            return EmbeddingResult(embeddings=[], model=self._model)
        if not self.available:
            logger.warning("Bifrost Gateway 或 Embedding 模型未配置，跳过向量化")
            return None

        try:
            kwargs = {"model": self._model, "input": clean}
            if self._dimensions:
                kwargs["dimensions"] = self._dimensions
            response = await self._get_client().embeddings.create(**kwargs)
            usage = response.usage
            return EmbeddingResult(
                embeddings=[item.embedding for item in response.data],
                model=response.model,
                prompt_tokens=getattr(usage, "prompt_tokens", 0),
                total_tokens=getattr(usage, "total_tokens", 0),
            )
        except Exception:
            logger.exception("Bifrost embedding 请求失败")
            return None


_embedding_client: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
