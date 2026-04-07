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
*   **Pixi platforms:** Developer environments are locked for **`win-64`** and **`osx-arm64` only**. **Intel Mac (`osx-64`) is not supported**—use Apple Silicon to develop or build the Mac app.
*   **Leaner Apple Silicon env:** Heavy Windows-only stacks (e.g. faster-whisper / funasr / modelscope) are not installed on `osx-arm64`, reducing `.pixi` size; Mac builds rely on **MLX** + **onnxruntime** for the default paths.
*   **Native App Icon:** The `.dmg` packaging process injects the custom `Privox` icon using native Swift commands.

**Build commands (reference)**

- macOS app bundle: `pixi run build` (runs `build_app.py` / PyInstaller).
- DMG: `./build_dmg.sh` (after `dist/Privox.app` exists). Optional: `PRIVOX_MIN_FREE_GB`, `PRIVOX_SIGNING_IDENTITY`, `PRIVOX_NOTARY_PROFILE`.

### 🐛 Bug Fixes
*   Fixed a critical issue on macOS where the audio buffer returned silent `0.00 RMS` arrays due to Apple's TCC Sandbox improperly caching PyInstaller bundles.
*   Fixed path resolution issues where `Privox.app` would crash inside a `.dmg` by forcing `DYLD_LIBRARY_PATH` explicitly in `mac_launcher.py`.
