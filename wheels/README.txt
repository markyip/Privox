Bundled llama-cpp-python (optional, for Windows installers)

1. Build or obtain a CUDA wheel for the same Python as pixi (e.g. cp312), e.g.:
   llama_cpp_python-0.3.20-cp312-cp312-win_amd64.whl
   Prefer: pixi run wheel-llama-cuda  (uses scripts/install_llama_cuda.py --wheel; CUDA + UTF-8 + Ninja).
   Avoid: pixi run pip wheel ... alone — that often builds CPU-only and can hit MSVC C4819/C2001 on jinja headers.

2. Copy the .whl file into this folder before running:
   pixi run build

3. PyInstaller embeds wheels/; the installer copies it next to Privox.exe. During first-run
   model setup, pip installs this wheel into the Pixi env before PyPI / source fallbacks.

*.whl files are gitignored by default (large binaries). CI or release builds should copy
the wheel in place before packaging.
