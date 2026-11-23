#!/bin/sh
# Rebuild Realm v2 (L_RealmV2) end to end (editor open, not in PIE):  sh Tools/mac/realmv2_rebuild.sh [layout|blender|ruins]
#   (no argument) ground + water + sea + barriers + plan in Blender, import them, build /Game/Maps/L_RealmV2
#   layout        only the plan changed (things moved, no ground, water or hazard changed): realmv2.json + the level, no import
#   blender       only the Blender part (no editor needed): the meshes and the plan
#   ruins         the ruins' and the ports' meshes (Tools/blender/assets/ruins.py, ports.py) and their import: once, and after changing them
# The tall trees' and the plants' further levels of detail are the realm's (sh Tools/mac/realm_rebuild.sh trees).
# The balance report (walking distances from each castle) needs scipy: it is measured with the tools' python first and
# kept in realmv2.json by the Blender run.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
B="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
PY="$ROOT/Tools/.venv/bin/python"
[ -x "$PY" ] && "$PY" "$ROOT/Tools/blender/realmv2_layout.py" --balance | grep -vE "^realmv2:"
if [ "$1" = "ruins" ]; then
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/assets/ruins.py" -- --no-render 2>&1 | grep -E "^exported|Traceback|Error"
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/assets/ports.py" -- --no-render 2>&1 | grep -E "^exported|Traceback|Error"
    python3 "$ROOT/Tools/ue_py.py" -c "
ROOT = r'$ROOT'
PARTS = ['meshes']; ONLY = ['SM_Ruin_Arch', 'SM_Ruin_Pillar_A', 'SM_Ruin_Pillar_B', 'SM_Ruin_Pillar_C', 'SM_Ruin_Block', 'SM_Port_Warehouse', 'SM_Port_Crane', 'SM_Port_Tower', 'SM_Port_Arch']
exec(open(ROOT + '/Tools/ue/import_assets.py').read())" 600 | tail -1
    exit 0
fi
if [ "$1" = "layout" ]; then
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/realmv2_layout.py" 2>&1 | grep -E "^realmv2|Traceback|Error"
else
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/assets/realmv2_terrain.py" -- --no-render > "$ROOT/Saved/build_realmv2_terrain.log" 2>&1
    grep -E "^realmv2|^barrier|Traceback|Error" "$ROOT/Saved/build_realmv2_terrain.log"
    [ "$1" = "blender" ] && exit 0
    python3 "$ROOT/Tools/ue_py.py" -c "
import json
ROOT = r'$ROOT'
TILES = json.load(open(ROOT + '/SourceArt/Meshes/realmv2_tiles.json'))
PARTS = ['meshes']; ONLY = TILES + [t + s for t in TILES for s in ('_L1', '_L2')] + ['SM_RealmV2Water', 'SM_RealmV2Sea', 'SM_RealmV2Barrier']
exec(open(ROOT + '/Tools/ue/import_assets.py').read())" 5400 | tail -1
    python3 "$ROOT/Tools/ue_py.py" "$ROOT/Tools/ue/realmv2_lods.py" 3600 | tail -1      # the ground's further levels of detail
fi
python3 "$ROOT/Tools/ue_py.py" "$ROOT/Tools/ue/build_realmv2.py" 3600 | tail -1
