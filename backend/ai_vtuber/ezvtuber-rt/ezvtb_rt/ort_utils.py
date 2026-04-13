import os
from datetime import datetime
import onnxruntime as ort


def _ts():
    return datetime.now().strftime('[%m/%d/%Y-%H:%M:%S]')


def createORTSession(model_path: str, device_id: int = 0):
    """创建 ONNX Runtime 推理会话。会输出加载流程和当前模型文件名。"""
    filename = os.path.basename(model_path)
    print(f'{_ts()} [ORT] Loading ONNX model from path {model_path}...')
    
    # Try CUDA first, fallback to CPU
    available_providers = ort.get_available_providers()
    if 'CUDAExecutionProvider' in available_providers:
        try:
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            options = ort.SessionOptions()
            options.enable_mem_pattern = True
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            options.enable_cpu_mem_arena = True
            provider_options = [{'device_id': device_id}, {}]
            session = ort.InferenceSession(model_path, sess_options=options, providers=providers, provider_options=provider_options)
            print(f'{_ts()} [ORT] Completed loading session: {filename} (CUDA)')
            return session
        except Exception as e:
            print(f'{_ts()} [ORT] CUDA failed, falling back to CPU: {e}')
    
    # CPU fallback
    providers = ['CPUExecutionProvider']
    options = ort.SessionOptions()
    options.enable_mem_pattern = True
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.enable_cpu_mem_arena = True
    session = ort.InferenceSession(model_path, sess_options=options, providers=providers)
    print(f'{_ts()} [ORT] Completed loading session: {filename} (CPU)')
    return session