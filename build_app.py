import os
import site
import shutil
import subprocess
import sys
import time


def _drop_user_site_from_sys_path() -> None:
    """Use Pixi/env site-packages only for the build. A user-site PyInstaller under
    %APPDATA%\\Python\\... can win on some setups and then fail (e.g. altgraph → pkg_resources).
    """
    try:
        usp = site.getusersitepackages()
    except Exception:
        return
    if not usp or not isinstance(usp, str):
        return
    usp_key = os.path.normcase(os.path.abspath(usp))
    sys.path[:] = [
        p
        for p in sys.path
        if os.path.normcase(os.path.abspath(p)) != usp_key
    ]


_drop_user_site_from_sys_path()

import PyInstaller.__main__


def _collect_zhconv_pyinstaller_args():
    """Only pass --hidden-import=zhconv if the build interpreter can import it (PyInstaller validates the name)."""
    try:
        import zhconv  # noqa: F401
    except ImportError:
        print(
            "WARNING: zhconv not installed in this Python — skipping --hidden-import=zhconv. "
            "Chinese script post-processing will rely on the Pixi env after install, or run: "
            "pixi run python build_app.py",
            file=sys.stderr,
        )
        return []
    return ["--hidden-import=zhconv"]


def _terminate_running_privox():
    """Terminate running Privox-related processes that may lock dist/Privox.exe."""
    try:
        # Kill packaged executable if running.
        subprocess.run(
            ["taskkill", "/F", "/IM", "Privox.exe"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass

    # Also stop python/pythonw instances running project entrypoints.
    kill_cmd = (
        r"Get-CimInstance Win32_Process -Filter ""Name = 'python.exe' OR Name = 'pythonw.exe'"" "
        r"| Where-Object { $_.CommandLine -match 'voice_input\.py' -or $_.CommandLine -match 'bootstrap\.py' -or $_.CommandLine -match 'gui_settings\.py' } "
        r"| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", kill_cmd],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass

    time.sleep(1.0)

# Ensure old processes are not locking output files.
_terminate_running_privox()

# Clean previous builds
if os.path.exists('build'):
    shutil.rmtree('build', ignore_errors=True)
if os.path.exists('dist'):
    # Retry once in case AV/file indexer briefly holds a handle.
    shutil.rmtree('dist', ignore_errors=True)
    if os.path.exists('dist'):
        time.sleep(1.0)
        shutil.rmtree('dist', ignore_errors=True)

print("Starting PyInstaller Build...")

_pyinstaller_argv = [
    'src/bootstrap.py',
    '--name=Privox',
    '--onefile',
    '--clean',
    '--noconsole',
    '--noupx', # Disabling UPX often reduces false positives from AV
    '--icon=assets/privox.ico',
    '--add-data=assets;assets',
    '--add-data=src;src',
    '--add-data=pixi.toml;.',
    '--add-data=pixi.lock;.',
    '--add-data=uninstall.bat;.',
    '--add-data=config.json;.',
    # Embed Windows metadata to reduce AV false positives
    '--version-file=version_info.txt',
    '--manifest=assets/privox.manifest',
    
    # Core Application (NOT bundled as binary, but as data for system-python launch)
    # '--hidden-import=voice_input',
    
    # Dependencies to Bundle (Lite but functional)
    # '--hidden-import=pystray',
    # '--hidden-import=pystray._win32',
    # '--hidden-import=sounddevice',
    # '--hidden-import=PIL',
    
    # Explicit Exclusions (Heavy Libs handled by Bootstrap)
    '--exclude-module=torch',
    '--exclude-module=torchaudio',
    '--exclude-module=torchvision',
    '--exclude-module=nvidia',
    '--exclude-module=caffe2',
    '--exclude-module=triton',
    '--exclude-module=matplotlib',
    '--exclude-module=pandas',
    '--exclude-module=scipy',
    '--exclude-module=transformers', 
    '--exclude-module=faster_whisper',
    '--exclude-module=ctranslate2',
    '--exclude-module=tokenizers',
    '--exclude-module=onnxruntime',
    # llama_cpp runtime is installed into Pixi env from bundled wheels/ at first-run model setup.
    # Keep bootstrap lean: do not embed llama_cpp package or lib/*.dll into Privox.exe.
    '--exclude-module=PIL',
    '--exclude-module=pystray',
    '--exclude-module=sounddevice',
    '--exclude-module=pynput',
    '--exclude-module=pyperclip',
    '--exclude-module=huggingface_hub',
]

if os.path.isdir("scripts"):
    _pyinstaller_argv.append("--add-data=scripts;scripts")

# Optional: vendor a CUDA-built llama_cpp_python-*.whl so end users skip source compiles.
if os.path.isdir("wheels"):
    whl_count = sum(1 for n in os.listdir("wheels") if n.endswith(".whl"))
    if whl_count:
        print(f"PyInstaller: embedding {whl_count} file(s) from wheels/ (llama-cpp runtime source for first-run install).")
    _pyinstaller_argv.append("--add-data=wheels;wheels")

_pyinstaller_argv.extend(_collect_zhconv_pyinstaller_args())

PyInstaller.__main__.run(_pyinstaller_argv)

print("Build Complete. Executable is in 'dist/Privox.exe'")
