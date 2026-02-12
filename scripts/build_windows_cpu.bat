@echo off
cd /d "%~dp0\.."
echo Building Wispr Voice Input (CPU OPTIMIZED)...

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo Note: This build aggressively excludes NVIDIA/CUDA libraries to save space.
echo If the app fails to launch with 'DLL load failed', revert to the standard build.

python -m PyInstaller --clean --noconsole --onefile ^
    --name WisprVoiceInput_CPU ^
    --icon "assets\icon.ico" ^
    --add-data "assets\icon.ico;assets" ^
    --hidden-import pystray._win32 ^
    --hidden-import sounddevice ^
    --hidden-import PIL ^
    --hidden-import cn2an ^
    --hidden-import funasr ^
    --hidden-import modelscope ^
    --exclude-module matplotlib ^
    --exclude-module pandas ^
    --exclude-module scipy ^
    --exclude-module tkinter ^
    --exclude-module nvidia ^
    --exclude-module caffe2 ^
    --collect-all llama_cpp ^
    --collect-all funasr ^
    --collect-all opencc ^
    src\voice_input.py

echo.
echo Build Complete. Executable is in dist\WisprVoiceInput_CPU.exe
pause
