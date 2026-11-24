# Realm v2: progress (kept by the map designer for a successor)

## Design numbers
- 640 m square (HALF 320), 0.25 m cells; all low rivers at -3 m (banks at 0 at every bridge), north inflows at +7 m.
- Mountain (owner's feedback, 2026-11-22: "twice that size, more peaks, intimidating, huge"): massif polygon `M_POLY`
  about 200 x 240 m (it was 200 x 165), eleven peaks (`PEAKS`), summit 216 m over the plain (it was 125 m, before that
  95 m). It cannot be wider: the two rivers, the north crossing's saddle and the centre-east mine's wall bound it; it grew
  north instead, and the way round its north (`NORTH_WAY`) is kept open.
- Ruins plateau 12 m, upper terrace 22 m, bluffs 7 m, hill towers 8 m, mounds 3 m.
- Player castle south-west (-176, -118), enemy north-east (246, 152). Mines: mine0 (west bluff), mine1 (north bluff),
  mine_nw, mine_c (centre-east, in the mountain's wall), mine_se.
- Sky (owner's feedback): `AVLSky` (`Source/VoxelLab/VLSky.*`): 29 voxel clouds (11 round the mountain at 92 to 150 m,
  12 banks beyond the edges, 6 wisps over valleys; a cloud is puffed away when the camera is within 70 m or rises to
  12 m under it) and 7 flocks of 6 birds (62 to 226 m). Placed by `realmv2_layout._sky()` -> `build_realmv2.sky()`.
  The project had no birds (only the deprecated main game's `SRBirds`, a procedural mesh); the loop / beat / glide idea
  is taken from it.

## 2026-11-23: open sea all round (owner: "increase the circumference of the map area so the ship has more room")
- The map is 780 m square (it was the ground tiles' 640): `MAP_EDGE = 390` in `Tools/ue/build_realmv2.py` places a
  `MapEdge` slab (invisible, no collision, tagged Ground) 2 x 390 m square at the seabed. The path grid takes its
  bounds from the Ground meshes, and from those bounds come the overview's whole-map zoom (now 3,727 m) and its pan
  limits, the minimap, the troop ship's chart (840 m: 30 m more each way), the water look and the AI's maps. The
  coast reaches 309 m from the middle at most and the islets 319 m: 81 m of open sea beyond the coast, 71 m beyond the
  islets. Every new cell is under water, so no unit stands there (`vl.Path` to the new sea: "no walkable ground").
- The sea mesh reaches 1,700 m from the middle (`FAR` in `realmv2_terrain.py`, was 600) and the seabed slab is
  3,600 m square, so the overview all the way out, panned to the edge, sees no end to the water.
- Grid 1560 x 1560 cells of 50 cm. Checks: `Tools/troopship_dock_test.py realmv2`: 0 failures, including the new
  `lap` (an eight-point course on a ring 350 m out, all the way round in 324 s, afloat throughout).
  `Tools/realmv2_test.py routes stuck`: pass (`stuck` now skips a tower's archers on its platform).

## Files
- Tools/blender/realmv2_layout.py (plan; `--debug` -> Saved/realmv2_plan.png + balance table), realmv2_cam.py,
  assets/realmv2_terrain.py, assets/ruins.py, Tools/ue/build_realmv2.py, Tools/realmv2_rebuild.sh,
  Tools/realmv2_test.py (routes, build, stuck).
- Game wiring: VLHUD.cpp / VLHUD.h / VLHUDMenus.cpp (map 0 = Realm v2, 1 Realm, 2 Flatlands, 3 Highlands),
  VLGameMode.cpp (`vl.Map realmv2`), VLAIWorld.cpp (realmv2.json), Config (MapsToCook, EditorStartupMap).

## Done
- Plan, terrain, water, backdrop, barriers, ruins, level, menu wiring; routes / build / stuck checks pass (first mountain).
- Town and Village removed from menus and configs.

## Next (in order)
1. Rebuild with the big mountain + sky; screenshots; rerun `Tools/realmv2_test.py`.
2. Delete L_Town / L_VoxelVillage and the assets only they use (scratchpad script `town_village_assets.py`: asset
   registry closure of the two maps minus the other four maps' closure minus anything named in code).
3. README section "Realm v2"; package (`sh Tools/package.sh`).

## 2026-11-22, later: new owner direction (not all done yet: see "State" below)
Owner's words relayed by the coordinator, in order:
1. Mountain "good job" (184 m, 11 peaks, benches with forest). Keep.
2. Tower rule (firm): NEVER a tower on a round drum with sheer walls and stairs (References/Remake/tower_cylinder_bad.png).
   Level ground, or a natural mound in wandering shelves. Realm v2: done in the plan (`KNOLLS`, home towers at level 0).
   L_Realm: plan changed (`realm_layout.py`: towers at their side's level 1, no drum, no flight); level rebuild pending.
3. Too much open land: pockets to build in, ringed by dense forest; low hills; hill plateaus with trees on top; the
   ravine significantly deeper and wider (References/RealmV2/terrain_pockets.png).
4. More space behind (north of) the mountain.
5. The map is an ISLAND (References/RealmV2/layout_island_suggestion.png = the new layout direction): sea all round,
   cliffs, beaches, rocky shores, a few islets; water channels round the mountain and plateau, falls off terraces;
   player SW, enemy NE, each with a fortified PORT (References/RealmV2/port.png: quay on pilings, crane, green-roofed
   warehouse with anchor banner, arch into the cliff, stairs up the cliff, harbour tower, rowing boat, a ship moored:
   the art agent is making the ship, probably SM_GrainBoat; leave a mooring, use SM_Boat until it exists).
   Five mines stay (W, NE homes; NW, centre-east, SE neutral). Scenery only.
6. Performance pass wanted (PIE was 24-27 ms GPU): ground LODs added (`merge_far`, `Tools/ue/realmv2_lods.py`:
   5.87 M faces -> 2.20 M (LOD 1, from 110 m) -> 1.76 M (LOD 2, from 280 m), same shape); backdrop joined (0.70 -> 0.52 M).
   `sh Tools/realmv2_perf.sh [profile]` measures three views.
7. No final package by this agent (the coordinator builds). A snapshot was packaged once (before the island direction).
8. Starting troops rule left as is (coordinator raises it with the owner).

Plan for the island (how to do it in the existing scripts):
- `rim_hills` -> a `COAST` polygon + islets as in highland_layout.py (ragged ledges, rocks, `softground.islet`); sea
  mesh `SM_RealmV2Sea` (highland_terrain.build_sea) + seabed slab; no backdrop mesh at all.
- Rivers become channels open to the sea at both ends at the sea's level (WAT = SEA = -6: ravines 6 m deep, 16 m wide,
  terraced walls); no north falls (`RIVER_UP`, `UPN` go).
- Mountain's north edge pulled back (about 15 m) for more ground behind it.
- Forest: `wood()` dense everywhere but the pockets (`FLATS` build), roads and a few glades; more `KNOLLS`-style hills.
- Ports: `assets/ports.py` (quay, crane, warehouse, harbour tower, arch), a stair down the sea cliff (a `RAMPS` STONE
  entry), SM_Boat moored until the ship exists.

## State (2026-11-22, about 02:50)
- The island is in the plan and the scripts: `COAST`, `ISLETS`, `BEACHES`, `PORTS`, `HILLOCKS`, `KNOLLS`, WAT = SEA = -6,
  wider channels, bridges on necks of land, dense forest (TREES D 3300), mountain's north pulled back, no backdrop
  (`SM_RealmV2Sea` instead), `assets/ports.py` (4 meshes), README rewritten for it.
- Town/Village deleted (maps + 76 assets; fences kept). Tower rule in the README; `realm_layout.py` changed.
- Running in the background (log: Saved/realmv2_rebuild.log, ends with V2DONE then REALMDONE):
  `realmv2_rebuild.sh ruins` -> `realmv2_rebuild.sh` (Blender, import of 1200 tile meshes about 40 min, LODs, level)
  -> delete SM_RealmV2Backdrop -> `realm_rebuild.sh` (L_Realm with its towers on level ground).
- After that: `sh Tools/realmv2_perf.sh`, PIE + `Tools/realmv2_test.py routes build stuck` on L_RealmV2, screenshots
  (pie.py; `vl.View free X Y Z Pitch Yaw FOV` in UE cm), `Tools/realm_test.py routes` on L_Realm (tower reachable),
  fill the island's numbers into the README's "Cost" bullet, release the lock
  (`sh Tools/editor.sh quit; rmdir Saved/editor.lock`). No package (the coordinator builds).
- The ship: `realmv2_layout.SHIP` picks SM_GrainBoat if SourceArt/Meshes/SM_GrainBoat.gltf exists when the plan runs,
  else SM_Boat; moorings: the instances tagged `Moored` (west pier about (-311, -163), east pier about (311, 164)).

## State (2026-11-22, end of the map designer's session)
- Built and saved: L_RealmV2 (the island: 387 tiles with LODs, sea, ports, sky) and L_Realm (towers on level ground).
- Checks on L_RealmV2 (PIE): `realmv2_test.py routes build stuck`: 0 failed. L_Realm: `realm_test.py routes`: the two
  tower routes found, units on the ground.
- PIE GPU ms (base / mountain / whole map): 18.3 / 21.1 / 25.0; L_Realm the same way 18.1 / - / 23.2.
- Not done: no package (the coordinator builds); the ship is still SM_Boat (SM_GrainBoat did not exist: run
  `sh Tools/realmv2_rebuild.sh layout` once it is in SourceArt/Meshes and imported); the highlands' and the Flatlands'
  towers still stand on the old mounds; the packaged frame time is not measured; the starting troops rule is unchanged.
- Screenshots: Saved/Screenshots/VL/realmv2_overview.png, realmv2_scale.png, realmv2_mountain.png, realmv2_base.png,
  realmv2_port.png, realmv2_mine.png, realmv2_ravine.png, realm_tower.png.
