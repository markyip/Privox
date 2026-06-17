# Privox 🎙️

![App version](https://img.shields.io/badge/app-v1.4-blue)
[![Python Version](https://img.shields.io/badge/python-3.10--3.12-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Noncommercial-green.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows-blue?logo=windows)
![Downloads](https://img.shields.io/github/downloads/markyip/Privox/total)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Donate-orange?logo=buy-me-a-coffee)](https://www.buymeacoffee.com/markyip)

**Stop typing, start speaking.**

A powerful, private, and fully local voice input assistant for Windows. Privox captures your speech, transcribes it, and refines the text using a locally running AI model — ensuring maximum privacy and complete data control.

> [!TIP]
> **Total Privacy**: Everything stays on your computer. Your voice and your words are never shared with anyone and never leave your machine.

---

## ✨ Why You'll Love Privox

- **Beautiful & Simple**: A clean, modern design that is easy to read and stays out of your way.
- **Speaks Your Language**: Intelligent support for English, Cantonese, Mandarin, Japanese, Korean, Hindi, Spanish, Arabic, and more.
- **Writes Like You**: Choose a "Persona" (like a Professional Writer or an Engineer) to match your writing style perfectly.
- **Forget Grammar Stress**: Privox automatically fixes spelling, grammar, and even removes those "uh" and "um" moments while you talk.
- **One-Key Magic**: Just tap your chosen hotkey to start talking and tap it again when you're done. Privox does the typing for you.

## 🚀 Getting Started

### 1. Installation

1. Download **Privox.exe** from our [Releases](https://github.com/markyip/Privox/releases) page. The latest stable release is **v1.4** (2026-06-17); see [RELEASE_NOTES.md](RELEASE_NOTES.md) for full changes.
2. Run the program and follow the simple on-screen instructions.
3. On your first run, Privox will take a few minutes to set up its "AI Brains"—then you're ready to go!

### 2. How to Use

> [!NOTE]
> **VRAM Usage**: Privox runs its AI models in a separate worker process. When the **VRAM Saver** kicks in after idle, that process is terminated so **GPU memory returns to ~0**. A lightweight **warm** worker (no models loaded) stays ready so the next wake skips process spawn. Models load **only when you press the hotkey** again — wake time depends on your ASR choice (~2–5 s for **Distil-Whisper** / **Whisper Turbo Cantonese CT2**, ~8–12 s for **Qwen-ASR**). Set **VRAM Saver timeout to 0** to keep models resident for instant response (~4–7 GB VRAM). Set `PRIVOX_WORKER_ISOLATION=0` to use the legacy in-process engine.

- **Always Ready**: Once launched, Privox lives in your **System Tray** (near the clock). You can right-click the icon to access Settings or exit the app.
- **Tap your hotkey** (default: `F8`): The app starts listening (you'll see a small animation in your taskbar).
- **Just Talk**: Speak naturally, as if you were talking to a friend.
- **Tap your hotkey again**: Stop talking and watch your words appear on the screen, perfectly polished!

> [!TIP]
> **Set it and forget it**: Open **Settings** from the tray icon and enable **Launch at Startup**. This way, Privox is always ready to help as soon as you turn on your computer.

> [!TIP]
> **Your Hotkey, Your Way**: Don't like `F8`? You can change it to any key or combination (like `Ctrl+Shift+Space`) in **Settings**. Open Settings by right-clicking the Privox icon in your taskbar.

> [!NOTE]
> **Speech model choices (Settings → AI Models)**  
> - **Qwen-ASR v3 0.6B** (default): best overall multilingual / code-mixed quality; slower idle wake.  
> - **Qwen-ASR v3 1.7B**: higher quality when you have more VRAM.  
> - **Distil-Whisper Large v3 (English)**: fastest idle wake for **English-only** dictation (faster-whisper / CT2).  
> - **Whisper Turbo Cantonese (CT2)**: Cantonese + English code-mix with fast wake; long English passages stay in English (per-segment language detection). Not recommended for Mandarin-only speech.

## ⚙️ Simple Controls

You don't need to be a computer expert to customize Privox. Just right-click the **Privox icon** near your clock (the system tray):

- **Settings**: Change your hotkey, **General** options (sounds, startup, **Chinese output script**, VRAM saver, auto-stop), **AI Models** (ASR + refiner, persona, custom instructions), and **Dictionary**. On Windows, refined text is delivered with **Ctrl+V** after a short end-of-recording vs foreground check; if the active window changed, Privox copies to the clipboard instead and notifies you.
- **Run at Startup**: Have Privox ready for you as soon as you turn on your computer.

## 🖥️ What You Need

- **Windows 10 or 11**.
- **A bit of space**: About **15GB** of space for the high-quality AI models.
- **Modern Hardware**: Works best on computers with an NVIDIA graphics card, but also runs on most modern desktop and laptop PCs.

## 📋 Good to Know

- **VRAM usage is model-dependent**: Privox loads two local AI models (ASR + Refiner). Typical active VRAM is around 4–7 GB depending on your selected backend and GPU size. On **10–12 GB cards**, Privox automatically caps how many refiner layers go on GPU to leave enough headroom for the ASR model — both coexist without CUDA out-of-memory errors.
- **TurboQuant refiner profiles**: Settings list **Gemma 4 E2B IT** and **E4B IT** (instruction-tuned checkpoints). They use tuned load settings (`n_ctx`, `n_gpu_layers`, `n_batch`) for a good balance on typical GPUs. This is not the separate Google **IT-Assistant** MTP drafter used for speculative decoding. **`n_ctx` is 8192** so longer dictation is less likely to be truncated during refinement; very long transcripts use a **compact system prompt** that still enforces the same critical rules but skips heavy few-shot blocks to fit context.
- **Config file safety**: If `config.json` or `.user_prefs.json` is temporarily invalid JSON while you save in an editor, Privox reports a clear error (including path and a short preview) when running **from source / Pixi** (`privox_app.log`). The **packaged executable** does not write that log file; fix the file and save again to apply settings.
- **VRAM Saver (worker isolation)**: ASR + refiner run in a **separate worker process**. After idle (`vram_timeout`, default 60 s), the loaded worker is killed and VRAM returns to **~0**; a **warm** worker (process only, no models) is respawned. Models reload on the **next hotkey**, not automatically in the background. Optional: `PRIVOX_IDLE_PRELOAD_ASR=1` for faster wake at the cost of idle VRAM. Tier 2 warm-worker recycle is **off by default** (`worker_kill_timeout=0`). Set **VRAM Saver timeout to 0** to keep models loaded.
- **Qwen-ASR on mid-range GPUs**: When using Qwen-ASR on a 10–12 GB card, the ASR model is loaded with a VRAM cap (`~42%` of total, ~5 GB on 12 GB) using `device_map` to prevent out-of-memory during the transition from CPU to GPU.
- **Very short sentences may not be refined**: To prevent hallucination, Privox will skip AI grammar correction if your spoken input is very short (roughly a few words). The original transcription will be typed out as-is. This is a deliberate safety measure to ensure quality output.
- **Chinese output script (繁體 / 简体)**: In **Settings → General**, **Simplified Chinese output (简体中文)** is **off by default**. When it is off, any Chinese in the **final pasted text** is normalized to **Traditional Chinese** (refiner instructions plus **zhconv** when the package is installed). Turn the option **on** to normalize everything to **Simplified** instead. This applies regardless of whether the speech recognition returned Traditional or Simplified characters. Colloquial Cantonese particles are still encouraged when the transcript looks like spoken Cantonese.
- **Logs and privacy (packaged app)**: The **built executable does not create or write `privox_app.log`** (no routine app log file on disk). Third-party libraries are **not** hooked through a stdout/stderr-to-log pipeline, which keeps installs quieter and avoids accidental capture of progress output. **Development** runs (`pixi run …` / `python src/voice_input.py`) still append to **`privox_app.log`** next to the project for troubleshooting. For **transcript-level** diagnostics (raw ASR, LLM prefix vs `<refined>`, paste preview), set **`PRIVOX_LOG_TRANSCRIPTION=1`** and run **from source**; that mode is intended for dev/debug, not the silent exe build. Severe failures may still surface via **tray notifications**, dialogs, or **`privox_error_last.txt`** when the app writes those paths.

## ⚠️ Known Limitations

- **Default speech model**: First-time setup downloads **Qwen-ASR v3 0.6B** (see `config.json`). **Distil-Whisper Large v3 (English)** and **Whisper Turbo Cantonese (CT2)** use faster-whisper (CT2) for lower VRAM and faster idle wake. **Qwen-ASR v3 1.7B** is optional for higher multilingual quality.
- **Multilingual accuracy varies**: Voice-to-text is **Qwen3-ASR** or **faster-whisper (Distil / Cantonese turbo)** depending on Settings. See the speech-model note under [How to Use](#2-how-to-use).
- **Accent variations may affect transcription accuracy**: The voice-to-text engine can be sensitive to strong or regional accents, which is an inherent limitation of the underlying ASR technology. If transcription quality seems off, try switching to a different ASR model in **Settings** (e.g., the Multilingual model may handle diverse accents better).
- **Occasional LLM hallucination**: Although multiple safeguards are in place, the refiner model may occasionally add, rephrase, or embellish words beyond the original transcript. The refiner is asked to return text inside `<refined>` tags; if a model ignores that format, Privox falls back to heuristics and may return the raw transcription when the reply looks like a prompt echo. If you notice output that doesn't match what you said, please report it.
- **Mixed-language in one utterance**: ASR quality still varies when you code-mix (e.g. English technical terms inside Chinese). The refiner is instructed to **preserve** Latin + CJK in the same sentence rather than translating everything to one language; if you see unwanted rewriting, try another ASR model or report an issue with a short example.

## 🛠️ Install troubleshooting (Pixi / `pixi.lock` v7)

If setup stops with **Lock-file version 7 is newer than supported** or **failed to fetch conda-pypi mapping** / **unexpected end of file**, the bundled Pixi under `%LOCALAPPDATA%\Privox\_internal\pixi\` is too old (e.g. 0.67). It cannot read the shipped lock file, tries to regenerate it, and may fail on a network fetch.

**Fix (existing install):**

```powershell
cd $env:LOCALAPPDATA\Privox
.\_internal\pixi\pixi.exe self-update
.\_internal\pixi\pixi.exe install --frozen
```

Or install [Pixi](https://pixi.sh) globally (`pixi self-update`), then run `pixi install --frozen` in the Privox folder. New installers upgrade or re-download Pixi **v0.69.0+** automatically and use `--frozen` so the lock file is not regenerated.

## 🗺️ What's Coming

We're actively working on making Privox even better:

- **♿ Accessibility Version**: A dedicated high-contrast, screen-reader-friendly version is under active development for users with accessibility needs.

## 🤝 Contributing & Feedback

Privox is a **solo project**, and I know there is always room for improvement. If you have ideas, suggestions, or feedback—no matter how small—I would genuinely appreciate hearing from you.

Here are some ways you can help:

- **🐛 Report bugs** by opening an [Issue](https://github.com/markyip/Privox/issues).
- **💡 Suggest features** or improvements—I'm always looking for fresh perspectives.
- **⭐ Star this repo** if you find it useful. It helps others discover the project.
- **📣 Share your experience**—what worked, what didn't, or what you wish was different.

Every piece of feedback helps shape Privox into a better tool. Thank you for your time and support!

## 🔧 Advanced Configuration

For power users who want to go beyond the Settings UI, Privox can be customized by editing the configuration files directly.

The **packaged app version** string is `APP_VERSION` in `src/bootstrap.py` (currently **1.4**); it should match `version_info.txt` and `assets/privox.manifest` when you cut a release build.

### Near-Zero Idle VRAM (Worker-Process Isolation)

Privox runs the ASR + refiner models in a **separate, killable worker process** so that idle returns **essentially all** GPU memory (including the CUDA context) to the OS. This is **on by default** for both the packaged app and the `pixi run start-worker-isolation` dev task (also launched by `run_dev.bat`).

> [!NOTE]
> The packaged `Privox.exe` is the installer/launcher; it runs `src/voice_input.py` under the bundled **Pixi `pythonw.exe`** (not a frozen binary), which is what lets it spawn the worker (`privox_worker.py`) directly — no dedicated frozen entry point is required.

Behaviour:

- **Idle VRAM ≈ 0**: at `vram_timeout` (default 60 s) the loaded worker is killed (weights + CUDA context) and a **warm** worker (no models, ~0 VRAM) is respawned. By default Privox does **not** reload models until your next hotkey (`PRIVOX_IDLE_PRELOAD_ASR` defaults to `0`).
- **Wake from idle**: warm worker has already paid spawn + import; you only wait for model load. Typical: **~2–5 s** (Distil / Cantonese CT2), **~8–12 s** (Qwen-ASR 0.6B).
- **Extended idle (tier 2, optional)**: `worker_kill_timeout` defaults to **0** (disabled). When set (e.g. `PRIVOX_WORKER_KILL_TIMEOUT=3600`), the warm worker is recycled after long idle; Privox respawns a fresh warm process immediately so the next wake still skips spawn+import.
- **Pre-warm Models on Startup** (Settings → General): load at launch for an instant first transcription (idle saver still frees VRAM after `vram_timeout`).
- **Faster idle wake at cost of VRAM**: `PRIVOX_IDLE_PRELOAD_ASR=1` preloads models after tier-1 idle.
- **Instant response**: VRAM Saver timeout **0**, or `PRIVOX_WORKER_ISOLATION=0` for in-process mode.

Environment variables (optional):

| Variable | Default | Purpose |
|----------|---------|---------|
| `PRIVOX_IDLE_PRELOAD_ASR` | `0` | After tier-1 idle, preload models in background (faster wake, uses VRAM while idle). |
| `PRIVOX_WORKER_KILL_TIMEOUT` | `0` (off) | Optional tier-2 warm-worker recycle after N seconds idle (then warm respawn). |
| `PRIVOX_WHISPER_PER_SEGMENT_LANGUAGE` | on | Per-segment LID for faster-whisper code-mix (set `0` to disable). |
| `PRIVOX_WORKER_ISOLATION` | `1` (packaged) | `0` = legacy in-process engine. |

See [RELEASE_NOTES.md](RELEASE_NOTES.md) for details.

### Adding Your Own AI Models

You can add custom ASR (voice-to-text) or LLM (refiner) models by editing `src/models_config.py`.

**To add a new voice-to-text model**, append an entry to `ASR_LIBRARY`:

Qwen3-ASR (`qwen_asr`):

```python
{
    "name": "My Qwen ASR",
    "whisper_repo": "org/Qwen3-ASR-0.6B",
    "whisper_model": "qwen3-asr-0.6b",
    "repo": "org/Qwen3-ASR-0.6B",
    "backend": "qwen_asr",
    "description": "Short description.",
}
```

faster-whisper / CT2 (`whisper`):

```python
{
    "name": "My CT2 Whisper",
    "whisper_repo": "org/my-model-ct2",
    "whisper_model": "my-model-id",
    "repo": "org/my-model-ct2",
    "backend": "whisper",
    "whisper_language": "en",  # optional pin, e.g. en
    "whisper_code_mix": True,  # optional: per-segment LID for Cantonese+English
    "description": "Short description.",
}
```

**To add a new refiner (LLM) model**, append an entry to `LLM_LIBRARY`:

```python
{
    "name": "My Custom LLM",
    "repo_id": "username/my-custom-llm-GGUF",
    "file_name": "my-custom-llm-Q4_K_M.gguf",
    "prompt_type": "chatml",  # Supported: "chatml", "gemma", "llama", "t5"
    "turboquant": true,
    "n_ctx": 6144,
    "n_gpu_layers": 24,
    "description": "A short description of this model."
}
```

> [!NOTE]
> LLM models must be in GGUF format and hosted on [Hugging Face](https://huggingface.co). Privox will download them automatically on first use.

> [!TIP]
> If a model repository uses Xet storage, installing `hf_xet` improves download performance.

After saving your changes, restart Privox. Your new models will appear in the **Settings** dropdowns.

### Customizing Prompts & Personas

You can create your own writing style directly in the **Settings UI**:

1. Open **Settings** → **AI Models** tab.
2. Select **"Custom"** from either the **Persona** or **Tone** dropdown.
3. Write your own instructions in the **Custom Instructions** text box.
4. Click **Save All Settings**.

Your custom instructions tell the AI exactly how to refine your speech. For example:

- _"Write like a friendly tech blogger. Keep sentences short and punchy."_
- _"Use formal Cantonese written style. Preserve all technical terms in English."_

### Custom Dictionary

Add domain-specific words (jargon, brand names, acronyms) that the AI should never misspell:

1. Open **Settings** → **Dictionary** tab.
2. Type a word and press **Enter** or click **Add**.

This is useful for names like `CUDA`, `PyTorch`, `Privox`, or any specialized terminology in your field.

## 📄 A Note on Usage

Privox is free for your **Personal & Research use**. Commercial or business use is not allowed without permission. See the [LICENSE](LICENSE) file for more details.

## 📧 Contact

For issues, questions, or suggestions, please open an issue on GitHub.
