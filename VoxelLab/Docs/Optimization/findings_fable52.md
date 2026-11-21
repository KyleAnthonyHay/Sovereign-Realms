# Optimization audit: findings (Fable 5.2)

Scope: static review of `Source/VoxelLab`, `Config`, `Tools/ue`, the cooked package, plus one 10-minute PIE profiling session on `L_Realm` (editor, Metal SM6). Nothing in the project was changed.

## Summary

1. **Units are the dominant scaling cost on every thread.** A unit is an `ACharacter` with about 80 scene components (38 joints, about 34 static-mesh parts, a spring arm, a camera, a 40-instance dust ISM), animated by about 32 separate `SetRelativeRotation` calls a frame, each propagating down the attachment tree. That is about 0.1 ms of game thread per unit. On the GPU, 100 extra units in view cost 6 to 10 ms. (F-01 to F-05)
2. **The frame is GPU-bound before any unit is on screen.** The largest items are TSR at about 5 ms, Lumen's radiance-cache trace at 4 to 7 ms, volumetric fog at 1.5 ms and opaque geometry at 4 to 5 ms. (F-06 to F-10)
3. **The package is 1.5 GB, of which roughly 700 MB is removable with config only.** The rest is mostly ground tiles. (F-11 to F-14)
4. **Load time**: synchronous path grid build and a 1.5 s every-frame minimap capture. (F-15, F-16)
5. **Gameplay code has many O(n²) scans** over `TActorIterator<AVLKing>`. One unit registry with a spatial hash fixes all of them. (F-17 to F-22)
6. **No scalability is exposed** beyond the frame cap. (F-23)

Suggested order: F-06 (one line), F-11/F-12/F-13 (packaging config), F-01 quick wins plus F-04 and F-05, F-03 (troop LODs), F-17 (unit registry), then F-02 (structural).

## Measurements

PIE in the editor (floating window), `L_Realm`, match started on Normal, overview camera. Internal resolution 1771 x 912, upscaled by TSR to 3224 x 1660 (from the ProfileGPU pass names). Frame capped at 60 fps. Numbers come from `vl.Perf` (4 samples each), `ProfileGPU` and `stat dumpave`.

The match kept running during the tests, so absolute values drift by 1 to 3 ms between runs; adjacent rows are the comparable ones. Game-thread time includes editor overhead (Slate is about 1.7 ms).

**Caveat on per-pass GPU times.** On Metal the per-pass attribution in `ProfileGPU` is unreliable. A bucket of about 5.2 ms is labelled `VSM Log Stats And Status` with everything on, moves to `TSR ClearPrevTextures` when Lumen, fog and shadows are off, and shrinks when the TSR history is halved. I treat it as TSR. Frame totals and on/off deltas are reliable; individual pass labels are not.

### GPU at match start (about 36 units in the world, zoom 0.45 over the map's middle)

| Configuration | GPU ms | Note |
| --- | --- | --- |
| Baseline (all on) | 22.9 (41 fps) | game thread 6.8 ms |
| Lumen GI off (`r.DynamicGlobalIlluminationMethod 0`) | 19.1 | -3.9 ms |
| Volumetric fog off | 21.2 | -1.7 ms |
| Lumen, reflections, fog, shadows all off | 15.2 to 16.1 | the floor for this view |
| ... and screen percentage 25 | 11.7 | resolution-independent floor |
| ... and TSR history 100% | 12.3 to 12.9 | -2.5 ms |
| ... and no static meshes at all | 10.5 to 11.3 | all opaque static geometry is 4 to 5 ms |
| ... and no instanced meshes (forest) | 13.1 to 13.3 | forest about 2 ms |

Second set, later in the match (baseline had drifted):

| Configuration | GPU ms (min / avg) |
| --- | --- |
| Baseline | 23.9 / 26.7 |
| `r.TSR.History.ScreenPercentage 100` | 21.8 / 22.4 |
| No instanced meshes | 21.6 / 22.5 |
| `r.Shadow.DistanceScale 0.27` (300 m instead of 1,100 m) | 24.6 (no gain) |
| Radiance cache probe resolution 16 | 22.9 / 24.0 (within noise) |
| Real-time sky capture off | 23.8 / 24.2 (within noise) |
| `sg.AntiAliasingQuality 2` | 24.6 / 28.1 (no gain; not conclusive) |

`ProfileGPU` at baseline: `LumenScreenProbeGather` 6.97 ms (of which `TraceFromProbes Res=32x32` 6.76), the TSR bucket 5.19, `BasePass` 2.24, `VolumetricFog` 1.66, sun `DirectLighting` 1.25, `LumenSceneLighting` 0.66 (culling 123 lights), `PrePass` 0.65, `PostProcessing` 0.75.

### Units

| Situation | fps | game ms | GPU ms |
| --- | --- | --- | --- |
| Home base in view, zoom 0.3, before spawning (about 36 units) | 39.3 | 9.7 | 21.9 |
| +180 troops (90 in view), just spawned | 26.6 | 30.5 | 35 to 43 |
| 100 fresh idle troops in view (about 140 alive) | 24 to 33 | 17.2 | 27 to 32 |
| ... shadows off | 36.7 | 17.3 | 25.3 to 26.4 |
| ... custom depth off | 34.2 | 17.3 | 27.3 to 27.6 |
| ... Lumen GI off | 37.4 | 18.4 | 24.2 to 24.4 |
| Zoom 1.0 (680 m) over the middle, same match | 27.8 | 20.0 | 31.1 to 31.7 |
| ... TSR history 100% | 31.1 | 18.7 | 27.8 to 28.5 |
| ... shadows off | 30.8 | 18.3 | 28.2 to 29.3 |
| Hero view at home | 31.9 | 15.0 | 23 to 25.7 |

`ProfileGPU` with 100 troops in view: `BasePass` 4.68 ms (was 2.24), `ShadowDepths` 1.60 (was 0.27), new `RenderVelocities` 1.02, `CustomDepth` 0.78, and `LumenSceneUpdate: 37 card captures` 0.95.

### CPU (`stat dumpave` over 40 frames, 140 troops alive, 32.3 ms frame)

Game thread: 15.7 ms of work, 8.1 ms waiting on frame sync.

| Item | ms | Calls |
| --- | --- | --- |
| `VLTroop` actor tick (`AVLKing::Tick`) | 8.66 | 140 |
| - `MoveComponent(SceneComp)` inside it | 7.18 | 4,544 |
| - `UpdateComponentToWorld` | 6.61 | 3,975 |
| - self (the pose maths, separation loop) | 1.48 | |
| `CharacterMovementComponent` | 3.03 | 140 |
| - `EndScopedMovementUpdate` (moving about 80 attached components) | 1.76 | |
| - `PhysWalking` (floor sweep against triangle-mesh ground) | 1.07 | |
| `VLArcherCombat` component tick | 0.97 | 76 |
| Post Tick Component Update | 2.72 | 10,295 items |
| HUD (`AVLHUD::DrawHUD`) | 1.16 | 4,591 canvas tiles |
| `UVLBattle::Tick` (average; the work lands every 0.25 s) | 0.61 | |

- **Render thread**: `UpdatePrimitive` 6.60 ms, `UpdateTransformCommand` 1.05 ms for 4,646 primitive transforms a frame.
- **RHI thread**: busy 26.8 of 32.2 ms.
- **Path grid** (existing editor log): `GRID built: 832x832 cells ... 494018 nodes ... in 1033 ms` (realm); `1080x1080 cells ... 858018 nodes ... in 1684 ms` (highlands).

### Package

From `Saved/package.log` and `UnrealPak -list` on the shipped `.utoc`: the container is 4,562 MiB raw and 958 MiB compressed. Raw export data is 3,720 MB for 1,771 packages.

| Content | Compressed MB |
| --- | --- |
| `Voxel/Meshes` | 597 |
| - highlands ground tiles | 196 + 60 bulk |
| - realm ground tiles | 103 + 46 bulk |
| - town / village / flatlands ground | 20 / 20 / 24 |
| Shader code | 150 |
| `NNEDenoiser` content | 103 |
| Audio | 61 |

Outside the container: executable 413 MB, `Engine/Plugins/NNE` binaries 97 MB.

---

## Findings

### F-01 Unit animation: 32 transform propagations per unit per frame (quick wins)

- **Area**: game thread, render thread.
- **Evidence**: `VLKing.cpp:2649` (`Animate`), `:3015` (`UpdateSword`), `:3106` (`UpdateCape`), `:3322` (`Tick`).
  - Every joint is its own `USceneComponent` (`BuildFigure`, `:254` to `:330`), set one at a time, parents before children, so a subtree is recomputed once per ancestor that moves.
  - The cape reads `GetComponentLocation()` between writes (`:3140`), forcing the chain current.
  - There is no throttling: no `WasRecentlyRendered`, no distance or idle check, no tick interval anywhere in the module.
  - Measured: 4,544 `MoveComponent` calls and 7.18 ms for 140 units, 2.7 ms post-tick, 6.6 ms render-thread `UpdatePrimitive`.
- **Impact**: high. About 12 ms of game thread and 7 ms of render thread at 140 units, linear in units.
- **Effort**: low for each, independently.
- **Fix**:
  1. Wrap `Animate` (and the archer's `Pose`, `VLArcherCombat.cpp:951`) in one `FScopedMovementUpdate` on the figure root so the tree propagates once. The cape must compute hinge positions from the pose maths instead of reading components back.
  2. Skip `Animate` for units not recently rendered (`WasRecentlyRendered(0.2f)`) that are not the player's pawn. Keep the game-side clocks (attack timing, `HitDummies`) running; they already sit in a separate block at the top.
  3. Beyond the far-pip distance (75 m), animate every second or third frame and skip the cape.
  4. Let a settled idle unit skip the pose.
- **Risk**: item 1 changes nothing visible; 2 to 4 are invisible when tuned.

### F-02 A unit is about 80 components and 34 draw calls (structural)

- **Area**: game thread, render thread, RHI, GPU.
- **Evidence**: `VLKing.cpp:296` to `:330` creates a joint component plus a `UStaticMeshComponent` per part; the log shows `King: 38 parts` for troops. With 140 units that is 4,646 primitive transform updates a frame and about 4,700 mesh draws per pass in four passes (base, shadow, velocity, custom depth). `EndScopedMovementUpdate` is 1.76 ms because each capsule move drags the whole tree.
- **Impact**: high. This is the ceiling on army size.
- **Effort**: high.
- **Fix**, best first:
  1. One skeletal mesh per troop kind with rigid one-bone-per-part skinning from the Blender pipeline, driven by the existing pose code through `UPoseableMeshComponent` or a custom anim instance.
  2. One `UInstancedStaticMeshComponent` per part kind per team for all units, batch-updated from a manager.
  3. Vertex animation with per-instance joint matrices.
- **Risk**: visual parity needs checking (cape, sword in fist, flash overlay, team materials, custom-depth stencil per side).

### F-03 Troops are 42k to 63k triangles with no LOD

- **Area**: GPU (base, shadow, velocity, custom-depth passes).
- **Evidence**: face totals in `SourceArt/Meshes/SM_<kind>_*.json`: Swordsman 31,627 quads, Builder 30,501, Archer 27,481, King 26,870, Spy 21,170. `Tools/ue/import_king.py` sets no LODs (`build_nanite` False, line 39). 100 troops in view raise the base pass from 2.2 to 4.7 ms and shadow depths from 0.27 to 1.6 ms, and add 1.0 ms velocity and 0.8 ms custom depth. In the overview a troop is 20 to 60 pixels tall.
- **Impact**: high. An estimated 4 to 8 ms of GPU at 100 units in view.
- **Effort**: medium.
- **Fix**: add LOD 1 and 2 per part the way `Tools/blender/assets/tree_lods.py` does for trees (remesh at 2x and 4x voxel size), assigned in `import_king.py`. The overview should never draw LOD 0.
- **Risk**: low.

### F-04 Every troop owns a spring arm, a camera, a spawned camera actor and a dust component

- **Area**: game thread, memory, draw calls.
- **Evidence**:
  - `VLKing.cpp:98` to `:110` creates `Boom` and `Camera` for every `AVLKing`, troops included.
  - `VLKing.cpp:183` spawns an `ACameraActor` (`OverviewCamera`) in every unit's `BeginPlay`.
  - `VLKing.cpp:361` calls `Dust->Setup` for every unit although `VLTroop.cpp:11` turns troop dust off.
  - `Setup` (`VLFootDust.cpp:28`) creates a dynamic material instance and 40 instances parked at Z = -100,000, which stretches the bounds over a kilometre so the component is never culled.
- **Impact**: medium. Per unit: one extra actor, three extra moved components, one never-culled draw, one material instance.
- **Effort**: low.
- **Fix**: create the boom and cameras only for the player's pawn (lazily in `TakeControlOf`, `VLKing.cpp:755`). Skip dust setup when `bFootDust` is false. Park hidden puffs at the component's own location with zero scale, and hide the component when `Alive == 0`.
- **Risk**: low; playing a troop must create them on demand.

### F-05 Unit parts feed Lumen's surface cache and contact shadows every frame

- **Area**: GPU.
- **Evidence**: `VLKing.cpp:318` to `:321`: parts cast shadows with `bCastContactShadow = true`; `bAffectDistanceFieldLighting` is off but `bAffectDynamicIndirectLighting` is left on. `LumenSceneUpdate: 37 card captures` (0.95 ms) appears only with troops in view.
- **Impact**: medium. About 1 ms for Lumen, plus a share of the shadow-depth growth.
- **Effort**: low.
- **Fix**: set `bAffectDynamicIndirectLighting = false` on unit parts and turn contact shadows off for troops. Consider casting shadows from the torso, legs and head only when far.
- **Risk**: low.

### F-06 TSR history at 200% of a Retina-sized output

- **Area**: GPU.
- **Evidence**: `TemporalSuperResolution(sg.AntiAliasingQuality=3) 1771x912 -> 3224x1660`, about 5.2 ms. `r.TSR.History.ScreenPercentage 100` saved 2.5 ms, 2.1 to 4.3 ms and 3.3 ms in three separate comparisons.
- **Impact**: high for the effort. 2.5 to 4 ms, about 10 to 13% of the frame.
- **Effort**: trivial.
- **Fix**: add `r.TSR.History.ScreenPercentage=100` under `[SystemSettings]` in `Config/DefaultEngine.ini`.
- **Risk**: slightly softer sub-pixel detail in motion; compare a screenshot.
- **Note**: I measured in a PIE window on a Retina display. `bAllowHighDPIInGameMode` is not set in the project and I did not run the packaged app, so its output resolution is unverified. Make the setting explicit either way.

### F-07 Lumen final gather raised to 2.0 in the level while the ini lowers it

- **Area**: GPU.
- **Evidence**: `Tools/ue/build_level.py:148` to `:149` set `lumen_scene_detail = 2.0` and `lumen_final_gather_quality = 2.0` on every map's post-process volume. `DefaultEngine.ini` meanwhile sets `r.Lumen.ScreenProbeGather.DownsampleFactor=32` and `r.Lumen.TraceMeshSDFs=0` because the gather was too expensive. `LumenScreenProbeGather` measures 4.4 to 7.0 ms, nearly all in `TraceFromProbes Res=32x32`; turning Lumen GI off gives back 3 to 4 ms net.
- **Impact**: medium to high. An estimated 1.5 to 3 ms from quality 1.0 plus a probe budget.
- **Effort**: low.
- **Fix**: try, in order, with screenshots: quality and detail 1.0; a lower `r.Lumen.ScreenProbeGather.RadianceCache.NumProbesToTraceBudget`; probe resolution 16 (my one test was within noise). Offer "Lumen off" as the low preset (F-23).
- **Risk**: visual; needs a look.

### F-08 Opaque geometry: 3.9 M ground triangles and shallow LOD chains

- **Area**: GPU, memory.
- **Evidence**:
  - Realm ground is 1,923,089 quads in 255 tiles; highlands 3,736,818 in 398. Tiles have no LODs.
  - Trees have exactly two levels (`Tools/ue/tree_lods.py`); 1,301 `SM_Tree2_D` are still about 1.2 M quads at LOD 1.
  - `SM_GrassTuft_C` is 946 quads a tuft across 3,007 instances.
  - With lighting off, all static meshes cost 4 to 5 ms at zoom 0.45, the forest about 2 ms of that.
- **Impact**: medium. 2 to 4 ms, more on the highlands.
- **Effort**: medium.
- **Fix**:
  1. Try Nanite on static voxel meshes (ground, buildings, rocks, trunks, backdrop). The renderer already runs its Nanite-forced prepass and Metal SM6 is in use. It is one flag in `import_assets.py` to test on one map; keep wind materials out at first.
  2. Otherwise add a LOD 1 for ground tiles, a third tree level, and coarser grass.
  3. Merge coplanar faces further than two by two (`realm_terrain.merge_quads`).
- **Risk**: Nanite needs checking on target Macs in 5.8; LODs are safe.

### F-09 Volumetric fog

- **Area**: GPU.
- **Evidence**: `build_level.py:122` to `:126` enable it to 120 m; each of 122 lamps has `volumetric_scattering_intensity = 0.6` (`:215`). Measured 1.5 to 1.7 ms.
- **Impact**: medium, 1 to 1.7 ms.
- **Effort**: low.
- **Fix**: switch it off (or coarsen the grid) by camera mode in the far overview; set lamp scattering to 0 on battle maps.
- **Risk**: none if tied to the overview.

### F-10 Sun shadows to 1,100 m, real-time sky capture, 122 lamps

- **Area**: GPU.
- **Evidence**: `build_realm.py` `far_shadows()`; `build_level.py:113`; `lamps()`. Measured: shadow distance 300 m gave no gain; sky capture was within noise; the lamps are 0.28 ms of light culling. Shadows cost 2 to 6 ms only with many units in view (F-03, F-05).
- **Impact**: low on their own. Recorded so nobody starts here.
- **Effort**: low.
- **Fix**: give lamps a `MaxDrawDistance`. Leave the rest.
- **Risk**: none.

### F-11 Packaged in Development configuration

- **Area**: package size, CPU.
- **Evidence**: `DefaultGame.ini` has `BuildConfiguration=PPBC_Development`; `Tools/package.sh` defaults to Development. The executable is 413 MB. Logging, stats and console stay compiled in.
- **Impact**: medium. Several hundred MB and a few percent of CPU.
- **Effort**: trivial.
- **Fix**: `sh Tools/package.sh Shipping`. Keep Development for automated tests, since the `vl.*` inbox stops working in Shipping.
- **Risk**: none for players.

### F-12 The NNE denoiser plugin ships with the game

- **Area**: package size, startup.
- **Evidence**: `Engine/Plugins/NNE/NNEDenoiser/Content` is 103 MB compressed (two 43 to 46 MB OIDN models) and the NNE plugin folder is 97 MB of binaries. Nothing uses path tracing. `ControlRig`, `SpeedTreeImporter`, `Interchange` and `VREditor` content is cooked too.
- **Impact**: medium, about 200 MB.
- **Effort**: trivial.
- **Fix**: disable `NNEDenoiser` and `NNERuntimeORT` in `VoxelLab.uproject`; review other default-on plugins in the cook log.
- **Risk**: none.

### F-13 Two shader formats are cooked

- **Area**: package size, cook time.
- **Evidence**: `Saved/package.log` shows libraries for both `SF_METAL_SM5` and `SF_METAL_SM6` (SM5: 31 MB global + 5 MB project, compressed). There is no `MacTargetSettings` section in `DefaultEngine.ini`.
- **Impact**: low to medium, 36 MB and half the material compile time.
- **Effort**: trivial.
- **Fix**: set `TargetedRHIs` to `SF_METAL_SM6` only.
- **Risk**: none on Apple Silicon.

### F-14 Ground tiles dominate the package and memory

- **Area**: package size, memory, load time.
- **Evidence**: 653 ground tiles are 339 MB compressed, plus about 110 MB of distance-field bulk data. Raw export data is 3.72 GB, about 330 bytes a quad. In `Tools/ue/import_assets.py`: `use_full_precision_u_vs = True` (line 151) and `CTF_USE_COMPLEX_AS_SIMPLE` by default (line 196). By proportion the highlands ground is of the order of 1.2 GB resident; that is an estimate, and `memreport -full` would confirm it.
- **Impact**: high for memory and download, medium for load time.
- **Effort**: medium.
- **Fix**:
  1. Half-precision UVs.
  2. A simplified collision mesh or heightfield for ground.
  3. A lower distance-field resolution on tiles.
  4. Fewer quads (F-08 item 3).
  5. Drop the three sandbox maps from `MapsToCook` (about 70 MB) and narrow `DirectoriesToAlwaysCook=/Game/Voxel`, which also cooks the superseded `SM_KingA_*`, `SM_KingT_*` and `SM_King_*` meshes.
- **Risk**: the footstep surface lookup reads the material from the collision face (`VLKing.cpp:3253`), so a simplified collider must keep per-face materials or the lookup must move.

### F-15 The path grid is built on the game thread at BeginPlay

- **Area**: load time, memory.
- **Evidence**: `VLGameMode.cpp:899` calls `EnsureBuilt()`; `VLGrid.cpp:113` to `:297` runs line traces and a capsule overlap per 50 cm cell. Log: 1,033 ms (realm), 1,684 ms (highlands). `FNode` stores eight `int32` neighbours (`VLGrid.h:63`), so roughly 65 to 75 MB on the highlands.
- **Impact**: medium. 1 to 1.7 s frozen on every match start and restart.
- **Effort**: medium.
- **Fix**: bake the grid at level build (`build_realm.py`) into an asset or file, or run `SampleCell` rows in a `ParallelFor`. Derive neighbours instead of storing them.
- **Risk**: a baked grid needs invalidating when the map changes; `RebuildArea` is unaffected.

### F-16 The minimap renders the whole scene every frame for 1.5 s

- **Area**: startup hitch, GPU memory.
- **Evidence**: `VLHUDGame.cpp:425` to `:465` and `:493` to `:496` call `CaptureSceneDeferred()` every frame for 1.5 s "so the exposure settles", with `bAlwaysPersistRenderingState = true`. The capture source is base colour, which does not depend on exposure. Lumen and shadows are not disabled in its show flags.
- **Impact**: medium for the first 1.5 s; low to medium GPU memory afterwards from the persistent view state.
- **Effort**: low.
- **Fix**: capture two or three frames at most, disable Lumen, shadows, AO, sky lighting and anti-aliasing in the show flags, drop the persistent state, and unregister afterwards. Better still, bake the texture at level build.
- **Risk**: none.

### F-17 No unit registry: 90 `TActorIterator` sites, several O(n²) per frame

- **Area**: game thread.
- **Evidence**:
  - `VLKing.cpp:605` `AutoSteer`: every walking unit scans every unit every frame.
  - `VLBattle.cpp:1573` `FindFoe`: called per unit from `TickAutoCombat` (`:1636`), all units in the same frame every 0.25 s. It compares `FString` kinds inside the loop (`VLRules::Troop`, `:31` to `:60`; `IsRanged`, `VLKing.h:89`).
  - `VLArrow.cpp:387` `UnitOnPath`: every flying arrow scans every unit every frame.
  - `VLBattle.cpp:1487` `TickDefence` and `:1779` `TickKings` walk the full list every frame.
  - One more full pass each, every frame: `VLGameMode.cpp:979`, `VLHUD.cpp:1046`, `VLHUD.cpp:1179`, `VLHUDGame.cpp:541`, `VLKing.cpp:1002`.
  - `GetPopulation` (`VLBattle.cpp:921`) and `GetSpyCount` (`:1049`) iterate per call.
  - `FindBuilding` (`:434`) is a linear search inside `DistanceTo`.
  - The combat `For()` helpers use `FindComponentByClass` (`VLSwordsmanCombat.cpp:201`).
  - Measured: `UVLBattle::Tick` averages 0.61 ms at 140 units, which is a multi-millisecond spike every 0.25 s.
- **Impact**: medium today; high at 300+ units or once F-01 is fixed.
- **Effort**: medium.
- **Fix**: per-team `TArray<AVLKing*>` in `UVLBattle`, cached combat-component pointers on `AVLKing`, an `EVLUnitKind` enum, a building map, and a uniform spatial hash (about 5 m cells) rebuilt once a frame. Spread `TickAutoCombat` over frames.
- **Risk**: low; behaviour should be identical.

### F-18 Character movement for every troop

- **Area**: game thread.
- **Evidence**: 3.03 ms for 140 units: `PhysWalking` 1.07 ms (capsule sweep against triangle-mesh ground) and 1.76 ms moving the attached tree.
- **Impact**: medium, about 22 microseconds a unit.
- **Effort**: medium.
- **Fix**: disable the movement tick for standing troops with no order and no velocity. Later, take walking height from the path grid instead of a floor sweep.
- **Risk**: medium; knock-backs, falls and the water rescue (`UpdateSafety`, `VLKing.cpp:625`) rely on real movement. Start with the idle case.

### F-19 HUD: thousands of one-pixel tiles and per-unit allocations each frame

- **Area**: game thread.
- **Evidence**:
  - `VLHUD.cpp:1168` to `:1221` `DrawFarPips` draws each pip as about 20 to 26 one-pixel `Fill` rows.
  - It also calls `GetPlatoon` into a fresh `TArray` up to six times per player unit.
  - `VLHUD.cpp:926` runs `PickUnderCursor` every frame in the overview: a 2 km trace with up to 8 retries, two projections per unit, then a walk over every actor in the level (1,212 in `L_Realm`) with a tag test and `FindComponentByClass` (`VLKing.cpp:1042`).
  - Measured: 1.16 ms, 4,591 canvas tiles.
- **Impact**: low to medium, 1 to 2 ms with a large army zoomed out.
- **Effort**: low.
- **Fix**: one pip texture, a per-unit platoon index, a cached list of selectable buildings, and picking only when the mouse moved or every third frame.
- **Risk**: none.

### F-20 Pathfinding: per-unit searches on a grid of up to 858k nodes

- **Area**: game thread spikes.
- **Evidence**: `VLGrid.cpp:708` `Flood` (A* with a binary heap and a fresh `TSet` per search). `UVLSwordsmanCombat::Chase` (`VLSwordsmanCombat.cpp:483`) runs one search per swordsman per repath; stuck units replan at `VLKing.cpp:590`. Timings are logged only at `Verbose`, so I have no numbers.
- **Impact**: unknown; likely medium in large melees.
- **Effort**: low to measure, medium to fix.
- **Fix**: expose the timing as a stat; share one flood among chasers of the same foe; try a straight `WalkLine` first; cap searches per frame.
- **Risk**: low.

### F-21 Smaller per-frame waste

- **Area**: game thread, audio.
- **Evidence and fix**:
  - `VLGameMode.cpp:1090` to `:1097`: `FileExists` on `Saved/VLCommands.txt` 20 times a second in every build. Compile it out of Shipping.
  - `VLGameMode.cpp:868` and `:930`: music is off by default, yet a stream still plays at volume 0.0001 and eight songs load synchronously. Do not create the component while the setting is 0.
  - `VLFootDust.cpp:107`: `MarkRenderStateDirty()` every frame while a puff lives. Use the flag on the last `UpdateInstanceTransform`, as `VLAmbience.cpp` does.
  - `VLAmbience.cpp:71`: all motes and smoke update every frame regardless of view.
  - `VLKing.cpp:527` and `VLArcherCombat.cpp:677`: unconditional `UE_LOG` per arrival and per shot. Gate them on `vl.BattleLog` / `vl.CombatLog`.
- **Impact**: low each.
- **Effort**: low.
- **Risk**: none.

### F-22 Arrows: a component per arrow

- **Area**: game thread, draw calls.
- **Evidence**: `VLArrow.cpp:188` to `:220` and `:476` to `:575`: each pooled arrow is its own `UStaticMeshComponent`, moved, line-traced and unit-scanned per frame.
- **Impact**: low now; medium with two archer armies.
- **Effort**: low to medium.
- **Fix**: one instanced component with the fade in per-instance custom data. The scan goes away with F-17.
- **Risk**: arrows attached to a rocking dummy (`:245`) can stay as components.

### F-23 No scalability exposed

- **Area**: scalability.
- **Evidence**: the settings screen has only a frame cap and an interface scale (`VLHUD.cpp:89` to `:117`, `VLHUDMenus.cpp:329`). There is no `sg.*`, screen percentage or dynamic resolution anywhere in `Source/` or `Config/`.
- **Impact**: high for players on smaller Macs, and the safest way to ship the visual trade-offs above.
- **Effort**: medium.
- **Fix**: three presets applied by console variable, plus a resolution-scale slider.
  - **High**: today's look with F-06.
  - **Medium**: Lumen quality 1.0, no volumetric fog in the overview, shadow quality 3, screen percentage 75.
  - **Low**: `r.DynamicGlobalIlluminationMethod 0` with DFAO, `r.ReflectionMethod 0`, no volumetric fog, screen percentage 60, halved grass cull distance, troop LOD bias +1.
  - Test `r.DynamicRes.OperationMode` on Metal.
- **Risk**: none; defaults stay as they are.

## Not measured, worth a follow-up

- The packaged app: output resolution, game-thread time without the editor, `memreport -full` on both battle maps.
- `L_Highlands`, which has twice the ground.
- A long AI-versus-AI match at `vl.TimeScale` with an Insights trace, for path-search and commander spikes (F-20).