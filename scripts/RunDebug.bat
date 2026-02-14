@echo off
cd /d "%~dp0.."
if exist "_internal\pixi\pixi.exe" (
    "_internal\pixi\pixi.exe" run python src\debug_install.py
) else (
    echo Pixi not found, trying PATH...
    pixi run python src\debug_install.py
)
pause
