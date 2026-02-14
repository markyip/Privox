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
    '--name=Privox',
    '--onefile',
    '--clean',
    '--noconsole',
    '--icon=assets/privox.ico',
    '--add-data=assets;assets',
    '--add-data=src/voice_input.py;src',
    '--add-data=src/download_models.py;src',
    '--add-data=pixi.toml;.',
    
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
    '--exclude-module=llama_cpp', # Exclude llama_cpp as it is in _internal_libs
    '--exclude-module=PIL',
    '--exclude-module=pystray',
    '--exclude-module=sounddevice',
    '--exclude-module=pynput',
    '--exclude-module=pyperclip',
    '--exclude-module=huggingface_hub',
])

print("Build Complete. Executable is in 'dist/Privox.exe'")
