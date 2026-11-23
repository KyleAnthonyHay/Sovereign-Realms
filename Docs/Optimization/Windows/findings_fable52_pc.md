# Windows PC optimization audit (Fable 5.2)

Date: 2026-11-23, branch `windows-support` at `bc883c7`. A read-only audit; the evidence is the code in
`Source/SovereignRealms`, the engine source in `UE_5.8/Engine/Source`, and the captures in `Saved/Perf/1080p` and
`Saved/Perf/1440p` (every CSV column, the `ProfileGPU` tables in `game.log`, the log's timestamps). Gains are estimates
unless a line says "measured"; each one names the measurement that would confirm it. (The auditor's write of this file
was refused by the harness, so the orchestrator saved it from the auditor's report; the merged plan is `PLAN.md`.)

## Summary

Where the frame goes at the 1080p overview (23.7 ms a frame, mean ms):
- Game thread 23.7: `CharacterMovement` 13.7, `WorldTickMisc` 2.8 (the rig's late pose pass), `TickActors` 2.4, `UI` 2.0,
  `Tickables` 0.9 (mean, with spikes to 31), `QueueTicks` 0.5 (median), the rest about 1.4.
- Render thread: about 10 ms of real work.
- GPU: 11.7 ms, of which 3.7 ms is 12,990 individual occlusion queries.

Three things the baseline write-up has wrong, all visible in the CSVs:
- The "stuck and failed to move" lines are not the cost. They are about 4 events a second against about 18,800 movement
  ticks a second. The 11-14 ms is the steady price of 313 movement components sweeping a capsule and a box against
  per-triangle ground collision every frame, idle or not.
- The 196 / 240 ms hitch is not the camera jump. It is `Tickables` (175.6 / 218.1 ms in that frame): the two enemy
  commanders planning Raid #5 at match clock 2:24.
- The poor 99th percentile is periodic, not random: a 24-40 ms `Tickables` spike every 2.45 s, a 17-20 ms `TickActors`
  spike every 1.22 s, plus 3-6 ms every 0.25 s.

Top 5 changes:
1. FP-01: the ground tiles collide with their LOD 2 triangles (the same shape, 3.3 times fewer faces). 3.5-6 ms game
   thread (estimate).
2. FP-02 / 03 / 04: movement asleep for garrisoned units, no floor sweep for standing units, then a general sleep.
   1.5-3 ms in this benchmark, more in a normal match.
3. FP-05 / 06: a route-search memo, a tighter A* inner loop, the raid's searches in parallel. The 196-240 ms hitch down
   to 30-50 ms, and the periodic spikes mostly gone.
4. FP-07: unit parts never occlusion-queried. 3.7 ms GPU at the 1080p overview (4.9 at "1440p"), 1.5-2.5 ms render
   thread (estimate).
5. FP-08: `r.Nanite=0` on Windows after an A/B. Up to 1.1-1.7 ms GPU and about 2,450 draws off the render thread.

After FP-01 to FP-04 the game thread should be near 14-16 ms at the overview. The render thread (10-16 ms) and the GPU
(11.7 ms) then become the next limits, which is why FP-07 and FP-08 are in the early batches.

## Measurement notes (read before comparing any new run with the baseline)

- **The "base" view is empty.** With `AIvsAI=2` the player's king is benched off the map (`VLBattle.cpp:2952-2970`), and
  `vl.View follow` follows him. `base.csv` has `DrawCall/Basepass` 3, `RHI/DrawCalls` 101 (median), GPU 3.9 ms. The base
  row is the game thread alone, and it still proves `CharacterMovement` costs 10.9 ms with nothing on screen.
- **"1440p" is 2194 x 1234.** `1440p/game.log:2106` says `window: kept as a window 2194 x 1234`, and TSR runs
  `1462x822 -> 2194x1234`. At 1080p TSR runs `1400x788 -> 1920x1080`. "Render scale 100 %" means the engine's automatic
  screen percentage (67-73 %), not native.
- **CSV rows are offset by one.** A row's `FrameTime` belongs to the previous row's thread timers.
- **The two runs are different matches**, so spike sizes differ between them for reasons other than resolution.
- **One side's field squad is jammed for the whole capture.** 104 (later 100) units are ordered to `(-4212, 3237, 1200)`
  every 6-9 s and end "at the end of their way" near `(-5100, 500)` on a steep climb. Every "stuck" line comes from that
  pile.
- **This was a Development build.** Confirm the targets in Shipping once the changes are in.

## Status of `PLAN.md` in the current code

Verified present:
- A1: one batched write (`VLKingRig.cpp:383-455`).
- A2: `Figure` absolute (`VLKingRig.cpp:352-358`).
- A3: `RigLate` (`VLKingRig.cpp:551-649`).
- A4: lazy `EnsureCameraRig`; the troops' dust destroyed (`VLKing.cpp:402-407`).
- A5: `VLKing.cpp:319-327`.
- A6: `VLKingRig.cpp:564-584`.
- B1 / B2: `UnitsNear` in `AutoSteer` and `FindFoe`.
- B4: `UnitsThisFrame` and batched rectangles.
- C1 and C6: `DefaultEngine.ini`.
- D6: `GRID timing (worker threads)`, 757 ms.
- E: the ground LODs (`realmv2_lods.py`). The tree and unit LODs were not re-checked.

Still open, and now the measured bottlenecks:
- "Character movement tick off for idle troops" (the deferred C-05 / F-18): FP-02 to FP-04.
- "Shared floods, path-search budgets, route caches" (the deferred F-20 / 61S-18, described as "unmeasured"): now
  measured, FP-05 / FP-06.
- "Staggered auto-combat" (deferred): FP-10 gives an exact alternative.
- "Instanced unit parts" (deferred): FP-15.
- "Incremental grid connectivity" (deferred): FP-13.

## Findings

### FP-01  Ground collision uses every LOD 0 triangle: point it at LOD 2 (the same shape)
- Area: game thread
- Where: `Tools/ue/import_assets.py:200-204` (`collision` defaults to `"complex"`, i.e. `CTF_USE_COMPLEX_AS_SIMPLE`);
  `SourceArt/Meshes/SM_RealmV2Ground_*.json`; `Tools/ue/realmv2_lods.py:44-52`; `VLKing.cpp:75-93`.
- Evidence:
  - `CharacterMovement` is 10.9 / 12.2 / 13.7 ms at 1080p for 313 components (35-44 us each), and 10.9 ms in the empty
    base view. The unit's own work is elsewhere (`TickActors` 1.6-2.6 ms; the rig in `WorldTickMisc`), so this is
    engine movement time.
  - Per tick the engine does one capsule sweep (`MoveAlongFloor`), one box sweep down (`FindFloor` with
    `bUseFlatBaseForFloorChecks`, `CharacterMovementComponent.cpp:7235-7238`), and three more sweeps plus a floor find
    on every 50 cm step up. All of them run against the render mesh.
  - README "Cost": 387 tiles, 5.40 M faces at LOD 0, 2.02 M at LOD 1, 1.64 M at LOD 2. LOD 1 / 2 are "the same shape"
    (coplanar same-material faces merged into quads of up to 1 m / 4 m).
  - The engine builds the collision triangle mesh from `UStaticMesh::LODForCollision` (`StaticMesh.cpp:9295`) and
    resolves a hit face's material from the same LOD (`StaticMeshComponent.cpp:3114`), so the footstep surfaces keep
    working.
- Change (ASSET, reproducible): in `realmv2_lods.py`, after `set_lod_screen_sizes`, add
  `dst.set_editor_property("lod_for_collision", 2)`. The script already saves every tile, so 387 assets change. Other
  maps only if their tiles have same-shape LODs.
- Expected gain: 3.5-6 ms of `CharacterMovement` at the overview (estimate, 25-45 %). Also faster arrow and aim traces,
  grid build (646 ms of floors) and `UpdateFarFog`.
- Risk: M. The surface is the same, but the triangle edges move. Check that the path grid is identical (1,096,134 nodes,
  22,159 regions, D6's checksum compare), that `SurfaceUnder` returns the same surfaces, and that 50 cm steps and arrow
  hits are unchanged.
- Platforms: both.
- Verify by: before changing anything, one Insights CPU trace (`-trace=cpu,frame`, 10 s) to see how much of
  `CharacterMovement` is under the sweep calls; if under a third, drop this item. After: the same capture,
  `Tools/realmv2_test.py` (`routes`, `stuck`), and an AI-vs-AI match.
- Confidence: medium (the mechanism is certain, the size is unmeasured).

### FP-02  Garrisoned units and tower guards: movement component asleep
- Area: game thread
- Where: `VLCommand.cpp:1251-1275` (`Enter`) and `1277-1310` (`Leave`); `VLBattle.cpp:2141` onward (`TickTowerGuards`,
  `bTowerGuard` set at 2242).
- Evidence: the 1080p log has 51 "Tower Archer ... takes post" lines. These units never walk, yet each runs a full
  movement tick with a floor sweep every frame (`bAlwaysCheckFloor` true by default, `CharacterMovementComponent.cpp:798`).
  That is 51 of 313 components, 16 %.
- Change: once a garrisoned unit stands (`IsMovingOnGround()` and zero velocity, checked in the existing guard / garrison
  tick, not in `Enter`, because it is placed 4 cm above the floor), call
  `GetCharacterMovement()->SetComponentTickEnabled(false)`. Turn it back on in `Leave` before the teleport, in `Die`, and
  when its tower falls. Archers turn with `SetActorRotation` (`VLArcherCombat.cpp:920`), which needs no movement tick.
- Expected gain: 0.8-1.5 ms at every view in this benchmark (estimate).
- Risk: L. One helper `SetMovementAwake(bool)`, plus a wake in `FollowPath` as a safety net.
- Platforms: both.
- Verify by: `Ticks/CharacterMovementComponent` drops by the number garrisoned; tower archers still shoot, come down on
  an order, and die with their tower.
- Confidence: high.

### FP-03  `bAlwaysCheckFloor = false`: standing units stop sweeping the floor
- Area: game thread
- Where: `VLKing.cpp:78-93`.
- Evidence: the engine's `FindFloor` (`CharacterMovementComponent.cpp:7235-7269`). With the flag false, a zero-delta tick
  reuses `CurrentFloor` when the base is valid, has query collision, blocks the capsule's channel and is not a movable
  base; otherwise it sweeps as now. Teleports still find the floor (`OnTeleported`, line 6534).
- Change: `Move->bAlwaysCheckFloor = false;` in the constructor.
- Expected gain: 0.5-1.5 ms in this benchmark (estimate), more in a normal match.
- Risk: L-M. A floor that vanishes under a standing unit without its collision being switched off would go unnoticed
  until the unit moves. The game razes with `SetActorEnableCollision(false)` (`VLBattle.cpp:1338`), which the engine's
  check covers. Test a tower falling under its archers, a razed building with units on its steps, and the water rescue.
- Platforms: both.
- Verify by: `CharacterMovement` with the armies standing, against the baseline.
- Confidence: high for the mechanism, medium for the size.

### FP-04  General movement sleep for standing units (the deferred C-05 / F-18)
- Area: game thread
- Where: `VLKing.cpp:2512-2547` (`PollInput`; `AddMovementInput` at 2536 / 2540 / 2894), `VLSwordsmanCombat.cpp:454`,
  every teleport (`SetActorLocation*` in `VLCommand.cpp`, `VLConstruction.cpp`, `VLKing.cpp:737, 3311`), and
  `VLKing.cpp:3253-3320` (`Die`, `Revive`).
- Evidence: after FP-03 a standing unit's tick is cheaper but not free: input consumption, `PerformMovement`, the scoped
  update and the tick dispatch (`QueueTicks` 0.2-0.5 ms for about 1,010 ticks).
- Change: sleep when all of these have held for 0.5 s: walking mode, zero velocity, no pending input, a walkable floor,
  not played by the player, not dead. Wake in one place, `AVLKing::WakeMovement()`, called from:
  - an `AddMovementInput` override (virtual on `APawn`), before the input is added so the first step isn't lost;
  - `FollowPath`, `YieldTo`, `ReceiveDamage`, `Revive`, `TakeControlOf` and every teleport helper;
  - all units inside the area whenever `UVLGrid::RebuildAreas` runs.
- Expected gain: most of `CharacterMovement` in a normal match; here 1-2 ms on top of FP-02 / FP-03 (estimate).
- Risk: M. A missed wake leaves a unit frozen or floating, so put it behind `vl.Opt.MoveSleep 0|1`.
- Platforms: both.
- Verify by: `Ticks/CharacterMovementComponent` over a match; AI-vs-AI with the cvar on and off;
  `Tools/realmv2_test.py stuck`.
- Confidence: medium.

### FP-05  Route searches: a memo for identical searches, and a tighter A* inner loop
- Area: hitches / game thread
- Where: `VLGrid.cpp:981-1048` (`Flood`) and `1089-1218` (`FindGroupPaths`, `FindPath`); `VLGrid.h:72-79` (`FNode`, 48
  bytes). Callers: `VLKing.cpp:647-657` (the stuck replan), `VLEnemyAI.cpp:498-505` (`RouteDefence`),
  `VLAISquads.cpp:676-683` (`PlanAttack`), `VLAISquads.cpp:787-796` and `1255-1265` (the flank evaluation).
- Evidence (the grid is 1280 x 1280, 1,096,134 nodes; rows shifted by one):
  - `Tickables` is 28-31 ms every 103 frames (2.45 s) at the 1080p overview (frames 5, 108, 211, 314, 417, 521), 38-41 ms
    at the "1440p" overview, and 24 ms in the 1440p base.
  - 2.45 s is every fourth commander think (`Prof.Think` 0.6 s, `StrategyEvery` 2 s, `VLEnemyAI.cpp:63-66`). The path is
    `ChooseStrategy` -> `PlanAttack` -> `RouteDefence` -> `FindPath` (read from the code, not profiled), so one
    cross-map search takes about 10-13 ms.
  - `TickActors` is 17.2-20.4 ms every 1.22 s in both 1440p captures, four in a row then a pause. That matches
    `AutoSteer`'s `StuckCount >= 2` replan (0.6 s twice, `Replans < 4`) and the log's "GAVE UP ... (4 fresh routes)" lines
    (28 for farmers at 1080p).
  - These spikes add 0.23-1.05 ms a frame on average and make up the gap between the median and the 99th percentile
    (24.2 against 62.2 at the 1440p overview).
  - In `Flood`, each of the 8 neighbours of every expanded node reads `Nodes[J].bNearWall` from a 48-byte struct (a
    likely cache miss on a 52 MB array), and every pop does a `TSet::Remove`.
- Change (routes stay identical):
  1. A memo in `FindGroupPaths` for the one-walker case. After the straight-line `WalkLine` test (kept, since it uses the
     exact start point), look up `(StartNode, ToNode, Revision)` in a small LRU (64 entries) holding the string-pulled
     corner list. `StringPull(Chain)` depends only on nodes, and `Revision` changes on every `RebuildAreas`. It hits on
     every stuck replan, on `PlanAttack` while the body stands, and on the static half of every flank evaluation
     (`P.End[Foe()] -> Goal`).
  2. In `Flood`: a `TArray<uint8> NearWall` beside `Nodes`, and `Remaining` as a count plus a stamp array. The same
     expansion order, the same `Cost` / `Next`.
- Expected gain: the 17-20 ms `TickActors` spikes go; the 24-40 ms `Tickables` spikes go while the army stands and
  roughly halve otherwise (estimate: 1.3-2 times from item 2); 0.3-0.8 ms a frame on the mean.
- Risk: L. Add a debug cvar that runs the search anyway and compares (`vl.Grid.MemoCheck`).
- Platforms: both.
- Verify by: `Tickables` and `TickActors` per frame (nothing over about 10 ms outside a raid launch); the 99th
  percentile; `Tools/realmv2_test.py routes` unchanged.
- Confidence: high for the diagnosis (period, size and code path all match), medium for item 2's size.

### FP-06  A raid or flank launch runs about 19 full-map searches in one frame: run them side by side
- Area: hitches
- Where: `VLAISquads.cpp:1250-1275` (the raid: the direct route, then two `RouteLength` calls per flank point), `784-800`
  (the attack flank), `VLAIWorld.cpp:62-85`.
- Evidence:
  - `1080p/mountain.csv` frame 734: `Tickables` 175.65 ms, frame 197 ms. `1440p/mountain.csv` frame 701: 218.1 ms, frame
    240 ms.
  - Both at match clock 2:24. The 1440p log has `AI 0 [2:24] Raid#5` and `AI 1 [2:24] Raid#5` 143 ms apart inside one
    frame number (`[ 38]`, 06.42.55:302 and :445).
  - `RenderThreadTime` was 15.0 ms in that frame. The 19 is inferred from the nine flank bridges, not counted at runtime.
- Change:
  - (a) FP-05's memo removes the static half.
  - (b) Give `Flood` its scratch (`Cost`, `Next`, `Seen`, `Stamp`) as a parameter, with a pool of scratch sets (13 MB
    each, allocated on first use, capped at the worker count). Collect a launch's `(from, to)` pairs, run them with
    `ParallelFor`, then evaluate in the original order. Each search is independent and deterministic.
- Expected gain: the 196 / 240 ms frame becomes 30-50 ms (estimate); `CPUUsage_Process` is 15.5 % of 12 threads, so the
  workers are free.
- Risk: M. `Flood` must touch nothing shared but the read-only grid; `RouteMark` / `RouteStamp` in `StringPull` need the
  same treatment. Memory up to 6 x 13 MB.
- Platforms: both.
- Verify by: the worst frame of a 4-minute capture; the raid log lines identical for a fixed start.
- Confidence: high for the diagnosis, medium for the size.

### FP-07  Unit parts are occlusion-queried one by one when far: a scene proxy that can't be occluded
- Area: GPU / render thread
- Where: `VLKing.cpp:312` (`NewObject<UStaticMeshComponent>` for each part); a new small class beside it.
- Evidence:
  - `ProfileGPU` at the 1080p overview: `IndividualQueries` 12,990 draws, 3.684 ms of an 11.59 ms frame (4.88 ms in the
    "1440p" frame); only 5 grouped queries. The CSV's `DrawCall/BeginOcclusionTests` is 12,662 mean at the overview,
    5,700 at the mountain, 0 at the base.
  - A troop is 34-38 separate mesh components (the log's `King: 34 parts ... cape 5 x 4`; 20 are cape panels), about
    11,000 for 313 units.
  - `FStaticMeshSceneProxy::CanBeOccluded()` returns false while `ShouldRenderCustomDepth()`
    (`StaticMeshSceneProxy.cpp:2429-2432`), and A6 turns custom depth off beyond 400 m, so far units become occludable.
  - Without approximate occlusion a visible primitive gets its own query every frame (`SceneVisibility.cpp` near 2982).
    Whether movable primitives lack approximate occlusion was not confirmed in the engine.
  - Near units are already never occlusion-culled, so nothing visible changes.
- Change: `UVLPartMeshComponent : UStaticMeshComponent`, overriding the virtual
  `CreateStaticMeshSceneProxy(Nanite::FMaterialAudit&, bool)` (`StaticMeshComponent.h:890`) to return a
  `FStaticMeshSceneProxy` subclass (`Public/StaticMeshSceneProxy.h:34-43`, exported constructor) with
  `CanBeOccluded() const override { return false; }`. Use it in `BuildFigure` and for any other separate unit parts. No
  asset changes.
- Expected gain: 3.5 ms GPU at the 1080p overview, 4.5 ms at "1440p"; 1.5-2.5 ms render thread (estimate);
  `RHI/DrawCalls` from 20,431 to about 9,500.
- Risk: L. Units behind the mountain are drawn when in the frustum (LOD 2 parts). The proxy constructor signature was
  checked against 5.8.4.
- Platforms: both.
- Verify by: `ProfileGPU` at the overview (`IndividualQueries` near 2,000 draws and under 0.6 ms), `GPUTime`,
  `RenderThreadTime`, and a screenshot diff at the three views.
- Confidence: high.
- Alternative: try `r.HZBOcclusion 1` (`SceneVisibility.cpp:123-131`) in a console session, no build needed. It can pop,
  so A/B only.

### FP-08  `r.Nanite=0` on Windows: no mesh is Nanite, so the setting only forces a full depth prepass
- Area: GPU / render thread / config
- Where: `Config/Windows/WindowsDeviceProfiles.ini`.
- Evidence:
  - Every importer sets `build_nanite` False (`import_assets.py:147`, `import_king.py:39`, `voxel_lods.py:55`).
  - `ProfileGPU`: `PrePass DDM_AllOpaqueNoVelocity (Forced by Nanite)` is 2,452 draws, 1.15 ms at 1080p and 1.66 ms at
    "1440p".
  - The engine's `GetEarlyZPassMode` (`RendererScene.cpp:4425-4453`) falls back to `DDM_NonMaskedOnly` when nothing forces
    the full pass (`r.DBuffer` is already False).
- Change: `+CVars=r.Nanite=0` in the Windows profile, only if the A/B wins. Keep `r.Nanite.ProjectEnabled` as it is.
- Expected gain: up to 1.1-1.7 ms GPU and about 2,400 draws off the render and RHI threads, minus the base-pass overdraw
  (3.57 ms today, with none).
- Risk: L (reversible; the Mac ships it).
- Platforms: Win only.
- Verify by: a console A/B at the mountain and the overview (`r.Nanite 1 / 0`), with `ProfileGPU` (prepass + base pass +
  occlusion) and `stat unit` Draw.
- Confidence: medium.

### FP-09  The stuck warnings: a symptom to note, not a cost to chase
- Area: game thread (diagnosis)
- Where: `VLKing.cpp:515` and `568` (capsules ignore pawns during an order and block again when it ends); the engine's
  `CharacterMovementComponent.cpp:5513-5549` and `161-168` (one log line a second per character, off in Shipping).
- Evidence:
  - All 616 lines name another troop's `CollisionCylinder`, with penetration of 5-83 cm.
  - The "other events since notify" counter is 0-2 in the lines sampled, so there were about 1,000 events in 240 s against
    4.5 million movement ticks.
  - They come from the jammed squad: units pass through one another while marching, stop overlapped, turn solid, and then
    can't move on the next input.
- Change: none for performance. Optionally `p.CharacterStuckWarningPeriod=-1` in Development. Stopping units from ending
  up inside one another changes movement outcomes, so it is a gameplay item for the owner.
- Expected gain: none measurable.
- Risk: L.
- Platforms: both.
- Verify by: an Insights trace, which shows the `ResolvePenetration` time directly.
- Confidence: high.

### FP-10  The auto-combat scan: 3-6 ms in one frame every 0.25 s
- Area: game thread / hitches
- Where: `VLBattle.cpp:2385-2470` (`TickAutoCombat`, `AutoTimer = 0.25f`) and `2303-2359` (`FindFoe`, `FindFoeIn`).
- Evidence: `Tickables` is 0.2 ms on most frames and 2.6-6.6 ms on every 11th frame at the overview. `FindFoe` gathers
  every unit within 40 m, own side included; a unit with no foe then calls `DistanceTo` for every building.
- Change (the same choices at the same cadence): a hash per team, or a team bit per cell, so only foes are gathered, in
  registry order. For buildings, test a cached centre-and-radius bound against the current best before the exact
  `DistanceTo`.
- Expected gain: the spike from 3-6 ms down to 1-2 ms (estimate).
- Risk: L (compare old and new results for a few matches).
- Platforms: both.
- Verify by: `vl.Opt.Timing` (`TickAutoCombat`) and the `Tickables` column.
- Confidence: medium.

### FP-11  The rig's late pass: pose the troops on worker threads
- Area: game thread
- Where: `VLKingRig.cpp:651-696` (`RigLateUpdate`), `551-649` (`RigLate`), `512-549` (`PoseNow`).
- Evidence: `WorldTickMisc` is 0.16 ms in the empty base view and 2.2-2.8 ms with units in view. That is most likely the
  late pose and write, because `RigLateUpdate` hangs on `OnWorldPostActorTick`; it isn't timed separately.
- Change: three passes:
  1. serial: the visibility, rate and custom-depth decisions;
  2. `ParallelFor`: `PoseNow(false)` for the units whose pose touches only their own buffer;
  3. serial: `RigFlush`.
  Size it first with `vl.RigStats`, which already reports the pose and write times separately.
- Expected gain: 0.8-1.5 ms at the wide views (estimate).
- Risk: M. `PoseFigure` and the poser lambdas must not touch shared state.
- Platforms: both.
- Verify by: `vl.RigStats 1`, `vl.RigCheck` (0 difference), `WorldTickMisc`.
- Confidence: medium.

### FP-12  Small game-thread items (one batch; each about 0.1-0.3 ms)
- Area: game thread
- Where / change:
  - **AI controllers** (`VLKing.cpp:58, 886`, troop spawning): 348 `AAIController` actors tick every frame to update a
    control rotation that nothing reads. After spawn, call `GetController()->SetActorTickEnabled(false)`.
  - **Physics interaction** (`VLKing.cpp:78-93`): set `Move->bEnablePhysicsInteraction = false`. The default is true,
    but nothing simulates physics.
  - **Overlap events**: `GetCapsuleComponent()->SetGenerateOverlapEvents(false)`. No code uses overlap events (no
    `BeginOverlap`, no `GetOverlapping*`), so sweeps skip gathering touches (`PrimitiveComponent.cpp:3351`) and
    `UpdateOverlapsImpl` returns early (`4480`).
  - **FARMHAND log**: about 1,500 lines in 4 minutes at Log level. Move them to Verbose.
- Expected gain: 0.3-0.6 ms together (estimate).
- Risk: L.
- Platforms: both.
- Verify by: `Ticks/Total` (about 1,004 down to about 650), `TickActors`, `QueueTicks`.
- Confidence: medium-high.

### FP-13  The grid rebuild after a building: 22-28 ms, of which 19-24 ms relabels every region
- Area: hitches
- Where: `VLGrid.cpp:612` onward (`RebuildAreas`), `463` (`LabelRegions`).
- Evidence: 71 lines like `GRID area: 4356 cells sampled again ... in 27.9 ms (... floors 3.5, joins 0.2, regions 23.8)`.
  In a played match that is a 25 ms frame on every building placed, finished or razed.
- Change: skip the relabel when the rebuilt cells' node counts, heights and neighbour links are unchanged (a finished
  building usually replaces a site of the same footprint); otherwise relabel as now.
- Expected gain: most rebuild hitches from about 25 ms to about 4 ms (estimate).
- Risk: M (the region ids feed `NearestNode(..., Region)` and the main-region tests).
- Platforms: both.
- Verify by: the `GRID area` times, and a debug compare against a full relabel.
- Confidence: medium.

### FP-14  Sound sets load synchronously at first use, in the middle of a match
- Area: hitches
- Where: `VLBattle.cpp:3379-3399` (`Sounds`: `LoadObject` for `S_<name>`, `_2` .. `_8` on the first call).
- Evidence: the `SkipPackage` warnings are not all at startup. At 1440p, 7 fall at 06.43.06 (inside the mountain capture)
  and 36 at 06.43.25-26 (inside the overview capture).
- Change: at match start call `Sounds()` once for every base name the code uses, and test
  `FPackageName::DoesPackageExist` before `LoadObject`.
- Expected gain: removes a few 2-10 ms frames at each sound's first play (estimate; not isolated in the CSVs).
- Risk: L.
- Platforms: both.
- Verify by: no `SkipPackage` lines after the match starts.
- Confidence: medium.

### FP-15  Later, a measured project: unit parts as instances (the deferred F-02 / R-04b)
- Area: render thread / GPU
- Where: `VLKing.cpp:254-417` (`BuildFigure`), `VLKingRig.cpp:383-455` (`RigFlush`).
- Evidence: after FP-07 / FP-08 the units still make about 11,000 of the 13,973 dynamic primitives. At the mountain view
  `DrawCall/CustomDepth` is 4,505 (5,323 at "1440p"), `Prepass` 947, `ShadowDepths` 1,196, and the render thread is
  14.3-16.1 ms, the highest of the three views.
- Change (outline): one `UInstancedStaticMeshComponent` per (part mesh, team material, custom depth on / off), owned by a
  manager, with `RigFlush` writing the instance transforms in one batch. Open points:
  - the hit flash (an overlay per unit today; per-instance custom data needs a material change, ASSET);
  - per-instance LOD on Metal and Direct3D in 5.8;
  - the 400 m custom-depth gate.
- Expected gain: the render thread down to about 6-8 ms at the mountain view (estimate).
- Risk: H (every unit's look, on both platforms).
- Platforms: both.
- Verify by: the draw-call columns; screenshot diffs at each LOD for both teams; the flash.
- Confidence: low-medium.

### FP-16  Lower-priority observations
- Area: config / render thread / startup
- **UI:** `UI` is 1.15 ms with nothing in view and 2.0 ms at the overview (`VLHUD.cpp:524-598`), so the panels cost more
  than the in-world marks. Not examined further; add `vl.Opt.Timing` scopes for the top bar, the platoon panel and the
  text first.
- **Scene instance churn:** `SceneCulling/NumAddedInstances` = `NumRemovedInstances` = 574 (base) or 1,099 (wide) every
  frame. This is probably the sky's 574 cubes (`VLSky.cpp:132-177`) and the ambience instances (`VLAmbience.cpp:174,
  215`); the 525 is inferred. The cost is small (0.32 + 0.26 ms).
- **PSO:** all 36 `PSOPrecacheState: Missed` lines are in frame 0, before the match is visible. A bundled cache isn't
  worth its upkeep yet.
- **Far fog:** `UpdateFarFog` (`VLGraphics.cpp:572-612`) does 17 complex 2 km traces every 0.2 s. Negligible.
- **LTCG:** `SovereignRealms.Target.cs:17-18` sets `bAllowLTCG` (the condition around it was not read), while
  `PROPOSAL.md` section 4 says LTCG was not done. One of the two is out of date.

## Implement in this order

**Batch 0: measure first (no code)**
1. One Insights CPU trace at the overview, to confirm FP-01's share and FP-09.
2. Fix the capture script's base view (`vl.AIvsAI.King 1`, or `vl.View free` at the castle) and label the second
   resolution honestly.
3. Console A/Bs: `r.Nanite 0` (FP-08) and `r.HZBOcclusion 1` (FP-07's alternative).

**Batch 1: game thread, low risk (C++ only)**
1. FP-02: garrisoned units asleep.
2. FP-03: `bAlwaysCheckFloor = false`.
3. FP-12: the AI controller ticks, physics interaction, capsule overlap events, the farmhand log.
4. FP-05: the route memo and the `Flood` inner loop.
5. FP-10: the auto-combat scan.

**Batch 2: render thread and GPU (C++ and config)**
1. FP-07: non-occludable unit parts.
2. FP-08: `r.Nanite=0` in the Windows profile, if the A/B won.
3. FP-14: sound sets loaded at match start.

**Batch 3: the collision asset change (ASSET, measured on its own)**
1. FP-01: `lod_for_collision = 2` on the Realm v2 tiles, with the grid-identity and footstep checks.

**Batch 4: larger code changes, each behind a cvar**
1. FP-06: parallel raid and flank searches.
2. FP-04: general movement sleep.
3. FP-11: parallel rig posing.
4. FP-13: the grid rebuild without the full relabel.

**Later, only if the render thread is still the limit**
1. FP-15: instanced unit parts.
