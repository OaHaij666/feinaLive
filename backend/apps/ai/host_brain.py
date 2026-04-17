"""AI主播大脑 - 基于 LangGraph 的对话流程

支持两种回复模式:
1. 完整回复 - 等待LLM完成后一次性返回
2. 流式同步回复 - 按句子同步发送文字和音频

记忆架构:
- 短期记忆: SessionHistory (当前会话, 50条)
- 中期记忆: UserProfile (用户画像 + 近期对话)
- 长期记忆: RAG (全局知识库)
- 定期摘要: LLM 生成印象 + 长期记忆
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Generator, Optional, TypedDict

from apps.ai.admin_commands import (
    AdminCommandHandler,
    CommandResult,
    FaceMode,
    get_admin_handler,
)
from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.ai.history import SessionHistory, get_session
from apps.ai.memory import (
    UserProfile,
    get_user_profile,
    trigger_summary_if_needed,
)
from apps.ai.prompt import build_chat_prompt, get_host_system_prompt
from apps.ai.tts import (
    TTSResult,
    VolcanoTTSClient,
    get_tts_client,
)
from apps.config import config
from apps.easyvtuber import get_easyvtuber_manager
from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


class DanmakuInput:
    def __init__(self, msg_id: str = "", user: str = "", content: str = "", timestamp: float = 0, uid: int = 0):
        self.msg_id = msg_id
        self.user = user
        self.content = content
        self.timestamp = timestamp or time.time()
        self.uid = uid

    def to_dict(self) -> dict:
        return {
            "msg_id": self.msg_id,
            "user": self.user,
            "content": self.content,
            "timestamp": self.timestamp,
            "uid": self.uid,
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


@dataclass
class StreamReplyChunk:
    type: str
    text: str = ""
    audio_data: bytes | None = None
    sentence_index: int = 0
    char_offset: int = 0
    is_final: bool = False

    def to_dict(self) -> dict:
        result = {"type": self.type, "is_final": self.is_final}
        if self.text:
            result["text"] = self.text
        if self.audio_data:
            import base64
            result["audio"] = base64.b64encode(self.audio_data).decode("utf-8")
            result["sentence_index"] = self.sentence_index
            result["char_offset"] = self.char_offset
            result["char_length"] = len(self.text)
        return result


class ChatState(TypedDict):
    text: str
    msg_id: str
    user: str
    session_id: str
    rag_context: list[str]
    user_memory_context: str
    prompt: str
    llm_stream: Optional[Generator]
    response: str
    audio_data: Optional[bytes]


async def retrieve_rag(state: ChatState) -> ChatState:
    retriever = RagRetrieverSimple()
    state["rag_context"] = retriever.retrieve(state["text"], top_k=3)
    return state


async def retrieve_user_memory(state: ChatState) -> ChatState:
    user = state["user"]
    user_profile = get_user_profile(user)
    
    state["user_memory_context"] = user_profile.get_memory_context()
    logger.debug(f"用户 {user} 记忆上下文: {state['user_memory_context'][:100] if state['user_memory_context'] else '(无)'}...")
    return state


async def build_prompt(state: ChatState) -> ChatState:
    history = get_session(state["session_id"])
    history_entries = history.get_recent_dicts(10)
    system_prompt = get_host_system_prompt()
    
    if state.get("rag_context"):
        rag_text = "\n".join(state["rag_context"])
        system_prompt += f"\n\n【相关知识】\n{rag_text}"
    
    if state.get("user_memory_context"):
        system_prompt += f"\n\n{state['user_memory_context']}"

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


async def update_user_memory(state: ChatState) -> ChatState:
    user = state["user"]
    content = state["text"]
    response = state["response"]
    
    if not response:
        return state
    
    user_profile = get_user_profile(user)
    user_profile.add_conversation(content, response)
    
    trigger_summary_if_needed(user_profile)
    
    logger.debug(f"用户 {user} 记忆已更新 (互动次数: {user_profile.interaction_count})")
    return state


class RagRetrieverSimple:
    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        return []


def create_chat_graph():
    graph = StateGraph(ChatState)

    graph.add_node("retrieve_rag", retrieve_rag)
    graph.add_node("retrieve_user_memory", retrieve_user_memory)
    graph.add_node("build_prompt", build_prompt)
    graph.add_node("stream_llm", stream_llm)
    graph.add_node("stream_tts", stream_tts)
    graph.add_node("save_history", save_history)
    graph.add_node("update_user_memory", update_user_memory)

    graph.set_entry_point("retrieve_rag")
    graph.add_edge("retrieve_rag", "retrieve_user_memory")
    graph.add_edge("retrieve_user_memory", "build_prompt")
    graph.add_edge("build_prompt", "stream_llm")
    graph.add_edge("stream_llm", "stream_tts")
    graph.add_edge("stream_tts", "save_history")
    graph.add_edge("save_history", "update_user_memory")
    graph.add_edge("update_user_memory", END)

    return graph.compile()


chat_graph = create_chat_graph()


class SentenceBuffer:
    """句子缓冲区，用于流式输出时按句子切分"""

    SENTENCE_END_PATTERN = re.compile(r'[。！？.!?~]+')

    def __init__(self):
        self.buffer = ""
        self.sentences: list[str] = []

    def add(self, text: str) -> list[str]:
        """添加文本，返回完整的句子"""
        self.buffer += text
        sentences = []

        while True:
            match = self.SENTENCE_END_PATTERN.search(self.buffer)
            if not match:
                break

            end_pos = match.end()
            sentence = self.buffer[:end_pos].strip()
            if sentence:
                sentences.append(sentence)
                self.sentences.append(sentence)
            self.buffer = self.buffer[end_pos:]

        return sentences

    def flush(self) -> str:
        """返回剩余的文本"""
        remaining = self.buffer.strip()
        self.buffer = ""
        if remaining:
            self.sentences.append(remaining)
        return remaining


class AIHostBrain:
    def __init__(self, room_id: int | str):
        self.room_id = str(room_id)
        self._danmaku_buffer: list[DanmakuInput] = []
        self._last_reply_time: float = 0
        self._is_replying: bool = False
        self._on_reply_callback = None
        self._on_stream_callback = None
        self._admin_handler = get_admin_handler()
        self._admin_result_callback: Optional[Callable[[CommandResult], None]] = None

    def set_on_reply(self, callback):
        self._on_reply_callback = callback

    def set_on_stream(self, callback):
        self._on_stream_callback = callback

    def set_on_admin_command_result(self, callback: Callable[[CommandResult], None]):
        self._admin_result_callback = callback

    def push_danmaku(self, msg_id: str, user: str, content: str, uid: int = 0) -> bool:
        if content.strip() == "/clear":
            from apps.ai.memory import clear_user_profile
            clear_user_profile(user)
            logger.info(f"用户 {user} 清除了自己的记忆")
            return False

        cmd_result = self._admin_handler.sync_handle(uid, user, content)
        if cmd_result:
            logger.info(f"Admin command executed: {cmd_result.message}")
            if self._admin_result_callback:
                self._admin_result_callback(cmd_result)
            return False

        if not self._admin_handler.should_process_danmaku(uid, user):
            logger.debug(f"弹幕被过滤 (sleep模式): [{user}] {content}")
            return False

        danmaku = DanmakuInput(msg_id=msg_id, user=user, content=content, uid=uid)
        self._danmaku_buffer.append(danmaku)
        if len(self._danmaku_buffer) > 20:
            self._danmaku_buffer = self._danmaku_buffer[-20:]
        logger.debug(f"弹幕入缓冲: [{user}] {content}")
        return True

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

        if self._admin_handler.get_state().is_sleeping:
            return None

        elapsed = time.time() - self._last_reply_time
        if elapsed < config.host_reply_interval:
            return None

        unanswered = [
            d for d in self.get_unanswered()
            if self._admin_handler.should_process_danmaku(d.uid, d.user)
        ]
        if not unanswered:
            return None

        self._is_replying = True
        try:
            return await self._generate_reply(unanswered)
        finally:
            self._is_replying = False
            self._last_reply_time = time.time()

    async def _generate_reply(self, unanswered: list[DanmakuInput]) -> HostReply | None:
        if not unanswered:
            return None

        first = unanswered[0]
        user = first.user
        combined_contents = [first.content]
        combined_msg_ids = [first.msg_id]

        for d in unanswered[1:]:
            if d.user == user:
                combined_contents.append(d.content)
                combined_msg_ids.append(d.msg_id)
            else:
                break

        combined_text = "\n".join(combined_contents)
        history = get_session(self.room_id)
        history.mark_answered_batch(combined_msg_ids)

        state: ChatState = {
            "text": combined_text,
            "msg_id": first.msg_id,
            "user": user,
            "session_id": self.room_id,
            "rag_context": [],
            "user_memory_context": "",
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
            source_danmaku=first,
        )

        if self._on_reply_callback:
            await self._on_reply_callback(reply)

        logger.info(f"AI主播回复 [{user}]: {full_response}")
        return reply

    async def stream_reply(self, user: str, content: str) -> AsyncIterator[StreamReplyChunk]:
        """流式同步回复 - 按句子同步发送文字和音频

        流程:
        1. LLM 流式输出文字
        2. 按句子切分
        3. 每个句子单独调用 TTS
        4. 返回音频时同时发送对应的文字
        """
        if self._is_replying:
            yield StreamReplyChunk(type="error", text="正在回复中，请稍候")
            return

        self._is_replying = True
        try:
            async for chunk in self._stream_reply_impl(user, content):
                yield chunk
        finally:
            self._is_replying = False
            self._last_reply_time = time.time()

    async def _stream_reply_impl(
        self, user: str, content: str
    ) -> AsyncIterator[StreamReplyChunk]:
        ai = get_ai_client()
        if not ai.available:
            yield StreamReplyChunk(type="error", text="AI配置不完整")
            return

        history = get_session(self.room_id)
        msg_id = f"stream_{int(time.time() * 1000)}"

        history.add_user_message(content=content, sender=user, msg_id=msg_id)

        user_profile = get_user_profile(user)
        user_memory_context = user_profile.get_memory_context()
        
        history_entries = history.get_recent_dicts(10)
        system_prompt = get_host_system_prompt()
        
        if user_memory_context:
            system_prompt += f"\n\n{user_memory_context}"
        
        prompt = build_chat_prompt(
            user_text=content,
            history_entries=history_entries,
            system_prompt=system_prompt,
        )

        messages = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in prompt
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

        sentence_buffer = SentenceBuffer()
        full_response = ""
        sentence_index = 0
        char_offset = 0
        sentence_offsets: list[tuple[int, str]] = []

        tts = get_tts_client()
        tts_tasks: list[asyncio.Task] = []

        async def process_sentence(sentence: str, idx: int, offset: int):
            """处理单个句子的 TTS"""
            result = await tts.synthesize(sentence)
            if result:
                return StreamReplyChunk(
                    type="audio",
                    text=sentence,
                    audio_data=result.audio_data,
                    sentence_index=idx,
                    char_offset=offset,
                )
            return None

        yield StreamReplyChunk(type="start")

        try:
            manager = get_easyvtuber_manager()
            manager.set_speaking(True)
        except Exception as e:
            logger.warning(f"设置 speaking 状态失败: {e}")

        async for chunk in ai.chat_stream(request):
            full_response += chunk

            new_sentences = sentence_buffer.add(chunk)
            for sentence in new_sentences:
                sentence_offsets.append((char_offset, sentence))
                yield StreamReplyChunk(type="text", text=sentence)

                task = asyncio.create_task(
                    process_sentence(sentence, sentence_index, char_offset)
                )
                tts_tasks.append(task)
                sentence_index += 1

                char_offset += len(sentence)

        remaining = sentence_buffer.flush()
        if remaining:
            sentence_offsets.append((char_offset, remaining))
            yield StreamReplyChunk(type="text", text=remaining)

            task = asyncio.create_task(
                process_sentence(remaining, sentence_index, char_offset)
            )
            tts_tasks.append(task)

        for completed in asyncio.as_completed(tts_tasks):
            result = await completed
            if result:
                yield result

        history.add_assistant_message(full_response)

        user_profile.add_conversation(content, full_response)
        
        trigger_summary_if_needed(user_profile)

        if len(full_response) > config.host_max_reply_length:
            full_response = full_response[:config.host_max_reply_length]

        yield StreamReplyChunk(type="end", text=full_response, is_final=True)

        try:
            manager = get_easyvtuber_manager()
            manager.set_speaking(False)
        except Exception as e:
            logger.warning(f"设置 speaking 状态失败: {e}")

        logger.info(f"AI主播流式回复 [{user}]: {full_response}")

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
