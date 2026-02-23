import PyInstaller.__main__
import os
import shutil

import sys

# Clean previous builds
if os.path.exists('build'):
    shutil.rmtree('build', ignore_errors=True)
if os.path.exists('dist'):
    shutil.rmtree('dist', ignore_errors=True)

print(f"Starting PyInstaller Build for {sys.platform}...")

is_mac = sys.platform == 'darwin'
icon_path = 'assets/privox.icns' if is_mac else 'assets/privox.ico'

# If compiling on mac and the icns isn't available, fallback to png
if is_mac and not os.path.exists(icon_path):
    icon_path = 'assets/icon.png'

pyinstaller_args = [
    'src/bootstrap.py',
    '--name=Privox',
    '--onefile' if not is_mac else '--onedir', # macOS bundle is better as onedir (.app)
    '--windowed' if is_mac else '--noconsole', # macOS specific flag for .app bundles
    '--clean',
    '--noupx', 
    f'--icon={icon_path}',
    '--add-data=assets:assets' if is_mac else '--add-data=assets;assets',
    '--add-data=src/voice_input.py:src' if is_mac else '--add-data=src/voice_input.py;src',
    '--add-data=src/download_models.py:src' if is_mac else '--add-data=src/download_models.py;src',
    '--add-data=src/gui_settings.py:src' if is_mac else '--add-data=src/gui_settings.py;src',
    '--add-data=src/models_config.py:src' if is_mac else '--add-data=src/models_config.py;src',
    '--add-data=pixi.toml:.' if is_mac else '--add-data=pixi.toml;.',
    
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
    '--exclude-module=llama_cpp', 
    '--exclude-module=mlx_lm',
    '--exclude-module=mlx',
    '--exclude-module=PIL',
    '--exclude-module=pystray',
    '--exclude-module=sounddevice',
    '--exclude-module=pynput',
    '--exclude-module=pyperclip',
    '--exclude-module=huggingface_hub',
]

PyInstaller.__main__.run(pyinstaller_args)

if is_mac:
    print("Build Complete. Application bundle is in 'dist/Privox.app'")
else:
    print("Build Complete. Executable is in 'dist/Privox.exe'")
