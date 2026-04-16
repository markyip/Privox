"""
Runtime toggles shared by voice_input: optional PyTorch-free mode (PRIVOX_NO_TORCH=1).

When NO_TORCH is active:
- No `import torch` (ASR: faster-whisper / CTranslate2 or Qwen3-ASR ONNX; PyTorch Qwen/SenseVoice disabled).
- GPU presence for refiner/offload uses ctranslate2 or llama backend, not torch.cuda.
"""
from __future__ import annotations

import os

NO_TORCH: bool = (os.environ.get("PRIVOX_NO_TORCH") or "").strip().lower() in ("1", "true", "yes", "on")

_torch_module = None


def get_torch():
    """Return torch module, or None when PRIVOX_NO_TORCH is set."""
    global _torch_module
    if NO_TORCH:
        return None
    if _torch_module is None:
        import torch as _t

        _t.set_num_threads(2)
        _torch_module = _t
    return _torch_module


def cuda_is_available() -> bool:
    """Non-invasive CUDA check to avoid triggering DLL context conflicts early."""
    if not NO_TORCH:
        t = get_torch()
        if t is not None:
            try: return bool(t.cuda.is_available())
            except Exception: pass
    
    # Check for NVIDIA driver / nvidia-smi as a passive heuristic
    # This avoids importing llama_cpp or ctranslate2 at the top-level
    import shutil
    if shutil.which("nvidia-smi"):
        return True
        
    # On Windows, we can also check for nvrtc64_*.dll or cublas64_*.dll presence 
    # but nvidia-smi is usually the best indicator of a functional driver.
    return False


def cuda_device_name(index: int = 0) -> str:
    if not NO_TORCH:
        t = get_torch()
        if t is not None and t.cuda.is_available():
            try:
                return str(t.cuda.get_device_name(index))
            except Exception:
                pass
    return "CUDA (no PyTorch)" if cuda_is_available() else "CPU"


def cuda_device_total_memory_gib(index: int = 0) -> float:
    """VRAM for layer planning; without PyTorch uses nvidia-smi or env override."""
    if not NO_TORCH:
        t = get_torch()
        if t is not None and t.cuda.is_available():
            try:
                return float(t.cuda.get_device_properties(index).total_memory) / (1024 ** 3)
            except Exception:
                pass
    env = (os.environ.get("PRIVOX_GPU_MEM_GIB") or "").strip()
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    try:
        import subprocess

        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            lines = [x.strip() for x in r.stdout.strip().splitlines() if x.strip()]
            if 0 <= index < len(lines):
                return float(lines[index]) / 1024.0
    except Exception:
        pass
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return 12.0
    except Exception:
        pass
def pre_load_cuda_dlls() -> bool:
    """Explicitly load critical CUDA DLLs to prevent native crashes in ONNX/CT2 on Windows."""
    import sys
    if sys.platform != "win32":
        return True
    
    import ctypes
    import os
    from pathlib import Path
    
    # Search order: Pixi env, then system PATH
    def get_root():
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent
        # src/privox_runtime.py -> src -> root
        return Path(os.path.abspath(__file__)).parent.parent
        
    root = get_root()
    search_dirs = [
        root / ".pixi" / "envs" / "default" / "bin",
        root / ".pixi" / "envs" / "default" / "Library" / "bin",
        root / "bin",
    ]
    
    # Critical DLLs for ONNX 1.24 (CUDA 12.x + cuDNN 9)
    # Search for exactly what's in the environment
    dlls_to_load = [
        "cudart64_12.dll",
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "cudnn64_9.dll",
    ]
    
    print(f"--- CUDA Pre-load Discovery (Root: {root}) ---")
    loaded_libs = []
    for dll_name in dlls_to_load:
        success = False
        # 1. Try absolute paths in our environment
        for d in search_dirs:
            p = d / dll_name
            if p.exists():
                try:
                    ctypes.CDLL(str(p))
                    print(f"Loaded {dll_name} from {d}")
                    success = True
                    break
                except Exception as e:
                    print(f"Found {dll_name} at {p} but failed to load: {e}")
        
        # 2. Fallback to standard search if not found in env
        if not success:
            try:
                ctypes.CDLL(dll_name)
                print(f"Loaded {dll_name} from system PATH")
                success = True
            except Exception:
                pass
                
        if success:
            loaded_libs.append(dll_name)
            
    if not loaded_libs:
        print("WARNING: No CUDA DLLs were loaded by the pre-loader.")
    else:
        print(f"CUDA Pre-load Summary: {len(loaded_libs)} lib(s) loaded.")
    print("-------------------------------")
    return len(loaded_libs) > 0
