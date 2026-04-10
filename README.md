# Privox 🎙️

![App version](https://img.shields.io/badge/app-v1.2.0-blue)
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

1. Download **Privox.exe** from our [Releases](https://github.com/markyip/Privox/releases) page. This repo’s current app version is **v1.2.0**; see [RELEASE_NOTES.md](RELEASE_NOTES.md) for changes.
2. Run the program and follow the simple on-screen instructions.
3. On your first run, Privox will take a few minutes to set up its "AI Brains"—then you're ready to go!

### 2. How to Use

- **Always Ready**: Once launched, Privox lives in your **System Tray** (near the clock). You can right-click the icon to access Settings or exit the app.
- **Tap your hotkey** (default: `F8`): The app starts listening (you'll see a small animation in your taskbar).
- **Just Talk**: Speak naturally, as if you were talking to a friend.
- **Tap your hotkey again**: Stop talking and watch your words appear on the screen, perfectly polished!

> [!TIP]
> **Set it and forget it**: Open **Settings** from the tray icon and enable **Launch at Startup**. This way, Privox is always ready to help as soon as you turn on your computer.

> [!TIP]
> **Your Hotkey, Your Way**: Don't like `F8`? You can change it to any key or combination (like `Ctrl+Shift+Space`) in **Settings**. Open Settings by right-clicking the Privox icon in your taskbar.

## ⚙️ Simple Controls

You don't need to be a computer expert to customize Privox. Just right-click the **Privox icon** near your clock (the system tray):

- **Settings**: Change your hotkey, **General** options (sounds, startup, **Chinese output script**, VRAM saver, auto-stop), **AI Models** (ASR + refiner, persona, custom instructions), and **Dictionary**.
- **Run at Startup**: Have Privox ready for you as soon as you turn on your computer.

## 🖥️ What You Need

- **Windows 10 or 11**.
- **A bit of space**: About **15GB** of space for the high-quality AI models.
- **Modern Hardware**: Works best on computers with an NVIDIA graphics card, but also runs on most modern desktop and laptop PCs.

## 📋 Good to Know

- **VRAM usage is model-dependent**: Privox loads two local AI models (ASR + Refiner). Typical active VRAM is around 4 GB with default settings, and can vary by selected ASR backend (e.g. Qwen-ASR vs faster-whisper) and refiner model.
- **TurboQuant refiner profiles**: Current refiner options use tuned load settings (`n_ctx`, `n_gpu_layers`, `n_batch`) to reduce VRAM pressure while preserving quality.
- **VRAM Saver**: Privox can automatically unload heavy models after inactivity and reload on next hotkey press.
- **Very short sentences may not be refined**: To prevent hallucination, Privox will skip AI grammar correction if your spoken input is very short (roughly a few words). The original transcription will be typed out as-is. This is a deliberate safety measure to ensure quality output.
- **Chinese output script (繁體 / 简体)**: In **Settings → General**, **Simplified Chinese output (简体中文)** is **off by default**. When it is off, any Chinese in the **final pasted text** is normalized to **Traditional Chinese** (refiner instructions plus **zhconv** when the package is installed). Turn the option **on** to normalize everything to **Simplified** instead. This applies regardless of whether the speech recognition returned Traditional or Simplified characters. Colloquial Cantonese particles are still encouraged when the transcript looks like spoken Cantonese.
- **Logs and privacy (packaged app)**: When you run the **built executable**, lines that could reveal what you said (transcription diagnostics, ASR text, refiner previews, timings tied to those steps) are **not** written to `privox_app.log`. Startup, model loading, and errors may still be logged. To debug transcript issues in an exe build, set environment variable **`PRIVOX_LOG_TRANSCRIPTION=1`** (or `true` / `yes` / `on`) and restart.

## ⚠️ Known Limitations

- **Multilingual accuracy varies**: Voice-to-text is provided by **faster-whisper** (English-focused Distil/Small, plus one **Multilingual Large v3 Turbo** checkpoint) and **Qwen-ASR** on Hugging Face (shipped default: **Qwen-ASR v3 1.7B**). Non-English and code-mixed speech are best-effort; if quality is weak for your language, try **Whisper Large v3 Turbo (Multilingual)** or another **Qwen-ASR** size in Settings. Please [open an Issue](https://github.com/markyip/Privox/issues) with the model name and a short example if something looks wrong.
- **Accent variations may affect transcription accuracy**: The voice-to-text engine can be sensitive to strong or regional accents, which is an inherent limitation of the underlying ASR technology. If transcription quality seems off, try switching to a different ASR model in **Settings** (e.g., the Multilingual model may handle diverse accents better).
- **Occasional LLM hallucination**: Although multiple safeguards are in place, the refiner model may occasionally add, rephrase, or embellish words beyond the original transcript. The refiner is asked to return text inside `<refined>` tags; if a model ignores that format, Privox falls back to heuristics and may return the raw transcription when the reply looks like a prompt echo. If you notice output that doesn't match what you said, please report it.
- **Mixed-language sentences are not supported**: Privox works best when you speak in a single language per recording. Mixing two languages within the same sentence (e.g., switching between English and Cantonese mid-sentence) may produce unexpected results.

## 🗺️ What's Coming

We're actively working on making Privox even better:

- **🍎 Mac Version**: A native macOS version is currently in development.
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

The **packaged app version** string is `APP_VERSION` in `src/bootstrap.py` (currently **1.2.0**); it should match `version_info.txt` and `assets/privox.manifest` when you cut a release build.

### Adding Your Own AI Models

You can add custom ASR (voice-to-text) or LLM (refiner) models by editing `src/models_config.py`.

**To add a new voice-to-text model**, append an entry to `ASR_LIBRARY`.

*faster-whisper (CTranslate2 checkpoints on Hugging Face):*

```python
{
    "name": "My Custom Whisper Model",
    "whisper_repo": "username/my-custom-whisper-model",
    "whisper_model": "large-v3-turbo",
    "repo": "username/my-custom-whisper-model",
    "description": "A short description of this model."
}
```

> [!NOTE]
> These entries must be compatible with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2 format).

*Qwen-ASR (Hugging Face audio models used by the `qwen_asr` backend):*

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

**To add a new refiner (LLM) model**, append an entry to `LLM_LIBRARY`:

```python
{
    "name": "My Custom LLM",
    "repo_id": "username/my-custom-llm-GGUF",
    "file_name": "my-custom-llm-Q4_K_M.gguf",
    "prompt_type": "chatml",  # Supported: "chatml", "gemma", "llama", "t5"
    "turboquant": true,
    "n_ctx": 3072,
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
