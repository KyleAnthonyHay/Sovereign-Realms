#!/bin/sh
# Rebuild the highlands (L_Highlands) end to end (editor open, not in PIE):  sh Tools/highland_rebuild.sh [layout]
#   (no argument) ground + water + sea + backdrop + far woods + barriers + plan in Blender, import them, build /Game/Maps/L_Highlands
#   layout        only the plan changed (things moved, no ground, water or hazard changed): highland.json + the level, no import
#   blender       only the Blender part (no editor needed): the meshes and the plan
# The tall trees' second level of detail is the realm's (sh Tools/realm_rebuild.sh trees).
# The balance report (walking distances from each castle) needs scipy: it is measured with the tools' python first and
# kept in highland.json by the Blender run.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
B=/Applications/Blender.app/Contents/MacOS/Blender
PY="$ROOT/../Tools/.venv/bin/python"
[ -x "$PY" ] && "$PY" "$ROOT/Tools/blender/highland_layout.py" --balance | grep -vE "^highland:"
if [ "$1" = "layout" ]; then
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/highland_layout.py" 2>&1 | grep -E "^highland|Traceback|Error"
else
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/assets/highland_terrain.py" -- --no-render > "$ROOT/Saved/build_highland_terrain.log" 2>&1
    grep -E "^highland|^barrier|Traceback|Error" "$ROOT/Saved/build_highland_terrain.log"
    [ "$1" = "blender" ] && exit 0
    python3 "$ROOT/Tools/ue_py.py" -c "
import json
ROOT = r'$ROOT'
PARTS = ['meshes']; ONLY = json.load(open(ROOT + '/SourceArt/Meshes/highland_tiles.json')) + ['SM_HighlandWater', 'SM_HighlandSea', 'SM_HighlandBackdrop', 'SM_HighlandWoods', 'SM_HighlandBarrier']
exec(open(ROOT + '/Tools/ue/import_assets.py').read())" 3600 | tail -1
fi
python3 "$ROOT/Tools/ue_py.py" "$ROOT/Tools/ue/build_highland.py" 3600 | tail -1
