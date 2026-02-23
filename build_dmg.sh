#!/bin/bash
# Privox macOS DMG Packager
# This script bundles the dist/Privox.app directory into a standard macOS .dmg installer

APP_NAME="Privox"
DMG_NAME="${APP_NAME}.dmg"
DIST_DIR="dist"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"

# Ensure the .app bundle exists
if [ ! -d "$APP_BUNDLE" ]; then
    echo "Error: $APP_BUNDLE does not exist. Please run 'pixi run build' first."
    exit 1
fi

echo "Packaging $APP_NAME into $DMG_NAME..."

# Remove old DMG if it exists
if [ -f "$DMG_NAME" ]; then
    rm -f "$DMG_NAME"
fi

# Create a temporary staging directory
STAGING_DIR="dmg_staging"
mkdir -p "$STAGING_DIR"

# Copy the app bundle into the staging directory
echo "Copying application resources..."
cp -R "$APP_BUNDLE" "$STAGING_DIR/"

# Create a symlink to the Applications folder for drag-and-drop
echo "Creating /Applications symlink..."
ln -s /Applications "$STAGING_DIR/Applications"

# Generate the compressed DMG using hdiutil
echo "Generating DMG image..."
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING_DIR" -ov -format UDZO "$DMG_NAME"

# Clean up staging files
echo "Cleaning up staging directory..."
rm -rf "$STAGING_DIR"

echo "Success! $DMG_NAME is ready for distribution."
