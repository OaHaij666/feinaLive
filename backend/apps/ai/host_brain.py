"""AI主播大脑 - 基于 LangGraph 的对话流程"""

import logging
import time
from dataclasses import dataclass, field
from typing import Generator, Optional, TypedDict

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.ai.history import SessionHistory, get_session
from apps.ai.prompt import build_chat_prompt, get_host_system_prompt
from apps.ai.tts import EdgeTTSClient, TTSResult, get_tts_client
from apps.config import config
from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


class DanmakuInput:
    def __init__(self, msg_id: str = "", user: str = "", content: str = "", timestamp: float = 0):
        self.msg_id = msg_id
        self.user = user
        self.content = content
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> dict:
        return {
            "msg_id": self.msg_id,
            "user": self.user,
            "content": self.content,
            "timestamp": self.timestamp,
        }


@dataclass
class HostReply:
    text: str
    audio: TTSResult | None = None
    source_danmaku: DanmakuInput | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "has_audio": self.audio is not None,
            "source_user": self.source_danmaku.user if self.source_danmaku else None,
        }


class ChatState(TypedDict):
    text: str
    msg_id: str
    user: str
    session_id: str
    rag_context: list[str]
    prompt: str
    llm_stream: Optional[Generator]
    response: str
    audio_data: Optional[bytes]


async def retrieve_rag(state: ChatState) -> ChatState:
    retriever = RagRetrieverSimple()
    state["rag_context"] = retriever.retrieve(state["text"], top_k=3)
    return state


async def build_prompt(state: ChatState) -> ChatState:
    history = get_session(state["session_id"])
    history_entries = history.get_recent_dicts(10)
    system_prompt = get_host_system_prompt()

    state["prompt"] = build_chat_prompt(
        user_text=state["text"],
        history_entries=history_entries,
        system_prompt=system_prompt,
    )
    return state


async def stream_llm(state: ChatState) -> ChatState:
    ai = get_ai_client()
    if not ai.available:
        logger.warning("AI配置不完整")
        state["llm_stream"] = None
        return state

    messages = [
        ChatMessage(role=m["role"], content=m["content"])
        for m in state["prompt"]
    ]
    request = ChatRequest(
        messages=messages,
        model=config.host_model,
        temperature=config.host_temperature,
        top_p=config.host_top_p,
        max_tokens=config.host_max_tokens,
        disable_thinking=config.llm_disable_thinking,
        stream=True,
    )

    chunks = []
    async for chunk in ai.chat_stream(request):
        chunks.append(chunk)

    state["llm_stream"] = chunks
    state["response"] = "".join(chunks)
    return state


async def stream_tts(state: ChatState) -> ChatState:
    if not state["response"]:
        state["audio_data"] = None
        return state

    tts = get_tts_client()
    result = await tts.synthesize(state["response"])
    state["audio_data"] = result.audio_data if result else None
    return state


async def save_history(state: ChatState) -> ChatState:
    history = get_session(state["session_id"])
    history.add_user_message(
        content=state["text"],
        sender=state["user"],
        msg_id=state["msg_id"],
    )
    if state["response"]:
        history.add_assistant_message(state["response"])
    return state


class RagRetrieverSimple:
    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        return []


def create_chat_graph():
    graph = StateGraph(ChatState)

    graph.add_node("retrieve_rag", retrieve_rag)
    graph.add_node("build_prompt", build_prompt)
    graph.add_node("stream_llm", stream_llm)
    graph.add_node("stream_tts", stream_tts)
    graph.add_node("save_history", save_history)

    graph.set_entry_point("retrieve_rag")
    graph.add_edge("retrieve_rag", "build_prompt")
    graph.add_edge("build_prompt", "stream_llm")
    graph.add_edge("stream_llm", "stream_tts")
    graph.add_edge("stream_tts", "save_history")
    graph.add_edge("save_history", END)

    return graph.compile()


chat_graph = create_chat_graph()


class AIHostBrain:
    def __init__(self, room_id: int | str):
        self.room_id = str(room_id)
        self._danmaku_buffer: list[DanmakuInput] = []
        self._last_reply_time: float = 0
        self._is_replying: bool = False
        self._on_reply_callback = None

    def set_on_reply(self, callback):
        self._on_reply_callback = callback

    def push_danmaku(self, msg_id: str, user: str, content: str):
        danmaku = DanmakuInput(msg_id=msg_id, user=user, content=content)
        self._danmaku_buffer.append(danmaku)
        if len(self._danmaku_buffer) > 20:
            self._danmaku_buffer = self._danmaku_buffer[-20:]
        logger.debug(f"弹幕入缓冲: [{user}] {content}")

    def get_unanswered(self) -> list[DanmakuInput]:
        history = get_session(self.room_id)
        unanswered = []
        for d in self._danmaku_buffer:
            if not history.is_answered(d.msg_id):
                unanswered.append(d)
        return unanswered

    async def try_reply(self) -> HostReply | None:
        if self._is_replying:
            return None

        elapsed = time.time() - self._last_reply_time
        if elapsed < config.host_reply_interval:
            return None

        unanswered = self.get_unanswered()
        if not unanswered:
            return None

        self._is_replying = True
        try:
            return await self._generate_reply(unanswered)
        finally:
            self._is_replying = False
            self._last_reply_time = time.time()

    async def _generate_reply(self, unanswered: list[DanmakuInput]) -> HostReply | None:
        target = unanswered[-1]
        history = get_session(self.room_id)

        history.add_user_message(
            content=target.content,
            sender=target.user,
            msg_id=target.msg_id,
        )

        for d in unanswered[:-1]:
            if not history.is_answered(d.msg_id):
                history.add_user_message(
                    content=d.content,
                    sender=d.user,
                    msg_id=d.msg_id,
                )

        state: ChatState = {
            "text": target.content,
            "msg_id": target.msg_id,
            "user": target.user,
            "session_id": self.room_id,
            "rag_context": [],
            "prompt": [],
            "llm_stream": None,
            "response": "",
            "audio_data": None,
        }

        full_response = ""
        async for chunk_result in chat_graph.astream(state):
            if "stream_llm" in chunk_result:
                full_response = chunk_result["stream_llm"].get("response", "")

        if not full_response:
            logger.warning("AI主播回复为空")
            return None

        if len(full_response) > config.host_max_reply_length:
            full_response = full_response[:config.host_max_reply_length]

        tts = get_tts_client()
        audio_result = await tts.synthesize(full_response)

        reply = HostReply(
            text=full_response,
            audio=audio_result,
            source_danmaku=target,
        )

        if self._on_reply_callback:
            await self._on_reply_callback(reply)

        logger.info(f"AI主播回复 [{target.user}]: {full_response}")
        return reply

    async def reply_to_text(self, user: str, content: str) -> HostReply | None:
        msg_id = f"manual_{int(time.time() * 1000)}"
        self.push_danmaku(msg_id=msg_id, user=user, content=content)
        return await self.try_reply()

    def clear_buffer(self):
        self._danmaku_buffer.clear()

    @property
    def is_replying(self) -> bool:
        return self._is_replying

    @property
    def buffer_size(self) -> int:
        return len(self._danmaku_buffer)

    @property
    def unanswered_count(self) -> int:
        return len(self.get_unanswered())


_brains: dict[str, AIHostBrain] = {}


def get_host_brain(room_id: int | str) -> AIHostBrain:
    key = str(room_id)
    if key not in _brains:
        _brains[key] = AIHostBrain(room_id)
    return _brains[key]
