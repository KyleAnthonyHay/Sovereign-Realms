# Buildings: castle, farm, mine, tower, barracks, archery range, stable, workshop, granary, treasury

Scripted Blender models, exported as glTF and imported as `/Game/SR/Buildings/SM_Bld_*`. Nothing here is edited
by hand: change the scripts and rebuild. Contract and parameters: `Docs/VISUAL_CONTRACT.md`, "Buildings".

| File | What it is |
| --- | --- |
| `Tools/blender/bldkit.py` | The kit: walls with real openings, batters, parapets, merlons, timber, cloth, props, preview scene, glTF export. Authors in Unreal cm, front toward -X, UVs at 4 cm per texel. |
| `Tools/blender/bld_castle.py`, `bld_farm.py`, `bld_mine.py`, `bld_tower.py`, `bld_barracks.py`, `bld_range.py`, `bld_stable.py`, `bld_workshop.py`, `bld_granary.py`, `bld_treasury.py` | One module per building: `build(kit, state)`, `MESH`, `FOOTPRINT`, `STATES`. |
| `Tools/blender/bld_rallyflag.py` | A prop with one mesh: `build(kit)`. |
| `Tools/blender/build_building.py` | Driver. Writes `SM_Bld_<Name>.gltf` + `.bin` and its `_Site`, `_Damaged`, `_Ruin` siblings, `<name>.json` (footprint, sockets, bounds; `states`: the siblings' mesh names, triangles, bounds, slots), `blender/<name>.blend`, and previews in `Saved/BuildingPreview/`. |
| `Tools/textures/gen_building_textures.py` | Draws `SourceArt/Textures/T_Bld_*.png`. |

## Rebuild

```sh
Tools/.venv/bin/python Tools/textures/gen_building_textures.py
for n in castle farm mine tower barracks range stable workshop granary treasury rallyflag; do     # every level too (LEVELS)
  /Applications/Blender.app/Contents/MacOS/Blender -b -P Tools/blender/build_building.py -- $n   # all states; --state damaged for one, --no-render to skip previews
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

## States

Every building is four meshes with one origin, orientation and footprint (`bldkit.STATES`):

| Mesh | Shown | How it is made |
| --- | --- | --- |
| `SM_Bld_<Name>` | finished | `complete(k)` in the module. |
| `SM_Bld_<Name>_Site` | during construction, round the finished mesh as that rises out of the ground | `site(k)`: `k.footings`, `k.scaffold`, `k.stone_stack`, `k.timber_pile`, `k.hoist`. Stays inside the footprint grown by 60 cm. |
| `SM_Bld_<Name>_Damaged` | below half health | The same `complete(k)` with `k.damaged` set, then `damage(k)`. The kit does the common part by itself: merlons are lost, hung cloth is torn, `k.cloth` awnings burn to tatters, `k.breach(...)` returns real openings for `wall()`, `gable_roof(holes=...)` cuts its holes. `damage(k)` adds soot (`k.scorch`), holes in flat roofs (`k.burn_hole`), fallen stone (`k.rubble`), charred timbers (`k.charred`). |
| `SM_Bld_<Name>_Ruin` | after destruction | `ruin(k)`: `k.ruin_rect` / `k.stub` wall stumps, `k.rubble`, soot. At most a quarter of the finished height, inside the footprint. |

Damage is decided by the kit's second dice (`k.drng`), so adding damage never changes the finished mesh. Only the
finished mesh's JSON entry carries sockets and colliders; they hold for all four.

Previews: `<name>_z<zoom>.png` (finished, game camera) and `<name>_<state>.png` (every state from the tactical
camera; the site is shown round the half-risen building).

A new surface needs three entries: a texture in the generator, a slot in `MATERIALS` (`bldkit.py`) and the same
slot in `BUILDING_SLOTS` (`Tools/build_visual_materials.py`).

## Levels

A module with `LEVELS = n` (the castle 7; tower, mine, farm, the four training buildings, granary and treasury 3)
builds each level above the first as its own finished and damaged mesh: `SM_Bld_<Name>_L<k>` and
`SM_Bld_<Name>_L<k>_Damaged`. Level 1 keeps the plain names; the site and the ruin are shared by every level.
`complete(k)` reads `k.level`; `<name>.json` lists them under `levels` (mesh, triangles, bounds, slots; sockets for
the finished one). Build one level with `--level 3`; `--levels-only` renders just `<name>_L<k>.png` (game camera,
far zoom, aimed 40% up the level-1 building), and a full build also renders `<name>_L<k>_damaged.png`.

Every level reads the same way across buildings: level 1 as built; level 2 built up in stone with a slate roof or a
timber-framed storey; level 3 fortified (a tower or turret under a steep slate cap, hoardings, iron, darker stone).
The surfaces for it: `Bld_Slate`, `Bld_Iron`, `Bld_StoneDark`, `Bld_Timber`.

**The level banner** (`k.level_flag(pos, height)`): a pole with a 92 x 192 cm team-coloured banner carrying the
level's numeral, cell `level` of `T_Bld_LevelFlag` (eight 32 x 64 texel cells, numerals 1-7, drawn by
`level_flag()` in the texture generator). It is part of each level's mesh, stands at the building's front-left where
the game camera always sees it, below the label socket (the HUD's bars), and is never torn on the damaged mesh.

In the game `ASRBuilding` loads the level meshes next to the state meshes (`LoadStateMeshes`) and shows the one for
its level whenever its state changes (`SetState`, `GetLevelMesh`; a missing level keeps the one below). When an
upgrade finishes the new look goes up with a burst of dust (`ApplyLevelLook`), and the label (the HUD's bars) rises
by as much as the mesh grew. Saved games restore it through `SetLevelForLoad`. Testing: `sr.SetLevel <type|all> <n>
[enemy]`, `sr.PutBuilding <type> X Y [level] [enemy]`.

Import only some meshes: `ONLY=['castle']` takes every mesh of a module (states and levels), exact names such as
`ONLY=['castle_l3', 'castle_l3_damaged']` only those.
