from types import SimpleNamespace

import pytest

from apps.ai.client import AIClient, ChatMessage, ChatRequest
from apps.ai.embedding import EmbeddingClient


class _CompletionEndpoint:
    def __init__(self, response=None, stream=None):
        self.response = response
        self.stream = stream
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.stream if kwargs.get("stream") else self.response


class _EmbeddingEndpoint:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _AsyncChunks:
    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        self._iter = iter(self.chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeOpenAI:
    def __init__(self, completion=None, stream=None, embedding=None):
        self.chat = SimpleNamespace(
            completions=_CompletionEndpoint(completion, stream)
        )
        self.embeddings = _EmbeddingEndpoint(embedding)
        self.closed = False

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_chat_uses_bifrost_openai_contract_without_client_api_key():
    response = SimpleNamespace(
        model_dump=lambda: {
            "model": "deepseek/deepseek-chat",
            "choices": [
                {
                    "message": {"content": "你好", "tool_calls": []},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }
    )
    fake = _FakeOpenAI(completion=response)
    client = AIClient(
        api_url="http://127.0.0.1:8081/v1",
        api_key="",
        default_model="deepseek/deepseek-chat",
        disable_thinking=True,
    )
    client._client = fake

    result = await client.chat(
        ChatRequest(
            messages=[ChatMessage(role="user", content="你好")],
            json_format=True,
            extra={"trace_id": "reply-1"},
        )
    )

    assert result is not None
    assert result.content == "你好"
    assert result.total_tokens == 5
    payload = fake.chat.completions.calls[0]
    assert payload["model"] == "deepseek/deepseek-chat"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["extra_body"] == {
        "trace_id": "reply-1",
        "thinking": {"type": "disabled"},
    }


@pytest.mark.asyncio
async def test_chat_stream_forwards_text_deltas():
    chunks = _AsyncChunks(
        [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="你"))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="好"))]),
        ]
    )
    fake = _FakeOpenAI(stream=chunks)
    client = AIClient(api_url="http://gateway/v1", default_model="model")
    client._client = fake

    result = [
        item
        async for item in client.chat_stream(
            ChatRequest(messages=[ChatMessage(role="user", content="hi")])
        )
    ]

    assert result == ["你", "好"]
    assert fake.chat.completions.calls[0]["stream"] is True


@pytest.mark.asyncio
async def test_embedding_uses_bifrost_openai_contract_and_preserves_order():
    response = SimpleNamespace(
        data=[SimpleNamespace(embedding=[1.0, 0.0]), SimpleNamespace(embedding=[0.0, 1.0])],
        model="text-embedding",
        usage=SimpleNamespace(prompt_tokens=4, total_tokens=4),
    )
    fake = _FakeOpenAI(embedding=response)
    client = EmbeddingClient(
        api_url="http://gateway/v1", model="text-embedding", dimensions=2
    )
    client._client = fake

    result = await client.embed_batch(["first", "", "second"])

    assert result is not None
    assert result.embeddings == [[1.0, 0.0], [0.0, 1.0]]
    assert fake.embeddings.calls[0] == {
        "model": "text-embedding",
        "input": ["first", "second"],
        "dimensions": 2,
    }
