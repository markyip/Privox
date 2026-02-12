import os
import sys
import subprocess
import threading
import time
import logging

# Set up logging for bootstrap
logging.basicConfig(
    filename='wispr_bootstrap.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def log_info(msg):
    logging.info(msg)
    print(msg)

def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def is_torch_available():
    try:
        import torch
        return True
    except ImportError:
        return False

def install_dependencies():
    # Target directory for libraries
    lib_dir = os.path.join(os.getcwd(), "_internal_libs")
    if not os.path.exists(lib_dir):
        os.makedirs(lib_dir)

    # Add to path immediately so we can check if they land
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)

    if is_torch_available():
        log_info("Required libraries already present.")
        return True

    log_info("Missing core AI libraries (PyTorch/CUDA).")
    log_info("Starting download... This may take several minutes (approx 2GB).")
    
    # We use a simple message box to notify the user if we are in noconsole mode
    if getattr(sys, 'frozen', False):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, 
                "Wispr Initial Setup:\n\nDetailed AI libraries (PyTorch/CUDA) are being downloaded and installed.\n"
                "This will happen only once. Please keep your internet connection active.\n\n"
                "Wait for the 'Ready' notification in the system tray.", 
                "Wispr Setup", 0x40)
        except:
            pass

    try:
        # Use pip to install to target directory
        # We target specific versions to ensure compatibility
        # --no-cache-dir to save disk space during install if needed
        # --only-binary=:all: to avoid build-from-source issues
        cmd = [
            sys.executable, "-m", "pip", "install", 
            "--target", lib_dir,
            "torch", "torchaudio", "nvidia-cudnn-cu12", "nvidia-cublas-cu12",
            "--no-cache-dir"
        ]
        
        log_info(f"Running: {' '.join(cmd)}")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                log_info(f"Pip: {line.strip()}")
        
        if process.returncode == 0:
            log_info("Installation successful.")
            return True
        else:
            log_info(f"Installation failed with code {process.returncode}")
            return False
            
    except Exception as e:
        log_info(f"Error during installation: {e}")
        return False

def main():
    log_info("Wispr Bootstrap Launcher starting...")
    
    # Ensure dependencies are met
    success = install_dependencies()
    
    if success:
        log_info("Launching Wispr main application...")
        # Add the lib dir to path for the main app
        lib_dir = os.path.join(os.getcwd(), "_internal_libs")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
            
        try:
            from voice_input import VoiceInputApp
            app = VoiceInputApp()
            app.run()
        except Exception as e:
            log_info(f"CRITICAL LAUNCH ERROR: {e}")
            if sys.platform == 'win32':
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, f"App Launch Failed:\n\n{e}", "Wispr Error", 0x10)
    else:
        log_info("Failed to prepare environment. Exiting.")
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, "Failed to download required AI components.\nCheck your internet and try again.", "Wispr Setup Error", 0x10)

if __name__ == "__main__":
    main()
