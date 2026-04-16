# Start no-torch mode without `pixi run` (skips Pixi PyPI sync). Use when another process holds
# onnxruntime DLLs and `pixi run no-torch` fails with WinError 32 on copy.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Py = Join-Path $Root ".pixi\envs\default\python.exe"
if (-not (Test-Path $Py)) {
    Write-Error "Missing $Py — run: pixi install (with other ORT-using apps closed)"
}
$env:PRIVOX_NO_TORCH = "1"
$env:PRIVOX_CT2_ASR = "1"
& $Py (Join-Path $Root "src\voice_input.py") @args
