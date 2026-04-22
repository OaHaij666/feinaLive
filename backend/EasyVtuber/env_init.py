import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
venv_path = os.path.join(script_dir, '..', '.venv')
cudnn_bin = os.path.join(venv_path, 'Lib', 'site-packages', 'nvidia', 'cudnn', 'bin')
torch_lib = os.path.join(venv_path, 'Lib', 'site-packages', 'torch', 'lib')

os.environ['PATH'] = f'{cudnn_bin};{torch_lib};' + os.environ.get('PATH', '')

sys.path.insert(0, os.path.join(script_dir, 'ezvtuber-rt'))

import ezvtb_rt
ezvtb_rt.init_model_path(os.path.join(script_dir, 'data', 'models'))

from ezvtb_rt.core_ort import CoreORT

print('EZVTB RT initialized with CUDA support')
print('PYTHONPATH:', sys.path[:3])
