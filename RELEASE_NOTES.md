# Privox v1.1.0 - Speed & Safety Update ⚡🛡️

This update focuses on making Privox faster, safer, and more robust against AI hallucinations while enhancing user privacy.

## ✨ New in v1.1.0

### 🚀 Performance & Responsiveness

- **Optimized Wake-up sequence**: Drastically reduced the time it takes for Privox to "wake up" after being idle. By caching imports and skipping redundant file checks, reloading models from VRAM Saver is now significantly faster.
- **Parallel Model Loading**: ASR and Refiner models now load simultaneously, cutting initial startup and wake-up times in half on multi-core systems.

### 🛡️ AI Safety & Reliability

- **Hallucination Safeguards**: Implemented a multi-layered protection system to prevent the AI from adding unintended text or "hallucinating" on very short or silent inputs.
- **Anti-Assistant Protection**: New "persona guards" prevent the LLM from slipping into an "assistant" role (answering questions, giving advice) and ensure it stays focused purely on refining your text.
- **Clean Meta-Commentary**: Added a dedicated stripper to remove LLM "chatter" (e.g., "Note: I've updated your grammar...") from results before they are typed into your apps.

### 🔒 Privacy-First Logging

- **Text Redaction**: For maximum privacy, user spoken text and refined output are no longer written to log files. Logs now only track metadata (character counts and timing) for diagnostic purposes while keeping your private thoughts private.

### 📦 System & Build Improvements

- **Legitimacy Metadata**: Embedded official Windows Version Info and application manifests into the executable. This reduces false-positive flags from antivirus software by clearly identifying Privox as a legitimate application.
- **Repo Cleanup**: Streamlined the repository by untracking internal agent artifacts, making it cleaner for contributors.

---

# Privox v1.0.0 - Initial Release 🚀

Privox is a private, local-first voice input assistant for Windows that transcribes your speech and intelligently refines it using state-of-the-art AI models.

## ✨ Key Features

### 🎙️ High-Precision Transcription

- **Faster-Whisper Engine**: Blazing fast transcription using the latest AI models.
- **True Multilingual Support**: Specialized logic for English, Cantonese, Traditional Chinese, Japanese, Korean, and more.
- **Intelligent LID (Language Detection)**: Automatically identifies which language you are speaking with high-confidence safety thresholds to prevent unintended translations.

### ✍️ Intelligent "Liquid Glass" Experience

- **Premium UI**: A clean, monotone "Liquid Glass" aesthetic with centered progress updates and professional typography.
- **Smart Refiner**: Uses Llama-3.2-3B to polish your speech into grammatically perfect text while removing filler words like "uh" and "um".
- **Custom Personas**: Choose how Privox writes—act like a Technical Writer, Engineer, or Lawyer with a single click.

### 🛡️ Robust & Private

- **100% Local**: All processing happens on your computer. Your privacy is guaranteed.
- **Smart Auto-Stop**: Advanced silence detection and safety timers ensure the microphone stops recording when you do.

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
