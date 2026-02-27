import sys
import os

# --- 0. Hard Environment Isolation (MUST BE FIRST) ---
os.environ["PYTHONNOUSERSITE"] = "1"
import site
site.ENABLE_USER_SITE = False

import logging
import threading
import queue
import time
import json
import re
import gc
import concurrent.futures
import subprocess
from datetime import datetime, timedelta
import models_config
from huggingface_hub import HfApi
import platform

IS_MAC = (sys.platform == 'darwin' or platform.system() == 'Darwin')
IS_WIN = (sys.platform == 'win32' or platform.system() == 'Windows')

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
    import pystray
    from PIL import Image, ImageDraw
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
        self.enabled = enabled and (winsound is not None)
        self.lock = threading.Lock()

    def _play(self, freq, duration):
        if self.enabled:
            try:
                with self.lock:
                    winsound.Beep(freq, duration)
            except Exception as e:
                log_print(f"Sound Error: {e}")

    def play_start(self):
        if self.enabled:
            threading.Thread(target=self._play, args=(1000, 200), daemon=True).start()

    def play_stop(self):
        if self.enabled:
            threading.Thread(target=self._play, args=(750, 200), daemon=True).start()

    def play_error(self):
        if self.enabled:
            threading.Thread(target=self._play, args=(400, 500), daemon=True).start()


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

    def load_model(self):
        if self.model:
            return

        repo_id = self.profile.get("repo_id", GRAMMAR_REPO)
        file_name = self.profile.get("file_name", GRAMMAR_FILE)
        is_reload = self._has_loaded_once  # True on wake-from-idle, False on first boot

        if IS_MAC:
            # --- macOS MLX Execution Path ---
            mlx_target_dir = os.path.join(APP_DATA_DIR, "models", "mlx-llama-3.2")
            if not os.path.exists(mlx_target_dir):
                self.loading_error = f"MLX Model missing: {mlx_target_dir}"
                log_print(self.loading_error)
                return
            
            try:
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
            return
            
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
                return

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
                        n_ctx=2048,
                        n_gpu_layers=n_gpu,
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

    def correct(self, text, is_command=False, language=None, language_prob=0.0, user_text=None):
        clean_text = text.strip()
        if not self.model or not clean_text:
            return text
            
        if len(clean_text) < 8 and clean_text.lower() not in [d.lower() for d in self.custom_dictionary]:
            log_print(f" [Short Input Skip] Input too short ({len(clean_text)} chars). Mirroring.")
            return text

        try:
            prompt_type = self.profile.get("prompt_type", "llama")

            if is_command:
                system_prompt = self.command_prompt or (
                    "You are Privox, an intelligent assistant. Execute the user's instruction perfectly. "
                    "Output ONLY the result inside <refined> and </refined> tags. Do not chat."
                )
                user_content = text
            else:
                core_directive = self.get_effective_prompt(language=language, language_prob=language_prob, user_text=user_text)
                system_prompt = models_config.get_system_formatter(language=language)
                user_content = f"[Core Directive]: {core_directive}\n[Transcript]: {text}\nOutput: "

            # Format based on model type
            if prompt_type == "t5":
                action = "Polish" if self.tone != "Natural" else "Fix grammar"
                prompt = f"{action}: {text}"
                stop_tokens = ["\n"]
            elif prompt_type == "chatml":
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
            max_tokens = min(2048, max(128, input_tokens_est * 4))

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
                    temperature=0.4,
                    repeat_penalty=1.2,
                    frequency_penalty=0.5,
                    top_p=0.9,
                    min_p=0.01,
                )
                raw_response = output['choices'][0]['text'].strip()
                
            if prompt_type == "t5":
                return raw_response

            # Extract text purely from inside the <refined> tags 
            import re
            match = re.search(r'<refined>(.*?)</refined>', raw_response, flags=re.DOTALL | re.IGNORECASE)
            
            result = None
            if match:
                log_print("Regex extracted <refined> block successfully.")
                result = match.group(1).strip()
            else:
                log_print("Warning: Model failed to use <refined> tags. Using raw output.")
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
