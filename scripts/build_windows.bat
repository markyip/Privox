@echo off
setlocal EnableExtensions
REM Build Privox Windows onefile installer payload. Run from repo: scripts\build_windows.bat
cd /d "%~dp0\.."

if not exist "pixi.toml" (
    echo ERROR: pixi.toml not found. Current dir must be the Privox repo root.
    exit /b 1
)

where pixi >nul 2>&1
if errorlevel 1 (
    echo ERROR: pixi is not on PATH. Install from https://pixi.sh
    exit /b 1
)

echo.
echo === Privox Windows build ===
echo Repo: %CD%
echo.

echo Syncing Pixi environment ^(ensures PyInstaller and deps are on disk^)...
pixi install
if errorlevel 1 (
    echo ERROR: pixi install failed.
    exit /b 1
)

pixi run python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo ERROR: PyInstaller is not importable in the Pixi env. Try: pixi clean -e default ^&^& pixi install
    exit /b 1
)

REM PyInstaller also cleans build/dist; this clears stale bytecode only.
if exist "src\__pycache__" rmdir /s /q "src\__pycache__"
if exist "__pycache__" rmdir /s /q "__pycache__"

echo Regenerating tray icon assets...
pixi run python -s -E scripts\generate_icon.py
if errorlevel 1 (
    echo ERROR: generate_icon.py failed.
    exit /b 1
)

echo.
echo Running PyInstaller ^(bundles llama_cpp/lib DLLs from current Pixi env if importable^)...
pixi run python -s -E build_app.py
if errorlevel 1 (
    echo ERROR: build_app.py failed.
    exit /b 1
)

if exist "dist\Privox.exe" (
    copy /Y "dist\Privox.exe" "Privox.exe" >nul
    echo.
    echo Build SUCCESS: dist\Privox.exe ^(also copied to repo root Privox.exe^)
) else (
    echo.
    echo Build FAILED: dist\Privox.exe not found.
    exit /b 1
)

endlocal
pause
