import os
os.environ['PATH'] = r'c:\my_code\feinaLive\backend\.venv\Lib\site-packages\nvidia\cudnn\bin;c:\my_code\feinaLive\backend\.venv\Lib\site-packages\torch\lib;' + os.environ['PATH']

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ezvtuber-rt'))

import ezvtb_rt
ezvtb_rt.init_model_path(os.path.join(os.path.dirname(__file__), 'data', 'models'))

import time
import numpy as np
from ezvtb_rt.core_ort import CoreORT

print("Initializing model...")
core = CoreORT(
    tha_model_version='v3',
    tha_model_seperable=True,
    tha_model_fp16=False,
    tha_model_name='',
    rife_model_enable=False,
    sr_model_enable=False,
    vram_cache_size=1.0,
    cache_max_giga=2.0,
    use_eyebrow=False,
)

print("\nTesting inference...")
img = np.random.randint(0, 255, (512, 512, 4), dtype=np.uint8)
poses = np.random.rand(1, 45).astype(np.float32) * 0.1  # 12 + 27 + 6

core.setImage(img)

start = time.time()
for i in range(10):
    result = core.inference([poses])
elapsed = time.time() - start

print(f"\nResults:")
print(f"  Output shape: {result.shape}")
print(f"  10 inferences in {elapsed:.2f}s")
print(f"  FPS: {10/elapsed:.2f}")
