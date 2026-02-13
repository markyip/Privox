# Privox v1.0.0 - Initial Release

Privox is a private, local-first voice input assistant for Windows that transcribes your speech and intelligently refines it using state-of-the-art AI models.

## Core Functionality

### 🎙️ High-Speed Transcription

- Powered by **Faster-Whisper (Distil-Large-v3)**.
- Full multilingual support (Traditional Chinese/Cantonese, Mandarin, English, etc.).
- Robust audio processing with parallel model loading for near-instant wake-up.

### ✍️ Intelligent Text Refinement

- Uses **Llama-3.2-3B-Instruct** for grammar correction and perfect formatting.
- **Text Editor Persona**: The AI focuses solely on polishing your dictation—no conversational filler or back-and-forth questions.
- Customizable prompts to fit your personal writing style.

### 🛠️ Effortless Local Setup

- **Smart Installer (`bootstrap.py`)**:
  - Automatically manages portable Python environments and GPU/CUDA dependencies.
  - Supports **Custom Installation Paths** (install to D: drive, external disks, etc.).
  - **Smart Model Merge**: Preserves large assets (Whisper blobs) during reinstalls/updates to save bandwidth.

### ✨ Premium UX Features

- **Auto-Stop**: Intelligent silence detection (10s) automatically stops recording.
- **VRAM Saver**: Models are auto-unloaded after 60s of inactivity to free up system resources.
- **Clipboard Fallback**: Transcribed text stays on the clipboard even after pasting, ensuring your data is never lost.
- **Clean Audio Feedback**: High-stability, serialized beep notifications (serialized to prevent distortion).
- **Proactive Privacy**: Local-only, optional file logging, and automatic cleanup of debug traces.

## System Requirements

- **OS**: Windows 10/11.
- **GPU**: NVIDIA GPU (CUDA 12+) recommended for maximum performance.
- **Disk**: ~4GB free space for models and local runtime.

---

_Privox: Speak your mind, let AI do the typing._
