import os
import sys
import shutil
import models_config

def log(msg):
    print(f"[ModelSetup] {msg}", flush=True)

def main():
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
    
    # Load settings from config.json if it exists
    whisper_model_name = models_config.ASR_LIBRARY[0]["whisper_model"]
    whisper_repo = models_config.ASR_LIBRARY[0]["whisper_repo"]
    grammar_file = models_config.LLM_LIBRARY[1]["file_name"] # Llama 3.2
    grammar_repo = models_config.LLM_LIBRARY[1]["repo_id"]
    
    config_path = os.path.join(app_data_dir, "config.json")
    if os.path.exists(config_path):
        try:
            import json
            with open(config_path, "r") as f:
                config = json.load(f)
                whisper_model_name = config.get("whisper_model", whisper_model_name)
                whisper_repo = config.get("whisper_repo", whisper_repo)
                grammar_file = config.get("grammar_file", grammar_file)
                grammar_repo = config.get("grammar_repo", grammar_repo)
                asr_backend = config.get("asr_backend", "whisper")
            log(f"Loaded tailored settings from config.json: {whisper_model_name}")
        except Exception as e:
            log(f"Config load error (using defaults): {e}")
            asr_backend = "whisper"

    models_dir = os.path.join(app_data_dir, "models")
    if not os.path.exists(models_dir):
        os.makedirs(models_dir)
        
    log(f"Checking AI Models (Backend: {asr_backend})...")

    # 0. SenseVoiceSmall (Alternative)
    if asr_backend == "sensevoice":
        sense_dir = os.path.join(models_dir, "SenseVoiceSmall")
        if not os.path.exists(sense_dir):
            log("Downloading SenseVoiceSmall from ModelScope...")
            try:
                from modelscope.hub.snapshot_download import snapshot_download
                snapshot_download('iic/SenseVoiceSmall', local_dir=sense_dir)
            except ImportError:
                log("modelscope not installed. Using huggingface fallback...")
                from huggingface_hub import snapshot_download
                snapshot_download(repo_id='iic/SenseVoiceSmall', local_dir=sense_dir)
        else:
            log("SenseVoiceSmall model present.")

    # 0. Install Llama-cpp-python with CUDA support (WINDOWS/LINUX ONLY)
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
                    log("Installing llama-cpp-python binary wheel (CUDA 12.4)...")
                    cmd += ["--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/cu124"]
                else:
                    log("Installing llama-cpp-python (CPU-only)...")
                
                cmd += [
                    "--no-input",
                    "--no-cache-dir",
                    "--force-reinstall",
                    "--only-binary=:all:",
                    "--no-deps"
                ]
                
                subprocess.check_call(cmd, env=env)
                log("llama-cpp-python installed successfully.")
            except subprocess.CalledProcessError as e:
                log(f"CRITICAL: Failed to install llama-cpp-python: {e}")
                pass
            
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError:
        log("Error: huggingface_hub not installed in environment.")
        sys.exit(1)

    # 1. Grammar Model (Llama)
    if is_mac:
        # macOS uses MLX, meaning we need the whole repo snapshot, not just a .gguf file
        # Default MLX Llama 3.2 3B Repo
        mlx_repo = "mlx-community/Llama-3.2-3B-Instruct-4bit"
        mac_target_dir = os.path.join(models_dir, "mlx-llama-3.2")
        
        # Simple check if model exists
        if not os.path.exists(os.path.join(mac_target_dir, "model.safetensors")):
            log(f"Downloading MLX Grammar Model ({mlx_repo}) for macOS...")
            snapshot_download(repo_id=mlx_repo, local_dir=mac_target_dir)
        else:
            log(f"MLX Grammar Model {mlx_repo} present.")
    else:
        # Windows/Linux uses single GGUF file
        if not os.path.exists(os.path.join(models_dir, grammar_file)):
            log(f"Downloading Grammar Model ({grammar_file})...")
            hf_hub_download(repo_id=grammar_repo, filename=grammar_file, local_dir=models_dir)
        else:
            log(f"Grammar Model {grammar_file} present.")

    # 2. Whisper Model (Faster-Whisper Format)
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
    critical_files = ["model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"]
    needs_download = False
    
    if existing_repo != whisper_repo:
            needs_download = True
            if os.path.exists(whisper_target):
                log(f"Repository mismatch ({existing_repo} vs {whisper_repo}). Clearing old model data...")
                try:
                    shutil.rmtree(whisper_target)
                    os.makedirs(whisper_target)
                except: pass
    
    if not os.path.exists(whisper_target):
        needs_download = True
    else:
        for f in critical_files:
            if not os.path.exists(os.path.join(whisper_target, f)):
                needs_download = True
                break
                
    if needs_download:
        log(f"Downloading Whisper Model ({whisper_model_name}) from {whisper_repo}...")
        snapshot_download(
            repo_id=whisper_repo, 
            local_dir=whisper_target,
            local_dir_use_symlinks=False
        )
        # Save the repo tag so we don't redownload again if successful
        try:
            with open(repo_tag_file, "w") as f:
                f.write(whisper_repo)
        except: pass
        
    log("Model downloads complete.")

if __name__ == "__main__":
    main()
