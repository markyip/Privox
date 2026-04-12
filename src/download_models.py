import os
import sys
import shutil
import subprocess
import threading
import time
import urllib.request
import models_config


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

def main(log_callback=None):
    def log_local(msg):
        if log_callback:
            log_callback(msg)
        else:
            log(msg)

    is_mac = sys.platform == "darwin"
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
        
    app_data_dir = models_config.get_app_data_dir(target_base_dir)
    
    # Load settings from .user_prefs.json (primary) or config.json (fallback)
    whisper_model_name = models_config.DEFAULT_ASR
    whisper_repo = models_config.ASR_LIBRARY[0]["whisper_repo"]
    grammar_name = models_config.DEFAULT_LLM
    
    asr_backend = "whisper" # Default value
    
    prefs_path = os.path.join(app_data_dir, ".user_prefs.json")
    config_path = os.path.join(app_data_dir, "config.json")
    
    load_path = prefs_path if os.path.exists(prefs_path) else config_path
    
    if os.path.exists(load_path):
        try:
            import json
            with open(load_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                whisper_model_name = config.get("whisper_model", whisper_model_name)
                grammar_name = config.get("current_refiner", grammar_name)
                asr_backend = config.get("asr_backend", "whisper")
                
                # Resolve ASR Repo
                for item in models_config.ASR_LIBRARY:
                    if item["name"] == whisper_model_name or item.get("whisper_model") == whisper_model_name:
                        if is_mac and item.get("mlx_repo"):
                            whisper_repo = item.get("mlx_repo")
                        else:
                            whisper_repo = item.get("whisper_repo") or item.get("repo")
                        whisper_model_name = item.get("whisper_model") or item["name"]
                        break
            log_local(f"Loaded tailored settings from {os.path.basename(load_path)}: {whisper_model_name}")
        except Exception as e:
            log_local(f"Config load error (using defaults): {e}")
            asr_backend = "whisper"

    log_local("[Stage 1/4] Environment verification & configuration loading...")

    # For installer stability, force plain HTTP backend for HF downloads.
    # Some Xet paths can appear "stuck" at 0.0MB in restricted networks.
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    log_local("Using HTTP download backend for Hugging Face (HF_HUB_DISABLE_XET=1).")
    
    models_dir = os.path.join(app_data_dir, "models")

    if not os.path.exists(models_dir):
        log_local(f"Creating models directory: {models_dir}")
        os.makedirs(models_dir)
        
    log_local(f"Checking AI Models (Backend: {asr_backend})...")

    grammar_file = models_config.LLM_LIBRARY[0]["file_name"]
    grammar_repo = models_config.LLM_LIBRARY[0]["repo_id"]
    for item in models_config.LLM_LIBRARY:
        if item["name"] == grammar_name:
            grammar_file = item.get("file_name", grammar_file)
            grammar_repo = item.get("repo_id", grammar_repo)
            break

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

    # 0. Install Llama-cpp-python with CUDA support (WINDOWS/LINUX ONLY)
    log_local("[Stage 2/4] Verifying LLM engine and CUDA dependencies...")
    # We check for version AND CUDA support. 0.2.24 (common in conda) is too old for Llama 3.2.
    needs_llama_install = False
    has_gpu = False
    
    if not is_mac:
        # 0a. Check for GPU presence
        try:
            import torch
            has_gpu = torch.cuda.is_available()
        except ImportError:
            try:
                import subprocess
                subprocess.check_output(["nvidia-smi"], stderr=subprocess.STDOUT)
                has_gpu = True
            except:
                has_gpu = False

        try:
            import llama_cpp
            version = getattr(llama_cpp, '__version__', '0.0.0')
            sys_info = str(llama_cpp.llama_print_system_info())
            llama_has_cuda = "CUDA = 1" in sys_info
            
            log(f"Found llama-cpp-python v{version} (CUDA: {llama_has_cuda}) | System GPU: {has_gpu}")
            
            # Llama 3.1/3.2 needs 0.2.90+ or 0.3.x
            v_parts = [int(p) for p in version.split('.') if p.isdigit()]
            if v_parts < [0, 2, 90]:
                log("Version is too old for Llama 3.2. Forcing update...")
                needs_llama_install = True
            elif has_gpu and not llama_has_cuda:
                log("GPU present but llama-cpp-python is CPU-only. Updating to CUDA version...")
                needs_llama_install = True
                
        except ImportError:
            log("llama-cpp-python missing. Attempting install...")
            needs_llama_install = True

        if needs_llama_install:
            import subprocess
            try:
                # Environment isolation
                env = os.environ.copy()
                env["PYTHONNOUSERSITE"] = "1"
                
                # Base command
                cmd = [sys.executable, "-m", "pip", "install", "llama-cpp-python==0.3.4"]
                
                if has_gpu:
                    log_local("Installing llama-cpp-python binary wheel (CUDA 12.4)...")
                    cmd += ["--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/cu124"]
                else:
                    log_local("Installing llama-cpp-python (CPU-only)...")
                
                cmd += [
                    "--no-input",
                    "--no-cache-dir",
                    "--only-binary=:all:",
                    "--no-deps"
                ]
                
                subprocess.check_call(cmd, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                log_local("llama-cpp-python installed successfully.")
            except subprocess.CalledProcessError as e:
                log_local(f"CRITICAL: Failed to install llama-cpp-python: {e}")
                pass

            
    try:
        from huggingface_hub import hf_hub_download, snapshot_download, hf_hub_url
    except ImportError:
        log_local("Error: huggingface_hub not installed in environment.")
        sys.exit(1)

    # 1. Grammar Model (LLM)
    log_local("[Stage 3/4] Verifying LLM Grammar Model files...")
    
    # Extract mlx_repo contextually based on the user's selected grammar_file
    mlx_repo = None
    for item in models_config.LLM_LIBRARY:
        if item.get("file_name") == grammar_file:
            mlx_repo = item.get("mlx_repo")
            break

    if is_mac:
        if mlx_repo:
            # Construct folder name from the repo string (e.g., "mlx-community/Qwen2.5-7B-Instruct" -> "Qwen2.5-7B-Instruct")
            repo_folder_name = mlx_repo.split("/")[-1]
            mac_target_dir = os.path.join(models_dir, repo_folder_name)
            
            has_weights = False
            if os.path.isdir(mac_target_dir):
                try:
                    has_weights = any(entry.endswith(".safetensors") for entry in os.listdir(mac_target_dir))
                except Exception:
                    has_weights = False

            has_required_files = (
                os.path.exists(os.path.join(mac_target_dir, "config.json")) and
                (
                    os.path.exists(os.path.join(mac_target_dir, "tokenizer.json")) or
                    os.path.exists(os.path.join(mac_target_dir, "tokenizer_config.json"))
                )
            )

            if not (has_weights and has_required_files):
                log_local(f"Downloading MLX Grammar Model ({mlx_repo}) for macOS...")
                snapshot_download(repo_id=mlx_repo, local_dir=mac_target_dir)
                log_local("MLX Grammar Model download complete.")
            else:
                log_local(f"MLX Grammar Model {mlx_repo} present.")
        else:
            log_local(f"WARNING: The selected Grammar Model ({grammar_file}) does not have a native MLX equivalent (mlx_repo missing in config).")
            log_local("It may not be supported on macOS or will rely on CPU fallback.")
    else:
        # Windows/Linux uses single GGUF file
        if not os.path.exists(os.path.join(models_dir, grammar_file)):
            log_local(f"Downloading Grammar Model ({grammar_file})...")
            log_local(f"Source Repo: {grammar_repo}")
            log_local("Large GGUF download can take several minutes depending on network speed.")

            target_path = os.path.join(models_dir, grammar_file)

            def _download_http_stream(repo_id, filename, out_path):
                # Direct streaming download to avoid silent cache-only phases.
                url = hf_hub_url(repo_id=repo_id, filename=filename)
                tmp_path = out_path + ".part"
                req = urllib.request.Request(url, headers={"User-Agent": "Privox-Installer/1.2.1"})
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
                            log_local(
                                f"Fallback download in progress... {mb:.1f} MB "
                                "(no size change yet, still waiting for network chunks)"
                            )
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

    # 2. ASR weights on disk (faster-whisper layout under models/whisper-<id>, or Qwen snapshot in same path)
    if asr_backend == "qwen_asr":
        log_local("[Stage 4/4] Verifying speech recognition model files (Qwen-ASR)...")
    else:
        log_local("[Stage 4/4] Verifying transcription model files (faster-whisper / Whisper)...")
    whisper_target = os.path.join(models_dir, "whisper-" + whisper_model_name)
    
    # Check for repo-specific tag to force redownload if we switched repos
    repo_tag_file = os.path.join(whisper_target, ".repo_id")
    existing_repo = ""
    if os.path.exists(repo_tag_file):
        try:
            with open(repo_tag_file, "r") as f:
                existing_repo = f.read().strip()
        except: pass
    
    # Robust check: Ensure critical files exist
    if is_mac:
        # MLX weights can be .safetensors or .npz
        critical_files = ["config.json", "tokenizer.json", "preprocessor_config.json"]
        # We'll check for either model.safetensors or weights.npz
        has_weights = os.path.exists(os.path.join(whisper_target, "model.safetensors")) or \
                      os.path.exists(os.path.join(whisper_target, "weights.npz"))
    else:
        critical_files = ["model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"]
        has_weights = os.path.exists(os.path.join(whisper_target, "model.bin"))

    needs_download = False
    
    if existing_repo != whisper_repo:
            needs_download = True
            if os.path.exists(whisper_target):
                log_local(f"Repository mismatch ({existing_repo} vs {whisper_repo}). Clearing old model data...")
                try:
                    shutil.rmtree(whisper_target)
                    os.makedirs(whisper_target)
                except: pass
    
    if not os.path.exists(whisper_target) or not has_weights:
        needs_download = True
    else:
        for f in critical_files:
            if not os.path.exists(os.path.join(whisper_target, f)):
                needs_download = True
                break
                
    if needs_download:
        # Actual repo is already resolved above based on Mac status
        actual_repo = whisper_repo
        
        log_local(f"Downloading Whisper Model ({whisper_model_name}) from {actual_repo}...")
        log_local("Note: Large models (3GB+) may take several minutes. Please wait.")
        snapshot_download(
            repo_id=actual_repo, 
            local_dir=whisper_target
        )
        # Save the repo tag so we don't redownload again if successful
        log_local("Finalizing ASR model setup...")
        try:
            with open(repo_tag_file, "w") as f:
                f.write(whisper_repo)
        except: pass
        log_local("ASR model setup complete.")
        
    log_local("All AI models are verified and ready.")

if __name__ == "__main__":
    main()
