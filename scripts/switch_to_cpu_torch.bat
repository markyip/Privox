@echo off
echo.
echo ===================================================
echo SWITCHING TO CPU-ONLY PYTORCH (For Smaller Builds)
echo ===================================================
echo.
echo This will uninstall your current PyTorch (likely CUDA/GPU version)
echo and install the lightweight CPU-only version.
echo.
echo Usage: Run this BEFORE running 'build_windows_cpu.bat'.
echo.

set /p choice="Do you want to proceed? (y/n): "
if /i "%choice%" neq "y" goto :eof

echo.
echo 1. Uninstalling current torch...
pip uninstall -y torch torchaudio torchvision

echo.
echo 2. Installing CPU-only torch...
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

echo.
echo Done! You can now run 'build_windows_cpu.bat' to create a small executable.
pause
