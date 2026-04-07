import os
import platform
import subprocess
import shutil
import sys
import glob

# --- Build Configuration ---
APP_NAME = "Privox"
BUNDLE_ID = "ai.privox.app"
VERSION = "1.0.0"

SOURCE_DIR = "src/mac_app"
BUILD_DIR = "build_mac"
APP_DIR = f"{BUILD_DIR}/{APP_NAME}.app"
MACOS_DIR = f"{APP_DIR}/Contents/MacOS"
RESOURCES_DIR = f"{APP_DIR}/Contents/Resources"
ENTITLEMENTS_PATH = "assets/entitlements.plist"
SIGNING_IDENTITY = os.environ.get("PRIVOX_SIGNING_IDENTITY", "-").strip() or "-"
REQUIRE_STABLE_SIGNATURE = os.environ.get("PRIVOX_REQUIRE_STABLE_SIGNATURE", "0") == "1"
NOTARY_PROFILE = os.environ.get("PRIVOX_NOTARY_PROFILE", "").strip()


def is_ad_hoc_signature(identity: str) -> bool:
    return identity in {"", "-"}


def run_checked(cmd, description):
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"{description} failed: {exc}")
        sys.exit(1)


def apply_codesign(app_path: str):
    ad_hoc = is_ad_hoc_signature(SIGNING_IDENTITY)
    if REQUIRE_STABLE_SIGNATURE and ad_hoc:
        print("Error: PRIVOX_REQUIRE_STABLE_SIGNATURE=1 but PRIVOX_SIGNING_IDENTITY is not set.")
        sys.exit(1)

    codesign_cmd = ["codesign", "--force", "--deep", "--sign", SIGNING_IDENTITY]
    if not ad_hoc:
        codesign_cmd.extend(["--options", "runtime", "--timestamp"])
    if os.path.exists(ENTITLEMENTS_PATH):
        codesign_cmd.extend(["--entitlements", ENTITLEMENTS_PATH])
    codesign_cmd.append(app_path)

    run_checked(codesign_cmd, "Code signing")

    verification_cmd = ["codesign", "--verify", "--deep", "--strict", "--verbose=2", app_path]
    run_checked(verification_cmd, "Code signature verification")

    if ad_hoc:
        print("Applied ad-hoc code signature to app bundle.")
        print("Note: ad-hoc signing helps dev builds, but macOS privacy permissions may still reset across future updates.")
        print("Set PRIVOX_SIGNING_IDENTITY to a persistent Apple signing identity to keep a stable app identity.")
    else:
        print(f"Applied stable code signature using identity: {SIGNING_IDENTITY}")


def maybe_notarize_dmg(dmg_path: str):
    if not NOTARY_PROFILE:
        return

    print(f"Submitting DMG for notarization with profile: {NOTARY_PROFILE}")
    notarize_cmd = ["xcrun", "notarytool", "submit", dmg_path, "--keychain-profile", NOTARY_PROFILE, "--wait"]
    run_checked(notarize_cmd, "Notarization")

    staple_cmd = ["xcrun", "stapler", "staple", dmg_path]
    run_checked(staple_cmd, "Stapling notarization ticket")
    print("Notarization complete and stapled to DMG.")


def find_icon_source():
    candidates = [
        ("assets/icon.icns", "icon.icns", "icon"),
        ("assets/privox.icns", "icon.icns", "icon"),
        ("assets/icon.png", "icon.png", "icon.png"),
    ]

    for source_path, target_name, plist_icon_name in candidates:
        if os.path.exists(source_path):
            return {
                "source_path": source_path,
                "target_name": target_name,
                "plist_icon_name": plist_icon_name,
            }

    return None

# Keep the app bundle path stable across rebuilds so macOS privacy permissions
# are less likely to treat every dev build as a brand new application.
os.makedirs(MACOS_DIR, exist_ok=True)
os.makedirs(RESOURCES_DIR, exist_ok=True)

# --- 1. Generate Info.plist ---
icon_info = find_icon_source()
icon_plist_block = ""
if icon_info:
    icon_plist_block = f"""    <key>CFBundleIconFile</key>
    <string>{icon_info["plist_icon_name"]}</string>
"""

PLIST_CONTENT = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>{APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>{BUNDLE_ID}</string>
{icon_plist_block}    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>{APP_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>{VERSION}</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>LSUIElement</key>
    <true/> <!-- Runs as a Menu Bar Application, hides Dock icon initially -->
    
    <!-- Privacy Permissions needed for Privox -->
    <key>NSMicrophoneUsageDescription</key>
    <string>Privox needs microphone access to record your voice for transcription.</string>
    <key>NSSpeechRecognitionUsageDescription</key>
    <string>Privox needs speech recognition to transcribe your audio.</string>
    <key>NSAppleEventsUsageDescription</key>
    <string>Privox needs permission to paste transcribed text into your active window.</string>
</dict>
</plist>
"""

with open(f"{APP_DIR}/Contents/Info.plist", "w") as f:
    f.write(PLIST_CONTENT)

print("Created Info.plist with TCC Privacy Flags.")
if icon_info:
    print(f"Info.plist configured to use app icon: {icon_info['target_name']}")
else:
    print("Warning: no app icon asset found in assets/. Bundle icon metadata will be omitted.")

# --- 2. Compile Swift ---
print("Compiling Swift application...")

# Match host CPU: arm64 for Apple Silicon, x86_64 for Intel (hardcoding arm64 breaks Intel Macs).
_machine = platform.machine().lower()
if _machine in ("arm64", "aarch64"):
    _swift_target = "arm64-apple-macosx13.0"
elif _machine in ("x86_64", "amd64", "i386"):
    _swift_target = "x86_64-apple-macosx13.0"
else:
    print(f"Warning: unknown platform.machine()={_machine!r}; using arm64-apple-macosx13.0")
    _swift_target = "arm64-apple-macosx13.0"
print(f"Swift compile target: {_swift_target}")

# We expect src/mac_app/App.swift to exist. 
# We'll compile it into the MacOS directory of our app bundle.
swift_files = [os.path.join(SOURCE_DIR, f) for f in os.listdir(SOURCE_DIR) if f.endswith('.swift')]

if not swift_files:
    print(f"Error: No .swift files found in {SOURCE_DIR}")
    exit(1)

compile_cmd = [
    "swiftc",
    "-parse-as-library",
    "-target", _swift_target,
    *swift_files,
    "-o", f"{MACOS_DIR}/{APP_NAME}"
]

try:
    subprocess.run(compile_cmd, check=True)
    print(f"Successfully compiled {APP_NAME} to {MACOS_DIR}/{APP_NAME}")
except subprocess.CalledProcessError as e:
    print(f"Compilation failed: {e}")
    print("Hints: install Xcode Command Line Tools (xcode-select --install), ensure `swiftc` is on PATH,")
    print("  and on Intel Macs the build now uses x86_64-apple-macosx13.0 (not arm64).")
    exit(1)

# --- 3. Copy Assets ---
# Copy application icon if it exists
if icon_info:
    shutil.copy(icon_info["source_path"], f"{RESOURCES_DIR}/{icon_info['target_name']}")
    print(f"Copied app icon asset into bundle: {icon_info['target_name']}")
else:
    print("Skipping app icon copy because no icon asset is present.")

print(f"App Bundle created successfully at {APP_DIR}")

# --- 3b. Code signing ---
apply_codesign(APP_DIR)

def prune_pixi_bundle_for_mac(env_root: str) -> None:
    """Remove unnecessary files from the copied .pixi env to reduce DMG size.
    Safe for macOS runtime: we only remove headers, docs, caches, tests, and
    packages that are not used on the Mac MLX path (faster_whisper, funasr, modelscope,
    and heavy frameworks like PyTorch that the bundled app no longer depends on).
    """
    removed = 0

    # 1. Remove C/C++ headers (not needed at runtime)
    include_dir = os.path.join(env_root, "include")
    if os.path.isdir(include_dir):
        shutil.rmtree(include_dir, ignore_errors=True)
        removed += 1

    # 2. Remove share/man, share/doc
    for sub in ("man", "doc", "info"):
        d = os.path.join(env_root, "share", sub)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            removed += 1

    # 3. __pycache__ and *.pyc under lib
    lib_root = os.path.join(env_root, "lib")
    if os.path.isdir(lib_root):
        for pycache in glob.glob(os.path.join(lib_root, "**", "__pycache__"), recursive=True):
            if os.path.isdir(pycache):
                shutil.rmtree(pycache, ignore_errors=True)
                removed += 1
        for pyc in glob.glob(os.path.join(lib_root, "**", "*.pyc"), recursive=True):
            try:
                os.remove(pyc)
                removed += 1
            except OSError:
                pass

    # 4. site-packages: remove tests/ and test/ dirs
    for pydir in ("python3.12", "python3.11", "python3.10"):
        site = os.path.join(lib_root, pydir, "site-packages")
        if not os.path.isdir(site):
            continue
        for name in os.listdir(site):
            if name in ("tests", "test") and os.path.isdir(os.path.join(site, name)):
                shutil.rmtree(os.path.join(site, name), ignore_errors=True)
                removed += 1
            pkg_dir = os.path.join(site, name)
            if os.path.isdir(pkg_dir):
                for sub in ("tests", "test"):
                    t = os.path.join(pkg_dir, sub)
                    if os.path.isdir(t):
                        shutil.rmtree(t, ignore_errors=True)
                        removed += 1

    # 5. Mac bundle does not use these at runtime (ASR is MLX-Whisper only)
    for pkg in ("faster_whisper", "funasr", "modelscope"):
        for pydir in ("python3.12", "python3.11", "python3.10"):
            site = os.path.join(env_root, "lib", pydir, "site-packages")
            if not os.path.isdir(site):
                continue
            for pattern in (pkg, pkg.replace("_", "-"), f"{pkg}-*.dist-info"):
                for path in glob.glob(os.path.join(site, pattern)):
                    if os.path.exists(path):
                        if os.path.isdir(path):
                            shutil.rmtree(path, ignore_errors=True)
                        else:
                            try:
                                os.remove(path)
                            except OSError:
                                pass
                        removed += 1

    # 6. Remove PyTorch stack and heavy GUI libs that are unused in the macOS
    # app bundle at runtime. The Swift UI is the primary GUI; Python-side PySide6
    # / customtkinter are only needed for the standalone GUI, not the bundled app.
    heavy_pkgs = ("torch", "torchaudio", "torchvision", "PySide6", "customtkinter")
    for pydir in ("python3.12", "python3.11", "python3.10"):
        site = os.path.join(env_root, "lib", pydir, "site-packages")
        if not os.path.isdir(site):
            continue
        for pkg in heavy_pkgs:
            for pattern in (
                pkg,
                pkg.replace("_", "-"),
                f"{pkg}-*.dist-info",
                f"{pkg.lower()}-*.dist-info",
            ):
                for path in glob.glob(os.path.join(site, pattern)):
                    if os.path.exists(path):
                        if os.path.isdir(path):
                            shutil.rmtree(path, ignore_errors=True)
                        else:
                            try:
                                os.remove(path)
                            except OSError:
                                pass
                        removed += 1

    if removed:
        print(f"Pruned {removed} items from bundled .pixi environment.")


# --- 4. DMG Packaging ---
if "--create-dmg" in sys.argv:
    slim_build = "--slim" in sys.argv
    print("\n--- Packaging DMG ---")
    if slim_build:
        print("Slim build: app will use user's local Python/MLX (no .pixi bundled).")
    else:
        print("Copying App Resources (This may take several minutes due to the size of the ML environment)...")

    # 4a. Copy source code (always needed so backend can run)
    shutil.copytree("src", f"{RESOURCES_DIR}/src", dirs_exist_ok=True)
    if os.path.exists("assets"):
        shutil.copytree("assets", f"{RESOURCES_DIR}/assets", dirs_exist_ok=True)

    # 4b. Copy .pixi environment unless --slim (user will use PRIVOX_PYTHON or venv)
    dest_pixi = f"{RESOURCES_DIR}/.pixi"
    if slim_build:
        if os.path.exists(dest_pixi):
            shutil.rmtree(dest_pixi)
            print("Removed existing .pixi from bundle (slim build).")
        print("Skipping .pixi bundle (--slim). User must have Python + MLX installed and set PRIVOX_PYTHON or use ~/Library/Application Support/Privox/venv.")
    elif os.path.exists(".pixi"):
        print("Copying .pixi environment...")
        if os.path.exists(dest_pixi):
            shutil.rmtree(dest_pixi)
        shutil.copytree(".pixi", dest_pixi, symlinks=True)
        dest_env = os.path.join(dest_pixi, "envs", "default")
        if os.path.isdir(dest_env):
            print("Pruning bundled .pixi (strip include, docs, cache, unused Mac packages)...")
            prune_pixi_bundle_for_mac(dest_env)

    # 4c. Create DMG using hdiutil
    print("Building DMG using hdiutil...")
    dmg_path = f"{BUILD_DIR}/{APP_NAME}.dmg"
    
    if os.path.exists(dmg_path):
        os.remove(dmg_path)
        
    dmg_cmd = [
        "hdiutil", "create", 
        "-volname", APP_NAME, 
        "-srcfolder", APP_DIR, 
        "-ov", 
        "-format", "UDBZ", 
        dmg_path
    ]
    
    try:
        subprocess.run(dmg_cmd, check=True)
        print(f"\n✅ DMG successfully created at {dmg_path}")
    except subprocess.CalledProcessError as e:
        print(f"DMG creation failed: {e}")
        exit(1)

    maybe_notarize_dmg(dmg_path)
else:
    print(f"To run: open {APP_DIR}")
    print(f"To build DMG: python build_mac_app.py --create-dmg")
    print(f"Slim DMG (use local Python/MLX): python build_mac_app.py --create-dmg --slim")
    print("")
    print("Stable-signing tips:")
    print("  export PRIVOX_SIGNING_IDENTITY='Developer ID Application: Your Name (TEAMID)'")
    print("  export PRIVOX_REQUIRE_STABLE_SIGNATURE=1")
    print("Optional notarization for DMG:")
    print("  export PRIVOX_NOTARY_PROFILE='your-notarytool-profile'")
