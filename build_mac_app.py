import os
import subprocess
import shutil
import sys

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

# We expect src/mac_app/App.swift to exist. 
# We'll compile it into the MacOS directory of our app bundle.
swift_files = [os.path.join(SOURCE_DIR, f) for f in os.listdir(SOURCE_DIR) if f.endswith('.swift')]

if not swift_files:
    print(f"Error: No .swift files found in {SOURCE_DIR}")
    exit(1)

compile_cmd = [
    "swiftc",
    "-parse-as-library",
    "-target", "arm64-apple-macosx13.0", # Build for Apple Silicon, macOS 13+
    *swift_files,
    "-o", f"{MACOS_DIR}/{APP_NAME}"
]

try:
    subprocess.run(compile_cmd, check=True)
    print(f"Successfully compiled {APP_NAME} to {MACOS_DIR}/{APP_NAME}")
except subprocess.CalledProcessError as e:
    print(f"Compilation failed: {e}")
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

# --- 4. DMG Packaging ---
if "--create-dmg" in sys.argv:
    print("\n--- Packaging DMG ---")
    print("Copying App Resources (This may take several minutes due to the size of the ML environment)...")
    
    # 4a. Copy source code
    shutil.copytree("src", f"{RESOURCES_DIR}/src", dirs_exist_ok=True)
    if os.path.exists("assets"):
        shutil.copytree("assets", f"{RESOURCES_DIR}/assets", dirs_exist_ok=True)
        
    # 4b. Copy .pixi environment (Preserving Symlinks is CRITICAL for Conda/Pixi)
    if os.path.exists(".pixi"):
        print("Copying .pixi environment...")
        shutil.copytree(".pixi", f"{RESOURCES_DIR}/.pixi", dirs_exist_ok=True, symlinks=True)
    
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
    print("")
    print("Stable-signing tips:")
    print("  export PRIVOX_SIGNING_IDENTITY='Developer ID Application: Your Name (TEAMID)'")
    print("  export PRIVOX_REQUIRE_STABLE_SIGNATURE=1")
    print("Optional notarization for DMG:")
    print("  export PRIVOX_NOTARY_PROFILE='your-notarytool-profile'")
