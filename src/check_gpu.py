import sys
import os
import torch

print(f"Python: {sys.version}")
print(f"Torch: {torch.__version__}")
print(f"CUDA Available (Torch): {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"Device: {torch.cuda.get_device_name(0)}")

try:
    from llama_cpp import Llama
    print("llama-cpp-python imported successfully.")
    # Attempt to load a dummy model or check build info if possible
    # There isn't a direct "is_cuda_built" flag exposed easily, but we can check __file__ or try to load with n_gpu_layers
    import inspect
    print(f"Llama location: {os.path.dirname(inspect.getfile(Llama))}")
except ImportError:
    print("llama-cpp-python NOT installed.")
except Exception as e:
    print(f"llama-cpp-python error: {e}")
