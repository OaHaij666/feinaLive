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
        "label": "火山引擎 TTS",
        "default_model": "voice-clone",
        "fields": [
            {"key": "appid", "label": "App ID", "type": "text", "required": True},
            {
                "key": "access_token",
                "label": "Access Token",
                "type": "secret",
                "required": True,
            },
            {
                "key": "default_voice",
                "label": "Speaker ID",
                "type": "text",
                "required": True,
            },
            {
                "key": "cluster",
                "label": "Cluster",
                "type": "text",
                "default": "volcano_icl",
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
