#!/bin/sh
# Rebuild the realm (L_Realm) end to end (editor open, not in PIE):  sh Tools/realm_rebuild.sh [layout]
#   (no argument) ground + water + sea + backdrop + barriers + plan in Blender, import them, build /Game/Maps/L_Realm
#   trees         the tall trees' further levels of detail (Tools/blender/assets/tree_lods.py -> LOD 1, 2 of SM_Tree2_*) and the small plants'
#                 (Tools/ue/plant_lods.py): once, and after importing the trees or the plants again
#   layout        only the plan changed (things moved, no ground, water or hazard changed): realm.json + the level, no import
# The balance report (walking distances from each castle) needs scipy: it is measured with the tools' python first and
# kept in realm.json by the Blender run.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
B=/Applications/Blender.app/Contents/MacOS/Blender
PY="$ROOT/Tools/.venv/bin/python"
[ -x "$PY" ] && "$PY" "$ROOT/Tools/blender/realm_layout.py" --balance | grep -vE "^realm:"
if [ "$1" = "trees" ]; then
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/assets/tree_lods.py" 2>&1 | grep -E "^LOD|Traceback|Error"
    python3 "$ROOT/Tools/ue_py.py" -c "
ROOT = r'$ROOT'
PARTS = ['meshes']; ONLY = ['SM_Tree2_%s_%s' % (k, p) for k in 'ABCD' for p in ('Leaves_L1', 'Leaves_L2', 'Trunk_L2')]
exec(open(ROOT + '/Tools/ue/import_assets.py').read())" 600 | tail -1
    python3 "$ROOT/Tools/ue_py.py" "$ROOT/Tools/ue/tree_lods.py" 600
    python3 "$ROOT/Tools/ue_py.py" "$ROOT/Tools/ue/plant_lods.py" 600      # the grass, flowers and bushes: their cheap far version
    exit 0
fi
if [ "$1" = "layout" ]; then
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/realm_layout.py" 2>&1 | grep -E "^realm|Traceback|Error"
else
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/assets/realm_terrain.py" -- --no-render > "$ROOT/Saved/build_realm_terrain.log" 2>&1
    grep -E "^realm|^barrier|Traceback|Error" "$ROOT/Saved/build_realm_terrain.log"
    python3 "$ROOT/Tools/ue_py.py" -c "
import json
ROOT = r'$ROOT'
PARTS = ['meshes']; ONLY = json.load(open(ROOT + '/SourceArt/Meshes/realm_tiles.json')) + ['SM_RealmWater', 'SM_RealmSea', 'SM_RealmBackdrop', 'SM_RealmBarrier']
exec(open(ROOT + '/Tools/ue/import_assets.py').read())" 2400 | tail -1
fi
python3 "$ROOT/Tools/ue_py.py" "$ROOT/Tools/ue/build_realm.py" 2400 | tail -1
