"""Provider-owned form schemas rendered safely by the control panel."""

PROVIDER_SCHEMAS = {
    "edge": {
        "type": "edge",
        "label": "Microsoft Edge TTS",
        "default_model": "edge-tts",
        "fields": [
            {
                "key": "default_voice",
                "label": "默认音色",
                "type": "text",
                "required": True,
                "default": "zh-CN-XiaoxiaoNeural",
                "placeholder": "zh-CN-XiaoxiaoNeural",
            },
        ],
    },
    "volcano": {
        "type": "volcano",
        "label": "火山引擎豆包语音 V3",
        "default_model": "seed-icl-2.0",
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "type": "secret",
                "required": True,
            },
            {
                "key": "default_voice",
                "label": "Speaker / 音色 ID",
                "type": "text",
                "required": True,
                "placeholder": "S_xxxxx 或官方音色 ID",
            },
            {
                "key": "resource_id",
                "label": "资源 ID",
                "type": "select",
                "required": True,
                "default": "seed-icl-2.0",
                "options": [
                    "seed-icl-2.0",
                    "seed-icl-1.0",
                    "seed-icl-1.0-concurr",
                    "seed-tts-2.0",
                    "seed-tts-1.0",
                    "seed-tts-1.0-concurr",
                ],
            },
            {
                "key": "sample_rate",
                "label": "采样率",
                "type": "select",
                "default": 24000,
                "options": [8000, 16000, 22050, 24000, 32000, 44100, 48000],
            },
        ],
    },
    "openai_compatible": {
        "type": "openai_compatible",
        "label": "OpenAI-compatible TTS",
        "default_model": "tts-1",
        "fields": [
            {
                "key": "base_url",
                "label": "Base URL",
                "type": "url",
                "required": True,
                "placeholder": "http://127.0.0.1:8000/v1",
            },
            {"key": "api_key", "label": "API Key", "type": "secret", "required": False},
            {"key": "default_voice", "label": "默认音色", "type": "text"},
            {
                "key": "formats",
                "label": "支持格式",
                "type": "multiselect",
                "options": ["mp3", "wav", "pcm", "ogg_opus"],
                "default": ["mp3"],
            },
            {"key": "health_path", "label": "健康检查路径", "type": "text", "default": "models"},
            {
                "key": "timeout_seconds",
                "label": "请求超时（秒）",
                "type": "number",
                "default": 60,
                "min": 1,
                "max": 300,
            },
            {"key": "voice_listing", "label": "支持音色列表", "type": "boolean", "default": False},
            {"key": "speed", "label": "支持语速", "type": "boolean", "default": True},
            {"key": "pitch", "label": "支持音高", "type": "boolean", "default": False},
            {"key": "emotion", "label": "支持情绪", "type": "boolean", "default": False},
            {"key": "word_timings", "label": "支持时间轴", "type": "boolean", "default": False},
        ],
    },
}


def schema_for(provider_type: str) -> dict:
    try:
        return PROVIDER_SCHEMAS[provider_type]
    except KeyError as exc:
        raise ValueError(f"Unknown provider type '{provider_type}'") from exc
