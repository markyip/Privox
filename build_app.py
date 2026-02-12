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
    
    # Core Application (NOT bundled as binary, but as data for system-python launch)
    # '--hidden-import=voice_input',
    
    # Dependencies to Bundle (Lite but functional)
    '--hidden-import=pystray',
    '--hidden-import=pystray._win32',
    '--hidden-import=sounddevice',
    '--hidden-import=PIL',
    # Removed hidden imports for external packages (funasr, etc)
    
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
    # '--exclude-module=tkinter', # Allowed for Installer UI
    '--exclude-module=transformers', # Explicitly exclude transformers too
    '--exclude-module=faster_whisper',
    '--exclude-module=ctranslate2',
    '--exclude-module=tokenizers',
    # '--exclude-module=funasr', # Removed
    # '--exclude-module=modelscope', # Removed
    # '--exclude-module=opencc', # Removed
    # '--exclude-module=cn2an', # Removed
    # '--exclude-module=jieba', # Removed
    '--exclude-module=onnxruntime',
    
    # Collects (Ensure bindings and small extensions are present where needed)
    '--collect-all=llama_cpp',
    # '--exclude-module=llama_cpp', 
    # Removed collections for funasr/opencc as they are now external
])

print("Build Complete. Executable is in 'dist/Privox.exe'")
