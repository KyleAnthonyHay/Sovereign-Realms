# Buildings: castle, farm, mine

Scripted Blender models, exported as glTF and imported as `/Game/SR/Buildings/SM_Bld_*`. Nothing here is edited
by hand: change the scripts and rebuild. Contract and parameters: `Docs/VISUAL_CONTRACT.md`, "Buildings".

| File | What it is |
| --- | --- |
| `Tools/blender/bldkit.py` | The kit: walls with real openings, batters, parapets, merlons, timber, cloth, props, preview scene, glTF export. Authors in Unreal cm, front toward -X, UVs at 4 cm per texel. |
| `Tools/blender/bld_castle.py`, `bld_farm.py`, `bld_mine.py`, `bld_rallyflag.py` | One module per model: `build(kit)`, `MESH`, `FOOTPRINT`. |
| `Tools/blender/build_building.py` | Driver. Writes `SM_Bld_<Name>.gltf` + `.bin`, `<name>.json` (footprint, sockets, bounds), `blender/<name>.blend`, and game-camera previews in `Saved/BuildingPreview/`. |
| `Tools/textures/gen_building_textures.py` | Draws `SourceArt/Textures/T_Bld_*.png`. |

## Rebuild

```sh
Tools/.venv/bin/python Tools/textures/gen_building_textures.py
for n in castle farm mine rallyflag; do
  /Applications/Blender.app/Contents/MacOS/Blender -b -P Tools/blender/build_building.py -- $n   # --no-render to skip previews
done
Tools/.venv/bin/python Tools/world/gen_battlefield.py      # only if a footprint, socket or the BUILDINGS table changed
```

Then, with the editor open on the project (R = the repo path):

```sh
python3 Tools/ue_py.py -c "PARTS=['textures']; TEX_PREFIX='T_Bld_'; exec(open(r'R/Tools/import_world_assets.py').read())"
python3 Tools/ue_py.py -c "ONLY=['building']; exec(open(r'R/Tools/build_visual_materials.py').read())"
python3 Tools/ue_py.py Tools/import_buildings.py
python3 Tools/ue_py.py -c "PARTS=['buildings']; exec(open(r'R/Tools/build_battlefield_visuals.py').read())"   # 'world' if gen_battlefield.py ran
```

Judge the result in the game, not in Blender: `python3 Tools/pie.py start`, then
`python3 Tools/pie.py shot <name> X Y zoom` (saves `Saved/Screenshots/SR/<name>.png`).

A new surface needs three entries: a texture in the generator, a slot in `MATERIALS` (`bldkit.py`) and the same
slot in `BUILDING_SLOTS` (`Tools/build_visual_materials.py`).
