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
import hashlib
import concurrent.futures
import subprocess
import torch
from datetime import datetime, timedelta
import models_config
from huggingface_hub import HfApi
if sys.platform == 'win32':
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

# Simplified Path Logic: Trust Pixi environment but handle DLLs if needed
if sys.platform == 'win32':
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
    log_print("Importing Llama components...")
    from llama_cpp import Llama
    log_print("Llama import successful.")
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
        
        # Native Popup for visibility
        if sys.platform == 'win32' and not getattr(sys, 'frozen', False):
             # Only show popup in dev mode for now to avoid annoying users, 
             # OR we can show it if we explicitly want GPU.
             pass
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
MIN_SPEECH_DURATION_MS = 400
SPEECH_PAD_MS = 500

# Models
# Models
WHISPER_SIZE = "distil-large-v3" 
WHISPER_REPO = "Systran/faster-distil-whisper-large-v3"
ASR_BACKEND = "whisper" # Default: whisper or sensevoice

# Llama 3.2 3B Instruct
GRAMMAR_REPO = "bartowski/Llama-3.2-3B-Instruct-GGUF"
GRAMMAR_FILE = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"


class SoundManager:
    def __init__(self, enabled=True):
        self.enabled = enabled and (winsound is not None)
        self.lock = threading.Lock()

    def _play(self, freq, duration):
        if self.enabled:
            # Using a lock ensures beeps don't collide if triggered rapidly
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

    def load_model(self):
        if self.model:
            return

        repo_id = self.profile.get("repo_id", GRAMMAR_REPO)
        file_name = self.profile.get("file_name", GRAMMAR_FILE)

        # 1. Check Local "models" folder (Offline Mode)
        local_model_path = os.path.join(BASE_DIR, "models", file_name)
        if os.path.exists(local_model_path):
            log_print(f"Found local model: {local_model_path}")
            model_path = local_model_path
        else:
            try:
                # 2. Check/Download from Hugging Face
                log_print(f"Checking Hugging Face for Refiner Model ({repo_id})...")
                
                # First try to get it from cache or defined local dir
                try:
                    model_path = hf_hub_download(
                        repo_id=repo_id, 
                        filename=file_name, 
                        local_files_only=True
                    )
                    log_print(f"Found in Hugging Face cache: {model_path}")
                except Exception:
                    log_print(f"Model not in cache. Downloading {file_name} from {repo_id}...")
                    local_dir = os.path.join(BASE_DIR, "models")
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
                    if f_size < 100 * 1024**2: # A 3B model should be > 200MB even at extreme quantization
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
            # Heavy Import: Llama
            log_print("Importing llama_cpp...")
            try:
                import llama_cpp
                log_print(f"llama-cpp-python Version: {getattr(llama_cpp, '__version__', 'Unknown')}")
                # Log the system info string - this tells us if CUDA is actually compiled in
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

            def _safe_llama_init(m_path, n_gpu):
                try:
                    return Llama(
                        model_path=m_path,
                        n_ctx=2048,
                        n_gpu_layers=n_gpu,
                        verbose=True,
                        n_threads=os.cpu_count() // 2 if os.cpu_count() else 4
                    )
                except (AssertionError, RuntimeError) as e:
                    # Broaden to RuntimeError because GGUF loading failures often manifest there too
                    log_print(f"CRITICAL: Llama initialization failed ({type(e).__name__}). File likely corrupt.")
                    if os.path.exists(m_path):
                        # Verify file size - if it's very small it's definitely a failed download
                        size_mb = os.path.getsize(m_path) / (1024 * 1024)
                        log_print(f"Removing corrupt model file: {m_path} ({size_mb:.1f} MB)")
                        try: os.remove(m_path)
                        except: pass
                    return None

            # Assertive GPU Offloading
            is_gpu = torch.cuda.is_available()
            n_gpu = 99 if is_gpu else 0
            
            log_print(f"Loading Llama (GPU={is_gpu}, layers={n_gpu})...")
            self.model = _safe_llama_init(model_path, n_gpu)
            
            if self.model is None:
                # First attempt failed and file was removed. Trigger redownload.
                log_print("Model file removed. Restarting load sequence to trigger redownload...")
                return self.load_model()

            # Handle internal llama-cpp failure that might have returned without raising but broke state
            # (Though _safe_llama_init usually catches the actual error)
            
            log_print(f"Done. (GPU Acceleration: {'ENABLED' if is_gpu else 'DISABLED'})")
        except Exception as e:
            err_trace = traceback.format_exc()
            log_print(f"\nError loading Grammar Model: {e}\n{err_trace}")
            self.loading_error = str(e)
            # Check for another AssertionError in the fallback as well
            if "AssertionError" in str(e):
                 log_print(f"Corruption detected in fallback. Removing {model_path} and retrying.")
                 try:
                    if os.path.exists(model_path):
                        os.remove(model_path)
                 except: pass
                 return self.load_model()

            if sys.platform == 'win32':
                 show_modern_error("Privox Model Error", f"Error loading Grammar Model (Llama): {e}", f"Traceback:\n{err_trace[:500]}")

    def get_effective_prompt(self, language=None, language_prob=0.0):
        """Constructs a composite prompt with hidden overrides.
        Layer 1: Core Safety/Format (Hidden)
        Layer 2: User Instructions (Visible in GUI)
        Layer 3: Late-Binding Overrides (Hidden, conditional)
        """
        key = f"{self.character}|{self.tone}"
        user_text = self.custom_prompts.get(key, "").strip()
        
        # Layer 1: Core System Directives (Global Critical Rules)
        directive = "REFINE TRANSCRIPT: Provide a clean, accurate version of the ASR input in its ORIGINAL LANGUAGE."
        
        # Language Hinting (Robust Multilingual Support)
        # Only inject specific language directive if confidence is high (> 0.4)
        if language and language != "en" and language_prob > 0.4:
            lang_name = models_config.ISO_LANGUAGE_MAP.get(language, language)
            directive = f"REFINE TRANSCRIPT: PROVIDE A CLEAN {lang_name.upper()} VERSION. DO NOT TRANSLATE TO ENGLISH."

        prompt = f"{directive}\n\n{models_config.CRITICAL_RULES}"
        
        dict_str = ", ".join(self.custom_dictionary)
        if dict_str:
            prompt += f"Specific Jargon/Hints: {dict_str}\n"

        if self.context_buffer:
            prompt += f"\n[Previous Context (For Continuity Only - Do NOT transcribe this again)]:\n{self.context_buffer}\n"

        # Layer 2: User-Edited Instructions
        if user_text:
            prompt += f"\n### ADDITIONAL USER INSTRUCTIONS ###\n{user_text}\n"

        # Layer 3: Late-Binding Overrides (Ensures Dropdown Priority)
        # We append these LAST so they win any conflicts in the LLM's attention.
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
            prompt += f"\n### SYSTEM OVERRIDES (HIGHEST PRIORITY) ###{overrides}\n"

        return prompt

    def correct(self, text, is_command=False, language=None, language_prob=0.0):
        # 1. Pre-processing Guardrail: Skip LLM for very short or empty inputs
        # (Unless it's a known keyword in the custom dictionary)
        clean_text = text.strip()
        if not self.model or not clean_text:
            return text
            
        if len(clean_text) < 8 and clean_text.lower() not in [d.lower() for d in self.custom_dictionary]:
            log_print(f" [Short Input Skip - Mirroring: '{clean_text}']")
            return text

        try:
            prompt_type = self.profile.get("prompt_type", "llama")

            if is_command:
                # Agent Mode
                system_prompt = self.command_prompt or (
                    "You are Privox, an intelligent assistant. Execute the user's instruction perfectly. "
                    "Output ONLY the result inside <refined> and </refined> tags. Do not chat."
                )
                user_content = text
            else:
                # Use the new robust Wrapper Structure
                core_directive = self.get_effective_prompt(language=language, language_prob=language_prob)
                # Dynamically select few-shot examples matched to the detected language
                system_prompt = models_config.get_system_formatter(language=language)
                user_content = f"[Core Directive]: {core_directive}\n[Transcript]: {text}\nOutput: "

            # Format based on model type
            if prompt_type == "t5":
                # CoEdit / T5 style: simple instruction + input (Does not use XML wrapping naturally)
                action = "Polish" if self.tone != "Natural" else "Fix grammar"
                prompt = f"{action}: {text}"
                stop_tokens = ["\n"]
            else:
                # Llama 3 / Qwen / Mistral style format
                prompt = (
                    f"<|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|>"
                    f"<|start_header_id|>user<|end_header_id|>\n\n{user_content}<|eot_id|>"
                    "<|start_header_id|>assistant<|end_header_id|>\n\n"
                )
                stop_tokens = ["<|eot_id|>"]
            
            # 2. Proportional max_tokens cap to prevent runaway generation
            # A refined output should never be drastically longer than the input.
            input_tokens_est = max(len(clean_text) // 3, len(clean_text.split()))
            max_tokens = min(1024, max(64, input_tokens_est * 4))

            output = self.model(
                prompt, 
                max_tokens=max_tokens,
                stop=stop_tokens, 
                echo=False,
                temperature=0.3,
            )
            raw_response = output['choices'][0]['text'].strip()
                
            # If standard instruction model (T5), just return the raw string
            if prompt_type == "t5":
                self.context_buffer = (self.context_buffer + " " + raw_response).strip()[-2000:]
                return raw_response

            # If Llama/Qwen, extract text purely from inside the <refined> tags 
            import re
            match = re.search(r'<refined>(.*?)</refined>', raw_response, flags=re.DOTALL | re.IGNORECASE)
            
            result = None
            if match:
                log_print("Regex extracted <refined> block successfully.")
                result = match.group(1).strip()
            else:
                # Fallback if the model hallucinated and forgot the tags.
                log_print("Warning: Model failed to use <refined> tags. Using raw output.")
                result = raw_response

            # 3. Post-generation Hallucination Validator
            result = self._validate_output(clean_text, result)

            self.context_buffer = (self.context_buffer + " " + result).strip()[-2000:]
            return result
        except Exception as e:
            log_print(f"Grammar Check Error: {e}")
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
        "focus on software engineering jargon",
        "do not simplify technical abbreviations",
        "do not add new semantic information",
        "output only the processed text",
        "remove fillers",
        "absolute no conversation",
    ]

    def _validate_output(self, original, refined):
        """Post-generation hallucination check. Returns original if output looks fabricated."""
        if not refined:
            return original

        orig_len = len(original)
        ref_len = len(refined)

        # Check 1: Output explosion (refined is absurdly longer than input)
        if orig_len > 0 and ref_len > max(200, orig_len * 5):
            log_print(f" [Hallucination Guard] Output explosion: {orig_len} -> {ref_len} chars. Returning original.")
            return original

        # Check 2: Prompt-echo detection (output contains system prompt fragments)
        refined_lower = refined.lower()
        for fp in self._PROMPT_FINGERPRINTS:
            if fp in refined_lower:
                log_print(f" [Hallucination Guard] Prompt echo detected: '{fp}'. Returning original.")
                return original

        return refined

    def unload_model(self):
        if self.model:
            del self.model
            self.model = None
            log_print("Grammar Model Unloaded.")

class VoiceInputApp:
    def __init__(self):
        log_print("Initializing Voice Input Application...")
        
        self.keyboard_controller = keyboard.Controller()
        
        # Load Config
        self.hotkey = keyboard.Key.f8 # Default
        self.sound_enabled = True
        self.auto_stop_enabled = True
        self.silence_timeout_ms = 10000
        self.custom_dictionary = []
        self.custom_prompts = {}
        self.character = "Writing Assistant"
        self.tone = "Natural"
        self.dictation_prompt = None
        self.command_prompt = None
        
        self.sound_manager = SoundManager(self.sound_enabled)
        
        # State
        self.q = queue.Queue()
        self.audio_buffer = [] 
        self.is_listening = False
        self.is_speaking = False
        self.running = True
        self.stream = None
        self.mic_active = False
        
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
        
        # Tray Icon (placeholder)
        self.icon = None

        # VRAM Saver State
        self.last_activity_time = time.time()
        self.heavy_models_loaded = False
        self.model_lock = threading.Lock()
        self.vram_timeout = 60 # Seconds before unloading
        self.pending_wakeup = False # Auto-start recording after loading?
        
        # Hotkey support
        self.hotkey_str = "f8"
        self.target_mods = set() # e.g. {'ctrl', 'shift'}
        self.target_key = "f8"
        self.active_mods = set()
        self.settings_process = None
        self.last_toggle_time = 0 # Hotkey de-bounce timer
        self.last_config_reload_time = 0 # Cooldown for config polling
        self._last_prefs_hash = None # Hash-based change detection
        
        # Load Config (FINAL STEP of init to prevent overwriting by defaults)
        self.load_config()
        
        # Set initial state to show loading spinner
        self.update_status("INITIALIZING")

        # Start loading threads
        threading.Thread(target=self.initial_load, daemon=True).start()

    def initial_load(self):
        # Run model cleanup FIRST to avoid race conditions with loading
        try:
            prefs_path = os.path.join(BASE_DIR, ".user_prefs.json")
            if os.path.exists(prefs_path):
                with open(prefs_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
                cleanup_days = prefs.get("model_cleanup_days", 7)
                if cleanup_days > 0:
                    self.cleanup_stale_models(cleanup_days)
        except: pass

        self.loading_status = "Loading VAD..."
        self.update_tray_tooltip()
        self.load_vad()
        
        # We load heavy models initially so it's ready for first use, 
        # then let the saver handle unloading if unused.
        self.load_heavy_models()

    def load_vad(self):
        # 1. Load VAD Model (Silero)
        log_print("Loading Silero VAD...", end="", flush=True)
        try:
            # Force Torch Hub to use the local models folder for VAD
            hub_dir = os.path.join(BASE_DIR, "models", "hub")
            if not os.path.exists(hub_dir):
                os.makedirs(hub_dir, exist_ok=True)
            torch.hub.set_dir(hub_dir)
            
            self.vad_model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                                  model='silero_vad',
                                                  force_reload=False,
                                                  onnx=False)
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
            self.update_tray_tooltip()
            return

    def load_heavy_models(self):
        """Concurrent loading of ASR and Grammar models to minimize wake-up latency."""
        with self.model_lock:
            if self.heavy_models_loaded:
                return

            log_print("Loading Heavy Models (Wake up)...")
            self.loading_status = "Loading Models..."
            self.update_tray_tooltip()

            def load_grammar():
                try:
                    self.grammar_checker.load_model()
                    # Track LLM usage here
                    self.track_model_usage(self.current_refiner)
                    return True
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

            # Use ThreadPoolExecutor for concurrent model loading
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(load_grammar), executor.submit(load_asr)]
                results = [f.result() for f in futures]

            if not results[1]: # Whisper is mandatory
                log_print("CRITICAL: ASR model failed to load.")
                self.loading_status = "ASR Load Error"
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
            else:
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
            self.update_tray_tooltip()
            self.update_status("SLEEP") # Trigger flat line animation
            log_print("Models Unloaded. VRAM released.")

    def track_model_usage(self, model_name):
        """Update last_used timestamp for the given model in hidden prefs."""
        try:
            prefs_path = os.path.join(BASE_DIR, ".user_prefs.json")
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

    def load_config(self):
        """Unified configuration loader with split protection and migration."""
        try:
            config_path = os.path.join(BASE_DIR, "config.json")
            prefs_path = os.path.join(BASE_DIR, ".user_prefs.json")
            
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
                "custom_dictionary", "current_refiner", "whisper_model",
                "asr_library", "llm_library"
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
            if prefs.get("current_refiner") == "CoEdit Large (T5)" and not prefs.get("_migrate_llama_3_2"):
                prefs["current_refiner"] = models_config.DEFAULT_LLM
                prefs["_migrate_llama_3_2"] = True
                with open(prefs_path, "w", encoding="utf-8") as f:
                    json.dump(prefs, f, indent=4)
            
            # Update mtime tracker immediately to avoid self-triggering polish loop
            if os.path.exists(prefs_path):
                self._last_prefs_mtime = os.path.getmtime(prefs_path)

            # --- 4. Apply Settings ---
            # Parse hotkey_str (e.g. "ctrl+shift+k")
            new_hotkey_str = prefs.get("hotkey", "f8").lower()
            hotkey_changed = new_hotkey_str != getattr(self, 'hotkey_str', '')
            self.hotkey_str = new_hotkey_str
            
            parts = [p.strip() for p in self.hotkey_str.split('+')]
            self.target_mods = set([p for p in parts if p in ["ctrl", "shift", "alt"]])
            self.target_key = parts[-1] if parts else "f8"
            log_print(f"Parsed Hotkey: Mods={self.target_mods}, Key={self.target_key}")
            
            # UPDATE HOTKEY IN-PLACE (No listener restart)
            if hotkey_changed:
                log_print(f"Hotkey changed ({getattr(self, 'hotkey_str_old', 'None')} -> {self.hotkey_str}). Updating in-place...")
                self.hotkey_str_old = self.hotkey_str
                # Listener already uses target_mods/target_key, so updating them is enough
                # We also clear active_mods to prevent "stuck" combinations during the transition
                self.active_mods.clear()
            
            # Update Tray ToolTip context
            self.update_tray_tooltip()
            
            self.last_config_reload_time = time.time()
            # Update hash tracker and mtime after all potential logic is done
            if os.path.exists(prefs_path):
                 with open(prefs_path, "rb") as f:
                     self._last_prefs_hash = hashlib.md5(f.read()).hexdigest()
                 self._last_prefs_mtime = os.path.getmtime(prefs_path)
                
            # Update Tray ToolTip context
            self.update_tray_tooltip()

            self.sound_enabled = prefs.get("sound_enabled", True)
            self.auto_stop_enabled = prefs.get("auto_stop_enabled", True)
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
            self.vram_timeout = max(5, prefs.get("vram_timeout", 60))
            self.character = prefs.get("character", "Writing Assistant")
            self.tone = prefs.get("tone", "Natural")
            self.custom_prompts = prefs.get("custom_prompts", {})
            self.current_refiner = prefs.get("current_refiner", models_config.DEFAULT_LLM)
            
            # Library Loading (Prefer User Prefs > Config > Default)
            self.asr_library = prefs.get("asr_library", config.get("asr_library", models_config.ASR_LIBRARY))
            self.llm_library = prefs.get("llm_library", config.get("llm_library", models_config.LLM_LIBRARY))

            # Filter libraries
            self.asr_library = [m for m in self.asr_library if self.verify_model(m, "asr")]
            self.llm_library = [m for m in self.llm_library if self.verify_model(m, "llm")]

            # Sync Current Profile from Library
            profile = {}
            for p in self.llm_library:
                if p["name"] == self.current_refiner:
                    profile = {
                        "repo_id": p.get("repo_id"),
                        "file_name": p.get("file_name"),
                        "prompt_type": p.get("prompt_type"),
                        "description": p.get("description", "")
                    }
                    # REMOVED recursive usage tracking here
                    break
            
            if hasattr(self, 'grammar_checker'):
                self.grammar_checker.profile = profile
                
                # Clear context cache if personality/tone changes abruptly to prevent bleed
                if self.grammar_checker.character != self.character or self.grammar_checker.tone != self.tone:
                     self.grammar_checker.context_buffer = ""
                     
                self.grammar_checker.character = self.character
                self.grammar_checker.tone = self.tone
                self.grammar_checker.custom_prompts = self.custom_prompts
                self.grammar_checker.custom_dictionary = self.custom_dictionary
            
            # ASR Model resolution
            global WHISPER_SIZE, WHISPER_REPO, ASR_BACKEND
            old_whisper = WHISPER_SIZE
            self.active_asr_name = prefs.get("whisper_model", models_config.DEFAULT_ASR)
            active_asr = self.active_asr_name
            
            # Find in library
            WHISPER_REPO = "Systran/faster-distil-whisper-large-v3" # Defaults
            WHISPER_SIZE = "distil-large-v3"

            for asr in self.asr_library:
                if asr["name"] == active_asr:
                    # Sync with library technical names
                    WHISPER_REPO = asr.get("whisper_repo") or asr.get("repo")
                    WHISPER_SIZE = asr.get("whisper_model") or asr.get("name")
                    # REMOVED recursive usage tracking here
                    break

            ASR_BACKEND = "whisper"
            
            # REMOVED cleanup_stale_models from here to prevent recursive reload loops

        except Exception as e:
            log_print(f"Error loading config: {e}")
            traceback.print_exc()

    def verify_model(self, model_data, model_type):
        """Verifies if a model repository or local path exists."""
        repo = model_data.get("repo")
        local_path = model_data.get("local_path")
        
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

        # 2. Check HuggingFace Repo (Fast head request)
        if repo:
            try:
                # We use a cached check if possible to avoid hitting HF on every startup
                # For now, a simple check is fine. In production we might skip this unless config changed.
                api = HfApi()
                api.repo_info(repo_id=repo)
                return True
            except:
                log_print(f"Verification Failed for model: {repo}")
                return False
        
        return False

    def cleanup_stale_models(self, days):
        """Deletes models that haven't been used in X days."""
        try:
            prefs_path = os.path.join(BASE_DIR, ".user_prefs.json")
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
        # status: READY, RECORDING, PROCESSING, ERROR, LOADING, SLEEP
        self.ui_state = status
        
        # Immediate text update (icon handled by loop or here if static)
        if not self.icon: return

        if status == "READY":
            hk_display = getattr(self, 'hotkey_str', 'F8').upper()
            self.icon.title = f"Privox: Ready ({hk_display})"
        elif status == "RECORDING":
            self.icon.title = "Privox: Listening..."
        elif status == "PROCESSING":
            self.icon.title = "Privox: Processing..."
        elif status == "DOWNLOADING":
            self.icon.title = "Privox: Downloading Model..."
        elif status == "ERROR":
            self.icon.title = "Privox: Error/No Mic"
        elif status == "SLEEP":
             self.icon.title = "Privox: Sleeping (VRAM Saver Active)"

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
                    
                elif self.ui_state in ["PROCESSING", "DOWNLOADING", "INITIALIZING"]:
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
            keyboard.Key.alt: "alt", keyboard.Key.alt_l: "alt", keyboard.Key.alt_gr: "alt"
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
            keyboard.Key.alt: "alt", keyboard.Key.alt_l: "alt", keyboard.Key.alt_gr: "alt"
        }
        if key in mod_map:
            val = mod_map[key]
            if val in self.active_mods:
                self.active_mods.remove(val)

    def start_listening(self):
        self.last_activity_time = time.time()
        log_print("\n[Start Listening]", flush=True)
        self.sound_manager.play_start()
        self.is_listening = True
        self.is_speaking = False
        self.audio_buffer = []
        if self.vad_iterator:
            self.vad_iterator.reset_states()
        self.update_status("RECORDING")

    def stop_listening(self):
        log_print(" [Stopped]", flush=True)
        self.sound_manager.play_stop()
        self.is_listening = False
        self.update_status("PROCESSING")
        
        if len(self.audio_buffer) > 0:
            audio_segment = np.array(self.audio_buffer)
            # Run transcription in a separate thread so we don't block the keyboard listener!
            threading.Thread(target=self.transcribe, args=(audio_segment,), daemon=True).start()
        else:
             self.update_status("READY")
             
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
                self.update_status("READY")
                return

            if max_amp < 0.001: 
                log_print(f" [Audio too quiet - Ignored]")
                self.update_status("READY")
                return

            # Ensure models are loaded before transcribing
            if not self.heavy_models_loaded:
                log_print("Waiting for models to load...")
                self.load_heavy_models()
                if not self.asr_model:
                     log_print("ASR Model still missing after lazy load attempt.")
                     self.update_status("READY")
                     return

            log_print(f" Transcribing Using Backend: {ASR_BACKEND} (Model: {WHISPER_SIZE if ASR_BACKEND == 'whisper' else 'SenseVoiceSmall'})...", flush=True)
            t0 = time.time()
            
            raw_text = ""
            if ASR_BACKEND == "sensevoice":
                # SenseVoice/funasr
                results = self.asr_model.generate(
                    input=audio_data.astype(np.float32),
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
                    log_print(f"  Segment: [{segment.start:.2f}s -> {segment.end:.2f}s] '{segment.text}'")
                    seg_results.append(segment.text)
                
                raw_text = " ".join(seg_results).strip()
            
            t1 = time.time()
            log_print(f" [ASR Total Time: {t1 - t0:.3f}s] Joined Result: '{raw_text}'")
            
            if not raw_text:
                log_print(" [Empty Transcription Result]")
                self.update_status("READY")
                return

            # --- Logic for Command Mode (DISABLED FOR NOW) ---
            is_command = False
            command_text = raw_text
            
            # if raw_text.lower().startswith("privox"):
            #     is_command = True
            #     command_text = re.sub(r'^(privox)\s*,?\s*', '', raw_text, flags=re.IGNORECASE)
            #     log_print(f" [Command Mode Detected] Input: {command_text}")
            
            log_print(f" Refining format ({self.current_refiner})...")
            t2 = time.time()
            detected_lang = info.language if ASR_BACKEND == 'whisper' else None
            detected_prob = info.language_probability if ASR_BACKEND == 'whisper' else 0.0
            final_text = self.grammar_checker.correct(command_text, is_command=is_command, language=detected_lang, language_prob=detected_prob)
            t3 = time.time()
            log_print(f" [Grammar Time: {t3 - t2:.3f}s]")
            
            log_print(f"Output: {final_text}")
            log_print(f" [Total Time: {t3 - t0:.3f}s]")
            
            try:
                self.paste_text(final_text)
            except Exception as e:
                log_print(f"Typing Error: {e}")
                self.sound_manager.play_error()
                
        except Exception as e:
            log_print(f"ASR Error: {e}")
            self.sound_manager.play_error()
        finally:
            self.update_status("READY")

    def paste_text(self, text):
        try:
            original_clipboard = pyperclip.paste()
            pyperclip.copy(text)
            time.sleep(0.05) 
            with self.keyboard_controller.pressed(keyboard.Key.ctrl):
                self.keyboard_controller.press('v')
                self.keyboard_controller.release('v')
            time.sleep(0.2) 
            pyperclip.copy(original_clipboard)
        except Exception as e:
            log_print(f"Paste Error: {e}")
            self.keyboard_controller.type(text)

    def start_audio_stream(self):
        try:
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
        except Exception as e:
            log_print(f"Microphone Error: {e}")
            self.mic_active = False
            self.update_status("ERROR")
            self.sound_manager.play_error()

    def processing_loop(self):
        self.start_audio_stream()
            
        while self.running:
            # VRAM Saver Check
            if self.heavy_models_loaded and not self.is_listening and self.ui_state != "PROCESSING":
                if (time.time() - self.last_activity_time) > self.vram_timeout:
                    self.unload_heavy_models()

            # Config Polling (Hot-reload)
            try:
                prefs_path = os.path.join(BASE_DIR, ".user_prefs.json")
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
            self.sound_manager.play_error()
            return

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

    def run(self):
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
        
        # Start Threads
        threading.Thread(target=self.processing_loop, daemon=True).start()
        threading.Thread(target=self.animation_loop, daemon=True).start()
        
        # Start Keyboard Listener (Manual Listener for better compatibility)
        log_print("Starting Keyboard Listener...")
        self.keyboard_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.keyboard_listener.start()
        
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
        
        app = VoiceInputApp()
        app.run()
    except Exception as e:
        import traceback
        err_msg = f"Fatal Error on Startup:\n\n{e}\n\n{traceback.format_exc()}"
        logging.error(err_msg)
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Privox failed to start:\n\n{e}\n\nCheck privox_app.log for details.", "Privox Fatal Error", 0x10)
        sys.exit(1)
