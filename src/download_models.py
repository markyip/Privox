import os
import sys
import shutil
import models_config

def log(msg):
    print(f"[ModelSetup] {msg}", flush=True)

def main(log_callback=None):
    def log_local(msg):
        if log_callback:
            log_callback(msg)
        else:
            log(msg)

    print(f"[DEBUG] download_models.main() entered with log_callback={log_callback}", flush=True)
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
    
    models_dir = os.path.join(app_data_dir, "models")

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

    # 0. Install Llama-cpp-python with CUDA support (WINDOWS/LINUX ONLY)
    log_local("[Stage 2/4] Verifying LLM engine and CUDA dependencies...")
    # We check for version AND CUDA support. 0.2.24 (common in conda) is too old for Llama 3.2.
    is_mac = sys.platform == "darwin"
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
        from huggingface_hub import hf_hub_download, snapshot_download
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
            # If this fails (e.g., 401 Unauthorized or 404 Not Found),
            # it will now raise an exception, crash the script, and alert the GUI.
            hf_hub_download(repo_id=grammar_repo, filename=grammar_file, local_dir=models_dir)
            log_local("Grammar Model download complete.")
        else:
            log_local(f"Grammar Model {grammar_file} present.")

    # 2. Whisper Model (Faster-Whisper Format)
    log_local("[Stage 4/4] Verifying Transcription Model files (Whisper)...")
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
    is_mac = sys.platform == "darwin"
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
        is_mac = sys.platform == "darwin"
        # Actual repo is already resolved above based on Mac status
        actual_repo = whisper_repo
        
        log_local(f"Downloading Whisper Model ({whisper_model_name}) from {actual_repo}...")
        log_local("Note: Large models (3GB+) may take several minutes. Please wait.")
        snapshot_download(
            repo_id=actual_repo, 
            local_dir=whisper_target
        )
        # Save the repo tag so we don't redownload again if successful
        log_local("Finalizing Whisper model setup...")
        try:
            with open(repo_tag_file, "w") as f:
                f.write(whisper_repo)
        except: pass
        log_local("Whisper Model setup complete.")
        
    log_local("All AI models are verified and ready.")

if __name__ == "__main__":
    main()
