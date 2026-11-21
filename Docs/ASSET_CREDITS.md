# Asset credits

Every outside asset in the natural-world pass, with where it came from and what it may be used for. Everything
else in the world (the pixel-art textures, the meshes, the maps, the water ripple and foam textures) is made by
this repository's own scripts.

## Poly Haven textures (CC0)

Licence: **CC0 1.0** (public domain dedication). Poly Haven's licence page, https://polyhaven.com/license, says:
"Our assets are all licensed as CC0", "You can use our assets for any purpose" (commercial work and products for sale
included) and "You do not need to give credit". Credit is given here anyway.

Downloaded 2026-11-19 through Poly Haven's public API (`https://api.polyhaven.com/files/<id>`) into
`SourceArt/Textures/PolyHaven/<id>/` (the diffuse and the OpenGL normal map of each, JPG; 39 MB in all; the roughness
maps were not kept). Imported by `Tools/import_world_assets.py` (`import_nature`) to
`/Game/SR/Textures/Nature/T_N_<Name>_D` / `_N` (normal maps with the green channel flipped for Unreal).

| Poly Haven id | Page | Size | Asset in the game | Used by |
| --- | --- | --- | --- | --- |
| `aerial_rocks_02` | https://polyhaven.com/a/aerial_rocks_02 | 2k | `T_N_AerialRock_D`, `_N` | `M_Terrain`: the mountains' rock seen from above (crags) |
| `cliff_side` | https://polyhaven.com/a/cliff_side | 2k | `T_N_Cliff_D`, `_N` | `M_Terrain`: the strata on standing rock faces |
| `rock_face_03` | https://polyhaven.com/a/rock_face_03 | 2k | `T_N_RockFace_D`, `_N` | `M_Terrain`: the rock's fine grain; `M_Rock`: boulders, scree, standing stones |
| `mossy_rock` | https://polyhaven.com/a/mossy_rock | 1k | `T_N_MossRock_D` (`_N` imported, unused) | `M_Terrain`, `M_Rock`: lichen on sky-facing rock |
| `aerial_grass_rock` | https://polyhaven.com/a/aerial_grass_rock | 2k | `T_N_AerialGrass_D` (`_N` imported, unused) | `M_Terrain`: the turf's wide blotches of colour |
| `leafy_grass` | https://polyhaven.com/a/leafy_grass | 1k | `T_N_Grass_D`, `_N` | `M_Terrain`: the turf's light and dark, and its normal detail |
| `brown_mud_leaves_01` | https://polyhaven.com/a/brown_mud_leaves_01 | 1k | `T_N_Mud_D` (`_N` imported, unused) | `M_Terrain`: wet mud and leaf litter at the water's edge |
| `river_small_rocks` | https://polyhaven.com/a/river_small_rocks | 1k | `T_N_Pebbles_D`, `_N` | `M_Terrain`: earth roads, the scree lip; `M_Water`: the bed seen through the shallows |
| `forrest_ground_01` | https://polyhaven.com/a/forrest_ground_01 | 1k | `T_N_Forest_D`, `_N` | `M_Terrain`: the forest floor under a closed canopy (phase 2) |

Already in the repository before this pass (see `SourceArt/Textures/Sources/PolyHaven/CREDITS.md`): the two Poly
Haven photographs `T_MountainRock` and `T_Snow` are made from, also CC0.

## Made here (no outside source)

| Asset | Made by |
| --- | --- |
| `T_N_WaterWaves_N` (ripple normals), `T_N_WaterNoise` (foam breakup, cloud, grain, streaks) | `Tools/textures/gen_nature_textures.py` (spectral and cellular noise, tileable) |
| `T_WaterFlow`, `T_WaterFlow4` (each river's current, the water's depth, the damp banks) | `Tools/world/gen_battlefield.py` (`build_flow_map`) |
| `T_WaterMap`, `T_WaterMap4` alpha (where ground mist pools) | `Tools/world/gen_battlefield.py` (`build_water_map`) |

Phase 2 (forests, leaves, fire) brought in **no outside asset**: everything below was made here.

| Asset | Made by |
| --- | --- |
| `T_Leaves`, `T_LeavesBirch`, `T_LeavesMaple`, `T_BarkBirch`, `T_Undergrowth` | `Tools/textures/gen_forest_textures.py` (drawn in code from small palettes) |
| `SM_Tree_Oak_*`, `SM_Tree_Maple_*`, `SM_Tree_Birch_*`, `SM_Tree_Snag`, `SM_Bush_*`, `SM_Under_*`, `SM_Log_*`, and every tree's far-view mesh | `Tools/world/props.py` (`build_forest_meshes`) |
| `T_Forest`, `T_Forest4` (the canopy and its shade) | `Tools/world/gen_battlefield.py` (`build_forest_map`) |
| `M_FX_Flame`, `M_FX_Smoke`, `M_FX_Embers`, `M_Leaves` (procedural: no textures) | `Tools/build_fx_materials.py` |

## Considered and not used

| Thing | Why not |
| --- | --- |
| ambientCG (https://ambientcg.com, CC0) | Equally usable; Poly Haven alone covered what the pass needed. A good second source for phase 2 (bark, leaves, forest floor). |
| Unreal's Water plugin / Single Layer Water shading | See `Docs/VISUAL_AUDIT.md` > Water: tied to Landscape and water-body actors, and the forums carry open Mac / Metal reports; the generator's own meshes and data maps do the job on every platform. |
| Quixel / Fab "free" assets | Licence is per-account and tied to Unreal use; not CC0, so kept out. |
