"""测试 AI 主播完整流程

测试流程:
1. 弹幕输入 -> LLM 流式输出
2. LLM 文字 -> TTS 音频
3. 同步返回文字和音频

运行方式:
    cd backend
    uv run python tests/test_ai_flow.py
"""

import asyncio
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.ai.host_brain import get_host_brain, StreamReplyChunk
from apps.config import config


async def test_stream_reply():
    """测试流式回复"""
    print("=" * 60)
    print("测试 AI 主播流式回复")
    print("=" * 60)
    print()

    brain = get_host_brain(config.default_room_id or 0)

    user = "测试用户"
    content = "你好，请用一句话介绍一下自己"

    print(f"[输入] 用户: {user}")
    print(f"[输入] 内容: {content}")
    print()
    print("-" * 60)
    print("[开始流式输出]")
    print("-" * 60)

    full_text = ""
    audio_chunks = 0

    async for chunk in brain.stream_reply(user, content):
        chunk_type = chunk.type

        if chunk_type == "start":
            print("\n[START] 开始生成回复...")

        elif chunk_type == "text":
            safe_text = chunk.text.encode('utf-8', errors='replace').decode('utf-8')
            print(f"[TEXT] {safe_text}")
            full_text += chunk.text

        elif chunk_type == "audio":
            audio_size = len(chunk.audio_data) if chunk.audio_data else 0
            text_preview = chunk.text[:20] if len(chunk.text) > 20 else chunk.text
            safe_text = text_preview.encode('utf-8', errors='replace').decode('utf-8')
            print(f"[AUDIO] 句子 {chunk.sentence_index}: {safe_text}... ({audio_size} bytes)")
            audio_chunks += 1

        elif chunk_type == "end":
            print(f"\n[END] 完成")
            safe_text = chunk.text.encode('utf-8', errors='replace').decode('utf-8')
            print(f"[完整回复] {safe_text}")

        elif chunk_type == "error":
            print(f"[ERROR] {chunk.text}")

    print()
    print("-" * 60)
    print("[统计]")
    print(f"  文字长度: {len(full_text)} 字符")
    print(f"  音频片段: {audio_chunks} 个")
    print("-" * 60)


async def test_tts_only():
    """单独测试 TTS"""
    print()
    print("=" * 60)
    print("测试 TTS 合成")
    print("=" * 60)
    print()

    from apps.ai.tts import get_tts_client

    tts = get_tts_client()
    text = "你好，这是一个测试。"

    print(f"[输入] {text}")
    print("[合成中...]")

    result = await tts.synthesize(text)

    if result:
        print(f"[成功] 音频大小: {len(result.audio_data)} bytes")
        print(f"[成功] 格式: {result.format}")
    else:
        print("[失败] TTS 合成返回空")


async def test_llm_only():
    """单独测试 LLM"""
    print()
    print("=" * 60)
    print("测试 LLM 流式输出")
    print("=" * 60)
    print()

    from apps.ai.client import get_ai_client, ChatRequest, ChatMessage

    ai = get_ai_client()

    if not ai.available:
        print("[跳过] LLM 未配置")
        return

    messages = [
        ChatMessage(role="system", content="你是一个友好的AI助手。"),
        ChatMessage(role="user", content="说一句话"),
    ]

    request = ChatRequest(
        messages=messages,
        model=config.host_model,
        temperature=0.7,
        max_tokens=50,
        stream=True,
    )

    print("[开始流式输出]")
    full_text = ""
    async for chunk in ai.chat_stream(request):
        safe_chunk = chunk.encode('utf-8', errors='replace').decode('utf-8')
        print(safe_chunk, end="", flush=True)
        full_text += chunk

    print()
    print(f"\n[完成] 共 {len(full_text)} 字符")


async def main():
    print("\n" + "=" * 60)
    print("  AI 主播流程测试")
    print("=" * 60)

    print("\n配置信息:")
    print(f"  LLM API: {config.llm_api_url[:30]}..." if config.llm_api_url else "  LLM API: 未配置")
    print(f"  LLM Model: {config.llm_model}")
    print(f"  TTS Provider: {config.tts_provider}")
    print(f"  TTS Voice: {config.tts_voice}")
    print(f"  Volcano Speaker: {config.volcano_speaker_id}")

    print("\n选择测试:")
    print("  1. 完整流程测试 (弹幕 -> LLM -> TTS)")
    print("  2. 仅测试 LLM")
    print("  3. 仅测试 TTS")
    print("  4. 全部测试")

    choice = input("\n请输入选项 (1-4): ").strip()

    if choice == "1":
        await test_stream_reply()
    elif choice == "2":
        await test_llm_only()
    elif choice == "3":
        await test_tts_only()
    elif choice == "4":
        await test_llm_only()
        await test_tts_only()
        await test_stream_reply()
    else:
        print("无效选项，执行完整流程测试")
        await test_stream_reply()

    print("\n测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
