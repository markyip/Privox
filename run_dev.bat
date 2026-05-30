@echo off
cd /d "%~dp0"
echo Starting Privox (Dev Mode - Worker Isolation)...
echo ASR + refiner run in a separate process; idle frees all VRAM.
pixi run start-worker-isolation
pause
