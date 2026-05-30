# Privox Release Notes

## Worker-Process VRAM Isolation (near-zero idle VRAM)

**Status:** Enabled by default for the **packaged app** and the `pixi run start-worker-isolation` dev task (`run_dev.bat`). Set `PRIVOX_WORKER_ISOLATION=0` to fall back to the legacy in-process engine.

Privox now runs the heavy ASR + refiner models inside a **separate, killable worker process** so the operating system can reclaim *all* GPU memory when idle — including the PyTorch/CUDA hardware context that `torch.cuda.empty_cache()` can never release inside a long-lived process.

> The packaged `Privox.exe` is the installer/launcher and runs `src/voice_input.py` under the bundled Pixi `pythonw.exe` (not a frozen binary), so it can spawn the worker directly without a dedicated frozen entry point.

### 🚀 Improvements

- **Near-zero idle VRAM**: When the VRAM Saver triggers, Privox now **terminates the inference worker process** instead of merely unloading model weights. This frees the entire GPU footprint (model weights **plus** the ~1–1.5 GB CUDA/cuDNN/cuBLAS context), bringing idle VRAM down to essentially **0**. (Set the VRAM Saver timeout to **0** to keep the worker resident for instant response.)
- **Faster wake from idle (~10–12 s)**: A never-loaded **"warm" worker** is pre-spawned in the background, so it has already paid the process-spawn and `import` cost (~4–5 s) while holding ~0 VRAM. Waking from idle then only needs to load the model weights. The remaining time is dominated by the Qwen3-ASR load (~8 s).
- **Two-tier idle policy**:
  - At the **VRAM Saver timeout** (`vram_timeout`, default 60 s) a *loaded* worker is killed and a fresh **warm** worker is respawned in the background — idle VRAM stays ~0 while keeping the next wake fast.
  - After **extended idle** (`worker_kill_timeout`, default 600 s; override with `PRIVOX_WORKER_KILL_TIMEOUT` or the `worker_kill_timeout` preference) the warm worker is also terminated to release its system RAM.
- **Graceful wake UX**: The worker is warmed on hotkey-down so model loading overlaps with you speaking; the tray tooltip reflects "Loading engine…" → "Ready" instead of getting stuck.

### 🔧 Technical Notes

- New modules: `src/privox_ipc.py` (length-prefixed framing over a local TCP socket) and `src/privox_worker.py` (the headless inference engine, reusing `VoiceInputApp` in `PRIVOX_ENGINE_MODE`).
- The main process keeps the tray, hotkey, microphone, VAD (CPU) and clipboard; only audio → refined-text inference is delegated to the worker.
- `bootstrap.run_app` sets `PRIVOX_WORKER_ISOLATION=1` for packaged launches; a truly frozen build of `voice_input.py` itself (not how Privox is currently packaged) would still fall back to the in-process path.

---

## v1.2 (GPU Stability & VRAM Fix Update)

**Release date:** 2026-05-28

This update resolves a crash that affected users with NVIDIA GPUs in the 10–12 GB range (e.g. RTX 3080, 4070, 4070 Ti) when using **Qwen-ASR** alongside a refiner model. It also fixes a separate issue where VRAM was not fully released during the **VRAM Saver idle** state.

### 🐛 Bug Fixes

- **Fixed tray icon state misalignment**: The tray icon's tooltip now accurately reflects the "Ready" state when the app is idle. Previously, it could falsely display "Listening..." if it got stuck during the model loading phase.

- **Fixed CUDA Out-of-Memory crash on startup** *(Qwen-ASR + 10–12 GB GPU)*: When both the grammar/refiner model and the Qwen-ASR model needed to share a mid-range GPU, the refiner could fill all available VRAM before the ASR model had a chance to load. Privox now automatically calculates how much VRAM the ASR model will need and reserves that headroom when loading the refiner — both models coexist without crashing.

- **Improved "Out of Storage" Error Handling & Cancellation**: Added a "Cancel Download" button to the model download UI, allowing users to safely interrupt large model downloads. Additionally, if the disk space runs out (`[Errno 28]`), Privox now gracefully catches the error and surfaces a clear message on the tray icon and error dialogs, instead of experiencing an unexpected application timeout.

- **Fixed VRAM not released during idle (VRAM Saver)**: After a recent update introduced smarter GPU layer placement via `device_map`, a subtle issue caused VRAM to remain occupied even after the VRAM Saver triggered and the app showed *"Idle (VRAM Free)"*. The root cause was that PyTorch's accelerate dispatch hooks intercept `.cpu()` calls on device-mapped models, silently preventing them from moving to CPU. Privox now correctly removes these hooks before offloading, ensuring GPU memory is fully freed at idle.

- **Fixed VRAM Saver timeout setting not accepting 0 (disabled)**: The Settings UI now correctly allows setting the VRAM Saver timer to **0** to disable it entirely, instead of clamping the value to a minimum of 5 seconds.

### 🔧 Improvements

- **Smarter VRAM allocation for Qwen-ASR**: The ASR model now loads with an explicit VRAM budget (`device_map=auto` + `max_memory`) on GPU systems, distributing model layers within available headroom rather than attempting a single large transfer that could fail.
- **VRAM flush between model loads**: A garbage-collection and CUDA cache flush step was added between the grammar model and ASR model load sequences, ensuring any scratch memory held by the refiner is returned to the driver before ASR initialises.
- **Improved ASR cleanup on backend switch**: Switching ASR models in Settings now correctly frees GPU memory from the previous model, including any accelerate dispatch hooks.

---


## v1.1 (Windows Experience Update)

**Release date:** 2026-05-15

This update focuses on making Privox faster, more reliable, and easier to use on Windows. We've combined several recent improvements into this single "v1.1" release to ensure the best experience for all users.

### 🚀 Performance & Speed
- **Lightning Fast AI**: We've optimized the app to take full advantage of modern NVIDIA graphics cards (including the RTX 40 and 50 series). This allows the AI to process your speech almost instantly without slowing down your computer.
- **Smoother Transcription**: The system is now much more efficient at turning your voice into text, providing a snappier feel especially on newer hardware.

### 🛠️ Reliability & "Just Works"
- **Fixed Startup Issues**: We resolved a common technical problem that caused the app to occasionally fail to start on certain Windows systems. It should now launch reliably every time.
- **Better Typing & Pasting**: When you finish speaking, Privox is now smarter about finding your active window and pasting your text exactly where your cursor is.
- **Modern AI Engine**: Upgraded core transcription engine (llama-cpp-python) to **v0.3.23**, enabling official Windows binary support and faster, more stable AI operations.
- **Cleaner Installation**: The app now does a better job of keeping your computer tidy by automatically cleaning up temporary background files.
- **Refined Installer UI**: Unified fonts and styling across the installer, and implemented correct taskbar icon association for a more professional look.
- **Improved Hotkey Reliability**: Implemented physical key-state verification to prevent the hotkey from getting "stuck" or missed during high system load.
- **Pre-warm Models**: Added a new "Pre-warm Models on Startup" feature (enabled by default) so the AI is ready to transcribe instantly without a first-use delay.

### 🛡️ Privacy & Security
- **Strictly Local**: We've further enhanced our privacy protections to ensure that your dictation never leaves your computer.
- **Silent & Unobtrusive**: The app now runs more smoothly in the background, keeping itself out of your way while you work.
