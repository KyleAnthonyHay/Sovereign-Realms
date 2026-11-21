#!/bin/sh
# Package a standalone Mac build:  sh Tools/package.sh [Shipping|Development]
# Result: Builds/Mac/VoxelLab.app (double-click it; first time: right-click > Open, it is unsigned).
#   Shipping (the default)   the build to play: no console, no log, no test hooks (the command inbox Saved/VLCommands.txt
#                            and vl.Record are compiled out), no debug files, its symbols stripped
#   Development              for tests: the ~ console, the log, the command inbox; about 200 MB bigger
# VL_STRIP=0 leaves the Shipping executable's symbols in (crash reports with names; about 100 MB more).
# The engine's own -archive step copies an app without its game data on this setup, so the complete staged app is
# copied over it instead. Close the editor first (the game and the editor fight over the audio device otherwise).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UE="${UE_ROOT:-/Users/Shared/Epic Games/UnrealInstall/UE_5.8}"
CONFIG="${1:-Shipping}"
case "$CONFIG" in
    Shipping) EXTRA="-nodebuginfo" ;;
    Development) EXTRA="" ;;
    *) echo "usage: sh Tools/package.sh [Shipping|Development]"; exit 2 ;;
esac
"$UE/Engine/Build/BatchFiles/RunUAT.sh" BuildCookRun -project="$ROOT/VoxelLab.uproject" -platform=Mac \
    -clientconfig="$CONFIG" -specifiedarchitecture=arm64 -build -cook -stage -pak -noP4 -utf8output $EXTRA > "$ROOT/Saved/package.log" 2>&1 \
    || { echo "packaging failed: see Saved/package.log"; exit 1; }
# (a Shipping build stages as VoxelLab-Mac-Shipping.app on some setups: take whichever app was staged last)
STAGED="$ROOT/Saved/StagedBuilds/Mac/VoxelLab.app"
[ "$CONFIG" = "Shipping" ] && [ -d "$ROOT/Saved/StagedBuilds/Mac/VoxelLab-Mac-Shipping.app" ] \
    && [ "$ROOT/Saved/StagedBuilds/Mac/VoxelLab-Mac-Shipping.app" -nt "$STAGED" ] && STAGED="$ROOT/Saved/StagedBuilds/Mac/VoxelLab-Mac-Shipping.app"
[ -d "$STAGED" ] || { echo "packaging failed: no staged app at $STAGED (see Saved/package.log)"; exit 1; }
mkdir -p "$ROOT/Builds/Mac"
rm -rf "$ROOT/Builds/Mac/VoxelLab.app"
ditto "$STAGED" "$ROOT/Builds/Mac/VoxelLab.app"
APP="$ROOT/Builds/Mac/VoxelLab.app"
# no debug files in the app (a .dSYM would be kept beside it, in Builds/Mac/Symbols, never inside)
find "$APP" -name "*.dSYM" -prune -print 2>/dev/null | while read -r D; do
    mkdir -p "$ROOT/Builds/Mac/Symbols" && rm -rf "$ROOT/Builds/Mac/Symbols/$(basename "$D")" && mv "$D" "$ROOT/Builds/Mac/Symbols/"
done
if [ "$CONFIG" = "Shipping" ] && [ "${VL_STRIP:-1}" != "0" ]; then
    # the executable's symbol table goes (the copy in Builds only: the staged app keeps it), then the app is signed
    # again as it was: ad hoc, with the same entitlements (the sandbox: it is where the saved settings live)
    EXE="$APP/Contents/MacOS/$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP/Contents/Info.plist" 2>/dev/null || echo VoxelLab)"
    ENT="$ROOT/Saved/package.entitlements.plist"
    if [ -f "$EXE" ] && codesign -d --entitlements "$ENT" --xml "$APP" 2>/dev/null; then
        BEFORE=$(stat -f %z "$EXE"); BAK="$ROOT/Saved/package.unstripped"     # (outside the app: a file left in the bundle fails the signature)
        cp "$EXE" "$BAK"
        if xcrun strip -x "$EXE" 2>>"$ROOT/Saved/package.log" \
            && { if [ -s "$ENT" ]; then codesign --force --sign - --entitlements "$ENT" --timestamp=none --generate-entitlement-der "$APP"; else codesign --force --sign - --timestamp=none "$APP"; fi; } >>"$ROOT/Saved/package.log" 2>&1 \
            && codesign --verify --strict "$APP" >>"$ROOT/Saved/package.log" 2>&1; then
            rm -f "$BAK"
            echo "stripped: executable $((BEFORE / 1048576)) MB -> $(($(stat -f %z "$EXE") / 1048576)) MB"
        else
            # anything went wrong: the executable as it was staged, signed as it was
            mv -f "$BAK" "$EXE"
            ditto "$STAGED/Contents/_CodeSignature" "$APP/Contents/_CodeSignature" 2>/dev/null
            echo "warning: the symbols could not be stripped (see Saved/package.log); the app is as staged"
        fi
    else
        echo "warning: the symbols were not stripped (no executable or no signature to read); the app is as staged"
    fi
fi
echo "built: $APP ($CONFIG, $(du -sh "$APP" | cut -f1))"
