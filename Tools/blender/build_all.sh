#!/bin/sh
# Rebuild every voxel asset from its generator (no preview renders):  sh Tools/blender/build_all.sh [name ...]
# Textures first (Tools/.venv python), then each Tools/blender/assets/<name>.py in Blender, four at a time, terrain last
# (it also writes SourceArt/layout.json). Logs: Saved/build_<name>.log
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
B=/Applications/Blender.app/Contents/MacOS/Blender
mkdir -p "$ROOT/Saved"
"$ROOT/Tools/.venv/bin/python" "$ROOT/Tools/blender/voxtex.py" >/dev/null 2>&1
NAMES="${*:-townhall barracks range_mine farm nature props castle}"
n=0
for a in $NAMES; do
  ( "$B" -b --factory-startup --python "$ROOT/Tools/blender/assets/$a.py" -- --no-render > "$ROOT/Saved/build_$a.log" 2>&1; echo "$a: $(grep -c '^exported' "$ROOT/Saved/build_$a.log") exported$(grep -q Traceback "$ROOT/Saved/build_$a.log" && echo ' (ERROR: see log)')" ) &
  n=$((n + 1)); [ $((n % 4)) -eq 0 ] && wait
done
wait
"$B" -b --factory-startup --python "$ROOT/Tools/blender/assets/terrain.py" -- --no-render > "$ROOT/Saved/build_terrain.log" 2>&1
grep -E "layout:|terrain:|fall curtain|Traceback|Error" "$ROOT/Saved/build_terrain.log"
"$B" -b --factory-startup --python "$ROOT/Tools/blender/find_chimneys.py" 2>&1 | grep -E "^SM_"
