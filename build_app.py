import os
import site
import platform
import shutil
import subprocess
import sys
from glob import glob

print(f"Starting PyInstaller Build for {sys.platform}...")

is_mac = sys.platform == 'darwin'
icon_path = 'assets/privox.icns' if is_mac else 'assets/privox.ico'
is_clean_build = os.environ.get("PRIVOX_BUILD_CLEAN", "0") == "1"
min_free_gb = int(os.environ.get("PRIVOX_MIN_FREE_GB", "12"))

free_bytes = shutil.disk_usage(".").free
min_free_bytes = min_free_gb * (1024 ** 3)
if free_bytes < min_free_bytes:
    free_gb = free_bytes / (1024 ** 3)
    raise RuntimeError(
        f"Insufficient free space for build: {free_gb:.1f} GiB available, "
        f"requires at least {min_free_gb} GiB. "
        "Free disk space or set PRIVOX_MIN_FREE_GB to a lower value."
    )

# Fast path by default: avoid full clean to reduce packaging time.
# Set PRIVOX_BUILD_CLEAN=1 for a full clean rebuild.
if is_clean_build:
    if os.path.exists('build'):
        shutil.rmtree('build', ignore_errors=True)
    if os.path.exists('dist'):
        shutil.rmtree('dist', ignore_errors=True)
else:
    if is_mac:
        app_bundle = os.path.join('dist', 'Privox.app')
        app_folder = os.path.join('dist', 'Privox')
        build_folder = os.path.join('build', 'Privox')
        if os.path.exists(build_folder):
            shutil.rmtree(build_folder, ignore_errors=True)
        if os.path.exists(app_folder):
            shutil.rmtree(app_folder, ignore_errors=True)
        if os.path.exists(app_bundle):
            shutil.rmtree(app_bundle, ignore_errors=True)
    else:
        exe_path = os.path.join('dist', 'Privox.exe')
        if os.path.exists(exe_path):
            os.remove(exe_path)

# If compiling on mac and the icns isn't available, fallback to png
if is_mac and not os.path.exists(icon_path):
    icon_path = 'assets/icon.png'

pyinstaller_args = [
    'src/mac_launcher.py' if is_mac else 'src/bootstrap.py',
    '--name=Privox',
    '--onefile' if not is_mac else '--onedir', # macOS bundle is better as onedir (.app)
    '--windowed' if is_mac else '--noconsole', # macOS specific flag for .app bundles
    '--noconfirm',
    '--noupx', 
    f'--icon={icon_path}',
    '--add-data=assets:assets' if is_mac else '--add-data=assets;assets',
    '--add-data=src/voice_input.py:src' if is_mac else '--add-data=src/voice_input.py;src',
    '--add-data=src/download_models.py:src' if is_mac else '--add-data=src/download_models.py;src',
    '--add-data=src/gui_settings.py:src' if is_mac else '--add-data=src/gui_settings.py;src',
    '--add-data=src/models_config.py:src' if is_mac else '--add-data=src/models_config.py;src',
    '--add-data=src/silero_vad_onnx.py:src' if is_mac else '--add-data=src/silero_vad_onnx.py;src',
    '--add-data=pixi.toml:.' if is_mac else '--add-data=pixi.toml;.',
    '--add-data=pixi.lock:.' if is_mac else '--add-data=pixi.lock;.',
    '--add-data=uninstall.bat:.' if is_mac else '--add-data=uninstall.bat;.',
    '--add-data=config.json:.' if is_mac else '--add-data=config.json;.',
    '--version-file=version_info.txt' if not is_mac else '',
    '--manifest=assets/privox.manifest' if not is_mac else '',

    
    # Explicit Exclusions (Heavy Libs handled by Bootstrap)
    '--exclude-module=torch',
    '--exclude-module=torchaudio',
    '--exclude-module=torchvision',
    '--exclude-module=nvidia',
    '--exclude-module=caffe2',
    '--exclude-module=triton',
    '--exclude-module=matplotlib',
    '--exclude-module=pandas',
    '--exclude-module=scipy',
    '--exclude-module=transformers', 
    '--exclude-module=faster_whisper',
    '--exclude-module=ctranslate2',
    '--exclude-module=tokenizers',
    '--exclude-module=onnxruntime',
    '--exclude-module=llama_cpp', 
    '--exclude-module=mlx_lm',
    '--exclude-module=mlx',
    '--exclude-module=PIL',
    '--exclude-module=pystray',
    '--exclude-module=sounddevice',
    '--exclude-module=pynput',
    '--exclude-module=pyperclip',
    '--exclude-module=huggingface_hub',
]

if is_clean_build:
    pyinstaller_args.append('--clean')

# Remove empty placeholders from platform-specific conditional args.
pyinstaller_args = [arg for arg in pyinstaller_args if arg and arg.strip()]

renamed_optional_bins = []


def disable_optional_media_binaries():
    if not is_mac:
        return
    if os.environ.get("PRIVOX_PRUNE_OPTIONAL_MEDIA", "1") != "1":
        return

    torio_lib_dir = os.path.join(
        ".pixi", "envs", "default", "lib", "python3.12",
        "site-packages", "torio", "lib"
    )
    if not os.path.isdir(torio_lib_dir):
        return
    disabled_store = os.path.join(".pixi", "envs", "default", ".privox_disabled_bins")
    os.makedirs(disabled_store, exist_ok=True)

    patterns = ("*ffmpeg*.so", "*sox*.so")
    for pattern in patterns:
        for path in glob(os.path.join(torio_lib_dir, pattern)):
            filename = os.path.basename(path)
            disabled_path = os.path.join(disabled_store, filename)
            if os.path.exists(disabled_path):
                continue
            os.rename(path, disabled_path)
            renamed_optional_bins.append((disabled_path, path))

    if renamed_optional_bins:
        print(
            f"Temporarily disabled {len(renamed_optional_bins)} optional "
            "torio ffmpeg/sox binaries to speed up analysis."
        )


def restore_optional_media_binaries():
    for disabled_path, original_path in reversed(renamed_optional_bins):
        if os.path.exists(disabled_path):
            os.rename(disabled_path, original_path)


def _remove_path(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)
        return True
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError:
            return False
    return False


def _site_packages_dirs(env_root):
    lib_root = os.path.join(env_root, "lib")
    for pydir in ("python3.12", "python3.11", "python3.10"):
        site = os.path.join(lib_root, pydir, "site-packages")
        if os.path.isdir(site):
            yield site


def prune_pixi_bundle_for_mac(env_root):
    """Remove dev-only and unused Mac runtime files from the bundled Pixi env."""
    if not is_mac:
        return
    if os.environ.get("PRIVOX_PRUNE_BUNDLED_PIXI", "1") != "1":
        print("Skipping bundled .pixi pruning (PRIVOX_PRUNE_BUNDLED_PIXI=0).")
        return

    removed = 0
    lib_root = os.path.join(env_root, "lib")

    # Headers, docs, metadata, tests, caches, and bytecode are not needed at runtime.
    for path in (
        os.path.join(env_root, "include"),
        os.path.join(env_root, "share", "man"),
        os.path.join(env_root, "share", "doc"),
        os.path.join(env_root, "share", "info"),
    ):
        if _remove_path(path):
            removed += 1

    if os.path.isdir(lib_root):
        for pattern in ("**/__pycache__", "**/*.pyc", "**/*.pyo", "**/*.a"):
            for path in glob(os.path.join(lib_root, pattern), recursive=True):
                if _remove_path(path):
                    removed += 1

    for site in _site_packages_dirs(env_root):
        for name in os.listdir(site):
            pkg_dir = os.path.join(site, name)
            if name in ("test", "tests") and _remove_path(pkg_dir):
                removed += 1
                continue
            if not os.path.isdir(pkg_dir):
                continue
            for sub in ("test", "tests", "__pycache__"):
                if _remove_path(os.path.join(pkg_dir, sub)):
                    removed += 1

    # The Mac app uses Swift for UI/hotkey/paste and MLX/ONNX for the runtime path.
    # Keep this list conservative: remove the largest stacks that are unused by
    # the bundled macOS app, while preserving MLX, ONNX Runtime, and downloader deps.
    unused_mac_pkgs = (
        "PySide6",
        "PySide6_Addons",
        "PySide6_Essentials",
        "shiboken6",
        "customtkinter",
        "torch",
        "torchaudio",
        "torchvision",
        "torchgen",
        "functorch",
        "faster_whisper",
        "funasr",
        "modelscope",
    )
    for site in _site_packages_dirs(env_root):
        for pkg in unused_mac_pkgs:
            patterns = (
                pkg,
                pkg.replace("_", "-"),
                f"{pkg}-*.dist-info",
                f"{pkg}_*.dist-info",
                f"{pkg}*.dist-info",
                f"{pkg.lower()}-*.dist-info",
                f"{pkg.lower()}_*.dist-info",
                f"{pkg.lower()}*.dist-info",
                f"{pkg}-*.egg-info",
                f"{pkg.lower()}-*.egg-info",
            )
            for pattern in patterns:
                for path in glob(os.path.join(site, pattern)):
                    if _remove_path(path):
                        removed += 1

    print(f"Pruned {removed} items from bundled .pixi environment.")


def copy_pixi_runtime_env_into_bundle():
    if not is_mac:
        return
    source_env = os.path.join(".pixi", "envs", "default")
    target_env = os.path.join(
        "dist", "Privox.app", "Contents", "Resources", ".pixi", "envs", "default"
    )
    if not os.path.isdir(source_env):
        raise RuntimeError(f"Missing runtime environment: {source_env}")
    if os.path.exists(target_env):
        shutil.rmtree(target_env, ignore_errors=True)
    print("Copying pixi runtime environment into app bundle...")
    shutil.copytree(source_env, target_env, symlinks=True)
    print("Pruning bundled .pixi environment for macOS runtime...")
    prune_pixi_bundle_for_mac(target_env)


try:
    disable_optional_media_binaries()
    PyInstaller.__main__.run(pyinstaller_args)
finally:
    restore_optional_media_binaries()

import plistlib


def compile_mac_swift_settings_helper():
    """SwiftUI binary launched by the PyInstaller app for Settings (avoids Qt gui_settings)."""
    helper = os.path.join("dist", "Privox.app", "Contents", "MacOS", "PrivoxSwiftUI")
    source_dir = "src/mac_app"
    if not os.path.isdir(source_dir):
        print("Warning: src/mac_app missing; skipping PrivoxSwiftUI.")
        return
    swift_files = sorted(
        os.path.join(source_dir, f)
        for f in os.listdir(source_dir)
        if f.endswith(".swift")
    )
    if not swift_files:
        print("Warning: no Swift sources in src/mac_app; skipping PrivoxSwiftUI.")
        return
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        swift_target = "arm64-apple-macosx13.0"
    elif machine in ("x86_64", "amd64", "i386"):
        swift_target = "x86_64-apple-macosx13.0"
    else:
        swift_target = "arm64-apple-macosx13.0"
    cmd = ["swiftc", "-parse-as-library", "-target", swift_target, *swift_files, "-o", helper]
    try:
        subprocess.run(cmd, check=True)
        os.chmod(helper, 0o755)
        print(f"Built SwiftUI settings helper: {helper}")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(
            f"Warning: could not build PrivoxSwiftUI ({exc}). "
            "Install Xcode Command Line Tools; Settings will fall back to Qt until fixed."
        )


def codesign_dist_mac_app():
    app_path = os.path.join("dist", "Privox.app")
    if not os.path.isdir(app_path):
        return
    identity = os.environ.get("PRIVOX_SIGNING_IDENTITY", "-").strip() or "-"
    sign_cmd = ["codesign", "--force", "--deep", "--sign", identity]
    if identity != "-":
        sign_cmd.extend(["--options", "runtime", "--timestamp"])
    entitlements = "assets/entitlements.plist"
    if os.path.exists(entitlements):
        sign_cmd.extend(["--entitlements", entitlements])
    sign_cmd.append(app_path)
    try:
        subprocess.run(sign_cmd, check=True)
        subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", "--verbose=2", app_path],
            check=True,
        )
        print("Re-signed dist/Privox.app (includes PrivoxSwiftUI).")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Warning: codesign on dist/Privox.app failed ({exc}).")


if is_mac:
    copy_pixi_runtime_env_into_bundle()
    print("Injecting macOS Privacy Permissions into Info.plist...")
    plist_path = 'dist/Privox.app/Contents/Info.plist'
    if os.path.exists(plist_path):
        try:
            with open(plist_path, 'rb') as f:
                plist = plistlib.load(f)
            
            # Add required privacy descriptions for macOS
            plist['NSMicrophoneUsageDescription'] = "Privox needs microphone access to listen to your speech and transcribe it."
            plist['NSAccessibilityUsageDescription'] = "Privox needs accessibility access to detect your global activation hotkey across all applications."
            # Stable bundle id helps TCC (Accessibility / Input Monitoring) map the same app across updates
            # when code signing identity is consistent. Matches build_mac_app.py.
            plist['CFBundleIdentifier'] = "ai.privox.app"
            
            # Optional: Hide dock icon since we rely on Menu Bar (LSUIElement)
            plist['LSUIElement'] = True
            
            with open(plist_path, 'wb') as f:
                plistlib.dump(plist, f)
            print("Successfully injected privacy strings and LSUIElement into Info.plist.")
        except Exception as e:
            print(f"Error modifying Info.plist: {e}")

    compile_mac_swift_settings_helper()
    codesign_dist_mac_app()

    print("Build Complete. Application bundle is in 'dist/Privox.app'")
else:
    print("Build Complete. Executable is in 'dist/Privox.exe'")
