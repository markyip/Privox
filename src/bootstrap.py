import os
import shutil
import sys
import subprocess
import threading
import time
import logging
import queue
import ctypes
import zipfile
import urllib.request
import json
import winreg

# --- 0. Hard Environment Isolation (MUST BE FIRST) ---
os.environ["PYTHONNOUSERSITE"] = "1"
import site
site.ENABLE_USER_SITE = False

if sys.platform == 'win32':
    # Inject pixi environment DLL paths if already present
    env_path = os.path.join(os.getcwd(), ".pixi", "envs", "default")
    dll_path = os.path.join(env_path, "Library", "bin")
    if os.path.exists(dll_path):
        os.add_dll_directory(dll_path)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QLineEdit, QProgressBar, QPlainTextEdit,
    QStackedWidget, QFileDialog, QMessageBox, QFrame, QSizePolicy
)
from PySide6.QtGui import QIcon, QFont, QColor, QPalette
from PySide6.QtCore import Qt, QSize, Signal, QObject, QThread, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, QParallelAnimationGroup, QPoint

# --- Versioning ---
APP_VERSION = "1.0"

# Disable Symlinks for Windows
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

# Paths
if getattr(sys, 'frozen', False):
    EXE_DIR = os.path.dirname(sys.executable)
else:
    EXE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

os.chdir(EXE_DIR)

class InstallWorker(QObject):
    finished = Signal(bool)
    log_signal = Signal(str)
    progress_signal = Signal(int)

    def __init__(self, target_dir):
        super().__init__()
        self.target_dir = os.path.normpath(target_dir)

    def run(self):
        try:
            target_dir = self.target_dir
            target_exe = os.path.join(target_dir, "Privox.exe")
            
            self.log_signal.emit(f"Installing to {target_dir}...")
            self.progress_signal.emit(10)

            # 1. Install Files
            if not install_app_files(target_dir, self.log_signal.emit):
                self.finished.emit(False)
                return
            
            self.progress_signal.emit(30)
            
            # 2. Pixi Setup
            pixi_exe = ensure_pixi(target_dir, self.log_signal.emit)
            if not pixi_exe:
                self.finished.emit(False)
                return
                
            self.progress_signal.emit(40)
            self.log_signal.emit("Setting up environment (Pixi)...")
            
            success = run_pixi_command(self, [pixi_exe, "install", "-v"], cwd=target_dir)
            if not success:
                self.finished.emit(False)
                return
                
            self.progress_signal.emit(80)

            # 3. Models
            self.log_signal.emit("Checking AI Models...")
            run_pixi_command(self, [pixi_exe, "run", "python", "src/download_models.py"], cwd=target_dir)
            
            self.progress_signal.emit(95)
            register_uninstaller(target_dir, target_exe)
            
            self.progress_signal.emit(100)
            self.finished.emit(True)
            
        except Exception as e:
            self.log_signal.emit(f"Fatal Error: {e}")
            self.finished.emit(False)

def run_pixi_command(worker, cmd, cwd):
    try:
        process = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in process.stdout:
            msg = line.strip()
            if msg:
                worker.log_signal.emit(msg)
        process.wait()
        return process.returncode == 0
    except Exception as e:
        worker.log_signal.emit(f"Command Error: {e}")
        return False

def apply_dark_title_bar(window):
    """ Enforces a pitch-black title bar on Windows 10/11 using DWM API. """
    if sys.platform != 'win32':
        return
    try:
        hwnd = window.effectiveWinId().value()
        
        # Disable Mica/Acrylic (DWMWA_SYSTEMBACKDROP_TYPE = 38, None = 1)
        none_backdrop = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(none_backdrop), 4)

        # Force Dark Mode (DWMWA_USE_IMMERSIVE_DARK_MODE = 20)
        dark = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark), 4)
        
        # Caption color (BGR: 0x00000000 for pitch black)
        # This prevents the blue-ish grey focus highlight on Win 11
        black = ctypes.c_int(0x00000000)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(black), 4)
        
        # Text color (White)
        white = ctypes.c_int(0x00FFFFFF)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(white), 4)
        
        # Redraw
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027) 
    except:
        pass

class InstallerGUI(QMainWindow):
    def __init__(self, mode="install"):
        super().__init__()
        self.mode = mode
        self.setWindowTitle("Privox " + ("Uninstall" if mode == "uninstall" else "Setup"))
        self.setFixedSize(700, 600) # Slightly larger for Swiss spacing
        
        # Favicon
        icon_path = os.path.join(EXE_DIR, "assets", "icon.ico")
        if not os.path.exists(icon_path) and getattr(sys, 'frozen', False):
             icon_path = os.path.join(sys._MEIPASS, "assets", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        # Absolute Frameless Window for Swiss Style
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint if mode == "uninstall" else Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.init_ui()
        self.load_styles()
        # Removed apply_mica_or_acrylic to prevent "Square Blur" artifacts on rounded corners.
        # We now rely solely on setAttribute(Qt.WA_TranslucentBackground) for transparency.

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        # Removed apply_mica_or_acrylic

    def init_ui(self):
        self.main_container = QWidget()
        self.main_container.setObjectName("main_container")
        self.setCentralWidget(self.main_container)
        layout = QVBoxLayout(self.main_container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Custom Title Bar
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("background: transparent;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(20, 0, 10, 0)
        
        win_title = QLabel("PRIVOX SETUP" if self.mode == "install" else "PRIVOX UNINSTALL")
        win_title.setStyleSheet("font-size: 10px; font-weight: 900; letter-spacing: 2px; color: rgba(255, 255, 255, 0.4);")
        title_layout.addWidget(win_title)
        title_layout.addStretch()
        
        btn_close = QPushButton("×")
        btn_close.setFixedSize(30, 30)
        btn_close.setStyleSheet("QPushButton { background: transparent; color: white; border: none; font-size: 20px; } QPushButton:hover { color: #ff5555; }")
        btn_close.clicked.connect(self.close)
        title_layout.addWidget(btn_close)
        
        layout.addWidget(title_bar)
        
        self.stack = QStackedWidget()
        
        # Welcome Page
        self.page_welcome = QWidget()
        self.init_welcome_page()
        self.stack.addWidget(self.page_welcome)
        
        # Progress Page
        self.page_progress = QWidget()
        self.init_progress_page()
        self.stack.addWidget(self.page_progress)
        
        # Success Page
        self.page_success = QWidget()
        self.init_success_page()
        self.stack.addWidget(self.page_success)
        
        layout.addWidget(self.stack)
        
        # Bottom Bar
        self.bottom_bar = QFrame()
        self.bottom_bar.setObjectName("bottom_bar")
        self.bottom_bar.setFixedHeight(80)
        self.bottom_bar.setStyleSheet("QFrame#bottom_bar { background-color: rgba(20, 20, 20, 0.4); border-top: 1px solid rgba(255, 255, 255, 0.05); }")
        bottom_layout = QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(40, 0, 40, 0)
        bottom_layout.setSpacing(16)
        
        self.btn_cancel = QPushButton("CANCEL")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setFixedSize(120, 44)
        self.btn_cancel.clicked.connect(self.close)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        
        self.btn_next = QPushButton("INSTALL" if self.mode == "install" else "UNINSTALL")
        self.btn_next.setObjectName("btn_next")
        self.btn_next.setFixedSize(140, 44) # Slightly wider for "INSTALLING..." text
        self.btn_next.setCursor(Qt.PointingHandCursor)
        # Direct style application to bypass QSS hierarchy issues
        self.btn_next.setStyleSheet("QPushButton#btn_next { background-color: #ffffff; color: #000000; border-radius: 6px; font-weight: 900; }")
        self.btn_next.clicked.connect(self.start_install if self.mode == "install" else self.start_uninstall)
        
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_next)
        
        layout.addWidget(self.bottom_bar)

    def load_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background: transparent;
            }
            QWidget#main_container { 
                background-color: rgba(18, 18, 18, 0.92); 
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QWidget { 
                color: #ffffff; 
                font-family: 'Inter', 'Segoe UI Variable Text', 'Segoe UI', Arial; 
            }
            QLabel#title { 
                font-size: 36px; 
                font-weight: 800; 
                letter-spacing: -1px; 
                color: #ffffff;
            }
            QLabel#desc { 
                color: rgba(255, 255, 255, 0.6); 
                font-size: 14px;
                line-height: 160%; 
            }
            QLineEdit { 
                background-color: rgba(255, 255, 255, 0.05); 
                border: 1px solid rgba(255, 255, 255, 0.1); 
                padding: 12px; 
                border-radius: 6px; 
                font-size: 13px;
            }
            QPushButton { 
                background-color: rgba(255, 255, 255, 0.05); 
                border: 1px solid rgba(255, 255, 255, 0.1); 
                border-radius: 6px; 
                padding: 10px; 
                font-weight: 800;
                font-size: 12px; 
                color: #ffffff; 
            }
            QPushButton:hover { 
                background-color: rgba(255, 255, 255, 0.1); 
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QPushButton#btn_next { 
                background-color: #ffffff !important; 
                color: #000000 !important; 
                border: 1px solid #ffffff; 
                border-radius: 6px;
                font-weight: 900;
            }
            QPushButton#btn_next:hover { 
                background-color: rgba(255, 255, 255, 0.8) !important; 
            }
            QPushButton#btn_next:pressed {
                background-color: rgba(255, 255, 255, 0.6);
            }
            QPushButton#btn_next:disabled { 
                background-color: transparent !important; 
                border: 1px solid rgba(255, 255, 255, 0.1) !important; 
                color: rgba(255, 255, 255, 0.2) !important; 
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.1);
                min-height: 20px;
                border-radius: 5px;
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
            QPushButton#btn_cancel { 
                background-color: transparent; 
                border: 1px solid rgba(255, 255, 255, 0.3); 
                color: #ffffff; 
                font-weight: 800;
            }
            QPushButton#btn_cancel:hover {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.5);
            }
            QProgressBar { 
                background-color: rgba(255, 255, 255, 0.05); 
                border: 1px solid rgba(255, 255, 255, 0.1); 
                border-radius: 10px; 
                height: 12px; 
                text-align: center; 
            }
            QProgressBar::chunk { 
                background-color: #ffffff; 
                border-radius: 6px;
            }
            QPlainTextEdit { 
                background-color: rgba(0, 0, 0, 0.3); 
                border: 1px solid rgba(255, 255, 255, 0.05); 
                border-radius: 8px;
                font-family: 'Consolas', 'Cascadia Code', monospace; 
                font-size: 11px; 
                color: rgba(255, 255, 255, 0.4); 
                padding: 12px;
            }
        """)

    def init_welcome_page(self):
        layout = QVBoxLayout(self.page_welcome)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        title = QLabel("Ready to Install" if self.mode == "install" else "Ready to Uninstall")
        title.setObjectName("title")
        layout.addWidget(title)
        
        desc_text = "Privox provides robust AI voice input while keeping your data private.\nThis setup will install the required models and dependencies."
        if self.mode == "uninstall":
            desc_text = "Uninstalling Privox will remove all local models, settings, and application files.\nYour custom prompts and dictionary will also be deleted."
            
        desc = QLabel(desc_text)
        desc.setObjectName("desc")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        path_box = QFrame()
        path_box.setStyleSheet("background-color: transparent; border: none; border-radius: 12px;")
        path_layout = QVBoxLayout(path_box)
        path_layout.setContentsMargins(24, 24, 24, 24)
        
        path_label = QLabel("INSTALLATION DIRECTORY:" if self.mode == "install" else "DETECTION LOCATION:")
        path_label.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-weight: 800; font-size: 11px; letter-spacing: 1px;")
        path_layout.addWidget(path_label)
        
        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        default_path = os.path.join(os.environ.get('LOCALAPPDATA', 'C:'), "Privox")
        if self.mode == "uninstall":
            # In uninstall mode, try to detect where we are running from
            # If frozen (exe), we are likely in the install dir.
            if getattr(sys, 'frozen', False):
                default_path = os.path.dirname(sys.executable)
            else:
                default_path = EXE_DIR
            
            # Make Read Only for Uninstaller to prevent user error
            self.path_edit.setReadOnly(True)
            self.path_edit.setStyleSheet("color: rgba(255, 255, 255, 0.5); background-color: rgba(0, 0, 0, 0.2); border: 1px solid rgba(255, 255, 255, 0.05);")

        self.path_edit.setText(os.path.normpath(default_path))
        
        btn_browse = QPushButton("Browse...")
        btn_browse.setFixedSize(80, 34)
        btn_browse.clicked.connect(self.browse_path)
        
        # Hide browse button in uninstall mode
        if self.mode == "uninstall":
            btn_browse.setVisible(False)
        
        row.addWidget(self.path_edit)
        row.addWidget(btn_browse)
        path_layout.addLayout(row)
        
        layout.addWidget(path_box)
        layout.addStretch()

    def browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Install Folder", self.path_edit.text())
        if path:
            self.path_edit.setText(os.path.normpath(path))

    def init_progress_page(self):
        layout = QVBoxLayout(self.page_progress)
        layout.setContentsMargins(40, 40, 40, 40)
        
        title = QLabel("Installing..." if self.mode == "install" else "Uninstalling...")
        title.setObjectName("title")
        layout.addWidget(title)
        
        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("percent")
        self.percent_label.setAlignment(Qt.AlignRight)
        self.percent_label.setStyleSheet("font-size: 18px; font-weight: 800; color: #ffffff;")
        layout.addWidget(self.percent_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(200)
        layout.addWidget(self.log_box)

    def init_success_page(self):
        layout = QVBoxLayout(self.page_success)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignCenter)
        
        title = QLabel("App Removed" if self.mode == "uninstall" else "Success!")
        title.setObjectName("title")
        title.setStyleSheet("color: #ffffff; font-size: 48px; font-weight: 800; letter-spacing: -2px;")
        layout.addWidget(title)
        
        desc_text = "Privox has been installed successfully."
        if self.mode == "uninstall":
            desc_text = "Privox has been removed from your system."
            
        desc = QLabel(desc_text)
        desc.setStyleSheet("font-size: 16px; color: rgba(255, 255, 255, 0.6);")
        layout.addWidget(desc)

    def start_install(self):
        self.stack.setCurrentIndex(1)
        self.btn_next.setEnabled(False)
        self.btn_next.setText("INSTALLING...")
        self.btn_next.setCursor(Qt.ArrowCursor)
        self.btn_cancel.setEnabled(False)
        
        self.thread = QThread()
        self.worker = InstallWorker(self.path_edit.text())
        self.worker.moveToThread(self.thread)
        
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_finished)
        self.worker.log_signal.connect(self.append_log)
        self.worker.progress_signal.connect(self.update_progress)
        
        self.thread.start()

    def update_progress(self, val):
        self.progress_bar.setValue(val)
        self.percent_label.setText(f"{val}%")

    def append_log(self, text):
        self.log_box.appendPlainText(text)

    def on_finished(self, success):
        self.thread.quit()
        if success:
            self.stack.setCurrentIndex(2)
            if self.mode == "uninstall":
                self.btn_next.setText("Close")
                self.btn_next.clicked.disconnect()
                self.btn_next.clicked.connect(self.close)
            else:
                self.btn_next.setText("Launch")
                self.btn_next.setEnabled(True)
                self.btn_next.clicked.disconnect()
                self.btn_next.clicked.connect(self.launch_app)
            self.btn_cancel.hide()
        else:
            QMessageBox.critical(self, "Error", "Installation failed. Check logs.")
            self.btn_next.setText("Failed")
            self.btn_next.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.btn_cancel.setText("Close")

    def launch_app(self):
        target_exe = os.path.join(self.path_edit.text(), "Privox.exe")
        if os.path.exists(target_exe):
            subprocess.Popen([target_exe, "--run"])
        self.close()

    def start_uninstall(self):
        self.stack.setCurrentIndex(1)
        self.btn_next.setEnabled(False)
        self.btn_next.setText("REMOVING...")
        self.btn_next.setCursor(Qt.ArrowCursor)
        self.btn_cancel.setEnabled(False)
        
        target_dir = self.path_edit.text()
        
        def run_uninstall():
            try:
                self.worker_uninstall(target_dir)
                self.on_finished(True)
            except Exception as e:
                self.append_log(f"Error: {e}")
                self.on_finished(False)
                
        threading.Thread(target=run_uninstall, daemon=True).start()

    def worker_uninstall(self, target_dir):
        # Debug logging to file
        try:
            with open(os.path.join(os.environ.get("TEMP", "."), "privox_uninstall_debug.txt"), "a") as f:
                f.write(f"Starting Uninstall. Target: {target_dir}, PID: {os.getpid()}\n")
        except: pass

        # 1. Kill Processes (Exclude Self)
        self.append_log("Terminating processes...")
        try:
            current_pid = os.getpid()
            # Kill other running Privox instances but not this one
            proc = subprocess.run(
                ["taskkill", "/F", "/IM", "Privox.exe", "/FI", f"PID ne {current_pid}", "/T"], 
                creationflags=subprocess.CREATE_NO_WINDOW, 
                capture_output=True,
                text=True
            )
            self.append_log(f"Taskkill: Code={proc.returncode}, Out={proc.stdout.strip()}, Err={proc.stderr.strip()}")
            time.sleep(1.0)
        except Exception as e:
            self.append_log(f"Taskkill error: {e}")
        self.update_progress(20)

        # 2. Cleanup Registry
        self.append_log("Cleaning up registry...")
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Privox")
        except: pass
        self.update_progress(40)

        # 3. Remove Shortcut
        self.append_log("Removing shortcuts...")
        try:
            start_menu = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs')
            ln_path = os.path.join(start_menu, "Privox.lnk")
            if os.path.exists(ln_path): os.remove(ln_path)
        except: pass
        self.update_progress(60)

        # 4. Delete Files (Delayed)
        self.append_log("Wiping application files...")
        temp_dir = os.environ.get('TEMP', os.path.expanduser("~"))
        
        # Safety: Ensure temp_dir is NOT the target_dir (prevent self-locking)
        if os.path.abspath(temp_dir) == os.path.abspath(target_dir):
            temp_dir = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Temp')
            
        # Robust PowerShell script for cleanup (More reliable than batch)
        ps_script = os.path.join(temp_dir, f"cleanup_privox_{os.getpid()}.ps1")
        log_file = os.path.join(temp_dir, f"privox_cleanup_{os.getpid()}.log")
        
        with open(ps_script, "w") as f:
            f.write(f"$ErrorActionPreference = 'SilentlyContinue'\n")
            f.write(f"$log = '{log_file}'\n")
            f.write(f"Add-Content $log 'Starting PowerShell Cleanup for PID {os.getpid()}'\n")
            
            # Phase 1: Wait for PID
            f.write(f"$target_pid = {os.getpid()}\n")
            f.write("count = 0\n")
            f.write("while ((Get-Process -Id $target_pid -ErrorAction SilentlyContinue) -and ($count -lt 30)) {\n")
            f.write("    Start-Sleep -Seconds 1\n")
            f.write("    $count++\n")
            f.write("}\n")
            
            # Phase 2: Force Kill specific Privox instances just in case
            f.write("Get-Process -Name 'Privox' -ErrorAction SilentlyContinue | Stop-Process -Force\n")
            f.write("Start-Sleep -Seconds 2\n")

            # Phase 3: Retry Delete Loop (Rename Strategy)
            f.write(f"$target_dir = '{target_dir}'\n")
            f.write(f"$trash_dir = '{target_dir}_TRASH'\n")
            
            # Try to rename first (atomic unlock)
            f.write("if (Test-Path $target_dir) {\n")
            f.write("    Rename-Item -LiteralPath $target_dir -NewName $trash_dir -ErrorAction SilentlyContinue\n")
            f.write("}\n")
            
            f.write(f"$del_target = if (Test-Path $trash_dir) {{ $trash_dir }} else {{ $target_dir }}\n")
            
            f.write("for ($i=1; $i -le 10; $i++) {\n")
            f.write("    if (Test-Path $del_target) {\n")
            f.write("        Add-Content $log \"Attempt $i to delete $del_target\"\n")
            f.write("        Remove-Item -LiteralPath $del_target -Recurse -Force -ErrorAction SilentlyContinue\n")
            f.write("        if (-not (Test-Path $del_target)) {\n")
            f.write("            Add-Content $log 'Success'\n")
            f.write("            break\n")
            f.write("        }\n")
            f.write("        Start-Sleep -Seconds 2\n")
            f.write("    } else { break }\n")
            f.write("}\n")
            
            # Self-delete (schedule)
            f.write(f"Remove-Item '{ps_script}' -Force\n")

        # Execute PowerShell hidden
        # Execute PowerShell hidden
        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script],
            cwd=temp_dir,
            creationflags=subprocess.CREATE_NO_WINDOW, # No window
            close_fds=True
        )
        self.update_progress(100)
        self.append_log("Uninstall complete.")

# --- Helper Functions (Migrated from legacy bootstrap.py) ---

def ensure_pixi(base_dir, log_cb):
    """ Checks for local pixi executable, downloads if missing. """
    internal_dir = os.path.join(base_dir, "_internal")
    pixi_dir = os.path.join(internal_dir, "pixi")
    pixi_exe = os.path.join(pixi_dir, "pixi.exe")
    
    if os.path.exists(pixi_exe):
        log_cb("Pixi detected.")
        return pixi_exe
        
    log_cb("Downloading Pixi (Standalone packages)...")
    if not os.path.exists(pixi_dir):
        os.makedirs(pixi_dir)
        
    url = "https://github.com/prefix-dev/pixi/releases/latest/download/pixi-x86_64-pc-windows-msvc.zip"
    zip_path = os.path.join(pixi_dir, "pixi.zip")
    
    try:
        urllib.request.urlretrieve(url, zip_path)
        log_cb("Extracting Pixi...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(pixi_dir)
        os.remove(zip_path)
        return pixi_exe if os.path.exists(pixi_exe) else None
    except Exception as e:
        log_cb(f"Pixi download error: {e}")
        return None

def install_app_files(target_dir, log_cb):
    """ Copies the EXE and resources to the target directory. """
    try:
        exe_name = "Privox.exe"
        target_exe = os.path.join(target_dir, exe_name)
        if not os.path.exists(target_dir): os.makedirs(target_dir)
        
        current_exe = sys.executable
        log_cb("Preparing installation directory...")
        
        # Kill running instances
        try:
            my_pid = os.getpid()
            subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/T"], creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True, timeout=5)
            subprocess.run(["taskkill", "/F", "/IM", "Privox.exe", "/FI", f"PID ne {my_pid}"], creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True, timeout=5)
            time.sleep(2.0)
        except: pass
        
        # Copy Core Files
        if os.path.normpath(current_exe) != os.path.normpath(target_exe):
            shutil.copy2(current_exe, target_exe)
        
        # Copy Configs
        for f in ["config.json", "pixi.toml", "pixi.lock"]:
            src = os.path.join(EXE_DIR, f)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(target_dir, f))

        # Copy Assets & Models
        for folder in ["models", "assets", "src"]:
            src = os.path.join(EXE_DIR, folder)
            dst = os.path.join(target_dir, folder)
            if os.path.exists(src):
                log_cb(f"Syncing {folder}...")
                # use dirs_exist_ok=True to merge/overwrite files but keep existing user files
                try:
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                except Exception as e:
                    log_cb(f"Warning syncing {folder}: {e}")
        
        create_shortcut(target_exe, target_dir)
        
        # Register in Windows Settings (Add/Remove Programs)
        log_cb("Registering uninstaller...")
        register_uninstaller(target_dir, target_exe)
        
        return True
    except Exception as e:
        log_cb(f"Install error: {e}")
        return False


def create_shortcut(target_exe, target_dir):
    try:
        app_name = "Privox"
        icon_path = os.path.join(target_dir, "assets", "icon.ico")
        
        # 1. Start Menu Shortcut
        start_menu = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs')
        if not os.path.exists(start_menu): os.makedirs(start_menu)
        create_lnk(target_exe, target_dir, icon_path, os.path.join(start_menu, f"{app_name}.lnk"))
        
        # 2. Startup Folder Shortcut (Auto-Launch)
        startup_folder = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
        if not os.path.exists(startup_folder): os.makedirs(startup_folder)
        create_lnk(target_exe, target_dir, icon_path, os.path.join(startup_folder, f"{app_name}.lnk"))

    except Exception as e:
        print(f"Shortcut creation failed: {e}")


def create_lnk(target_exe, target_dir, icon_path, lnk_path):
    try:
        # Added --run flag to shortcut Arguments (NOT TargetPath)
        vbs_script = f'Set oWS = WScript.CreateObject("WScript.Shell")\nsLinkFile = "{lnk_path}"\nSet oLink = oWS.CreateShortcut(sLinkFile)\noLink.TargetPath = "{target_exe}"\noLink.Arguments = "--run"\noLink.WorkingDirectory = "{target_dir}"\noLink.IconLocation = "{icon_path},0"\noLink.Save'
        vbs_file = os.path.join(os.environ['TEMP'], f"mkshortcut_{os.getpid()}_{hash(lnk_path)}.vbs")
        with open(vbs_file, "w") as f: f.write(vbs_script)
        subprocess.call(["cscript", "//nologo", vbs_file], creationflags=subprocess.CREATE_NO_WINDOW)
        if os.path.exists(vbs_file): os.remove(vbs_file)
    except: pass

def apply_mica_or_acrylic(window, acrylic=True):
    if sys.platform != 'win32': return
    try:
        hwnd = window.effectiveWinId().value()
        # DWMWA_SYSTEMBACKDROP_TYPE: 1=None, 2=Mica, 3=Acrylic (Tabbed), 4=MicaAlt
        backdrop_type = ctypes.c_int(3 if acrylic else 2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop_type), 4)
        
        # Dark Mode Force
        dark = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
        
        # Caption color to black/transparent
        black = ctypes.c_int(0x00000000)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(black), 4)
    except: pass

def register_uninstaller(install_dir, exe_path):
    if sys.platform != 'win32': return
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Privox"
        icon_path = os.path.join(install_dir, "assets", "icon.ico")
        install_date = time.strftime("%Y%m%d")
        
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Privox")
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, icon_path)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{exe_path}" --uninstall')
            winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, f'"{exe_path}" --uninstall --quiet')
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Privox Team")
            winreg.SetValueEx(key, "InstallDate", 0, winreg.REG_SZ, install_date)
            winreg.SetValueEx(key, "URLInfoAbout", 0, winreg.REG_SZ, "https://github.com/markyip/Privox")
            winreg.SetValueEx(key, "HelpLink", 0, winreg.REG_SZ, "https://github.com/markyip/Privox")
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "Language", 0, winreg.REG_DWORD, 1033) # US English
            winreg.SetValueEx(key, "WindowsInstaller", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, 250000) # KB
            
        # Broadcast environment change to refresh Shell/Settings
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x001A, 0, "Environment")
    except Exception as e:
        print(f"Failed to register uninstaller: {e}")

def run_app():
    """ Launches the main application using Pixi. """
    internal_dir = os.path.join(EXE_DIR, "_internal")
    pixi_exe = os.path.join(internal_dir, "pixi", "pixi.exe")
    
    if os.path.exists(pixi_exe):
        # We use 'pixi run start-windowless' to ensure no terminal window is created
        subprocess.Popen([pixi_exe, "run", "start-windowless"], cwd=EXE_DIR, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        # Fallback if somehow Pixi is missing but we're trying to run
        print("Error: Pixi environment not found. Please reinstall.")
        sys.exit(1)

if __name__ == "__main__":
    if "--run" in sys.argv:
        run_app()
        sys.exit(0)
        
    mode = "install"
    if "--uninstall" in sys.argv:
        mode = "uninstall"

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Global palette setup for Fusion Dark - Transparent compatible
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(0, 0, 0, 0)) # Fully transparent for DWM
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 25, 25, 100))
    palette.setColor(QPalette.AlternateBase, QColor(18, 18, 18))
    palette.setColor(QPalette.Text, Qt.white)
    # Remove QPalette.Button to allow QSS to take full control
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)
    
    gui = InstallerGUI(mode=mode)
    gui.show()
    sys.exit(app.exec())
