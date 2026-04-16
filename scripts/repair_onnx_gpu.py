"""
faster-whisper pulls PyPI `onnxruntime` (CPU); that wheel can overwrite GPU DLLs.

1. Exit Privox and any Python/IDE using `.pixi/envs/default` (DLL lock on Windows).
2. Run:  .\\.pixi\\envs\\default\\python.exe scripts\\repair_onnx_gpu.py
   or:   pixi run repair-onnx-gpu   (if pixi does not try to sync mid-task)

Uses `pip install --no-deps` so numpy/sympy/torch pins from Pixi are not altered.

If uninstall fails with WinError 5 / 32, close apps using onnxruntime and retry.
If the environment looks broken afterward, run `pixi install` to restore conda pins, then run this script again.
"""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    print("Uninstalling CPU package 'onnxruntime' (if present)...", flush=True)
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "onnxruntime"], check=False)

    print("Force-reinstalling onnxruntime-gpu (--no-deps, keeps Pixi numpy/sympy/torch)...", flush=True)
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--force-reinstall",
            "--no-deps",
            "onnxruntime-gpu>=1.24,<2",
        ],
        check=False,
    )
    if r.returncode != 0:
        return r.returncode

    try:
        from onnxruntime.capi._pybind_state import get_available_providers

        print("Execution providers:", get_available_providers(), flush=True)
    except Exception as e:
        print("Warning: could not list providers:", e, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
