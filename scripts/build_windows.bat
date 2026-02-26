@echo off
cd /d "%~dp0\.."
echo Cleaning environment...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build
if exist "src\__pycache__" rmdir /s /q src\__pycache__
if exist "__pycache__" rmdir /s /q __pycache__

echo Regenerating Icons...
pixi run python -s -E scripts\generate_icon.py

echo Building Privox...
pixi run python -s -E build_app.py

if exist "dist\Privox.exe" (
    echo.
    echo Copying Privox.exe to root...
    copy /Y "dist\Privox.exe" "Privox.exe"
    echo.
    echo Build SUCCESS! Run 'Privox.exe' to test.
) else (
    echo.
    echo Build FAILED. "dist\Privox.exe" not found.
)
pause
