#!/bin/sh
# Rebuild the town end to end (editor open, not in PIE):  sh Tools/town_rebuild.sh [layout]
#   (no argument) terrain + water + layout in Blender, import them, build /Game/Maps/L_Town
#   layout        only the plan changed (things moved, no ground changed): town.json + the level, no import
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
B=/Applications/Blender.app/Contents/MacOS/Blender
if [ "$1" = "layout" ]; then
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/town_layout.py" 2>&1 | grep -E "^town|Traceback|Error"
else
    "$B" -b --factory-startup --python "$ROOT/Tools/blender/assets/town_terrain.py" -- --no-render > "$ROOT/Saved/build_town_terrain.log" 2>&1
    grep -E "^town|Traceback|Error" "$ROOT/Saved/build_town_terrain.log"
    python3 "$ROOT/Tools/ue_py.py" -c "
import json
ROOT = r'$ROOT'
PARTS = ['meshes']; ONLY = json.load(open(ROOT + '/SourceArt/Meshes/town_tiles.json')) + ['SM_TownWater', 'SM_TownSea']
exec(open(ROOT + '/Tools/ue/import_assets.py').read())" 1500 | tail -1
fi
python3 "$ROOT/Tools/ue_py.py" "$ROOT/Tools/ue/build_town.py" 1500 | tail -1
