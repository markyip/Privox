# Privox v1.0.0 - Initial Release

A powerful, private, and fully local voice input assistant for **Windows** and **macOS (Apple Silicon)**. Privox captures your speech, transcribes it, and refines the text using a locally running AI model — ensuring maximum privacy and complete data control.

This section rolls up everything that shipped across the **1.1.0** / **1.1.1** line plus the **1.2.0** release (version bump and refiner prompting). Older **v1.1.x** headings are folded in here so there is a single current changelog entry.

### Versioning
- Application metadata at **1.2.0**: `APP_VERSION` in `src/bootstrap.py`, Settings footer, Windows `version_info.txt` / `assets/privox.manifest`, and installer download `User-Agent`.

- **Faster-Whisper (Windows) / MLX-Whisper (macOS)**: Fast local transcription; Windows uses CTranslate2 / faster-whisper, Apple Silicon uses MLX-accelerated models.
- **True Multilingual Support**: Specialized logic for English, Cantonese, Traditional Chinese, Japanese, Korean, and more.
- **Intelligent LID (Language Detection)**: Automatically identifies the language you are speaking with high-confidence safety thresholds.
- **Optimized Performance**: Parallel model loading and optimized wake-up sequences ensure minimal latency when starting or resuming from idle.

### Performance and VRAM
- TurboQuant profile support for Qwen 3.5 4B (`n_ctx`, `n_gpu_layers`, tuned `n_batch` behavior).
- Improved low-VRAM stability with safer GPU layer fallback behavior in `GrammarChecker`.
- Default refiner remains `Gemma 4 E2B (TurboQuant)` for balanced quality vs VRAM.

### Installer and downloads
- Hugging Face downloads use `huggingface_hub` (and related dependencies); large repos may benefit from optional `hf_xet` where the environment provides it.
- `hf_xet` is **not** a direct `pixi.toml` dependency; it may still appear transitively via the Hugging Face stack.

### 🔒 Private & Secure

### Project cleanup
- Removed stale `refiner_profiles` block from `config.json`.
- Cleaned `.gitignore` JSON preference rules for clearer behavior.
- Updated documentation to reflect current TurboQuant-based refiner strategy.
- Dev utility **`check_gpu.py`** moved from `src/` to **`scripts/check_gpu.py`** (Torch CUDA + llama-cpp import smoke check; run inside the Pixi environment).

### Documentation and ASR catalog
- README aligned with the current ASR catalog (faster-whisper + Qwen-ASR; removed references to retired per-language Whisper Large entries).
- Documented Python **3.10–3.12** (per `pixi.toml`) and refiner `<refined>`-tag behavior with fallback when models do not comply.

### ASR model list
- Removed separate **Whisper Large v3 Turbo** presets per language (Cantonese, Korean, German, French, Japanese, Hindi); use **Whisper Large v3 Turbo (Multilingual)** or **Qwen-ASR** for those use cases.

### ASR defaults and catalog (documentation update)
- **Default speech model** is **Qwen-ASR v3 1.7B** (`whisper_model` id `qwen3-asr-1.7b`). Shipped `config.json`, installer verification, and model-setup defaults use this id consistently with `whisper_repo` **Qwen/Qwen3-ASR-1.7B**.
- **Qwen2-Audio 7B** is **removed** from the ASR library and Settings picker. Users who still had that preset are migrated to the new default.
- Settings loads **`whisper_model` ids** from `config.json` into the ASR combo by resolving them to the matching library **display name**; prefs and technical config stay in sync after migrations.

### Output / paste behavior (documentation update)
- After refinement, paste uses a **single serialized clipboard workflow**: the clipboard is **verified** to contain the intended text before simulating **Ctrl+V**, reducing cases where unrelated previously copied text was inserted.

### Refiner robustness
- Stronger handling when the refiner omits `<refined>` tags (strip prompt/`CRITICAL RULES` echo; fall back to transcription when appropriate).
- **Cantonese oral** wording is preserved when the transcript looks like spoken Cantonese. **Output script** (繁體 vs 简体) is controlled by the General setting, not by copying ASR’s mix of scripts.

- **Windows**: Windows 10/11; NVIDIA GPU (CUDA 12+) recommended; CPU supported; ~15 GB disk for models.
- **macOS**: **Apple Silicon only** (M1 or newer), macOS 14+ recommended; **Intel Macs are not supported**. ~15 GB disk for models and runtime; MLX-accelerated ASR/LLM paths.

### Privacy / logging (frozen executable)
- Transcription-related log lines (diagnostics, ASR/refiner text snippets, etc.) are **suppressed** when `sys.frozen` (PyInstaller build). Set **`PRIVOX_LOG_TRANSCRIPTION=1`** to re-enable for support.

### Voice capture
- Auto-stop uses **VAD** plus a **mic energy** fallback for quiet microphones; Silero **end-of-speech** silence uses a shorter internal window than the user **Auto-Stop** seconds so stopping after you finish talking behaves more naturally.

### Refiner prompting (multilingual, 1.2.0)
- **Arabic numerals (0–9)** for any numeric reference across **all** supported languages (counts, money, dates, math, lists, etc.), while keeping non-numeric wording in the transcript language (`CRITICAL_RULES` 6–7, 11).
- **Spoken arithmetic and large numbers** guidance extended to all languages (operators + − × ÷ =; locale-aware magnitudes such as 萬/億, 万/億, 만/억, lakh/crore, millions / grouping).
- **Language-specific few-shot examples** for numbers and math (e.g. ja, ko, fr, de, es, ar, hi) plus a generic fallback when the detected locale has no dedicated block.
- **User prompt layer**: base directive and high-confidence language hints reinforce digits and math rules for non-English as well as English.
