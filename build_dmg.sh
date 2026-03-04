#!/bin/bash
set -euo pipefail
# Privox macOS DMG Packager
# This script bundles the dist/Privox.app directory into a standard macOS .dmg installer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="Privox"
DMG_NAME="${APP_NAME}.dmg"
DIST_DIR="dist"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
APP_EXECUTABLE="${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"
STAGING_DIR="dmg_staging"
LOG_DIR="${SCRIPT_DIR}/build_logs"
LOG_FILE="${LOG_DIR}/build_dmg_$(date +"%Y%m%d_%H%M%S").log"
MIN_FREE_GB="${PRIVOX_MIN_FREE_GB:-12}"

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "Build log: $LOG_FILE"

available_kb=$(df -k . | awk 'NR==2 {print $4}')
required_kb=$((MIN_FREE_GB * 1024 * 1024))
if [ "${available_kb:-0}" -lt "$required_kb" ]; then
    echo "Error: insufficient disk space."
    echo "Available: $((available_kb / 1024 / 1024)) GiB, required: ${MIN_FREE_GB} GiB."
    echo "Free disk space and retry, or lower PRIVOX_MIN_FREE_GB if you know what you are doing."
    exit 1
fi

on_error() {
    local exit_code=$?
    echo
    echo "Build failed (exit code: $exit_code)."
    echo "Showing last 60 log lines:"
    tail -n 60 "$LOG_FILE" || true
    if [[ -t 1 ]]; then
        echo
        read -r -p "Press Enter to close this window..." _
    fi
    exit "$exit_code"
}

cleanup() {
    rm -rf "$STAGING_DIR"
}

trap on_error ERR
trap cleanup EXIT

ensure_app_bundle() {
    [ -d "$APP_BUNDLE" ] && [ -x "$APP_EXECUTABLE" ]
}

run_build() {
    local clean_mode="$1"
    if ! command -v pixi >/dev/null 2>&1; then
        echo "Error: pixi is not installed or not in PATH."
        exit 1
    fi
    if [ "$clean_mode" = "1" ]; then
        echo "Running clean build (PRIVOX_BUILD_CLEAN=1 pixi run build)..."
        if ! PRIVOX_BUILD_CLEAN=1 pixi run build; then
            echo "Error: clean build failed."
            exit 1
        fi
    else
        echo "Running fast build (pixi run build)..."
        if ! pixi run build; then
            echo "Error: fast build failed."
            exit 1
        fi
    fi
}

# Ensure the .app bundle exists and contains executable; rebuild automatically when invalid.
if ! ensure_app_bundle; then
    echo "App bundle missing or incomplete. Attempting fast build..."
    run_build 0
fi

if ! ensure_app_bundle; then
    echo "App bundle still incomplete after fast build. Retrying with clean build..."
    run_build 1
fi

if ! ensure_app_bundle; then
    echo "Error: app bundle is invalid."
    echo "Expected executable: $APP_EXECUTABLE"
    echo "Tip: inspect the latest build log and dist layout."
    exit 1
fi

echo "Packaging $APP_NAME into $DMG_NAME..."

# Remove old DMG if it exists
if [ -f "$DMG_NAME" ]; then
    rm -f "$DMG_NAME"
fi

# Create a temporary staging directory; trap ensures cleanup on exit (success or failure)
mkdir -p "$STAGING_DIR"

# Copy the app bundle into the staging directory
echo "Copying application resources..."
cp -R "$APP_BUNDLE" "$STAGING_DIR/"

# Ad-hoc Code Signing (essential for privacy permissions on modern macOS)
echo "Applying ad-hoc code signature..."
ENTITLEMENTS="assets/entitlements.plist"
if [ -f "$ENTITLEMENTS" ]; then
    codesign --deep --force --options runtime --entitlements "$ENTITLEMENTS" -s - "$STAGING_DIR/$APP_NAME.app"
else
    codesign --deep --force -s - "$STAGING_DIR/$APP_NAME.app"
fi

# Create a symlink to the Applications folder for drag-and-drop
echo "Creating /Applications symlink..."
ln -s /Applications "$STAGING_DIR/Applications"

# Generate the compressed DMG using hdiutil
echo "Generating DMG image..."
if ! hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING_DIR" -ov -format UDZO "$DMG_NAME"; then
    echo "Error: hdiutil failed to create DMG."
    exit 1
fi

echo "Success! $DMG_NAME is ready for distribution."
echo "Build log saved at: $LOG_FILE"
