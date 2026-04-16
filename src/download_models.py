import json
import os
import sys
import shutil
import subprocess
import threading
import time
import urllib.request
import models_config




def ensure_asr_snapshot(
    target_base_dir: str,
    whisper_model_name: str,
    whisper_repo: str,
    asr_backend: str,
    log_local=None,
) -> None:
    """
    Ensure ASR weights exist under models/whisper-<whisper_model_name>.
    Runs snapshot_download from whisper_repo when files are missing or repo tag mismatches.
    Used by download_models.main() and by Settings GUI when user selects an ONNX ASR preset.
    """
    if log_local is None:
        log_local = log

    try:
        from huggingface_hub import snapshot_download
    except ImportError as e:
        raise RuntimeError("huggingface_hub is required for model download.") from e

    models_dir = os.path.join(target_base_dir, "models")
    if not os.path.exists(models_dir):
        log_local(f"Creating models directory: {models_dir}")
        os.makedirs(models_dir, exist_ok=True)

    if asr_backend == "qwen_asr":
        log_local("[ASR] Verifying Qwen-ASR (Transformers) files...")
    else:
        log_local("[ASR] Verifying faster-whisper / Whisper files...")

    whisper_target = os.path.join(models_dir, "whisper-" + whisper_model_name)
    repo_tag_file = os.path.join(whisper_target, ".repo_id")
    existing_repo = ""
    if os.path.exists(repo_tag_file):
        try:
            with open(repo_tag_file, "r") as f:
                existing_repo = f.read().strip()
        except Exception:
            pass

    critical_files = ["model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"]
    needs_download = False

    if existing_repo != whisper_repo:
        needs_download = True
        if os.path.exists(whisper_target):
            if existing_repo.strip():
                log_local(
                    f"ASR .repo_id mismatch ({existing_repo!r} vs {whisper_repo!r}); clearing folder before re-download."
                )
            else:
                log_local(
                    f"ASR folder exists without a valid .repo_id (e.g. partial download); "
                    f"clearing before snapshot to {whisper_repo!r}."
                )
            try:
                shutil.rmtree(whisper_target)
                os.makedirs(whisper_target)
            except Exception:
                pass

    if not os.path.exists(whisper_target):
        needs_download = True
    else:
        for f in critical_files:
            if not os.path.exists(os.path.join(whisper_target, f)):
                needs_download = True
                break

    if not needs_download:
        log_local(f"[ASR] Already present: {whisper_target}")
        return

    if asr_backend == "qwen_asr":
        log_local(
            f"Downloading Qwen-ASR from {whisper_repo} "
            f"(local folder whisper-{whisper_model_name})."
        )
    else:
        log_local(f"Downloading Whisper / CT2 weights ({whisper_model_name}) from {whisper_repo}...")
    log_local("Note: Large models may take several minutes. Please wait.")

    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

    dl_kw: dict = {"repo_id": whisper_repo, "local_dir": whisper_target}

    try:
        snapshot_download(**dl_kw)
    except Exception as e:
        log_local(f"[ASR] huggingface_hub snapshot_download failed: {e}")
        raise RuntimeError(
            f"Failed to download ASR from {whisper_repo!r} into {whisper_target}. "
            "Check network, disk space, and HF access. "
            "Try: pixi run python src/download_models.py from the install folder."
        ) from e

    log_local("Finalizing ASR download...")
    try:
        with open(repo_tag_file, "w") as f:
            f.write(whisper_repo)
    except Exception:
        pass

    log_local("[ASR] Setup complete.")


def _win_short_path(path: str) -> str:
    """8.3 path so CMAKE_ARGS is not split on spaces (Program Files, etc.)."""
    if sys.platform != "win32" or not path or not os.path.exists(path):
        return path
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetShortPathNameW(os.path.normpath(path), buf, len(buf))
        return buf.value if n else path
    except Exception:
        return path


def _find_nvcc_windows() -> str | None:
    """Return path to nvcc.exe from CUDA_PATH or default NVIDIA install roots."""
    for key in ("CUDA_PATH", "CUDA_HOME", "CUDA_ROOT"):
        root = os.environ.get(key)
        if root:
            cand = os.path.join(root, "bin", "nvcc.exe")
            if os.path.isfile(cand):
                return cand
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    cuda = os.path.join(pf, "NVIDIA GPU Computing Toolkit", "CUDA")
    best_path = None
    best_ver: tuple[int, ...] = ()
    if not os.path.isdir(cuda):
        return None
    for name in os.listdir(cuda):
        if not name.startswith("v"):
            continue
        cand = os.path.join(cuda, name, "bin", "nvcc.exe")
        if not os.path.isfile(cand):
            continue
        parts = []
        for p in name.lstrip("v").split("."):
            if p.isdigit():
                parts.append(int(p))
            else:
                break
        tup = tuple(parts) if parts else (0,)
        if tup > best_ver:
            best_ver = tup
            best_path = cand
    return best_path


def _local_llama_cpp_wheel_paths(wheels_dir: str) -> list[str]:
    """Paths to bundled llama_cpp_python-*.whl matching this Python, highest version first."""
    if not wheels_dir or not os.path.isdir(wheels_dir):
        return []
    from packaging.version import Version

    import platform as plat

    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"

    def _parse_ver(basename: str) -> Version:
        if not basename.startswith("llama_cpp_python-") or not basename.endswith(".whl"):
            return Version("0")
        core = basename[len("llama_cpp_python-") : -4]
        sep = f"-{py_tag}-"
        idx = core.find(sep)
        ver_s = core[:idx] if idx > 0 else core.split("-")[0]
        try:
            return Version(ver_s)
        except Exception:
            return Version("0")

    ranked: list[tuple[Version, str]] = []
    for name in os.listdir(wheels_dir):
        if not name.endswith(".whl") or not name.startswith("llama_cpp_python-"):
            continue
        nlow = name.lower()
        # cp312-cp312-win_amd64, or py3-none-win_amd64 from `pip wheel` (any Python 3 on that platform).
        py_match = py_tag in name
        if not py_match and sys.version_info.major == 3 and "py3-none" in nlow:
            py_match = True
        if not py_match:
            continue
        if sys.platform == "win32" and plat.machine().lower() in ("amd64", "x86_64"):
            if "win_amd64" not in nlow:
                continue
        full = os.path.join(wheels_dir, name)
        if os.path.isfile(full):
            ranked.append((_parse_ver(name), full))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [p for _v, p in ranked]


def log(msg):
    print(f"[ModelSetup] {msg}", flush=True)


def reconcile_whisper_model_folder_id(whisper_model_name: str, whisper_repo: str) -> str:
    """
    Local ASR files live under models/whisper-<whisper_model>.
    If config.json has a stale whisper_model id but whisper_repo matches a library entry,
    return that entry's folder id (fixes ONNX downloaded into whisper-distil-large-v3, etc.).
    """
    r = (whisper_repo or "").strip()
    if not r:
        return whisper_model_name
    for m in models_config.ASR_LIBRARY:
        m_repo = (m.get("whisper_repo") or m.get("repo") or "").strip()
        if m_repo == r:
            mid = (m.get("whisper_model") or "").strip()
            return mid if mid else whisper_model_name
    return whisper_model_name


def main(log_callback=None):
    def log_local(msg):
        if log_callback:
            log_callback(msg)
        else:
            log(msg)

    print(f"[DEBUG] download_models.main() entered with log_callback={log_callback}", flush=True)
    # huggingface_hub uses threaded tqdm for each file; mixed with [ModelSetup] lines it corrupts Windows consoles
    # (prompt glued to progress text, bars re-printing after "complete"). Disable tqdm for CLI unless user opted in.
    if log_callback is None and os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS") is None:
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        log_local(
            "HF per-file progress bars disabled for clean [ModelSetup] logs "
            "(set HF_HUB_DISABLE_PROGRESS_BARS=0 before running to show tqdm)."
        )
    log_local("Initializing model setup engine...")
    # 0. Environment Isolation
    os.environ["PYTHONNOUSERSITE"] = "1"
    import site
    site.ENABLE_USER_SITE = False
    
    # Determine target_base_dir relative to the script location
    # This ensures that even if called from elsewhere, we use the project root.
    if getattr(sys, 'frozen', False):
        target_base_dir = os.path.dirname(sys.executable)
    else:
        target_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Load settings from config.json if it exists
    _def_asr = next(
        m for m in models_config.ASR_LIBRARY
        if m.get("whisper_model") == models_config.DEFAULT_ASR_WHISPER_MODEL
    )
    whisper_model_name = _def_asr["whisper_model"]
    whisper_repo = _def_asr["whisper_repo"]
    grammar_file = models_config.LLM_LIBRARY[0]["file_name"] 
    grammar_repo = models_config.LLM_LIBRARY[0]["repo_id"]
    
    config_path = os.path.join(target_base_dir, "config.json")
    asr_backend = "whisper"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                whisper_model_name = config.get("whisper_model", whisper_model_name)
                whisper_repo = config.get("whisper_repo", whisper_repo)
                grammar_file = config.get("grammar_file", grammar_file)
                grammar_repo = config.get("grammar_repo", grammar_repo)
                asr_backend = config.get("asr_backend", "whisper")
            log_local(f"Loaded tailored settings from config.json: {whisper_model_name}")
        except Exception as e:
            log_local(f"Config load error (using defaults): {e}")
            asr_backend = "whisper"

    _fixed_id = reconcile_whisper_model_folder_id(whisper_model_name, whisper_repo)
    if _fixed_id != whisper_model_name:
        log_local(
            f"[ASR] Corrected whisper_model folder id {whisper_model_name!r} -> {_fixed_id!r} "
            f"(must match ASR_LIBRARY entry for repo {whisper_repo})."
        )
        whisper_model_name = _fixed_id
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    _cfg = json.load(f)
                _cfg["whisper_model"] = whisper_model_name
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(_cfg, f, indent=4)
                log_local("[ASR] Wrote corrected whisper_model to config.json.")
        except Exception as _e:
            log_local(f"[ASR] Could not update config.json: {_e}")

    log_local("[Stage 1/4] Environment verification & configuration loading...")

    # For installer stability, force plain HTTP backend for HF downloads.
    # Some Xet paths can appear "stuck" at 0.0MB in restricted networks.
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    log_local("Using HTTP download backend for Hugging Face (HF_HUB_DISABLE_XET=1).")
    
    models_dir = os.path.join(target_base_dir, "models")
    if not os.path.exists(models_dir):
        log_local(f"Creating models directory: {models_dir}")
        os.makedirs(models_dir)
        
    log_local(f"Checking AI Models (Backend: {asr_backend})...")

    # 0. SenseVoiceSmall (Alternative)
    if asr_backend == "sensevoice":
        sense_dir = os.path.join(models_dir, "SenseVoiceSmall")
        if not os.path.exists(sense_dir):
            log_local("Downloading SenseVoiceSmall from ModelScope...")
            try:
                from modelscope.hub.snapshot_download import snapshot_download
                snapshot_download('iic/SenseVoiceSmall', local_dir=sense_dir)
            except ImportError:
                log_local("modelscope not installed. Using huggingface fallback...")
                from huggingface_hub import snapshot_download
                snapshot_download(repo_id='iic/SenseVoiceSmall', local_dir=sense_dir)
        else:
            log_local("SenseVoiceSmall model present.")

    # 0. Install Llama-cpp-python with CUDA support
    log_local("[Stage 2/4] Verifying LLM engine and CUDA dependencies...")
    # We check for version AND CUDA support. 0.2.24 (common in conda) is too old for Llama 3.2.
    needs_llama_install = False
    
    # 0a. Check for GPU presence
    has_gpu = False
    try:
        import torch
        has_gpu = torch.cuda.is_available()
    except ImportError:
        try:
            subprocess.check_output(["nvidia-smi"], stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            has_gpu = True
        except:
            has_gpu = False

    def _version_tuple(v):
        parts = []
        for p in str(v).split('.'):
            if p.isdigit():
                parts.append(int(p))
            else:
                break
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    try:
        import llama_cpp
        version = getattr(llama_cpp, '__version__', '0.0.0')
        _sys_fn = getattr(llama_cpp, "llama_system_info", getattr(llama_cpp, "llama_print_system_info", None))
        sys_info = str(_sys_fn()) if _sys_fn else ""
        llama_has_cuda = ("CUDA = 1" in sys_info) or ("CUDA :" in sys_info)
        
        log_local(f"Found llama-cpp-python v{version} (CUDA: {llama_has_cuda}) | System GPU: {has_gpu}")
        
        # Windows+cp312 abetlen wheels often stop at 0.3.19 CUDA; treat 0.3.19+CUDA as OK. Never accept CPU-only
        # llama when the machine has a CUDA GPU - that breaks offload and often fails to load new GGUF.
        if _version_tuple(version) < (0, 3, 19):
            log_local("llama-cpp-python is below 0.3.19. Forcing update...")
            needs_llama_install = True
        elif has_gpu and not llama_has_cuda:
            log_local("GPU present but llama-cpp-python is CPU-only. Updating to CUDA build...")
            needs_llama_install = True
            
    except ImportError:
        log_local("llama-cpp-python missing. Attempting install...")
        needs_llama_install = True

    if needs_llama_install:
        try:
            # Environment isolation
            env = os.environ.copy()
            env["PYTHONNOUSERSITE"] = "1"

            def _pip_run(cmd, env_try, attempt_label):
                """Run pip; log stderr/stdout tail on failure so installers are diagnosable on Windows."""
                log_local(f"llama-cpp {attempt_label}: {' '.join(cmd)}")
                try:
                    r = subprocess.run(
                        cmd,
                        env=env_try,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=7200,
                    )
                except subprocess.TimeoutExpired:
                    log_local("llama-cpp pip: timed out after 2h.")
                    return False
                if r.returncode == 0:
                    return True
                blob = ((r.stderr or "").strip() + "\n" + (r.stdout or "").strip()).strip()
                tail = blob[-4000:] if blob else "(no pip output)"
                log_local(f"llama-cpp pip failed (exit {r.returncode}). Last output:\n{tail}")
                return False

            def _cmake_env(base_env, gpu):
                env_try = base_env.copy()
                cmake_base = "-DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=OFF"
                if gpu:
                    cmake_base += " -DGGML_CUDA=ON"
                    # CMake 4.x + MSVC: "No CUDA toolset found" unless nvcc is explicit (and paths avoid spaces).
                    if sys.platform == "win32":
                        nvcc = _find_nvcc_windows()
                        if nvcc:
                            nvcc_cmake = _win_short_path(nvcc).replace("\\", "/")
                            cmake_base += f" -DCMAKE_CUDA_COMPILER={nvcc_cmake}"
                            # MSVC newer than CUDA's tested list + UTF-8 (matches scripts/install_llama_cuda.py).
                            cmake_base += (
                                " -DCMAKE_CUDA_FLAGS=-allow-unsupported-compiler;-Xcompiler=/utf-8"
                            )
                            env_try["CUDACXX"] = nvcc
                            cuda_root = os.path.dirname(os.path.dirname(nvcc))
                            env_try["CUDA_PATH"] = cuda_root
                            env_try["CUDA_HOME"] = cuda_root
                env_try["CMAKE_ARGS"] = cmake_base
                env_try["CFLAGS"] = "/utf-8"
                env_try["CXXFLAGS"] = "/utf-8"
                return env_try

            if has_gpu:
                _nv = _find_nvcc_windows()
                if _nv:
                    log_local(f"Source builds will use CMAKE_CUDA_COMPILER={_win_short_path(_nv)} (fixes 'No CUDA toolset found').")
                else:
                    log_local("WARNING: nvcc.exe not found in CUDA_PATH / Program Files - GPU source builds may fail.")
                log_local(
                    "Installing llama-cpp-python (GPU): order is bundled wheels/ (if present), "
                    "PyPI 0.3.20 wheels, install_llama_cuda.py (Windows sdist), pip 0.3.20 sdist, "
                    "0.3.19 wheels/sdist, legacy wheels, then CPU."
                )
            else:
                log_local("Installing llama-cpp-python (CPU)...")

            exe = sys.executable
            abetlen_cuda = [
                ("cu124", "https://abetlen.github.io/llama-cpp-python/whl/cu124"),
                ("cu121", "https://abetlen.github.io/llama-cpp-python/whl/cu121"),
                ("cu118", "https://abetlen.github.io/llama-cpp-python/whl/cu118"),
            ]

            def _run_win_install_llama_cuda_script() -> bool:
                """MSVC + Windows SDK + Ninja on PATH; 0.3.20 wheel missing on cp312 often falls through to sdist."""
                helper = os.path.join(target_base_dir, "scripts", "install_llama_cuda.py")
                if not os.path.isfile(helper):
                    log_local("scripts/install_llama_cuda.py not found (reinstall app or copy scripts/ next to Privox.exe).")
                    return False
                log_local(
                    "No 0.3.20 CUDA wheel for this Python - running scripts/install_llama_cuda.py "
                    "(0.3.20: MSVC + CUDA paths, then pip sdist if needed)..."
                )
                r = subprocess.run(
                    [exe, helper],
                    env=env.copy(),
                    cwd=target_base_dir,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=7200,
                )
                if r.returncode == 0:
                    log_local("install_llama_cuda.py finished OK.")
                    return True
                tail = ((r.stderr or "") + (r.stdout or ""))[-4000:]
                log_local(f"install_llama_cuda.py failed (exit {r.returncode}). Last output:\n{tail}")
                return False

            legacy_wheel_attempts = []
            if has_gpu:
                for ver in ("0.3.4", "0.2.90"):
                    for _tag, url in abetlen_cuda[:2]:
                        legacy_wheel_attempts.append(
                            [
                                exe, "-m", "pip", "install", "--upgrade",
                                f"llama-cpp-python=={ver}",
                                "--extra-index-url", url,
                                "--only-binary=:all:",
                                "--no-deps", "--no-input", "--no-cache-dir",
                            ]
                        )

            installed = False
            if has_gpu:
                # 0) Vendor wheel shipped inside the installer (wheels/*.whl) — same Python tag as Pixi (e.g. cp312).
                wheels_root = os.path.join(target_base_dir, "wheels")
                bundled_wheels = _local_llama_cpp_wheel_paths(wheels_root)
                if bundled_wheels:
                    log_local(
                        f"Installing from {len(bundled_wheels)} bundled wheel(s) under wheels/ (newest first)..."
                    )
                for bi, whl_path in enumerate(bundled_wheels, 1):
                    cmd = [
                        exe,
                        "-m",
                        "pip",
                        "install",
                        "--upgrade",
                        "--force-reinstall",
                        "--no-deps",
                        "--no-input",
                        "--no-cache-dir",
                        whl_path,
                    ]
                    label = f"GPU bundled wheel {bi}/{len(bundled_wheels)} ({os.path.basename(whl_path)})"
                    if _pip_run(cmd, _cmake_env(env, has_gpu), label):
                        installed = True
                        break

                # Order matters: 0.3.19 prebuilt must NOT win before we try 0.3.20 source (install_llama_cuda.py).
                for _tag, url in abetlen_cuda:
                    cmd = [
                        exe, "-m", "pip", "install", "--upgrade",
                        "llama-cpp-python==0.3.20",
                        "--extra-index-url", url,
                        "--only-binary=:all:",
                        "--no-deps", "--no-input", "--no-cache-dir",
                    ]
                    if _pip_run(cmd, _cmake_env(env, has_gpu), f"GPU 0.3.20 wheel ({_tag})"):
                        installed = True
                        break

                if not installed and sys.platform == "win32":
                    if _run_win_install_llama_cuda_script():
                        installed = True

                if not installed:
                    for _tag, url in abetlen_cuda[:2]:
                        cmd = [
                            exe, "-m", "pip", "install", "--upgrade",
                            "llama-cpp-python==0.3.20",
                            "--extra-index-url", url,
                            "--no-deps", "--no-input", "--no-cache-dir",
                        ]
                        if _pip_run(cmd, _cmake_env(env, has_gpu), f"GPU 0.3.20 sdist ({_tag})"):
                            installed = True
                            break

                if not installed:
                    for _tag, url in abetlen_cuda:
                        cmd = [
                            exe, "-m", "pip", "install", "--upgrade",
                            "llama-cpp-python==0.3.19",
                            "--extra-index-url", url,
                            "--only-binary=:all:",
                            "--no-deps", "--no-input", "--no-cache-dir",
                        ]
                        if _pip_run(cmd, _cmake_env(env, has_gpu), f"GPU 0.3.19 wheel ({_tag})"):
                            installed = True
                            break

                if not installed:
                    for _tag, url in abetlen_cuda[:2]:
                        cmd = [
                            exe, "-m", "pip", "install", "--upgrade",
                            "llama-cpp-python==0.3.19",
                            "--extra-index-url", url,
                            "--no-deps", "--no-input", "--no-cache-dir",
                        ]
                        if _pip_run(cmd, _cmake_env(env, has_gpu), f"GPU 0.3.19 sdist ({_tag})"):
                            installed = True
                            break
            else:
                cpu_cmds = [
                    [
                        exe, "-m", "pip", "install", "--upgrade",
                        "llama-cpp-python==0.3.20",
                        "--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/cpu",
                        "--only-binary=:all:",
                        "--no-deps", "--no-input", "--no-cache-dir",
                    ],
                    [
                        exe, "-m", "pip", "install", "--upgrade",
                        "llama-cpp-python==0.3.20",
                        "--no-deps", "--no-input", "--no-cache-dir",
                    ],
                ]
                for i, cmd in enumerate(cpu_cmds, 1):
                    if _pip_run(cmd, env, f"CPU pip {i}/{len(cpu_cmds)}"):
                        installed = True
                        break

            if not installed and legacy_wheel_attempts:
                log_local(
                    "Trying legacy abetlen wheels (0.3.4 / 0.2.90) - often the newest prebuilt for Windows+cp312. "
                    "If the refiner still fails to load Gemma/Qwen GGUF, build 0.3.20+ from source "
                    "(scripts/install_llama_cuda.py) or use a Python version with newer wheels."
                )
                for j, cmd in enumerate(legacy_wheel_attempts, 1):
                    env_try = _cmake_env(env, has_gpu)
                    if _pip_run(cmd, env_try, f"legacy wheel {j}/{len(legacy_wheel_attempts)}"):
                        installed = True
                        break

            # Last resort on GPU: CPU wheel so ASR still works; refiner is slow or may OOM - better than silent failure.
            if not installed and has_gpu:
                log_local(
                    "WARNING: All CUDA installs failed. Falling back to CPU llama-cpp-python - "
                    "refiner will be slow; install Visual Studio 2022 Build Tools (C++) and a CUDA toolkit, "
                    "then run: pixi run install-llama-cuda  OR  python scripts/install_llama_cuda.py"
                )
                for ver in ("0.3.20", "0.3.19", "0.3.4"):
                    cmd = [
                        exe, "-m", "pip", "install", "--upgrade",
                        f"llama-cpp-python=={ver}",
                        "--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/cpu",
                        "--only-binary=:all:",
                        "--no-deps", "--no-input", "--no-cache-dir",
                    ]
                    if _pip_run(cmd, env, f"CPU fallback wheel {ver}"):
                        installed = True
                        break

            if not installed:
                log_local(
                    "CRITICAL: Could not install llama-cpp-python. "
                    "Windows+GPU: ensure MSVC Build Tools (C++), Windows SDK, and CUDA Toolkit; "
                    "optional: install 'CUDA' integration for Visual Studio from the NVIDIA installer. "
                    "Then from the install folder run: python scripts\\install_llama_cuda.py"
                )
            else:
                log_local("llama-cpp-python installed successfully.")
        except subprocess.CalledProcessError as e:
            log_local(f"CRITICAL: Failed to install llama-cpp-python: {e}")
            pass
            
    try:
        from huggingface_hub import hf_hub_download, snapshot_download, hf_hub_url
    except ImportError:
        log_local("Error: huggingface_hub not installed in environment.")
        sys.exit(1)

    # 1. Grammar Model (LLM Refiner)
    log_local("[Stage 3/4] Verifying LLM Grammar Model files...")
    if not os.path.exists(os.path.join(models_dir, grammar_file)):
        log_local(f"Downloading Grammar Model ({grammar_file})...")
        log_local(f"Source Repo: {grammar_repo}")
        log_local("Large GGUF download can take several minutes depending on network speed.")

        target_path = os.path.join(models_dir, grammar_file)

        def _download_http_stream(repo_id, filename, out_path):
            # Direct streaming download to avoid silent cache-only phases.
            url = hf_hub_url(repo_id=repo_id, filename=filename)
            tmp_path = out_path + ".part"
            req = urllib.request.Request(url, headers={"User-Agent": "Privox-Installer/1.2.2"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", "0") or "0")
                downloaded = 0
                last_log = time.time()
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(8 * 1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_log >= 5:
                            mb = downloaded / (1024 * 1024)
                            if total > 0:
                                pct = (downloaded / total) * 100
                                log_local(f"Direct download... {mb:.1f} MB ({pct:.1f}%)")
                            else:
                                log_local(f"Direct download... {mb:.1f} MB")
                            last_log = now
            os.replace(tmp_path, out_path)

        try:
            # Prefer explicit streamed HTTP so installer always shows true byte progress.
            _download_http_stream(grammar_repo, grammar_file, target_path)
        except Exception as first_error:
            log_local(f"Direct HTTP attempt failed: {first_error}. Falling back to huggingface_hub...")
            stop_event = threading.Event()

            def progress_heartbeat():
                last_bytes = -1
                stall_count = 0
                while not stop_event.wait(5):
                    size_bytes = 0
                    if os.path.exists(target_path):
                        try:
                            size_bytes = os.path.getsize(target_path)
                        except Exception:
                            size_bytes = 0

                    if size_bytes == last_bytes:
                        stall_count += 1
                    else:
                        stall_count = 0
                    last_bytes = size_bytes

                    mb = size_bytes / (1024 * 1024)
                    if stall_count >= 6:
                        log_local(f"Fallback download in progress... {mb:.1f} MB (no size change yet, still waiting for network chunks)")
                    else:
                        log_local(f"Fallback download in progress... {mb:.1f} MB")

            progress_thread = threading.Thread(target=progress_heartbeat, daemon=True)
            progress_thread.start()
            try:
                hf_hub_download(
                    repo_id=grammar_repo,
                    filename=grammar_file,
                    local_dir=models_dir,
                    etag_timeout=30,
                )
            except Exception as second_error:
                log_local(f"Fallback attempt failed: {second_error}. Retrying once...")
                hf_hub_download(
                    repo_id=grammar_repo,
                    filename=grammar_file,
                    local_dir=models_dir,
                    force_download=False,
                    etag_timeout=30,
                )
            finally:
                stop_event.set()
                progress_thread.join(timeout=1)

        log_local("Grammar Model download complete.")
    else:
        log_local(f"Grammar Model {grammar_file} present.")

    # 2. ASR weights on disk (faster-whisper layout under models/whisper-<id>, or Qwen / ONNX snapshot)
    log_local("[Stage 4/4] Verifying speech / transcription model files...")
    ensure_asr_snapshot(target_base_dir, whisper_model_name, whisper_repo, asr_backend, log_local)

    log_local("All AI models are verified and ready.")

if __name__ == "__main__":
    main()
