# Privox

A powerful, private, and local voice input assistant for Windows. Privox captures your speech, transcribes it using **Faster-Whisper**, and refines the text using **Llama 3** for perfect grammar and formatting.

> [!WARNING]
> **Disk Space Requirement**: This application requires approximately **15GB** of free disk space for the AI models and portable environments.
>
> **Why so large?** Privox runs completely locally to ensure your privacy. This means it bundles:
>
> 1.  **AI Models**: High-quality speech recognition (Whisper) and text refinement (Llama 3) models (~13GB total).
> 2.  **GPU Drivers**: NVIDIA CUDA libraries bundled via Pixi to ensure performance.
> 3.  **Portable Runtime**: A dedicated Pixi environment to avoid system conflicts.

## Features

- **High-Accuracy Transcription**: Powered by `faster-whisper` (Distil-Large-v3).
- **Multilingual Support**: Supports English, Traditional Chinese (Cantonese), Mandarin, Japanese, Korean, and many European languages.
- **Intelligent Formatting**: Uses `Llama-3.2-3B-Instruct` to fix grammar, punctuation, and format lists automatically.
- **Strict Editing Mode**: Optimized to polish text without conversational filler or answering questions.
- **Auto-Stop**: Automatically stops recording after **10 seconds** of silence.
- **Disk Safety**: Built-in verification to ensure sufficient storage before installation.
- **VRAM Saver**: Dynamically unloads AI models from memory after 60 seconds of inactivity.
- **Pixi Orchestration**: Isolated dependencies and CUDA management for high reliability.

## Requirements

- **OS**: Windows 10/11
- **GPU**: NVIDIA GPU with CUDA support (Recommended for speed).
  - _Note: Llama 3 can run on CPU, but GPU is faster._
- **Python**: 3.10 - 3.12 (if running from source)

## Installation

### For Users

1. Download the latest `Privox.exe` from the Releases page.
2. Run the installer and follow the GUI prompts.
3. The installer will automatically set up the environment and models.

### For Developers

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/markyip/Privox.git
    cd Privox
    ```
2.  **Install Pixi** (if not already installed): [https://pixi.sh/](https://pixi.sh/)
3.  **Initialize Environment:**
    ```bash
    pixi run start
    ```

## Usage

### Running from Source

```bash
# Recommended: Automatic setup and launch
python src/bootstrap.py

# Advanced: Direct launch (requires manual dependency/model setup)
python src/voice_input.py
```

### Hotkeys

- **F8** (Default): Toggle recording.
  - _Press once to start listening, press again to stop._
- **Dictation Mode**: Just speak normally, and Privox will type the corrected text into your active window.

### System Tray

- **Right-click** the cyan Privox icon in the system tray to:
  - **Run at Startup**: Toggle auto-launch.
  - **Reconnect Audio**: Restart the microphone stream if issues occur.
  - **Exit**: Close the application.

## Offline Mode / Manual Model Loading

If you cannot access Hugging Face or prefer to use a local model file:

1.  **Create a folder** named `models` in the same directory as `Privox.exe` (or `src/voice_input.py`).
2.  **Download the model file:**
    - [Llama-3.2-3B-Instruct-Q4_K_M.gguf](https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf?download=true)
3.  **Place the file** inside the `models` folder.
4.  **Launch Privox**. It will detect the local file and skip the download.

### Building the Executable

To create a standalone `.exe` file (the "Installer"):

1.  Run the Pixi build task:

    ```bash
    pixi run build
    ```

2.  The output executable will be located in `dist/Privox.exe`.

### How it works

Privox uses a **Bootstrap** architecture. The `.exe` you build is a lightweight launcher that:

1.  Provides a GUI to select an installation path.
2.  Self-extracts into that path.
3.  Downloads **Pixi** and sets up the heavy AI environment locally on the user's machine.
4.  Downloads the **AI Models** (Llama 3 & Whisper).

This ensures the initial download is small (~12MB) while providing a robust, isolated environment for the user.

### Advanced: CPU-Only Build

If you want a smaller executable (removing NVIDIA drivers) for non-GPU machines:

1.  Run `scripts/switch_to_cpu_torch.bat` to install lightweight PyTorch.
2.  Run `scripts/build_windows_cpu.bat`.

## Configuration

Privox uses a `config.json` file for customization. When running as an `.exe`, placed this file in the **same directory** as `Privox.exe`.

| Parameter            | Default                 | Description                                                                          |
| :------------------- | :---------------------- | :----------------------------------------------------------------------------------- |
| `hotkey`             | `"f8"`                  | Single key (e.g., `"f8"`, `"space"`) or combinations (e.g., `"ctrl+1"`, `"alt+f8"`). |
| `sound_enabled`      | `true`                  | Enables/disables start and stop beeps.                                               |
| `vram_timeout`       | `60`                    | Seconds of inactivity before AI models are unloaded from VRAM.                       |
| `whisper_model`      | `"distil-large-v3"`     | Faster-Whisper model size.                                                           |
| `auto_stop_enabled`  | `true`                  | Automatically stop recording after silence.                                          |
| `silence_timeout_ms` | `10000`                 | Milliseconds of silence before auto-stop.                                            |
| `grammar_repo`       | (Llama 3.2)             | HuggingFace repository for the formatting model.                                     |
| `grammar_file`       | (GGUF)                  | Specific GGUF file to use.                                                           |
| `dictation_prompt`   | (Default System Prompt) | Custom system prompt. Use `{dict}` to insert custom dictionary hints.                |
| `custom_dictionary`  | `[...]`                 | List of words to help the AI recognize specific names/terms.                         |

> [!TIP]
> **Customizing Behavior**: You can change `dictation_prompt` to make Privox behave differently (e.g., "Summarize this spoken text into a single sentence").

> [!TIP]
> You do not need to rebuild the app after changing `config.json`. Simply restart Privox to apply new settings.

## Memory Management (VRAM Saver)

Privox is designed to be resource-friendly.

- **Active**: Uses ~2-4GB VRAM (depending on models).
- **Idle**: Unloads models after 60s, dropping VRAM usage to near zero.

## Troubleshooting

- **Logs**: By default, Privox does not write logs to files to keep your directory clean. If you encounter issues, you can enable logging by setting the environment variable `PRIVOX_DEBUG=1` before running. This will generate `privox_app.log` (app) or `privox_setup.log` (installer).
- **Audio Issues**: Use the "Reconnect Audio" tray option.
- **GPU Not Used**: Ensure CUDA is installed and `torch.cuda.is_available()` returns True.

## Known Issues

- **Language Mixing**: Privox currently cannot effectively handle mixing multiple languages (e.g., English and Chinese) within the same sentence. It is optimized for one primary language at a time.
- **Formatting Predictability**: While we've introduced flexible formatting (paragraphs vs. bullet points), the model's decision is not always perfectly controllable or predictable with current prompts. We are experimenting with better system instructions to improve consistency.

## Roadmap

- [x] **Multi-language Support**: Add support for non-English transcription (Cantonese, Mandarin, etc.) and translation features.
- [x] **Auto-Stop Implementation**.
- [x] **Custom System Prompts**.
- [ ] **Lightweight Models**: Explore smaller models for faster execution and reduced storage requirements.
- [ ] **Simultaneous Multi-language Handling**: Investigate models that can effectively process multiple languages within the same sentence.
- [ ] **Tone Selection**: Explore building or integrating models that offer multiple tone options (e.g., sarcastic, polite, friendly).
- [ ] **Configuration GUI**: A standalone settings window to adjust hotkeys and models without editing `config.json`.
