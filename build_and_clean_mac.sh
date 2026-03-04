#!/bin/bash
# Privox macOS All-in-One Build & Cleanup Script
# This script builds the Privox.app, packages it into a DMG, 
# and then forcefully cleans up the heavy 3GB+ local pixi environment.

set -e

echo "========================================="
echo "  Privox macOS Build & Cleanup Utility   "
echo "========================================="

echo "\n[1/3] Building the macOS Application Bundle..."
# pixi run build triggers the `python build_app.py` process defined in pixi.toml
pixi run build

echo "\n[2/3] Packaging into Privox.dmg..."
bash build_dmg.sh

echo "\n[3/3] Cleaning up heavy build artifacts and caches..."
# Remove the local 2.6GB+ Pixi environment
if [ -d ".pixi" ]; then
    echo "Removing .pixi environment..."
    rm -rf ".pixi"
fi

# Remove PyInstaller build directories
if [ -d "build" ]; then
    echo "Removing temporary build/ directory..."
    rm -rf "build"
fi

# Remove PyInstaller dist directory (The DMG is already created in the root)
if [ -d "dist" ]; then
    echo "Removing dist/ directory..."
    rm -rf "dist"
fi

# Optionally, clean the global rattler cache if the user really wants to save space
# echo "Cleaning global Pixi package cache..."
# pixi global cache clear 

echo "\n========================================="
echo "  Success! Your 'Privox.dmg' is ready.   "
echo "  All temporary build files and heavy    "
echo "  dependencies have been removed.        "
echo "========================================="
