import os
import sys
import subprocess

script_dir = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(script_dir, '..', '.venv', 'Scripts', 'python.exe')

env = os.environ.copy()
env['PATH'] = rf'{script_dir}\.venv\Lib\site-packages\nvidia\cudnn\bin;{script_dir}\.venv\Lib\site-packages\torch\lib;' + env.get('PATH', '')

cmd = [venv_python, '-m', 'src.main'] + sys.argv[1:]
result = subprocess.run(cmd, env=env, cwd=script_dir)
sys.exit(result.returncode)
