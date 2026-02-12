@echo off
cd /d "%~dp0\.."
echo Building Wispr Voice Input...
python build_app.py
pause
