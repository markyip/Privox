# Privox Project Roadmap 🚀

This document tracks planned features, experimental ideas, and pending improvements for the Privox AI Assistant.

## 📋 High Priority (Next Steps)

- [ ] **Settings GUI**: Move away from manual `config.json` editing to a dedicated settings window.
- [ ] **Status Indicator Improvements**: Add a clearer visual overlay (HUD) to show when the app is listening vs. processing.
- [ ] **One-Click Update**: Implement a button to trigger `git pull` and environment refresh from within the app.
- [ ] **Auto-Launch on Startup**: Option to add Privox to Windows startup registry.

## ✨ Feature Ideas (Roadmap)

- [ ] **Smart Command Mode**: Fully activate the "Privox..." wake-word to execute system commands (e.g., "Privox, open Chrome").
- [ ] **Contextual Memory**: Allow Llama to remember the last few transcriptions for better corrections.
- [ ] **App-Specific Prompts**: Automatically switch dictation prompts based on the active window (e.g., formal for Outlook, casual for WhatsApp).
- [ ] **Multi-Model Support**: Quick toggle between different LLM sizes (e.g., 1B for speed, 8B for high-quality writing).
- [ ] **Offline Knowledge Base**: Local RAG (Retrieval-Augmented Generation) for searching previous voice notes.

- [x] **Path Resolution Fix**: Unified all paths to use `BASE_DIR`, ensuring portability across custom install directories.
- [ ] **Binary Installer (MSI/EXE)**: Create a more standard Windows installer package (Inno Setup or WiX).
- [ ] **Plugin System**: Allow users to add custom modules for specific transcription tasks.
- [ ] **Mac/Linux Support**: Port the bootstrap and audio logic to other platforms.

## 🌐 Language & Dictation Focus

- [x] **General Language Support**: Optimized prompts for standard English and multilingual dictation (fixing grammar, spelling, and flow).
- [ ] **Cantonese & Kongish (Future)**: Re-integrate specialized Cantonese handling when switching back to ultra-low latency or fine-tuned models.

- [x] **SenseVoiceSmall Integration**: Implemented as an alternative backend for ultra-low latency. Toggle via `config.json`.
- [ ] **Long Sentence Optimization**: Research and improve handling of long Cantonese sentences (currently prone to context drift vs. English).
- [ ] **Cantonese SLM**: Fine-tune a Small Language Model (SLM) specifically on Hong Kong chat data.
- [ ] **Traditional Chinese Punctuation Refinement**: Further tune the prompt for HK-style punctuation (e.g., using 「」 instead of "").
- [ ] **Audio Denoising**: Filter out Hong Kong background noise (MTR, traffic) before sending to Whisper.

---

_Got a new idea? Add it to this list!_
