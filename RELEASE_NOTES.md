# Privox Release Notes

## v1.2.2

**Release date:** 2026-04-15

### Release summary
- Stabilization release for the current codebase snapshot that finalizes the **v1.2.2** cut.
- Versioned metadata and docs are aligned for release packaging and GitHub distribution.

### Versioning
- Application metadata at **1.2.2**: `APP_VERSION` in `src/bootstrap.py`, Settings footer, Windows `version_info.txt` / `assets/privox.manifest`, and model-setup download `User-Agent`.

### Long transcripts and `<refined>` (follow-up to v1.2.1)
- **v1.2.1** raised Gemma **`n_ctx` to 6144**, compact system prompts for long inputs, and scaled **`max_tokens`** — this release hardens **Gemma 4 E2B/E4B** in production: **chat-native inference** via `create_chat_completion` with **`chat_format="gemma"`** so tokenization matches official templates (adds BOS correctly) and avoids **`<unused*>` degeneracy** from raw completion.
- **Fallbacks**: folded **system + user** in one turn; streaming **early-abort** on `<unused*>` spam; optional **two-turn system/user** raw prompt retry with stronger `repeat_penalty`.
- **Transcription logs** (when `PRIVOX_LOG_TRANSCRIPTION=1` or non-frozen dev): clarify that the **LLM string prefix** may still look like ASR; log **`<refined>` inner preview** and **pasted-text preview** so diagnostics align with final output.

### VRAM saver and wake performance
- **Idle unload** always releases **both ASR and refiner** (removed `unload_asr_on_idle`); ASR is cleared with **`del`** plus existing GC/CUDA cache flush.
- After VRAM-saver wake, **Grammar and Qwen-ASR load in parallel** by default (wall time ≈ max of the two). Set **`PRIVOX_SEQUENTIAL_QWEN_LOAD=1`** if you need strict sequential load (e.g. CUDA OOM).
- **Prefs hot-reload** is paused while heavy models initialize; after load, **prefs poll baseline** is synced so **`track_model_usage`** does not trigger a spurious **`load_config`**.

### Hotkey / VRAM-saver race
- If recording stops (toggle or auto-stop) while models are still loading after wake, **pending auto-start is cancelled** so Privox does not start a second phantom session when loading finishes.

### Settings (model setup)
- Saving **only ASR** or **only refiner** shows a **model-setup** dialog that lists **just the changed model**, not both.

## v1.2.1

### Versioning
- Application metadata at **1.2.1**: `APP_VERSION` in `src/bootstrap.py`, Settings footer, Windows `version_info.txt` / `assets/privox.manifest`, and installer download `User-Agent`.

### Refiner: long transcripts and context
- **Gemma 4 E2B / E4B (TurboQuant)** default **`n_ctx` increased from 3072 to 6144** so refinement sees more of long dictation before hitting context limits.
- **Long transcripts (> ~300 characters)** use **`get_system_formatter_for_transcript`**: shorter system prompt (still includes **`CRITICAL_RULES`**) and explicit **no summarization / no shortening**, instead of the full few-shot formatter that could crowd out the transcript.
- **Grammar refinement `max_tokens`** scaled up for long inputs (including CJK-length heuristics, capped at 4096) so outputs are not cut off prematurely.

### Config reload robustness
- **`load_config`** reads JSON with **`utf-8-sig`** and **`_safe_json_load`**: on **`JSONDecodeError`**, logs the **file path** and a **short preview** of the contents, returns empty dicts where appropriate, and avoids noisy tracebacks when a file is mid-save or malformed.

### Documentation
- **README** updated: TurboQuant / VRAM notes, **`n_ctx` 6144**, compact-prompt behavior, config safety, and LLM library example aligned with current defaults.

## v1.2.0

This section rolls up everything that shipped across the **1.1.0** / **1.1.1** line plus the **1.2.0** release (version bump and refiner prompting). Older **v1.1.x** headings are folded in here so there is a single current changelog entry.

### Versioning
- Application metadata at **1.2.0**: `APP_VERSION` in `src/bootstrap.py`, Settings footer, Windows `version_info.txt` / `assets/privox.manifest`, and installer download `User-Agent`.

### Refiner model library
- Removed legacy refiners: `CoEdit Large (T5)`, `Llama 3.2 3B Instruct`, `Qwen 3.5 9B`, and `Qwen 2.5 7B`.
- Kept and tuned active refiners:
  - `Multilingual (Qwen 3.5 4B)` with TurboQuant load settings.
  - `Gemma 4 E2B (TurboQuant)`.
  - `Gemma 4 E4B (TurboQuant)`.
- Updated migration logic to auto-redirect removed refiner names to the current default.

### Performance and VRAM
- TurboQuant profile support for Qwen 3.5 4B (`n_ctx`, `n_gpu_layers`, tuned `n_batch` behavior).
- Improved low-VRAM stability with safer GPU layer fallback behavior in `GrammarChecker`.
- Default refiner remains `Gemma 4 E2B (TurboQuant)` for balanced quality vs VRAM.

### Installer and downloads
- Hugging Face downloads use `huggingface_hub` (and related dependencies); large repos may benefit from optional `hf_xet` where the environment provides it.
- `hf_xet` is **not** a direct `pixi.toml` dependency; it may still appear transitively via the Hugging Face stack.

### Logging and environment hygiene
- Reduced noisy llama.cpp diagnostics being reported as hard errors in app logs.
- Improved GPU backend detection wording for newer llama.cpp system info format.
- Sanitized user-level `site-packages` paths on startup to reduce environment contamination.
- Hugging Face **tqdm** “Loading checkpoint shards” lines on stderr are downgraded so they are not mislabeled as hard errors in the app log.

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

### Chinese output (Settings → General)
- **Default (checkbox off)**: All Chinese in the **final output** is steered toward **Traditional (繁體中文)** and post-processed with **zhconv** (`zh-hant`) when available, **regardless of ASR script**.
- **Simplified Chinese output (简体中文) enabled**: Same pipeline targets **Simplified (简体)** (`zh-hans`).
- Preference is stored as `use_simplified_chinese_output` in `.user_prefs.json`.

### Privacy / logging (frozen executable)
- Transcription-related log lines (diagnostics, ASR/refiner text snippets, etc.) are **suppressed** when `sys.frozen` (PyInstaller build). Set **`PRIVOX_LOG_TRANSCRIPTION=1`** to re-enable for support.

### Voice capture
- Auto-stop uses **VAD** plus a **mic energy** fallback for quiet microphones; Silero **end-of-speech** silence uses a shorter internal window than the user **Auto-Stop** seconds so stopping after you finish talking behaves more naturally.

### Refiner prompting (multilingual, 1.2.0)
- **Arabic numerals (0–9)** for any numeric reference across **all** supported languages (counts, money, dates, math, lists, etc.), while keeping non-numeric wording in the transcript language (`CRITICAL_RULES` 6–7, 11).
- **Spoken arithmetic and large numbers** guidance extended to all languages (operators + − × ÷ =; locale-aware magnitudes such as 萬/億, 万/億, 만/억, lakh/crore, millions / grouping).
- **Language-specific few-shot examples** for numbers and math (e.g. ja, ko, fr, de, es, ar, hi) plus a generic fallback when the detected locale has no dedicated block.
- **User prompt layer**: base directive and high-confidence language hints reinforce digits and math rules for non-English as well as English.
