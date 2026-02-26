# Privox v1.0.0 - Initial Release �

Privox is a powerful, private, and local voice input assistant for Windows. It captures your speech, transcribes it using Faster-Whisper, and refines the text using Llama 3 for perfect grammar and formatting.

## ✨ Key Features

### 🎙️ High-Precision Transcription

- **Faster-Whisper Engine**: Blazing fast transcription using the latest AI models.
- **True Multilingual Support**: Specialized logic for English, Cantonese, Traditional Chinese, Japanese, Korean, and more.
- **Intelligent LID (Language Detection)**: Automatically identifies the language you are speaking with high-confidence safety thresholds.
- **Optimized Performance**: Parallel model loading and optimized wake-up sequences ensure minimal latency when starting or resuming from idle.

### ✍️ Intelligent Refinement

- **Smart Refiner**: Uses Llama-3.2-3B to polish your speech into grammatically perfect text while removing filler words like "uh" and "um".
- **Hallucination Safeguards**: Multi-layered protection prevents the AI from adding unintended text or "hallucinating" on short inputs.
- **Anti-Assistant Protection**: Persona guards ensure the AI stays focused on refining your text rather than acting as a chatbot.
- **Clean Output**: Automatic meta-commentary stripping removes trailing AI "notes" or internal explanations.
- **Custom Personas**: Choose how Privox writes—act like a Technical Writer, Engineer, or Lawyer with a single click.

### �️ Private & Secure

- **100% Local**: All processing happens on your computer. Your privacy is guaranteed.
- **Privacy-First Logging**: User text and refined output are never written to logs—only diagnostic metadata is tracked.
- **Legitimacy Metadata**: Embedded Windows Version Info and application manifests reduce false-positive flags from antivirus software.
- **Smart Auto-Stop**: Advanced silence detection and safety timers ensure the microphone stops recording when you do.

### ✍️ Premium Experience

- **Liquid Glass UI**: A clean, monotone aesthetic with centered progress updates and professional typography.
- **One-Key Magic**: Single hotkey operation for seamless start/stop recording.

## 🛠️ Effortless Local Setup

- **Smart Installer (`bootstrap.py`)**: Automatically manages portable Python environments and GPU/CUDA dependencies.
- **GPU Orchestration**: Built-in support for NVIDIA GPUs with automatic fallback and repair for CPU mode.
- **Disk Safety**: Verifies space and system requirements before downloading large AI assets.

## 🖥️ System Requirements

- **OS**: Windows 10/11.
- **GPU**: NVIDIA GPU (CUDA 12+) recommended; CPU support available.
- **Disk**: ~15GB free space for the high-quality local AI "brains".

---

_Privox: Your voice, perfectly written._
