import sys
import os

# --- 0. Hard Environment Isolation (MUST BE FIRST) ---
os.environ["PYTHONNOUSERSITE"] = "1"
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import site
site.ENABLE_USER_SITE = False

import logging
import threading
import queue
import time
import json
import re
import importlib.util
import hashlib
import gc
import concurrent.futures
import subprocess
from datetime import datetime, timedelta
import models_config
from huggingface_hub import HfApi
import platform
from tqdm.auto import tqdm as base_tqdm

IS_MAC = (sys.platform == 'darwin' or platform.system() == 'Darwin')
IS_WIN = (sys.platform == 'win32' or platform.system() == 'Windows')
DOWNLOAD_PROGRESS_REPORTER = None


class PrivoxDownloadTqdm(base_tqdm):
    def __init__(self, *args, **kwargs):
        # huggingface_hub may pass extra metadata like `name`; tqdm doesn't need it.
        kwargs.pop("name", None)
        super().__init__(*args, **kwargs)
        self._last_report_time = 0.0
        self._last_report_n = -1
        self._report(force=True)

    def update(self, n=1):
        result = super().update(n)
        self._report()
        return result

    def close(self):
        self._report(force=True)
        return super().close()

    def display(self, *args, **kwargs):
        # The app surfaces progress in SwiftUI, so we suppress tqdm terminal redraw noise.
        return None

    def _report(self, force=False):
        global DOWNLOAD_PROGRESS_REPORTER
        if DOWNLOAD_PROGRESS_REPORTER is None:
            return

        now = time.time()
        if not force and self.n == self._last_report_n and (now - self._last_report_time) < 0.25:
            return

        progress = None
        if self.total and self.total > 0:
            progress = max(0.0, min(1.0, float(self.n) / float(self.total)))

        description = (self.desc or "Downloading models").replace("\n", " ").strip()
        DOWNLOAD_PROGRESS_REPORTER(progress, description)
        self._last_report_time = now
        self._last_report_n = self.n

if IS_MAC:
    try:
        # Pre-import MLX on the MAIN THREAD to prevent silent deadlocks 
        # when wake-up logic initializes it from a background ThreadPoolExecutor later.
        import mlx_whisper
        import mlx.core as mx
    except ImportError:
        pass


if IS_WIN:
    import winreg
    import ctypes
    from ctypes import wintypes

def setup_logging():
    # Determine BASE_DIR early
    if getattr(sys, 'frozen', False):
        # We want the log to be in the same folder as the app for portability/custom paths
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    if not os.path.exists(base_dir):
        try: os.makedirs(base_dir, exist_ok=True)
        except: pass

    # Configure logging to always write to file in AppData
    log_file = os.path.join(base_dir, 'privox_app.log')
    log_level = logging.INFO
    log_format = '%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s'
    log_datefmt = '%Y-%m-%d %H:%M:%S'

    logging.basicConfig(
        format=log_format,
        datefmt=log_datefmt,
        level=log_level,
        force=True,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout) if sys.stdout else logging.NullHandler()
        ]
    )
    
    # Redirect stdout/stderr
    class LoggerWriter:
        def __init__(self, level):
            self.level = level
        def write(self, message):
            if message.strip():
                self.level(message.strip())
        def flush(self):
            pass

    sys.stdout = LoggerWriter(logging.info)
    sys.stderr = LoggerWriter(logging.error)

# Silence noisy external loggers
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

# Initialize logging IMMEDIATELY to catch import errors
setup_logging()

def log_print(msg, **kwargs):
    # Only print to stdout. sys.stdout is already redirected to logging.info
    # This prevents duplicate log entries.
    print(msg, **kwargs)

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        
        if sys.platform == "darwin" and getattr(sys, 'frozen', False):
            # PyInstaller macOS .app bundles place resources in Contents/Resources
            app_contents = os.path.dirname(os.path.dirname(sys.executable))
            res_path = os.path.join(app_contents, "Resources")
            if os.path.exists(os.path.join(res_path, relative_path)):
                return os.path.join(res_path, relative_path)
                
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

log_print("Starting Privox...")

# --- 1. System Diagnostics & Path Prioritization ---
try:
    import sys
    import os
    import logging
    
    # We MUST ensure standard libraries are reachable BEFORE we clobber sys.path
    log_print(f"System Diagnostic - Python Interpreter: {sys.executable}")
    log_print(f"System Diagnostic - sys.prefix: {sys.prefix}")
    
    # Check for core modules
    try:
        import timeit
        import json
        import re
        log_print("System Diagnostic - Standard libraries verified.")
    except ImportError as e:
        log_print(f"CRITICAL SYSTEM ERROR: Standard library missing: {e}")
        # If standard libs are missing, something is wrong with the Python install.
        # We'll try to add the default Lib paths if we can guess them.
        lib_path = os.path.join(sys.prefix, "Lib")
        if os.path.exists(lib_path) and lib_path not in sys.path:
            sys.path.append(lib_path)
    
except Exception as e:
    print(f"Boot Error: {e}")

# Base Directory for models/libs
if getattr(sys, 'frozen', False):
    # For custom install paths, we use the EXE directory
    BASE_DIR = os.path.dirname(os.path.normpath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP_DATA_DIR = models_config.get_app_data_dir(BASE_DIR)

# Simplified Path Logic: Trust Pixi environment but handle DLLs if needed
if IS_WIN:
    # Ensure CUDA DLLs from pixi env are reachable (usually in .pixi/envs/default/bin)
    pixi_bin = os.path.join(BASE_DIR, ".pixi", "envs", "default", "bin")
    if os.path.exists(pixi_bin):
        try:
            os.add_dll_directory(pixi_bin)
            logging.info(f"Added Pixi bin to DLL directory: {pixi_bin}")
        except Exception as e:
            logging.warning(f"Failed to add Pixi bin to DLL directory: {e}")

def show_modern_error(title, message, subtext=""):
    """Shows a premium styled error dialog, falling back to ctypes if PySide6 fails."""
    try:
        from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor
        
        # Ensure a QApplication exists
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
            
        dlg = QDialog()
        dlg.setWindowTitle(title)
        dlg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        dlg.setAttribute(Qt.WA_TranslucentBackground)
        
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 18, 18, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 16px;
                color: white;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(32, 28, 32, 28)
        container_layout.setSpacing(18)
        
        # Header
        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet("font-weight: 900; color: rgba(255, 255, 255, 0.4); font-size: 10px; letter-spacing: 2px; border: none;")
        container_layout.addWidget(title_lbl)
        
        # Body
        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: 500; border: none;")
        msg_lbl.setWordWrap(True)
        container_layout.addWidget(msg_lbl)
        
        if subtext:
            sub_lbl = QLabel(subtext)
            sub_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 13px; border: none;")
            sub_lbl.setWordWrap(True)
            container_layout.addWidget(sub_lbl)
            
        # Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn = QPushButton("CLOSE")
        btn.setFixedSize(120, 42)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #000000;
                border-radius: 8px;
                font-weight: 800;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.85);
            }
        """)
        btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(btn)
        container_layout.addLayout(btn_layout)
        
        layout.addWidget(container)
        dlg.exec()
    except Exception as e:
        # Final fallback to standard Windows message box
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"{message}\n\n{subtext}", title, 0x10)

try:
    log_print("Importing core utilities...")
    log_print(f"DEBUG: sys.path is: {sys.path}")
    import wave
    import traceback
    import sounddevice as sd
    import numpy as np
    from pynput import keyboard
    import pyperclip
    from huggingface_hub import hf_hub_download, snapshot_download
    
    # Global Torch Import (Essential for multi-threaded access)
    import torch
    
    log_print(f"--- TORCH DIAGNOSTICS ---")
    log_print(f"Python Version: {sys.version}")
    log_print(f"Torch Version: {torch.__version__}")
    log_print(f"Torch Path: {getattr(torch, '__file__', 'Unknown')}")
    log_print("Importing Model components...")
    if not IS_MAC:
        from llama_cpp import Llama
    log_print("Model components import successful.")
    log_print(f"CUDA Available: {torch.cuda.is_available()}")
    log_print(f"CUDA Version: {torch.version.cuda}")
    log_print(f"CuDNN Version: {torch.backends.cudnn.version()}")
    if torch.cuda.is_available():
        log_print(f"Current Device: {torch.cuda.get_device_name(0)}")
    else:
        log_print("CUDA NOT AVAILABLE. Possible reasons:")
        log_print("1. CPU version of Torch installed (check version above)")
        log_print("2. Missing CUDA DLLs in PATH")
        log_print("3. GPU driver issues")
    log_print(f"-------------------------")
    
    # Windows Sound
    try:
        import winsound
    except ImportError:
        winsound = None
    
    log_print("Core imports successful.")
except Exception as e:
    import traceback
    err_stack = traceback.format_exc()
    log_print(f"CRITICAL UTILITY IMPORT ERROR: {e}")
    log_print(err_stack)
    if IS_WIN:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, f"Privox Import Error:\n\n{e}\n\nTraceback:\n{err_stack[:500]}...", "Privox Fatal Error", 0x10)
    else:
        show_modern_error("Privox Fatal Error", str(e), f"Traceback:\n{err_stack[:500]}...")
    sys.exit(1)

# --- 2. Programmatic Console Hiding (Fail-safe for Windows) ---
if sys.platform == "win32":
    # If launched via python.exe (creating a console), hide it immediately.
    # This ensures that even if launched manually with python, it goes to background.
    kernel32 = ctypes.WinDLL('kernel32')
    user32 = ctypes.WinDLL('user32')
    hWnd = kernel32.GetConsoleWindow()
    if hWnd != 0:
        # Set title BEFORE hiding to ensure uninstaller can find/kill by title
        kernel32.SetConsoleTitleW("Privox_Service_Background_Engine")
        user32.ShowWindow(hWnd, 0) # 0 = SW_HIDE

# --- 3. Configuration ---
SAMPLE_RATE = 16000
BLOCK_SIZE = 512 
VAD_THRESHOLD = 0.5 
MIN_SPEECH_DURATION_MS = 250
SPEECH_PAD_MS = 500

# Models
WHISPER_SIZE = "distil-large-v3" 
WHISPER_REPO = "Systran/faster-distil-whisper-large-v3"
ASR_BACKEND = "whisper" 

# Llama 3.2 3B Instruct
GRAMMAR_REPO = "bartowski/Llama-3.2-3B-Instruct-GGUF"
GRAMMAR_FILE = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"


class SoundManager:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.lock = threading.Lock()
        self.start_sound_path = "/System/Library/Sounds/Ping.aiff"
        self.stop_sound_path = "/System/Library/Sounds/Pop.aiff"
        self.error_sound_path = "/System/Library/Sounds/Basso.aiff"

    def _play_windows_beep(self, freq, duration):
        if winsound is None:
            return
        winsound.Beep(freq, duration)

    def _play_mac_sound(self, sound_path):
        if not sound_path or not os.path.exists(sound_path):
            return
        subprocess.run(
            ["afplay", sound_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )

    def _play(self, freq=None, duration=None, sound_path=None):
        if self.enabled:
            try:
                with self.lock:
                    if IS_WIN:
                        self._play_windows_beep(freq, duration)
                    elif IS_MAC:
                        self._play_mac_sound(sound_path)
            except Exception as e:
                log_print(f"Sound Error: {e}")

    def play_start(self):
        if self.enabled:
            threading.Thread(
                target=self._play,
                kwargs={"freq": 1000, "duration": 200, "sound_path": self.start_sound_path},
                daemon=True
            ).start()

    def play_stop(self):
        if self.enabled:
            threading.Thread(
                target=self._play,
                kwargs={"freq": 750, "duration": 200, "sound_path": self.stop_sound_path},
                daemon=True
            ).start()

    def play_error(self):
        if self.enabled:
            threading.Thread(
                target=self._play,
                kwargs={"freq": 400, "duration": 500, "sound_path": self.error_sound_path},
                daemon=True
            ).start()


# --- Persona & Tone Logic (Moved to models_config.py) ---
# Dictionaries CHARACTER_LENSES and TONE_OVERLAYS are now imported from models_config.

class GrammarChecker:
    _llama_imported = False  # Class-level flag to avoid redundant imports/diagnostics
    _Llama = None            # Cached Llama class reference

    def __init__(self, refiner_profile=None, custom_dictionary=None, custom_prompts=None, command_prompt=None, character=None, tone=None):
        self.model = None
        self.profile = refiner_profile or {}
        self.custom_dictionary = custom_dictionary or []
        self.custom_prompts = custom_prompts or {}
        self.loading_error = None
        self.command_prompt = command_prompt
        self.character = character or "Writing Assistant"
        self.tone = tone or "Natural"
        self.icon = None # Placeholder
        self.context_buffer = "" # Max 2000 chars of conversation history
        self._has_loaded_once = False  # Instance-level: tracks if we've loaded before (for verbose control)

    def get_mlx_target_dir(self, repo_id=None):
        repo_id = repo_id or self.profile.get("mlx_repo")
        if not repo_id:
            return None
        repo_folder_name = repo_id.split("/")[-1]
        return os.path.join(APP_DATA_DIR, "models", repo_folder_name)

    def is_mlx_model_dir_ready(self, target_dir):
        if not target_dir or not os.path.isdir(target_dir):
            return False

        try:
            dir_entries = os.listdir(target_dir)
        except Exception:
            return False

        has_weights = any(entry.endswith(".safetensors") for entry in dir_entries)
        has_config = os.path.exists(os.path.join(target_dir, "config.json"))
        has_tokenizer = (
            os.path.exists(os.path.join(target_dir, "tokenizer.json")) or
            os.path.exists(os.path.join(target_dir, "tokenizer_config.json"))
        )
        return has_weights and has_config and has_tokenizer

    def resolve_local_mlx_model_dir(self, repo_id=None):
        repo_id = repo_id or self.profile.get("mlx_repo")
        if not repo_id:
            return None

        repo_folder_name = repo_id.split("/")[-1]
        candidates = [
            os.path.join(APP_DATA_DIR, "models", repo_folder_name),
            os.path.join(BASE_DIR, "models", repo_folder_name),
        ]

        for candidate in candidates:
            if self.is_mlx_model_dir_ready(candidate):
                return candidate
        return None

    def ensure_mlx_model_available(self, download_if_missing=True):
        mlx_repo = self.profile.get("mlx_repo")
        if not mlx_repo:
            self.loading_error = "No MLX repo defined for this refiner."
            return None

        resolved_dir = self.resolve_local_mlx_model_dir(repo_id=mlx_repo)
        if resolved_dir:
            return resolved_dir

        if not download_if_missing:
            return None

        target_dir = self.get_mlx_target_dir(repo_id=mlx_repo)
        if not target_dir:
            raise RuntimeError("MLX LLM target directory could not be determined.")

        os.makedirs(target_dir, exist_ok=True)
        log_print(f"MLX Grammar model missing locally. Downloading {mlx_repo} to {target_dir}...")
        snapshot_download(
            repo_id=mlx_repo,
            local_dir=target_dir,
            tqdm_class=PrivoxDownloadTqdm
        )

        repo_tag_file = os.path.join(target_dir, ".repo_id")
        try:
            with open(repo_tag_file, "w", encoding="utf-8") as f:
                f.write(mlx_repo)
        except Exception:
            pass

        if not self.is_mlx_model_dir_ready(target_dir):
            raise RuntimeError(f"MLX Grammar model download completed but required files are missing in {target_dir}")

        return target_dir

    def load_model(self):
        if self.model:
            return True

        repo_id = self.profile.get("repo_id", GRAMMAR_REPO)
        file_name = self.profile.get("file_name", GRAMMAR_FILE)
        is_reload = self._has_loaded_once  # True on wake-from-idle, False on first boot

        if IS_MAC:
            # --- macOS MLX Execution Path ---
            mlx_repo = self.profile.get("mlx_repo")
            if not mlx_repo:
                self.loading_error = f"No MLX repo defined for {file_name}. Unsupported on Mac."
                log_print(self.loading_error)
                return False

            try:
                mlx_target_dir = self.ensure_mlx_model_available(download_if_missing=True)
                log_print("Importing Apple MLX framework...")
                import mlx.core as mx
                from mlx_lm import load, generate
                
                log_print(f"Loading MLX Model from {mlx_target_dir} into Unified Memory...")
                self.model, self.tokenizer = load(mlx_target_dir)
                log_print("MLX Model Loaded Successfully. (Using Apple Silicon Acceleration)")
                self.mlx_generate = generate
            except Exception as e:
                err_trace = traceback.format_exc()
                log_print(f"\nCRITICAL: Failed to load MLX Model: {e}\n{err_trace}")
                self.loading_error = str(e)
                if self.icon:
                     self.icon.notify(f"MLX Error: {e}", "Privox Error")
                return False
            return True
            
        # --- Windows/Linux Llama Context Execution Path ---

        # 1. Check Local "models" folder (Priority: AppData, Fallback: BaseDir)
        local_model_path = os.path.join(APP_DATA_DIR, "models", file_name)
        if not os.path.exists(local_model_path):
             local_model_path = os.path.join(BASE_DIR, "models", file_name)

        if os.path.exists(local_model_path):
            if not is_reload:
                log_print(f"Found local model: {local_model_path}")
            model_path = local_model_path
        else:
            try:
                # Check/Download from Hugging Face
                log_print(f"Checking Hugging Face for Refiner Model ({repo_id})...")
                
                from huggingface_hub import hf_hub_download
                try:
                    model_path = hf_hub_download(
                        repo_id=repo_id, 
                        filename=file_name, 
                        local_files_only=True
                    )
                    log_print(f"Found in Hugging Face cache: {model_path}")
                except Exception:
                    log_print(f"Model not in cache. Downloading {file_name} from {repo_id}...")
                    local_dir = os.path.join(APP_DATA_DIR, "models")
                    if not os.path.exists(local_dir):
                        os.makedirs(local_dir, exist_ok=True)
                    
                    model_path = hf_hub_download(
                        repo_id=repo_id, 
                        filename=file_name,
                        local_dir=local_dir,
                        local_dir_use_symlinks=False
                    )
                    log_print(f"Download complete: {model_path}")
                
                # Verify file integrity
                if os.path.exists(model_path):
                    f_size = os.path.getsize(model_path)
                    log_print(f"Model file verified: {model_path} ({f_size / 1024**2:.2f} MB)")
                    if f_size < 100 * 1024**2: 
                         log_print("WARNING: Model file seems too small. Moving to backup/re-download.")
                         os.rename(model_path, model_path + ".bak")
                         return self.load_model() # Recursive retry
            except Exception as e:
                log_print(f"\nCRITICAL: Failed to download/locate model: {e}")
                self.loading_error = f"Download Failed: {e}"
                if self.icon:
                     self.icon.notify(f"Error: Could not download refiner ({file_name}). Check internet or place in 'models' folder.", "Privox Error")
                return False

        try:
            # --- Optimization 2: Cache llama_cpp import, skip diagnostics on reload ---
            if not GrammarChecker._llama_imported:
                log_print("Importing llama_cpp...")
                try:
                    import llama_cpp
                    log_print(f"llama-cpp-python Version: {getattr(llama_cpp, '__version__', 'Unknown')}")
                    sys_info = llama_cpp.llama_print_system_info()
                    log_print(f"llama-cpp-python System Info: {sys_info}")
                    if "CUDA = 1" in str(sys_info) or "BLAS = 1" in str(sys_info):
                        log_print("GPU Backend detected in llama-cpp-python.")
                    else:
                        log_print("WARNING: llama-cpp-python appears to be CPU-ONLY.")
                except ImportError as ie:
                    log_print(f"CRITICAL: Failed to import llama_cpp: {ie}")
                    raise ie
                
                from llama_cpp import Llama
                GrammarChecker._Llama = Llama
                GrammarChecker._llama_imported = True
            
            Llama = GrammarChecker._Llama
            use_verbose = not is_reload

            def _safe_llama_init(m_path, n_gpu):
                try:
                    return Llama(
                        model_path=m_path,
                        n_ctx=4096,
                        n_gpu_layers=-1,
                        verbose=use_verbose,
                        n_threads=os.cpu_count() // 2 if os.cpu_count() else 4
                    )
                except (AssertionError, RuntimeError) as e:
                    log_print(f"CRITICAL: Llama initialization failed ({type(e).__name__}). File likely corrupt.")
                    if os.path.exists(m_path):
                        size_mb = os.path.getsize(m_path) / (1024 * 1024)
                        log_print(f"Removing corrupt model file: {m_path} ({size_mb:.1f} MB)")
                        try: os.remove(m_path)
                        except: pass
                    return None

            is_gpu = torch.cuda.is_available()
            n_gpu = 99 if is_gpu else 0
            
            log_print(f"Loading Llama (GPU={is_gpu}, layers={n_gpu}){'  [Quick Reload]' if is_reload else ''}...")
            self.model = _safe_llama_init(model_path, n_gpu)
            
            if self.model is None:
                log_print("Model file removed. Restarting load sequence to trigger redownload...")
                return self.load_model()

            self._has_loaded_once = True
            log_print(f"Done. (GPU Acceleration: {'ENABLED' if is_gpu else 'DISABLED'})")
            return True
        except Exception as e:
            err_trace = traceback.format_exc()
            log_print(f"\nError loading Grammar Model: {e}\n{err_trace}")
            self.loading_error = str(e)
            
            if "AssertionError" in str(e):
                 log_print(f"Corruption detected in fallback. Removing {model_path} and retrying.")
                 try:
                    if os.path.exists(model_path):
                        os.remove(model_path)
                 except: pass
                 return self.load_model()

            if IS_WIN:
                 show_modern_error("Privox Model Error", f"Error loading Grammar Model (Llama): {e}", f"Traceback:\n{err_trace[:500]}")
            return False

    def get_effective_prompt(self, language=None, language_prob=0.0, user_text=None):
        """Constructs a composite prompt with hidden overrides.
        Layer 1: Core Safety/Format (Hidden)
        Layer 2: User Instructions (Visible in GUI)
        Layer 3: Late-Binding Overrides (Hidden, conditional)
        """
        directive = "REFINE TRANSCRIPT: Provide a clean, accurate version of the ASR input in its ORIGINAL LANGUAGE."
        
        # Language Hinting (Robust Multilingual Support)
        if language and language != "en" and language_prob > 0.4:
            lang_name = models_config.ISO_LANGUAGE_MAP.get(language, language)
            directive = f"REFINE TRANSCRIPT: PROVIDE A CLEAN {lang_name.upper()} VERSION. DO NOT TRANSLATE TO ENGLISH."

        # NEW: Inject direct formatting instruction right to the core directive layer
        directive += "\nCRITICAL FORMATTING: Whenever the user dictates a list, sequence of items, or steps, you MUST format your output as a clear bulleted or numbered list. Add paragraphs where logical."

        prompt_directive = f"{directive}\n\n{models_config.CRITICAL_RULES}"
        
        # Layer 2: User-Edited Instructions
        if user_text:
            prompt_directive += f"\n### ADDITIONAL USER INSTRUCTIONS ###\n{user_text}\n"

        # Jargon Injection
        dict_str = ", ".join(self.custom_dictionary)
        if dict_str:
            prompt_directive += f"\n### JARGON/HINTS (PRIORITY) ###\nSpecific Jargon/Hints to recognize: {dict_str}\n"

        # Layer 3: Late-Binding Overrides (Ensures Dropdown Priority)
        overrides = ""
        if self.character != "Custom":
            lens = models_config.CHARACTER_LENSES.get(self.character, "")
            if lens:
                overrides += f"\n[STRICT IDENTITY OVERRIDE]: {lens}"
        
        if self.tone != "Custom":
            overlay = models_config.TONE_OVERLAYS.get(self.tone, "")
            if overlay:
                overrides += f"\n[STRICT STYLE OVERRIDE]: {overlay}"
        
        if overrides:
            prompt_directive += f"\n### SYSTEM OVERRIDES (HIGHEST PRIORITY) ###{overrides}\n"

        return prompt_directive

    def _looks_like_structured_dictation(self, text):
        if not text:
            return False

        normalized = text.lower()
        structure_markers = [
            "list", "bullet", "numbered", "steps", "step one", "step two",
            "first", "second", "third", "next", "finally"
        ]
        if any(marker in normalized for marker in structure_markers):
            return True

        if text.count(",") >= 2 and (" and " in normalized or " then " in normalized):
            return True

        return False

    def _should_use_compact_formatter(self, clean_text, user_text):
        if not clean_text:
            return True
        if user_text and user_text.strip():
            return False
        if self._looks_like_structured_dictation(clean_text):
            return False
        return len(clean_text) <= 280

    def _should_fast_path_refine(self, clean_text, user_text):
        if not clean_text:
            return False
        if user_text and user_text.strip():
            return False
        if self.custom_dictionary:
            return False
        if self.character != "Writing Assistant" or self.tone != "Natural":
            return False
        if self._looks_like_structured_dictation(clean_text):
            return False
        if "\n" in clean_text or len(clean_text) > 48:
            return False
        if len(clean_text.split()) > 10:
            return False
        return True

    def _fast_path_cleanup(self, text):
        normalized = re.sub(r'\s+', ' ', text or '').strip()
        if not normalized:
            return text

        normalized = re.sub(r'\bi\b', 'I', normalized)
        if normalized and normalized[0].islower():
            normalized = normalized[0].upper() + normalized[1:]
        if normalized[-1].isalnum():
            normalized += "."
        return normalized

    def correct(self, text, is_command=False, language=None, language_prob=0.0, user_text=None):
        clean_text = text.strip()
        if not self.model or not clean_text:
            return text
            
        if len(clean_text) < 8 and clean_text.lower() not in [d.lower() for d in self.custom_dictionary]:
            log_print(f" [Short Input Skip] Input too short ({len(clean_text)} chars). Mirroring.")
            return text

        try:
            prompt_type = self.profile.get("prompt_type", "llama")
            use_compact_formatter = False

            if is_command:
                system_prompt = self.command_prompt or (
                    "You are Privox, an intelligent assistant. Execute the user's instruction perfectly. "
                    "Output ONLY the result inside <refined> and </refined> tags. Do not chat."
                )
                user_content = text
            else:
                # Resolve Custom Instruction if not explicitly provided
                if not user_text and hasattr(self, 'custom_prompts'):
                    prompt_key = f"{self.character}|{self.tone}"
                    user_text = self.custom_prompts.get(prompt_key, "")

                if self._should_fast_path_refine(clean_text, user_text):
                    log_print(f" [Fast Refine Path] Skipping LLM for simple short dictation ({len(clean_text)} chars).")
                    return self._fast_path_cleanup(text)

                core_directive = self.get_effective_prompt(language=language, language_prob=language_prob, user_text=user_text)
                use_compact_formatter = self._should_use_compact_formatter(clean_text, user_text)
                system_prompt = models_config.get_system_formatter(
                    language=language,
                    prompt_type=prompt_type,
                    compact=use_compact_formatter
                )
                user_content = f"[Core Directive]: {core_directive}\n[Transcript]: {text}\nOutput: "

            # Format based on model type
            if prompt_type == "t5":
                action = "Polish" if self.tone != "Natural" else "Fix grammar"
                prompt = f"{action}: {text}"
                stop_tokens = ["\n"]
            elif prompt_type == "chatml":
                system_prompt += (
                    "\nTHINKING MODE IS DISABLED. Do not output <think> tags, internal reasoning, "
                    "or analysis. Return only the final answer inside <refined> tags."
                )
                user_content = f"/no_think\n{user_content}"
                prompt = (
                    f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                    f"<|im_start|>user\n{user_content}<|im_end|>\n"
                    "<|im_start|>assistant\n"
                )
                stop_tokens = ["<|im_end|>"]
            else:
                prompt = (
                    f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|>"
                    f"<|start_header_id|>user<|end_header_id|>\n\n{user_content}<|eot_id|>"
                    "<|start_header_id|>assistant<|end_header_id|>\n\n"
                )
                stop_tokens = ["<|eot_id|>"]
            
            # 2. Proportional max_tokens cap to prevent runaway generation
            input_tokens_est = max(len(clean_text) // 3, len(clean_text.split()))
            if IS_MAC:
                if prompt_type == "chatml":
                    max_tokens = min(96 if use_compact_formatter else 128, max(24, input_tokens_est))
                else:
                    max_tokens = min(96 if use_compact_formatter else 144, max(32, int(input_tokens_est * 1.5)))
            else:
                max_tokens = min(2048, max(128, input_tokens_est * 4))

            log_print(
                f" Refiner prompt mode: {'compact' if use_compact_formatter else 'full'} "
                f"(prompt_type={prompt_type}, prompt_chars={len(system_prompt) + len(user_content)}, max_tokens={max_tokens})"
            )

            if IS_MAC:
                # --- MLX Execution ---
                output = self.mlx_generate(
                    self.model, 
                    self.tokenizer, 
                    prompt=prompt, 
                    max_tokens=max_tokens,
                    verbose=False
                )
                raw_response = output.strip()
            else:
                # --- Windows Llama CPP Execution ---
                output = self.model(
                    prompt, 
                    max_tokens=max_tokens,
                    stop=stop_tokens, 
                    echo=False,
                    temperature=0.4,     # Increased from 0.3 to reduce determinism
                    repeat_penalty=1.2,  # Prevents token-level loops
                    frequency_penalty=0.5, # Specifically discourages character repetition
                    top_p=0.9,
                    min_p=0.01,
                )
                raw_response = output['choices'][0]['text'].strip()
            
            # Diagnostic Log
            if raw_response:
                log_print(f" LLM Raw Response (len={len(raw_response)}): '{raw_response[:100]}...'")
            else:
                log_print(" Warning: LLM returned empty response.")
                
            if prompt_type == "t5":
                return raw_response

            # Qwen-family chat models may still emit internal reasoning blocks.
            raw_response = self._strip_thinking_blocks(raw_response)

            # Extract text purely from inside the <refined> tags 
            import re
            match = re.search(r'<refined>(.*?)</refined>', raw_response, flags=re.DOTALL | re.IGNORECASE)
            
            result = None
            if match:
                log_print(" Regex extracted <refined> block successfully.")
                result = match.group(1).strip()
            else:
                # Fallback if the model hallucinated and forgot the tags.
                log_print(" Warning: Model failed to use <refined> tags.")
                
                # Sub-fallback: If the model echoed the prompt, try to strip it
                # (Sometimes models fail to follow 'echo=False' or the prompt structure confuses them)
                if "[Transcript]:" in raw_response:
                    log_print("  Detected prompt echo in raw response. Attempting to strip...")
                    parts = re.split(r'\[Transcript\]:.*?\n', raw_response, flags=re.DOTALL | re.IGNORECASE)
                    if len(parts) > 1:
                        result = parts[-1].strip()
                        log_print(f"  Stripped echo. New candidate length: {len(result)}")
                    else:
                        result = raw_response
                else:
                    result = raw_response

            # Post-processing
            result = self._strip_meta_commentary(result)
            result = self._validate_output(clean_text, result)

            return result
        except Exception as e:
            log_print(f"Grammar Check Error: {e}")
            return text

    # --- LLM self-commentary patterns that get embedded inside <refined> output ---
    _META_COMMENTARY_PATTERNS = [
        "\nnote:", "\nnote -", "\nnotes:",
        "\nplease note", "\np.s.", "\nps:",
        "\ni've preserved", "\ni have preserved",
        "\ni've maintained", "\ni have maintained",
        "\ni've replaced", "\ni have replaced",
        "\ni've improved", "\ni have improved",
        "\ni've also", "\ni also",
        "\ni've ensured", "\ni have ensured",
        "\nspecifically,",
        "\nadditionally,",
        "\nin this version",
        "\nchanges made:",
        "\nexplanation:",
    ]

    def _strip_meta_commentary(self, text):
        """Remove trailing LLM self-commentary that leaks inside <refined> tags."""
        if not text:
            return text

        text_lower = text.lower()
        earliest_cut = len(text)

        for pattern in self._META_COMMENTARY_PATTERNS:
            idx = text_lower.find(pattern)
            if idx > 0 and idx < earliest_cut:
                earliest_cut = idx

        if earliest_cut < len(text):
            stripped = text[:earliest_cut].rstrip()
            log_print(f" [Meta-Commentary Strip] Removed {len(text) - earliest_cut} chars of LLM self-commentary.")
            return stripped

        return text

    def _strip_thinking_blocks(self, text):
        """Remove leaked Qwen thinking blocks before we parse the answer."""
        if not text:
            return text

        stripped = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
        if stripped != text:
            log_print(f" [Thinking Strip] Removed {len(text) - len(stripped)} chars of leaked reasoning.")
            return stripped

        # Some Qwen responses stream an opening <think> block without a closing tag.
        if text.lstrip().lower().startswith("<think>"):
            split_match = re.search(r'</think>\s*', text, flags=re.IGNORECASE)
            if split_match:
                candidate = text[split_match.end():].strip()
                log_print(" [Thinking Strip] Removed prefixed <think> block.")
                return candidate

            log_print(" [Thinking Strip] Response contains only leaked reasoning. Reverting to empty candidate.")
            return ""

        return text

    # --- Prompt-echo fingerprints (substrings the LLM may regurgitate) ---
    _PROMPT_FINGERPRINTS = [
        "core directive",
        "strict identity override",
        "strict style override",
        "additional user instructions",
        "previous context",
        "fix grammar",
        "no hallucination",
        "maintain the speaker's original cadence",
    ]

    def _validate_output(self, original_text, refined_text):
        """Final sanity check to detect and fix hallucinations or echo loops."""
        if not refined_text:
            return original_text
            
        # 1. Detect prompt leakage (LLM echoeing its instructions)
        ref_lower = refined_text.lower()
        if "<think>" in ref_lower or ref_lower.startswith("okay, let's") or ref_lower.startswith("okay, the user"):
            log_print(" [Hallucination Guard] Detected leaked reasoning content. Reverting to original.")
            return original_text
        for finger in self._PROMPT_FINGERPRINTS:
            if finger in ref_lower and len(refined_text) > len(original_text) * 2:
                log_print(f" [Hallucination Guard] Detected prompt fingerprint '{finger}'. Reverting to original.")
                return original_text

        # 2. Detect extreme length mismatch (hallucinated story-telling)
        if len(refined_text) > len(original_text) * 4 and len(original_text) > 30:
            log_print(" [Hallucination Guard] Extreme length mismatch detected. Reverting to original.")
            return original_text

        # 3. Detect repetitive loops (e.g. "I have, I have, I have...")
        if len(refined_text) > 50:
            words = refined_text.split()
            # If a single word or 2-word phrase makes up > 40% of the output
            if len(words) > 10:
                from collections import Counter
                counts = Counter(words)
                top_word, top_count = counts.most_common(1)[0]
                if top_count / len(words) > 0.4:
                    log_print(f" [Hallucination Guard] Detected word loop ('{top_word}'). Reverting.")
                    return original_text

        return refined_text
    def unload_model(self):
        if self.model:
            del self.model
            self.model = None
            log_print("Grammar Model Unloaded.")

class VoiceInputApp:
    def __init__(self, headless=False):
        global DOWNLOAD_PROGRESS_REPORTER
        self.headless = headless
        self.running = True
        self.mic_active = False
        log_print("Initializing Voice Input Application...")
        
        self.keyboard_controller = keyboard.Controller()
        
        # Load Config
        self.hotkey = keyboard.Key.space # Default
        self.sound_enabled = True
        self.auto_stop_enabled = True
        self.silence_timeout_ms = 10000
        self.custom_dictionary = []
        self.custom_prompts = {}
        self.character = "Writing Assistant"
        self.tone = "Natural"
        self.paste_delay_seconds = 0
        self.current_refiner = ""
        self.dictation_prompt = None
        self.command_prompt = None
        self.active_mlx_repo = None
        self.active_whisper_repo = None
        
        self.sound_manager = SoundManager(self.sound_enabled)
        
        # State
        self.q = queue.Queue()
        self.audio_buffer = [] 
        self.is_listening = False
        self.is_speaking = False
        self.stream = None
        self.audio_stream_lock = threading.Lock()
        
        self.models_ready = False
        self.loading_status = "Initializing..."
        self.ui_state = "LOADING"
        
        # Initialize Placeholders
        self.grammar_checker = GrammarChecker(
            custom_dictionary=self.custom_dictionary, 
            custom_prompts=self.custom_prompts,
            command_prompt=self.command_prompt,
            character=self.character,
            tone=self.tone
        )
        self.grammar_checker.icon = None # Will assign later
        self.vad_model = None
        self.asr_model = None
        self.vad_iterator = None
        self.mlx_asr_local_path = None
        self.mlx_asr_warmed = False
        self.mlx_qwen_asr_local_path = None
        
        # Tray Icon (placeholder)
        self.icon = None

        # VRAM Saver State
        self.last_activity_time = time.time()
        self.heavy_models_loaded = False
        self.model_lock = threading.Lock()
        self.vram_timeout = 300 # Seconds before unloading
        self.pending_wakeup = False # Auto-start recording after loading?
        self.model_reload_requested = False
        
        # Hotkey support
        self.hotkey_str = "ctrl+shift+space"
        self.target_mods = {"ctrl", "shift"} # e.g. {'ctrl', 'shift'}
        self.target_key = "space"
        self.active_mods = set()
        self.settings_process = None
        self.last_toggle_time = 0 # Hotkey de-bounce timer
        self.last_config_reload_time = 0 # Cooldown for config polling
        self._last_prefs_hash = None # Hash-based change detection
        self.last_mic_retry_time = 0
        self.mic_retry_interval = 5.0
        DOWNLOAD_PROGRESS_REPORTER = self.emit_download_progress
        
        # Load Config (FINAL STEP of init to prevent overwriting by defaults)
        self.load_config()

        self.loading_status = "Loading VAD..."
        self.load_vad()
        
        # Set initial state to show loading spinner
        self.update_status("INITIALIZING")

        # Start loading threads
        threading.Thread(target=self.initial_load, daemon=True).start()

    def initial_load(self):
        # Run model cleanup FIRST to avoid race conditions with loading
        try:
            prefs_path = os.path.join(APP_DATA_DIR, ".user_prefs.json")
            if os.path.exists(prefs_path):
                with open(prefs_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
                cleanup_days = prefs.get("model_cleanup_days", 7)
                if cleanup_days > 0:
                    self.cleanup_stale_models(cleanup_days)
        except: pass

        # We load heavy models initially so it's ready for first use, 
        # then let the saver handle unloading if unused.
        self.load_heavy_models()

    def get_mlx_asr_target_dir(self, repo_id=None):
        repo_id = repo_id or self.active_mlx_repo or WHISPER_REPO
        if not repo_id:
            return None
        repo_folder_name = repo_id.split("/")[-1]
        return os.path.join(APP_DATA_DIR, "models", repo_folder_name)

    def is_mlx_asr_dir_ready(self, target_dir):
        if not target_dir or not os.path.isdir(target_dir):
            return False

        required_files = ["config.json"]
        try:
            dir_entries = os.listdir(target_dir)
        except Exception:
            return False

        has_weights = any(
            entry.endswith(".npz") or entry.endswith(".safetensors")
            for entry in dir_entries
        )
        has_required_files = all(os.path.exists(os.path.join(target_dir, file_name)) for file_name in required_files)
        # Some MLX Whisper repos use weights.npz while others ship weights.safetensors.
        # Treat tokenizer files as optional so we don't get stuck re-downloading healthy model folders.
        return has_weights and has_required_files

    def is_mlx_qwen_asr_dir_ready(self, target_dir):
        if not target_dir or not os.path.isdir(target_dir):
            return False

        try:
            dir_entries = os.listdir(target_dir)
        except Exception:
            return False

        has_weights = any(entry.endswith(".safetensors") for entry in dir_entries)
        has_config = os.path.exists(os.path.join(target_dir, "config.json"))
        has_tokenizer = (
            os.path.exists(os.path.join(target_dir, "tokenizer.json")) or
            os.path.exists(os.path.join(target_dir, "tokenizer_config.json"))
        )
        return has_weights and has_config and has_tokenizer

    def resolve_local_mlx_asr_dir(self, repo_id=None, whisper_model=None):
        repo_id = repo_id or self.active_mlx_repo or WHISPER_REPO
        whisper_model = whisper_model or WHISPER_SIZE

        candidates = []
        if repo_id:
            repo_folder_name = repo_id.split("/")[-1]
            candidates.append(os.path.join(APP_DATA_DIR, "models", repo_folder_name))
            candidates.append(os.path.join(BASE_DIR, "models", repo_folder_name))
        if self.active_whisper_repo:
            whisper_repo_folder_name = self.active_whisper_repo.split("/")[-1]
            candidates.append(os.path.join(APP_DATA_DIR, "models", whisper_repo_folder_name))
            candidates.append(os.path.join(BASE_DIR, "models", whisper_repo_folder_name))
        if whisper_model:
            candidates.append(os.path.join(BASE_DIR, "models", f"whisper-{whisper_model}"))

        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if self.is_mlx_asr_dir_ready(candidate):
                return candidate
        return None

    def resolve_local_mlx_qwen_asr_dir(self, repo_id=None):
        repo_id = repo_id or self.active_mlx_repo or WHISPER_REPO
        if not repo_id:
            return None

        repo_folder_name = repo_id.split("/")[-1]
        candidates = [
            os.path.join(APP_DATA_DIR, "models", repo_folder_name),
            os.path.join(BASE_DIR, "models", repo_folder_name),
        ]

        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if self.is_mlx_qwen_asr_dir_ready(candidate):
                return candidate
        return None

    def ensure_mlx_asr_model_available(self, download_if_missing=True):
        if not (IS_MAC and ASR_BACKEND == "whisper"):
            return None

        mlx_repo = self.active_mlx_repo or WHISPER_REPO
        resolved_dir = self.resolve_local_mlx_asr_dir(repo_id=mlx_repo)
        if resolved_dir:
            self.mlx_asr_local_path = resolved_dir
            return resolved_dir

        if not download_if_missing:
            return None

        target_dir = self.get_mlx_asr_target_dir(repo_id=mlx_repo)
        if not target_dir:
            raise RuntimeError("MLX ASR target directory could not be determined.")

        os.makedirs(target_dir, exist_ok=True)
        log_print(f"MLX-Whisper model missing locally. Downloading {mlx_repo} to {target_dir}...")
        self.update_status("DOWNLOADING")
        self.emit_download_progress(0.0, f"Preparing {mlx_repo}")
        snapshot_download(
            repo_id=mlx_repo,
            local_dir=target_dir,
            tqdm_class=PrivoxDownloadTqdm
        )

        repo_tag_file = os.path.join(target_dir, ".repo_id")
        try:
            with open(repo_tag_file, "w", encoding="utf-8") as f:
                f.write(mlx_repo)
        except Exception:
            pass

        if not self.is_mlx_asr_dir_ready(target_dir):
            raise RuntimeError(f"MLX ASR model download completed but required files are missing in {target_dir}")

        self.mlx_asr_local_path = target_dir
        self.emit_download_progress(1.0, "Model download complete")
        return target_dir

    def ensure_mlx_qwen_asr_model_available(self, download_if_missing=True):
        if not (IS_MAC and ASR_BACKEND == "mlx_qwen_asr"):
            return None

        mlx_repo = self.active_mlx_repo or WHISPER_REPO
        resolved_dir = self.resolve_local_mlx_qwen_asr_dir(repo_id=mlx_repo)
        if resolved_dir:
            self.mlx_qwen_asr_local_path = resolved_dir
            return resolved_dir

        if not download_if_missing:
            return None

        target_dir = self.get_mlx_asr_target_dir(repo_id=mlx_repo)
        if not target_dir:
            raise RuntimeError("MLX Qwen-ASR target directory could not be determined.")

        os.makedirs(target_dir, exist_ok=True)
        log_print(f"MLX Qwen-ASR model missing locally. Downloading {mlx_repo} to {target_dir}...")
        self.update_status("DOWNLOADING")
        self.emit_download_progress(0.0, f"Preparing {mlx_repo}")
        snapshot_download(
            repo_id=mlx_repo,
            local_dir=target_dir,
            tqdm_class=PrivoxDownloadTqdm
        )

        repo_tag_file = os.path.join(target_dir, ".repo_id")
        try:
            with open(repo_tag_file, "w", encoding="utf-8") as f:
                f.write(mlx_repo)
        except Exception:
            pass

        if not self.is_mlx_qwen_asr_dir_ready(target_dir):
            raise RuntimeError(f"MLX Qwen-ASR model download completed but required files are missing in {target_dir}")

        self.mlx_qwen_asr_local_path = target_dir
        self.emit_download_progress(1.0, "Model download complete")
        return target_dir

    def transcribe_with_mlx_qwen_asr(self, audio_data):
        if self.asr_model is None:
            return ""

        audio_np = audio_data.astype(np.float32)
        try:
            if hasattr(self.asr_model, "transcribe"):
                results = self.asr_model.transcribe(audio_np)
                if isinstance(results, list) and results:
                    first = results[0]
                    return (first.get("text", "") if isinstance(first, dict) else getattr(first, "text", str(first))).strip()
                if hasattr(results, "text"):
                    return str(results.text).strip()
                if isinstance(results, dict):
                    return str(results.get("text", "")).strip()
                if isinstance(results, str):
                    return results.strip()
            if hasattr(self.asr_model, "generate"):
                import mlx.core as mx
                results = self.asr_model.generate(audio=[mx.array(audio_np)])
                if hasattr(results, "text"):
                    return str(results.text).strip()
                if isinstance(results, dict):
                    return str(results.get("text", "")).strip()
                if isinstance(results, str):
                    return results.strip()
        except Exception as error:
            log_print(f" MLX Qwen-ASR Critical Error: {error}")
            return ""

        log_print(" MLX Qwen-ASR returned an unsupported response shape.")
        return ""

    def get_mlx_llm_target_dir(self, repo_id=None):
        repo_id = repo_id or self.grammar_checker.profile.get("mlx_repo")
        if not repo_id:
            return None
        repo_folder_name = repo_id.split("/")[-1]
        return os.path.join(APP_DATA_DIR, "models", repo_folder_name)

    def is_mlx_llm_dir_ready(self, target_dir):
        if not target_dir or not os.path.isdir(target_dir):
            return False

        try:
            dir_entries = os.listdir(target_dir)
        except Exception:
            return False

        has_weights = any(entry.endswith(".safetensors") for entry in dir_entries)
        has_config = os.path.exists(os.path.join(target_dir, "config.json"))
        has_tokenizer = (
            os.path.exists(os.path.join(target_dir, "tokenizer.json")) or
            os.path.exists(os.path.join(target_dir, "tokenizer_config.json"))
        )
        return has_weights and has_config and has_tokenizer

    def resolve_local_mlx_llm_dir(self, repo_id=None):
        repo_id = repo_id or self.grammar_checker.profile.get("mlx_repo")
        if not repo_id:
            return None

        repo_folder_name = repo_id.split("/")[-1]
        candidates = [
            os.path.join(APP_DATA_DIR, "models", repo_folder_name),
            os.path.join(BASE_DIR, "models", repo_folder_name),
        ]

        for candidate in candidates:
            if self.is_mlx_llm_dir_ready(candidate):
                return candidate
        return None

    def emit_download_progress(self, progress, status):
        percent = -1
        if progress is not None:
            percent = max(0, min(100, int(round(progress * 100))))
        safe_status = (status or "Downloading models").replace("|", "/")
        log_print(f"DETAIL: DOWNLOAD_PROGRESS|{percent}|{safe_status}")

    def load_vad(self):
        # 1. Load VAD Model (Silero)
        log_print("Loading Silero VAD...", end="", flush=True)
        try:
            torch.set_num_threads(1)
            if hasattr(torch, "set_num_interop_threads"):
                torch.set_num_interop_threads(1)

            # Force Torch Hub to use the local models folder for VAD
            hub_dir = os.path.join(BASE_DIR, "models", "hub")
            if not os.path.exists(hub_dir):
                os.makedirs(hub_dir, exist_ok=True)
            torch.hub.set_dir(hub_dir)

            repo_dir = os.path.join(hub_dir, "snakers4_silero-vad_master")
            if os.path.exists(os.path.join(repo_dir, "hubconf.py")):
                log_print(f"Loading Silero VAD from local cache: {repo_dir}")
                self.vad_model, utils = torch.hub.load(
                    repo_or_dir=repo_dir,
                    source='local',
                    model='silero_vad',
                    force_reload=False,
                    trust_repo=True,
                    onnx=False
                )
            else:
                log_print("Local Silero cache missing. Loading from torch.hub repository...")
                self.vad_model, utils = torch.hub.load(
                    repo_or_dir='snakers4/silero-vad',
                    model='silero_vad',
                    force_reload=False,
                    trust_repo=True,
                    onnx=False
                )
            (self.get_speech_timestamps, self.save_audio, self.read_audio, self.VADIterator, self.collect_chunks) = utils
            self.vad_iterator = self.VADIterator(self.vad_model, 
                                                 threshold=VAD_THRESHOLD, 
                                                 sampling_rate=SAMPLE_RATE, 
                                                 min_silence_duration_ms=self.silence_timeout_ms, 
                                                 speech_pad_ms=SPEECH_PAD_MS)
            log_print("Done.")
        except Exception as e:
            log_print(f"\nError loading VAD: {e}")
            self.loading_status = "Error Loading VAD"
            if not self.headless:
                self.update_tray_tooltip()
            return

    def load_heavy_models(self):
        """Concurrent loading of ASR and Grammar models to minimize wake-up latency."""
        with self.model_lock:
            if self.heavy_models_loaded:
                return

            log_print("Loading Heavy Models (Wake up)...")
            self.loading_status = "Loading Models..."
            if not self.headless:
                self.update_tray_tooltip()

            def load_grammar():
                try:
                    success = self.grammar_checker.load_model()
                    if success:
                        # Track LLM usage here
                        self.track_model_usage(self.current_refiner)
                    return success
                except Exception as e:
                    log_print(f"Parallel Load Error (Grammar): {e}")
                    return False

            def load_asr():
                try:
                    is_gpu = torch.cuda.is_available()
                    device_str = "cuda" if is_gpu else "cpu"
                    
                    if ASR_BACKEND == "sensevoice":
                        sense_dir = os.path.join(BASE_DIR, "models", "SenseVoiceSmall")
                        log_print(f"ASR Diagnostic - Initializing SenseVoiceSmall on {device_str}...")
                        from funasr import AutoModel
                        self.asr_model = AutoModel(
                            model=sense_dir if os.path.exists(sense_dir) else "iic/SenseVoiceSmall",
                            device=device_str,
                            disable_update=True
                        )
                        log_print(f"SenseVoice initialized successfully.")
                    elif ASR_BACKEND == "qwen_asr":
                        log_print(f"ASR Diagnostic - Initializing Qwen3ASRModel ({WHISPER_REPO}) on {device_str}...")
                        from qwen_asr import Qwen3ASRModel
                        
                        is_mac_mps = IS_MAC and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()

                        # Apply memory constraint when on GPU to prevent accelerate from grabbing all VRAM 
                        # and fighting with llama.cpp already in memory.
                        if is_gpu:
                            # 12GB is typical. Let's cap transformers to a safe conservative limit like 6GB 
                            # (Qwen3-ASR 1.7B takes ~3.5GB in float16)
                            max_mem = {0: "6GiB", "cpu": "8GiB"}
                            dtype = torch.float16
                            device_map = "auto"
                        elif is_mac_mps:
                            max_mem = None
                            dtype = torch.float16
                            device_map = "mps"
                            log_print("Apple Silicon (MPS) acceleration ENABLED for Qwen-ASR.")
                        else:
                            max_mem = None
                            dtype = torch.float32
                            device_map = "cpu"

                        # Load in 16-bit based on CUDA/MPS availability with max_memory constraints
                        self.asr_model = Qwen3ASRModel.from_pretrained(
                            WHISPER_REPO,
                            device_map=device_map,
                            max_memory=max_mem,
                            dtype=dtype,
                            low_cpu_mem_usage=True,
                            local_files_only=True
                            # We deliberately OMIT forced_aligner for speed and lower VRAM
                        )
                        log_print(f"Qwen3ASRModel initialized successfully.")
                    elif ASR_BACKEND == "mlx_qwen_asr":
                        local_mlx_path = self.ensure_mlx_qwen_asr_model_available(download_if_missing=True)
                        log_print(f"ASR Diagnostic - Initializing Apple MLX Qwen-ASR from {local_mlx_path}...")
                        from mlx_audio.stt.utils import load_model as load_mlx_audio_model
                        self.asr_model = load_mlx_audio_model(local_mlx_path)
                        self.mlx_qwen_asr_local_path = local_mlx_path
                        log_print("MLX Qwen-ASR initialized successfully.")
                    elif IS_MAC:
                        # MLX-Whisper initialization on Mac
                        local_mlx_path = self.ensure_mlx_asr_model_available(download_if_missing=True)
                        log_print(f"ASR Diagnostic - Initializing Apple MLX-Whisper from {local_mlx_path}...")
                        import mlx_whisper
                        self.asr_model = mlx_whisper
                        self.mlx_asr_local_path = local_mlx_path
                        if self.mlx_asr_local_path and not self.mlx_asr_warmed:
                            log_print("Warming up MLX-Whisper with a silent startup pass...")
                            try:
                                warmup_audio = np.zeros(SAMPLE_RATE, dtype=np.float32)
                                self.asr_model.transcribe(
                                    warmup_audio,
                                    path_or_hf_repo=self.mlx_asr_local_path
                                )
                                self.mlx_asr_warmed = True
                                log_print("MLX-Whisper warm-up complete.")
                            except Exception as warmup_error:
                                log_print(f"MLX-Whisper warm-up skipped due to error: {warmup_error}")
                        log_print(f"MLX-Whisper initialized successfully.")
                    else:
                        compute_type = "float16" if is_gpu else "int8"
                        from faster_whisper import WhisperModel
                        local_whisper = os.path.join(BASE_DIR, "models", f"whisper-{WHISPER_SIZE}")
                        model_path = local_whisper if os.path.exists(os.path.join(local_whisper, "model.bin")) else WHISPER_REPO
                        log_print(f"ASR Diagnostic - Initializing WhisperModel ({WHISPER_SIZE}) on {device_str}...")
                        self.asr_model = WhisperModel(model_path, device=device_str, compute_type=compute_type)
                        log_print(f"WhisperModel initialized successfully.")
                    
                    # Track ASR model usage here instead of in load_config
                    self.track_model_usage(getattr(self, 'active_asr_name', WHISPER_SIZE))
                    return True
                except Exception as e:
                    log_print(f"Parallel Load Error (ASR): {e}")
                    self.loading_status = "Error Loading ASR"
                    return False

            # Sequential vs Parallel loading strategy
            if ASR_BACKEND == "qwen_asr":
                # Safety Mode: Qwen-ASR uses a different transformer backend. 
                # Sequential load prevents CUDA race conditions.
                log_print("Using Sequential Load Strategy (Safety Mode)...")
                res_grammar = load_grammar()
                res_asr = load_asr()
                results = [res_grammar, res_asr]
            else:
                # Performance Mode: Load Whisper + LLM in parallel
                log_print("Using Parallel Load Strategy (Performance Mode)...")
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [executor.submit(load_grammar), executor.submit(load_asr)]
                    results = [f.result() for f in futures]

            if not results[1]: # Whisper is mandatory
                log_print("CRITICAL: ASR model failed to load.")
                self.loading_status = "ASR Load Error"
                self.update_status("ERROR")
                if not self.headless:
                    self.update_tray_tooltip()
                self.pending_wakeup = False
                return

            if not results[0]:
                log_print("WARNING: Grammar model failed to load. Proceeding with ASR only.")

            self.models_ready = True
            self.heavy_models_loaded = True
            self.loading_status = "Ready" if results[0] else "ASR Only"
            self.update_status("READY")
            
            # Reset activity timer so we don't immediately unload
            self.last_activity_time = time.time()
            
            # If this was a manual F8 wakeup, we immediately start listening. 
            # Otherwise (initial load), we play the 'Ready' sound.
            if self.pending_wakeup:
                log_print("Pending Wakeup found. Auto-starting recording...")
                self.pending_wakeup = False
                # Tiny delay to ensure UI updates and avoid race conditions with sound manager
                time.sleep(0.1) 
                self.start_listening()
            elif not self.headless:
                self.sound_manager.play_start()
  

    def unload_heavy_models(self):
        with self.model_lock:
            if not self.heavy_models_loaded:
                return
            
            idle_time = time.time() - self.last_activity_time
            log_print(f"Unloading Models (VRAM Saver - Idle for {idle_time:.1f}s)...")
            self.asr_model = None
            self.grammar_checker.unload_model()
            self.grammar_checker.context_buffer = "" # Clear conversation context
            
            # Force Garbage Collection
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            self.heavy_models_loaded = False
            self.loading_status = "Idle (VRAM Free)"
            if not self.headless:
                self.update_tray_tooltip()
                self.update_status("SLEEP") # Trigger flat line animation
            log_print("Models Unloaded. VRAM released.")

    def track_model_usage(self, model_name):
        """Update last_used timestamp for the given model in hidden prefs."""
        try:
            prefs_path = os.path.join(APP_DATA_DIR, ".user_prefs.json")
            if os.path.exists(prefs_path):
                # RE-READ to ensure we have latest state (avoid race conditions with GUI)
                if os.path.exists(prefs_path):
                    with open(prefs_path, "r", encoding="utf-8") as f:
                        latest_prefs = json.load(f)
                else: 
                    latest_prefs = {}
                
                stats = latest_prefs.get("model_usage_stats", {})
                stats[model_name] = datetime.now().isoformat()
                latest_prefs["model_usage_stats"] = stats
                
                with open(prefs_path, "w", encoding="utf-8") as f:
                    json.dump(latest_prefs, f, indent=4)
        except Exception as e:
            log_print(f"Error tracking usage: {e}")

    def normalize_asr_preference(self, value):
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        legacy_aliases = {
            "turbo": "Whisper Large v3 Turbo (Multilingual)",
            "large-v3-turbo": "Whisper Large v3 Turbo (Multilingual)",
            "distil-large-v3": "Distil-Whisper Large v3 (English)",
            "small": "OpenAI Whisper Small",
            "qwen2-audio-7b": "Whisper Large v3 Turbo (Multilingual)",
            "Qwen2-Audio-7B": "Whisper Large v3 Turbo (Multilingual)",
        }
        return legacy_aliases.get(normalized, normalized)

    def normalize_llm_preference(self, value):
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        legacy_aliases = {
            "Standard (Llama 3.2)": models_config.DEFAULT_LLM,
            "Multilingual (Qwen 3.5 9B)": "Multilingual (Qwen 3 8B)",
            "Qwen3.5-9B-Q4_K_M.gguf": "Multilingual (Qwen 3 8B)",
            "Multilingual (Qwen 3.5 4B)": "Multilingual (Qwen 3 4B)",
            "Qwen3.5-4B-Q4_K_M.gguf": "Multilingual (Qwen 3 4B)",
            "Qwen3-8B-Q4_K_M.gguf": "Multilingual (Qwen 3 8B)",
            "Qwen3-4B-Q4_K_M.gguf": "Multilingual (Qwen 3 4B)",
            "Qwen2.5-7B-Instruct-Q4_K_M.gguf": "Multilingual (Qwen 2.5 7B)",
            "Llama-3.2-3B-Instruct-Q4_K_M.gguf": "Llama 3.2 3B Instruct",
        }
        return legacy_aliases.get(normalized, normalized)

    def load_config(self):
        """Unified configuration loader with split protection and migration."""
        try:
            config_path = os.path.join(APP_DATA_DIR, "config.json")
            prefs_path = os.path.join(APP_DATA_DIR, ".user_prefs.json")
            old_refiner = getattr(self, "current_refiner", "")
            old_active_asr = getattr(self, "active_asr_name", "")
            old_asr_repo = getattr(self, "active_mlx_repo", None) or globals().get("WHISPER_REPO", "")
            old_asr_backend = globals().get("ASR_BACKEND", "whisper")
            self.model_reload_requested = False
            
            # --- 1. Load Technical Config (Static/Public) ---
            config = {}
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            
            # --- 2. Load User Preferences (Hidden/Private) ---
            prefs = {}
            if os.path.exists(prefs_path):
                with open(prefs_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)

            # --- 3. Migration Logic (Move settings from config -> prefs) ---
            pref_keys = [
                "hotkey", "sound_enabled", "vram_timeout", "character", "tone", 
                "custom_prompts", "auto_stop_enabled", "silence_timeout_ms", 
                "paste_delay_seconds", "custom_dictionary", "current_refiner", "whisper_model"
            ]
            
            migrated = False
            for key in pref_keys:
                if key in config:
                    # Move to prefs if not already there (prefer existing prefs)
                    if key not in prefs:
                        prefs[key] = config[key]
                    del config[key]
                    migrated = True

            if migrated:
                log_print("Migrating user settings to hidden .user_prefs.json...")
                with open(prefs_path, "w", encoding="utf-8") as f:
                    json.dump(prefs, f, indent=4)
                with open(config_path, "w", encoding="utf-8") as f:
                    # Keep formatted technical config
                    json.dump(config, f, indent=4)
                
            # --- 3b. Force transition for the new default if still on old default (ONE-TIME) ---
            prefs_modified = False

            if prefs.get("current_refiner") == "CoEdit Large (T5)" and not prefs.get("_migrate_llama_3_2"):
                prefs["current_refiner"] = models_config.DEFAULT_LLM
                prefs["_migrate_llama_3_2"] = True
                prefs_modified = True

            if (prefs.get("vram_timeout") in [None, 60]) and not prefs.get("_migrate_vram_timeout_300"):
                prefs["vram_timeout"] = 300
                prefs["_migrate_vram_timeout_300"] = True
                prefs_modified = True

            for library_key in ["asr_library", "llm_library"]:
                if library_key in prefs:
                    del prefs[library_key]
                    prefs_modified = True

            normalized_whisper_model = self.normalize_asr_preference(prefs.get("whisper_model"))
            if normalized_whisper_model != prefs.get("whisper_model"):
                prefs["whisper_model"] = normalized_whisper_model
                prefs_modified = True

            normalized_refiner = self.normalize_llm_preference(prefs.get("current_refiner", models_config.DEFAULT_LLM))
            if normalized_refiner != prefs.get("current_refiner"):
                prefs["current_refiner"] = normalized_refiner
                prefs_modified = True

            if prefs_modified:
                with open(prefs_path, "w", encoding="utf-8") as f:
                    json.dump(prefs, f, indent=4)
            
            # Update mtime tracker immediately to avoid self-triggering polish loop
            if os.path.exists(prefs_path):
                self._last_prefs_mtime = os.path.getmtime(prefs_path)

            # --- 4. Apply Settings ---
            # Parse hotkey_str (e.g. "ctrl+shift+k")
            new_hotkey_str = prefs.get("hotkey", "ctrl+shift+space").lower()
            hotkey_changed = new_hotkey_str != getattr(self, 'hotkey_str', '')
            self.hotkey_str = new_hotkey_str
            
            parts = [p.strip().lower() for p in self.hotkey_str.split('+')]
            # Support multiple aliases for modifiers
            mod_map = {
                "cmd": "cmd", "command": "cmd", "⌘": "cmd",
                "alt": "alt", "option": "alt", "⌥": "alt",
                "ctrl": "ctrl", "control": "ctrl", "⌃": "ctrl",
                "shift": "shift", "⇧": "shift"
            }
            self.target_mods = set([mod_map[p] for p in parts if p in mod_map])
            self.target_key = parts[-1] if parts else "space"
            
            log_print(f"Parsed Hotkey: Mods={self.target_mods}, Key={self.target_key}")
            
            # UPDATE HOTKEY IN-PLACE (No listener restart)
            if hotkey_changed:
                log_print(f"Hotkey changed ({getattr(self, 'hotkey_str_old', 'None')} -> {self.hotkey_str}). Updating in-place...")
                self.hotkey_str_old = self.hotkey_str
                # Listener already uses target_mods/target_key, so updating them is enough
                # We also clear active_mods to prevent "stuck" combinations during the transition
                self.active_mods.clear()
            
            # Update Tray ToolTip context
            if not self.headless:
                self.update_tray_tooltip()
            
            self.last_config_reload_time = time.time()
            # Update hash tracker and mtime after all potential logic is done
            if os.path.exists(prefs_path):
                 with open(prefs_path, "rb") as f:
                     self._last_prefs_hash = hashlib.md5(f.read()).hexdigest()
                 self._last_prefs_mtime = os.path.getmtime(prefs_path)
                
            # Update Tray ToolTip context
            if not self.headless:
                self.update_tray_tooltip()

            self.sound_enabled = prefs.get("sound_enabled", True)
            self.auto_stop_enabled = prefs.get("auto_stop_enabled", True)
            try:
                self.paste_delay_seconds = max(0, int(prefs.get("paste_delay_seconds", 0)))
            except Exception:
                self.paste_delay_seconds = 0
            old_silence = getattr(self, "silence_timeout_ms", 10000)
            # Backend Clamping: Min 5s
            self.silence_timeout_ms = max(5000, prefs.get("silence_timeout_ms", 10000))
            
            # Dynamic VAD Re-initialization if timeout changed
            if hasattr(self, 'VADIterator') and self.vad_model and self.silence_timeout_ms != old_silence:
                log_print(f"Applying new Auto-Stop Timeout: {self.silence_timeout_ms}ms")
                self.vad_iterator = self.VADIterator(self.vad_model, 
                                                     threshold=VAD_THRESHOLD, 
                                                     sampling_rate=SAMPLE_RATE, 
                                                     min_silence_duration_ms=self.silence_timeout_ms, 
                                                     speech_pad_ms=SPEECH_PAD_MS)

            self.custom_dictionary = prefs.get("custom_dictionary", [])
            self.vram_timeout = max(5, prefs.get("vram_timeout", 300))
            self.character = prefs.get("character", "Writing Assistant")
            self.tone = prefs.get("tone", "Natural")
            self.custom_prompts = prefs.get("custom_prompts", {})
            self.current_refiner = self.normalize_llm_preference(prefs.get("current_refiner", models_config.DEFAULT_LLM))
            
            # Library definitions are app-curated data. Keep prefs limited to the selected model names.
            self.asr_library = models_config.ASR_LIBRARY
            self.llm_library = models_config.LLM_LIBRARY

            # Filter libraries
            self.asr_library = [m for m in self.asr_library if self.verify_model(m, "asr")]
            self.llm_library = [m for m in self.llm_library if self.verify_model(m, "llm")]

            available_asr_names = {
                alias
                for model in self.asr_library
                for alias in (model.get("name"), model.get("whisper_model"))
                if alias
            }
            if self.asr_library and self.normalize_asr_preference(prefs.get("whisper_model", models_config.DEFAULT_ASR)) not in available_asr_names:
                fallback_asr = next(
                    (m["name"] for m in self.asr_library if m.get("name") == models_config.DEFAULT_ASR),
                    self.asr_library[0]["name"]
                )
                log_print(f"Selected ASR '{prefs.get('whisper_model')}' is unavailable in this runtime. Falling back to '{fallback_asr}'.")
                prefs["whisper_model"] = fallback_asr
                with open(prefs_path, "w", encoding="utf-8") as f:
                    json.dump(prefs, f, indent=4)

            available_llm_names = {
                alias
                for model in self.llm_library
                for alias in (model.get("name"), model.get("file_name"))
                if alias
            }
            if self.llm_library and self.normalize_llm_preference(prefs.get("current_refiner", models_config.DEFAULT_LLM)) not in available_llm_names:
                fallback_llm = next(
                    (m["name"] for m in self.llm_library if m.get("name") == models_config.DEFAULT_LLM),
                    self.llm_library[0]["name"]
                )
                log_print(f"Selected LLM '{prefs.get('current_refiner')}' is unavailable in this runtime. Falling back to '{fallback_llm}'.")
                prefs["current_refiner"] = fallback_llm
                with open(prefs_path, "w", encoding="utf-8") as f:
                    json.dump(prefs, f, indent=4)

            self.current_refiner = self.normalize_llm_preference(prefs.get("current_refiner", models_config.DEFAULT_LLM))

            # Sync Current Profile from Library
            profile = {}
            for p in self.llm_library:
                # Robust matching: check both human-readable name and internal filename
                if p["name"] == self.current_refiner or p.get("file_name") == self.current_refiner:
                    profile = {
                        "repo_id": p.get("repo_id"),
                        "file_name": p.get("file_name"),
                        "prompt_type": p.get("prompt_type"),
                        "description": p.get("description", ""),
                        "mlx_repo": p.get("mlx_repo")
                    }
                    # REMOVED recursive usage tracking here
                    break
            
            if hasattr(self, 'grammar_checker'):
                self.grammar_checker.profile = profile

                if old_refiner and self.current_refiner != old_refiner:
                    log_print(f"Refiner change detected: {old_refiner} -> {self.current_refiner}")
                    self.grammar_checker.unload_model()
                    self.model_reload_requested = True
                
                # Clear context cache if personality/tone changes abruptly to prevent bleed
                if self.grammar_checker.character != self.character or self.grammar_checker.tone != self.tone:
                     self.grammar_checker.context_buffer = ""
                     
                self.grammar_checker.character = self.character
                self.grammar_checker.tone = self.tone
                self.grammar_checker.custom_prompts = self.custom_prompts
                self.grammar_checker.custom_dictionary = self.custom_dictionary
            
            # ASR Model resolution
            global WHISPER_SIZE, WHISPER_REPO, ASR_BACKEND
            self.active_asr_name = self.normalize_asr_preference(prefs.get("whisper_model", models_config.DEFAULT_ASR))
            active_asr = self.active_asr_name
            
            # Find in library
            WHISPER_REPO = "Systran/faster-distil-whisper-large-v3" # Defaults
            WHISPER_SIZE = "distil-large-v3"
            self.active_mlx_repo = None
            self.active_whisper_repo = WHISPER_REPO

            ASR_BACKEND = "whisper"
            for asr in self.asr_library:
                if asr["name"] == active_asr or asr.get("whisper_model") == active_asr:
                    # Sync with library technical names
                    self.active_mlx_repo = asr.get("mlx_repo")
                    self.active_whisper_repo = asr.get("whisper_repo") or asr.get("repo")
                    if IS_MAC and asr.get("mlx_repo"):
                        WHISPER_REPO = asr.get("mlx_repo")
                    else:
                        WHISPER_REPO = asr.get("whisper_repo") or asr.get("repo")
                        
                    WHISPER_SIZE = asr.get("whisper_model") or asr.get("name")
                    ASR_BACKEND = asr.get("mac_backend") if (IS_MAC and asr.get("mac_backend")) else asr.get("backend", "whisper")
                    log_print(f" Resolved ASR: {active_asr} -> Repo: {WHISPER_REPO} (Backend: {ASR_BACKEND})")
                    break

            if old_active_asr and (
                active_asr != old_active_asr or
                WHISPER_REPO != old_asr_repo or
                ASR_BACKEND != old_asr_backend
            ):
                log_print(f"ASR change detected: {old_active_asr} -> {active_asr}. Scheduling reload...")
                self.asr_model = None
                self.mlx_asr_local_path = None
                self.mlx_asr_warmed = False
                self.mlx_qwen_asr_local_path = None
                self.model_reload_requested = True

            if self.model_reload_requested:
                self.heavy_models_loaded = False
                self.models_ready = False
                self.loading_status = "Switching Models..."
            
            # REMOVED cleanup_stale_models from here to prevent recursive reload loops

        except Exception as e:
            log_print(f"Error loading config: {e}")
            traceback.print_exc()

    def verify_model(self, model_data, model_type):
        """Verifies if a model repository or local path exists."""
        repo = model_data.get("repo") or model_data.get("repo_id") or model_data.get("whisper_repo")
        local_path = model_data.get("local_path")
        whisper_model = model_data.get("whisper_model")
        file_name = model_data.get("file_name")
        mlx_repo = model_data.get("mlx_repo")
        backend = model_data.get("mac_backend") if (model_type == "asr" and IS_MAC and model_data.get("mac_backend")) else model_data.get("backend", "whisper")
        preferred_repo = mlx_repo if (model_type in {"asr", "llm"} and IS_MAC and mlx_repo) else repo

        if model_type == "asr" and backend == "qwen_asr":
            if importlib.util.find_spec("qwen_asr") is None:
                return False
        
        # 1. Check local path if provided
        if local_path:
            full_path = os.path.join(BASE_DIR, local_path)
            if os.path.isdir(full_path):
                # Basic signature check
                if model_type == "asr" and os.path.exists(os.path.join(full_path, "model.bin")):
                    return True
                if model_type == "llm" and any(f.endswith(".gguf") for f in os.listdir(full_path)):
                    return True
            return False

        # 2. Check standard 'models/' directory for repo-based models (Offline Support)
        models_dir = os.path.join(BASE_DIR, "models")
        if model_type == "asr" and whisper_model:
            if IS_MAC and mlx_repo:
                if self.resolve_local_mlx_asr_dir(repo_id=mlx_repo, whisper_model=whisper_model):
                    return True
            target = os.path.join(models_dir, f"whisper-{whisper_model}")
            # For faster-whisper we check model.bin, for transformers (Qwen) we check config.json
            if os.path.isdir(target) and (os.path.exists(os.path.join(target, "model.bin")) or os.path.exists(os.path.join(target, "config.json"))):
                return True
        elif model_type == "llm" and file_name:
            if IS_MAC and mlx_repo and self.resolve_local_mlx_llm_dir(repo_id=mlx_repo):
                return True
            target = os.path.join(models_dir, file_name)
            if os.path.exists(target):
                return True

        # 3. Keep curated remote models visible even before they are downloaded.
        # Otherwise macOS MLX models get filtered out at startup and we fall back
        # to the wrong non-MLX repo/path during the actual download step.
        if preferred_repo:
            return True
        
        return False

    def cleanup_stale_models(self, days):
        """Deletes models that haven't been used in X days."""
        try:
            prefs_path = os.path.join(APP_DATA_DIR, ".user_prefs.json")
            if not os.path.exists(prefs_path): return
            
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            
            stats = prefs.get("model_usage_stats", {})
            threshold = datetime.now() - timedelta(days=days)
            
            # Collect all models currently in libraries to avoid deleting active ones
            all_known_files = []
            for m in models_config.ASR_LIBRARY:
                all_known_files.append(m.get("whisper_model", "").lower())
                all_known_files.append(m.get("name", "").lower())
            for m in models_config.LLM_LIBRARY:
                all_known_files.append(m.get("file_name", "").lower())
                all_known_files.append(m.get("name", "").lower())
            
            # Current globals
            all_known_files.append(WHISPER_SIZE.lower())
            all_known_files.append(GRAMMAR_FILE.lower())
            
            models_dir = os.path.join(BASE_DIR, "models")
            if not os.path.exists(models_dir): return
            
            for item in os.listdir(models_dir):
                item_path = os.path.join(models_dir, item)
                item_lower = item.lower()
                
                # Never delete specific infrastructure folders
                if item_lower in ["hub", "cache", ".cache"]:
                    continue

                # Never delete models that are in our library definitions
                is_active = False
                for known in all_known_files:
                    if known and (known in item_lower or item_lower in known):
                        is_active = True
                        break
                
                if is_active:
                    continue

                # Final check against usage stats
                is_used_recently = False
                for model_key, last_used_iso in stats.items():
                    try:
                        last_used = datetime.fromisoformat(last_used_iso)
                        if last_used > threshold:
                            if item_lower in model_key.lower() or model_key.lower() in item_lower:
                                is_used_recently = True
                                break
                    except: pass
                
                if not is_used_recently:
                    log_print(f"Cleaning up stale model: {item} (Unused for {days}+ days)")
                    import shutil
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                        
        except Exception as e:
            log_print(f"Cleanup error: {e}")
            

    def update_tray_tooltip(self):
        if self.icon:
            gpu_status = "GPU" if torch.cuda.is_available() else "CPU"
            hk_display = getattr(self, 'hotkey_str', 'F8').upper()
            self.icon.title = f"Privox: {self.loading_status} ({gpu_status})\nHotkey: {hk_display}"

    def update_status(self, status):
        # status: READY, RECORDING, PROCESSING, ERROR, DOWNLOADING, INITIALIZING, SLEEP
        self.ui_state = status

        # Keep one source of truth for tray text to avoid inconsistent tooltip/title states.
        status_text = {
            "READY": "Ready",
            "RECORDING": "Listening...",
            "PROCESSING": "Processing...",
            "TRANSCRIBING": "Transcribing...",
            "REFINING": "Refining...",
            "DOWNLOADING": "Downloading Model...",
            "ERROR": "Error/No Mic",
            "SLEEP": "Sleeping (VRAM Saver Active)",
            "INITIALIZING": "Initializing..."
        }.get(status)

        if status_text:
            self.loading_status = status_text
            
        if self.headless:
            log_print(f"STATUS: {status}")
            return
            
        self.update_tray_tooltip()

    def animation_loop(self):
        frame = 0
        while self.running:
            try:
                if not self.icon:
                    time.sleep(1)
                    continue

                # Default static icon path
                icon_path = resource_path("assets/icon.png")
                base_img = None
                if os.path.exists(icon_path):
                     base_img = Image.open(icon_path).convert("RGBA")
                
                # If static state, just ensure base icon is set once (to avoid cpu usage)
                # But here we want custom static states too (e.g. ready = normal)
                
                new_icon = None
                
                if self.ui_state == "RECORDING":
                    # Waveform Animation
                    new_icon = self.draw_waveform(frame, base_img)
                    frame += 1
                    time.sleep(0.08) # 12fps
                    
                elif self.ui_state in ["PROCESSING", "TRANSCRIBING", "REFINING", "DOWNLOADING", "INITIALIZING"]:
                    # Spinner Animation for processing, downloading, and initializing
                    new_icon = self.draw_spinner(frame, base_img)
                    frame += 1
                    time.sleep(0.08)
                    
                elif self.ui_state == "SLEEP":
                    # Flat Line (Static or slow pulse?) -> Let's do static flat line
                    # Only update if current icon is not already it? 
                    # Simpler to re-draw for now, optimization later if needed.
                    new_icon = self.draw_flat_line(base_img)
                    time.sleep(0.5) # Slow update
                    
                elif self.ui_state == "ERROR":
                    # Error Dot (Static - Monotone White)
                    # Maybe draw an "!" or solid circle
                    if base_img:
                        new_icon = base_img.copy()
                        d = ImageDraw.Draw(new_icon)
                        # Draw "!" or white dot
                        d.ellipse((48, 48, 60, 60), fill="white", outline="white")
                    time.sleep(0.5)
                    
                else: # READY or LOADING
                    # Just the base icon (Normal)
                    # Maybe clear any overlays
                    if base_img: new_icon = base_img
                    time.sleep(0.5)

                if new_icon:
                    self.icon.icon = new_icon
                    
            except Exception as e:
                log_print(f"Anim Error: {e}")
                time.sleep(1)

    def draw_waveform(self, frame, base_img):
        # Draw dynamic waveform bars on top of base or instead of?
        # User said "waveform as icon". Our icon IS a waveform.
        # So we should animate the bars of the icon itself? 
        # But we loaded a PNG. We can't easily animate components of a flat PNG.
        # OPTION: Draw the waveform procedurally from scratch (like generate_icon.py).
        
        size = (64, 64)
        bg_color = (25, 25, 35, 255) 
        bar_color = (255, 255, 255, 255)
        
        img = Image.new("RGBA", size, bg_color)
        draw = ImageDraw.Draw(img)
        
        # 4 Bars
        import random
        import math
        
        bar_w = 8
        gap = 4
        total_w = (4 * bar_w) + (3 * gap)
        start_x = (64 - total_w) // 2
        center_y = 32
        
        # Animate heights based on sine wave + noise
        for i in range(4):
            # Phase shift for each bar
            # Time varying
            t = frame * 0.5
            
            # Base height + sin wave
            # random noise to look like voice
            noise = random.randint(-5, 5)
            h = 20 + int(15 * math.sin(t + i)) + noise
            h = max(4, min(60, h))
            
            x = start_x + i * (bar_w + gap)
            y1 = center_y - (h // 2)
            y2 = center_y + (h // 2)
            
            draw.rectangle((x, y1, x+bar_w, y2), fill=bar_color)
            
        # Monotone: No Red Dot
        # draw.ellipse((50, 50, 60, 60), fill="#ff4444", outline="white")
            
        return img

    def draw_spinner(self, frame, base_img):
        # Processing: Rotating Circle (Monotone White)
        size = (64, 64)
        bg_color = (25, 25, 35, 255) 
        img = Image.new("RGBA", size, bg_color)
        draw = ImageDraw.Draw(img)
        
        # Draw Arc
        start_angle = (frame * 30) % 360
        end_angle = (start_angle + 270) % 360
        
        draw.arc((12, 12, 52, 52), start=start_angle, end=end_angle, fill="white", width=4)
        
        return img

    def draw_flat_line(self, base_img):
        # Sleep Mode (Monotone White)
        size = (64, 64)
        bg_color = (25, 25, 35, 255) 
        img = Image.new("RGBA", size, bg_color)
        draw = ImageDraw.Draw(img)
        
        # Flat Line
        draw.line((10, 32, 54, 32), fill="white", width=3) # Changed from grey to white for visibility
        
        return img

    def audio_callback(self, indata, frames, time, status):
        if self.running and self.mic_active and self.models_ready:
            self.q.put(indata.copy())

    def on_press(self, key):
        """Standard keyboard listener callback."""
        # 1. Track Modifiers
        mod_map = {
            keyboard.Key.ctrl: "ctrl", keyboard.Key.ctrl_l: "ctrl", keyboard.Key.ctrl_r: "ctrl",
            keyboard.Key.shift: "shift", keyboard.Key.shift_l: "shift", keyboard.Key.shift_r: "shift",
            keyboard.Key.alt: "alt", keyboard.Key.alt_l: "alt", keyboard.Key.alt_gr: "alt",
            keyboard.Key.cmd: "cmd", keyboard.Key.cmd_l: "cmd", keyboard.Key.cmd_r: "cmd"
        }
        
        if key in mod_map:
            val = mod_map[key]
            self.active_mods.add(val)
            # If the modifier itself is the target key (e.g. just Ctrl+Shift), don't return
            if val != self.target_key:
                return

        # 2. Key Normalization
        key_name = ""
        try:
            k_name = getattr(key, 'name', None)
            k_char = getattr(key, 'char', None)
            k_vk = getattr(key, 'vk', None)

            if k_name:
                key_name = k_name
            elif k_vk and 65 <= k_vk <= 90:
                # A-Z (VK codes 65-90). Safely bypasses unprintable ASCII generated by Ctrl+Key
                key_name = chr(k_vk).lower()
            elif k_vk and 48 <= k_vk <= 57:
                # 0-9 (VK codes 48-57)
                key_name = chr(k_vk)
            elif k_char:
                # Pynput unprintable char fallback (e.g. Ctrl+A = \x01)
                if 1 <= ord(k_char) <= 26: 
                     key_name = chr(ord(k_char) + 96)
                else:
                     key_name = k_char.lower()
            elif k_vk:
                    # Handle virtual keys (important for some mouse remappings)
                    # VK codes: F1=0x70 ... F12=0x7B, F13=0x7C ... F24=0x87. Space=0x20, Enter=0x0D
                    vk_map = {
                        0x70: "f1", 0x71: "f2", 0x72: "f3", 0x73: "f4",
                        0x74: "f5", 0x75: "f6", 0x76: "f7", 0x77: "f8",
                        0x78: "f9", 0x79: "f10", 0x7A: "f11", 0x7B: "f12",
                        0x7C: "f13", 0x7D: "f14", 0x7E: "f15", 0x7F: "f16",
                        0x80: "f17", 0x81: "f18", 0x82: "f19", 0x83: "f20",
                        0x84: "f21", 0x85: "f22", 0x86: "f23", 0x87: "f24",
                        0x20: "space", 0x0D: "enter", 0x09: "tab", 0x1B: "esc",
                        0x21: "page_up", 0x22: "page_down", 0x23: "end", 0x24: "home",
                        0x2D: "insert", 0x2E: "delete"
                    }
                    key_name = vk_map.get(k_vk, str(k_vk))
        except Exception:
             pass

        # 3. Check Match
        if key_name == self.target_key:
            # DE-BOUNCE: Prevent rapid-fire re-triggering (e.g. from key auto-repeat)
            now = time.time()
            if now - self.last_toggle_time < 0.4:
                return
            self.last_toggle_time = now
            
            # Win32 Robustness: Check for "Stuck" modifiers using ctypes
            if sys.platform == 'win32' and self.active_mods != self.target_mods:
                import ctypes
                # Check physical state of tracked modifiers
                stuck = []
                for mod in list(self.active_mods):
                    vk = 0
                    if mod == 'ctrl': vk = 0x11
                    elif mod == 'shift': vk = 0x10
                    elif mod == 'alt': vk = 0x12
                    
                    # GetAsyncKeyState returns MSB set if key is down
                    if vk and not (ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000):
                        stuck.append(mod)
                
                if stuck:
                    log_print(f" [Hotkey Diagnostic] Clearing stuck modifiers: {stuck}")
                    for mod in stuck:
                        self.active_mods.remove(mod)

            # Check if active modifiers match EXACTLY what is required
            if self.active_mods == self.target_mods:
                self.toggle_hotkey()
            else:
                log_print(f" [Hotkey Ignored] Key '{key_name}' pressed, but modifiers mismatch. Expected: {self.target_mods}, Actual: {self.active_mods}")

    def on_release(self, key):
        """Untrack modifiers."""
        mod_map = {
            keyboard.Key.ctrl: "ctrl", keyboard.Key.ctrl_l: "ctrl", keyboard.Key.ctrl_r: "ctrl",
            keyboard.Key.shift: "shift", keyboard.Key.shift_l: "shift", keyboard.Key.shift_r: "shift",
            keyboard.Key.alt: "alt", keyboard.Key.alt_l: "alt", keyboard.Key.alt_gr: "alt",
            keyboard.Key.cmd: "cmd", keyboard.Key.cmd_l: "cmd", keyboard.Key.cmd_r: "cmd"
        }
        if key in mod_map:
            val = mod_map[key]
            if val in self.active_mods:
                self.active_mods.remove(val)

    def start_listening(self):
        self.last_activity_time = time.time()
        log_print("\n[Start Listening]", flush=True)
        self.is_listening = True
        self.is_speaking = False
        self.audio_buffer = []
        if self.vad_iterator:
            self.vad_iterator.reset_states()
        if self.headless:
            log_print("STATUS: RECORDING")
        else:
            self.update_status("RECORDING")
            self.sound_manager.play_start()

    def stop_listening(self):
        log_print(" [Stopped]", flush=True)
        if not self.headless:
            self.sound_manager.play_stop()
        self.is_listening = False
        if not self.headless:
            self.update_status("PROCESSING")
        else:
            log_print("STATUS: PROCESSING")
        
        if len(self.audio_buffer) > 0:
            audio_segment = np.array(self.audio_buffer)
            # Run transcription in a separate thread so we don't block the keyboard listener!
            threading.Thread(target=self.transcribe, args=(audio_segment,), daemon=True).start()
        else:
            if not self.headless:
                self.update_status("READY")
            else:
                log_print("STATUS: READY")
             
        self.audio_buffer = []
        self.last_activity_time = time.time()

    def transcribe(self, audio_data):
        try:
            duration = len(audio_data) / SAMPLE_RATE
            max_amp = np.max(np.abs(audio_data))
            rms = np.sqrt(np.mean(audio_data**2))
            
            log_print(f"\n--- Transcription Diagnostic ---")
            log_print(f"Audio Stats - Duration: {duration:.2f}s, Max Amp: {max_amp:.4f}, RMS: {rms:.4f}")
            
            if duration < (MIN_SPEECH_DURATION_MS / 1000):
                log_print(f" [Audio too short - Ignored]")
                if not self.headless:
                    self.update_status("READY")
                else:
                    log_print("STATUS: READY")
                return

            if max_amp < 0.001: 
                log_print(f" [Audio too quiet - Ignored]")
                if not self.headless:
                    self.update_status("READY")
                else:
                    log_print("STATUS: READY")
                return

            # Ensure models are loaded before transcribing
            if not self.heavy_models_loaded:
                log_print("Waiting for models to load...")
                self.load_heavy_models()
                if not self.asr_model:
                     log_print("ASR Model still missing after lazy load attempt.")
                     if not self.headless:
                        self.update_status("READY")
                     else:
                        log_print("STATUS: READY")
                     return

            log_print(f" Transcribing Using Backend: {ASR_BACKEND} (Model: {getattr(self, 'active_asr_name', WHISPER_SIZE)})...", flush=True)
            if not self.headless:
                self.update_status("TRANSCRIBING")
            else:
                log_print("STATUS: TRANSCRIBING")
            t0 = time.time()
            
            raw_text = ""
            info = None
            if ASR_BACKEND == "sensevoice":
                # SenseVoice/funasr
                results = self.asr_model.generate(
                    input=audio_data.flatten().astype(np.float32),
                    cache={},
                    language="auto", # SenseVoice handles LID well
                    use_itn=True,
                    batch_size_s=60,
                    merge_vad=True,
                    merge_length_s=15,
                )
                
                # funasr output is a list of dicts: [{'text': '...', 'key': '...'}]
                if results and len(results) > 0:
                    raw_text = results[0].get('text', '')
                    # Clean up emotion/event tags like <|HAPPY|>, <|ENTHUSIASTIC|>, etc.
                    raw_text = re.sub(r'<\|.*?\|>', '', raw_text).strip()
                
                log_print(f" SenseVoice Result - Raw: '{raw_text}'")
            elif ASR_BACKEND == "qwen_asr":
                # Qwen3-ASR (Transformers backend) expects (waveform, sr) tuple
                results = self.asr_model.transcribe(
                    audio=(audio_data.astype(np.float32), 16000),
                    language=None, # Auto-detect
                    return_time_stamps=False # DISABLE forced alignment
                )
                if results and len(results) > 0:
                    raw_text = results[0].get('text', '') if isinstance(results[0], dict) else getattr(results[0], 'text', str(results[0]))
                log_print(f" Qwen3-ASR Result: '{raw_text}'")
            elif ASR_BACKEND == "mlx_qwen_asr":
                model_source = self.mlx_qwen_asr_local_path or self.active_mlx_repo or WHISPER_REPO
                log_print(f" Transcribing Using MLX Qwen-ASR (Source: {model_source})...")
                raw_text = self.transcribe_with_mlx_qwen_asr(audio_data)
                log_print(f" MLX Qwen-ASR Result: '{raw_text}'")
            elif IS_MAC:
                # MLX-Whisper
                local_mlx_path = self.mlx_asr_local_path or self.ensure_mlx_asr_model_available(download_if_missing=True)
                log_print(f" Transcribing Using MLX-Whisper (Source: {local_mlx_path or WHISPER_REPO})...")
                try:
                    results = self.asr_model.transcribe(
                        audio_data.astype(np.float32), 
                        path_or_hf_repo=local_mlx_path or WHISPER_REPO
                    )
                    raw_text = results.get('text', "").strip()
                    log_print(f" MLX-Whisper Result - Raw: '{raw_text}'")
                except Exception as asr_e:
                    log_print(f" MLX-ASR Critical Error: {asr_e}")
                    raw_text = ""
            else:
                # Faster-Whisper
                segments, info = self.asr_model.transcribe(
                    audio_data.astype(np.float32), 
                    beam_size=5,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500)
                )
                
                log_print(f" ASR Result - Language Detected: {info.language} ({info.language_probability:.2f})")
                
                # Collect segments and log each one
                seg_results = []
                for segment in segments:
                    log_print(f"  Segment: [{segment.start:.2f}s -> {segment.end:.2f}s] ({len(segment.text)} chars)")
                    seg_results.append(segment.text)
                
                raw_text = " ".join(seg_results).strip()
            
            t1 = time.time()
            log_print(f" [ASR Total Time: {t1 - t0:.3f}s] Result: {len(raw_text)} chars")
            
            if not raw_text:
                log_print(" [Empty Transcription Result]")
                if not self.headless:
                    self.update_status("READY")
                else:
                    log_print("STATUS: READY")
                return

            # --- Logic for Command Mode (DISABLED FOR NOW) ---
            is_command = False
            command_text = raw_text
            
            # if raw_text.lower().startswith("privox"):
            #     is_command = True
            #     command_text = re.sub(r'^(privox)\s*,?\s*', '', raw_text, flags=re.IGNORECASE)
            #     log_print(f" [Command Mode Detected] Input: {command_text}")
            
            log_print(f" Refining format ({self.current_refiner})...")
            if not self.headless:
                self.update_status("REFINING")
            else:
                log_print("STATUS: REFINING")
            t2 = time.time()
            detected_lang = info.language if (info and ASR_BACKEND == 'whisper') else None
            detected_prob = info.language_probability if (info and ASR_BACKEND == 'whisper') else 0.0
            final_text = self.grammar_checker.correct(command_text, is_command=is_command, language=detected_lang, language_prob=detected_prob)
            t3 = time.time()
            log_print(f" [Grammar Time: {t3 - t2:.3f}s]")
            
            log_print(f" [Refined Output: {len(final_text)} chars]")
            log_print(f" [Total Time: {t3 - t0:.3f}s]")
            
            try:
                self.paste_text(final_text)
            except Exception as e:
                log_print(f"Typing Error: {e}")
                if not self.headless:
                    self.sound_manager.play_error()
                
        except Exception as e:
            log_print(f"ASR Error: {e}")
            self.loading_status = "ASR Error"
            if not self.headless:
                self.sound_manager.play_error()
        finally:
            # Only reset to READY if we haven't hit an error state
            if self.loading_status not in ["ASR Error", "Refiner Error"]:
                if not self.headless:
                    self.update_status("READY")
                else:
                    log_print("STATUS: READY")

    def paste_text(self, text):
        try:
            original_clipboard = pyperclip.paste()
            pyperclip.copy(text)
            initial_clipboard_delay = 0.01
            if self.paste_delay_seconds > 0:
                log_print(f"Paste delay active. Waiting {self.paste_delay_seconds}s before inserting text...")
            time.sleep(initial_clipboard_delay + self.paste_delay_seconds)
            
            if IS_MAC:
                # Use AppleScript to paste on macOS to bypass pynput Sandbox inheritance blocks
                import subprocess
                subprocess.run([
                    "osascript", 
                    "-e", 
                    'tell application "System Events" to keystroke "v" using command down'
                ])
            else:
                modifier = keyboard.Key.cmd if IS_MAC else keyboard.Key.ctrl
                with self.keyboard_controller.pressed(modifier):
                    self.keyboard_controller.press('v')
                    self.keyboard_controller.release('v')
                
            time.sleep(0.05)
            pyperclip.copy(original_clipboard)
        except Exception as e:
            log_print(f"Paste Error: {e}")
            if not self.headless:
                self.keyboard_controller.type(text)

    def start_audio_stream(self):
        with self.audio_stream_lock:
            self.last_mic_retry_time = time.time()
            if self.mic_active and self.stream is not None:
                log_print("Microphone stream already active. Skipping duplicate start request.")
                log_print("DETAIL: MICROPHONE_STREAM_ACTIVE")
                return

            log_print("DETAIL: MICROPHONE_RECONNECTING")
            try:
                if self.stream is not None:
                    try:
                        self.stream.stop()
                    except Exception:
                        pass
                    try:
                        self.stream.close()
                    except Exception:
                        pass
                    self.stream = None

                # Diagnostic: Log input device
                try:
                    device_info = sd.query_devices(kind='input')
                    log_print(f"Audio Diagnostic - Using Default Input: {device_info.get('name')} (Channels: {device_info.get('max_input_channels')})")
                except Exception as de:
                    log_print(f"Audio Diagnostic - Could not query input device: {de}")

                self.stream = sd.InputStream(
                    callback=self.audio_callback,
                    channels=1,
                    samplerate=SAMPLE_RATE,
                    blocksize=BLOCK_SIZE
                )
                self.stream.start()
                self.mic_active = True
                log_print("Microphone Stream Started.")
                log_print("DETAIL: MICROPHONE_STREAM_ACTIVE")
                if self.ui_state == "ERROR" and self.models_ready and not self.is_listening:
                    self.update_status("READY")
            except Exception as e:
                log_print(f"Microphone Error: {e}")
                self.mic_active = False
                self.stream = None
                log_print("DETAIL: MICROPHONE_STREAM_INACTIVE")
                log_print("DETAIL: MICROPHONE_UNAVAILABLE")
                self.update_status("ERROR")
                if not self.headless:
                    self.sound_manager.play_error()

    def processing_loop(self):
        self.start_audio_stream()
            
        while self.running:
            if not self.mic_active and (time.time() - self.last_mic_retry_time) >= self.mic_retry_interval:
                log_print("Microphone inactive. Attempting automatic audio reconnect...")
                self.start_audio_stream()

            # VRAM Saver Check
            if self.heavy_models_loaded and not self.is_listening and self.ui_state != "PROCESSING":
                if (time.time() - self.last_activity_time) > self.vram_timeout:
                    self.unload_heavy_models()

            # Config Polling (Hot-reload)
            try:
                prefs_path = os.path.join(APP_DATA_DIR, ".user_prefs.json")
                if os.path.exists(prefs_path):
                    mtime = os.path.getmtime(prefs_path)
                    if not hasattr(self, '_last_prefs_mtime'):
                        self._last_prefs_mtime = mtime
                    elif mtime > self._last_prefs_mtime:
                        # Use HASH based comparison to avoid metadata "touches" causing loops
                        with open(prefs_path, "rb") as f:
                            current_hash = hashlib.md5(f.read()).hexdigest()
                        
                        if current_hash != self._last_prefs_hash:
                            log_print(f"Configuration content change detected. Reloading...")
                            self._last_prefs_hash = current_hash
                            self._last_prefs_mtime = mtime
                            time.sleep(0.1)
                            self.load_config()
                            log_print(f"Reload complete. Hotkey: {self.hotkey_str}")
                        else:
                            # Content is same, just metadata was touched. Update mtime to stop polling.
                            self._last_prefs_mtime = mtime
            except: pass

            try:
                try:
                    chunk = self.q.get(timeout=0.5)
                except queue.Empty:
                    continue
                    
                if not self.is_listening:
                    continue
                    
                chunk = chunk.flatten()
                self.audio_buffer.extend(chunk)
                
                # Check VAD for Manual Toggle Feedback & Auto-Stop
                if self.vad_iterator:
                    chunk_tensor = torch.from_numpy(chunk).float()
                    speech_dict = self.vad_iterator(chunk_tensor, return_seconds=True)
                    
                    if speech_dict:
                        if 'start' in speech_dict and not self.is_speaking:
                             self.is_speaking = True
                        if 'end' in speech_dict and self.is_listening and self.auto_stop_enabled:
                             log_print(" [Auto-Stop Detected: Silence after speech]")
                             self.stop_listening()
                    
                    # Safety Fallback: Absolute silence timeout (if never started speaking)
                    if self.is_listening and not self.is_speaking and self.auto_stop_enabled:
                        if (time.time() - self.last_activity_time) > (self.silence_timeout_ms / 1000):
                            log_print(" [Auto-Stop Detected: Initial silence timeout]")
                            self.stop_listening()
                            
            except Exception as e:
                log_print(f"Loop Error: {e}")
                time.sleep(1)

    def show_settings_gui(self, icon, item):
        if self.settings_process and self.settings_process.poll() is None:
            # Already running
            return
            
        gui_path = resource_path("src/gui_settings.py")
        if not getattr(sys, 'frozen', False):
            # In Dev mode, we might need absolute path
            gui_path = os.path.join(BASE_DIR, "src", "gui_settings.py")

        log_print(f"Launching Settings GUI: {gui_path}")
        try:
            # Removed CREATE_NO_WINDOW and set cwd to BASE_DIR to ensure it finds config.json correctly
            self.settings_process = subprocess.Popen([sys.executable, gui_path], 
                                                     cwd=BASE_DIR,
                                                     shell=False)
            
            def watch_process():
                self.settings_process.wait()
                ret_code = self.settings_process.returncode
                log_print(f"Settings GUI closed (Exit Code: {ret_code}). Reloading config...")
                self.load_config()
                
                if ret_code == 10:
                    log_print("Restart requested by Settings GUI. Triggering full app restart...")
                    self.restart_app(reopen_settings=True)
                
            threading.Thread(target=watch_process, daemon=True).start()
        except Exception as e:
            log_print(f"Failed to launch Settings GUI: {e}")

    def exit_action(self, icon, item):
        if self.settings_process:
            try: self.settings_process.terminate()
            except: pass
        icon.visible = False
        icon.stop() 
        os._exit(0)

    def restart_app(self, reopen_settings=False):
        """Restarts the entire application, optionally re-opening settings."""
        log_print(f"Restarting Privox (reopen_settings={reopen_settings})...")
        
        # Cleanup
        if self.icon:
            self.icon.stop()
        
        if getattr(sys, 'frozen', False):
            args = [sys.executable]
        else:
            args = [sys.executable, sys.argv[0]]
            
        if reopen_settings:
            args.append("--settings")
        
        # Give OS a moment to release file handles/mutex if needed
        # But os.execv replaces the process, so it should be fine.
        # However, subprocess is safer for avoiding mutex race conditions on Windows.
        subprocess.Popen(args, cwd=BASE_DIR, shell=False)
        os._exit(0)

    def reconnect_action(self, icon, item):
        log_print("User requested audio reconnect...")
        self.start_audio_stream()

    def toggle_startup(self, icon, item):
        if sys.platform != 'win32':
            log_print("Auto-launch is only supported on Windows.")
            return

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "Privox"
        # If frozen, use executable path. If script, use python + script path (less reliable for auto-start without wrapper)
        # But user wants this for the built exe mainly.
        exe_path = sys.executable 
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if item.checked: # Currently checked, so turn OFF
                 try:
                    winreg.DeleteValue(key, app_name)
                    log_print("Auto-launch disabled.")
                 except FileNotFoundError:
                    pass
            else: # Currently unchecked, so turn ON
                 winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
                 log_print(f"Auto-launch enabled. Path: {exe_path}")
            winreg.CloseKey(key)
        except Exception as e:
            log_print(f"Error checking startup status: {e}")

    def check_startup_status(self, item):
        if sys.platform != 'win32':
            return False
            
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "Privox"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, app_name)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def toggle_hotkey(self):
        """Toggle recording triggered by hotkey (manual listener)."""
        # Wake up detection
        if not self.heavy_models_loaded:
            if not self.pending_wakeup:
                log_print("Wake up detected. Pre-loading models...")
                self.pending_wakeup = True
                threading.Thread(target=self.load_heavy_models, daemon=True).start()
            return

        if not self.vad_model or self.asr_model is None:
            log_print("Ignored Hotkey: Models not fully loaded.")
            self.update_status("INITIALIZING")
            self.sound_manager.play_error()
            return

        if not self.mic_active:
            log_print("Hotkey pressed while microphone is inactive. Attempting audio reconnect...")
            self.start_audio_stream()
            if not self.mic_active:
                log_print("Ignored Hotkey: No Microphone Active")
                self.sound_manager.play_error()
                return
            
        if not self.is_listening:
            # If it's currently processing an old prompt, clicking the hotkey again should start a NEW recording gracefully.
            if self.ui_state == "PROCESSING":
                 log_print("Interrupting current processing to start new recording.")
            self.start_listening()
        else:
            self.stop_listening()

    def headless_ipc_loop(self):
        """Reads stdin from the Swift parent process for IPC commands."""
        log_print("Started Headless IPC Loop listening on stdin.")
        while self.running:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                command = line.strip().upper()
                if command == "QUIT":
                    log_print("IPC Command: QUIT received.")
                    self.running = False
                    os._exit(0)
                elif command == "TOGGLE" or command == "RECORD":
                    log_print(f"IPC Command: {command} received. Toggling recording...")
                    self.toggle_hotkey()
                elif command == "RECONNECT_AUDIO":
                    log_print("IPC Command: RECONNECT_AUDIO received. Restarting microphone stream...")
                    self.start_audio_stream()
                elif command == "RELOAD_CONFIG":
                    log_print("IPC Command: RELOAD_CONFIG received. Reloading preferences...")
                    self.load_config()
                    if self.model_reload_requested or not self.heavy_models_loaded:
                        log_print("Config change requires model initialization. Restarting model loader...")
                        self.update_status("INITIALIZING")
                        threading.Thread(target=self.load_heavy_models, daemon=True).start()
            except Exception as e:
                log_print(f"IPC Read Error: {e}")
                time.sleep(1)

    def run(self):
        # Start Threads
        threading.Thread(target=self.processing_loop, daemon=True).start()
        
        # --- Headless Mode ---
        if self.headless:
            log_print("Running in headless mode. Bypassing PyStray and Pynput.")
            self.headless_ipc_loop()
            return
        
        # --- GUI Mode (Windows/Linux) ---
        # Single Instance Mutex Check (Windows)
        self.mutex_handle = None
        if sys.platform == 'win32':
            mutex_name = "Global\\Privox_SingleInstance_Mutex"
            self.mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
            last_error = ctypes.windll.kernel32.GetLastError()
            
            # ERROR_ALREADY_EXISTS = 183
            if last_error == 183:
                log_print("Another instance of Privox is already running. Exiting.")
                if self.mutex_handle:
                    ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
                
                # POPUP to let user know why it's invisible
                ctypes.windll.user32.MessageBoxW(0, "Privox is already running in the background.\nCheck your system tray or Task Manager.", "Privox", 0x40)
                sys.exit(0)
            
            log_print("Acquired single-instance mutex.")

        # Setup Tray Menu
        menu = pystray.Menu(
            pystray.MenuItem('Settings...', self.show_settings_gui),
            pystray.MenuItem('Exit', self.exit_action)
        )
        
        # Create Icon
        image = self.draw_flat_line(None)
        self.icon = pystray.Icon("Privox", image, "Privox: Initializing...", menu)
        
        # Initial tooltip update
        self.update_tray_tooltip()
        
        # Pass icon to grammar checker for notifications immediately
        self.grammar_checker.icon = self.icon

        print("System Tray started. Check your taskbar.")
        
        threading.Thread(target=self.animation_loop, daemon=True).start()
        
        # Start Keyboard Listener (Manual Listener for better compatibility)
        log_print("Starting Keyboard Listener...")
        try:
            self.keyboard_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
            self.keyboard_listener.start()
            time.sleep(0.2)
            if not self.keyboard_listener.is_alive():
                raise RuntimeError("Keyboard listener thread failed to start.")
            log_print("Keyboard Listener started.")
        except Exception as e:
            log_print(f"Keyboard Listener failed: {e}")
            self.loading_status = "Hotkey listener failed (check Accessibility permission)"
            self.update_status("ERROR")
        
        # Run Icon (Native Loop)
        log_print("Starting Tray Icon Loop...")
        
        # Check if we should auto-open settings
        if "--settings" in sys.argv:
            log_print("Auto-opening settings as requested...")
            self.show_settings_gui(self.icon, None)

        self.icon.run()

if __name__ == "__main__":
    try:
        # 3. Early GPU Check
        import torch
        gpu_detected = torch.cuda.is_available()
        
        logging.info("--- VoiceInputApp Startup ---")
        logging.info(f"Python Executable: {sys.executable}")
        logging.info(f"sys.path: {sys.path}")
        logging.info(f"GPU Support Detected: {gpu_detected}")
        if gpu_detected:
            logging.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            logging.warning("GPU NOT DETECTED early. Processing may be slow.")
        
        is_headless = "--headless" in sys.argv
        app = VoiceInputApp(headless=is_headless)
        app.run()
    except Exception as e:
        import traceback
        err_msg = f"Fatal Error on Startup:\n\n{e}\n\n{traceback.format_exc()}"
        logging.error(err_msg)
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Privox failed to start:\n\n{e}\n\nCheck privox_app.log for details.", "Privox Fatal Error", 0x10)
        sys.exit(1)
