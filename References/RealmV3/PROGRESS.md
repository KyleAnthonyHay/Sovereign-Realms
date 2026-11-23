# Realm v3: progress (kept by the map designer for a successor)

## Design numbers (PLAN.md has the tables)
- 416 m square (HALF 208), 0.25 m cells; the sea at -6, the forest's floor 1 to 4.5 m, the basin / passes / ramps'
  feet 4 m, the plateaus 14 m, the quays -5 m, the summit 66 m.
- Point-symmetric about (0, 0). Plateau A centre (-112, 114), 120 x 108 m; castle (-112, 130); home mines (-153, 128)
  and (-71, 128); towers (-142, 84) and (-80, 104); base ramp (-78, 76, 14 m) to (-67.4, 3.7, 4 m), 18 m wide; pass to
  (-47.9, -15.7), 12 m wide; port: quay x -189..-176, y 86..126, stair (-132, 107, 14 m) to (-178, 107, -5 m).
  Everything of B: the negative. Neutral mines (31.5, 48.5) and (-31.5, -48.5); the lane from pass to pass.
- Land 127,425 m²: forest 70,595, ridges 24,604, ground a unit can reach 28,487. Plateau top 9,090 m² (7,185 free to
  build on), basin floor 6,612 m² (5,133). Trees 4,024 (3,994 forest: 566 per hectare of it; LOD 2 total 4.31 M faces,
  Realm v2's 3.84 M).

## Files
- Tools/blender/realmv3_layout.py (the plan; `--debug` -> Saved/realmv3_plan.png, `--balance` the routes),
  realmv3_cam.py, assets/realmv3_terrain.py (tiles + far levels, `SM_RealmV3Ramps`, `SM_RealmV3Sea`,
  `SM_RealmV3Barrier`), Tools/ue/build_realmv3.py, Tools/ue/realmv3_lods.py, Tools/windows/realmv3_rebuild.ps1
  (`layout` / `blender` / `import` / `level`), Tools/mac/realmv3_rebuild.sh, Tools/realmv3_test.py
  (`routes around times build stuck`), Tools/realmv3_shots.py, Tools/windows/realmv3_perf.ps1, Tools/mac/realmv3_perf.sh.
- Game wiring: VLHUD.cpp / VLHUD.h / VLHUDMenus.cpp (map 5 = Realm v3; New Game shows six maps, v3 third),
  VLGameMode.cpp (`vl.Map realmv3`), VLAIWorld.cpp (realmv3.json), Config/DefaultGame.ini (MapsToCook).
  The overview's furthest zoom (de76f37) needed nothing: it reads the path grid's bounds ("the whole map
  (416 x 416 m) is in view at 1981 m" in the log).
- The tools' python on Windows: `Tools\.venv\Scripts\python.exe` (made from the engine's python: numpy, scipy, pillow).

## Three things a successor must know
1. **The lid.** The game's path grid calls the largest connected piece of standable ground "the map". Here the
   forest's floor is three times the playable ground, so the first build's grid took the forest for the map and found
   "no walkable ground" at either castle. `SM_RealmV3Barrier` therefore carries, besides the walls, a sheet at chest
   height over all the ground behind them (`build_barrier`, "the lid"): the grid's body test finds it and makes no
   node there. Grid now: 143,292 nodes, the main region 111,401 (it was 372,212 nodes, the main one the forest).
2. **The ramps' sheet.** The voxel ground rises in quarter-block shelves; the owner read the ramps as stairs. The
   base ramps and their shoulders are covered by `SM_RealmV3Ramps` (tagged Ground): the mesher's own top faces on
   the true slope, the voxels up to a quarter block under it (`G["sheet"]`, `build_sheet`). Things stand on
   `G["top"]`; the npz's `h` is that top, `voxels` the voxels.
3. **A pass begins square at the ramp's foot** (`ramp_fields`, `act`): its floor's round end once cut a 1.25 m step
   across the ramp's last metres, which the plan's route got round along the edges and the game's did not.

## Checks (2026-11-23, PIE on L_RealmV3, Windows; `Tools/realmv3_test.py`, the log in Saved/realmv3_test.log)
- 121 checks passed. One failed in the full run: a barracks for the enemy's Builder behind its castle, refused as
  "too uneven" (the enemy's commander had built on the place asked for, and the nearest spot left was on the rim).
  The test now asks at up to three places on the enemy's plateau; `build stuck` run again on a fresh match: 11 of 11.
- **Routes** (path grid): player castle -> the middle of the basin 199.3 m, enemy 199.9 m (0.3 % apart); castle to
  castle 405.2 / 405.7 m; own quay 80.0 / 79.0 m; the other side's quay 453.0 / 454.4 m. Every route off a plateau
  goes by its ramp and its pass; every route to the other side by both ramps and both passes; a route to a quay by
  that side's stair.
- **No way round**: 38 probes in the forest, on the coast (a ring 176 m out), on the ridges, beside the ramps and on
  the sea cliffs by the ports: the path grid has ground at 0 of them. 24 routes from all over plateau A (and its
  quay) to plateau B: 24 by both ramps and both passes. The plan, with either pass shut: no route.
- **Travel time** (the hero running): the player's door to the middle 26.0 s; from the middle to four fifths up each
  ramp 16.9 s on the player's side and 16.9 s on the enemy's (0.0 % apart). The enemy's castle and towers kill the
  hero at its door, so the two sides are compared from the middle outwards; the enemy's whole walk door to middle
  was not timed.
- **Building**: barracks, farms, an archery range and a tower laid on plateau A (six places), barracks in the basin
  either side of the lane, a barracks and a range on plateau B by the enemy's Builder.
- **Stuck**: every unit on the plan's ground.
- **Symmetry**: cells whose height differs from their twin's: 0. Hard edges on open ground: 0 cells.

## Frame time (PIE GPU ms, this PC, VSync on so every frame is 16.67 ms; `realmv3_perf.ps1` / `realmv2_perf.ps1`)
| View | Realm v3 | Realm v2 (the same PC, the same day) |
|---|---|---|
| base (the hero at the player's castle) | 4.06 | 4.36 |
| pass (v3) / mountain (v2): not the same view; each map's own | 7.96 | 5.26 |
| overview (the postcard: the whole map) | 6.73 | 6.94 |
- Realm v2's figures in its PROGRESS.md (18.3 / 21.1 / 25.0) are the Mac's; they are not comparable with these.
- The pass view looks over the forest at 30 to 150 m, where the trees are at LOD 0 and 1: it is a millisecond dearer
  than the dearest of Realm v2's three views (6.94). With a tree every 3.75 m (4,562 trees) it was 8.17 and the
  overview 7.15; the plan has 4 m now. The LOD distances are Realm v2's (the owner's rule: none coarser at play
  distances). One run each; not measured on the Mac or packaged.
- No thermal trip: OVERHEAT.flag never appeared.

## Screenshots (Saved/Screenshots/VL/, `python Tools/realmv3_shots.py`)
realmv3_overview, _plan, _threequarter, _plateau_a, _plateau_b, _ramp_a, _ramp_b, _ramp_a_low, _ramp_b_low,
_ramp_a_down, _pass, _pass_floor, _basin, _basin_mine, _dock_a, _dock_b, _dock_a_stair, _forest, _forest_canopy,
_coast, _base. The first build's ramps and plateaus, for comparison: Saved/Screenshots/VL/before/
(realmv3_ramp_a, _plateau_a, _plateau_b, _overview, _pass).

## Not done / to review
- No package (the coordinator builds). The Mac has not built or measured this map.
- The sea's depth: left to the shared water material (the boat's agent). Nothing in this map forks it: the sea is
  `SM_RealmV3Sea` with the `water` slot, as Realm v2's. The seabed is the flat slab at -8 m; the coast's rocks reach
  3 m out and the six islets (4 to 5 m rocks) stand 16 to 20 m off the cliffs: a ship's route round the island must
  keep 25 m off, or the islets go (`ISLETS` in the plan).
- The ports are scenery, as Realm v2's (quay, warehouse, crane, arch, harbour tower, `SM_Dock` with the ship
  `Moored`); units walk the stair, the quay and the pier.
- The forest is not walkable anywhere (a decision: it keeps the map to its gameplay and makes "no way round"
  certain). If the owner wants glades or a walkable verge, they are `region` in the plan.
- The ramps' sheet is the one piece of ground on any map that is not voxel shelves. If the owner wants the same on
  other maps' ramps, `build_sheet` is the recipe.
- The Test World still opens Realm v2.
- Rebuilding: a change of ground needs `realmv3_rebuild.ps1` (about 35 minutes: Blender 10, import 20, level 3);
  things moved only: `realmv3_rebuild.ps1 layout`.
