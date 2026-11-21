#!/bin/sh
# Package a standalone Mac build:  sh Tools/package.sh [Development|Shipping]
# Result: Builds/Mac/VoxelLab.app (double-click it; first time: right-click > Open, it is unsigned).
# The engine's own -archive step copies an app without its game data on this setup, so the complete staged app is
# copied over it instead. Close the editor first (the game and the editor fight over the audio device otherwise).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UE="${UE_ROOT:-/Users/Shared/Epic Games/UnrealInstall/UE_5.8}"
CONFIG="${1:-Development}"
"$UE/Engine/Build/BatchFiles/RunUAT.sh" BuildCookRun -project="$ROOT/VoxelLab.uproject" -platform=Mac \
    -clientconfig="$CONFIG" -build -cook -stage -pak -noP4 -utf8output > "$ROOT/Saved/package.log" 2>&1 \
    || { echo "packaging failed: see Saved/package.log"; exit 1; }
mkdir -p "$ROOT/Builds/Mac"
rm -rf "$ROOT/Builds/Mac/VoxelLab.app"
ditto "$ROOT/Saved/StagedBuilds/Mac/VoxelLab.app" "$ROOT/Builds/Mac/VoxelLab.app"
echo "built: $ROOT/Builds/Mac/VoxelLab.app ($(du -sh "$ROOT/Builds/Mac/VoxelLab.app" | cut -f1))"
