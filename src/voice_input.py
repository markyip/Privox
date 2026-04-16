import sys
import os
import json

# --- 0. Hard Environment Isolation (MUST BE FIRST) ---
os.environ["PYTHONNOUSERSITE"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["RAYON_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# Hugging Face hub prints symlink limitations to stderr on Windows; avoid log spam.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
import site
site.ENABLE_USER_SITE = False

def _sanitize_user_site_paths():
    """Remove user-level site-packages from sys.path to avoid package shadowing."""
    sanitized = []
    removed = []
    # Identify the pixi environment root to avoid removing it
    pixi_root = os.environ.get("CONDA_PREFIX", ".pixi").replace("\\", "/").lower()
    
    for p in sys.path:
        if not p:
            sanitized.append(p)
            continue
        p_norm = p.replace("\\", "/").lower()
        
        # Detect typical user-site paths on Windows/Linux/Mac
        is_user_site = (
            ("appdata" in p_norm or "/python/" in p_norm or ".local/lib" in p_norm) 
            and "site-packages" in p_norm
        )
        
        # Detect shadowing: if it's a user site path and NOT inside our pixi/venv root, remove it.
        if is_user_site and pixi_root not in p_norm:
            removed.append(p)
            continue
        sanitized.append(p)
        
    sys.path[:] = sanitized
    return removed


_removed_user_site_paths = _sanitize_user_site_paths()


def _privox_install_root() -> str:
    """Directory containing config.json / .pixi / models (same rule as BASE_DIR below)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.normpath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- 1. DLL Registration & CUDA Pre-load (MUST BE BEFORE ANY 3RD PARTY IMPORTS) ---
if sys.platform == "win32":
    import ctypes
    from pathlib import Path
    
    # Pre-calculate root
    if getattr(sys, "frozen", False):
        _root = Path(sys.executable).parent
    else:
        _root = Path(__file__).parent.parent.absolute()
    
    # Register search paths
    for _d in [
        _root / ".pixi" / "envs" / "default" / "bin",
        _root / ".pixi" / "envs" / "default" / "Library" / "bin",
    ]:
        if _d.exists():
            os.add_dll_directory(str(_d))
            os.environ["PATH"] = str(_d) + os.pathsep + os.environ.get("PATH", "")

    # Pre-load CUDA DLLs explicitly to fix native crashes in ORT/CT2
    # We must do this before importing any ML libraries.
    sys.path.append(os.path.join(str(_root), "src"))
    try:
        from privox_runtime import pre_load_cuda_dlls
        pre_load_cuda_dlls()
    except Exception as _e_pre:
        print(f"CUDA Pre-load Error: {_e_pre}")

    # CUDA DLLs are now pinned by pre_load_cuda_dlls() above; 
    # we avoid creating a global Sentinel session to save VRAM headroom.

import logging
import threading
import queue
import time
import re
import gc
import hashlib
import concurrent.futures
import subprocess
import importlib
import warnings
from privox_runtime import (
    NO_TORCH,
    get_torch,
    cuda_is_available,
    cuda_device_name,
    cuda_device_total_memory_gib,
)

torch = get_torch()
if torch is not None:
    torch.set_num_threads(2)  # Constrain underlying OpenMP/MKL to avoid CPU spikes on start

# Downgrade noisy third-party warnings (nagisa SyntaxWarning; transformers generation hints).
warnings.filterwarnings(
    "ignore",
    message=r"invalid escape sequence",
    category=SyntaxWarning,
)
for _msg in (
    "The following generation flags are not valid",
    "Setting `pad_token_id` to `eos_token_id`",
):
    warnings.filterwarnings("ignore", message=_msg, category=UserWarning)
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

    is_frozen = getattr(sys, "frozen", False)

    # Dev: log file under project / exe folder. Packaged exe: no log file (NullHandler only).
    log_file = os.path.join(base_dir, "privox_app.log")
    log_level = logging.INFO
    log_format = "%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s"
    log_datefmt = "%Y-%m-%d %H:%M:%S"

    if is_frozen:
        _handlers: list[logging.Handler] = [logging.NullHandler()]
    else:
        _handlers = [logging.FileHandler(log_file, encoding="utf-8")]
        if sys.stdout:
            _handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        format=log_format,
        datefmt=log_datefmt,
        level=log_level,
        force=True,
        handlers=_handlers,
    )

    class _ThirdPartyNoiseFilter(logging.Filter):
        """Libraries sometimes log benign hints as ERROR; downgrade for readable logs."""

        def filter(self, record: logging.LogRecord) -> bool:
            if record.levelno != logging.ERROR:
                return True
            try:
                msg = record.getMessage()
            except Exception:
                return True
            if "generation flags are not valid" in msg:
                record.levelno = logging.WARNING
                record.levelname = "WARNING"
            return True

    for _h in logging.root.handlers:
        _h.addFilter(_ThirdPartyNoiseFilter())

    # Redirect stdout/stderr
    class LoggerWriter:
        def __init__(self, level):
            self.level = level

        @staticmethod
        def _is_llama_diagnostic(message_lower):
            noisy_prefixes = (
                "llama_", "llm_", "ggml_", "gguf", "cuda :", "device ", "model metadata:",
                "using gguf chat template:", "using chat eos_token:", "using chat bos_token:",
            )
            return (
                "llama" in message_lower and (
                    message_lower.startswith(noisy_prefixes)
                    or "not marked as eog" in message_lower
                    or "offloading" in message_lower
                    or "kv buffer size" in message_lower
                    or "compute buffer size" in message_lower
                    or "graph nodes" in message_lower
                )
            )

        @staticmethod
        def _stderr_downgrade(message_lower: str) -> str | None:
            """Map stderr lines that third parties print as 'errors' to a real log level name."""
            if "using cache found" in message_lower:
                return "info"
            if "generation flags are not valid" in message_lower:
                return "warning"
            if "pad_token_id" in message_lower and "eos_token_id" in message_lower:
                return "warning"
            # llama.cpp / GGML often prints GPU discovery to stderr; not application failures.
            if message_lower.startswith(("ggml_", "gguf")) or "ggml_cuda_init" in message_lower:
                return "info"
            if message_lower.startswith("device ") and (
                "nvidia" in message_lower
                or "amd" in message_lower
                or "compute capability" in message_lower
                or "vmm:" in message_lower
            ):
                return "info"
            # Transformers + tqdm emit weight-load progress to stderr; not failures.
            if "loading checkpoint shards" in message_lower or "checkpoint shard" in message_lower:
                return "info"
            # faster-whisper / huggingface_hub download bars use tqdm on stderr (model.bin, tokenizer.json, …).
            if "userwarning" in message_lower and "huggingface" in message_lower:
                return "warning"
            if "%|" in message_lower and any(
                x in message_lower
                for x in ("mb/s", "kb/s", "gb/s", "ib/s", "b/s", "it/s", "?b/s", "/1.", "/0.")
            ):
                return "info"
            if re.search(r"\[\d+:\d+", message_lower) and (
                "b/s" in message_lower or "it/s" in message_lower
            ):
                return "info"
            if re.search(
                r"(^|\s)(config|tokenizer|vocabulary|preprocessor_config)\.json|model\.bin|\.safetensors",
                message_lower,
            ) and "[" in message_lower and "]" in message_lower:
                return "info"
            return None

        def write(self, message):
            msg = message.strip()
            if not msg:
                return
            if self.level == logging.error:
                ml = msg.lower()
                tier = LoggerWriter._stderr_downgrade(ml)
                if tier == "info":
                    logging.info(msg)
                    return
                if tier == "warning":
                    logging.warning(msg)
                    return
                if self._is_llama_diagnostic(ml):
                    logging.info(msg)
                    return
            self.level(msg)

        def flush(self):
            pass

    if not is_frozen:
        sys.stdout = LoggerWriter(logging.info)
        sys.stderr = LoggerWriter(logging.error)

# Silence noisy external loggers
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

# Initialize logging IMMEDIATELY to catch import errors
setup_logging()

def log_print(msg, **kwargs):
    """Dev: print → LoggerWriter → logging + log file. Packaged exe: no log file and no stdout capture."""
    if getattr(sys, "frozen", False):
        return
    print(msg, **kwargs)


def transcription_logging_enabled() -> bool:
    """Packaged exe: do not persist ASR/refiner output or transcript-adjacent diagnostics to the log file."""
    if (os.environ.get("PRIVOX_LOG_TRANSCRIPTION") or "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return not getattr(sys, "frozen", False)


def log_transcription(msg, **kwargs):
    if transcription_logging_enabled():
        log_print(msg, **kwargs)


def _safe_json_load(path: str, label: str) -> dict:
    """Load JSON with BOM tolerance; on failure log path + preview and return {}."""
    raw = ""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = f.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except json.JSONDecodeError as e:
        preview = (raw[:400] if raw else "").replace("\r", "\\r").replace("\n", "\\n")
        log_print(
            f"Invalid JSON in {label} ({path}): {e}. "
            f"Fix the file (valid UTF-8, double-quoted keys, no trailing commas). Preview: {preview!r}"
        )
        return {}
    except OSError as e:
        log_print(f"Could not read {label} ({path}): {e}")
        return {}


def _contains_cjk_char(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in (s or ""))


def _transcript_mixes_cjk_and_latin(text: str | None) -> bool:
    """True when ASR mixes Latin-letter words with CJK, Japanese kana, or Korean Hangul."""
    if not (text and str(text).strip()):
        return False
    if not re.search(r"[A-Za-z]{2,}", text):
        return False
    if _contains_cjk_char(text):
        return True
    for c in text:
        o = ord(c)
        if 0x3040 <= o <= 0x30FF or 0xAC00 <= o <= 0xD7AF:  # Hiragana/Katakana, Hangul syllables
            return True
    return False


def _apply_chinese_output_script(text: str | None, use_simplified: bool) -> str:
    """Normalize Chinese in final text: Traditional by default, or Simplified when user opts in (zhconv)."""
    if not (text and str(text).strip()):
        return text or ""
    if not _contains_cjk_char(text):
        return text
    try:
        import zhconv
    except ImportError:
        return text
    try:
        return zhconv.convert(text, "zh-hans" if use_simplified else "zh-hant")
    except Exception:
        return text


# English cardinal words → digits for dictated lists (e.g. "one, two, three, four" → "1, 2, 3, 4").
_EN_CARDINAL_WORDS: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
}
_EN_CARDINAL_ALT = "|".join(sorted(_EN_CARDINAL_WORDS.keys(), key=len, reverse=True))
_EN_SPOKEN_LIST_RE = re.compile(
    rf"(?<![\w/])(?P<body>(?:{_EN_CARDINAL_ALT})(?:\s*(?:,|\band\b)\s*(?:{_EN_CARDINAL_ALT}))+)",
    re.IGNORECASE,
)
# Space-separated small cardinals only (three+ in a row); avoids "no one" style false positives.
_EN_SMALL_ALT = "one|two|three|four|five|six|seven|eight|nine|ten"
_EN_SPOKEN_SPACE_RUN_RE = re.compile(
    rf"(?<![\w])(?P<body>(?:{_EN_SMALL_ALT})(?:\s+(?:{_EN_SMALL_ALT})){{2,}})(?!\w)",
    re.IGNORECASE,
)


def _convert_english_spoken_digit_lists(text: str) -> str:
    """Turn comma/'and'-linked or space-run spoken cardinals into Arabic numerals."""
    if not text:
        return text

    sep_re = re.compile(r"\s*,\s*|\s+\band\b\s+", re.IGNORECASE)

    def _repl_comma_and(m: re.Match) -> str:
        body = m.group("body")
        parts = [p.strip().lower() for p in sep_re.split(body) if p.strip()]
        if len(parts) < 2:
            return m.group(0)
        digits: list[str] = []
        for p in parts:
            if p not in _EN_CARDINAL_WORDS:
                return m.group(0)
            digits.append(_EN_CARDINAL_WORDS[p])
        return ", ".join(digits)

    out = _EN_SPOKEN_LIST_RE.sub(_repl_comma_and, text)

    def _repl_space_run(m: re.Match) -> str:
        body = m.group("body")
        parts = body.split()
        if len(parts) < 3:
            return m.group(0)
        digits: list[str] = []
        for p in parts:
            pl = p.lower()
            if pl not in _EN_CARDINAL_WORDS:
                return m.group(0)
            digits.append(_EN_CARDINAL_WORDS[pl])
        return ", ".join(digits)

    return _EN_SPOKEN_SPACE_RUN_RE.sub(_repl_space_run, out)


def _finalize_refiner_text(text: str | None, use_simplified_zh: bool) -> str:
    """Spoken English number lists → digits, then Chinese script normalization."""
    if text is None:
        return ""
    t = _convert_english_spoken_digit_lists(str(text))
    return _apply_chinese_output_script(t, use_simplified_zh)


_numpy_metadata_shim_installed = False


def ensure_numpy_version_visible_to_metadata():
    """HuggingFace transformers checks numpy via importlib.metadata.version('numpy').
    Mixed conda/pip installs sometimes leave importable numpy but broken/missing dist-info,
    which yields got_ver=None and crashes ctranslate2/faster-whisper import."""
    global _numpy_metadata_shim_installed
    if _numpy_metadata_shim_installed:
        return
    import importlib.metadata as im
    try:
        v = im.version("numpy")
        if v:
            _numpy_metadata_shim_installed = True
            return
    except Exception:
        pass
    try:
        import numpy as np
        nv = str(np.__version__)
    except Exception as e:
        log_print(f"WARNING: Could not read numpy version for metadata shim: {e}")
        return
    _orig = im.version

    def _version_with_numpy_fallback(dist_name, *, _o=_orig, _nv=nv):
        if dist_name == "numpy":
            try:
                got = _o(dist_name)
                if got:
                    return got
            except Exception:
                pass
            return _nv
        return _o(dist_name)

    im.version = _version_with_numpy_fallback  # type: ignore[assignment]
    _numpy_metadata_shim_installed = True
    log_print(
        "NOTICE: Patched importlib.metadata.version('numpy') to use numpy.__version__ "
        f"({nv}); consider `pixi install` or reinstalling numpy to fix package metadata."
    )


log_print("Starting Privox...")

if sys.platform == 'win32':
    # --- Single Instance Enforcement (Prevents model/log corruption) ---
    class SingleInstance:
        def __init__(self):
            self.mutexname = "Privox_SingleInstance_Mutex_Service"
            self.mutex = ctypes.windll.kernel32.CreateMutexW(None, False, self.mutexname)
            self.last_error = ctypes.windll.kernel32.GetLastError()
            if self.last_error == 183: # ERROR_ALREADY_EXISTS
                # Use ctypes to show a silent exit or a logging entry. 
                # We don't want a popup every time a user accidentally double-clicks.
                # However, for debugging we log it.
                print("DEBUG: Another instance of Privox is already running. Exiting to prevent corruption.")
                sys.exit(0)
    _si = SingleInstance()

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
try:
    import sys
    import os
    import logging
    
    # We MUST ensure standard libraries are reachable BEFORE we clobber sys.path
    log_print(f"System Diagnostic - Python Interpreter: {sys.executable}")
    log_print(f"System Diagnostic - sys.prefix: {sys.prefix}")
    if _removed_user_site_paths:
        log_print(f"System Diagnostic - Removed user site-packages paths: {len(_removed_user_site_paths)}")
    
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

BASE_DIR = _privox_install_root()
if sys.platform == "win32":
    logging.info("Privox install root (BASE_DIR): %s", BASE_DIR)

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
    
    log_print(f"--- TORCH DIAGNOSTICS ---")
    log_print(f"Python Version: {sys.version}")
    if torch is not None:
        log_print(f"Torch Version: {torch.__version__}")
        log_print(f"Torch Path: {getattr(torch, '__file__', 'Unknown')}")
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
            if sys.platform == "win32" and not getattr(sys, "frozen", False):
                pass
    else:
        log_print(
            "PRIVOX_NO_TORCH=1: PyTorch not loaded (WebRTC VAD; ASR: faster-whisper and/or Qwen ONNX)."
        )
    # Before any thread imports faster_whisper/transformers (numpy metadata quirks on mixed conda/pip).
    ensure_numpy_version_visible_to_metadata()

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
# Silero probability threshold; lower = more sensitive (helps quiet mics / distant speech).
VAD_THRESHOLD = 0.4
MIN_SPEECH_DURATION_MS = 400
SPEECH_PAD_MS = 500
# If chunk RMS reaches this, we treat it as "there was audible input" even when VAD misses (quiet gain).
INITIAL_SPEECH_ENERGY_RMS = 0.00085

# Models
# Models
WHISPER_SIZE = "distil-large-v3" 
WHISPER_REPO = "Systran/faster-distil-whisper-large-v3"
ASR_BACKEND = "whisper" # Default: whisper or sensevoice
# Optional ISO code passed to faster-whisper (e.g. yue for Cantonese-tuned checkpoints).
WHISPER_TRANSCRIBE_LANGUAGE = None

# Fallback refiner when profile is empty (matches LLM_LIBRARY[0])
GRAMMAR_REPO = models_config.LLM_LIBRARY[0]["repo_id"]
GRAMMAR_FILE = models_config.LLM_LIBRARY[0]["file_name"]


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


def _infer_language_from_transcript(text: str) -> tuple[str | None, float]:
    """Guess ISO-ish language for refiner prompts when ASR has no LID (e.g. qwen_asr). Returns (code, confidence)."""
    if not text or not text.strip():
        return None, 0.0
    han = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    hiragana = len(re.findall(r"[\u3040-\u309f]", text))
    katakana = len(re.findall(r"[\u30a0-\u30ff]", text))
    hangul = len(re.findall(r"[\uac00-\ud7af]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    total = han + hiragana + katakana + hangul + latin
    if total == 0:
        return None, 0.0
    kana = hiragana + katakana
    if hangul >= total * 0.22 and hangul >= max(han, kana):
        return "ko", 0.88
    if kana > 0 and (kana >= total * 0.12 or han <= kana * 3):
        return "ja", 0.85
    if han >= total * 0.18:
        return "zh", 0.9
    if latin >= total * 0.72:
        return "en", 0.75
    return None, 0.0


# Distinctive Han forms: count to guess Traditional vs Simplified output (refiner often flips script).
_TRAD_DISTINCT = frozenset(
    "這邊體廣門聽國學會還開長東車時來說話點過個們問間關頭員團選種總從應該計記訊議務質產親龍鳥魚馬風雲參與舊嚴據處樂極構樹機殺歲歸歷畢畫異當發盜盡監盤眾確碩礎顯題館鐵際線聲電腦裏經師場見覽觀討許訪評詳誤課講識讀變讓貓負貢貧貨購贊贈趕跡軌農釋鋼錄錯鍾險隱雖韓項順預領頻養餘騎鬆鹽麗點齊齡臺灣華書導師顯響腦腳臟與舊艱蘭號處術衛衝裝製複規視覺親覽覺觀計訊記訓託許訟訪評詞話該詳語誤說課謂講證識譯警護譽豐豫貓貝負貢貧貨販貪購賽贊贈趕趨跡跟路跳躍身軌軍農邊達遠遲郵鄉酒釋針鋼錄錯鍵鐘鐵鑽隊際險隱集雖電霧項順預領頻願類顯風飛餘餅騎體鬱魚鳥鹽麗麟齊齡"
)
_SIMP_DISTINCT = frozenset(
    "这边体广门听国学会还开长东车时点过来说边个们问间关头员团选种总从应该计记讯议务质产亲龙鸟鱼马云参与旧严据处乐极构树机杀岁归历毕画异当发盗尽监盘众确硕础显题馆铁际线声电脑里经师场见览观讨许访评详误课讲识读变让猫负贫货购赞赠赶迹轨农释钢录错钟险隐虽韩项顺预领频养余骑松盐丽点齐龄台湾华书导师显响脑脚脏与旧艰兰号处术卫冲装制复规视觉亲览觉观计讯记训托许讼访评词话该详语误说课谓讲证识译警护誉丰豫猫贝负贡贫货贩贪购赛赞赠赶趋迹跟路跳跃身轨军农边达远迟邮乡酒释针钢录错键钟铁钻队际险隐集虽电雾项顺预领频愿类显风飞余饼骑体郁鱼鸟盐丽麟齐龄"
)
# Spoken Cantonese particles / forms (preserve in refiner; do not 書面語化).
_CANTONESE_ORAL_MARKERS = frozenset(
    "嘅咗唔佢冇啲囉咩喺乜咁咪喇喎噉囖吖嘛啱呃啫咋畀俾掂求其係嚟啱哋噃啩啲"
)


def _infer_chinese_script_variant(text: str) -> tuple[str | None, float]:
    """Return ('traditional'|'simplified', confidence) or (None, 0) if unclear."""
    if not text:
        return None, 0.0
    t = 0
    s = 0
    for ch in text:
        if ch in _TRAD_DISTINCT:
            t += 1
        if ch in _SIMP_DISTINCT:
            s += 1
    if t == 0 and s == 0:
        return None, 0.0
    if t >= 2 and t >= s * 2:
        return "traditional", min(0.95, 0.55 + 0.05 * min(t, 8))
    if s >= 2 and s >= t * 2:
        return "simplified", min(0.95, 0.55 + 0.05 * min(s, 8))
    if t > s:
        return "traditional", 0.6
    if s > t:
        return "simplified", 0.6
    return None, 0.0


def _looks_like_cantonese_oral(text: str) -> bool:
    if not text:
        return False
    return any(ch in text for ch in _CANTONESE_ORAL_MARKERS)


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
        self.use_simplified_chinese_output = False
        self.icon = None # Placeholder
        self.context_buffer = "" # Max 2000 chars of conversation history
        self._has_loaded_once = False  # Instance-level: tracks if we've loaded before (for verbose control)

    def load_model(self, attempts=0):
        if self.model:
            return True
            
        if attempts > 2:
            log_print("CRITICAL: Model loading failed after 3 attempts. Stopping to prevent infinite loop.")
            self.loading_error = "Model loading failed repeatedly. Please check your internet connection or model files."
            if self.icon:
                self.icon.notify("Privox Error: Model loading failed repeatedly. Check logs.", "Privox")
            return False

        repo_id = self.profile.get("repo_id", GRAMMAR_REPO)
        file_name = self.profile.get("file_name", GRAMMAR_FILE)
        profile_name = self.profile.get("name", "")
        is_reload = self._has_loaded_once  # True on wake-from-idle, False on first boot
        log_print(
            f"Resolved Refiner Profile: name={profile_name or 'N/A'}, repo_id={repo_id}, file_name={file_name}, "
            f"prompt_type={self.profile.get('prompt_type', 'unknown')}"
        )

        # --- Optimization 3: Skip HF cache probe if local file already exists ---
        local_model_path = os.path.join(BASE_DIR, "models", file_name)
        if os.path.exists(local_model_path):
            if not is_reload:
                log_print(f"Found local model: {local_model_path}")
            model_path = local_model_path
        else:
            try:
                # Check/Download from Hugging Face
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
                        local_dir=local_dir
                    )
                    log_print(f"Download complete: {model_path}")
                
                # Verify file integrity
                if os.path.exists(model_path):
                    f_size = os.path.getsize(model_path)
                    log_print(f"Model file verified: {model_path} ({f_size / 1024**2:.2f} MB)")
                    if f_size < 100 * 1024**2: # A 3B model should be > 200MB even at extreme quantization
                         log_print("WARNING: Model file seems too small. Moving to backup/re-download.")
                         if os.path.exists(model_path + ".bak"):
                             try: os.remove(model_path + ".bak")
                             except: pass
                         os.rename(model_path, model_path + ".bak")
                         return self.load_model(attempts=attempts + 1) # Recursive retry
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
                    llama_version = getattr(llama_cpp, '__version__', 'Unknown')
                    log_print(f"llama-cpp-python Version: {llama_version}")
                    _sys_fn = getattr(llama_cpp, "llama_system_info", getattr(llama_cpp, "llama_print_system_info", None))
                    sys_info = _sys_fn() if _sys_fn else b""
                    log_print(f"llama-cpp-python System Info: {sys_info}")
                    sys_info_text = str(sys_info)
                    llama_has_cuda = ("CUDA = 1" in sys_info_text) or ("CUDA :" in sys_info_text)
                    if llama_has_cuda:
                        log_print("GPU Backend detected in llama-cpp-python.")
                    else:
                        log_print("WARNING: llama-cpp-python appears to be CPU-ONLY.")
                except ImportError as ie:
                    log_print(f"CRITICAL: Failed to import llama_cpp: {ie}")
                    raise ie
                
                from llama_cpp import Llama
                GrammarChecker._Llama = Llama
                GrammarChecker._llama_imported = True

                # Newer GGUF families require newer llama runtime to parse/load reliably.
                model_sig = (repo_id + " " + file_name).lower()
                needs_new_runtime = ("gemma-4" in model_sig) or ("qwen3.5" in model_sig)
                if needs_new_runtime:
                    try:
                        v_parts = [int(p) for p in str(llama_version).split('.')[:3]]
                        while len(v_parts) < 3:
                            v_parts.append(0)
                        # Windows cp312 abetlen CUDA wheels often stop at 0.3.19; 0.3.19+ is acceptable here.
                        if tuple(v_parts) < (0, 3, 19):
                            self.loading_error = (
                                f"Incompatible llama-cpp-python runtime ({llama_version}) for this refiner model. "
                                "Upgrade to >=0.3.19 (CUDA build on GPU), e.g. run model setup or install_llama_cuda.py."
                            )
                            log_print(self.loading_error)
                            return False
                    except Exception:
                        pass
                    if cuda_is_available() and not llama_has_cuda:
                        self.loading_error = (
                            "llama-cpp-python is CPU-only but a CUDA GPU appears available to Privox. "
                            "Reinstall llama-cpp-python with the CUDA 12.4 wheel (do not use the CPU wheel). "
                            "Run: python src/download_models.py or pip install with --extra-index-url cu124."
                        )
                        log_print(self.loading_error)
                        return False
            
            Llama = GrammarChecker._Llama

            # Keep llama.cpp stdout/stderr noise minimal unless explicitly requested per profile.
            use_verbose = bool(self.profile.get("llama_verbose", False))
            last_init_error_text = ""

            def _safe_llama_init(m_path, n_gpu_layers, n_ctx, n_batch):
                nonlocal last_init_error_text
                try:
                    _llama_kw: dict = dict(
                        model_path=m_path,
                        n_ctx=n_ctx,
                        n_gpu_layers=n_gpu_layers,
                        n_batch=n_batch,
                        verbose=use_verbose,
                        n_threads=min(4, os.cpu_count() // 2) if os.cpu_count() else 4,
                    )
                    # Gemma: llama.cpp chat path tokenizes with BOS (see llama_chat_format); raw
                    # self.model(prompt) does not — causes <unused*> degeneracy on Gemma 4 GGUF.
                    if (self.profile.get("prompt_type") or "").lower() == "gemma":
                        _llama_kw["chat_format"] = "gemma"
                    return Llama(**_llama_kw)
                except (AssertionError, RuntimeError, ValueError) as e:
                    last_init_error_text = str(e)
                    err_msg = str(e).lower()
                    if "out of memory" in err_msg or "cuda_error_out_of_memory" in err_msg or "failed to allocate" in err_msg:
                        log_print(f"Llama initialization OOM ({type(e).__name__}) with n_gpu_layers={n_gpu_layers}, n_ctx={n_ctx}, n_batch={n_batch}.")
                        return None
                    # Do NOT auto-delete model on generic ValueError/RuntimeError.
                    # Some backends/models can raise ValueError for non-corruption reasons
                    # (unsupported runtime combo, metadata parsing differences, etc.).
                    # We only remove tiny obviously-incomplete files.
                    log_print(f"Llama initialization failed ({type(e).__name__}): {e}")
                    if os.path.exists(m_path):
                        size_mb = os.path.getsize(m_path) / (1024 * 1024)
                        if size_mb < 256:
                            log_print(f"Model file appears incomplete ({size_mb:.1f} MB). Removing: {m_path}")
                            try: os.remove(m_path)
                            except: pass
                    return None

            # Assertive GPU Offloading
            is_gpu = cuda_is_available()
            turboquant = bool(self.profile.get("turboquant", False))

            # TurboQuant profile lowers context/batch defaults to reduce VRAM pressure.
            default_n_ctx = 3072 if turboquant else 4096
            n_ctx = int(self.profile.get("n_ctx", default_n_ctx))
            n_batch = 256 if turboquant else 512

            gpu_mem_gb = cuda_device_total_memory_gib(0) if is_gpu else 0.0

            # Allow higher batching for modern 40-series cards (8GB-12GB) to speed up prompt processing.
            if is_gpu and gpu_mem_gb:
                if gpu_mem_gb <= 8.5:
                    n_batch = min(n_batch, 128) # Safety cap for low-end cards
                elif gpu_mem_gb <= 12.5:
                    n_batch = min(n_batch, 512) # High-speed batching for 4070/4070Ti

            # Instead of "all layers" (-1), use bounded offload counts.
            if is_gpu:
                preferred_layers = int(self.profile.get("n_gpu_layers", 24 if turboquant else 40))
                if gpu_mem_gb and gpu_mem_gb <= 12.5:
                    preferred_layers = min(preferred_layers, 16)
                layer_plan = [preferred_layers, 24, 16, 8, 0]
            else:
                layer_plan = [0]

            # Deduplicate while preserving order
            seen = set()
            layer_plan = [x for x in layer_plan if not (x in seen or seen.add(x))]

            log_print(
                f"Loading Llama (GPU={is_gpu}, vram_gb={gpu_mem_gb:.1f}, turboquant={turboquant}, n_ctx={n_ctx}, n_batch={n_batch}, layers_plan={layer_plan})"
                f"{'  [Quick Reload]' if is_reload else ''}..."
            )
            self.model = None
            for n_gpu_layers in layer_plan:
                self.model = _safe_llama_init(model_path, n_gpu_layers, n_ctx, n_batch)
                if self.model is not None:
                    break
                if is_gpu and n_gpu_layers != layer_plan[-1]:
                    log_print(f"Retrying with lower GPU offload... next n_gpu_layers={layer_plan[layer_plan.index(n_gpu_layers) + 1]}")
            
            if self.model is None:
                # Qwen-specific hard fallback for stubborn init failures.
                is_qwen_profile = "qwen" in (repo_id + " " + file_name + " " + profile_name).lower()
                if is_qwen_profile:
                    qwen_fallback_n_ctx = 2048
                    qwen_fallback_n_batch = 64
                    qwen_fallback_layers = 0
                    log_print(
                        "Qwen hard-fallback triggered: retrying with "
                        f"n_ctx={qwen_fallback_n_ctx}, n_batch={qwen_fallback_n_batch}, n_gpu_layers={qwen_fallback_layers}"
                    )
                    self.model = _safe_llama_init(
                        model_path,
                        qwen_fallback_layers,
                        qwen_fallback_n_ctx,
                        qwen_fallback_n_batch
                    )

                if self.model is not None:
                    self._has_loaded_once = True
                    log_print(f"Done. (GPU Acceleration: {'ENABLED' if is_gpu else 'DISABLED'}) [Qwen Hard Fallback]")
                    return True

                # Model file exists and full offload fallback exhausted, but backend still cannot parse/open it.
                # Avoid repeating the same sequence; provide an actionable compatibility hint.
                if "failed to load model from file" in (last_init_error_text or "").lower():
                    self.loading_error = (
                        "Model file format appears incompatible with current llama-cpp-python runtime. "
                        "Please update llama-cpp-python and retry."
                    )
                    log_print(
                        "Model init failed due to file/runtime compatibility (not VRAM offload). "
                        "Skipping repeated retries."
                    )
                    return False

                # Could be OOM fallback exhaustion or a genuinely bad model file.
                log_print("Model initialization failed after all fallback settings. Restarting load sequence...")
                return self.load_model(attempts=attempts + 1)

            self._has_loaded_once = True
            log_print(f"Done. (GPU Acceleration: {'ENABLED' if is_gpu else 'DISABLED'})")
            return True
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
                 return self.load_model(attempts=attempts + 1)

            if sys.platform == 'win32':
                 show_modern_error("Privox Model Error", f"Error loading Grammar Model (Llama): {e}", f"Traceback:\n{err_trace[:500]}")
            return False

    def get_effective_prompt(self, language=None, language_prob=0.0, transcript=None):
        """Constructs a composite prompt with hidden overrides.
        Layer 1: Core Safety/Format (Hidden)
        Layer 2: User Instructions (Visible in GUI)
        Layer 3: Late-Binding Overrides (Hidden, conditional)
        """
        key = f"{self.character}|{self.tone}"
        user_text = self.custom_prompts.get(key, "").strip()
        sample = (transcript or "").strip()

        # Layer 1: Core System Directives (Global Critical Rules)
        directive = (
            "REFINE TRANSCRIPT: Provide a clean, accurate version of the ASR input in its ORIGINAL LANGUAGE. "
            "Do NOT translate into English or any other language. "
            "Whenever the utterance refers to a numeric value (counts, amounts, dates, math, lists, etc.), "
            "write it with Western Arabic digits (0–9); this applies in every supported language (CRITICAL RULE 6)."
        )

        # Language Hinting (Robust Multilingual Support)
        # Only inject specific language directive if confidence is high (> 0.4)
        _non_en_numbers_block = (
            "\nSPOKEN NUMBERS & MATH: Follow CRITICAL RULES 6 and 10–11: "
            "every numeric reference → Western Arabic digits (0–9) while keeping all other words in this language; "
            "item lists → digit form; "
            "spoken arithmetic → + − × ÷ = using that language’s cues; "
            "large numbers → locale-appropriate grouping/unit words (e.g. 萬/億, 万/億, 만/억, lakh/crore, millions). "
            "Never invent unstated results or round beyond what was spoken."
        )
        if language and language != "en" and language_prob > 0.4:
            lang_name = models_config.ISO_LANGUAGE_MAP.get(language, language)
            # Do not replace the whole directive with "CLEAN <LANG>" when the utterance mixes CJK + Latin —
            # that wording pushes the model to translate English into Chinese (etc.).
            if sample and _transcript_mixes_cjk_and_latin(sample):
                directive += (
                    f"\nCODE-MIXING ({lang_name} + Latin/English): The transcript mixes {lang_name} with embedded "
                    "English or other Latin-script words. Preserve that mix: keep Latin segments as spoken "
                    "(phrasing, technical terms, names, product words). "
                    "Do NOT translate those Latin segments into Chinese or vice versa unless fixing a clear ASR error. "
                    "Apply Traditional/Simplified rules only to Chinese characters (see USER PREFERENCE below)."
                )
                directive += _non_en_numbers_block
            else:
                directive = f"REFINE TRANSCRIPT: PROVIDE A CLEAN {lang_name.upper()} VERSION. DO NOT TRANSLATE TO ENGLISH."
                directive += _non_en_numbers_block
        elif language == "en" and language_prob > 0.4:
            directive += (
                "\nENGLISH SPOKEN NUMBERS & MATH: Same global policy as all languages (CRITICAL RULE 6): "
                "any numeric meaning → Western Arabic digits (0–9)—cardinal lists ('one, two, three, four' → '1, 2, 3, 4'), "
                "including space-separated runs like 'one two three'. "
                "Spoken arithmetic (plus, minus, times, multiplied by, divided by, equals) → +, −, ×, ÷, = with digits per CRITICAL RULE 10 (choose − vs - and ÷ vs / by context)."
            )

        # Chinese script: user chooses Simplified vs Traditional for all Chinese output (default: Traditional).
        if sample:
            _has_zh = (language == "zh" and language_prob > 0.4) or _contains_cjk_char(sample)
            _mixed_cjk_lat = _transcript_mixes_cjk_and_latin(sample)
            if _has_zh:
                if self.use_simplified_chinese_output:
                    if _mixed_cjk_lat:
                        directive += (
                            "\nUSER PREFERENCE (MANDATORY): Chinese characters MUST use Simplified (简体中文). "
                            "Latin/English words and phrases stay as in the transcript (code-mixing); do not translate them to Chinese."
                        )
                    else:
                        directive += (
                            "\nUSER PREFERENCE (MANDATORY): Output MUST be Simplified Chinese (简体中文) only. "
                            "Convert all Traditional forms to standard Simplified characters "
                            "(e.g. use 体/这/们/还/点/过/说/电/学/开/门/时/来/个/国/会/长/东/车; do not leave 體/這/們/還/點/過/說/電/學/開/門/時/來/個/國/會/長/東/車 when a Simplified form exists). "
                            "Apply this regardless of whether the transcript was Traditional or Simplified."
                        )
                else:
                    if _mixed_cjk_lat:
                        directive += (
                            "\nUSER PREFERENCE (MANDATORY): Chinese characters MUST use Traditional (繁體中文). "
                            "Latin/English words and phrases stay as in the transcript (code-mixing); do not translate them to Chinese."
                        )
                    else:
                        directive += (
                            "\nUSER PREFERENCE (MANDATORY): Output MUST be Traditional Chinese (繁體中文) only. "
                            "Convert all Simplified forms to standard Traditional characters "
                            "(e.g. use 體/這/們/還/點/過/說/電/學/開/門/時/來/個/國/會/長/東/車; never 体/这/们/还/点/过/说/电/学/开/门/时/来/个/国/会/长/东/车). "
                            "Apply this regardless of whether the transcript was Traditional or Simplified."
                        )
            if _looks_like_cantonese_oral(sample):
                directive += (
                    "\nCANTONESE ORAL (廣東話口語): The transcript reads as spoken Cantonese. "
                    "Preserve colloquial particles and wording (e.g. 嘅、咗、唔、佢、冇、啲、喺、係、乜、點、咁、咪、喇、囉、咩). "
                    "Do not rewrite into formal Written Chinese / Mandarin book style (書面語) unless ADDITIONAL USER INSTRUCTIONS explicitly request formal writing. "
                    "Fix only clear dictation/ASR errors and punctuation; keep the spoken Cantonese voice."
                )

        # NEW: Inject direct formatting instruction right to the core directive layer
        directive += "\nCRITICAL FORMATTING: Whenever the user dictates a list, sequence of items, or steps, you MUST format your output as a clear bulleted or numbered list. Add paragraphs where logical."

        prompt = f"{directive}\n\n{models_config.CRITICAL_RULES}"
        
        dict_str = ", ".join(self.custom_dictionary)
        if dict_str:
            prompt += f"Specific Jargon/Hints: {dict_str}\n"

        # [DISABLED] Contextual memory — currently interferes with output quality
        # if self.context_buffer:
        #     prompt += f"\n[Previous Context (For Continuity Only - Do NOT transcribe this again)]:\n{self.context_buffer}\n"

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

    @staticmethod
    def _is_gemma_unused_degeneracy(text: str) -> bool:
        """Detect Gemma pathologies: repeated <unusedNN> tokens (wrong chat template / quant quirks)."""
        if not text:
            return False
        head = text[:4000]
        n = len(re.findall(r"<unused\d+>", head, flags=re.IGNORECASE))
        if n < 10:
            return False
        if text.lstrip().startswith("<unused"):
            return True
        return len(head) >= 300 and (n * 11) > len(head) * 0.25

    def _run_gemma_chat_completion(self, user_content: str, max_tokens: int) -> tuple[str, bool]:
        """
        Gemma refiner via create_chat_completion so llama_cpp applies the same BOS/special
        tokenization as format_gemma (raw self.model(str) skips that and can emit <unused*> spam).
        """
        extra_stop = ["</refined>", "<end_of_turn>", "<end_of_turn>\n"]
        parts: list[str] = []
        try:
            stream = self.model.create_chat_completion(
                messages=[{"role": "user", "content": user_content}],
                max_tokens=max_tokens,
                temperature=0.0,
                top_p=1.0,
                repeat_penalty=1.1,
                seed=42,
                stop=extra_stop,
                stream=True,
            )
        except Exception as e:
            log_print(f"Gemma create_chat_completion failed: {e}")
            return "", True

        for chunk in stream:
            ch0 = chunk["choices"][0]
            delta = ch0.get("delta") or {}
            piece = delta.get("content") or ""
            if piece:
                parts.append(piece)
            acc = "".join(parts)
            if "</refined>" in acc:
                break
            if self._is_gemma_unused_degeneracy(acc):
                log_transcription(" Gemma refiner: early-abort on <unused*> degeneracy.")
                return "", True
        text = "".join(parts).strip()
        if text and self._is_gemma_unused_degeneracy(text):
            return "", True
        return text, False

    def _run_gemma_raw_prompt_stream(
        self, prompt: str, max_tokens: int, stop_tokens
    ) -> tuple[str, bool]:
        """Last-resort raw prompt + stream (e.g. two-turn system/user); still may lack BOS."""
        stop_list = list(stop_tokens) if isinstance(stop_tokens, (list, tuple)) else (
            [stop_tokens] if stop_tokens else []
        )
        for s in ("</refined>", "<end_of_turn>", "<end_of_turn>\n"):
            if s not in stop_list:
                stop_list.append(s)
        gen_kw: dict = dict(
            max_tokens=max_tokens,
            stop=stop_list,
            echo=False,
            temperature=0.35,
            top_p=0.92,
            repeat_penalty=1.28,
            seed=43,
        )
        parts: list[str] = []
        # stream= must not appear in gen_kw — same kw twice raises TypeError on Llama.__call__.
        for out in self.model(prompt, stream=True, **gen_kw):
            chunk = out["choices"][0]["text"]
            parts.append(chunk)
            acc = "".join(parts)
            if "</refined>" in acc:
                break
            if self._is_gemma_unused_degeneracy(acc):
                log_transcription(" Gemma raw fallback: early-abort on <unused*> degeneracy.")
                return "", True
        text = "".join(parts).strip()
        if text and self._is_gemma_unused_degeneracy(text):
            return "", True
        return text, False

    def _run_refiner_completion(
        self, prompt: str, prompt_type: str, max_tokens: int, stop_tokens
    ) -> tuple[str, bool]:
        """Non-Gemma chat templates only (Llama/Qwen/…). Returns (raw_text, always False)."""
        stop_list = list(stop_tokens) if isinstance(stop_tokens, (list, tuple)) else (
            [stop_tokens] if stop_tokens else []
        )
        if "</refined>" not in stop_list:
            stop_list.append("</refined>")

        gen_kw: dict = dict(
            max_tokens=max_tokens,
            stop=stop_list,
            echo=False,
            temperature=0.3,
            top_p=0.9,
            repeat_penalty=1.1,
            seed=42,
        )

        output = self.model(prompt, stream=False, **gen_kw)
        text = (output["choices"][0]["text"] or "").strip()
        return text, False

    def correct(self, text, is_command=False, language=None, language_prob=0.0):
        # 1. Pre-processing Guardrail: Skip LLM for very short or empty inputs
        # (Unless it's a known keyword in the custom dictionary)
        clean_text = text.strip()
        if not self.model or not clean_text:
            return _finalize_refiner_text(text, self.use_simplified_chinese_output)
            
        if len(clean_text) < 8 and clean_text.lower() not in [d.lower() for d in self.custom_dictionary]:
            log_transcription(f" [Short Input Skip] Input too short ({len(clean_text)} chars). Mirroring.")
            return _finalize_refiner_text(text, self.use_simplified_chinese_output)

        lang_effective, prob_effective = language, language_prob
        if (not lang_effective or prob_effective <= 0.4) and clean_text:
            inf_lang, inf_prob = _infer_language_from_transcript(clean_text)
            if inf_prob >= 0.72:
                lang_effective = inf_lang
                prob_effective = max(prob_effective, inf_prob)
                log_transcription(f" Refiner language hint (script inference): {lang_effective} (p={prob_effective:.2f})")

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
                core_directive = self.get_effective_prompt(
                    language=lang_effective,
                    language_prob=prob_effective,
                    transcript=clean_text,
                )
                # Dynamically select few-shot examples + INJECT PERSONA into System Prompt identity
                system_prompt = models_config.get_system_formatter_for_transcript(
                    language=lang_effective, 
                    transcript_char_len=len(clean_text),
                    persona_mission=core_directive
                )
                user_content = (
                    f"[Core Directive]: {core_directive}\n"
                    f"[Transcript]: {text}\n"
                    "Do not repeat the Core Directive, rules, or examples. "
                    "Write only the opening tag <refined>, the cleaned transcript, and </refined>.\n"
                    "Output: "
                )

            # Format based on model type
            if prompt_type == "t5":
                # CoEdit / T5 style
                action = "Polish" if self.tone != "Natural" else "Fix grammar"
                prompt = f"{action}: {text}"
                stop_tokens = ["\n"]
            elif prompt_type == "chatml":
                # Qwen / ChatML style format
                prompt = (
                    f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                    f"<|im_start|>user\n{user_content}<|im_end|>\n"
                    "<|im_start|>assistant\n"
                )
                stop_tokens = ["<|im_end|>"]
            elif prompt_type == "gemma":
                # Fold system into one user message for create_chat_completion(chat_format=gemma).
                combined_user = f"{system_prompt}\n\n{user_content}"
                prompt = ""
                stop_tokens = []
            else:
                # Llama 3 / Mistral style format
                prompt = (
                    f"<|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|>"
                    f"<|start_header_id|>user<|end_header_id|>\n\n{user_content}<|eot_id|>"
                    "<|start_header_id|>assistant<|end_header_id|>\n\n"
                )
                stop_tokens = ["<|eot_id|>"]
            
            # 2. Proportional max_tokens: CJK-heavy text needs ~1 token/char of headroom; cap runaway at 4096.
            char_n = len(clean_text)
            word_n = len(clean_text.split())
            input_tokens_est = max(char_n // 2, word_n * 3, char_n // 4 + 200)
            max_tokens = min(8192, max(256, int(char_n * 1.3) + 512, input_tokens_est * 3))

            raw_response = ""
            gemma_degenerate = False
            if prompt_type == "gemma":
                raw_response, gemma_degenerate = self._run_gemma_chat_completion(
                    combined_user, max_tokens
                )
                if gemma_degenerate:
                    log_transcription(
                        " Gemma: chat path degenerate; retrying two-turn system/user template..."
                    )
                    prompt_fb = (
                        f"<start_of_turn>system\n{system_prompt}<end_of_turn>\n"
                        f"<start_of_turn>user\n{user_content}<end_of_turn>\n"
                        "<start_of_turn>model\n"
                    )
                    raw_response, gemma_degenerate = self._run_gemma_raw_prompt_stream(
                        prompt_fb, max_tokens, ["<end_of_turn>"]
                    )
            else:
                raw_response, gemma_degenerate = self._run_refiner_completion(
                    prompt, prompt_type, max_tokens, stop_tokens
                )
            if gemma_degenerate:
                log_transcription(
                    " Gemma refiner degeneracy (<unused*> / bad distribution). Using ASR transcript."
                )
                return _finalize_refiner_text(clean_text, self.use_simplified_chinese_output)

            raw_for_extract = self._strip_critical_rules_echo(raw_response)

            # Diagnostic: full LLM string often starts with an ASR echo or filler BEFORE <refined>;
            # the pasted text comes from inside <refined> only — do not read this prefix as final output.
            if raw_response:
                prev_n = min(140, len(raw_response))
                tail = "..." if len(raw_response) > prev_n else ""
                log_transcription(
                    f" LLM response length={len(raw_response)}; start of string (may differ from pasted text): "
                    f"'{raw_response[:prev_n]}{tail}'"
                )
            else:
                log_transcription(" Warning: LLM returned empty response.")
                
            # If standard instruction model (T5), just return the raw string
            if prompt_type == "t5":
                # self.context_buffer = (self.context_buffer + " " + raw_response).strip()[-2000:]  # [DISABLED]
                return _finalize_refiner_text(raw_response, self.use_simplified_chinese_output)

            # If Llama/Qwen, extract text from <refined> tags (strict, then partial/unclosed).
            match = re.search(r"<refined>(.*?)</refined>", raw_for_extract, flags=re.DOTALL | re.IGNORECASE)
            if not match:
                match = re.search(
                    r"<\s*refined\s*>(.*?)(?:<\s*/\s*refined\s*>|$)",
                    raw_for_extract,
                    flags=re.DOTALL | re.IGNORECASE,
                )

            result = None
            if match:
                log_transcription(" Regex extracted <refined> block successfully.")
                result = match.group(1).strip()
                result = re.sub(r"<\s*/?\s*refined\s*>", "", result, flags=re.IGNORECASE).strip()
                if result:
                    pv_n = min(320, len(result))
                    pv_tail = "..." if len(result) > pv_n else ""
                    log_transcription(
                        f" <refined> inner preview ({len(result)} chars; paste also runs digit/zh finalize): "
                        f"'{result[:pv_n]}{pv_tail}'"
                    )
            else:
                log_transcription(" Warning: Model failed to use <refined> tags.")
                fb = self._fallback_extract_refined_body(raw_for_extract, clean_text)
                if fb:
                    log_transcription(f" Fallback extraction recovered {len(fb)} chars (heuristic, no tags).")
                    result = fb
                elif "[Transcript]:" in raw_response:
                    log_transcription("  Detected prompt echo in raw response. Attempting legacy strip...")
                    parts = re.split(r"\[Transcript\]:.*?\n", raw_response, flags=re.DOTALL | re.IGNORECASE)
                    if len(parts) > 1:
                        result = parts[-1].strip()
                        log_transcription(f"  Stripped echo. New candidate length: {len(result)}")
                    else:
                        result = raw_response
                elif self._looks_like_prompt_echo(raw_response):
                    log_transcription(" Raw response looks like prompt echo only. Using ASR transcript (no refiner output).")
                    result = clean_text
                else:
                    result = raw_for_extract or raw_response

            # 3a. Strip trailing meta-commentary ("Note:", "I've preserved...", etc.)
            result = self._strip_meta_commentary(result)

            # 3b. Post-generation Hallucination Validator
            result = self._validate_output(clean_text, result)

            # self.context_buffer = (self.context_buffer + " " + result).strip()[-2000:]  # [DISABLED]
            return _finalize_refiner_text(result, self.use_simplified_chinese_output)
        except Exception as e:
            log_print(f"Grammar Check Error: {e}")
            return _finalize_refiner_text(text, self.use_simplified_chinese_output)

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
            log_transcription(f" [Meta-Commentary Strip] Removed {len(text) - earliest_cut} chars of LLM self-commentary.")
            return stripped

        return text

    def _strip_critical_rules_echo(self, s: str) -> str:
        """Remove regurgitated prompt chunks (Core Directive line, CRITICAL RULES, numbered rules)."""
        s = (s or "").strip()
        if not s:
            return s
        lines = s.split("\n")
        out: list[str] = []
        i, n = 0, len(lines)
        rule_num = re.compile(r"^\s*\d+\.\s+[A-Z][A-Z0-9,\s/'&\-]{2,}.*:.*$")
        while i < n:
            low = lines[i].strip().lower()
            if low.startswith("[core directive]"):
                i += 1
                continue
            if low.startswith("### system overrides") or low.startswith("### additional user instructions"):
                i += 1
                continue
            if low.startswith("critical rules"):
                i += 1
                while i < n:
                    ln = lines[i].strip()
                    if not ln:
                        i += 1
                        continue
                    if rule_num.match(lines[i]):
                        i += 1
                        continue
                    break
                continue
            out.append(lines[i])
            i += 1
        s = "\n".join(out).strip()

        cr = (models_config.CRITICAL_RULES or "").strip()
        if not cr:
            return s
        cr_lines = [x.strip() for x in cr.splitlines() if x.strip()]
        s_lines = s.splitlines()
        ri = 0
        while ri < len(s_lines) and not s_lines[ri].strip():
            ri += 1
        if ri < len(s_lines) and s_lines[ri].strip().lower() == cr_lines[0].lower():
            ci = 0
            while ci < len(cr_lines) and ri < len(s_lines):
                if not s_lines[ri].strip():
                    ri += 1
                    continue
                if s_lines[ri].strip().lower() != cr_lines[ci].lower():
                    break
                ci += 1
                ri += 1
            if ci == len(cr_lines) or ci >= max(4, (len(cr_lines) * 2 + 2) // 3):
                return "\n".join(s_lines[ri:]).strip()
        return s

    def _looks_like_prompt_echo(self, s: str) -> bool:
        if not s:
            return True
        sl = s.lower()
        markers = (
            "[core directive]",
            "[transcript]",
            "must wrap your final",
            "do not output anything outside",
            "<example_",
            "### system overrides",
            "### additional user instructions",
            "you are a precise text-processing api",
            "output only the processed text",
            "critical rules:",
            "conservative refinement:",
        )
        return any(m in sl for m in markers)

    def _fallback_extract_refined_body(self, raw: str, transcript: str) -> str | None:
        """Recover refined text when tags are missing (Gemma often echoes instructions)."""
        s = self._strip_critical_rules_echo((raw or "").strip())
        t = (transcript or "").strip()
        if not s:
            return None

        m = re.search(r"<\s*refined\s*>(.*?)(?:<\s*/\s*refined\s*>|$)", s, flags=re.DOTALL | re.IGNORECASE)
        if m:
            body = m.group(1).strip()
            if body and not self._looks_like_prompt_echo(body):
                return body

        if re.search(r"\boutput:\s*", s, flags=re.IGNORECASE):
            tail = re.split(r"(?i)\boutput:\s*", s)[-1].strip()
            if tail and len(tail) < len(s):
                s = tail

        line_starts = (
            "[core directive]",
            "[transcript]",
            "### additional",
            "### system overrides",
            "[strict identity",
            "[strict style",
        )
        lines = s.split("\n")
        out_lines: list[str] = []
        for line in lines:
            low = line.strip().lower()
            if not out_lines and not low:
                continue
            if not out_lines:
                if any(low.startswith(p) for p in line_starts):
                    continue
                if low.startswith("refine transcript:") or low.startswith("critical formatting"):
                    continue
                if low.startswith("critical rules"):
                    continue
            out_lines.append(line)
        candidate = "\n".join(out_lines).strip()

        if t:
            parts = candidate.split("\n", 1)
            first = parts[0].strip()
            if first.lower() == t.lower():
                candidate = parts[1].strip() if len(parts) > 1 else ""
            elif len(first) >= 12 and len(t) >= 12 and t.lower().startswith(first.lower()[:12]):
                candidate = parts[1].strip() if len(parts) > 1 else ""

        paras = [p.strip() for p in re.split(r"\n\s*\n+", candidate) if p.strip()]
        scored: list[tuple[int, str]] = []
        for p in paras:
            if self._looks_like_prompt_echo(p):
                continue
            pl = len(p)
            if pl < max(4, len(t) // 8 if t else 4):
                continue
            if t and pl > max(500, len(t) * 10):
                continue
            scored.append((abs(pl - len(t)), p))
        if scored:
            scored.sort(key=lambda x: x[0])
            return scored[0][1]

        if candidate and not self._looks_like_prompt_echo(candidate):
            cap = max(200, len(t) * 10) if t else 200
            if len(candidate) <= cap:
                return candidate

        return None

    # --- Prompt-echo fingerprints (substrings the LLM may regurgitate) ---
    _PROMPT_FINGERPRINTS = [
        "critical rules:",
        "conservative refinement:",
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
        # Assistant-behavior fingerprints (chatbot preambles / meta-talk)
        "as an ai",
        "as a language model",
        "i'd be happy to",
        "i can help",
        "let me help",
        "i'll do my best",
        "here's the corrected",
        "here is the refined",
        "here is the corrected",
        "here's the refined",
        "below is the",
        "i've refined",
        "i have refined",
    ]

    # Chatbot preamble patterns (output STARTS WITH these → assistant behavior)
    _ASSISTANT_PREFIXES = [
        "sure,", "sure!", "certainly,", "certainly!", "of course,", "of course!",
        "here is", "here's", "here are", "i'd be", "i can", "let me",
        "absolutely,", "absolutely!", "no problem",
    ]

    def _validate_output(self, original, refined):
        """Post-generation hallucination check. Returns original if output looks fabricated."""
        if not refined:
            return original

        orig_len = len(original)
        ref_len = len(refined)

        # Check 1: Output explosion (refined is absurdly longer than input)
        if orig_len > 0 and ref_len > max(200, orig_len * 5):
            log_transcription(f" [Hallucination Guard] Output explosion: {orig_len} -> {ref_len} chars. Returning original.")
            return original

        # Check 2: Prompt-echo detection (output contains system prompt fragments)
        refined_lower = refined.lower()
        for fp in self._PROMPT_FINGERPRINTS:
            if fp in refined_lower:
                log_transcription(f" [Hallucination Guard] Prompt echo detected: '{fp}'. Returning original.")
                return original

        # Check 3: Assistant-behavior detection (output starts with chatbot preambles)
        for prefix in self._ASSISTANT_PREFIXES:
            if refined_lower.startswith(prefix):
                log_transcription(f" [Hallucination Guard] Assistant preamble detected: '{prefix}'. Returning original.")
                return original

        # Check 4: Character-level repetition guard (e.g., "GGGGGGGG")
        # Matches any non-whitespace character repeated 4 or more times
        if re.search(r'([^\s\w])\1{4,}', refined) or re.search(r'([a-zA-Z])\1{6,}', refined):
            log_transcription(f" [Hallucination Guard] Excessive character repetition detected. Returning original.")
            return original

        # Check 5: Word-level repetition guard
        words = refined.split()
        if len(words) > 10:
            for i in range(len(words) - 5):
                if words[i:i+3] == words[i+3:i+6]:
                    log_transcription(f" [Hallucination Guard] Phrase repetition detected. Returning original.")
                    return original

        return refined

    def unload_model(self):
        if self.model:
            try:
                self.model.close()
            except Exception:
                pass
            del self.model
            self.model = None
            log_print("Grammar Model Unloaded.")


def _ensure_packaging_for_silero():
    """Silero hub code does `from packaging import version`; ensure a pip wheel is on sys.path."""
    try:
        import packaging  # noqa: F401
        return
    except ImportError:
        pass
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-input", "--no-cache-dir", "packaging>=23.0"],
        capture_output=True,
        text=True,
        timeout=300,
        creationflags=flags,
    )
    if r.returncode != 0:
        raise RuntimeError(
            "The 'packaging' package is missing (required by Silero VAD) and pip install failed "
            f"(exit {r.returncode}). stderr tail: {(r.stderr or '')[-800:]}"
        )
    importlib.invalidate_caches()
    import packaging  # noqa: F401


def _privox_vad_prefers_cuda() -> bool:
    """Default False: keep Silero VAD on CPU so GPU VRAM can approach zero when ASR/refiner unload."""
    v = (os.environ.get("PRIVOX_VAD_CUDA") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


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
        self.current_refiner = ""
        self.dictation_prompt = None
        self.command_prompt = None
        
        self.sound_manager = SoundManager(self.sound_enabled)
        
        # State
        self.q = queue.Queue()
        self.audio_buffer = [] 
        self.is_listening = False
        self.is_speaking = False
        self._heard_voice_energy = False
        self._last_loud_chunk_time = 0.0
        self.running = True
        self.stream = None
        self.mic_active = False
        
        self.models_ready = False
        self.loading_status = "Initializing..."
        self.ui_state = "LOADING"
        self._transcribe_task_id = 0
        
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
        self._asr_loaded_key = None  # (ASR_BACKEND, WHISPER_SIZE) after successful ASR load
        self.model_lock = threading.Lock()
        self._paste_clipboard_lock = threading.Lock()
        self.vram_timeout = 60 # Seconds before unloading
        # Idle unload policy: unload ASR with refiner after VRAM Saver timeout (wake-up reload is fast enough).
        self.use_simplified_chinese_output = False
        self.pending_wakeup = False # Auto-start recording after loading?
        # If True, user stopped recording (toggle or auto-stop) while ASR/LLM were still loading —
        # do not auto-start again when load finishes (avoids phantom sessions after VRAM saver wake).
        self._wakeup_autostart_cancelled = False
        self._heavy_model_load_in_progress = False  # suppress prefs hot-reload during ASR/LLM init
        self.last_model_error = ""
        self.model_load_started_at = 0.0
        self.model_load_timed_out = False
        self.model_load_stage = "idle"
        
        # Hotkey support
        self.hotkey_str = "f8"
        self.target_mods = set() # e.g. {'ctrl', 'shift'}
        self.target_key = "f8"
        self.active_mods = set()
        self.settings_process = None
        self.last_toggle_time = 0 # Hotkey de-bounce timer
        self._hotkey_primary_down = False  # True while primary key held; blocks OS key-repeat (phantom stop→start)
        self.last_config_reload_time = 0 # Cooldown for config polling
        self._last_prefs_hash = None # Hash-based change detection
        self._last_prefs_poll_mono = 0.0  # throttle prefs hot-reload (mic still fills queue when not listening)
        self._last_listener_watchdog_time = 0.0 # watchdog for keyboard listener
        self._hf_repo_verify_cache = {}  # repo_id -> (monotonic_ts, ok: bool); avoids HF spam on reload

        # Load Config (FINAL STEP of init to prevent overwriting by defaults)
        self.load_config()
        
        # Set initial state to show loading spinner
        self.update_status("INITIALIZING")

        # Start loading threads
        threading.Thread(target=self.initial_load, daemon=True).start()

    def _emit_runtime_error(self, title, message, error_detail="", include_thread_dump=False):
        """Surface runtime errors for EXE mode where console logs are not visible."""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = f"[{stamp}] {title}\n{message}\n\n{error_detail}\n"
        if include_thread_dump:
            try:
                frames = sys._current_frames()
                payload += "\n--- Thread Stack Dump ---\n"
                for t in threading.enumerate():
                    payload += f"\n[Thread: {t.name} | ident={t.ident}]\n"
                    frame = frames.get(t.ident)
                    if frame:
                        payload += "".join(traceback.format_stack(frame))
                    else:
                        payload += "No frame available.\n"
            except Exception as dump_err:
                payload += f"\n(Thread dump failed: {dump_err})\n"
        candidate_paths = [
            os.path.join(BASE_DIR, "privox_error_last.txt"),
            os.path.join(os.getcwd(), "privox_error_last.txt"),
            os.path.join(os.getenv("TEMP", BASE_DIR), "privox_error_last.txt"),
        ]
        try:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop", "privox_error_last.txt")
            candidate_paths.append(desktop)
        except Exception:
            pass

        seen = set()
        for path in candidate_paths:
            if not path or path in seen:
                continue
            seen.add(path)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(payload)
            except Exception:
                pass

        try:
            if self.icon:
                self.icon.notify(message, title)
        except Exception:
            pass

        # For packaged EXE, show a visible popup because stdout/stderr are hidden.
        if getattr(sys, "frozen", False):
            try:
                show_modern_error(title, message, error_detail[:600] if error_detail else "")
            except Exception:
                pass

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
        
        # In packaged EXE mode, prefer lazy heavy-model loading to avoid
        # startup hangs caused by backend/model initialization edge cases.
        if getattr(sys, "frozen", False):
            self.loading_status = "Ready (Lazy Model Warmup)"
            self.update_tray_tooltip()
            self.update_status("READY")
            return

        # In dev mode we still pre-load for faster first transcription.
        self.load_heavy_models()

    def _vad_end_silence_ms(self) -> int:
        """Silence after speech before Silero emits 'end'. Shorter than full Auto-Stop seconds (UI setting)."""
        st = int(getattr(self, "silence_timeout_ms", 10000) or 10000)
        return int(min(3500, max(550, st // 5)))

    def load_vad(self):
        if NO_TORCH:
            log_print("Loading WebRTC VAD (no PyTorch)...", end="", flush=True)
            try:
                from webrtc_vad_adapter import WebRtcVadAdapter

                self.vad_model = object()  # sentinel: VAD loaded (Silero uses nn.Module)
                self.get_speech_timestamps = None
                self.save_audio = None
                self.read_audio = None
                self.collect_chunks = None
                self.VADIterator = None
                self.vad_iterator = WebRtcVadAdapter(
                    aggressiveness=2,
                    sample_rate=SAMPLE_RATE,
                    min_silence_duration_ms=self._vad_end_silence_ms(),
                    speech_pad_ms=SPEECH_PAD_MS,
                )
                log_print("Done.")
                self.models_ready = True
            except Exception as e:
                log_print(f"\nError loading WebRTC VAD: {e}")
                self.loading_status = "Error Loading VAD"
                self.update_tray_tooltip()
                self.update_status("ERROR")
                self._emit_runtime_error(
                    "Privox VAD Error",
                    "Failed to load WebRTC VAD (install webrtcvad or unset PRIVOX_NO_TORCH).",
                    str(e),
                )
            return

        # 1. Load VAD Model (Silero)
        log_print("Loading Silero VAD...", end="", flush=True)
        try:
            _ensure_packaging_for_silero()
            # Force Torch Hub to use the local models folder for VAD
            hub_dir = os.path.join(BASE_DIR, "models", "hub")
            if not os.path.exists(hub_dir):
                os.makedirs(hub_dir, exist_ok=True)
            torch.hub.set_dir(hub_dir)
            
            self.vad_model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=False,
                trust_repo=True,  # headless / PyTorch 2.x hub security prompt
            )
            if _privox_vad_prefers_cuda() and torch.cuda.is_available():
                try:
                    self.vad_model = self.vad_model.cuda()
                except Exception as _cuda_vad_err:
                    log_print(f"VAD CUDA placement failed; using CPU: {_cuda_vad_err}")
                    try:
                        self.vad_model = self.vad_model.cpu()
                    except Exception:
                        pass
            else:
                try:
                    self.vad_model = self.vad_model.cpu()
                except Exception as _cpu_vad_err:
                    log_print(f"VAD CPU placement warning: {_cpu_vad_err}")
            try:
                self.vad_model.eval()
            except Exception:
                pass
            (self.get_speech_timestamps, self.save_audio, self.read_audio, self.VADIterator, self.collect_chunks) = utils
            self.vad_iterator = self.VADIterator(
                self.vad_model,
                threshold=VAD_THRESHOLD,
                sampling_rate=SAMPLE_RATE,
                min_silence_duration_ms=self._vad_end_silence_ms(),
                speech_pad_ms=SPEECH_PAD_MS,
            )
            log_print("Done.")
            self.models_ready = True # Allow microphone capturing immediately after VAD is ready
        except Exception as e:
            log_print(f"\nError loading Silero VAD: {e}")
            # Silero uses torch.hub (GitHub) + hub cache under models/hub — unrelated to whisper-* / GGUF weights.
            # Offline, strict proxies, or missing torchaudio often break hub load; fall back when possible.
            try:
                from webrtc_vad_adapter import WebRtcVadAdapter

                log_print(
                    "Silero VAD unavailable; falling back to WebRTC VAD. "
                    "(For Silero: ensure network once so torch.hub can populate models/hub, "
                    "or install torchaudio in the Pixi env.)"
                )
                self.vad_model = object()  # sentinel (same as PRIVOX_NO_TORCH path)
                self.get_speech_timestamps = None
                self.save_audio = None
                self.read_audio = None
                self.VADIterator = None
                self.collect_chunks = None
                self.vad_iterator = WebRtcVadAdapter(
                    aggressiveness=2,
                    sample_rate=SAMPLE_RATE,
                    min_silence_duration_ms=self._vad_end_silence_ms(),
                    speech_pad_ms=SPEECH_PAD_MS,
                )
                log_print("WebRTC VAD ready.")
                self.models_ready = True
                self.loading_status = "Ready (WebRTC VAD)"
                self.update_tray_tooltip()
                self.update_status("READY")
                return
            except Exception as e2:
                log_print(f"WebRTC VAD fallback failed: {e2}")

            self.loading_status = "Error Loading VAD"
            self.update_tray_tooltip()
            self.update_status("ERROR")
            self._emit_runtime_error(
                "Privox VAD Error",
                "Failed to load VAD (Silero via torch.hub and WebRTC fallback). "
                "Silero needs a one-time download into models/hub (GitHub) and torchaudio in the env; "
                "or install webrtcvad for offline WebRTC VAD.",
                f"Silero: {e}\nWebRTC: {e2}",
            )
            return

    def load_heavy_models(self):
        """Concurrent loading of ASR and Grammar models to minimize wake-up latency."""
        with self.model_lock:
            if self.heavy_models_loaded:
                return

            self._heavy_model_load_in_progress = True
            try:
                log_print("Loading Heavy Models (Wake up)...")
                self.loading_status = "Loading Models..."
                self.update_tray_tooltip()
                self.model_load_started_at = time.time()
                self.model_load_timed_out = False
                self.model_load_stage = "starting"

                def load_watchdog():
                    # If model loading hangs (no exception), surface a visible timeout error.
                    while True:
                        time.sleep(2)
                        if self.heavy_models_loaded or self.loading_status in ["ASR Load Error", "Error Loading ASR", "Error Loading VAD"]:
                            return
                        stage = getattr(self, "model_load_stage", "")
                        if stage == "loading_asr_hf_download":
                            try:
                                timeout_s = int(
                                    (os.environ.get("PRIVOX_ASR_HF_DOWNLOAD_TIMEOUT_S") or "7200").strip()
                                )
                            except ValueError:
                                timeout_s = 7200
                        else:
                            try:
                                timeout_s = int(
                                    (os.environ.get("PRIVOX_MODEL_LOAD_TIMEOUT_S") or "240").strip()
                                )
                            except ValueError:
                                timeout_s = 240
                        if self.model_load_started_at and (time.time() - self.model_load_started_at) > timeout_s:
                            self.model_load_timed_out = True
                            self.last_model_error = (
                                f"Model loading exceeded {timeout_s}s. "
                                f"Current stage: {self.model_load_stage}. "
                                "Likely a backend init hang."
                                + (
                                    " First-time Qwen ONNX download can take 15–60+ minutes — "
                                    "increase PRIVOX_ASR_HF_DOWNLOAD_TIMEOUT_S (default 7200s) if needed."
                                    if stage == "loading_asr_hf_download"
                                    else ""
                                )
                            )
                            self.loading_status = "Model Load Timeout"
                            self.update_tray_tooltip()
                            self.update_status("ERROR")
                            self._emit_runtime_error(
                                "Privox Model Timeout",
                                "Model loading timed out.",
                                self.last_model_error,
                                include_thread_dump=True,
                            )
                            return

                threading.Thread(target=load_watchdog, daemon=True).start()

                def load_grammar():
                    try:
                        self.model_load_stage = "loading_grammar"
                        t0 = time.time()
                        success = self.grammar_checker.load_model()
                        dt = time.time() - t0
                        log_print(f"Grammar load time: {dt:.2f}s (success={success})")
                        if success:
                            # Track LLM usage here
                            self.track_model_usage(self.current_refiner)
                        return success
                    except Exception as e:
                        log_print(f"Parallel Load Error (Grammar): {e}")
                        self.last_model_error = f"Grammar: {e}"
                        return False

                def load_asr():
                    try:
                        self.model_load_stage = "loading_asr"
                        t0 = time.time()
                        if NO_TORCH and ASR_BACKEND in ("qwen_asr", "sensevoice"):
                            raise RuntimeError(
                                f"ASR backend '{ASR_BACKEND}' requires PyTorch. "
                                "Unset PRIVOX_NO_TORCH or switch ASR to faster-whisper in Settings."
                            )
                        is_gpu = cuda_is_available()
                        device_str = "cuda" if is_gpu else "cpu"

                        if ASR_BACKEND == "sensevoice":
                            sense_dir = os.path.join(BASE_DIR, "models", "SenseVoiceSmall")
                            log_print(f"ASR Diagnostic - Initializing SenseVoiceSmall on {device_str}...")
                            try:
                                from funasr import AutoModel
                            except ImportError as e:
                                log_print(
                                    "SenseVoice requires the `funasr` package (not bundled by default). "
                                    "Install with: pixi add --pypi funasr   or   pip install funasr"
                                )
                                raise RuntimeError(
                                    "ASR backend 'sensevoice' needs funasr. Add it to your env or switch ASR in Settings."
                                ) from e
                            self.asr_model = AutoModel(
                                model=sense_dir if os.path.exists(sense_dir) else "iic/SenseVoiceSmall",
                                device=device_str,
                                disable_update=True
                            )
                            log_print(f"SenseVoice initialized successfully.")

                        elif ASR_BACKEND == "qwen_asr":
                            log_print(f"ASR Diagnostic - Initializing Qwen3ASRModel ({WHISPER_REPO}) on {device_str}...")
                            from qwen_asr import Qwen3ASRModel

                            if is_gpu:
                                cap_env = (os.environ.get("PRIVOX_ASR_MAX_GPU_GIB") or "").strip()
                                cap_gib = None
                                if cap_env:
                                    try:
                                        cap_gib = float(cap_env)
                                    except ValueError:
                                        cap_gib = None
                                if cap_gib is None:
                                    try:
                                        total_gib = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                                    except Exception:
                                        total_gib = 12.0
                                    if total_gib <= 8.5:
                                        cap_gib = max(2.25, total_gib * 0.38)
                                    elif total_gib <= 13.0:
                                        cap_gib = max(3.0, total_gib * 0.42)
                                    else:
                                        cap_gib = min(5.5, max(3.5, total_gib * 0.28))
                                max_mem = {0: f"{cap_gib:.2f}GiB", "cpu": "12GiB"}
                                dtype = torch.float16
                                try:
                                    if torch.cuda.is_bf16_supported():
                                        dtype = torch.bfloat16
                                except Exception:
                                    pass
                                log_print(
                                    f"Qwen-ASR VRAM cap ~{cap_gib:.2f} GiB on GPU (set PRIVOX_ASR_MAX_GPU_GIB to override); dtype={dtype}"
                                )
                            else:
                                max_mem = None
                                dtype = torch.float32

                            self.asr_model = Qwen3ASRModel.from_pretrained(
                                WHISPER_REPO,
                                dtype=dtype,
                                low_cpu_mem_usage=True,
                                local_files_only=True,
                            )
                            if is_gpu:
                                self.asr_model.model.to("cuda")
                            log_print("Qwen3ASRModel initialized successfully.")
                        else:
                            # int8_float16 cuts VRAM vs pure float16 on CUDA with small quality cost.
                            compute_type = "int8_float16" if is_gpu else "int8"
                            from faster_whisper import WhisperModel
                            local_whisper = os.path.join(BASE_DIR, "models", f"whisper-{WHISPER_SIZE}")
                            model_path = local_whisper if os.path.exists(os.path.join(local_whisper, "model.bin")) else WHISPER_REPO
                            log_print(
                                f"ASR Diagnostic - Initializing WhisperModel ({WHISPER_SIZE}) on {device_str}, compute_type={compute_type}..."
                            )
                            try:
                                self.asr_model = WhisperModel(
                                    model_path, device=device_str, compute_type=compute_type, cpu_threads=4
                                )
                            except Exception as e1:
                                if is_gpu and compute_type == "int8_float16":
                                    log_print(f"Whisper int8_float16 failed ({e1}); retrying float16...")
                                    self.asr_model = WhisperModel(
                                        model_path, device=device_str, compute_type="float16", cpu_threads=4
                                    )
                                else:
                                    raise
                            log_print("WhisperModel initialized successfully.")

                        # Track ASR model usage here instead of in load_config
                        self.track_model_usage(getattr(self, 'active_asr_name', WHISPER_SIZE))
                        self._asr_loaded_key = (ASR_BACKEND, WHISPER_SIZE)
                        dt = time.time() - t0
                        log_print(f"ASR load time: {dt:.2f}s (backend={ASR_BACKEND})")
                        return True
                    except Exception as e:
                        log_print(f"Parallel Load Error (ASR): {e}")
                        self.last_model_error = f"ASR: {e}\n{traceback.format_exc()}"
                        self.loading_status = "Error Loading ASR"
                        return False

                def _env_sequential_qwen() -> bool:
                    v = (os.environ.get("PRIVOX_SEQUENTIAL_QWEN_LOAD") or "").strip().lower()
                    return v in ("1", "true", "yes", "on")

                # Sequential vs Parallel loading strategy
                # Forcing Sequential Mode for all backends to prevent severe CPU saturation and OOMs.
                log_print("Using Sequential Load Strategy to prevent CPU spikes...")
                
                old_threads = 4  # Fallback
                _t = get_torch()
                if _t is not None:
                    try:
                        old_threads = _t.get_num_threads()
                        _t.set_num_threads(1)
                    except Exception:
                        pass

                try:
                    res_grammar = load_grammar()
                    res_asr = load_asr()

                finally:
                    if _t is not None:
                        try:
                            _t.set_num_threads(old_threads)
                        except Exception:
                            pass
                        
                results = [res_grammar, res_asr]

                if not results[1]:  # ASR is mandatory
                    log_print("CRITICAL: ASR model failed to load.")
                    self.loading_status = "ASR Load Error"
                    self.update_tray_tooltip()
                    self.update_status("ERROR")
                    if self.icon and self.last_model_error:
                        try:
                            self.icon.notify(f"Privox model load failed: {self.last_model_error}", "Privox Error")
                        except Exception:
                            pass
                    self._emit_runtime_error(
                        "Privox Model Load Error",
                        "Failed to load speech model (ASR).",
                        self.last_model_error,
                    )
                    self.pending_wakeup = False
                    self.model_load_stage = "failed_asr"
                    return

                if not results[0]:
                    log_print("WARNING: Grammar model failed to load. Proceeding with ASR only.")

                self.heavy_models_loaded = True
                self.model_load_started_at = 0.0
                self.model_load_stage = "ready"
                self.loading_status = "Ready" if results[0] else "ASR Only"
                # Do not clobber RECORDING: user may have started the mic while models were still loading.
                if self.is_listening:
                    self.update_status("RECORDING")
                else:
                    self.update_status("READY")

                # Reset activity timer so we don't immediately unload
                self.last_activity_time = time.time()

                # If this was a manual F8 wakeup, we might already be listening.
                # Otherwise (initial load), we play the 'Ready' sound.
                if self.pending_wakeup:
                    self.pending_wakeup = False
                    if not self.is_listening:
                        if self._wakeup_autostart_cancelled:
                            log_print(
                                "Pending Wakeup: recording stopped during model load; skipping auto-start "
                                "(press hotkey again to record)."
                            )
                        else:
                            log_print("Pending Wakeup found. Auto-starting recording...")
                            # Tiny delay to ensure UI updates and avoid race conditions with sound manager
                            time.sleep(0.1)
                            self.start_listening()
                    else:
                        log_print("Pending Wakeup found, but already listening. Skipping auto-start.")
                else:
                    self.sound_manager.play_start()
            finally:
                # track_model_usage() updates .user_prefs.json during load; align poll baseline
                # so we do not spuriously run load_config() right after wake (log noise + extra work).
                try:
                    self._sync_prefs_poll_from_disk()
                except Exception:
                    pass
                self._heavy_model_load_in_progress = False
                
                # CRITICAL: Reset the silence budget now that we are actually ready to process.
                self.last_activity_time = time.time()
                self._last_loud_chunk_time = time.time()
                self._heard_voice_energy = False
                
                # --- SAFE AUDIO START ---
                if not self.mic_active:
                    log_print("Models loaded (or skipped). Starting audio system...")
                    self.start_audio_stream()

    def unload_heavy_models(self):
        with self.model_lock:
            if not self.heavy_models_loaded:
                return
            
            idle_time = time.time() - self.last_activity_time
            log_print(f"Unloading Models (VRAM Saver - Idle for {idle_time:.1f}s)...")
            
            if self.asr_model is not None:

                
                # Targeted internal model cleanup
                try:
                    models_to_clean = [self.asr_model]
                    if hasattr(self.asr_model, "model"):
                        models_to_clean.append(self.asr_model.model)
                    
                    for m in models_to_clean:
                        try:
                            if hasattr(m, "cpu"): m.cpu()
                        except: pass
                except: pass

                if ASR_BACKEND == "qwen_asr":
                    log_print("Qwen-ASR reference preserved locally in RAM.")
                else:
                    self.asr_model = None
                    log_print("ASR model reference destroyed.")
            
            self.grammar_checker.unload_model()
            self.grammar_checker.context_buffer = "" # Clear conversation context
            
            # CRITICAL: Force garbage collection to reclaim VRAM from C++ backends
            import gc
            gc.collect()
            log_print("VRAM Saver: Garbage collection forced.")

            if self.vad_model is not None and not NO_TORCH and not _privox_vad_prefers_cuda():
                try:
                    # WebRTC fallback uses a non-module sentinel; only real Silero nn.Module supports .cpu().
                    if hasattr(self.vad_model, "cpu"):
                        self.vad_model.cpu()
                    if hasattr(self, "VADIterator") and self.VADIterator is not None:
                        self.vad_iterator = self.VADIterator(
                            self.vad_model,
                            threshold=VAD_THRESHOLD,
                            sampling_rate=SAMPLE_RATE,
                            min_silence_duration_ms=self._vad_end_silence_ms(),
                            speech_pad_ms=SPEECH_PAD_MS,
                        )
                except Exception as _vad_idle_err:
                    log_print(f"VAD idle CPU refresh: {_vad_idle_err}")

            # Flush CUDA and Force Garbage Collection
            _t = get_torch()
            try:
                if _t is not None and _t.cuda.is_available():
                    _t.cuda.synchronize()
            except Exception:
                pass

            # Double cycle with driver 'breather' ensures full cleanup of cyclic references
            for _ in range(2):
                gc.collect()
                if _t is not None:
                    try:
                        if _t.cuda.is_available():
                            _t.cuda.empty_cache()
                    except Exception:
                        pass
                time.sleep(0.1)
            
            self.heavy_models_loaded = False
            self._asr_loaded_key = None
            self.loading_status = "Idle (VRAM Free)"
            self.update_tray_tooltip()
            self.update_status("SLEEP") # Trigger flat line animation
            log_print("Models Unloaded. VRAM released.")

    def _sync_prefs_poll_from_disk(self):
        """Refresh hot-reload snapshot so internal prefs writes do not trigger load_config."""
        prefs_path = os.path.join(BASE_DIR, ".user_prefs.json")
        if os.path.exists(prefs_path):
            self._last_prefs_mtime = os.path.getmtime(prefs_path)
            with open(prefs_path, "rb") as f:
                self._last_prefs_hash = hashlib.md5(f.read()).hexdigest()

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
            config = _safe_json_load(config_path, "config.json") if os.path.exists(config_path) else {}

            # --- 2. Load User Preferences (Hidden/Private) ---
            prefs = _safe_json_load(prefs_path, ".user_prefs.json") if os.path.exists(prefs_path) else {}

            # --- 3. Migration Logic (Move settings from config -> prefs) ---
            pref_keys = [
                "hotkey", "sound_enabled", "vram_timeout", "character", "tone", 
                "custom_prompts", "auto_stop_enabled", "silence_timeout_ms", 
                "custom_dictionary", "current_refiner", "whisper_model",
                "asr_library", "llm_library",
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
                
            # --- 3b. Refiner migration for removed legacy options ---
            removed_refiners = {
                "CoEdit Large (T5)",
                "Llama 3.2 3B Instruct",
                "Standard (Llama 3.2)",
                "Multilingual (Qwen 3.5 9B)",
                "Multilingual (Qwen 2.5 7B)",
                "Multilingual (Qwen 3.5 4B)",
            }
            if prefs.get("current_refiner") in removed_refiners:
                prefs["current_refiner"] = models_config.DEFAULT_LLM
                with open(prefs_path, "w", encoding="utf-8") as f:
                    json.dump(prefs, f, indent=4)

            _gem = models_config.LLM_LIBRARY[0]
            if config.get("grammar_file") == "Qwen3.5-4B-Q4_K_M.gguf" or config.get("grammar_repo") == "unsloth/Qwen3.5-4B-GGUF":
                config["grammar_repo"] = _gem["repo_id"]
                config["grammar_file"] = _gem["file_name"]
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=4)
            
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

            self.sound_enabled = prefs.get("sound_enabled", True)
            self.auto_stop_enabled = prefs.get("auto_stop_enabled", True)
            old_silence = getattr(self, "silence_timeout_ms", 10000)
            # Backend Clamping: Min 5s
            self.silence_timeout_ms = max(5000, prefs.get("silence_timeout_ms", 10000))
            
            # Dynamic VAD Re-initialization if timeout changed
            if self.vad_model and self.silence_timeout_ms != old_silence:
                log_print(f"Applying new Auto-Stop Timeout: {self.silence_timeout_ms}ms")
                if NO_TORCH:
                    from webrtc_vad_adapter import WebRtcVadAdapter

                    self.vad_iterator = WebRtcVadAdapter(
                        aggressiveness=2,
                        sample_rate=SAMPLE_RATE,
                        min_silence_duration_ms=self._vad_end_silence_ms(),
                        speech_pad_ms=SPEECH_PAD_MS,
                    )
                elif hasattr(self, "VADIterator") and self.VADIterator is not None:
                    self.vad_iterator = self.VADIterator(
                        self.vad_model,
                        threshold=VAD_THRESHOLD,
                        sampling_rate=SAMPLE_RATE,
                        min_silence_duration_ms=self._vad_end_silence_ms(),
                        speech_pad_ms=SPEECH_PAD_MS,
                    )

            self.custom_dictionary = prefs.get("custom_dictionary", [])
            self.vram_timeout = max(5, prefs.get("vram_timeout", 60))
            self.use_simplified_chinese_output = bool(prefs.get("use_simplified_chinese_output", False))
            self.character = prefs.get("character", "Writing Assistant")
            self.tone = prefs.get("tone", "Natural")
            self.custom_prompts = prefs.get("custom_prompts", {})
            old_refiner = getattr(self, "current_refiner", "")
            self.current_refiner = prefs.get("current_refiner", models_config.DEFAULT_LLM)
            
            # Library Loading: Use source-of-truth from code to avoid stale cached libraries
            # in .user_prefs.json causing wrong model selection.
            self.asr_library = models_config.ASR_LIBRARY
            self.llm_library = models_config.LLM_LIBRARY

            # Filter ASR library only. For LLM/refiner, keep source-of-truth entries
            # even if network verification is temporarily unavailable.
            self.asr_library = [m for m in self.asr_library if self.verify_model(m, "asr")]

            # Sync Current Profile from Library
            profile = {}
            for p in self.llm_library:
                if p["name"] == self.current_refiner:
                    profile = {
                        "name": p.get("name"),
                        "repo_id": p.get("repo_id"),
                        "file_name": p.get("file_name"),
                        "prompt_type": p.get("prompt_type"),
                        "description": p.get("description", ""),
                        "turboquant": p.get("turboquant", False),
                        "n_ctx": p.get("n_ctx"),
                        "n_gpu_layers": p.get("n_gpu_layers"),
                    }
                    # REMOVED recursive usage tracking here
                    break

            # If current_refiner is missing from library, force a stable fallback
            # to avoid accidental fallback to stale global defaults.
            if not profile and self.llm_library:
                fallback = self.llm_library[0]
                log_print(f"WARNING: Refiner '{self.current_refiner}' not found in active library. Falling back to '{fallback.get('name')}'.")
                self.current_refiner = fallback.get("name", models_config.DEFAULT_LLM)
                profile = {
                    "name": fallback.get("name"),
                    "repo_id": fallback.get("repo_id"),
                    "file_name": fallback.get("file_name"),
                    "prompt_type": fallback.get("prompt_type"),
                    "description": fallback.get("description", ""),
                    "turboquant": fallback.get("turboquant", False),
                    "n_ctx": fallback.get("n_ctx"),
                    "n_gpu_layers": fallback.get("n_gpu_layers"),
                }
            
            if hasattr(self, 'grammar_checker'):
                # --- Refiner Model Hot-Reload ---
                if self.current_refiner != old_refiner:
                    log_print(f"Refiner change detected: {old_refiner} -> {self.current_refiner}")
                    self.grammar_checker.profile = profile
                    if self.heavy_models_loaded:
                        log_print("Hot-swapping Grammar Model...")
                        self.grammar_checker.unload_model()
                        self.grammar_checker.load_model()
                else:
                    self.grammar_checker.profile = profile
                
                # Clear context cache if personality/tone changes abruptly to prevent bleed
                if self.grammar_checker.character != self.character or self.grammar_checker.tone != self.tone:
                     self.grammar_checker.context_buffer = ""
                     
                self.grammar_checker.character = self.character
                self.grammar_checker.tone = self.tone
                self.grammar_checker.custom_prompts = self.custom_prompts
                self.grammar_checker.custom_dictionary = self.custom_dictionary
                self.grammar_checker.use_simplified_chinese_output = self.use_simplified_chinese_output
            
            # ASR Model resolution
            global WHISPER_SIZE, WHISPER_REPO, ASR_BACKEND, WHISPER_TRANSCRIBE_LANGUAGE
            old_whisper = WHISPER_SIZE
            _wm_pref = prefs.get("whisper_model")
            _prefs_wm_missing = not _wm_pref
            if not _wm_pref:
                _wr_cfg = (config.get("whisper_repo") or "").strip()
                if _wr_cfg:
                    for m in models_config.ASR_LIBRARY:
                        if (m.get("whisper_repo") or m.get("repo") or "").strip() == _wr_cfg:
                            _wm_pref = m.get("name")
                            break
            if not _wm_pref:
                _wm_pref = models_config.DEFAULT_ASR
            if _prefs_wm_missing and _wm_pref and _wm_pref != models_config.DEFAULT_ASR:
                prefs["whisper_model"] = _wm_pref
                try:
                    with open(prefs_path, "w", encoding="utf-8") as f:
                        json.dump(prefs, f, indent=4)
                except OSError:
                    pass
            self.active_asr_name = _wm_pref
            active_asr = self.active_asr_name
            _ct2_env = (os.environ.get("PRIVOX_CT2_ASR") or "").strip().lower()
            _force_whisper = _ct2_env in ("1", "true", "yes", "on") or NO_TORCH
            if _force_whisper:
                # Only replace the user's Settings choice when it is a PyTorch ASR (Qwen / SenseVoice).
                # PRIVOX_CT2_ASR / NO_TORCH must not clobber a saved faster-whisper model (e.g. Large v3 Turbo).
                _saved_for_ct2 = active_asr
                _needs_torch_asr = False
                for asr in self.asr_library:
                    if asr["name"] == _saved_for_ct2 or asr.get("whisper_model") == _saved_for_ct2:
                        _needs_torch_asr = asr.get("backend", "whisper") in ("qwen_asr", "sensevoice")
                        break
                if _needs_torch_asr:
                    active_asr = models_config.DEFAULT_ASR
                    self.active_asr_name = active_asr
                    log_print(
                        "PRIVOX_CT2_ASR / PRIVOX_NO_TORCH: saved ASR needs PyTorch — "
                        f"switched to default faster-whisper ({models_config.DEFAULT_ASR})."
                    )
                if NO_TORCH:
                    log_print(
                        "PRIVOX_NO_TORCH: WebRTC VAD; PyTorch ASR (Qwen-ASR / SenseVoice) disabled — "
                        "faster-whisper (CT2) and/or Qwen ONNX ASR still allowed."
                    )
                if _ct2_env in ("1", "true", "yes", "on") and not _needs_torch_asr:
                    log_print(
                        "PRIVOX_CT2_ASR: CTranslate2 ASR path — "
                        f"using whisper_model from settings ({_saved_for_ct2})."
                    )

            # Find in library
            WHISPER_REPO = "Systran/faster-distil-whisper-large-v3" # Defaults
            WHISPER_SIZE = "distil-large-v3"
            WHISPER_TRANSCRIBE_LANGUAGE = None

            ASR_BACKEND = "whisper"
            matched_asr = False
            for asr in self.asr_library:
                if asr["name"] == active_asr or asr.get("whisper_model") == active_asr:
                    # Sync with library technical names
                    WHISPER_REPO = asr.get("whisper_repo") or asr.get("repo")
                    WHISPER_SIZE = asr.get("whisper_model") or asr.get("name")
                    ASR_BACKEND = asr.get("backend", "whisper")
                    _wl = asr.get("whisper_language")
                    WHISPER_TRANSCRIBE_LANGUAGE = (_wl or "").strip() or None
                    matched_asr = True
                    break
            if not matched_asr and self.asr_library:
                log_print(
                    f"WARNING: ASR choice '{active_asr}' not in active library "
                    f"(removed or offline). Falling back to '{models_config.DEFAULT_ASR}'."
                )
                for asr in self.asr_library:
                    if asr["name"] == models_config.DEFAULT_ASR:
                        WHISPER_REPO = asr.get("whisper_repo") or asr.get("repo")
                        WHISPER_SIZE = asr.get("whisper_model") or asr.get("name")
                        ASR_BACKEND = asr.get("backend", "whisper")
                        _wl = asr.get("whisper_language")
                        WHISPER_TRANSCRIBE_LANGUAGE = (_wl or "").strip() or None
                        self.active_asr_name = asr["name"]
                        break

            if NO_TORCH and ASR_BACKEND in ("qwen_asr", "sensevoice"):
                log_print(
                    f"PRIVOX_NO_TORCH: ASR backend '{ASR_BACKEND}' needs PyTorch; using faster-whisper defaults."
                )
                ASR_BACKEND = "whisper"
                for asr in self.asr_library:
                    if asr.get("name") == models_config.DEFAULT_ASR:
                        WHISPER_REPO = asr.get("whisper_repo") or asr.get("repo") or WHISPER_REPO
                        WHISPER_SIZE = asr.get("whisper_model") or asr.get("name") or WHISPER_SIZE
                        _wl = asr.get("whisper_language")
                        WHISPER_TRANSCRIBE_LANGUAGE = (_wl or "").strip() or None
                        self.active_asr_name = asr["name"]
                        break

            if getattr(self, "heavy_models_loaded", False) and getattr(self, "_asr_loaded_key", None) is not None:
                if self._asr_loaded_key != (ASR_BACKEND, WHISPER_SIZE):
                    log_print(
                        "ASR preset changed (settings) but the previous ASR is still loaded. "
                        "Restart Privox, or wait for VRAM idle unload and transcribe again to load: "
                        f"backend={ASR_BACKEND}, folder id={WHISPER_SIZE}."
                    )
            
            # REMOVED cleanup_stale_models from here to prevent recursive reload loops

            # Config reload can interleave with model load; avoid stuck INITIALIZING / wrong tray state.
            if getattr(self, "heavy_models_loaded", False) and getattr(self, "ui_state", "") == "INITIALIZING":
                if self.is_listening:
                    self.update_status("RECORDING")
                else:
                    self.update_status("READY")

        except Exception as e:
            import traceback as _tb

            log_print(f"Error loading config: {e}")
            _tb.print_exc()

    def verify_model(self, model_data, model_type):
        """Verifies if a model repository or local path exists."""
        repo = model_data.get("repo")
        local_path = model_data.get("local_path")
        whisper_model = model_data.get("whisper_model")
        file_name = model_data.get("file_name")
        
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
            target = os.path.join(models_dir, f"whisper-{whisper_model}")
            if os.path.isdir(target):
                if model_data.get("backend") == "qwen_asr_onnx":
                    try:
                        from qwen3_asr_onnx import onnx_bundle_is_complete

                        if onnx_bundle_is_complete(target):
                            return True
                    except Exception:
                        pass
                    # Folder exists but ONNX bundle incomplete (or partial download): do not return False
                    # here — fall through to HuggingFace repo check so the preset stays in the library.
                elif os.path.exists(os.path.join(target, "model.bin")) or os.path.exists(
                    os.path.join(target, "config.json")
                ):
                    return True
        elif model_type == "llm" and file_name:
            target = os.path.join(models_dir, file_name)
            if os.path.exists(target):
                return True

        # 3. Check HuggingFace Repo (Fast head request) - Fallback for un-downloaded models
        if repo:
            ttl = 120.0
            now = time.monotonic()
            hit = self._hf_repo_verify_cache.get(repo)
            if hit is not None and (now - hit[0]) < ttl:
                return hit[1]
            try:
                HfApi().repo_info(repo_id=repo)
                self._hf_repo_verify_cache[repo] = (now, True)
                return True
            except Exception:
                log_print(f"Verification Failed for model (and not found locally): {repo}")
                self._hf_repo_verify_cache[repo] = (now, False)
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
        """Tray title: prefer live ui_state (listening/processing) over loading_status so prefs reload does not clobber RECORDING."""
        if not self.icon:
            return
        gpu_status = "GPU" if cuda_is_available() else "CPU"
        hk_display = getattr(self, "hotkey_str", "F8").upper()
        st = getattr(self, "ui_state", "READY")

        if st == "RECORDING":
            self.icon.title = f"Privox: Listening... ({gpu_status})\nHotkey: {hk_display}"
        elif st == "PROCESSING":
            self.icon.title = f"Privox: Processing... ({gpu_status})\nHotkey: {hk_display}"
        elif st == "INITIALIZING":
            self.icon.title = f"Privox: {self.loading_status} ({gpu_status})\nHotkey: {hk_display}"
        elif st == "DOWNLOADING":
            self.icon.title = f"Privox: Downloading model... ({gpu_status})\nHotkey: {hk_display}"
        elif st == "ERROR":
            self.icon.title = f"Privox: Error ({gpu_status})\nHotkey: {hk_display}"
        elif st == "SLEEP":
            self.icon.title = f"Privox: Sleeping (VRAM saver) ({gpu_status})\nHotkey: {hk_display}"
        else:
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

    def _listener_key_token(self, key):
        """Normalize pynput key to the same token used for self.target_key (e.g. 'f8', 'space')."""
        try:
            k_name = getattr(key, "name", None)
            k_char = getattr(key, "char", None)
            k_vk = getattr(key, "vk", None)

            if k_name:
                return k_name
            if k_vk and 65 <= k_vk <= 90:
                return chr(k_vk).lower()
            if k_vk and 48 <= k_vk <= 57:
                return chr(k_vk)
            if k_char:
                if 1 <= ord(k_char) <= 26:
                    return chr(ord(k_char) + 96)
                return k_char.lower()
            if k_vk:
                vk_map = {
                    0x70: "f1", 0x71: "f2", 0x72: "f3", 0x73: "f4",
                    0x74: "f5", 0x75: "f6", 0x76: "f7", 0x77: "f8",
                    0x78: "f9", 0x79: "f10", 0x7A: "f11", 0x7B: "f12",
                    0x7C: "f13", 0x7D: "f14", 0x7E: "f15", 0x7F: "f16",
                    0x80: "f17", 0x81: "f18", 0x82: "f19", 0x83: "f20",
                    0x84: "f21", 0x85: "f22", 0x86: "f23", 0x87: "f24",
                    0x20: "space", 0x0D: "enter", 0x09: "tab", 0x1B: "esc",
                    0x21: "page_up", 0x22: "page_down", 0x23: "end", 0x24: "home",
                    0x2D: "insert", 0x2E: "delete",
                }
                return vk_map.get(k_vk, str(k_vk))
        except Exception:
            pass
        return ""

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

        key_name = self._listener_key_token(key)

        # 3. Check Match
        if key_name == self.target_key:
            # OS key-repeat sends repeated key-down without key-up; first down toggles, repeats must not
            # (otherwise: stop session -> repeat arrives after debounce -> starts a phantom session).
            if self._hotkey_primary_down:
                return

            # Win32 Robustness: Check for "Stuck" modifiers using ctypes
            if sys.platform == 'win32' and self.active_mods != self.target_mods:
                import ctypes
                stuck = []
                for mod in list(self.active_mods):
                    vk = 0
                    if mod == 'ctrl': vk = 0x11
                    elif mod == 'shift': vk = 0x10
                    elif mod == 'alt': vk = 0x12
                    
                    if vk and not (ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000):
                        stuck.append(mod)
                
                if stuck:
                    log_print(f" [Hotkey Diagnostic] Clearing stuck modifiers: {stuck}")
                    for mod in stuck:
                        self.active_mods.remove(mod)

            if self.active_mods != self.target_mods:
                log_print(f" [Hotkey Ignored] Key '{key_name}' pressed, but modifiers mismatch. Expected: {self.target_mods}, Actual: {self.active_mods}")
                return

            now = time.time()
            if now - self.last_toggle_time < 0.4:
                return

            self._hotkey_primary_down = True
            self.last_toggle_time = now
            self.toggle_hotkey()

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

        key_name = self._listener_key_token(key)
        if key_name == self.target_key:
            self._hotkey_primary_down = False

    def start_listening(self):
        self._transcribe_task_id += 1
        self.last_activity_time = time.time()
        log_print("\n[Start Listening]", flush=True)
        self.sound_manager.play_start()
        self.is_listening = True
        self.is_speaking = False
        self._heard_voice_energy = False
        self._last_loud_chunk_time = time.time()
        self.audio_buffer = []
        if self.vad_iterator:
            self.vad_iterator.reset_states()
        self.update_status("RECORDING")
        self.update_tray_tooltip()

    def stop_listening(self):
        log_print(" [Stopped]", flush=True)
        self.sound_manager.play_stop()
        # Any stop during a VRAM-saver wake load means "do not auto-start when load finishes"
        # (covers auto-stop and toggle-off; avoids race vs setting heavy_models_loaded before this runs).
        if self.pending_wakeup:
            self._wakeup_autostart_cancelled = True
        self.is_listening = False
        self.update_status("PROCESSING")
        self.update_tray_tooltip()

        if len(self.audio_buffer) > 0:
            audio_segment = np.array(self.audio_buffer)
            task_id = getattr(self, "_transcribe_task_id", 0)
            # Run transcription in a separate thread so we don't block the keyboard listener!
            threading.Thread(target=self.transcribe, args=(audio_segment, task_id), daemon=True).start()
        else:
             self.update_status("READY")
             
        self.audio_buffer = []
        self.last_activity_time = time.time()

    def _run_with_timeout(self, func, timeout_s, label):
        """Run a blocking callable with timeout to prevent permanent PROCESSING state."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(func)
            try:
                return fut.result(timeout=timeout_s)
            except concurrent.futures.TimeoutError:
                self.loading_status = "Refiner Error" if "Refiner" in label else "ASR Error"
                self.last_model_error = f"{label} timed out after {timeout_s}s"
                self._emit_runtime_error(
                    "Privox Processing Timeout",
                    f"{label} timed out.",
                    self.last_model_error,
                )
                raise TimeoutError(self.last_model_error)

    def transcribe(self, audio_data, task_id=None):
        try:
            duration = len(audio_data) / SAMPLE_RATE
            max_amp = np.max(np.abs(audio_data))
            rms = np.sqrt(np.mean(audio_data**2))
            
            log_transcription(f"\n--- Transcription Diagnostic ---")
            log_transcription(f"Audio Stats - Duration: {duration:.2f}s, Max Amp: {max_amp:.4f}, RMS: {rms:.4f}")
            
            if duration < (MIN_SPEECH_DURATION_MS / 1000):
                log_transcription(f" [Audio too short - Ignored]")
                self.update_status("READY")
                return

            if max_amp < 0.001: 
                log_transcription(f" [Audio too quiet - Ignored]")
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

            _asr_label = getattr(self, "active_asr_name", None) or (
                WHISPER_SIZE
                if ASR_BACKEND == "whisper"
                else WHISPER_REPO
            )
            log_transcription(f" Transcribing Using Backend: {ASR_BACKEND} (Model: {_asr_label})...", flush=True)
            t0 = time.time()
            
            raw_text = ""
            info = None
            if ASR_BACKEND == "sensevoice":
                # SenseVoice/funasr
                results = self._run_with_timeout(
                    lambda: self.asr_model.generate(
                        input=audio_data.flatten().astype(np.float32),
                        cache={},
                        language="auto", # SenseVoice handles LID well
                        use_itn=True,
                        batch_size_s=60,
                        merge_vad=True,
                        merge_length_s=15,
                    ),
                    timeout_s=120,
                    label="ASR generate",
                )
                
                # funasr output is a list of dicts: [{'text': '...', 'key': '...'}]
                if results and len(results) > 0:
                    raw_text = results[0].get('text', '')
                    # Clean up emotion/event tags like <|HAPPY|>, <|ENTHUSIASTIC|>, etc.
                    raw_text = re.sub(r'<\|.*?\|>', '', raw_text).strip()
                
                log_transcription(f" SenseVoice Result - Raw: '{raw_text}'")
                


            elif ASR_BACKEND == "qwen_asr":
                # Pre-transcription check: ensure model is on CUDA (if available) before proceeding
                if cuda_is_available() and getattr(self.asr_model.model, "device", type("D", (), {"type": "cpu"})).type != "cuda":
                    # Fast RAM -> VRAM transfer
                    self.asr_model.model.to("cuda")

                # Slicing logic strictly derived from ONNX build to prevent OOM
                CHUNK_SIZE = 30 * 16000 # 30 seconds at 16kHz
                audio_np = audio_data.astype(np.float32)
                chunks = [audio_np[i:i + CHUNK_SIZE] for i in range(0, len(audio_np), CHUNK_SIZE)]
                
                seg_texts = []
                for idx, chunk in enumerate(chunks):
                    if len(chunks) > 1: log_transcription(f"  Transcribing chunk {idx+1}/{len(chunks)}...")
                    results = self._run_with_timeout(
                        lambda c=chunk: self.asr_model.transcribe(
                            audio=(c, 16000),
                            language=None, # Auto-detect
                            return_time_stamps=False # DISABLE forced alignment
                        ),
                        timeout_s=120,
                        label=f"ASR transcribe chunk {idx+1}",
                    )
                    if results and len(results) > 0:
                        txt = results[0].get('text', '') if isinstance(results[0], dict) else getattr(results[0], 'text', str(results[0]))
                        if txt: seg_texts.append(txt)
                
                raw_text = " ".join(seg_texts).strip()
                log_transcription(f" Qwen3-ASR Result: '{raw_text}'")
                
            else:
                # Faster-Whisper: `multilingual=True` runs language ID per segment so code-switched
                # speech (e.g. EN phrases in a ZH-dominant clip) is less often forced into one script.
                # Disable with PRIVOX_WHISPER_PER_SEGMENT_LANGUAGE=0 if you see unstable LID.
                _seg_lid = (os.environ.get("PRIVOX_WHISPER_PER_SEGMENT_LANGUAGE") or "").strip().lower()
                _use_per_segment_lang = _seg_lid not in ("0", "false", "no", "off")
                _asr_kw: dict = dict(
                    audio=audio_data.astype(np.float32),
                    task="transcribe",
                    beam_size=5,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500),
                )
                # Library may pin decoding language (e.g. yue for Cantonese CT2). Do not combine with
                # per-segment LID — faster-whisper would override the pinned language each segment.
                if WHISPER_TRANSCRIBE_LANGUAGE:
                    _asr_kw["language"] = WHISPER_TRANSCRIBE_LANGUAGE
                elif _use_per_segment_lang:
                    _asr_kw["multilingual"] = True
                    _asr_kw["initial_prompt"] = (
                        "Transcript may mix English and Chinese; keep each language in its usual spelling."
                    )
                segments, info = self._run_with_timeout(
                    lambda kw=_asr_kw: self.asr_model.transcribe(**kw),
                    timeout_s=120,
                    label="ASR transcribe",
                )
                
                log_transcription(f" ASR Result - Language Detected: {info.language} ({info.language_probability:.2f})")
                
                # Collect segments and log each one
                seg_results = []
                for segment in segments:
                    log_transcription(f"  Segment: [{segment.start:.2f}s -> {segment.end:.2f}s] ({len(segment.text)} chars)")
                    seg_results.append(segment.text)
                
                raw_text = " ".join(seg_results).strip()
            
            t1 = time.time()
            log_transcription(f" [ASR Total Time: {t1 - t0:.3f}s] Result: {len(raw_text)} chars")
            # Always log full ASR (preview) via log_print — refiner detail may be off in packaged builds.
            _asr_pv = raw_text[:400].replace("\n", " ").strip()
            if len(raw_text) > 400:
                _asr_pv += "..."
            log_print(f"ASR text ({len(raw_text)} chars, preview): {_asr_pv!r}")
            
            if not raw_text:
                log_transcription(" [Empty Transcription Result]")
                self.update_status("READY")
                return

            # --- Logic for Command Mode (DISABLED FOR NOW) ---
            is_command = False
            command_text = raw_text
            
            # if raw_text.lower().startswith("privox"):
            #     is_command = True
            #     command_text = re.sub(r'^(privox)\s*,?\s*', '', raw_text, flags=re.IGNORECASE)
            #     log_print(f" [Command Mode Detected] Input: {command_text}")
            


            import gc
            gc.collect()
            time.sleep(0.5) 
            
            # Since we aggressively skip loading the grammar model during init for ONNX,
            # we must explicitly trigger it here now that the ASR is purged from VRAM.
            if getattr(self, "current_refiner", ""):
                self.grammar_checker.load_model()
            
            log_transcription(f" Refining format ({self.current_refiner})...")
            t2 = time.time()
            detected_lang = info.language if (info and ASR_BACKEND == 'whisper') else None
            detected_prob = info.language_probability if (info and ASR_BACKEND == 'whisper') else 0.0
            final_text = self._run_with_timeout(
                lambda: self.grammar_checker.correct(
                    command_text,
                    is_command=is_command,
                    language=detected_lang,
                    language_prob=detected_prob,
                ),
                timeout_s=90,
                label="Refiner processing",
            )
            t3 = time.time()
            log_transcription(f" [Grammar Time: {t3 - t2:.3f}s]")
            
            log_transcription(f" [Refined Output: {len(final_text)} chars]")
            log_transcription(f" [Total Time: {t3 - t0:.3f}s]")
            ft_str = str(final_text) if final_text is not None else ""
            _ref_pv = ft_str[:400].replace("\n", " ").strip()
            if len(ft_str) > 400:
                _ref_pv += "..."
            log_print(f"Refiner output ({len(ft_str)} chars, preview): {_ref_pv!r}")
            _asr_n = " ".join(raw_text.split())
            _ref_n = " ".join(ft_str.split())
            if _asr_n == _ref_n:
                log_print(
                    "Refiner: same as ASR after whitespace normalize — model applied little/no surface edit "
                    "(expected for clean English; rules ask not to invent content)."
                )
            else:
                log_print(
                    f"Refiner: text differs from ASR (ASR {len(raw_text)} chars → refined {len(ft_str)} chars)."
                )
            
            if final_text is None or not str(final_text).strip():
                log_transcription(" [Skip paste: empty refined output]")
            else:
                ft = str(final_text)
                cap = 500
                log_transcription(
                    f" [Pasted text preview] ({len(ft)} chars): "
                    f"'{ft[:cap]}{'...' if len(ft) > cap else ''}'"
                )
                try:
                    self.paste_text(final_text)
                except Exception as e:
                    log_print(f"Typing Error: {e}")
                    self.sound_manager.play_error()
                

                
        except Exception as e:
            log_print(f"ASR Error: {e}")
            self.loading_status = "ASR Error"
            self.sound_manager.play_error()
        finally:
            if task_id is None or task_id == getattr(self, "_transcribe_task_id", 0):
                # Always leave PROCESSING: on error show ERROR tray state (was: stuck spinner forever).
                if self.loading_status in ["ASR Error", "Refiner Error"]:
                    self.update_status("ERROR")
                elif self.ui_state != "RECORDING":
                    self.update_status("READY")
                self.update_tray_tooltip()

    def paste_text(self, text):
        """Paste via clipboard + Ctrl+V. Serialized and clipboard-verified: avoids pasting stale clipboard on Windows."""
        if text is None:
            return
        text = str(text)
        if not text.strip():
            return

        def _norm_clip(s):
            if s is None:
                return ""
            return s.replace("\r\n", "\n").replace("\r", "\n")

        target = _norm_clip(text)

        with self._paste_clipboard_lock:
            try:
                original_clipboard = pyperclip.paste()
            except Exception:
                original_clipboard = ""

            try:
                pyperclip.copy(text)
                ok = False
                deadline = time.time() + 0.6
                while time.time() < deadline:
                    try:
                        if _norm_clip(pyperclip.paste()) == target:
                            ok = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.025)

                if not ok:
                    log_print(
                        "Paste: clipboard did not update in time; skipping Ctrl+V to avoid injecting stale clipboard."
                    )
                    try:
                        pyperclip.copy(original_clipboard)
                    except Exception:
                        pass
                    return

                delay = 0.09 if sys.platform == "win32" else 0.05
                time.sleep(delay)
                with self.keyboard_controller.pressed(keyboard.Key.ctrl):
                    self.keyboard_controller.press("v")
                    self.keyboard_controller.release("v")
                time.sleep(0.2)
                try:
                    pyperclip.copy(original_clipboard)
                except Exception:
                    pass
            except Exception as e:
                log_print(f"Paste Error: {e}")
                try:
                    pyperclip.copy(original_clipboard)
                except Exception:
                    pass
                if len(text) <= 800:
                    self.keyboard_controller.type(text)
                else:
                    log_print("Paste fallback: text too long for type(); not pasting.")

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

            # Keyboard Listener Watchdog
            # Windows hooks can be dropped by the OS after long idle or power state changes.
            if self.running:
                now_watchdog = time.monotonic()
                if now_watchdog - self._last_listener_watchdog_time >= 5.0: # Check every 5 seconds
                    self._last_listener_watchdog_time = now_watchdog
                    if self.keyboard_listener is not None and not self.keyboard_listener.is_alive():
                        log_print(" [Watchdog] Keyboard Listener died. Restarting...")
                        try:
                            self.keyboard_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
                            self.keyboard_listener.start()
                        except Exception as e:
                            log_print(f" [Watchdog] Failed to restart Keyboard Listener: {e}")

            # Config Polling (Hot-reload) — skip while heavy ASR/LLM load runs to avoid extra disk/CPU during init.
            # When not listening, the mic callback still enqueues chunks every block; without throttling we would
            # stat/read/hash prefs at audio rate (~50–100+/s), which spikes CPU (worse now that load_config is heavier).
            try:
                if not getattr(self, "_heavy_model_load_in_progress", False):
                    poll_interval = 0.35 if self.is_listening else 0.75
                    now_mono = time.monotonic()
                    if now_mono - self._last_prefs_poll_mono >= poll_interval:
                        self._last_prefs_poll_mono = now_mono
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

                if self.is_listening and len(chunk) > 0:
                    rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
                    if rms >= INITIAL_SPEECH_ENERGY_RMS:
                        self._heard_voice_energy = True
                        self._last_loud_chunk_time = time.time()
                
                # Check VAD for Manual Toggle Feedback & Auto-Stop
                # CRITICAL: Suspend Auto-Stop logic while AI models are still loading (Wake up phase)
                if self.vad_iterator and not self._heavy_model_load_in_progress:
                    if NO_TORCH:
                        speech_dict = self.vad_iterator(chunk.astype(np.float32), return_seconds=True)
                    else:
                        chunk_tensor = torch.from_numpy(chunk).float()
                        speech_dict = self.vad_iterator(chunk_tensor, return_seconds=True)
                    
                    if speech_dict:
                        if 'start' in speech_dict and not self.is_speaking:
                             self.is_speaking = True
                        if 'end' in speech_dict and self.is_listening and self.auto_stop_enabled:
                             log_print(" [Auto-Stop Detected: Silence after speech]")
                             self.stop_listening()
                    
                    # No VAD "speech start" yet: stop only if the mic never crossed the energy floor (truly idle).
                    if self.is_listening and not self.is_speaking and self.auto_stop_enabled:
                        if not self._heard_voice_energy:
                            if (time.time() - self.last_activity_time) > (self.silence_timeout_ms / 1000):
                                log_print(
                                    " [Auto-Stop Detected: Initial silence timeout "
                                    "(no speech detected by VAD/mic energy; raise gain or disable Auto-Stop)]"
                                )
                                self.stop_listening()
                        elif (time.time() - self._last_loud_chunk_time) > (self.silence_timeout_ms / 1000):
                            log_print(" [Auto-Stop Detected: Silence after audio (mic energy)]")
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
        # VAD must be ready before any wake / toggle logic — otherwise an ignored first keypress
        # must not schedule pending_wakeup (auto-start after load), which felt like a phantom session.
        if not self.vad_model:
            log_print("Ignored Hotkey: VAD Model not fully loaded.")
            self.sound_manager.play_error()
            return

        # Wake up detection - Trigger background load if needed, but don't block!
        if not self.heavy_models_loaded:
            # Dev: initial_load already runs load_heavy_models() on a daemon thread — do not start another
            # thread that only blocks on model_lock during ONNX snapshot_download.
            if self.mic_active:
                # User can actually record once load completes — allow auto-start after load.
                if getattr(self, "_heavy_model_load_in_progress", False):
                    if not self.pending_wakeup:
                        log_print(
                            "Model load already in progress (first-run Qwen ONNX download can take 15–60+ minutes). "
                            "Tray will show Ready when done; transcription waits until then."
                        )
                    self.pending_wakeup = True
                    self._wakeup_autostart_cancelled = False
                elif not self.pending_wakeup:
                    log_print("Wake up detected. Pre-loading models in background...")
                    self.pending_wakeup = True
                    self._wakeup_autostart_cancelled = False
                    threading.Thread(target=self.load_heavy_models, daemon=True).start()
            else:
                # Mic not up yet (or stream failed): still kick off model load so install/wake can finish,
                # but never auto-start recording when load completes from this path.
                if not getattr(self, "_heavy_model_load_in_progress", False):
                    log_print(
                        "Wake up: pre-loading models in background (microphone not active yet — "
                        "no auto-start after load; press hotkey again when ready)."
                    )
                    threading.Thread(target=self.load_heavy_models, daemon=True).start()

        # Guard: mic required to start/stop a recording session.
        # Transcription/Refinement will wait for asr_model/llm_model inside transcribe().
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
        if "--benchmark-ct2-asr" in sys.argv:
            if getattr(sys, "frozen", False):
                logging.error(
                    "CT2 ASR benchmark is not available inside the packaged exe "
                    "(faster-whisper is loaded via Pixi at runtime). "
                    "Run: pixi run python src/voice_input.py --benchmark-ct2-asr [options]"
                )
                sys.exit(1)
            _i = sys.argv.index("--benchmark-ct2-asr")
            _bench_argv = sys.argv[_i + 1 :]
            import benchmark_ct2_asr as _bench_ct2

            sys.exit(_bench_ct2.main(argv=_bench_argv, base_dir=BASE_DIR))

        # 3. Early GPU Check (torch.cuda when PyTorch present; else CT2/llama heuristic)
        gpu_detected = cuda_is_available()

        logging.info("--- VoiceInputApp Startup ---")
        logging.info(f"Python Executable: {sys.executable}")
        logging.info(f"sys.path: {sys.path}")
        logging.info(f"GPU Support Detected: {gpu_detected}")
        if gpu_detected:
            logging.info(f"Using GPU: {cuda_device_name(0)}")
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
            _hint = (
                "This build does not write privox_app.log."
                if getattr(sys, "frozen", False)
                else "Check privox_app.log in the install folder for details."
            )
            ctypes.windll.user32.MessageBoxW(
                0,
                f"Privox failed to start:\n\n{e}\n\n{_hint}",
                "Privox Fatal Error",
                0x10,
            )
        sys.exit(1)
