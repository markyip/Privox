"""Optional dev check: Torch CUDA + llama-cpp-python import (run from pixi env)."""
import inspect
import os
import sys

import torch

print(f"Python: {sys.version}")
print(f"Torch: {torch.__version__}")
print(f"CUDA Available (Torch): {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"Device: {torch.cuda.get_device_name(0)}")

try:
    from llama_cpp import Llama

    print("llama-cpp-python imported successfully.")
    print(f"Llama location: {os.path.dirname(inspect.getfile(Llama))}")
except ImportError:
    print("llama-cpp-python NOT installed.")
except Exception as e:
    print(f"llama-cpp-python error: {e}")
