import sys
import os

# --- 0. Hard Environment Isolation (MUST BE FIRST) ---
# This prevents picking up broken PySide6 versions from user site-packages
os.environ["PYTHONNOUSERSITE"] = "1"
import site
site.ENABLE_USER_SITE = False

if sys.platform == 'win32':
    # Inject pixi environment DLL paths explicitly to resolve procedure conflicts
    env_path = os.path.join(os.getcwd(), ".pixi", "envs", "default")
    dll_path = os.path.join(env_path, "Library", "bin")
    if os.path.exists(dll_path):
        os.add_dll_directory(dll_path)
    # Also try bin in prefix
    bin_path = os.path.join(env_path, "bin")
    if os.path.exists(bin_path):
        os.add_dll_directory(bin_path)

import copy
import json
import models_config
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QLineEdit,
    QScrollArea, QGraphicsDropShadowEffect, QSizePolicy, QPlainTextEdit,
    QDialog, QComboBox, QCheckBox, QProgressBar, QSpinBox,
)
import ctypes
import subprocess
import tempfile
import sounddevice as sd


def _win_vbs_escape_path(p: str) -> str:
    return os.path.normpath(p).replace("\\", "\\\\")


def _win_create_shortcut(lnk_path: str, target_exe: str, arguments_vbs_fragment: str, work_dir: str, icon_path: str) -> None:
    """Write a .lnk via cscript + VBScript (matches bootstrap installer). arguments_vbs_fragment sets oLink.Arguments."""
    lf, tp, wd, ic = map(_win_vbs_escape_path, (lnk_path, target_exe, work_dir, icon_path))
    vbs_script = (
        'Set oWS = WScript.CreateObject("WScript.Shell")\n'
        f'sLinkFile = "{lf}"\n'
        "Set oLink = oWS.CreateShortcut(sLinkFile)\n"
        f'oLink.TargetPath = "{tp}"\n'
        f"{arguments_vbs_fragment}"
        f'oLink.WorkingDirectory = "{wd}"\n'
        f'oLink.IconLocation = "{ic},0"\n'
        "oLink.WindowStyle = 7\n"
        "oLink.Save\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".vbs", delete=False, encoding="utf-8") as tmp:
        tmp.write(vbs_script)
        vbs_file = tmp.name
    try:
        subprocess.run(
            ["cscript", "//nologo", vbs_file],
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=30,
        )
    finally:
        try:
            os.remove(vbs_file)
        except Exception:
            pass


# --- DWM Helpers for Glassmorphism ---
def apply_mica_or_acrylic(window, acrylic=True):
    if sys.platform != 'win32': return
    try:
        hwnd = window.effectiveWinId().value()
        # DWMWA_SYSTEMBACKDROP_TYPE: 1=None, 2=Mica, 3=Acrylic (Tabbed), 4=MicaAlt
        # REMOVED ACRYLIC TO FIX ROUNDED CORNER ARTIFACTS
        # backdrop_type = ctypes.c_int(3 if acrylic else 2)
        # ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop_type), 4)
        
        # Dark Mode Force (Keep this for consistency, though usually for titled windows)
        dark = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
        
        # Caption color to black/transparent
        black = ctypes.c_int(0x00000000)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(black), 4)
    except: pass

# Windows Registry for Startup
if sys.platform == 'win32':
    import winreg

# SVG Icons for the dropdown arrow
import re

# --- Model Update Worker & Signals ---
class ModelUpdateSignals(QObject):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(bool, str)

class StderrInterceptor:
    def __init__(self, orig, signal_callback):
        self.orig = orig
        self.callback = signal_callback
        self.buffer = ""
        self.pct_re = re.compile(r"(\d+(?:\.\d+)?)%")
        
    def write(self, s):
        if self.orig:
            try:
                self.orig.write(s)
            except: pass
        self.buffer += s
        if '\r' in self.buffer or '\n' in self.buffer:
            matches = self.pct_re.findall(self.buffer)
            if matches:
                self.callback(int(matches[-1]))
            self.buffer = ""
            
    def flush(self):
        if self.orig and hasattr(self.orig, 'flush'):
            try:
                self.orig.flush()
            except: pass

class ModelUpdateWorker(QObject):
    def __init__(self, signals):
        super().__init__()
        self.signals = signals

    @Slot()
    def run(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        import download_models

        def ui_log(msg):
            self.signals.status.emit(msg)
            # print to original stderr for debugging
            try:
                sys.__stderr__.write(f"[UI LOG] {msg}\n")
            except: pass

        # Initial heartbeat
        print("[DEBUG] Worker thread started. Emitting heartbeat...", flush=True)
        ui_log("Starting model setup engine...")

        print("[DEBUG] Redirecting stderr...", flush=True)
        old_stderr = sys.stderr
        sys.stderr = StderrInterceptor(old_stderr, self.signals.progress.emit)
        
        try:
            print("[DEBUG] Calling download_models.main()...", flush=True)
            # Re-ensure path for download_models internal imports if any
            download_models.main(log_callback=ui_log)
            print("[DEBUG] download_models.main() finished successfully.", flush=True)
            self.signals.finished.emit(True, "")
        except Exception as e:
            self.signals.finished.emit(False, str(e))
        finally:
            sys.stderr = old_stderr


class OnnxAsrPrefetchSignals(QObject):
    finished = Signal(bool, str)
    log_line = Signal(str)


class OnnxAsrPrefetchWorker(QObject):
    """Background HF snapshot for ONNX ASR presets when user selects them in Settings."""

    def __init__(self, base_dir: str, whisper_model: str, whisper_repo: str, asr_backend: str, signals: OnnxAsrPrefetchSignals):
        super().__init__()
        self.base_dir = base_dir
        self.whisper_model = whisper_model
        self.whisper_repo = whisper_repo
        self.asr_backend = asr_backend
        self.signals = signals

    @Slot()
    def run(self):
        import download_models

        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        def _log(m: str) -> None:
            try:
                print(f"[ONNX prefetch] {m}", flush=True)
            except Exception:
                pass
            self.signals.log_line.emit(m)

        try:
            download_models.ensure_asr_snapshot(
                self.base_dir,
                self.whisper_model,
                self.whisper_repo,
                self.asr_backend,
                log_local=_log,
            )
            self.signals.finished.emit(True, "")
        except Exception as e:
            self.signals.finished.emit(False, str(e))


ARROW_DOWN_SVG = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path fill='%23aaaaaa' d='M2 4l4 4 4-4z'/></svg>"
ARROW_UP_SVG = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path fill='%23ffffff' d='M2 8l4-4 4 4z'/></svg>"

class ModernComboBox(QComboBox):
    """Custom ComboBox to handle the expand/collapse arrow state and full-width styling."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        # We use QSS to handle the arrow state via :on and :off pseudo-states
        # Swiss Style Typography & Glass UI
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 1px 18px 1px 15px;
                color: #ffffff;
                font-size: 13px;
                font-weight: 500;
            }}
            QComboBox:hover {{
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border-left-width: 0px;
            }}
            QComboBox::down-arrow {{
                image: url("{ARROW_DOWN_SVG}");
                width: 12px;
                height: 12px;
            }}
            QComboBox::down-arrow:on {{
                image: url("{ARROW_UP_SVG}");
            }}
            QComboBox QAbstractItemView {{
                background-color: #1a1a1a;
                border: 1px solid rgba(255, 255, 255, 0.1);
                selection-background-color: rgba(255, 255, 255, 0.1);
                color: #ffffff;
                outline: none;
                padding: 10px;
                border-radius: 8px;
            }}
        """)

class NavigablePlainTextEdit(QPlainTextEdit):
    """QPlainTextEdit that allows Tab/Shift+Tab navigation to move focus."""
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Tab:
            self.focusNextChild()
            event.accept()
        elif event.key() == Qt.Key_Backtab: # Shift + Tab
            self.focusPreviousChild()
            event.accept()
        else:
            super().keyPressEvent(event)


class ModernDialog(QDialog):
    """Refined generic dialog for alerts and confirmations with a premium feel."""
    def __init__(self, parent=None, title="PRIVOX", message="", subtext="", buttons=["OK"], detail_lines=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 18, 18, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 16px;
            }
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(32, 28, 32, 28)
        container_layout.setSpacing(18)
        
        # Title Bar
        title_bar = QHBoxLayout()
        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet("font-weight: 900; color: rgba(255, 255, 255, 0.4); font-size: 10px; letter-spacing: 2px; border: none;")
        title_bar.addWidget(title_lbl)
        title_bar.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("QPushButton { border: none; color: #666666; font-size: 16px; background: transparent; } QPushButton:hover { color: #ffffff; }")
        close_btn.clicked.connect(self.reject)
        title_bar.addWidget(close_btn)
        container_layout.addLayout(title_bar)
        
        # Content
        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: 500; border: none;")
        msg_lbl.setWordWrap(True)
        container_layout.addWidget(msg_lbl)
        
        if subtext:
            sub_lbl = QLabel(subtext)
            sub_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 13px; border: none;")
            sub_lbl.setWordWrap(True)
            container_layout.addWidget(sub_lbl)

        if detail_lines:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setStyleSheet("""
                QScrollArea { background: transparent; border: none; }
                QScrollBar:vertical {
                    border: none; background: transparent; width: 8px; margin: 0;
                }
                QScrollBar::handle:vertical {
                    background: rgba(255, 255, 255, 0.12);
                    min-height: 24px;
                    border-radius: 4px;
                }
            """)
            inner = QWidget()
            inner.setStyleSheet("background: transparent;")
            inner_l = QVBoxLayout(inner)
            inner_l.setContentsMargins(4, 4, 12, 4)
            inner_l.setSpacing(8)
            for line in detail_lines:
                row = QLabel(f"•\u00a0{line}")
                row.setWordWrap(True)
                row.setStyleSheet(
                    "color: rgba(255, 255, 255, 0.78); font-size: 13px; border: none; line-height: 140%;"
                )
                inner_l.addWidget(row)
            inner_l.addStretch()
            scroll.setWidget(inner)
            h = min(220, max(96, 28 * len(detail_lines) + 36))
            scroll.setFixedHeight(h)
            container_layout.addWidget(scroll)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()
        
        for btn_text in buttons:
            btn = QPushButton(btn_text)
            btn.setMinimumHeight(42)
            btn.setMinimumWidth(100)
            btn.setCursor(Qt.PointingHandCursor)
            
            # Highlight primary button (last or "Save"/"OK")
            is_primary = btn_text in ["Save", "OK", "INSTALL", "Launch"] or (btn_text == buttons[-1] and len(buttons) > 1)
            
            if is_primary:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        color: #000000;
                        border-radius: 8px;
                        font-weight: 800;
                        padding: 0 24px;
                        font-size: 13px;
                    }
                    QPushButton:hover {
                        background-color: rgba(255, 255, 255, 0.85);
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(255, 255, 255, 0.05);
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        color: #ffffff;
                        border-radius: 8px;
                        font-weight: 600;
                        padding: 0 20px;
                        font-size: 13px;
                    }
                    QPushButton:hover {
                        background-color: rgba(255, 255, 255, 0.1);
                        border: 1px solid rgba(255, 255, 255, 0.2);
                    }
                """)
            
            # Map results
            if btn_text == "Save" or btn_text == "OK":
                btn.clicked.connect(lambda: self.done(1))
            elif btn_text == "Discard":
                btn.clicked.connect(lambda: self.done(2))
            elif btn_text == "Cancel":
                btn.clicked.connect(self.reject)
            else:
                # Direct result based on button order if not matched
                btn.clicked.connect(lambda checked=False, b=btn_text: self.done(buttons.index(b) + 1))
            
            btn_layout.addWidget(btn)
        
        container_layout.addLayout(btn_layout)
        layout.addWidget(self.container)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, 'drag_pos'):
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

class ModernProgressDialog(QDialog):
    """Premium Centered Progress Update with Liquid Glass styling."""
    def __init__(self, parent=None, title="UPDATING MODELS"):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(480, 260)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 18, 18, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
            }
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(40, 32, 40, 32)
        container_layout.setSpacing(0)
        
        container_layout.addStretch()

        # Title Bar (Small, centered)
        title_lbl = QLabel(title.upper())
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("font-weight: 900; color: rgba(255, 255, 255, 0.3); font-size: 10px; letter-spacing: 3px; border: none;")
        container_layout.addWidget(title_lbl)
        
        container_layout.addSpacing(30)
        
        # Center Stack (Progress + Status)
        center_layout = QVBoxLayout()
        center_layout.setSpacing(15)
        center_layout.setAlignment(Qt.AlignCenter)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumWidth(300)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #ffffff;
                border-radius: 4px;
            }
        """)
        center_layout.addWidget(self.progress_bar)
        self.main_status = QLabel("Downloading models...")
        self.main_status.setAlignment(Qt.AlignCenter)
        self.main_status.setStyleSheet("color: white; font-size: 18px; font-weight: 700; border: none;")
        center_layout.addWidget(self.main_status)
        
        self.sub_status = QLabel("Preparing environment...")
        self.sub_status.setAlignment(Qt.AlignCenter)
        self.sub_status.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 13px; font-style: italic; border: none;")
        center_layout.addWidget(self.sub_status)
        
        # --- Restart Button (Initially Hidden) ---
        self.restart_btn = QPushButton("RESTART NOW")
        self.restart_btn.setFixedSize(160, 42)
        self.restart_btn.setCursor(Qt.PointingHandCursor)
        self.restart_btn.setVisible(False)
        self.restart_btn.setStyleSheet("""
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
        self.restart_btn.clicked.connect(self.accept)
        center_layout.addWidget(self.restart_btn, alignment=Qt.AlignCenter)
        
        container_layout.addLayout(center_layout)
        container_layout.addStretch()
        
        layout.addWidget(self.container)

    def set_status(self, main_text, sub_text=None):
        self.main_status.setText(main_text)
        if sub_text:
            self.sub_status.setText(sub_text)

    def set_progress(self, value):
        if value <= 0:
            # Indeterminate mode if no progress reported yet
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(value))

    def show_completion(self, main_text="AI Setup Complete", sub_text="Restoring application background engine..."):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #00ff88;
                border-radius: 4px;
            }
        """)
        self.main_status.setText(main_text)
        self.main_status.setStyleSheet("color: #00ff88; font-size: 20px; font-weight: 800; border: none;")
        self.sub_status.setText(sub_text)
        self.sub_status.setStyleSheet("color: white; font-size: 14px; font-weight: 500; border: none;")
        self.restart_btn.setVisible(True)
        self.restart_btn.setFocus()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, 'drag_pos'):
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

class SettingsGUI(QMainWindow):
    def __init__(self, config_path="config.json"):
        super().__init__()
        # Set a clear default font to avoid setPointSize(-1) warnings
        self.setFont(QFont("Inter", 10))
        self.config_path = config_path
        self.is_dirty = False
        self._saved_settings_snapshot = None
        self._onnx_prefetch_thread = None
        self._status_transient_text = None
        self._onnx_prefetch_detail = ""
        self._status_clear_timer = QTimer(self)
        self._status_clear_timer.setSingleShot(True)
        self._status_clear_timer.timeout.connect(self._clear_transient_status)

        self.load_config()
        self.init_ui()
        self.load_initial_state()
        
        # Set Window Icon
        try:
            icon_path = self.get_resource_path("assets/icon.ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                # Set App ID for Windows Taskbar Grouping
                if sys.platform == 'win32':
                    myappid = u'markyip.privox.settings.1.2'
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except: pass

    def get_resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, relative_path)
        
    def load_config(self):
        # Robust config path resolution
        if not os.path.exists(self.config_path):
            # Try finding it relative to this script (Project Root)
            script_dir = os.path.dirname(os.path.abspath(__file__)) # src/
            project_root = os.path.dirname(script_dir) # Project/
            candidate = os.path.join(project_root, "config.json")
            if os.path.exists(candidate):
                self.config_path = candidate
        
        self.config_path = os.path.abspath(self.config_path)
        base_dir = os.path.dirname(self.config_path)
        self.base_dir = base_dir
        self.prefs_path = os.path.join(base_dir, ".user_prefs.json")
        
        # Load Tech Config
        self.tech_config = {}
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.tech_config = json.load(f)

        _gem = models_config.LLM_LIBRARY[0]
        if self.tech_config.get("grammar_file") == "Qwen3.5-4B-Q4_K_M.gguf" or self.tech_config.get(
            "grammar_repo"
        ) == "unsloth/Qwen3.5-4B-GGUF":
            self.tech_config["grammar_repo"] = _gem["repo_id"]
            self.tech_config["grammar_file"] = _gem["file_name"]
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.tech_config, f, indent=4)

        # Load User Prefs
        self.prefs = {}
        if os.path.exists(self.prefs_path):
            with open(self.prefs_path, "r", encoding="utf-8") as f:
                self.prefs = json.load(f)
            if self.prefs and models_config.scrub_obsolete_user_pref_keys(self.prefs):
                with open(self.prefs_path, "w", encoding="utf-8") as f:
                    json.dump(self.prefs, f, indent=4)

        # Unified state
        self.config = {**self.tech_config, **self.prefs}
        
        # Dictionary migration/initialization
        if "custom_dictionary" not in self.prefs:
            self.prefs["custom_dictionary"] = self.tech_config.get("custom_dictionary", [])
            
        # Library Loading (Always use fresh config/code over user prefs to prevent stale URLs)
        self.asr_library = self.tech_config.get("asr_library", models_config.ASR_LIBRARY)
        
        self.llm_library = self.tech_config.get("llm_library", models_config.LLM_LIBRARY)
        if isinstance(self.llm_library, list):
            _drop = {"Multilingual (Qwen 3.5 4B)"}
            self.llm_library = [m for m in self.llm_library if m.get("name") not in _drop]
            if not self.llm_library:
                self.llm_library = list(models_config.LLM_LIBRARY)

        self.custom_prompts = self.prefs.get("custom_prompts", self.tech_config.get("custom_prompts", models_config.DEFAULT_PROMPTS))
        
        char = self.prefs.get("character", self.tech_config.get("character", "Writing Assistant"))
        tone = self.prefs.get("tone", self.tech_config.get("tone", "Natural"))
        self.last_prompt_key = f"{char}|{tone}"
        
        # --- Migration: Clean Hints {dict} from saved prompts ---
        # Backend now handles dictionary injection automatically.
        for key, prompt in self.custom_prompts.items():
            if "Hints: {dict}" in prompt:
                # Remove the hint line and trailing newlines
                clean_prompt = prompt.replace("Hints: {dict}", "").replace("\n\n\n", "\n\n").strip()
                self.custom_prompts[key] = clean_prompt
                self.prefs["custom_prompts"] = self.custom_prompts

        # --- Migration: Unified Descriptive Naming ---
        if self.prefs.get("whisper_model") == "distil-large-v3":
            self.prefs["whisper_model"] = "Distil-Whisper Large v3 (English)"
        if self.prefs.get("current_refiner") == "Standard (Llama 3.2)":
            self.prefs["current_refiner"] = models_config.DEFAULT_LLM
        # If any of the above were found in tech_config but not yet in prefs, this ensures sync
        if self.tech_config.get("whisper_model") == "distil-large-v3":
            self.tech_config["whisper_model"] = "Distil-Whisper Large v3 (English)"
        if self.tech_config.get("current_refiner") == "Standard (Llama 3.2)":
            self.tech_config["current_refiner"] = models_config.DEFAULT_LLM

        # --- Migration: removed ASR options (library + old id stored in tech_config) ---
        removed_asr_labels = frozenset({"Qwen2-Audio-7B", "qwen2-audio-7b"})
        if self.prefs.get("whisper_model") in removed_asr_labels:
            self.prefs["whisper_model"] = models_config.DEFAULT_ASR
        if self.tech_config.get("whisper_model") in removed_asr_labels:
            self.tech_config["whisper_model"] = models_config.DEFAULT_ASR_WHISPER_MODEL
            
        # --- Migration: redirect removed refiner names to current default ---
        removed_refiners = {
            "CoEdit Large (T5)",
            "Llama 3.2 3B Instruct",
            "Multilingual (Qwen 3.5 9B)",
            "Multilingual (Qwen 2.5 7B)",
            "Multilingual (Qwen 3.5 4B)",
        }
        if self.prefs.get("current_refiner") in removed_refiners:
            self.prefs["current_refiner"] = models_config.DEFAULT_LLM
        if self.tech_config.get("current_refiner") in removed_refiners:
            self.tech_config["current_refiner"] = models_config.DEFAULT_LLM

        self.config = {**self.tech_config, **self.prefs}

    def _resolve_asr_display_name(self, value):
        """config.json may use whisper_model id; ASR combo uses ASR_LIBRARY display names."""
        if not value:
            return models_config.DEFAULT_ASR
        for m in self.asr_library:
            if m["name"] == value or m.get("whisper_model") == value:
                return m["name"]
        return models_config.DEFAULT_ASR

    CRITICAL_RULES = models_config.CRITICAL_RULES
    DEFAULT_PROMPTS = models_config.DEFAULT_PROMPTS

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, 'drag_pos'):
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def closeEvent(self, event):
        if self.is_dirty:
            detail = self._unsaved_change_descriptions()
            dialog = ModernDialog(
                self,
                "EXIT SETTINGS",
                "Save changes before exiting?",
                "You have unsaved edits in the following areas. What would you like to do?",
                buttons=["Cancel", "Discard", "Save"],
                detail_lines=detail,
            )
            result = dialog.exec()
            if result == 3: # Save (based on button index + 1, Save is last)
                self.save_config()
                event.accept()
            elif result == 2: # Discard
                event.accept()
            else: # Cancel
                event.ignore()
        else:
            event.accept()

    def init_ui(self):
        self.setWindowTitle("Privox_Settings_GUI")
        self.resize(1000, 750)
        self.setMinimumSize(900, 700)
        
        # Frameless Modern Window
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Dark Palette
        # SWISS STYLE + GLASSMORPHISM THEME
        self.setStyleSheet("""
            QMainWindow {
                background: transparent;
            }
            QWidget {
                color: #ffffff;
                font-family: 'Inter', 'Segoe UI Variable Text', 'Segoe UI', Arial;
            }
            QLabel {
                font-size: 13px;
                color: #e0e0e0;
            }
            QLabel#header_text {
                font-size: 28px;
                font-weight: 800;
                letter-spacing: -0.5px;
                margin-bottom: 20px;
                color: #ffffff;
            }
            QPushButton#sidebar_btn {
                background-color: transparent;
                border: 1px solid transparent; /* Prevents native 'ghost' edges */
                color: #888888;
                text-align: left;
                padding-left: 24px;
                font-size: 14px;
                font-weight: 500;
                height: 50px;
                outline: none;
                border-radius: 8px;
            }
            QPushButton#sidebar_btn:hover {
                background-color: rgba(255, 255, 255, 0.03);
            }
            QPushButton#sidebar_btn[active="true"] {
                color: #ffffff;
                background-color: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.1);
                font-weight: 700;
            }
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 10px;
                color: #ffffff;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(255, 255, 255, 0.3);
                background-color: rgba(255, 255, 255, 0.08);
            }
            QPlainTextEdit {
                background-color: rgba(0, 0, 0, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 12px;
                color: #cccccc;
                font-size: 13px;
                line-height: 150%;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.1);
                min-height: 30px;
                border-radius: 4px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QCheckBox {
                spacing: 12px;
                font-weight: 500;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                background: rgba(255, 255, 255, 0.05);
            }
            QCheckBox::indicator:checked {
                background: #ffffff;
                border: 1px solid #ffffff;
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path fill='%23000000' d='M9.5 3L4.5 8 2.5 6'/></svg>");
            }
            QSpinBox {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 1px 5px 1px 12px;
                color: #ffffff;
                font-size: 13px;
                min-height: 38px;
            }
            QSpinBox:focus {
                border: 1px solid rgba(255, 255, 255, 0.3);
                background-color: rgba(255, 255, 255, 0.08);
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background: transparent;
                border: none;
                width: 24px;
            }
            QSpinBox::up-arrow {
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 12 12'><path fill='%23aaaaaa' d='M2 8l4-4 4 4z'/></svg>");
                width: 10px;
                height: 10px;
            }
            QSpinBox::down-arrow {
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 12 12'><path fill='%23aaaaaa' d='M2 4l4 4 4-4z'/></svg>");
                width: 10px;
                height: 10px;
            }
        """)

        central_widget = QWidget()
        central_widget.setObjectName("central_widget")
        self.setCentralWidget(central_widget)
        # Apply professional deep background with nearly solid opacity
        central_widget.setStyleSheet("QWidget#central_widget { background-color: rgba(18, 18, 18, 0.98); border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.1); }")
        
        main_v_layout = QVBoxLayout(central_widget)
        main_v_layout.setContentsMargins(0, 0, 0, 0)
        main_v_layout.setSpacing(0)

        # --- Custom Title Bar ---
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("background: transparent;")
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(20, 0, 10, 0)
        
        win_title = QLabel("PRIVOX SETTINGS")
        win_title.setStyleSheet("font-size: 10px; font-weight: 900; letter-spacing: 2px; color: rgba(255, 255, 255, 0.4);")
        title_bar_layout.addWidget(win_title)
        title_bar_layout.addStretch()
        
        btn_min = QPushButton("−")
        btn_min.setFixedSize(30, 30)
        btn_min.setStyleSheet("QPushButton { background: transparent; color: white; border: none; font-size: 20px; } QPushButton:hover { background: rgba(255, 255, 255, 0.1); }")
        btn_min.clicked.connect(self.showMinimized)
        title_bar_layout.addWidget(btn_min)

        btn_close = QPushButton("×")
        btn_close.setFixedSize(30, 30)
        btn_close.setStyleSheet("QPushButton { background: transparent; color: white; border: none; font-size: 20px; } QPushButton:hover { background: #e81123; color: white; }")
        btn_close.clicked.connect(self.close)
        title_bar_layout.addWidget(btn_close)
        
        main_v_layout.addWidget(title_bar)

        main_layout = QHBoxLayout()
        main_v_layout.addLayout(main_layout)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- Sidebar ---
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(240)
        self.sidebar.setStyleSheet("background-color: transparent; border-right: 1px solid rgba(255, 255, 255, 0.1);")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 40, 0, 10)
        sidebar_layout.setSpacing(2)

        self.btn_models = QPushButton("AI Models")
        self.btn_general = QPushButton("General")
        self.btn_dict = QPushButton("Dictionary")

        self.sidebar_buttons = [self.btn_models, self.btn_general, self.btn_dict]
        for btn in self.sidebar_buttons:
            btn.setObjectName("sidebar_btn")
            btn.setCursor(Qt.PointingHandCursor)
            # Add a small vertical indicator pill on the left
            indicator = QFrame(btn)
            indicator.setObjectName("indicator")
            indicator.setFixedSize(4, 24)
            indicator.setStyleSheet("QFrame#indicator { background-color: #ffffff; border-radius: 2px; }")
            indicator.move(10, 13) # Precise alignment
            indicator.setVisible(False)
            setattr(btn, "nav_indicator", indicator)
            sidebar_layout.addWidget(btn)
        
        self.btn_models.clicked.connect(lambda: self.switch_tab(0))
        self.btn_general.clicked.connect(lambda: self.switch_tab(1))
        self.btn_dict.clicked.connect(lambda: self.switch_tab(2))

        sidebar_layout.addStretch()

        self.btn_save_all = QPushButton("SAVE ALL SETTINGS")
        self.btn_save_all.setFixedSize(200, 44)
        self.btn_save_all.setCursor(Qt.PointingHandCursor)
        self.btn_save_all.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.5);
                border-radius: 8px;
                font-weight: 700;
                font-size: 11px;
                letter-spacing: 1.5px;
                margin-left: 20px;
                margin-bottom: 20px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.2);
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.12);
            }
        """)
        self.btn_save_all.clicked.connect(self.save_config)
        sidebar_layout.addWidget(self.btn_save_all)
        
        footer_label = QLabel("v1.2.3")
        footer_label.setStyleSheet("color: #444444; padding-left: 20px;")
        sidebar_layout.addWidget(footer_label)

        main_layout.addWidget(self.sidebar)

        # --- Content Area ---
        content_container = QWidget()
        content_container.setStyleSheet("background-color: transparent;")
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(40, 30, 40, 30) # Reduced from 48
        
        self.stack = QStackedWidget()
        
        # 1. Models Tab
        self.tab_models = QWidget()
        self.init_models_tab()
        self.stack.addWidget(self.tab_models)
        
        # 2. General Tab
        self.tab_general = QWidget()
        self.init_general_tab()
        self.stack.addWidget(self.tab_general)
        
        # 3. Dictionary Tab
        self.tab_dict = QWidget()
        self.init_dict_tab()
        self.stack.addWidget(self.tab_dict)

        content_layout.addWidget(self.stack)
        main_layout.addWidget(content_container)

        # --- Status bar (inside rounded panel, below sidebar + content) ---
        status_strip = QFrame()
        status_strip.setObjectName("status_strip")
        status_strip.setFixedHeight(30)
        status_strip.setStyleSheet("""
            QFrame#status_strip {
                background-color: rgba(0, 0, 0, 0.28);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                border-bottom-left-radius: 11px;
                border-bottom-right-radius: 11px;
            }
        """)
        status_layout = QHBoxLayout(status_strip)
        status_layout.setContentsMargins(14, 0, 14, 0)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            "color: rgba(255, 255, 255, 0.5); font-size: 11px; font-weight: 500;"
        )
        self._status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._status_label.setWordWrap(False)
        self._status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        status_layout.addWidget(self._status_label, 1)
        main_v_layout.addWidget(status_strip)

        self.switch_tab(0)
        self._refresh_status_bar()

    def _clear_transient_status(self):
        self._status_transient_text = None
        self._refresh_status_bar()

    def set_status_message(self, text: str, timeout_ms: int = 0) -> None:
        """Show a temporary status message; restores Ready / dirty / download state when timeout_ms elapses."""
        self._status_clear_timer.stop()
        self._status_transient_text = (text or "").strip() or None
        self._refresh_status_bar()
        if timeout_ms > 0 and self._status_transient_text:
            self._status_clear_timer.start(timeout_ms)

    def _refresh_status_bar(self) -> None:
        if not getattr(self, "_status_label", None):
            return
        if self._status_transient_text:
            self._status_label.setText(self._status_transient_text)
        elif self.is_dirty:
            self._status_label.setText(
                "Unsaved changes — use SAVE ALL SETTINGS or choose on exit"
            )
        else:
            self._status_label.setText("Ready")
        pp = getattr(self, "prefs_path", "") or ""
        cfg = getattr(self, "config_path", "") or ""
        if pp or cfg:
            self._status_label.setToolTip(f"Preferences: {pp}\nConfig: {cfg}")
        else:
            self._status_label.setToolTip("")



    def mark_dirty(self):
        self.is_dirty = True
        if not self._status_transient_text:
            self._refresh_status_bar()

    def _hotkey_display_label(self):
        tip = (self.hk_val.toolTip() or "").strip()
        if tip:
            return tip
        return (self.hk_val.text() or self.prefs.get("hotkey", "f8")).strip()

    def _capture_settings_snapshot(self):
        return {
            "character": self.char_combo.currentText(),
            "tone": self.tone_combo.currentText(),
            "asr": self.asr_combo.currentText(),
            "llm": self.llm_combo.currentText(),
            "sound_enabled": self.check_sound.isChecked(),
            "startup_enabled": self.check_startup.isChecked(),
            "use_simplified_chinese_output": self.check_simplified_chinese.isChecked(),
            "vram_timeout_s": self.vram_spin.value(),
            "auto_stop_s": self.stop_spin.value(),
            "hotkey_pref": (self.prefs.get("hotkey", "f8") or "f8").lower(),
            "hotkey_display": self._hotkey_display_label(),
            "prompt_editor_text": self.prompt_editor.toPlainText(),
            "custom_prompts": copy.deepcopy(self.custom_prompts),
            "dictionary": tuple(sorted(self.prefs.get("custom_dictionary", []))),
        }

    def _refresh_saved_snapshot(self):
        self._saved_settings_snapshot = self._capture_settings_snapshot()

    def _unsaved_change_descriptions(self):
        snap = self._saved_settings_snapshot
        if snap is None:
            return ["Settings were modified."]
        cur = self._capture_settings_snapshot()
        lines = []

        if cur["character"] != snap["character"]:
            lines.append(f"Persona: {snap['character']} → {cur['character']}")
        if cur["tone"] != snap["tone"]:
            lines.append(f"Tone: {snap['tone']} → {cur['tone']}")
        if cur["asr"] != snap["asr"]:
            lines.append(f"Voice-to-text model: {snap['asr']} → {cur['asr']}")
        if cur["llm"] != snap["llm"]:
            lines.append(f"Refiner (LLM): {snap['llm']} → {cur['llm']}")
        if cur["sound_enabled"] != snap["sound_enabled"]:
            lines.append(
                "Sound effects: "
                f"{'on' if cur['sound_enabled'] else 'off'} "
                f"(was {'on' if snap['sound_enabled'] else 'off'})"
            )
        if cur["startup_enabled"] != snap["startup_enabled"]:
            lines.append(
                "Launch at startup: "
                f"{'on' if cur['startup_enabled'] else 'off'} "
                f"(was {'on' if snap['startup_enabled'] else 'off'})"
            )
        if cur["use_simplified_chinese_output"] != snap["use_simplified_chinese_output"]:
            lines.append(
                "Simplified Chinese output: "
                f"{'on' if cur['use_simplified_chinese_output'] else 'off'} "
                f"(was {'on' if snap['use_simplified_chinese_output'] else 'off'})"
            )
        if cur["vram_timeout_s"] != snap["vram_timeout_s"]:
            lines.append(f"VRAM saver: {snap['vram_timeout_s']}s → {cur['vram_timeout_s']}s")
        if cur["auto_stop_s"] != snap["auto_stop_s"]:
            lines.append(f"Auto-stop silence: {snap['auto_stop_s']}s → {cur['auto_stop_s']}s")
        if cur["hotkey_pref"] != snap["hotkey_pref"]:
            lines.append(f"Recording hotkey: {snap['hotkey_display']} → {cur['hotkey_display']}")
        prompts_changed = cur["custom_prompts"] != snap["custom_prompts"]
        editor_changed = (cur["prompt_editor_text"] or "").strip() != (snap["prompt_editor_text"] or "").strip()
        if prompts_changed or editor_changed:
            lines.append("Custom instructions: edited (current or other persona/tone presets)")

        if cur["dictionary"] != snap["dictionary"]:
            s_set, c_set = set(snap["dictionary"]), set(cur["dictionary"])
            n_add = len(c_set - s_set)
            n_rem = len(s_set - c_set)
            if n_add and n_rem:
                lines.append(f"Custom dictionary: {n_add} added, {n_rem} removed")
            elif n_add:
                lines.append(f"Custom dictionary: {n_add} term(s) added")
            elif n_rem:
                lines.append(f"Custom dictionary: {n_rem} term(s) removed")
            else:
                lines.append("Custom dictionary: modified")

        return lines if lines else ["Settings were modified."]

    def load_initial_state(self):
        # Load initial values from unified config (honors global defaults if no user prefs)
        
        # Helper to set combo text safely
        def set_combo_safe(combo, text):
            index = combo.findText(text)
            if index >= 0:
                combo.setCurrentIndex(index)
            else:
                # Fallback: try case-insensitive or partial match
                for i in range(combo.count()):
                    item_text = combo.itemText(i).lower()
                    if text.lower() in item_text:
                        combo.setCurrentIndex(i)
                        return
                
                # Special fallback for Refiner: prefer Gemma E2B if saved name missing
                if combo == self.llm_combo:
                    for i in range(combo.count()):
                        if "gemma 4 e2b" in combo.itemText(i).lower():
                            combo.setCurrentIndex(i)
                            return

                # Default to index 0 if still not found
                if combo.count() > 0:
                    combo.setCurrentIndex(0)

        self.char_combo.blockSignals(True)
        self.tone_combo.blockSignals(True)
        self.asr_combo.blockSignals(True)
        self.llm_combo.blockSignals(True)
        
        set_combo_safe(self.char_combo, self.config.get("character", "Writing Assistant"))
        set_combo_safe(self.tone_combo, self.config.get("tone", "Natural"))
        _asr_cfg = self.config.get("whisper_model")
        if not _asr_cfg:
            _wr = (self.config.get("whisper_repo") or self.tech_config.get("whisper_repo") or "").strip()
            if _wr:
                for m in self.asr_library:
                    if (m.get("whisper_repo") or m.get("repo") or "").strip() == _wr:
                        _asr_cfg = m.get("whisper_model")
                        break
        _asr_combo_val = models_config.DEFAULT_ASR if not _asr_cfg else self._resolve_asr_display_name(_asr_cfg)
        set_combo_safe(self.asr_combo, _asr_combo_val)
        set_combo_safe(self.llm_combo, self.config.get("current_refiner", models_config.DEFAULT_LLM))

        # Initialize descriptions
        self.update_asr_desc(self.asr_combo.currentText())
        self.update_llm_desc(self.llm_combo.currentText())
        
        # Connect change signals now that initial load is done
        self.char_combo.blockSignals(False)
        self.tone_combo.blockSignals(False)
        self.asr_combo.blockSignals(False)
        self.llm_combo.blockSignals(False)
        
        # Wire up dirty signals
        self.char_combo.currentIndexChanged.connect(self.mark_dirty)
        self.tone_combo.currentIndexChanged.connect(self.mark_dirty)
        self.asr_combo.currentIndexChanged.connect(self.mark_dirty)
        self.llm_combo.currentIndexChanged.connect(self.mark_dirty)
        self.check_sound.toggled.connect(self.mark_dirty)
        self.check_startup.toggled.connect(self.mark_dirty)
        self.check_simplified_chinese.toggled.connect(self.mark_dirty)
        self.vram_spin.valueChanged.connect(self.mark_dirty)
        self.stop_spin.valueChanged.connect(self.mark_dirty)
        self.prompt_editor.textChanged.connect(self.mark_dirty)

        self.check_sound.setChecked(self.config.get("sound_enabled", True))
        self.check_startup.setChecked(self.check_startup_status())
        self.check_simplified_chinese.setChecked(bool(self.config.get("use_simplified_chinese_output", False)))
        self.vram_spin.setValue(max(5, int(self.config.get("vram_timeout", 60))))
        
        # Auto-stop conversion display (ms to s)
        stop_ms = self.config.get("silence_timeout_ms", 10000)
        self.stop_spin.setValue(max(5, int(stop_ms/1000)))
        self.hk_val.setText(self.config.get("hotkey", "F8").upper())

        # Initial prompt load
        self.on_prompt_change()
        self.refresh_dict_list()
        
        # Initial Refiner Config
        # Priority: User Prefs > Config > Default
        current_llm = self.prefs.get("current_refiner", self.config.get("current_refiner"))
        if current_llm:
            idx = self.llm_combo.findText(current_llm)
            if idx >= 0:
                self.llm_combo.setCurrentIndex(idx)
            else:
                print(f"DEBUG: Saved Refiner '{current_llm}' not found in library. Defaulting.")
        
        # Initial ASR Config
        current_asr = self.prefs.get("whisper_model", self.config.get("whisper_model"))
        if current_asr:
            idx = self.asr_combo.findText(self._resolve_asr_display_name(current_asr))
            if idx >= 0:
                self.asr_combo.setCurrentIndex(idx)

        # Sync prefs to UI selection immediately to avoid false model-change detection on first save
        self.prefs["whisper_model"] = self.asr_combo.currentText()
        self.prefs["current_refiner"] = self.llm_combo.currentText()

        # Reset Dirty Flag after load
        self.is_dirty = False
        self._refresh_saved_snapshot()
        self._refresh_status_bar()
        # Prefetch ONNX only ran on combo text changes; initial selection was set with signals blocked.
        print(f"DEBUG: Initial Refiner: {current_llm}")

    def switch_tab(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.sidebar_buttons):
            is_active = (i == index)
            # Ensure proper string matching for stylesheet
            btn.setProperty("active", "true" if is_active else "false")
            if hasattr(btn, "nav_indicator"):
                btn.nav_indicator.setVisible(is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def init_models_tab(self):
        layout = QVBoxLayout(self.tab_models)
        layout.setSpacing(20) # Reduced from 32
        layout.setContentsMargins(0, 0, 0, 0)

        # Labels for dynamic info (Borderless/Minimalist)
        self.asr_info = QLabel("")
        self.asr_info.setStyleSheet("color: #888888; font-size: 11px; margin-top: 2px; border: none; background: transparent;")
        self.asr_info.setWordWrap(True)
        self.llm_info = QLabel("")
        self.llm_info.setStyleSheet("color: #888888; font-size: 11px; margin-top: 2px; border: none; background: transparent;")
        self.llm_info.setWordWrap(True)

        # Merged AI Group with careful layout
        ai_group = QFrame()
        ai_group.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """)
        ai_vbox = QVBoxLayout(ai_group)
        ai_vbox.setContentsMargins(22, 22, 22, 22)
        ai_vbox.setSpacing(14)
        
        header = QLabel("TRANSCRIPTION & REFINEMENT")
        header.setStyleSheet("font-weight: 800; color: rgba(255, 255, 255, 0.6); border: none; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;")
        ai_vbox.addWidget(header)
        
        # ASR Block
        lbl_asr = QLabel("VOICE-TO-TEXT MODEL")
        lbl_asr.setStyleSheet("color: #888888; border: none; font-size: 11px; margin-top: 8px;")
        ai_vbox.addWidget(lbl_asr)
        ai_vbox.addWidget(self.create_asr_combo())
        ai_vbox.addWidget(self.asr_info)
        
        # LLM Block
        lbl_llm = QLabel("REFINER (LLM) MODEL")
        lbl_llm.setStyleSheet("color: #888888; border: none; font-size: 11px; margin-top: 12px;")
        ai_vbox.addWidget(lbl_llm)
        ai_vbox.addWidget(self.create_llm_combo())
        ai_vbox.addWidget(self.llm_info)
        
        layout.addWidget(ai_group)

        # Persona Group
        persona_layout = QHBoxLayout()
        self.char_combo = ModernComboBox()
        self.char_combo.addItems(["Writing Assistant", "Code Expert", "Academic", "Executive Secretary", "Personal Buddy", "Custom"])
        self.char_combo.currentTextChanged.connect(self.on_prompt_change)
        
        self.tone_combo = ModernComboBox()
        self.tone_combo.addItems(["Professional", "Natural", "Polite", "Casual", "Aggressive", "Concise", "Custom"])
        self.tone_combo.currentTextChanged.connect(self.on_prompt_change)

        persona_layout.addWidget(self.create_field("Persona", self.char_combo))
        persona_layout.addWidget(self.create_field("Tone", self.tone_combo))
        persona_layout.setSpacing(16)
        layout.addLayout(persona_layout)

        # Prompt Editor
        prompt_header = QLabel("CUSTOM INSTRUCTIONS")
        prompt_header.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff; margin-top: 5px;")
        layout.addWidget(prompt_header)
        
        self.prompt_editor = NavigablePlainTextEdit()
        self.prompt_editor.setPlaceholderText("Enter custom instructions here...")
        self.prompt_editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Deep smoky look for editor
        self.prompt_editor.setStyleSheet("QPlainTextEdit { background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 12px; font-size: 14px; }")
        self.prompt_editor.textChanged.connect(self.update_prompt_count)
        layout.addWidget(self.prompt_editor, 1) # Give it stretch
        
        # Character Counter
        self.char_count_lbl = QLabel("0 / 2000")
        self.char_count_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.3); font-size: 11px; margin-top: 4px;")
        self.char_count_lbl.setAlignment(Qt.AlignRight)
        layout.addWidget(self.char_count_lbl)
        
        layout.addStretch()

    def create_field(self, label, widget):
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4) # Standardized for Phase 2
        lbl = QLabel(label)
        lbl.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-size: 11px; font-weight: 700; text-transform: uppercase;")
        vbox.addWidget(lbl)
        vbox.addWidget(widget)
        return container

    def create_asr_combo(self):
        self.asr_combo = ModernComboBox()
        for i, m in enumerate(self.asr_library):
            self.asr_combo.addItem(m["name"])
            self.asr_combo.setItemData(i, m["name"], Qt.ToolTipRole) # Tooltip
        self.asr_combo.currentTextChanged.connect(self.update_asr_desc)
        return self.asr_combo

    def create_llm_combo(self):
        self.llm_combo = ModernComboBox()
        for i, m in enumerate(self.llm_library):
            self.llm_combo.addItem(m["name"])
            self.llm_combo.setItemData(i, m["name"], Qt.ToolTipRole) # Tooltip
        self.llm_combo.currentTextChanged.connect(self.update_llm_desc)
        return self.llm_combo

    def update_asr_desc(self, text):
        desc = ""
        for m in self.asr_library:
            if m["name"] == text:
                desc = m.get("description", "")
                break
        self.asr_info.setText(desc)
        self.asr_info.setVisible(bool(desc))



    def update_llm_desc(self, text):
        desc = ""
        for m in self.llm_library:
            if m["name"] == text:
                desc = m.get("description", "")
                break
        self.llm_info.setText(desc)
        self.llm_info.setVisible(bool(desc))

    def init_general_tab(self):
        layout = QVBoxLayout(self.tab_general)
        layout.setSpacing(12) # Reduced from 20 for Phase 2
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Hotkey Frame
        hk_frame = QFrame()
        hk_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """)
        hk_layout = QHBoxLayout(hk_frame)
        hk_layout.setContentsMargins(20, 16, 20, 16) # Reduced from 24
        
        hk_info = QVBoxLayout()
        hk_title = QLabel("RECORDING HOTKEY")
        hk_title.setStyleSheet("font-weight: 800; color: rgba(255, 255, 255, 0.4); border: none; font-size: 11px; letter-spacing: 1px;")
        self.hk_val = QLabel("F8")
        self.hk_val.setStyleSheet("font-size: 32px; font-weight: 900; color: #ffffff; border: none; letter-spacing: -1px;")
        hk_info.addWidget(hk_title)
        hk_info.addWidget(self.hk_val)
        
        hk_layout.addLayout(hk_info)
        hk_layout.addStretch()
        
        btn_rec = QPushButton("RECORD NEW")
        btn_rec.setFixedSize(140, 44)
        btn_rec.setCursor(Qt.PointingHandCursor)
        btn_rec.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #ffffff;
                border-radius: 6px;
                font-weight: 800;
                font-size: 12px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.85);
            }
            QPushButton#btn_rec[recording="true"] {
                background-color: #ff3b30;
                color: #ffffff;
                border: 1px solid #ff3b30;
            }
        """)
        btn_rec.setObjectName("btn_rec")
        btn_rec.clicked.connect(self.start_hotkey_record)
        self.btn_rec = btn_rec
        hk_layout.addWidget(btn_rec)
        
        layout.addWidget(hk_frame)

        # Switches
        self.check_sound = QCheckBox("Play Sound Effects (Beeps)")
        self.check_startup = QCheckBox("Launch Privox at Startup")
        
        self.check_simplified_chinese = QCheckBox("Simplified Chinese output (简体中文)")
        self.check_simplified_chinese.setToolTip(
            "Off (default): all Chinese in the final output is normalized to Traditional (繁體中文).\n"
            "On: all Chinese is normalized to Simplified (简体中文).\n"
            "Applies regardless of whether dictation was Traditional or Simplified; uses zhconv when available."
        )
        for chk in [self.check_sound, self.check_startup, self.check_simplified_chinese]:
            chk.setStyleSheet("QCheckBox::indicator { width: 40px; height: 20px; } padding: 4px;")
            layout.addWidget(chk)
            
        self.check_startup.clicked.connect(self.toggle_startup)

        # Timeouts
        timeout_layout = QHBoxLayout()
        self.vram_spin = QSpinBox()
        self.vram_spin.setMinimum(5)
        self.vram_spin.setMaximum(3600)
        self.vram_spin.setFixedWidth(80)
        self.vram_spin.setSuffix(" s")
        self.vram_spin.valueChanged.connect(self.mark_dirty)

        self.stop_spin = QSpinBox()
        self.stop_spin.setMinimum(5)
        self.stop_spin.setMaximum(30)
        self.stop_spin.setFixedWidth(80)
        self.stop_spin.setSuffix(" s")
        self.stop_spin.valueChanged.connect(self.mark_dirty)

        timeout_layout.addWidget(self.create_field("VRAM Saver", self.vram_spin))
        timeout_layout.addWidget(self.create_field("Auto-Stop", self.stop_spin))
        timeout_layout.addStretch()
        layout.addLayout(timeout_layout)

        # Input Source Display
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(20, 16, 20, 16)
        
        input_lbl = QLabel("INPUT SOURCE")
        input_lbl.setStyleSheet("font-weight: 800; color: rgba(255, 255, 255, 0.4); border: none; font-size: 11px; letter-spacing: 1px;")
        
        try:
            device_info = sd.query_devices(kind='input')
            device_name = device_info.get('name', 'Unknown Device')
            channels = device_info.get('max_input_channels', 0)
            status_text = f"{device_name} ({channels} Ch)"
            status_color = "#4CAF50" # Green
        except Exception:
            status_text = "No Input Device Found"
            status_color = "#FF5555" # Red

        self.input_val = QLabel(status_text)
        self.input_val.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {status_color}; border: none;")
        self.input_val.setWordWrap(False)
        
        input_info_layout = QVBoxLayout()
        input_info_layout.setSpacing(4)
        input_info_layout.addWidget(input_lbl)
        input_info_layout.addWidget(self.input_val)
        
        input_layout.addLayout(input_info_layout)
        
        # Refresh Button
        btn_refresh = QPushButton("↻")
        btn_refresh.setFixedSize(32, 32)
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.setToolTip("Refresh Input Devices")
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                color: #ffffff;
                border-radius: 16px;
                font-size: 18px;
                font-weight: bold;
                border: 1px solid rgba(255, 255, 255, 0.2);
                padding-bottom: 3px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
                border: 1px solid #ffffff;
            }
        """)
        btn_refresh.clicked.connect(self.refresh_input_source)
        input_layout.addStretch()
        input_layout.addWidget(btn_refresh)
        
        layout.addWidget(input_frame)
        layout.addStretch()
        
    def refresh_input_source(self):
        try:
            # Re-query
            device_info = sd.query_devices(kind='input')
            device_name = device_info.get('name', 'Unknown Device')
            channels = device_info.get('max_input_channels', 0)
            status_text = f"{device_name} ({channels} Ch)"
            status_color = "#4CAF50" # Green

            self.input_val.setStyleSheet("font-size: 14px; font-weight: 600; color: #ffffff; border: none;")
            QTimer.singleShot(
                200,
                lambda c=status_color: self.input_val.setStyleSheet(
                    f"font-size: 14px; font-weight: 600; color: {c}; border: none;"
                ),
            )
            
        except Exception:
            status_text = "No Input Device Found"
            status_color = "#FF5555" # Red
            
        self.input_val.setText(status_text)
        self.input_val.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {status_color}; border: none;")

    def init_dict_tab(self):
        layout = QVBoxLayout(self.tab_dict)
        layout.setSpacing(20)
        layout.setContentsMargins(0, 0, 0, 0)
        
        sub = QLabel("Enhance AI accuracy for specific names, terms, or brands.")
        sub.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(sub)
        
        add_layout = QHBoxLayout()
        add_layout.setSpacing(12)
        self.dict_input = QLineEdit()
        self.dict_input.setPlaceholderText("Type a word and press Enter...")
        self.dict_input.setFixedHeight(44)
        btn_add = QPushButton("ADD")
        btn_add.setFixedSize(80, 44)
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                font-weight: 800;
                font-size: 11px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
            }
        """)
        
        add_layout.addWidget(self.dict_input)
        add_layout.addWidget(btn_add)
        layout.addLayout(add_layout)
        
        # Connect events
        self.dict_input.returnPressed.connect(self.add_dict_word)
        btn_add.clicked.connect(self.add_dict_word)
        
        self.dict_scroll = QScrollArea()
        self.dict_scroll.setWidgetResizable(True)
        self.dict_container = QWidget()
        self.dict_list_layout = QVBoxLayout(self.dict_container)
        self.dict_list_layout.setAlignment(Qt.AlignTop)
        self.dict_list_layout.setContentsMargins(12, 12, 12, 12)
        self.dict_list_layout.setSpacing(8)
        self.dict_scroll.setWidget(self.dict_container)
        self.dict_scroll.setStyleSheet("""
            QScrollArea {
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 8px;
            }
            QScrollBar:vertical {
                width: 8px;
                background: transparent;
                margin: 0px 0px 0px 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.1);
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        layout.addWidget(self.dict_scroll, 1)  # Stretch to fill available height

    def on_prompt_change(self):
        """Handle persona or tone change. Save current prompt and load new one."""
        char = self.char_combo.currentText()
        tone = self.tone_combo.currentText()
        new_key = f"{char}|{tone}"
        
        # Save current if edited
        current_text = self.prompt_editor.toPlainText().strip()
        if current_text:
            self.custom_prompts[self.last_prompt_key] = current_text
            
        self.last_prompt_key = new_key
        
        # Load new
        saved_prompt = self.custom_prompts.get(new_key)
        if not saved_prompt:
            # Fallback to defaults if no user prompt saved
            default_text = self.DEFAULT_PROMPTS.get(new_key)
            if not default_text:
                # Generate a generic prompt if key is missing completely
                default_text = f"Refine the provided transcript according to the '{tone}' tone and '{char}' persona."
            saved_prompt = default_text
            
        self.prompt_editor.setPlainText(saved_prompt)
        self.update_prompt_count()

    def update_prompt_count(self):
        text = self.prompt_editor.toPlainText()
        count = len(text)
        max_chars = 2000
        
        self.char_count_lbl.setText(f"{count} / {max_chars}")
        
        if count > max_chars:
            self.char_count_lbl.setStyleSheet("color: #ff4444; font-size: 11px; margin-top: 4px; font-weight: bold;")
        else:
            self.char_count_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.3); font-size: 11px; margin-top: 4px;")

    def save_config(self):
        # 1. Capture old values from PREFS (the source of truth for UI state), not config
        old_asr = self.prefs.get("whisper_model", "")
        old_llm = self.prefs.get("current_refiner", "")

        # Update main prefs
        self.prefs["character"] = self.char_combo.currentText()
        self.prefs["tone"] = self.tone_combo.currentText()
        self.prefs["whisper_model"] = self.asr_combo.currentText()
        self.prefs["current_refiner"] = self.llm_combo.currentText()
        self.prefs["sound_enabled"] = self.check_sound.isChecked()
        self.prefs["use_simplified_chinese_output"] = self.check_simplified_chinese.isChecked()
        self.prefs["auto_stop_enabled"] = True 
        
        # Capture current prompt edits before saving
        char = self.char_combo.currentText()
        tone = self.tone_combo.currentText()
        self.custom_prompts[f"{char}|{tone}"] = self.prompt_editor.toPlainText().strip()
        
        self.prefs["custom_prompts"] = self.custom_prompts
        
        # 3. Update Technical Config
        new_asr = self.asr_combo.currentText()
        new_llm = self.llm_combo.currentText()
        for m in self.asr_library:
            if m["name"] == new_asr:
                self.tech_config["whisper_model"] = m.get("whisper_model", "")
                self.tech_config["whisper_repo"] = m.get("whisper_repo", "")
                self.tech_config["asr_backend"] = m.get("backend", "whisper")
                break
        for m in self.llm_library:
            if m["name"] == new_llm:
                self.tech_config["grammar_repo"] = m.get("repo_id", "")
                self.tech_config["grammar_file"] = m.get("file_name", "")
                break
        
        try:
            self.prefs["vram_timeout"] = max(5, self.vram_spin.value())
        except: pass
        try:
            val = max(5, self.stop_spin.value())
            # Convert Seconds from UI to MS for backend, capped at 30s
            self.prefs["silence_timeout_ms"] = min(30000, val * 1000)
        except: pass

        # Save last edited prompt
        current_text = self.prompt_editor.toPlainText().strip()
        if current_text:
            self.custom_prompts[self.last_prompt_key] = current_text

        models_config.scrub_obsolete_user_pref_keys(self.prefs)
        # Save files
        with open(self.prefs_path, "w", encoding="utf-8") as f:
            json.dump(self.prefs, f, indent=4)
        
        print(f"DEBUG: Saved Prefs. Hotkey: {self.prefs.get('hotkey')}, Path: {self.prefs_path}")
        
        # Update tech config if needed
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.tech_config, f, indent=4)
            
        self.is_dirty = False
        self._refresh_saved_snapshot()

        # 5. Check for changes
        new_asr = self.prefs.get("whisper_model", "")
        new_llm = self.prefs.get("current_refiner", "")
        
        asr_changed = old_asr != new_asr
        llm_changed = old_llm != new_llm
        models_changed = asr_changed or llm_changed

        if models_changed:
            change_lines = []
            if asr_changed:
                change_lines.append(f"Speech (ASR): {old_asr} → {new_asr}")
            if llm_changed:
                change_lines.append(f"Refiner (LLM): {old_llm} → {new_llm}")
            body = "\n".join(change_lines)
            if asr_changed and llm_changed:
                hint = (
                    "Setup will verify local files and download any missing model data "
                    "(this may be several gigabytes total)."
                )
            elif asr_changed:
                hint = (
                    "Setup will verify the new speech model; a large download runs only if "
                    "those files are not already on disk. The refiner is unchanged."
                )
            else:
                hint = (
                    "Setup will verify the new refiner; a large download runs only if "
                    "those files are not already on disk. Speech recognition is unchanged."
                )
            dialog = ModernDialog(
                self,
                "MODEL SETUP",
                "Your selection changed.",
                f"{body}\n\n{hint}\n\nProceed?",
                buttons=["Cancel", "OK"],
            )
            if dialog.exec() == 1: # OK
                self.handle_model_change_and_restart(old_asr, old_llm)
            else:
                # Revert selection in UI and prefs
                self.prefs["whisper_model"] = old_asr
                self.prefs["current_refiner"] = old_llm
                self.asr_combo.setCurrentText(old_asr)
                self.llm_combo.setCurrentText(old_llm)
                with open(self.prefs_path, "w", encoding="utf-8") as f:
                    json.dump(self.prefs, f, indent=4)
                self.is_dirty = False
                self._refresh_saved_snapshot()
                self._refresh_status_bar()
        else:
            self.show_toast("Settings saved successfully!")
            self.set_status_message("Settings saved.", 4000)

    # Common system / app shortcuts that should not be used as a Privox hotkey
    CONFLICTING_HOTKEYS = {
        # Clipboard & Undo
        "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+y",
        # Text editing
        "ctrl+a", "ctrl+s", "ctrl+d", "ctrl+f", "ctrl+h",
        "ctrl+p", "ctrl+n", "ctrl+o", "ctrl+w", "ctrl+q",
        "ctrl+r", "ctrl+t", "ctrl+e", "ctrl+g", "ctrl+k",
        "ctrl+l", "ctrl+b", "ctrl+i", "ctrl+u",
        # Window management
        "alt+f4", "alt+tab", "alt+enter",
        # System
        "ctrl+alt+delete", "ctrl+shift+esc",
        # Dangerous solo keys that break navigation
        "tab", "enter", "backspace", "delete", "space",
        "up", "down", "left", "right",
        "home", "end", "page_up", "page_down",
    }

    def start_hotkey_record(self):
        self.btn_rec.setText("RECORDING...")
        self.btn_rec.setProperty("recording", True)
        self.btn_rec.style().unpolish(self.btn_rec)
        self.btn_rec.style().polish(self.btn_rec)
        self.btn_rec.setEnabled(False)
        self.grabKeyboard()
        self.is_recording_hk = True

    def keyPressEvent(self, event):
        if hasattr(self, 'is_recording_hk') and self.is_recording_hk:
            key = event.key()
            modifiers = event.modifiers()
            
            # Escape to cancel
            if key == Qt.Key_Escape:
                self.stop_hotkey_recording()
                return

            # Capture combinations
            parts = []
            if modifiers & Qt.ControlModifier: parts.append("ctrl")
            if modifiers & Qt.ShiftModifier: parts.append("shift")
            if modifiers & Qt.AltModifier: parts.append("alt")
            
            # Map the primary key
            key_map = {
                Qt.Key_F1: "f1", Qt.Key_F2: "f2", Qt.Key_F3: "f3", Qt.Key_F4: "f4",
                Qt.Key_F5: "f5", Qt.Key_F6: "f6", Qt.Key_F7: "f7", Qt.Key_F8: "f8",
                Qt.Key_F9: "f9", Qt.Key_F10: "f10", Qt.Key_F11: "f11", Qt.Key_F12: "f12",
                Qt.Key_Space: "space", Qt.Key_Return: "enter", Qt.Key_Enter: "enter",
                Qt.Key_Tab: "tab", Qt.Key_Backspace: "backspace", Qt.Key_Delete: "delete",
                Qt.Key_Up: "up", Qt.Key_Down: "down", Qt.Key_Left: "left", Qt.Key_Right: "right",
                Qt.Key_Home: "home", Qt.Key_End: "end", Qt.Key_PageUp: "page_up", Qt.Key_PageDown: "page_down",
                Qt.Key_Insert: "insert"
            }
            
            main_key = ""
            if key in key_map:
                main_key = key_map[key]
            elif Qt.Key_A <= key <= Qt.Key_Z:
                main_key = chr(key).lower()
            elif Qt.Key_0 <= key <= Qt.Key_9:
                main_key = chr(key).lower()
            else:
                # Fallback for other characters
                text = event.text().strip().lower()
                if text and text.isprintable():
                    main_key = text
            
            # Ignore if just a modifier was pressed (key will be Key_Control, etc.)
            mod_keys = [Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta]
            if not main_key or key in mod_keys:
                # Update visual feedback to show progress (modifiers only)
                if parts:
                    disp = " + ".join([p.upper() for p in parts]) + " ..."
                    self.hk_val.setText(disp)
                return
                
            parts.append(main_key)
            hk_str = "+".join(parts)

            # --- Conflict check ---
            if hk_str.lower() in self.CONFLICTING_HOTKEYS:
                disp_conflict = " + ".join([p.upper() for p in parts])
                # Reset display to old hotkey and keep recording mode active
                old_hk = self.prefs.get("hotkey", "F8").upper()
                self.hk_val.setText(old_hk)
                self.hk_val.setToolTip("")
                self.show_toast(f"⚠  {disp_conflict} conflicts with a system shortcut — try another.", toast_type="warning")
                # Stay in recording mode so the user can immediately try again
                return

            # Save and finalize
            disp_full = " + ".join([p.upper() for p in parts])

            # Elide if too long
            disp_elided = disp_full
            if len(disp_full) > 16:
                disp_elided = disp_full[:14] + ".."

            self.hk_val.setText(disp_elided)
            self.hk_val.setToolTip(disp_full) # Tooltip for full hotkey

            self.prefs["hotkey"] = hk_str
            self.stop_hotkey_recording()
            self.is_dirty = True
        else:
            super().keyPressEvent(event)

    def stop_hotkey_recording(self):
        self.is_recording_hk = False
        self.releaseKeyboard()
        self.btn_rec.setText("RECORD NEW")
        self.btn_rec.setProperty("recording", False)
        self.btn_rec.style().unpolish(self.btn_rec)
        self.btn_rec.style().polish(self.btn_rec)
        self.btn_rec.setEnabled(True)

    def add_dict_word(self):
        word = self.dict_input.text().strip()
        if word:
            words = self.prefs.get("custom_dictionary", [])
            if word in words:
                self.show_toast(f"'{word}' is already in the dictionary!")
                return

            words.append(word)
            self.prefs["custom_dictionary"] = words
            self.dict_input.clear()
            self.refresh_dict_list()
            self.mark_dirty()

    def show_toast(self, message, toast_type="info"):
        toast = QLabel(message, self)

        if toast_type == "warning":
            toast.setStyleSheet("""
                QLabel {
                    background-color: rgba(20, 20, 20, 0.96);
                    color: #ffffff;
                    border-radius: 8px;
                    padding: 12px 20px 12px 20px;
                    font-size: 13px;
                    font-weight: 600;
                    border: 1px solid rgba(255, 255, 255, 0.30);
                    border-left: 3px solid rgba(255, 255, 255, 0.90);
                }
            """)
        else:
            toast.setStyleSheet("""
                QLabel {
                    background-color: rgba(20, 20, 20, 0.95);
                    color: #ffffff;
                    border-radius: 6px;
                    padding: 12px 24px;
                    font-size: 13px;
                    font-weight: 600;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                }
            """)

        toast.setAlignment(Qt.AlignCenter)
        toast.adjustSize()

        # Position at bottom center with some margin
        x = (self.width() - toast.width()) // 2
        y = self.height() - toast.height() - 60
        toast.move(x, y)

        # Shadow effect
        shadow = QGraphicsDropShadowEffect(toast)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 4)
        toast.setGraphicsEffect(shadow)

        toast.show()
        toast.raise_()

        # Auto dismiss
        QTimer.singleShot(3000, toast.deleteLater)

    def remove_dict_word(self, word):
        words = self.prefs.get("custom_dictionary", [])
        if word in words:
            words.remove(word)
            self.prefs["custom_dictionary"] = words
            self.refresh_dict_list()
            self.mark_dirty()

    def refresh_dict_list(self):
        # Clear layout
        while self.dict_list_layout.count():
            item = self.dict_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        for word in self.prefs.get("custom_dictionary", []):
            item_frame = QFrame()
            item_frame.setStyleSheet("background-color: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 6px; padding: 5px;")
            item_layout = QHBoxLayout(item_frame)
            item_layout.setContentsMargins(10, 5, 10, 5)
            
            lbl = QLabel(word)
            lbl.setStyleSheet("color: #dddddd; font-size: 13px; border: none;")
            
            # Elide text if too long
            fm = lbl.fontMetrics()
            elided_text = fm.elidedText(word, Qt.ElideRight, 280) # Approx width
            lbl.setText(elided_text)
            if elided_text != word:
                lbl.setToolTip(word)
            btn_del = QPushButton("×")
            btn_del.setFixedSize(24, 24)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet("color: #ff5555; background: transparent; font-size: 18px; border: none;")
            btn_del.clicked.connect(lambda ch=None, w=word: self.remove_dict_word(w))
            
            item_layout.addWidget(lbl)
            item_layout.addStretch()
            item_layout.addWidget(btn_del)
            self.dict_list_layout.addWidget(item_frame)
        
        # Spacer to keep items at top
        self.dict_list_layout.addStretch()

    def toggle_startup(self):
        if sys.platform != "win32":
            return

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "Privox"
        startup_folder = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
            "Startup",
        )
        shortcut_path = os.path.join(startup_folder, "Privox.lnk")
        if getattr(sys, "frozen", False):
            install_root = os.path.dirname(sys.executable)
        else:
            install_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        try:
            if self.check_startup.isChecked():
                # Prefer Startup-folder .lnk (WorkingDirectory set). HKCU\\Run has no cwd and duplicates installer shortcut → mutex exit / failed launch.
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
                    try:
                        winreg.DeleteValue(key, app_name)
                    except FileNotFoundError:
                        pass
                    winreg.CloseKey(key)
                except Exception:
                    pass

                os.makedirs(startup_folder, exist_ok=True)
                if getattr(sys, "frozen", False):
                    tgt = sys.executable
                    arg_frag = 'oLink.Arguments = "--run"\n'
                    icon = sys.executable
                else:
                    tgt = sys.executable
                    bootstrap_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bootstrap.py")
                    bp_esc = _win_vbs_escape_path(bootstrap_path)
                    arg_frag = f'oLink.Arguments = Chr(34) & "{bp_esc}" & Chr(34) & " --run"\n'
                    icon = os.path.join(install_root, "assets", "icon.ico")
                    if not os.path.isfile(icon):
                        icon = tgt

                _win_create_shortcut(shortcut_path, tgt, arg_frag, install_root, icon)
            else:
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
                    try:
                        winreg.DeleteValue(key, app_name)
                    except FileNotFoundError:
                        pass
                    winreg.CloseKey(key)
                except Exception as e:
                    print(f"Error removing startup registry: {e}")
                if os.path.isfile(shortcut_path):
                    try:
                        os.remove(shortcut_path)
                    except Exception as e:
                        print(f"Error removing startup shortcut: {e}")
        except Exception as e:
            print(f"Error toggle startup: {e}")

    def check_startup_status(self):
        if sys.platform != "win32":
            return False

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "Privox"
        reg_exists = False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, app_name)
            winreg.CloseKey(key)
            reg_exists = True
        except Exception:
            pass

        startup_folder = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
            "Startup",
        )
        shortcut_exists = os.path.isfile(os.path.join(startup_folder, "Privox.lnk"))

        # Installer + old "HKCU\Run" both present → two processes at logon; second hits mutex and exits (looks like a failed launch).
        if reg_exists and shortcut_exists:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
                winreg.CloseKey(key)
            except Exception:
                pass
            reg_exists = False

        return reg_exists or shortcut_exists


    def handle_model_change_and_restart(self, old_asr, old_llm):
        """
        Updates models via download_models.py using a thread-safe QThread/Signal approach.
        """
        # --- Premium Dialog Setup ---
        dlg = ModernProgressDialog(self)
        
        # --- Thread and Signal Wiring ---
        dlg.signals = ModelUpdateSignals() # Attach to dialog to prevent GC
        worker = ModelUpdateWorker(dlg.signals)
        # Parent SettingsGUI (not the dialog) so the thread is not destroyed with the dialog
        # before sys.exit(10); avoids "QThread: Destroyed while thread is still running".
        thread = QThread(self)
        worker.moveToThread(thread)
        dlg.worker = worker # Keep reference
        dlg._model_setup_thread = thread

        def on_status(msg):
            msg_l = msg.lower()
            if "downloading" in msg_l:
                dlg.set_status("Downloading Model Files", msg)
            elif "verifying" in msg_l:
                dlg.set_status("Verifying Local Files", msg)
            elif "finalizing" in msg_l or "complete" in msg_l:
                dlg.set_status("Finalizing Setup", msg)
            else:
                dlg.set_status("Model Setup Engine", msg)
        
        def on_progress(val):
            if val > 0:
                dlg.set_progress(val)
            if val == 100:
                dlg.set_status("Download Complete", "Verifying files...")

        def on_finished(success, error_msg):
            thread.quit()
            thread.wait()
            if success:
                dlg.show_completion()
            else:
                # REVERT CONFIGURATION
                try:
                    self.prefs["whisper_model"] = old_asr
                    self.prefs["current_refiner"] = old_llm
                    with open(self.prefs_path, "w", encoding="utf-8") as f:
                        json.dump(self.prefs, f, indent=4)
                    # SYNC UI after restoration
                    self.load_initial_state()
                except: pass

                dlg.reject()
                # Use ModernDialog for Error
                err_dlg = ModernDialog(
                    self, 
                    "Update Failed", 
                    "Model setup encountered an error.", 
                    f"{error_msg[:300]}\n\nPrevious settings have been restored.",
                    buttons=["OK"]
                )
                err_dlg.exec()

        dlg.signals.status.connect(on_status)
        dlg.signals.progress.connect(on_progress)
        dlg.signals.finished.connect(on_finished)
        thread.started.connect(worker.run)
        
        thread.start()
        
        # Block until thread finishes (success or revert)
        _accepted = dlg.exec() == QDialog.Accepted
        _t = getattr(dlg, "_model_setup_thread", None)
        if _t is not None:
            _t.quit()
            if not _t.wait(60_000):
                print("WARNING: Model setup QThread did not finish within 60s.", flush=True)
        if _accepted:
            print("Restarting application to apply model changes...")
            # Use exit code 10 to signal a restart requirement with settings recovery
            sys.exit(10)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SettingsGUI()
    font = QFont("Inter", 10)
    if font.exactMatch():
        app.setFont(font)
    else:
        app.setFont(QFont("Segoe UI", 10))

    window.show()
    apply_mica_or_acrylic(window, acrylic=True)
    sys.exit(app.exec())
