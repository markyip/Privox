# Privox 🎙️

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Noncommercial-green.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows-blue?logo=windows)
![Downloads](https://img.shields.io/github/downloads/markyip/Privox/total)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Donate-orange?logo=buy-me-a-coffee)](https://www.buymeacoffee.com/markyip)

**Stop typing, start speaking.**

Privox is a powerful, private, and local voice input assistant for Windows. It captures your speech, transcribes it using **Faster-Whisper**, and refines the text using **Llama 3** for perfect grammar and formatting—instantly typing the result into any application.

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

1. Download **Privox.exe** from our [Releases](https://github.com/markyip/Privox/releases) page.
2. Run the program and follow the simple on-screen instructions.
3. On your first run, Privox will take a few minutes to set up its "AI Brains"—then you're ready to go!

### 2. How to Use

- **Tap your hotkey** (default: `F8`): The app starts listening (you'll see a small animation in your taskbar).
- **Just Talk**: Speak naturally, as if you were talking to a friend.
- **Tap your hotkey again**: Stop talking and watch your words appear on the screen, perfectly polished!

> [!TIP]
> **Your Hotkey, Your Way**: Don't like `F8`? You can change it to any key or combination (like `Ctrl+Shift+Space`) in **Settings**. Open Settings by right-clicking the Privox icon in your taskbar.

## ⚙️ Simple Controls

You don't need to be a computer expert to customize Privox. Just right-click the **Privox icon** near your clock (the system tray):

- **Settings**: Change your hotkey, your writing style, or which language you want to use.
- **Run at Startup**: Have Privox ready for you as soon as you turn on your computer.

## 🖥️ What You Need

- **Windows 10 or 11**.
- **A bit of space**: About **15GB** of space for the high-quality AI models.
- **Modern Hardware**: Works best on computers with an NVIDIA graphics card, but also runs on most modern desktop and laptop PCs.

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
> ASR models must be compatible with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2 format).

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

## 📄 A Note on Usage

Privox is free for your **Personal & Research use**. Commercial or business use is not allowed without permission. See the [LICENSE](LICENSE) file for more details.

## 📧 Contact

For issues, questions, or suggestions, please open an issue on GitHub.
