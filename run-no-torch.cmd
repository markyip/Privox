@echo off
setlocal
cd /d "%~dp0"
if not exist ".pixi\envs\default\python.exe" (
  echo Missing .pixi\envs\default\python.exe — run: pixi install
  exit /b 1
)
set PRIVOX_NO_TORCH=1
set PRIVOX_CT2_ASR=1
".pixi\envs\default\python.exe" "src\voice_input.py" %*
