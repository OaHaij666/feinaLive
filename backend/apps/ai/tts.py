"""AI主播大脑 - TTS语音合成"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from apps.config import config

logger = logging.getLogger(__name__)


@dataclass
class TTSResult:
    audio_data: bytes
    text: str
    voice: str


class EdgeTTSClient:
    def __init__(self, voice: str | None = None):
        self.voice = voice or config.tts_voice

    async def synthesize(self, text: str) -> TTSResult | None:
        if not text.strip():
            return None
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, self.voice)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            if not audio_data:
                logger.warning("TTS生成音频为空")
                return None
            return TTSResult(audio_data=audio_data, text=text, voice=self.voice)
        except ImportError:
            logger.error("edge-tts未安装，请运行: pip install edge-tts")
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


_tts_client: EdgeTTSClient | None = None


def get_tts_client() -> EdgeTTSClient:
    global _tts_client
    if _tts_client is None:
        _tts_client = EdgeTTSClient()
    return _tts_client
