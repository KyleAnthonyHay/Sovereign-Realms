# Optimization audit: Opus 5.5

Scope: `VoxelLab/` (UE 5.8, macOS, Apple Silicon). Findings only: no code or assets were changed. Paths are relative to `VoxelLab/`. I ran one short profiling session in the editor (about 5 minutes, lock taken and released); see *Measurements*. The other figures come from reading the code, configs, build scripts and the packaged build's IoStore table of contents (`UnrealPak <utoc> -List`).

## Summary

1. **With many troops the game is game-thread bound. The cause is the unit rig, not the AI.** I measured 194 troops in L_Realm (AI vs AI): game thread 29.9 ms, GPU 24 ms.
   - `TickActors` takes 13.7 ms. About 80 % of the troop tick is component transform propagation: 6,267 `MoveComponent(SceneComp)` calls a frame.
   - `CharacterMovement` takes 5.5 ms. Of that, 3.4 ms (stat-inflated) is the capsule move re-propagating the 70-component rig, which `Animate` then poses again anyway.
   - `EndOfFrameUpdates` takes 3.4 ms and the HUD (`UI`) 3.3 ms.
   - On the render thread, 6,600 primitive transform updates a frame.
   - Every troop also ticks a spring arm, two cameras and a hidden skeletal mesh it never uses (1,485 ticks a frame).
   - Fixes:
     - Batch the rig's transform writes and stop the capsule cascading (C-01, C-02).
     - Animation LOD and visibility gating (C-03).
     - Strip the per-troop camera rig (C-04).
     - Together these should take the game thread from about 30 ms to about 10-12 ms at 200 troops.
2. **Without armies the GPU is the limit, and it is resolution bound.** `r.ScreenPercentage 50` cut the GPU time from 46.6 to 23.6 ms. The game has no render-scale, upscaling or quality setting.
   - The biggest passes are Lumen's screen probe gather (4-12 ms) and volumetric fog (1.6-5.8 ms).
   - The level's post-process volume runs Lumen Final Gather Quality 2 and Scene Detail 2 on every map.
   - Fixes: a TSR render scale (R-01), Lumen quality 1 (R-02), cheaper fog (R-03), and a quality menu (S-01).
3. **The scene issues about 12.7 k Metal draw calls a frame with 194 troops.**
   - Every voxel material slot is its own section: a swordsman is 59 sections and an archer 70; the realm's ground is 1,370 and the highlands' 2,270.
   - Nothing has LODs except trees and plants: troops are 42-63 k triangles, buildings 85-140 k.
   - Fixes: an atlas / texture-array material, a merged unit mesh, and voxel LODs (R-04, R-05).
4. **The package is 1.5 GB, and about 0.5 GB of it is easy to remove.**
   - The NNE denoiser plugin is about 200 MB and is unused (P-01).
   - The Development executable carries 173 MB of link-edit data (P-02).
   - Shaders are cooked for both SM5 and SM6 (P-03).
   - The ground tiles are 480 MB of the 1.0 GB `.ucas` (P-04).
5. **Smaller items:**
   - All 8 songs are loaded synchronously and kept resident. One plays muted, and is decoded, while music is "off" (P-05).
   - The path grid takes 1.06 s to build on the realm (measured) and 2.4 s on the highlands, single-threaded. Each building placement causes a 22 ms hitch (P-07).
   - About 40 `TActorIterator` sites. A unit registry in `UVLBattle` removes most of them (C-07).

## Measurements

These are PIE numbers from the editor, so the editor's own Slate costs about 1-1.5 ms of GPU and up to 15 ms of render thread, and stats inflate the CPU. The PIE viewport rendered at 3224 x 1660 (a Retina 2x of the 1612 x 830 the README quotes). The battle evolved between samples (AI vs AI), so compare relative numbers, not absolute ones. The machine is the one in the README (M5 Pro). Tools: `csvprofile frames=N` (with `r.GPUCsvStatsEnabled 1`), `ProfileGPU` + `Tools/gpuprof.py`, and `stat dumpframe -ms=0.25` with `stat namedevents`.

**Baseline: L_Realm, hero view at start, match running, no armies**

| | ms |
|---|---|
| Frame time | 25.0 |
| Game thread | 7.7 |
| GPU | 22.2 |

GPU passes:

| Pass | ms |
|---|---|
| LumenScreenProbeGather | 4.2-6.6 |
| VSM Log Stats And Status | 5.2 (see R-11) |
| VolumetricFog | 1.56 |
| BasePass | 1.6-1.7 |
| ShadowDepths (VSM, non-Nanite) | 1.0-1.1 |
| DirectLighting | 0.9 |
| RenderVelocities | 0.7-0.8 |
| LumenSceneLighting | 0.65-0.8 |
| PostProcessing | 0.76 |

**L_Realm with 194 troops** (`vl.SpawnTeam` 60 swordsmen + 40 archers a side, AI vs AI), overview at its usual zoom

| | ms |
|---|---|
| Frame time | 29.9 |
| Game thread | 29.9 (bound) |
| GPU | 24.2 |
| RHI thread | 2.5 |

- **Game thread, exclusive:**

  | Stat | ms |
  |---|---|
  | TickActors | 13.68 |
  | CharacterMovement | 5.47 |
  | EndOfFrameUpdates | 3.42 |
  | UI (HUD) | 3.27 |
  | Tickables | 0.89 |
  | QueueTicks | 0.32 |

- **Ticks a frame:** 1,485.
  - 194 each of VLTroop, AIController, CharacterMovementComponent, SpringArmComponent and SkeletalMeshComponent.
  - 391 CameraComponent: two per unit.
  - 92 VLArcherCombat.
- **`stat dumpframe`, inflated by about 1.5x by stats:**
  - VLTroop ticks: 16.6 ms in all.
    - `MoveComponent(SceneComp)`: 13.5 ms over 6,267 calls.
    - `UpdateComponentToWorld`: 12.5 ms over 5,943 calls.
    - The `Figure` subtree: 3.7 ms. `Joint_Chest`: 2.4 ms. `Joint_Body`: 1.8 ms. Each cape column root: about 0.27 ms.
  - CharacterMovement: 9.1 ms in all.
    - `EndScopedMovementUpdate`: 3.4 ms. This is `UpdateChildTransforms` cascading through Figure > Joint_Body > Chest > cape.
    - FindFloor: 2.4 ms over 341 sweeps.
    - ResolvePenetration plus the move sweeps: about 2.4 ms.
  - Render thread:
    - `UpdatePrimitive`: 7.4 ms, with 6,603 `UpdatePrimitiveTransform` calls.
    - `UpdateIndirectLightingCacheBuffer`: 5,719 calls, 0.52 ms.
    - Metal draw calls in the frame: 11,735 + 787 + 218, about 12.7 k.
    - `GenerateDynamicMeshDrawCommands`: 5.5 ms on one worker.
- **GPU (CSV):**

  | Pass | ms |
  |---|---|
  | LumenScreenProbeGather | 4.43 |
  | Basepass | 3.12 (up from 1.6) |
  | VolumetricFog | 1.67 |
  | SlateUI | 1.46 |
  | ShadowProjection | 1.06 |
  | LumenSceneLighting | 0.95 |
  | RenderVelocities | 0.81 |
  | Prepass | 0.75 |
  | ShadowDepths | 0.44 |
  | CustomDepth | 0.19 |

**The same match later, in a heavier GPU state** (the overview over the forest and the bridge fight). Each row is about 70 frames, taken one after the other:

| Setting | GPU ms | Game thread ms |
|---|---|---|
| default | 46.6 | 16.8 |
| `r.ScreenPercentage 50` | **23.6** | 15.4 |
| `r.Shadow.Virtual.Enable 0` | 45.4 | 17.8 |
| `r.VolumetricFog 0` | **42.4** | 17.7 |
| `r.CustomDepth 0` | 49.4 (noise) | 19.6 |
| earlier: `r.VolumetricFog 0` + `r.DynamicGlobalIlluminationMethod 0` against default | 20.7 against 24.2 | |

`ProfileGPU` in that state:

| Pass | ms |
|---|---|
| LumenScreenProbeGather | 11.86 |
| VSM Log Stats And Status | 9.98 |
| BasePass | 6.68 |
| VolumetricFog | 5.77 |
| DirectLighting | 3.27 |
| TranslucencyVolumeLighting | 1.34 |
| RenderVelocities | 1.34 |
| LumenSceneUpdate (37 card captures) | 0.82 |
| CustomDepth | 0.69 |

**Load:** `GRID built: 832x832 cells ... in 1056 ms` (L_Realm). One building placement: `GRID area: 4356 cells sampled again ... in 21.7 ms`.

**Package** (`Builds/Mac/VoxelLab.app`, 1.5 GB):

| Part | Size | Notes |
|---|---|---|
| `MacOS/VoxelLab` | 413 MB | arm64, Development, `__LINKEDIT` 173 MB |
| `UE/Engine/Plugins/NNE/NNERuntimeORT` | 97 MB | |
| `VoxelLab-Mac.ucas` | 1,004 MB | breakdown below |

The `.ucas` breakdown, by span on disk:

| Content | MB |
|---|---|
| `/Game/Voxel/Meshes` | 642 |
| ...of which SM_HighlandGround_* | 256 |
| ...of which SM_RealmGround_* | 149 |
| ...of which SM_TownGround_* | 27 |
| ...of which SM_Flat_* | 25 |
| ...of which SM_Terrain_* | 23 |
| `<ShaderCode>` (stored with compression None) | 165 |
| `Engine/Plugins/NNE` (OIDN models: two files of 46 + 43 MB) | 103 |
| `/Game/Voxel/Audio` (music .ubulk 6.5-9.8 MB per song, 58 MB in all) | 61 |

Shader type stats (`Saved/Cooked/.../ShaderTypeStats-*.csv`): METAL_SM6 has 11,902 shaders, 188 MB raw (Global 168 MB); METAL_SM5 has 7,147 shaders, 80 MB raw.

---

## Findings

Each finding gives its area, the evidence, the estimated impact, the effort and risk, and the fix. Within each section they are ordered by impact divided by effort.

### Game thread: units

**C-01: Rig transform propagation in `AVLKing::Animate`, `UpdateSword` and `UpdateCape`** (game thread and render thread)
- **Evidence:**
  - `Source/VoxelLab/VLKing.cpp:2884-2925`: the Figure, then Body, Chest, Head, arms and legs, each with `SetRelativeRotation`. Each call runs `UpdateComponentToWorld` over the whole subtree beneath it.
  - The rig is about 35 joint `USceneComponent`s plus 35 `UStaticMeshComponent`s per unit (`BuildFigure`, `VLKing.cpp:264-322`).
  - The cape (`VLKing.cpp:3204`) does `SetWorldRotation` on 20 panels, each re-propagating the rows below it. It reads `N.Joint->GetComponentLocation()` (`:3135`), so it depends on that propagation.
  - The archer pose then rewrites Chest, Head and the arms again (`VLArcherCombat.cpp:951-1110`).
  - Measured: 6,267 scene-component moves a frame for 194 troops, which is 13.5 ms of the 16.6 ms troop tick (stat timing). The render thread then receives 6,600 primitive transform updates (7.4 ms `UpdatePrimitive`).
- **Impact: High.** About 8-10 ms of game thread and 3-5 ms of render thread at 200 units, scaling linearly.
- **Effort:** Medium. **Risk:** Low (the same pose, computed differently).
- **Fix:**
  1. Write all joint rotations with the `_Direct` setters (`SetRelativeRotation_Direct` and friends), then call `Figure->UpdateComponentToWorld()` once. That is one pass over about 70 components instead of about 300 updates.
  2. Do the cape in figure-local math: hinge positions from the parent panel's pivot and length, not from `GetComponentLocation`. Write its rotations the same direct way.
  3. Fold the archer and spy poses into the same pass: compute, then propagate once.
  4. Longer term, see R-04(b): one rigid-skinned skeletal mesh per unit turns all of this into one bone-buffer upload.

**C-02: The capsule move cascades through the whole rig every frame**
- **Evidence:** `Figure` is attached to the capsule (`VLKing.cpp:93-94`). Each CharacterMovement step ends in `EndScopedMovementUpdate`, which ran `UpdateChildTransforms` through Figure > Body > Chest > Cape: 3.4 of 9.1 ms of CharacterMovement (stat timing). `Animate` then moves the Figure again (`:2884`), cascading a second time.
- **Impact: High** (about 2-3 ms at 200 units, real timing).
- **Effort:** Low to medium. **Risk:** Low.
- **Fix:** make `Figure` absolute (`SetAbsolute(true, true, true)`) and place it in world space once in `Animate` (actor transform × rest offset), so that capsule sweeps no longer touch the 70 children. Combined with C-01, every part's transform is computed exactly once a frame.

**C-03: No animation LOD, no visibility gating, no tick intervals anywhere**
- **Evidence:** a grep for `TickInterval`, `WasRecentlyRendered`, `Significance` and `SetComponentTickInterval` finds nothing. Every unit runs the full gait solve, leg IK, sword, 20-panel spring cape (sub-stepped at 90 Hz, `VLKing.cpp:3170-3179`) and, for archers, the bow pose, every frame. That includes units off screen and units drawn as HUD pips in the far overview (the HUD switches to pips beyond 75 m).
- **Impact: High** in the overview and in big battles (30-70 % of the C-01 cost).
- **Effort:** Low. **Risk:** Low. Far units stutter only if the thresholds are too aggressive.
- **Fix:** a per-unit significance step.
  - Not recently rendered: no `Animate` (keep the gait phase advancing) and no cape.
  - Far (beyond about 60 m from the camera, or HUD pips on): pose at 15-20 Hz, cape frozen or rigid, archer pose only while shooting.
  - Units the player controls: always full rate.
  - `UVLArcherCombat` ticks unconditionally (`VLArcherCombat.cpp:70-75`). Disable its tick while idle and at rest.

**C-04: Every troop carries the king's camera rig, its own overview camera actor and a ticking hidden skeletal mesh**
- **Evidence:**
  - The `AVLKing` constructor makes a `SpringArm` and a `Camera` for every unit (`VLKing.cpp:99-112`).
  - `BeginPlay` spawns an `ACameraActor` per unit (`VLKing.cpp:192`).
  - The `USkeletalMeshComponent` is hidden, but `SetComponentTickEnabled(false)` in the constructor did not stop it ticking.
  - Measured ticks: 194 SpringArm, 391 CameraComponent (two per unit) and 194 SkeletalMeshComponent.
  - Each troop also has a `UVLFootDust` ISM (40 hidden instances) and its own MID, although troops have `bFootDust = false` (`VLTroop.cpp:11`).
- **Impact: Medium:** about 1-2 ms of game thread at 200 units. It also removes about 200 actors and 400 or more components.
- **Effort:** Low. **Risk:** Low. Control can pass to a troop (`TakeControlOf`), so create the camera rig lazily there, or move the player's camera to the controller or to one shared actor.
- **Fix:**
  - Create `Boom`, `Camera` and `OverviewCamera` only for a player-controlled unit.
  - Set `GetMesh()->PrimaryComponentTick.bStartWithTickEnabled = false` and `SetComponentTickEnabled(false)` after registration, or swap the default skeletal mesh component for nothing via `ObjectInitializer.DoNotCreateDefaultSubobject`.
  - Create `Dust` only when `bFootDust` is set.

**C-05: Character movement, 5.5 ms at 194 troops (about 28 µs a unit)**
- **Evidence:**
  - CSV `Exclusive/GameThread/CharacterMovement` is 5.47 ms.
  - FindFloor, step-up and penetration sweeps run against complex-as-simple trimeshes (buildings 55-70 k faces, ground tiles about 9.4 k faces each, tree trunks).
  - All idle troops still run the full CharacterMovement tick.
- **Impact:** Medium to high.
- **Effort:** Medium. **Risk:** Medium. Movement feel and stuck behaviour need retesting.
- **Fix:**
  - After C-02, disable the movement component's tick for units standing still with no order (re-enable on an order, a hit or a knock).
  - Use simpler collision (P-06) so sweeps are cheaper.
  - Consider a custom walking mode for AI troops on orders that takes Z from `UVLGrid` nodes instead of floor sweeps (the NavWalking idea); the grid already knows every floor.

**C-06: AutoSteer separation is O(n²) every frame, with an actor iterator per moving unit**
- **Evidence:** `VLKing.cpp:605-620`. Each moving AI unit builds a `TActorIterator<AVLKing>` (which gathers the class's objects into a fresh array) and tests every unit.
- **Impact: Medium:** 200 moving units means 40 k pair tests plus 200 iterator constructions a frame, about 1-2 ms.
- **Effort:** Low. **Risk:** Low.
- **Fix:** a per-frame unit array (C-07) plus a uniform spatial hash (about 2 m cells) rebuilt once a frame. Query only the 3×3 neighbouring cells.

**C-07: Many `TActorIterator` sites; no unit registry** (84 iterator sites, about 40 over `AVLKing`)
- **Evidence:**
  - `UVLBattle::FindFoe` (`VLBattle.cpp:1573`): iterator per unit per auto-combat pass. `TickAutoCombat` runs every 0.25 s, so 240 × 240 pair tests plus 240 iterators, a spike every 0.25 s.
  - `GetUnits` and `GetPopulation`: per call.
  - `TickDefence` (`:1487`): every frame.
  - Arrows' `UnitOnPath` (`VLArrow.cpp:387`): per flying arrow per frame.
  - The AI's `Observe` and `Micro` (`VLEnemyAI.cpp:673`, `VLAISquads.cpp:1500+`).
  - `TickShuffle` (`VLGameMode.cpp:979`): every frame.
  - `VLRules::Troop(const FString&)` is a string-compare chain (`VLBattle.cpp:31-68`) called inside these O(n²) loops (`FindFoe` reads `.Notice` per pair). AI code calls it with `TEXT()` literals, building temporary FStrings.
- **Impact: Medium** in aggregate (about 1-3 ms of steady load plus spikes at 200 or more units).
- **Effort:** Medium. **Risk:** Low.
- **Fix:**
  - `UVLBattle` keeps `TArray<AVLKing*> Units[2]` updated on spawn and death (plus a spatial hash refreshed once a frame). Replace the per-unit iterators with it.
  - Give `AVLKing` an `EVLUnitKind` enum and cache its `FTroop&` on spawn.
  - Index `Buildings` by actor: `FindBuilding` is a linear weak-pointer scan, called 4-5 times per fighting unit per frame from the combat components.

**C-08: HUD cost, measured at 3.3 ms with 194 troops** (`Exclusive/GameThread/UI`)
- **Evidence**, checked in code:
  - **Hover pick every frame in the overview** (`VLHUD.cpp:926` → `AVLKing::PickAt`, `VLKing.cpp:966-1085`): up to 8 line traces, then 2 `ProjectWorldLocationToScreen` per live unit. When the pointer is on the ground it also runs a `TActorIterator<AActor>` over the whole level with `ActorHasTag(TEXT("Selectable"))`, which builds an FName per actor.
  - **Route lines** for every selected unit, up to 24 dashes a leg with no cap (`VLHUD.cpp:1377-1452`).
  - **Far-pip diamonds** drawn as about 21 one-pixel `DrawRect`s per unit (`VLHUD.cpp:1166-1221`), plus a 6-platoon `GetPlatoon` / `Contains` scan per player unit.
  - **Text** measured two or three times per string per frame (`VLHUD.cpp:625-668`).
- **Impact: Medium:** 2-3 ms in the overview with large selections.
- **Effort:** Low to medium. **Risk:** Low.
- **Fix:**
  - Pick against `Battle->GetBuildings()` only, and re-pick only when the mouse or the camera moves.
  - Draw one route per group.
  - Draw each pip as one atlas icon, or batch them in one `FCanvasTriangleItem`.
  - Build a unit-to-platoon map once a frame.
  - Cache text widths.

**C-09: Arrows** (`VLArrow.cpp:381-415`, `:536-551`)
- **Evidence:** each flying arrow does a `TActorIterator<AVLKing>` over all units plus a complex line trace every frame.
- **Impact: Medium** in archer battles: 25-40 arrows in the air is about 10 k unit tests a frame; 96 at the pool cap is about 2.5 ms.
- **Effort:** Low. **Risk:** Low.
- **Fix:** gather the foes per team once per `UVLArrows::Tick` (C-07) and broad-phase by segment bounds. A simple trace (not complex) is probably enough against voxel geometry.

**C-10: The enemy commander's periodic spikes** (`VLEnemyAI.cpp`, `VLAISquads.cpp`, `VLAIWorld.cpp`)
- **Evidence:**
  - `MusterPoint` (`VLEnemyAI.cpp:204-213`) falls back to two full `TActorIterator<AActor>` tag scans whenever the map has no `TeamStart` / `Rally` tags (`Map.bHasMuster` is never set on the fallback path). It is called 2-5 times per `Think`.
  - `ChooseStrategy` (`:1070`) and `TryBuild` (`:1441`) scan every actor with `FName::ToString` per tag.
  - `PlanAttack` runs up to 3 castle-to-castle A* searches on the 50 cm grid every strategy look (2-6 s; `VLAISquads.cpp:676-694`).
  - `UnitPower` allocates FStrings per call (`VLEnemyAI.cpp:76-107`).
- **Impact:** Medium for frame-time spikes; low for the average.
- **Effort:** Low. **Risk:** Low.
- **Fix:**
  - Cache the muster point and the vein list in `FVLAIMap`.
  - Cache attack routes for 20-30 s, invalidated on building changes.
  - Use static base powers.

**C-11: Smaller per-frame and per-event game-thread costs** (each is Low impact and Low effort)
- `AVLKing::HitDummies` (`VLKing.cpp:912`): `TActorIterator<AActor>` over the whole level on every sword blow by every unit. Cache the dummies at BeginPlay. `GetDummies` (`VLCommand.cpp:434`) likewise.
- `UVLConstruction::TickSites` and `TickYards`: a TMap per frame and slot recomputation per building per frame. Keep a builder registry, cache the slots, and tick at 5 Hz.
- The placement ghost's validity check runs about 145-260 vertical traces whenever the snapped cell changes (`VLConstruction.cpp:565-770`). Cache per cell for the placement session, or read heights from `UVLGrid`.
- Guards re-path one by one (`VLCommand.cpp:1876-1934`). Group them by ward and use one `FindGroupPaths`.
- The command inbox does `IFileManager::FileExists` 20 times a second (`VLGameMode.cpp:1094-1099`). Compile it out of Shipping.
- `AVLGameMode::TickShuffle`: an iterator plus a TMap rebuilt every frame. Use C-07's registry.
- `VLArcherCombat.cpp:677`: an unguarded `UE_LOG` on every engagement.

### Rendering and GPU

**R-01: Resolution bound; no render scale or upscaling option**
- **Evidence:**
  - `r.ScreenPercentage 50` cut the GPU from 46.6 to 23.6 ms (measured).
  - PIE rendered at 3224 × 1660 (Retina 2×).
  - `Config/DefaultEngine.ini` sets no screen percentage or dynamic resolution, and there is no `DefaultScalability.ini`.
  - The settings menu has only a frame cap (`VLHUD.cpp:98`) and interface scale.
- **Impact: High.** A TSR render scale of 67-75 % should save about 30-45 % of GPU time at Retina resolutions.
- **Effort:** Low. **Risk:** Low. The voxel art is high-contrast: check TSR shimmer on block edges.
- **Fix:**
  - Set `r.ScreenPercentage` 70-75 by default (TSR is the AA method already), or `r.ScreenPercentage.Mode` with a target resolution.
  - Add a "Render scale" slider.
  - Optionally enable dynamic resolution (`r.DynamicRes.OperationMode 1` with a target frame time) in battles.
  - Verify what the packaged game renders at on Retina displays.

**R-02: Lumen screen probe gather is the largest GPU pass (4.2-11.9 ms)**
- **Evidence:**
  - `Tools/ue/build_level.py:146-147` sets `lumen_final_gather_quality 2.0` and `lumen_scene_detail 2.0` on the level's post-process volume. `build_realm.py:181` (and the highland and town builders) reuse it.
  - `DefaultEngine.ini` already uses `ScreenProbeGather.DownsampleFactor=32` and `TraceMeshSDFs=0`. Quality 2 multiplies the gather's tracing back up.
  - Turning Lumen and volumetric fog off together saved 3.5 ms in the light state.
- **Impact: High** (2-6 ms, likely).
- **Effort:** Low. **Risk:** Medium (the bounce light and look need an A/B).
- **Fix:**
  - Set the final gather quality to 1 and scene detail to 1, and A/B the look with `Tools/compare.py`.
  - Tie the Lumen quality to `sg.GlobalIlluminationQuality` so the player can lower it (S-01).
  - Consider `r.Lumen.ScreenProbeGather.ShortRangeAO 0` and fewer reflection traces (the roughness is 0.9 almost everywhere: `r.Lumen.Reflections.MaxRoughnessToTrace`).

**R-03: Volumetric fog (1.6-5.8 ms; off saved 4.2 ms)**
- **Evidence:**
  - `build_level.py:120-124` sets volumetric fog on, 120 m distance, sun scattering 1.6 (`:41`).
  - 122 (realm) and 154 (highlands) lamp point lights each have `volumetric_scattering_intensity 0.6` (`build_level.py:258`).
  - The pass was `VolumetricFog::ConservativeDepth` dominated.
- **Impact:** Medium to high.
- **Effort:** Low. **Risk:** Low to medium (the god rays are part of the look).
- **Fix:**
  - Set `r.VolumetricFog.GridPixelSize` to 16-24 and `GridSizeZ` to 48.
  - Set the lamps' volumetric scattering to 0 (or leave it on only near the hero).
  - Fade out or switch off volumetric fog when the overview pulls far back.
  - Add a quality option.

**R-04: Draw-call count (about 12.7 k Metal draws a frame with 194 troops)**
- **Evidence:** section counts from `SourceArt/Meshes/*.gltf`:

  | Mesh | Sections |
  |---|---|
  | SM_Swordsman (34 parts) | 59 |
  | SM_Archer (38 parts) | 70 |
  | SM_KingB | 74 |
  | SM_Spy | 58 |
  | SM_RealmGround_* (255 tiles) | 1,370 |
  | SM_HighlandGround_* (398 tiles) | 2,270 |
  | buildings | 15-20 each |
  | SM_LanternPost | 4 |
  | SM_Rock_B | 5 |

  - Each voxel slot (`MI_Vox_<slot>`) is a separate material instance, so a separate section.
  - Units render in prepass, base, velocity, VSM and custom depth.
  - Scattered props are single actors: 288 SM_Wheat, 186 fence pieces, about 180 rocks, lily pads and lanterns (`SourceArt/realm.json`).
- **Impact: High** (render thread, RHI, Metal encoding; the CPU side of the GPU too).
- **Effort:** High for (b); Medium for (a), (c) and (d). **Risk:** Medium.
- **Fix:**
  - (a) One `M_Voxel` with all slot textures in a `Texture2DArray` or atlas. The slot index goes in a vertex attribute (UV1 or vertex alpha where free), plus a small per-slot parameter table (roughness, emissive, metallic). Every voxel mesh then becomes one section: units go from about 60 to 1-2 sections, ground tiles from about 5.4 to 1.
  - (b) Each unit as one rigid-skinned skeletal mesh (one bone per part, the cape panels as bones), animated by writing bone transforms (`UPoseableMeshComponent`, or an AnimInstance reading the pose array). That gives 1-3 draws per unit and one transform update per unit, and removes C-01 entirely.
  - (c) Merge ground sections per tile with (a).
  - (d) Move wheat, fences, rocks, lily pads and lantern posts into HISM components, as `AVLForest` already does for trees.

**R-05: No LODs on units, buildings or terrain; very dense unit meshes**
- **Evidence:**
  - Unit triangle counts (part JSONs): Swordsman 63,262, Builder 61,009, Archer 54,969, King 53,750, Spy 42,350.
  - Single parts: SM_Archer_Head 20,059 triangles, SM_Swordsman_Head 18,757, SM_KingB_Chest 14,475 (voxel 1.25 cm).
  - Buildings: SM_Castle 58 k faces (about 116 k triangles), SM_BarracksYard 69 k, SM_ArcheryHall 68 k. No LODs.
  - Ground: L_Realm 1.92 M faces, L_Highlands 3.74 M. No LODs.
  - Only trees and plants have LOD 1 (`Tools/ue/tree_lods.py`, `plant_lods.py`).
  - 240 units is about 13-15 M triangles, drawn into several passes even when they show as 5-pixel pips.
- **Impact: High** for the overview, big battles and the VSM.
- **Effort:** Medium. **Risk:** Low to medium (LOD pops).
- **Fix:**
  - Voxel LODs from the same Blender mesher at 2.5 cm and 5 cm for unit parts. Heads especially: 18 k triangles for a head is enormous.
  - LOD 1 at 50 cm blocks for buildings, as `tree_lods.py` does.
  - Per-part `LDMaxDrawDistance` for tiny parts (bow strings, cape panels, hands) at about 80-100 m.
  - Beyond about 75 m (where the HUD switches to pips), one merged low-poly mesh per unit kind, ideally in an ISM per kind.
  - For ground and buildings: test Nanite on Apple Silicon SM6. These are opaque, have no WPO, and Nanite is already forcing a depth prepass ("PrePass ... (Forced by Nanite)" in ProfileGPU). It would remove the draw-call and LOD problems for static geometry.

**R-06: Custom depth and the silhouette for every unit, including enemies**
- **Evidence:**
  - `VLKing.cpp:236-240`: `SetRenderCustomDepth(true)` on every part of every unit, stencil 1 or 2.
  - `r.CustomDepth=3`.
  - `M_Silhouette` runs as a full-screen post-process each frame.
  - Measured CustomDepth: 0.19-0.69 ms GPU, plus the draw calls in the render thread.
- **Impact:** Low to medium.
- **Effort:** Low. **Risk:** Low.
- **Fix:** write custom depth only for units within about 60 m of the camera (hero view and near overview). Disable it for all units, and the blendable, when the overview is pulled back.

**R-07: Two-sided and WPO `M_VoxSway` on about 10 k plant instances and on unit capes and cloth**
- **Evidence:**
  - `build_special_materials.py:320`: `two_sided True`.
  - `import_assets.py:157-161`: grass, flowers and wheat use `MI_Sway_*`.
  - 8,000 grass tufts, 2,400 flowers and 288 wheat on the realm.
  - WPO means velocity output (RenderVelocities 0.7-1.3 ms) and VSM page invalidation for shadow-casting WPO (wheat, banners, capes).
  - `DefaultEngine.ini` already turns off `UseReceiverMaskDirectional` to stop the shimmer, which makes the sun's VSM render more pages.
- **Impact:** Low to medium.
- **Effort:** Low. **Risk:** Low (the plants are closed voxel blocks: back faces are never seen).
- **Fix:**
  - `two_sided False`.
  - Set `ShadowCacheInvalidationBehavior = Rigid` on swaying shadow casters (wheat, banners). Then try restoring `r.Shadow.Virtual.UseReceiverMaskDirectional=1`.
  - Lower `world_position_offset_disable_distance` (60 m) where the sway is invisible from the overview.

**R-08: Lamp point lights: 122 on the realm, 154 on the highlands**
- **Evidence:** `build_level.py:240-260`: stationary (treated as movable, no static lighting), radius about 300-480 cm, no shadows. DirectLighting was 0.9-3.3 ms.
- **Impact:** Low to medium.
- **Effort:** Low. **Risk:** Low.
- **Fix:**
  - Set `MaxDrawDistance` and `MaxDistanceFadeRange` on the lamps (about 80-120 m: they are invisible from the far overview).
  - Optionally set `bAffectGlobalIllumination=false` so Lumen's surface-cache lighting skips them.

**R-09: Indirect lighting cache updates for 5,700 movable primitives a frame**
- **Evidence:** 5,719 `STAT_UpdateIndirectLightingCacheBuffer` calls, 0.52 ms of render thread (stat timing). `r.AllowStaticLighting=False`, so the cache has nothing to serve.
- **Impact:** Low (about 0.5 ms of render thread).
- **Effort:** Low. **Risk:** None.
- **Fix:** `IndirectLightingCacheQuality = ILCQ_Off` on unit parts, arrows and dust.

**R-10: Sky light real-time capture**
- **Evidence:** `build_level.py:110` sets `real_time_capture True` on a static sun and sky.
- **Impact:** Low.
- **Effort:** Low. **Risk:** None.
- **Fix:** turn it off and recapture once (`RecaptureSky`) on level load.

**R-11: Investigate "VSM Log Stats And Status" at 5.2-10 ms in ProfileGPU**
- **Evidence:**
  - The pass is a single-group compute shader (`VirtualShadowMapArray.cpp:3644-3712`, compiled with `CFLAG_SkipOptimizations`). It still showed 5.2 ms with CSV stopped, and 10 ms in the heavy state.
  - It generates stats when `IsCsvLogEnabled()`, an Insights VSM channel, `r.Shadow.Virtual.Stats.*` or page-area diagnostics are on (`:2488-2498`).
  - It is most likely a profiling or editor artifact: a timer absorbing overlapping work, or the editor's trace channels. It could also be real cost in Development builds.
- **Impact:** Unknown. Possibly High in Development packages.
- **Effort:** Low (one capture).
- **Fix:** run `ProfileGPU` in the packaged Development build (and with `-trace=none`). If the pass is still there, find which condition enables stats. Shipping builds compile most of it out.

**R-12: `dynamic_shadow_distance_movable_light 110000` on the realm and highlands**
- **Evidence:** `build_realm.py:148-152` and the highland equivalent. Under VSM (`r.Shadow.Virtual.Enable=1`) the directional clipmaps ignore this distance. If a lower quality level falls back to cascaded shadow maps, 1,100 m cascades are extremely expensive and blurry.
- **Impact:** Low now; High under a CSM fallback.
- **Effort:** Low. **Risk:** Low.
- **Fix:** keep it for VSM, but set a sane CSM distance in the scalability levels without VSM (`r.Shadow.DistanceScale` or the per-level `r.Shadow.MaxCSMResolution` / cascades), or keep VSM on all levels.

**R-13: Title backdrop and minimap**
- **Evidence:**
  - The title screen renders the full realm with Lumen, fog and VSM behind the menu at the game's frame cap (60 by default).
  - The minimap capture runs every frame for the first 1.5 s of a match with lighting, shadows and Lumen show flags still on (`VLHUDGame.cpp:425-496`). The capture source is BaseColor.
- **Impact:** Low (power and heat in menus; a load-time hitch).
- **Effort:** Low. **Risk:** None.
- **Fix:**
  - Cap the menus at 30 fps and/or lower the screen percentage behind the title.
  - Capture the minimap 2-3 frames with Lighting, DynamicShadows, GlobalIllumination, Lumen, AO, Atmosphere and AntiAliasing off, then release the view state.

### Memory, load time and package size

**P-01: The NNE denoiser plugin ships about 200 MB of unused data**
- **Evidence:**
  - The `.ucas` holds `Engine/Plugins/NNE/NNEDenoiser/Content/*oidn*` (46.3 + 42.9 + 6.9 + 3.4 + 2.4 + 1.2 MB, 103 MB in all).
  - The app holds `Contents/UE/Engine/Plugins/NNE/NNERuntimeORT` (97 MB of dylibs).
  - Nothing in the game uses the path tracer or Movie Render Queue denoising. The plugins are enabled by engine default.
- **Impact: High** for size (about 13 % of the app); it also loads a 97 MB runtime at startup.
- **Effort:** Low. **Risk:** None.
- **Fix:** in `VoxelLab.uproject`, add `{ "Name": "NNEDenoiser", "Enabled": false }` and `{ "Name": "NNERuntimeORT", "Enabled": false }`. Check the plugin list for other default-on runtime plugins with content (Interchange content is also cooked: 3.3 MB).

**P-02: The package is a Development build with symbols**
- **Evidence:** `Config/DefaultGame.ini` has `BuildConfiguration=PPBC_Development`, and `Tools/package.sh` defaults to Development. `MacOS/VoxelLab` is 413 MB arm64 with a 173 MB `__LINKEDIT` segment.
- **Impact: High** for size; Medium for CPU (Shipping drops stats, checks and logging: typically 5-15 % of game thread).
- **Effort:** Low. **Risk:** Low: Shipping has no console, and testing relies on `vl.*` and the command inbox. Keep Development for test builds.
- **Fix:** ship a Shipping build (`sh Tools/package.sh Shipping`), with symbols stripped (UBT's strip / `-nodebuginfo`). Compile the inbox poll and debug-only commands out with `#if !UE_BUILD_SHIPPING`.

**P-03: Shaders are cooked for both METAL_SM5 and METAL_SM6**
- **Evidence:**
  - The engine's `BaseEngine.ini` defaults `+TargetedRHIs=SF_METAL_SM5` and `+TargetedRHIs=SF_METAL_SM6`.
  - The project does not override them.
  - Shader type stats: SM6 188 MB raw, SM5 80 MB raw; `<ShaderCode>` is 165 MB on disk.
  - SM6 also carries hardware ray-tracing and MegaLights global shaders, although `raytracing="0"` (`FHardwareRayTraceLightSamplesCS` 10.8 MB, `FShadeLightSamplesCS` 10 MB, `FGenerateLightSamplesCS` 8.3 MB, `FLumenReflectionHardwareRayTracingCS` 6.3 MB).
- **Impact:** Medium (about 60-80 MB, and cook time).
- **Effort:** Low. **Risk:** Low, if Apple Silicon (SM6) is the only target. SM5 serves Intel Macs.
- **Fix:**
  - In `Config/Mac/MacEngine.ini`, under `[/Script/MacTargetPlatform.MacTargetSettings]`, use `-TargetedRHIs=SF_METAL_SM5`.
  - Disable unused features at project level so their global shaders are not compiled: `r.MegaLights.Allow 0`, hardware ray tracing off, `r.Nanite.ProjectEnabled 0` if R-05's Nanite test is not adopted.

**P-04: Ground tiles are 480 MB of the 1.0 GB content, and their collision and distance fields cost runtime memory**
- **Evidence:**
  - `.ucas` spans: SM_HighlandGround_* 256 MB (398 tiles, 3.74 M faces), SM_RealmGround_* 149 MB (1.92 M faces), SM_TownGround_* 27 MB, SM_Flat_* 25 MB, SM_Terrain_* 23 MB.
  - About 68 bytes a face on disk after Oodle.
  - Every tile is imported with complex-as-simple collision (`import_assets.py:202-204`), full-precision UVs (`:152`), recomputed tangents (`:151`), and a mesh distance field (`r.GenerateMeshDistanceFields=True`).
  - `realm_terrain.merge_quads` only joins faces 2 × 2, because per-block colour variation and baked corner shading live in the vertex colours.
- **Impact: High** for size and memory: GPU vertex and index data, Chaos trimeshes and distance fields for 1.9-3.7 M faces per map.
- **Effort:** Medium to high. **Risk:** Medium (the look of the ground).
- **Fix:**
  - (a) Move per-block colour jitter into the material: a hash of the block coordinate, from world position. The mesher can then greedy-merge large coplanar runs that share an AO pattern. Expect 3-10× fewer ground faces.
  - (b) Give each tile a separate, geometry-only greedy collision mesh (`UStaticMesh::ComplexCollisionMesh`). Collision then stops scaling with visual detail, and grid build, sweeps and traces all get cheaper.
  - (c) Try `use_full_precision_u_vs False` (UVs index a small palette texture) and a lower `DistanceFieldResolutionScale` on tiles.
  - (d) Stop cooking dev and legacy content. `DirectoriesToAlwaysCook=/Game/Voxel` forces in every unreferenced asset (SM_KingA_* 5 MB, SM_Tree_* 8 MB, SM_Terrain_* 23 MB, King/troop backups). `MapsToCook` includes L_Flatlands (a review map) and L_VoxelVillage.

**P-05: Music loaded synchronously, kept resident, and decoded while muted**
- **Evidence:**
  - `VLGameMode.cpp:877-884` does `LoadObject` for all 8 songs in `BeginPlay`.
  - `Tools/ue/import_audio.py:56-58` sets `RETAIN_ON_LOAD`, although its docstring says "the songs stream". That keeps about 58 MB of compressed audio (6.5-9.8 MB each) in memory.
  - `MusicSetting` is forced to 0 (`VLGameMode.cpp:868`), but `NextSong` still creates the component and calls `FadeIn(3, max(…, 0.0001))` (`:939-948`). A 48 kHz stereo song is decoded and mixed at -80 dB all match long.
- **Impact:** Medium for memory (about 50 MB); Low for CPU (one decoder); Low for load time (a sync load of 8 assets on each map start).
- **Effort:** Low. **Risk:** None.
- **Fix:**
  - Set the songs to `LoadOnDemand` / streaming (the default with stream caching).
  - Hold them as soft references and load the next song asynchronously near the end of the current one.
  - Do not create or play `Music` while the setting is 0, and stop it when the setting goes to 0.

**P-06: Complex-as-simple collision on 816 meshes, including water, sea and backdrop**
- **Evidence:**
  - `import_assets.py:202-204` makes every mesh whose JSON says `"collision": "complex"` (816 of 1,031) `CTF_USE_COMPLEX_AS_SIMPLE`. That includes SM_HighlandWater (282 k faces), SM_HighlandSea (199 k), SM_RealmWater (192 k) and SM_RealmSea (111 k).
  - At runtime the water has no collision except for the grid build's `LineTraceComponent` (`VLGrid.cpp:176-192`), and the backdrop has none.
  - Buildings are 42-70 k faces of trimesh.
- **Impact:** Medium for memory and cook size (Chaos trimesh data); also speeds C-05, P-07 and the arrow traces.
- **Effort:** Medium. **Risk:** Low to medium.
- **Fix:**
  - Water and sea: set their collision to none and give the grid its water heights from the layout JSON (or one flat box per sheet).
  - Props and fences: simple boxes.
  - Buildings: a coarse 50 cm collision mesh via `ComplexCollisionMesh`.

**P-07: Path grid build at match start, the area rebuild hitch, and the grid's memory**
- **Evidence:**
  - Measured `GRID built ... 832x832 ... in 1056 ms` (L_Realm). The README gives 2.4 s for 1080 × 1080 on the highlands.
  - `UVLGrid::Build` (`VLGrid.cpp:113-296`) samples 1.17 M cells serially, each with at least one line trace and a capsule overlap.
  - One building placement measured `GRID area ... 4356 cells ... in 21.7 ms` (a dropped frame each time).
  - `FNode` is 48 bytes (`VLGrid.h:63-70`) plus 16 bytes of A* scratch per node, and 9 bytes per cell. The realm's 494 k nodes come to about 32 MB plus 6 MB of cells; the highlands about 60-80 MB.
- **Impact: Medium** (load time: 1-2.4 s; the hitch; memory).
- **Effort:** Low (ParallelFor) or Medium (baking). **Risk:** Low.
- **Fix:**
  - `ParallelFor` over rows. Chaos scene queries are thread-safe for reads; build per-row node lists, then concatenate and fix up `First`. Expect a 5-8× speed-up on an M-series CPU.
  - Or bake the grid at level-build time into a per-map asset (the levels are generated by script anyway) and only `RebuildArea` at runtime. Run `RebuildArea` in parallel too.
  - Compact the nodes: Z as int16 at 1 cm steps; neighbours as an 8-bit mask plus a per-direction layer index instead of 8 × int32. That is about 4× smaller.

**P-08: Unit spawn cost**
- **Evidence:** `BuildFigure` creates and registers about 70 components (and a MID, a dust ISM with 40 instances, a camera actor) per unit at runtime (`VLKing.cpp:254-375`).
- **Impact:** Low (a 1-3 ms hitch per spawn; noticeable with `vl.SpawnTeam` or simultaneous training).
- **Effort:** Low to medium.
- **Fix:** C-04 removes part of it. Pool dead units' actors for reuse, and prewarm one of each kind at match start.

### Scalability

**S-01: No graphics quality settings; no `DefaultScalability.ini`**
- **Evidence:** the settings screen has volume, frame cap (30 / 60 / 120 / unlimited), camera, look speed, invert and interface scale (`VLHUDMenus.cpp`, `VLHUD.cpp:55-117`). No `sg.*`, `GameUserSettings` scalability, render scale or GI, shadow or fog choices.
- **Impact: High** for players on lower-end Macs (M1 and M2 base models at about a third of an M5 Pro's GPU).
- **Effort:** Low to medium. **Risk:** Low.
- **Fix:** a Graphics section driving `UGameUserSettings`:
  - Quality preset (`SetOverallScalabilityLevel`).
  - Render scale (R-01).
  - Global illumination: Lumen high / low / off, with SkyLight and SSAO as the fallback.
  - Volumetric fog on or off.
  - Shadows (VSM / low).
  - Foliage distance: scale `build_realm.CULL` through `foliage.LODDistanceScale` or the HISM cull-distance scale.
  - Add a `Config/DefaultScalability.ini` with per-level values tuned for this game.

---

## Already fine (checked, no action)

- **Enemy commander:** `FVLCommander::Step` only advances clocks; `Think` (0.6-1.5 s), strategy (2-6 s) and micro (0.5-1 s) are timer-gated. The influence map is 10 m cells (784 cells on the realm), rebuilt once per think, under 0.05 ms.
- **Path queries:** `OrderMove` issues one `FindGroupPaths` per order (one flood per region, straight-line shortcut), not one per unit.
- **Troop footsteps** are off (`VLTroop.cpp:11-12`). The shuffle uses group timers. Sword and arrow sounds are gap-throttled.
- **Arrows:** a component pool capped at 96; no per-shot `NewObject` after warm-up; logs behind `vl.ArcherLog`.
- **`AVLForest`:** one HISM per mesh kind; it ticks only during a dust poof. Grass and flower cull distances and LOD 1 are in place. `bAffectDistanceFieldLighting` is off for crowns and undergrowth.
- **Unit parts:** `NoCollision` and `bAffectDistanceFieldLighting=false`. `bCastContactShadow` is set, but no light has a contact shadow length, so it costs nothing.
- **Hit flash:** one MID per unit, overlay removed when done.
- **Minimap steady state:** `bCaptureEveryFrame=false`, 512², units hidden.
- **`DrawHealthBars`, platoon tags, order markers, training bars:** small counts; ground plates are batched.
- **Textures:** 0.5 MB in all (`never_stream`, Pixels2D group).
- **Hardware ray tracing** is off at runtime (`raytracing="0"` in the cook log), so there is no BLAS memory.

## Suggested order for the fix pass

1. Do these together:
   - P-01 (NNE off)
   - P-02 (Shipping and strip)
   - P-03 (SM6 only)
   - P-05 (music)
   - R-01 (render scale)
   - C-04 (per-troop camera rig, skeletal mesh tick, dust)
   - R-09, R-10, C-11's small items

   All are low effort and low risk: about 0.5 GB off the package, about 30-45 % of GPU time at Retina resolutions, and about 1-2 ms of game thread at 200 units.
2. C-01, C-02, C-03 (the rig: about 10-15 ms of game thread at 200 units), with C-06 and C-07 (the unit registry and spatial hash), C-08 (HUD) and C-09 (arrows).
3. R-02, R-03 and S-01 (Lumen and fog quality and a Graphics menu), A/B'd against the reference shots.
4. P-07 (parallel or baked grid) and C-05 (movement).
5. The structural changes, each its own project:
   - R-04(a): atlas material
   - R-05: LODs, a far-unit proxy, and the Nanite test for static geometry
   - P-04: greedy ground and collision meshes
   - R-04(b): skinned units