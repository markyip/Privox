# Release Notes

## [1.0.0] - Upcoming Release
This major release introduces full native support for **macOS (Apple Silicon)** alongside Windows, transforming Privox into a truly cross-platform local AI assistant!

### 🌟 New Features
*   **macOS Apple Silicon Support:** Privox now runs flawlessly on Mac using the hyper-optimized `mlx-whisper` backend for lightning-fast local transcription.
*   **Dual OS Input System:** 
    *   Added seamless support for macOS Accessibility APIs to control dictation via `Cmd+Opt+Z`.
    *   Windows continues to use `F8` as the global hotkey.
*   **Native Permissions Handling:** Added explicit macOS AVFoundation bridging to ensure the Microphone privacy prompt triggers correctly on the first launch.

### 🛠️ Build & Developer Improvements
*   **macOS DMG Packager:** A completely automated pipeline (`build_dmg.sh`) that bundles the heavy ML Python environments into a single, drag-and-drop macOS App.
*   **DMG Size Optimization:** Newly introduced stripping commands cut the final DMG size down from 1.3GB to under 1GB by removing unused Qt frameworks natively before packaging.
*   **All-in-One Mac Build Command:** Developers can now build a Gatekeeper-trusted DMG locally and auto-clean the massive 3GB+ `.pixi` environment with a single command: `pixi run build-mac`.
*   **Native App Icon:** The `.dmg` packaging process now injects the custom `Privox` icon using native Swift commands.

### 🐛 Bug Fixes
*   Fixed a critical issue on macOS where the audio buffer returned silent `0.00 RMS` arrays due to Apple's TCC Sandbox improperly caching PyInstaller bundles.
*   Fixed path resolution issues where `Privox.app` would crash inside a `.dmg` by forcing `DYLD_LIBRARY_PATH` explicitly in `mac_launcher.py`.
