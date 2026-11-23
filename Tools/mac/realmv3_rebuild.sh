#!/bin/sh
# Rebuild Realm v3 (L_RealmV3) end to end (editor open, not in PIE):  sh Tools/mac/realmv3_rebuild.sh [layout|blender]
#   (no argument) ground + sea + barriers + plan in Blender, import them, build /Game/Maps/L_RealmV3
#   layout        only the plan changed (things moved, no ground or hazard changed): realmv3.json + the level, no import
#   blender       only the Blender part (no editor needed): the meshes and the plan
# The tall trees' and the plants' further levels of detail are the realm's (sh Tools/mac/realm_rebuild.sh trees).
# The balance report (walking distances from each castle) needs scipy: it is measured with the tools' python first and
# kept in realmv3.json by the Blender run.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
B="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
PY="$ROOT/Tools/.venv/bin/python"
[ -x "$PY" ] && "$PY" "$ROOT/Tools/blender/realmv3_layout.py" --balance | grep -vE "^realmv3:"
if [ "$1" = "layout" ]; then
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/realmv3_layout.py" 2>&1 | grep -E "^realmv3|Traceback|Error"
else
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/assets/realmv3_terrain.py" -- --no-render > "$ROOT/Saved/build_realmv3_terrain.log" 2>&1
    grep -E "^realmv3|^barrier|Traceback|Error" "$ROOT/Saved/build_realmv3_terrain.log"
    [ "$1" = "blender" ] && exit 0
    python3 "$ROOT/Tools/ue_py.py" -c "
import json
ROOT = r'$ROOT'
TILES = json.load(open(ROOT + '/SourceArt/Meshes/realmv3_tiles.json'))
PARTS = ['meshes']; ONLY = TILES + [t + s for t in TILES for s in ('_L1', '_L2')] + ['SM_RealmV3Ramps', 'SM_RealmV3Sea', 'SM_RealmV3Barrier']
exec(open(ROOT + '/Tools/ue/import_assets.py').read())" 5400 | tail -1
    python3 "$ROOT/Tools/ue_py.py" "$ROOT/Tools/ue/realmv3_lods.py" 3600 | tail -1      # the ground's further levels of detail
fi
python3 "$ROOT/Tools/ue_py.py" "$ROOT/Tools/ue/build_realmv3.py" 3600 | tail -1
