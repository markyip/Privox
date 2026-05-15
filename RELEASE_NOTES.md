# Privox Release Notes

## v1.1 (Windows Experience Update)

**Release date:** 2026-05-15

This update focuses on making Privox faster, more reliable, and easier to use on Windows. We've combined several recent improvements into this single "v1.1" release to ensure the best experience for all users.

### 🚀 Performance & Speed
- **Lightning Fast AI**: We've optimized the app to take full advantage of modern NVIDIA graphics cards (including the RTX 40 and 50 series). This allows the AI to process your speech almost instantly without slowing down your computer.
- **Smoother Transcription**: The system is now much more efficient at turning your voice into text, providing a snappier feel especially on newer hardware.

### 🛠️ Reliability & "Just Works"
- **Fixed Startup Issues**: We resolved a common technical problem that caused the app to occasionally fail to start on certain Windows systems. It should now launch reliably every time.
- **Better Typing & Pasting**: When you finish speaking, Privox is now smarter about finding your active window and pasting your text exactly where your cursor is.
- **Modern AI Engine**: Upgraded core transcription engine (llama-cpp-python) to **v0.3.23**, enabling official Windows binary support and faster, more stable AI operations.
- **Cleaner Installation**: The app now does a better job of keeping your computer tidy by automatically cleaning up temporary background files.
- **Refined Installer UI**: Unified fonts and styling across the installer, and implemented correct taskbar icon association for a more professional look.
- **Improved Hotkey Reliability**: Implemented physical key-state verification to prevent the hotkey from getting "stuck" or missed during high system load.
- **Pre-warm Models**: Added a new "Pre-warm Models on Startup" feature (enabled by default) so the AI is ready to transcribe instantly without a first-use delay.

### 🛡️ Privacy & Security
- **Strictly Local**: We've further enhanced our privacy protections to ensure that your dictation never leaves your computer.
- **Silent & Unobtrusive**: The app now runs more smoothly in the background, keeping itself out of your way while you work.
