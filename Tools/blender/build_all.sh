#!/bin/sh
# Rebuild everything: .blend + .fbx, rendered cells, sheets + metadata, previews.
#   Tools/blender/build_all.sh [--elev 30] [--cm-per-px 1.75] [other render_sprites.py options]
#   PREVIEW_ARGS=--no-gif skips the animated GIFs.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
PY="${PYTHON:-$ROOT/Tools/.venv/bin/python}"
if [ ! -x "$PY" ]; then
    python3 -m venv "$ROOT/Tools/.venv" && "$ROOT/Tools/.venv/bin/pip" install pillow numpy
fi
for name in shieldbearer archer; do
    "$BLENDER" -b -P "$HERE/build_character.py" -- "$name" 2>&1 | grep -E "^(saved|exported)|Error|Traceback" || true
    "$BLENDER" -b "$ROOT/SourceArt/Characters/blender/$name.blend" -P "$HERE/render_sprites.py" -- "$@" 2>&1 \
        | grep -E "^(rendered|wrote)|Error|Traceback" || true
done
status=0
"$PY" "$HERE/make_sheets.py" || status=1
"$PY" "$HERE/make_previews.py" $PREVIEW_ARGS
exit $status
