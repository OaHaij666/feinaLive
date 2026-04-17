"""AI主播大脑 - TTS语音合成

火山引擎 TTS (声音复刻)

同步方案:
- 按句子分块同步，每个句子单独合成
- 音频和文字一起发送，保证同步
"""

import asyncio
import logging
import re
import base64
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from apps.config import config

logger = logging.getLogger(__name__)


@dataclass
class TTSResult:
    audio_data: bytes
    text: str
    voice: str


@dataclass
class TTSSentenceResult:
    audio_data: bytes
    text: str
    sentence_index: int
    voice: str


class VolcanoTTSClient:
    """火山引擎 TTS 客户端 (声音复刻)"""

    SENTENCE_END_PATTERN = re.compile(r'[。！？.!?~\n]+')

    def __init__(
        self,
        appid: str | None = None,
        access_token: str | None = None,
        speaker_id: str | None = None,
        encoding: str | None = None,
        speed_ratio: float | None = None,
    ):
        self.appid = appid or config.volcano_appid
        self.access_token = access_token or config.volcano_access_token
        self.speaker_id = speaker_id or config.volcano_speaker_id
        self.encoding = encoding or config.tts_encoding
        self.speed_ratio = speed_ratio or config.tts_speed_ratio

    async def synthesize(self, text: str) -> TTSResult | None:
        if not text.strip():
            return None

        import aiohttp

        url = "https://openspeech.bytedance.com/api/v1/tts"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer;{self.access_token}",
        }
        payload = {
            "app": {
                "appid": self.appid,
                "token": "access_token",
                "cluster": "volcano_icl",
            },
            "user": {"uid": "tts_user"},
            "audio": {
                "voice_type": self.speaker_id,
                "encoding": self.encoding,
                "speed_ratio": self.speed_ratio,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "query",
                "with_frontend": 1,
                "frontend_type": "unitTson",
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60),
                    skip_auto_headers=["Accept-Encoding"],
                ) as resp:
                    if resp.status != 200:
                        text_content = await resp.text()
                        logger.error(f"TTS HTTP错误 {resp.status}: {text_content}")
                        return None

                    result = await resp.json()
                    audio_data = result.get("data")
                    if audio_data:
                        audio_bytes = base64.b64decode(audio_data)
                        return TTSResult(audio_data=audio_bytes, text=text, voice=self.speaker_id)
                    else:
                        logger.error(f"TTS未返回音频数据: {result.get('message', '未知错误')}")
                        return None

        except Exception as e:
            logger.error(f"TTS合成失败: {e}")
            return None

    async def synthesize_to_file(self, text: str, output_path: str | Path) -> Path | None:
        result = await self.synthesize(text)
        if not result:
            return None
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(result.audio_data)
        logger.info(f"TTS音频已保存: {output_path}")
        return output_path

    def split_sentences(self, text: str) -> list[str]:
        """按句子切分文本"""
        sentences = []
        current = ""
        for char in text:
            current += char
            if self.SENTENCE_END_PATTERN.match(char):
                if current.strip():
                    sentences.append(current.strip())
                current = ""
        if current.strip():
            sentences.append(current.strip())
        return sentences

    async def synthesize_stream_by_sentence(
        self, text: str
    ) -> AsyncIterator[TTSSentenceResult]:
        """按句子流式合成，每个句子返回一次

        这样可以实现文字和语音的同步：
        - 每个句子合成完成后立即返回
        - 前端收到音频和文字一起播放
        """
        sentences = self.split_sentences(text)

        for idx, sentence in enumerate(sentences):
            if not sentence.strip():
                continue

            result = await self.synthesize(sentence)
            if result:
                yield TTSSentenceResult(
                    audio_data=result.audio_data,
                    text=sentence,
                    sentence_index=idx,
                    voice=self.speaker_id,
                )


_tts_client: VolcanoTTSClient | None = None


def get_tts_client() -> VolcanoTTSClient:
    """获取 TTS 客户端单例"""
    global _tts_client
    if _tts_client is None:
        _tts_client = VolcanoTTSClient()
        logger.info(f"使用火山引擎 TTS, 音色: {config.volcano_speaker_id}")
    return _tts_client
