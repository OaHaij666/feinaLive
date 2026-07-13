from __future__ import annotations

import sys
from pathlib import Path

from .args import args

SOURCE_DIR = Path(__file__).resolve().parent
VENDOR_DIR = SOURCE_DIR.parents[1] / "vendor" / "ezvtuber_rt"
if str(VENDOR_DIR) not in sys.path:
    sys.path.append(str(VENDOR_DIR))

import ezvtb_rt  # noqa: E402

ezvtb_rt.init_model_path(str(SOURCE_DIR.parent / "data" / "models"))


def get_core(
    use_tensorrt: bool = True,
    model_version: str = "v3",
    model_name: str = "",
    model_seperable: bool = True,
    model_half: bool = True,
    model_cache_size: float = 1.0,
    model_use_eyebrow: bool = True,
    use_interpolation: bool = True,
    interpolation_scale: int = 2,
    interpolation_half: bool = True,
    cacher_ram_size: float = 2.0,
    use_sr: bool = False,
    sr_x4: bool = True,
    sr_half: bool = True,
    sr_a4k: bool = False,
):
    if use_tensorrt:
        try:
            from ezvtb_rt.core_trt import CoreTRT as Core
        except ImportError:
            args.use_tensorrt = False
            from ezvtb_rt.core_ort import CoreORT as Core
    else:
        from ezvtb_rt.core_ort import CoreORT as Core
    return Core(
        tha_model_version=model_version,
        tha_model_seperable=model_seperable,
        tha_model_fp16=model_half,
        tha_model_name=model_name,
        rife_model_enable=use_interpolation,
        rife_model_scale=interpolation_scale,
        rife_model_fp16=interpolation_half,
        sr_model_enable=use_sr,
        sr_model_scale=4 if sr_x4 else 2,
        sr_model_fp16=sr_half,
        sr_a4k=sr_a4k,
        vram_cache_size=model_cache_size,
        cache_max_giga=cacher_ram_size,
        use_eyebrow=model_use_eyebrow,
    )
