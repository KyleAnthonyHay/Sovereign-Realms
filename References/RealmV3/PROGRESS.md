# Realm v3: progress (kept by the map designer for a successor)

## Design numbers (PLAN.md has the tables)
- 512 m square (HALF 256), 0.25 m cells; the sea at -6, the forest's floor 1 to 4.5 m, the basin / passes / ramps'
  feet 4 m, the plateaus 14 m, the quays -5 m; ridge crests 14 to 22.5 m over the basin, the summit 29 m.
- Point-symmetric about (0, 0). Plateau A centre (-130, 130), 164 x 148 m; castle (-130, 148); home mines (-187, 150)
  and (-73, 150); towers (-168, 100) and (-84, 100); base ramp (-78, 72, 14 m) to (-67.4, 3.7, 4 m), 18 m wide; pass to
  (-47.9, -15.7), 12 m wide; port: quay x -229..-216, y 102..142, stair (-172, 123, 14 m) to (-218, 123, -5 m).
  Everything of B: the negative. Neutral mines (31.5, 48.5) and (-31.5, -48.5); the lane from pass to pass.
- Land 183,394 m²: forest 99,840, ridges 30,550, ground a unit can reach 48,704. Plateau top 19,350 m² (16,981 free
  to build on), basin floor 6,612 m² (5,133). Trees 5,722 in the level (5,678 forest: 569 per hectare of it).
  Ground 6.70 / 2.63 / 2.32 M triangles at LOD 0 / 1 / 2 (220 tiles).

## The owner's second round (2026-11-23 evening): lower walls, plateaus twice the size
- Ridges (`ridges()` in the layout): crest height `hc = 5 + 8 peak + 4 corner` (was 15 + 33 + 22), a saddle down to
  0.42 of it within 10 to 48 m of each pass, smaller teeth and noise, `SHOULDER` 6 (10), `foot` over 4.5 m (7). The
  terraces are gone: the rock is pushed up and down in 2 m and 4.5 m columns (`shash` 796 / 797) and cut in steps of
  0.5 / 1 / 2 m whose start moves in every 3 m block (`shash` 795), heights kept to half metres. Crags: at most 9 m
  over the plateau (15). Measured on the npz: crests 14 to 22.5 m over the basin, 8 to 12 m by the passes, the summit
  29 m (a corner spine), the crags 23 m.
- Plateaus: `PA = (-130, 130, 82, 74)`, superellipse power `PP = 3` (2.5); the castle, mines, towers, plaza, roads,
  spawn, rally and port moved with it (`PORT_X = PA[0] - PA[2] - 4`); the coast 219 m (182), `HALF` 256, the sea
  `FAR` 520, the postcard camera `DIST` 900 (740); the shots', tests' and dock test's coordinates moved to match.
- `Tools/realmv3_shots.py walls <tag>`: the game's own two cameras (the overview as it opens, turned both ways and
  pulled right in; the hero's follow camera and a low look along the ground) over the plateaus, ramps, passes and
  the basin.

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

## Checks after the second round (2026-11-23 evening, PIE on L_RealmV3, Windows)
- `Tools/realmv3_test.py routes around times build stuck`: all pass (Saved/realmv3_test.log; `build stuck` again on a
  fresh match, Saved/realmv3_test_build.log: 0 failed). The new `build` spot in plateau A's south-east corner asks for
  a range: a third farm there was refused by the game's farm limit (3), not by the ground.
- Routes (path grid): castle -> the middle of the basin 224.0 m (player) and 225.7 m (enemy), 0.8 % apart; the plan
  237.2 / 236.7 m. Castle to castle 448.8 m. Own quay 99.9 m. With either pass shut (the plan): no route.
- No way round: 38 probes (forest, a coast ring 212 m out, ridges, beside the ramps, the sea cliffs by the ports):
  ground at 0; 24 routes from all over plateau A (and its quay) to plateau B: all by both ramps and both passes.
- Travel time: door to the middle 29.1 s (26.0 before: the plateau is deeper); the middle to four fifths up each
  ramp 16.5 s and 16.5 s (0.0 % apart).
- Building: barracks, farms, ranges and a tower at nine places on plateau A (its far corners too), barracks either
  side of the lane, a barracks and a range on plateau B by the enemy's Builder: none refused. Stuck: none.
- `Tools/troopship_dock_test.py realmv3`: 0 failures (docks in 1.41 s at the player's berth, gangplank out, ten
  soldiers aboard and ashore; the minimap order, a course, a patrol; and at the enemy's quay in 1.17 s).
- Symmetry: 0 cells differ from their twin; hard edges on open ground: 0.

## Checks of the first build (2026-11-23, PIE on L_RealmV3, Windows; `Tools/realmv3_test.py`)
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
| View | Realm v3 now (two runs) | Realm v3 before the second round | Realm v2 (the same PC, the same day) |
|---|---|---|---|
| base (the hero at the player's castle) | 4.08 / 4.12 | 4.06 | 4.36 |
| pass (v3) / mountain (v2): not the same view; each map's own | 8.76 / 8.70 | 7.96 | 5.26 |
| overview (the postcard: the whole map) | 7.58 / 7.52 | 6.73 | 6.94 |
- After the second round the island is bigger (5,722 trees, was 4,024, at the same density), which is what the
  overview and the pass view pay for: about 0.8 ms each. The pass view's camera is the same point as before, which
  now stands over the bigger plateau's south rim. The lower ridges added nothing (the base view is unchanged).
- Realm v2's figures in its PROGRESS.md (18.3 / 21.1 / 25.0) are the Mac's; they are not comparable with these.
- The pass view looks over the forest at 30 to 150 m, where the trees are at LOD 0 and 1: it is a millisecond dearer
  than the dearest of Realm v2's three views (6.94). With a tree every 3.75 m (4,562 trees) it was 8.17 and the
  overview 7.15; the plan has 4 m now. The LOD distances are Realm v2's (the owner's rule: none coarser at play
  distances). One run each; not measured on the Mac or packaged.
- No thermal trip: OVERHEAT.flag never appeared.

## Screenshots (Saved/Screenshots/VL/, `python Tools/realmv3_shots.py`)
Second round: `realmv3_walls_before_*` and `realmv3_walls_after_*` (`realmv3_shots.py walls before|after`: over_*,
near_*, hero_*, herolow_*, and _postcard), `realmv3_plateau_before_a/_b` and `realmv3_plateau_after_a/_b/_overview`.
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
- The island had to grow to 512 m for the bigger plateaus; the forest fills the rest at the same density, which
  costs about 0.8 ms in the overview. Thinning the forest or coarser tree LODs would win it back; neither was done
  (the owner's rules: dense forest, no coarse LODs at play distances).
- The hero's low camera at the basin's edge still sees the ridge's face fill the top of the frame (14 m and more of
  rock 20 to 30 m away); from the overview and the postcard the basin and both plateaus are now clear.
- Rebuilding: a change of ground needs `realmv3_rebuild.ps1` (about 60 minutes now: Blender 10, import 30, LODs 12,
  level 3);
  things moved only: `realmv3_rebuild.ps1 layout`.
