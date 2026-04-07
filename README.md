# Privox 🎙️

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Noncommercial-green.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20(Apple%20Silicon)-lightgrey?logo=apple)
![Downloads](https://img.shields.io/github/downloads/markyip/Privox/total)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Donate-orange?logo=buy-me-a-coffee)](https://www.buymeacoffee.com/markyip)

**Stop typing, start speaking.**

A powerful, private, and fully local voice input assistant for **Windows** and **macOS (Apple Silicon)**. Privox captures your speech, transcribes it, and refines the text using a locally running AI model — ensuring maximum privacy and complete data control.

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

**Windows**

1. Download **Privox.exe** from our [Releases](https://github.com/markyip/Privox/releases) page.
2. Run the program and follow the simple on-screen instructions.

**macOS (Apple Silicon only)**

1. Download **Privox.dmg** from [Releases](https://github.com/markyip/Privox/releases).
2. Open the DMG, drag **Privox.app** into **Applications**.
3. On first launch, macOS may show a security prompt: use **Open** from the right-click menu if needed, and grant **Microphone** (and related) permissions when asked.

On first run, Privox may take a few minutes to set up its local models—then you're ready to go.

> [!NOTE]
> **Intel-based Macs are not supported** for the prebuilt macOS app or the Pixi developer environment. Use a Mac with **Apple Silicon (M1 / M2 / M3 / …)**.

### 2. How to Use

- **Always Ready**: On **Windows**, Privox lives in the **system tray** (near the clock). On **macOS**, it runs from the **menu bar**; use the icon to open Settings or quit.
- **Start dictation** (on **Windows**, default hotkey `F8`; on **macOS**, use your configured shortcut): The app starts listening (Windows shows a taskbar animation; macOS uses the menu bar status).
- **Just Talk**: Speak naturally, as if you were talking to a friend.
- **Stop dictation** the same way: stop talking and watch your words appear on the screen, perfectly polished!

> [!TIP]
> **Set it and forget it**: Open **Settings** from the tray (**Windows**) or menu bar (**macOS**) and enable **Launch at Startup** where available, so Privox is ready when you log in.

> [!TIP]
> **Your Hotkey, Your Way**: On **Windows**, the default global hotkey is `F8` (change it in **Settings**). On **macOS**, dictation uses the shortcut configured for Accessibility/paste integration (see in-app Settings).

## ⚙️ Simple Controls

You don't need to be a computer expert to customize Privox. On **Windows**, right-click the **Privox** system tray icon; on **macOS**, use the **menu bar** icon:

- **Settings**: Change your hotkey, your writing style, or which language you want to use.
- **Run at Startup**: Have Privox ready for you as soon as you turn on your computer.

## 🖥️ What You Need

**Windows**

- **Windows 10 or 11**
- About **15 GB** free disk space for models and environment
- **NVIDIA GPU (CUDA 12+)** recommended; CPU mode is supported

**macOS**

- **macOS 14 or later** on **Apple Silicon** (M1 or newer). Intel Macs are not supported.
- About **15 GB** free disk space recommended for models and the bundled runtime (more may be needed during builds)
- Transcription and refinement use **MLX**-accelerated models on the Neural Engine / GPU where applicable

**Both platforms**

- A microphone and enough RAM/VRAM for the models you select in Settings (roughly **~4 GB VRAM** on Windows when both ASR and refiner are loaded; Apple Silicon uses unified memory).

## 📋 Good to Know

- **VRAM usage (~4 GB when active)**: While running, Privox loads two AI models (voice-to-text and refiner) that consume approximately 4 GB of GPU VRAM. To free up VRAM for other applications, Privox includes a **VRAM Saver** feature that automatically unloads the models after a period of inactivity. The models will reload automatically the next time you press your hotkey.
- **Very short sentences may not be refined**: To prevent hallucination, Privox will skip AI grammar correction if your spoken input is very short (roughly a few words). The original transcription will be typed out as-is. This is a deliberate safety measure to ensure quality output.

## ⚠️ Known Limitations

- **Non-English ASR models are not fully tested**: Privox includes several language-specific voice-to-text models (Cantonese, Korean, Japanese, French, German, Hindi, and Multilingual). While they should work well, I have not been able to personally test every language. If you encounter issues with a specific language model, please [open an Issue](https://github.com/markyip/Privox/issues)—your feedback helps improve support for everyone.
- **Accent variations may affect transcription accuracy**: The voice-to-text engine can be sensitive to strong or regional accents, which is an inherent limitation of the underlying ASR technology. If transcription quality seems off, try switching to a different ASR model in **Settings** (e.g., the Multilingual model may handle diverse accents better).
- **Occasional LLM hallucination**: Although multiple safeguards are in place, the refiner model may occasionally add, rephrase, or embellish words beyond the original transcript. We are continuously working on tighter controls to limit the model from slipping into an "assistant" role. If you notice output that doesn't match what you said, please report it.
- **Mixed-language sentences are not supported**: Privox works best when you speak in a single language per recording. Mixing two languages within the same sentence (e.g., switching between English and Cantonese mid-sentence) may produce unexpected results.

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

### Adding Your Own AI Models

You can add custom ASR (voice-to-text) or LLM (refiner) models by editing `src/models_config.py`.

**To add a new voice-to-text model**, append an entry to `ASR_LIBRARY`:

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
> On **Windows**, ASR models are typically used with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2 format). On **macOS**, the app prefers **MLX**-format repos from the `mlx_repo` fields in `models_config.py`. For **Qwen ASR** on Mac, use the **MLX** backend (`mlx_qwen_asr`) in settings—the PyTorch `qwen-asr` stack is not shipped in the Apple Silicon Pixi environment because it conflicts with the `mlx-lm` / `transformers` versions required for the refiner.

**To add a new refiner (LLM) model**, append an entry to `LLM_LIBRARY`:

```python
{
    "name": "My Custom LLM",
    "repo_id": "username/my-custom-llm-GGUF",
    "file_name": "my-custom-llm-Q4_K_M.gguf",
    "prompt_type": "llama",  # Use "llama" for chat models or "t5" for seq2seq
    "description": "A short description of this model."
}
```

> [!NOTE]
> LLM models must be in GGUF format and hosted on [Hugging Face](https://huggingface.co). Privox will download them automatically on first use.

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

## 🧩 Development (Pixi)

The repo uses [Pixi](https://pixi.sh/) with **two lock platforms**: `win-64` and `osx-arm64`. There is **no** `osx-64` (Intel Mac) environment—develop and build the Mac app on Apple Silicon only.

```bash
pixi install
pixi run start          # run voice_input.py
pixi run build          # PyInstaller bundle (Windows → .exe, macOS → Privox.app)
```

**macOS DMG (testing / distribution)**

From the project root (where `build_dmg.sh` lives):

```bash
./build_dmg.sh
```

The script expects a valid `dist/Privox.app` (run `pixi run build` first if needed). It re-signs the staged app, adds an **Applications** shortcut, and runs `hdiutil` to produce `Privox.dmg`.

Useful environment variables:

| Variable | Purpose |
|----------|---------|
| `PRIVOX_MIN_FREE_GB` | Minimum free disk GiB before packaging (default `12`; lower e.g. to `5` only if you understand peak usage during copy/DMG creation) |
| `PRIVOX_SIGNING_IDENTITY` | Apple **Developer ID Application** identity for stable signing (instead of ad hoc `-`) |
| `PRIVOX_NOTARY_PROFILE` | `notarytool` keychain profile name to submit and staple the DMG |

## 📄 A Note on Usage

Privox is free for your **Personal & Research use**. Commercial or business use is not allowed without permission. See the [LICENSE](LICENSE) file for more details.

## 📧 Contact

For issues, questions, or suggestions, please open an issue on GitHub.
