# Privox Release Notes

## v1.4 (Prompt, Filler Control & Diagnostics Update)

**Release date:** 2026-06-17

This release focuses on prompt engineering refinements to improve filler word removal, sentence breaking coherence, and universal grammar correction across all persona and tone settings, as well as diagnostic latency profiling for worker idle-wake.

### 🚀 Prompt & Refinement Improvements

- **Universal Spoken Filler Control**: Expanded Rule 12 (`SPOKEN FILLERS / HESITATION`) to apply unconditionally across all personas and tones, including `Natural` tone and `Personal Buddy` persona. Added more fillers (`erm`, and discourse-marker uses of `like`, `you know`, `I mean`, `right`, `okay` when used as pause fillers).
- **Sentence Breaking & Punctuation Coherence**: Updated Rule 3 (`PUNCTUATION, GRAMMAR & SENTENCE COHERENCE`) to explicitly grant the refiner permission to re-punctuate, merge, or split sentences when the raw ASR-produced boundaries are illogical or incoherent.
- **Universal Grammar Enforcement**: Added explicit instructions to each standard persona lens to ensure grammar, spelling, and sentence coherence are corrected, resolving a conflict in the conversational `Natural` tone overlay while preserving the speaker's vocabulary and cadence.
- **Simplified Inline Directives**: Updated internal language-conditional prompt logic in `voice_input.py` to reference the central Rule 12 directly, ensuring consistent filler-removal behavior across language-mix boundaries.

### 📊 Idle-Wake Performance Diagnostics

- **Diagnostic Latency Profiling**: Added automated benchmarking for cold/warm worker process wake-up times and model-loading costs.
- **VRAM-Isolated Process Warm-Fresh Spawn**: Verified ~2.5 seconds saved by using a pre-spawned background worker process to avoid import cost on wake.
- **CUDA Graph Warmup Verification**: Confirmed built-in warmup keeps initial transcription latency under ~0.20 seconds, eliminating first-use transcription lag.

---

## v1.3 (Installer, UX & Engine Update)

**Release date:** 2026-05-30

This release polishes first-run installation, tray and settings UX, idle-wake feedback, and the development stack (PyTorch CUDA 12.8, Gemma 4 refiner labels, llama-cpp GPU install).

### 🐛 Bug Fixes

- **Tray tooltip stuck on “Loading…” after models are ready**: The status line now switches to **Ready** when the inference worker (or in-process ASR + refiner) has finished loading, even if `ui_state` was still `INITIALIZING` or `loading_status` still said “Loading engine…”.
- **No start/ready sound when waking from VRAM idle**: Auto-stop is suspended while models reload; completing a wake load can auto-start recording when intended, or play a **ready** chime if you are already listening. A short **wake** tone confirms hotkey capture when the mic is not up yet.
- **Settings hotkey capture toggled recording**: While **RECORD NEW** is active, the main app ignores the recording hotkey so your current key can be captured. You may press the **same** hotkey again to keep it (no forced change to a different key).
- **Installer failed on `pixi.lock` v7 / conda-pypi mapping**: Bundled Pixi is upgraded to **v0.69+** and setup uses `pixi install --frozen` so the shipped lock file is not regenerated (avoids “Lock-file version 7 is newer than supported” and flaky mapping downloads on older Pixi 0.67).
- **Settings download progress** showed a blank bar until completion; now updates during download.

### 🚀 Improvements

- **Faster idle wake-to-transcribe**: The inference worker loads **Qwen ASR first** and reports ready before the Gemma refiner finishes; refiner loads in the background. Main process uses a **single background load** on hotkey-down and when recording starts (overlaps speech with model load). Sequential in-process wake also loads ASR before refiner; parallel load threshold lowered to **8 GiB** VRAM.
- **ASR options in Settings**: Default **Qwen-ASR v3 0.6B** (optional **1.7B**); **Distil-Whisper Large v3 (English)** and **Whisper Turbo Cantonese (CT2)** (JackyHoCL, faster-whisper) for faster idle wake. Cantonese CT2 uses per-segment language detection so long English passages stay in English. Legacy labels migrate automatically.
- **Idle VRAM stays at ~0 after tier 1**: By default Privox does not preload models after the VRAM saver kills a loaded worker (`PRIVOX_IDLE_PRELOAD_ASR=0`); models load on the next hotkey. Set `PRIVOX_IDLE_PRELOAD_ASR=1` for faster wake at the cost of idle VRAM.
- **Idle wake UX**: Wake/load feedback aligned (spinner + wake tone while loading, start tone when ready); `[Wake timing]` logs for diagnostics.
- **Settings model download**: Progress bar reports byte progress and stage labels during Hugging Face / GGUF downloads.
- **Clearer Gemma 4 refiner names in Settings**: Lists **Gemma 4 E2B IT** and **Gemma 4 E4B IT (TurboQuant)** with migration from older misleading labels; default refiner aligned to the E2B IT profile.
- **PyTorch 2.10 + CUDA 12.8** in the Pixi environment (`torch` / `torchaudio` cu128 wheels) for current NVIDIA drivers.
- **llama-cpp CUDA install**: `install-llama-cuda` and model download flows try **cu128 → cu126 → cu125 → cu124** wheels, then fall back to a local source build when needed.
- **Sound settings hot-reload**: `sound_enabled` from Settings is applied to the running app without restart; beep playback no longer uses a global lock that could delay stop tones after rapid toggles.
- **Hotkey preference safety**: Saving settings or internal prefs updates no longer drops the hotkey back to F8 when another write omits the field.

### 🔧 Technical Notes

- Installer writes `.privox_hotkey_capture` while Settings captures a hotkey; the main process skips `toggle_hotkey` while that flag exists.
- README adds **Install troubleshooting (Pixi / pixi.lock v7)** for manual recovery under `%LOCALAPPDATA%\Privox`.
- See **Worker-Process VRAM Isolation** below for the idle VRAM architecture (enabled by default in packaged builds).

---

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
- **"Pre-warm Models on Startup" honored under isolation**: when this Setting is enabled, the worker loads its models at launch for an instant first transcription (idle still frees everything after the VRAM Saver timeout). When disabled, only the worker process is pre-warmed (~0 VRAM) and models load on the first hotkey.

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
