import PyInstaller.__main__
import os
import shutil

# Clean previous builds
if os.path.exists('build'):
    shutil.rmtree('build', ignore_errors=True)
if os.path.exists('dist'):
    shutil.rmtree('dist', ignore_errors=True)

print("Starting PyInstaller Build...")

PyInstaller.__main__.run([
    'src/bootstrap.py',
    '--name=WisprLocal',
    '--onefile',
    '--clean',
    '--noconsole',
    '--icon=assets/icon.ico',
    '--add-data=assets;assets',
    '--add-data=src/voice_input.py;.', # Include the main script as data so it's next to bootstrap
    # Hidden imports for bootstrap and basic UI
    '--hidden-import=pystray',
    '--hidden-import=pynput',
    '--hidden-import=PIL',
    '--hidden-import=PIL._imaging',
    '--hidden-import=pyperclip',
    '--hidden-import=huggingface_hub',
    '--hidden-import=numpy',
    '--hidden-import=pkg_resources', # Often needed for pip/entry points
    # EXCLUDE heavy libraries for Lite Build
    '--exclude-module=torch',
    '--exclude-module=torchaudio',
    '--exclude-module=nvidia', # Excludes all nvidia-cuda-*
    '--exclude-module=llama_cpp',
    '--exclude-module=faster_whisper',
    '--exclude-module=transformers',
    '--exclude-module=matplotlib',
    '--exclude-module=notebook',
    # Optimization
    '--collect-all=pystray',
    '--collect-submodules=pynput',
    '--copy-metadata=tqdm',
    '--copy-metadata=requests',
    '--copy-metadata=packaging',
])

print("Build Complete. Executable is in 'dist/WisprLocal.exe'")
