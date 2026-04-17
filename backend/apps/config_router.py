"""配置管理 API"""

import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])

CONFIG_FILE = Path(__file__).parent.parent.parent / "config.yaml"


class EasyVtuberInputConfig(BaseModel):
    type: str = "debug"
    osf_address: str = "127.0.0.1:11573"
    mouse_range: str = "0,0,1920,1080"


class EasyVtuberModelConfig(BaseModel):
    version: str = "v3"
    precision: str = "half"
    separable: bool = True
    use_tensorrt: bool = True
    use_eyebrow: bool = True


class EasyVtuberPerformanceConfig(BaseModel):
    frame_rate: int = 30
    interpolation: str = "x2"
    super_resolution: str = "off"
    ram_cache: str = "2gb"
    vram_cache: str = "2gb"


class EasyVtuberWebSocketConfig(BaseModel):
    enabled: bool = True
    port: int = 8765
    host: str = "localhost"


class EasyVtuberOutputConfig(BaseModel):
    websocket: EasyVtuberWebSocketConfig = EasyVtuberWebSocketConfig()


class EasyVtuberConfig(BaseModel):
    enabled: bool = True
    character: str = "lambda_00"
    input: EasyVtuberInputConfig = EasyVtuberInputConfig()
    model: EasyVtuberModelConfig = EasyVtuberModelConfig()
    performance: EasyVtuberPerformanceConfig = EasyVtuberPerformanceConfig()
    output: EasyVtuberOutputConfig = EasyVtuberOutputConfig()


class HostConfig(BaseModel):
    room_id: int = 0
    reply_interval: int = 5
    max_reply_length: int = 100
    model: str = "doubao-seed-character-251128"
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 200
    disable_thinking: bool = True


class BilibiliConfig(BaseModel):
    room_id: int = 0
    sessdata: str = ""


class TTSConfig(BaseModel):
    voice: str = "zh-CN-XiaoxiaoNeural"


class FullConfig(BaseModel):
    bilibili: BilibiliConfig = BilibiliConfig()
    host: HostConfig = HostConfig()
    tts: TTSConfig = TTSConfig()
    easyvtuber: EasyVtuberConfig = EasyVtuberConfig()


@router.get("", response_model=FullConfig)
async def get_full_config():
    return FullConfig(
        bilibili=BilibiliConfig(
            room_id=config.bilibili_room_id,
        ),
        host=HostConfig(
            room_id=config.default_room_id,
            reply_interval=config.host_reply_interval,
            max_reply_length=config.host_max_reply_length,
            model=config.host_model,
            temperature=config.host_temperature,
            top_p=config.host_top_p,
            max_tokens=config.host_max_tokens,
            disable_thinking=config.llm_disable_thinking,
        ),
        tts=TTSConfig(voice=config.tts_voice),
        easyvtuber=EasyVtuberConfig(
            enabled=config.easyvtuber_enabled,
            character=config.easyvtuber_character,
            input=EasyVtuberInputConfig(
                type=config.easyvtuber_input_type,
                osf_address=config.easyvtuber_osf_address,
                mouse_range=config.easyvtuber_mouse_range,
            ),
            model=EasyVtuberModelConfig(
                version=config.easyvtuber_model_version,
                precision=config.easyvtuber_model_precision,
                separable=config.easyvtuber_model_separable,
                use_tensorrt=config.easyvtuber_use_tensorrt,
                use_eyebrow=config.easyvtuber_use_eyebrow,
            ),
            performance=EasyVtuberPerformanceConfig(
                frame_rate=config.easyvtuber_frame_rate,
                interpolation=config.easyvtuber_interpolation,
                super_resolution=config.easyvtuber_super_resolution,
                ram_cache=config.easyvtuber_ram_cache,
                vram_cache=config.easyvtuber_vram_cache,
            ),
            output=EasyVtuberOutputConfig(
                websocket=EasyVtuberWebSocketConfig(
                    enabled=config.easyvtuber_ws_enabled,
                    port=config.easyvtuber_ws_port,
                    host=config.easyvtuber_ws_host,
                )
            ),
        ),
    )


@router.put("", response_model=FullConfig)
async def update_full_config(config_data: FullConfig):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if config_data.bilibili:
            data["bilibili"] = config_data.bilibili.model_dump()
        data["host"] = config_data.host.model_dump()
        data["tts"] = config_data.tts.model_dump()
        data["easyvtuber"] = config_data.easyvtuber.model_dump()

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        config._load()

        return config_data

    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新配置失败: {e}")


@router.get("/easyvtuber", response_model=EasyVtuberConfig)
async def get_easyvtuber_config():
    return EasyVtuberConfig(
        enabled=config.easyvtuber_enabled,
        character=config.easyvtuber_character,
        input=EasyVtuberInputConfig(
            type=config.easyvtuber_input_type,
            osf_address=config.easyvtuber_osf_address,
            mouse_range=config.easyvtuber_mouse_range,
        ),
        model=EasyVtuberModelConfig(
            version=config.easyvtuber_model_version,
            precision=config.easyvtuber_model_precision,
            separable=config.easyvtuber_model_separable,
            use_tensorrt=config.easyvtuber_use_tensorrt,
            use_eyebrow=config.easyvtuber_use_eyebrow,
        ),
        performance=EasyVtuberPerformanceConfig(
            frame_rate=config.easyvtuber_frame_rate,
            interpolation=config.easyvtuber_interpolation,
            super_resolution=config.easyvtuber_super_resolution,
            ram_cache=config.easyvtuber_ram_cache,
            vram_cache=config.easyvtuber_vram_cache,
        ),
        output=EasyVtuberOutputConfig(
            websocket=EasyVtuberWebSocketConfig(
                enabled=config.easyvtuber_ws_enabled,
                port=config.easyvtuber_ws_port,
                host=config.easyvtuber_ws_host,
            )
        ),
    )


@router.put("/easyvtuber", response_model=EasyVtuberConfig)
async def update_easyvtuber_config(config_data: EasyVtuberConfig):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        data["easyvtuber"] = config_data.model_dump()

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        config._load()

        return config_data

    except Exception as e:
        logger.error(f"更新 EasyVtuber 配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新配置失败: {e}")


@router.get("/easyvtuber/characters")
async def list_characters():
    from pathlib import Path

    images_dir = Path(__file__).parent.parent.parent / "ai_vtuber" / "data" / "images"
    characters = []

    if images_dir.exists():
        for f in images_dir.glob("*.png"):
            characters.append({
                "name": f.stem,
                "path": str(f.relative_to(images_dir.parent.parent)),
            })

    return {"characters": characters}
