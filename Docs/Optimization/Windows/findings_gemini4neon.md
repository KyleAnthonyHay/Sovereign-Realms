# Sovereign Realms — Windows PC Performance Optimization Audit (`GN`)

## Executive Summary

Sovereign Realms on Windows (Ryzen 5 7600X, RX 9070 GRE 12 GB, DX12/SM6, UE 5.8.4) is **100% Game-Thread bound** across all six baseline captures (`15.5–25.1 ms` mean GT vs `4.1–16.1 ms` RT and `6.8–12.0 ms` GPU), with severe `p99` frame-pacing spikes (`49.7–62.2 ms` periodic, `196–240 ms` max).
1. **Game Thread (`10.9–14.4 ms` in `CharacterMovement` alone, 60–70% of GT):** `313` characters run full `UCharacterMovementComponent` floor sweeps every frame (`bAlwaysCheckFloor=true`, `bUseFlatBaseForFloorChecks=true`) while `FollowPath`/`StopOrder` toggles `ECC_Pawn` between `Ignore` and `Block`, causing **616 `"is stuck and failed to move!"` depenetration storms** in 4 minutes. Another **348 unused `AAIController`s** tick every frame (`34%` of all ticks).
2. **Hitches (`100%` of `>50 ms` spikes are `Tickables`):** Every `2.44 s`, `FVLCommander::ChooseStrategy` -> `PlanAttack` -> `RouteDefence` runs synchronous 50 cm A* searches across the `1,096,134`-node `UVLGrid` (`28–41 ms` spikes). When an attack launches, `LaunchAttack` re-runs `PlanAttack` plus flank routes plus `FindGroupPaths` on the **same tick**, producing the **`175.6 ms` (1080p) and `218.1 ms` (1440p) mountain freezes**. Building placements add `25–32 ms` full-map `LabelRegions` hitches (`68` consecutive calls = `~1.8 s` at `TestWorld` start).
3. **Render Thread (`10.2–16.1 ms`) & GPU (`6.8–12.0 ms`):** Once GT drops below `10 ms`, RT becomes the bottleneck due to three massive draw-call multipliers: (a) UE 5.8 defaults to **`r.HZBOcclusion=0`**, issuing **`12,505–12,662` hardware occlusion query draw calls/frame** (`4.88 ms` GPU at 1440p — #1 GPU pass!); (b) `vl.Opt.UnitDepthFar=40000` (400 m) causes **`4,505–5,323` mean / `11,030` max `CustomDepth` draw calls** in `mountain` view; and (c) `UVLConstruction::SpawnProps` spawns **~1,750 individual `Movable` `AStaticMeshActor`s** (84 un-instanced `SM_Wheat` actors per farm!).
4. **Churn, PSOs & Assets:** `AVLAmbience` and `AVLSky` pass `bMarkRenderStateDirty=true` on `UpdateInstanceTransform`, tearing down and re-adding **`574–1,099` GPUScene instances every single frame**. Windows lacks a `.stable.upipelinecache` (and `D3D12.PSO.DiskCache` is deprecated in UE 5.8), has `34–44` PSO misses, mid-match `FlushAsyncLoading` stalls, and **both `MI_Vox_smoke` and `MI_Vox_mote`** lack `InstancedStaticMeshes` usage on `M_Voxel`.
5. **Combined outcome:** Executing Batches 1–3 below is projected to bring **1440p High** from `~40–43 fps` (`23.3–25.1 ms` mean, `240 ms` max) to a steady **`85–110+ fps` (`9–12 ms` GT, `6–9 ms` RT, `6–8 ms` GPU, `< 18 ms` p99)** with zero visual degradation on High and full Mac parity.

---

## Status of Earlier Plan (`Docs/Optimization/PLAN.md`) in Current Code

Verified directly against `Source/SovereignRealms/` and `Config/`:
- **Landed and active:** `A1` (`RigPose`/`RigFlush`/`RigLateUpdate`, `CustomDepth` gate, `UnitGI=0`), `A2` (unit LODs in `Tools/ue/voxel_lods.py`), `A3` (`VLFootDust` zero-scale pool), `B1` (`UVLBattle` unit/building/dummy/mine registries + spatial hash), `B2` (`AVLFarmer::UpdateTickRate` — note `0.25 s` causes occasional `Max iterations 8 hit` on hitches), `B3` (`UVLGrid::Build` `ParallelFor` + union-find `LabelRegions` + `RebuildAreas`), `B5` (`UVLConstruction` placement memo), `C1–C5` (Lumen off, `r.AmbientOcclusionLevels=0`, VSM off, lamp cull/fade, wheat WPO disable, one-sided sway, plant/tree/ground LODs), `D1–D2` (presets + menu cap), `E1–E2` (Mac cook/PSO).
- **Partially landed / missed sub-items:**
  - `B4` (`AVLHUD`): `UnitsThisFrame()` and `BeginRects`/`EndRects` landed, **but `DrawFarPips` (`VLHUD.cpp:1521-1535`) still renders every diamond with two nested `dy += 1.f` scanline loops (~22–28 quads/unit instead of 2 triangles/quads)**.
  - `A1` (`VLKingRig.cpp`): `UnitDepthFar` is `40000 cm` (400 m) and still includes enemies, ambient farmers, tower guards, and all ~25–30 parts per unit (`5,323` CustomDepth draw calls in `mountain`).
  - `A3` (`VLFootDust`): fixed for dust, **but `AVLAmbience` (`VLAmbience.cpp:115, 174, 215`) and `AVLSky` (`VLSky.cpp:20, 132, 177`) still park hidden instances at `Z = -100000` and pass `bMarkRenderStateDirty=true` every frame**.
  - `E2` (PSO cache & shader stripping): only configured for Mac (`Config/Mac/MacEngine.ini`); Windows lacks `.stable.upipelinecache` collection and still cooks RayTracing/Lumen/VSM/Nanite shader permutations.

---

## Detailed Findings

### GN-01 — Stop Troop-on-Troop `ECC_Pawn` Penetration Storms & Disable Redundant `CharacterMovementComponent` Floor Sweeps
- **Area:** Game thread
- **Where:**
  - `Source/SovereignRealms/VLKing.cpp`: `AVLKing::AVLKing()` (`L78–L94`), `AVLKing::FollowPath()` (`L515`), `AVLKing::StopOrder()` (`L568`), `AVLKing::Die()`
  - `Source/SovereignRealms/VLCommand.cpp`: `UVLCommand::Enter()` (`L1251–L1273`), `UVLCommand::Leave()` (`L1275–L1310`)
  - Engine reference verified: `UE_5.8/Engine/Source/Runtime/Engine/Private/Components/CharacterMovementComponent.cpp` (`L798`, `L7235–L7269`, `L7348–L7368`)
- **Evidence:**
  - Across all 6 CSV captures, `Exclusive/GameThread/CharacterMovement` is **`10.90–14.37 ms/frame`** (`60–70%` of total GT) with **`313.0` CMC ticks/frame** (`312 VLTroop` + `1 VLKing`).
  - `Saved/Perf/1080p/game.log` contains **616 `"is stuck and failed to move!"` warnings** in 4 minutes — 100% are `VLTroop` capsules penetrating another `VLTroop`'s `CollisionCylinder` (`PenetrationDepth: 8.8–15.1 cm`).
  - `FollowPath()` (`VLKing.cpp:515`) sets `ECC_Pawn -> ECR_Ignore` so marching troops pass through each other, then `StopOrder()` (`VLKing.cpp:568`) immediately restores `ECC_Pawn -> ECR_Block`. Overlapping arriving troops instantly lock into penetration; every subsequent nudge or step triggers `ResolvePenetration` + `SafeMoveUpdatedComponent` retry loops and log spam.
  - `AVLKing::AVLKing()` leaves `Move->bAlwaysCheckFloor = true` (UE default, `CharacterMovementComponent.cpp:798`) and `Move->bEnablePhysicsInteraction = true`, and sets `Move->bUseFlatBaseForFloorChecks = true` (`VLKing.cpp:92`). In UE 5.8 (`CharacterMovementComponent.cpp:7235, 7352–7368`), `bAlwaysCheckFloor=true` forces **every stationary troop and garrisoned tower archer** to execute `ComputeFloorDist` -> `FloorSweepTest` every frame, and `bUseFlatBaseForFloorChecks=true` performs **1–2 rotated box sweeps** against the complex voxel terrain trimesh per floor check.
- **Change:**
  1. **Keep `ECC_Pawn = ECR_Ignore` for AI troops (`AVLTroop`) at all times** (keep `ECR_Block` only on the player-controlled pawn, or apply soft separation in `AutoSteer` / `TickYield` when idle troops overlap). Update `VLKing.cpp:515, 568` and `AVLTroop::AVLTroop()` so troops never lock capsules in penetration.
  2. **Disable unnecessary floor sweeps & physics interaction** in `AVLKing::AVLKing()` (`VLKing.cpp:78–94`):
     ```cpp
     Move->bAlwaysCheckFloor = false;           // UE 5.8 CharacterMovementComponent.cpp:7235 reuses CurrentFloor while stationary on static ground, still re-checks on any move/teleport/base change
     Move->bEnablePhysicsInteraction = false;   // no Chaos rigid-body pushing in voxel RTS
     ```
     And in `AVLTroop::AVLTroop()` (`VLTroop.cpp`), set `GetCharacterMovement()->bUseFlatBaseForFloorChecks = false;` (keep `true` on `AVLKing` hero for crisp ledge platforming; AI troops walk on `UVLGrid` cells away from cliff edges and do not need dual-box floor sweeps).
  3. **Disable CMC tick when garrisoned or dead:** In `UVLCommand::Enter()` (`VLCommand.cpp:1271`), call `Unit->GetCharacterMovement()->SetComponentTickEnabled(false);` (re-enable in `UVLCommand::Leave()`, `VLCommand.cpp:1308`). Likewise disable CMC tick in `AVLKing::Die()` once grounded/settled (re-enable on King respawn).
- **Expected gain:** **5.0–7.5 ms/frame on GameThread** (`CharacterMovement` drops from `10.9–14.4 ms` to `~4–7 ms`); eliminates all `616` stuck/depenetration warnings.
- **Risk:** Low. With `ECC_Pawn = ECR_Ignore` on troops, idle troops arriving at the exact same fallback point could visually overlap slightly if `FitSlots` fails; mitigate with a tiny `10 Hz` idle separation nudge in `AutoSteer` when two stationary troops are `< 60 cm` apart (already how marching separation works). With `bAlwaysCheckFloor = false`, `FindFloor` still triggers automatically if a building beneath a unit loses collision (`CharacterMovementComponent.cpp:7251`).
- **Platforms:** Both (Windows + Mac)
- **Verify by:** Run `Tools/windows/perf_capture.ps1` (or `vl.Perf` + `csvprofile`): confirm `Exclusive/GameThread/CharacterMovement` drops by `>= 5 ms`, zero `"is stuck and failed to move!"` lines in `game.log`, and units still stand properly on ground, stairs, bridges, and tower lookouts (and fall/respawn properly if a building collapses).
- **Confidence:** High

---

### GN-02 — Sleep Idle Grounded `AVLTroop` CMCs & Throttle Off-Screen/Distant Troop Movement (Plus Optional Grid-Walk Fast Path)
- **Area:** Game thread
- **Where:**
  - `Source/SovereignRealms/VLTroop.h/.cpp`, `Source/SovereignRealms/VLKing.cpp` (`AVLKing::Tick`, `PollInput`, `FollowPath`, `ReceiveDamage`)
  - `Source/SovereignRealms/VLFarmer.cpp` (`AVLFarmer::UpdateTickRate`, `L54–L68`)
- **Evidence:**
  - In `base` view, almost all `312` troops are off-screen, yet `Ticks/CharacterMovementComponent = 313.0` every frame and `CharacterMovement = 10.90–11.88 ms`.
  - `AVLFarmer::UpdateTickRate` (`VLFarmer.cpp:54–68`) already throttles 36 farmers' tick interval (`0.05–0.25 s`) to save CPU — however, `1440p/game.log:4539–4540` shows `GetSimulationTimeStep() - Max iterations 8 hit` on farmers when a hitch combines with a `0.25 s` tick interval (exceeding `MaxSimulationTimeStep (0.05) * 8 = 0.4 s` or triggering multi-substep bursts).
- **Change:**
  1. **Phase A (low risk — CMC sleep + safe distance throttle):**
     - Sleep `UCharacterMovementComponent` (`SetComponentTickEnabled(false)`) on non-player `AVLTroop`s that are grounded (`IsMovingOnGround()`), idle (`!bAutoWalk && Velocity.SizeSquared() < 1.f && GetPendingInputVector().IsNearlyZero()`), and not recently hit/knocked back (`> 0.5 s`). Wake immediately in `FollowPath()`, `AddMovementInput()`, `LaunchCharacter()`, `ReceiveDamage()`, and `TakeControlOf()`.
     - For walking non-player `AVLTroop`s that are **off-screen** (outside `RigLate`'s frustum) or **> 200 m from camera**, set `Move->SetComponentTickInterval(0.033f)` (30 Hz) — strictly below `MaxSimulationTimeStep = 0.05f` so it always runs **1 simulation substep** (zero `Max iterations` warnings, and cap `AVLFarmer::UpdateTickRate` max interval at `0.05f` for its CMC while keeping actor AI tick at `0.25f`).
  2. **Phase B (optional follow-up — kinematic `UVLGrid` walking for distant/off-screen troops):**
     - When `!IsPlayerControlled() && bAutoWalk && !IsFalling()` and `UVLGrid::NodeAt(Feet)` is valid (and not on a steep/bridge transition), step `Location += Velocity * Dt` and set `Z = Grid->NodePos(Node).Z + CapsuleHalfHeight` without running Chaos sweep queries; fall back to full CMC immediately on knockback, `IsFalling()`, missing grid node, or player possession.
- **Expected gain:** Phase A: **2.5–4.0 ms GT** (on top of `GN-01`); Phase B: **additional 2.0–3.5 ms GT** (total `CharacterMovement` `< 2.0 ms` with 300+ troops!).
- **Risk:** Phase A: Low (must ensure every wake trigger re-enables CMC tick; `SetComponentTickInterval` for CMC must stay `<= MaxSimulationTimeStep` to avoid substep explosions). Phase B: Medium (requires testing stairs, bridges, narrow gates, and knockback handoff).
- **Platforms:** Both (Windows + Mac)
- **Verify by:** Check `Ticks/CharacterMovementComponent` and `Exclusive/GameThread/CharacterMovement` across `base`/`mountain`/`overview`, confirm zero `Max iterations` warnings in `game.log`, and run `Tools/aivsai.py` / combat duel test to verify identical troop positioning and knockback.
- **Confidence:** High (Phase A) / Medium (Phase B)

---

### GN-03 — Remove 348 Unused `AAIController` Actors Using `bRunPhysicsWithNoController = true`
- **Area:** Game thread (and Memory / GC)
- **Where:**
  - `Source/SovereignRealms/VLTroop.cpp:15` (`AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;`)
  - `Source/SovereignRealms/VLKing.cpp:58` (`AIControllerClass`), `L78–L94` (`UCharacterMovementComponent` setup), `L2512–L2546` (`AVLKing::PollInput`)
  - `Source/SovereignRealms/VLFarmer.cpp` (inherits `AVLTroop`)
  - Engine reference verified: `UE_5.8/Engine/Source/Runtime/Engine/Private/Components/CharacterMovementComponent.cpp` (`L1751–L1753`, `L5662`, `L5686`, `L5901`, `L6637`)
- **Evidence:**
  - Every baseline CSV shows **`ActorCount/AIController = 348`** and **`Ticks/AIController = 348`** every single frame — **34% of `Ticks/Total` (`1,005–1,016`)**!
  - Neither `AVLTroop` nor `AVLFarmer` uses `UBehaviorTree`, `UBlackboardComponent`, `UAIPerceptionComponent`, `UPathFollowingComponent`, or `AAIController::MoveTo`. All movement calls `AddMovementInput()` directly from `AVLKing::PollInput()`.
  - Verified in UE 5.8 `CharacterMovementComponent.cpp:1751–1753`: `bShouldPerformControlledCharMove` evaluates `|| (!CharacterOwner->GetController() && bRunPhysicsWithNoController)`, which consumes `PendingInputVector` and runs full `PerformMovement` without any `AController`!
- **Change:**
  1. In `AVLKing::AVLKing()` (`VLKing.cpp:78–94`): add `Move->bRunPhysicsWithNoController = true;` and `AIControllerClass = nullptr;`.
  2. In `AVLTroop::AVLTroop()` (`VLTroop.cpp:15`): change `AutoPossessAI = EAutoPossessAI::Disabled;`.
  3. In `AVLKing::PollInput()` (`VLKing.cpp:2519, 2538`): remove the `GetController() &&` condition inside the `if (!PC)` branch (`if (AutoSteer(DeltaSeconds, Wish))` and `else if (TickYield(DeltaSeconds, Wish))`).
  4. Audit all `GetController()` calls in `Source/SovereignRealms/` (all remaining uses check `Cast<APlayerController>(GetController())` to detect hero possession — those remain `nullptr` and work identically when unpossessed).
- **Expected gain:** **0.8–1.5 ms/frame GT** (`Ticks/Total` drops from `~1,015` to `~667`; `TotalActorCount` drops by `348`), plus faster troop spawning and lighter GC.
- **Risk:** Low. Verify `AVLKing::TakeControlOf` (when the player possesses and later releases a troop back to AI) simply calls `UnPossess()` without needing to spawn an `AAIController`, and `Pawn::IsLocallyControlled()` / `HasValidData()` paths in `CharacterMovementComponent.cpp` work cleanly (already verified at `L1751`, `L5662`, `L5686`, `L5901`, `L6637`).
- **Platforms:** Both (Windows + Mac)
- **Verify by:** Confirm `ActorCount/AIController == 0` and `Ticks/AIController == 0` in CSV; test troop marching, combat, and taking/releasing control (`Enter`/`Tab`) in hero mode.
- **Confidence:** High

---

### GN-04 — Eliminate the `28–62 ms` Periodic & `175–218 ms` Attack-Launch `Tickables` Hitches (`FVLCommander` + `UVLGrid::Flood`)
- **Area:** Startup & hitches / Game thread
- **Where:**
  - `Source/SovereignRealms/VLEnemyAI.cpp`: `FVLCommander::Think` (`L688–L695`), `ChooseStrategy` (`L1090–L1111`), `RouteDefence` (`L498–L505`)
  - `Source/SovereignRealms/VLAISquads.cpp`: `PlanAttack` (`L642–L698`), `LaunchAttack` (`L700–L838`), `LaunchRaid` (`L1186–L1276`)
  - `Source/SovereignRealms/VLGrid.cpp`: `UVLGrid::Flood` (`L981–L1048`), `FindGroupPaths` (`L1089–L1208`)
- **Evidence:**
  - **100% of `>50 ms` hitches across all 6 captures** occur in `Exclusive/GameThread/Tickables`:
    - `1080p/overview`: **13 spikes of `28.1–31.0 ms` every `2.44–2.46 s`** (`p99 FT = 49.7 ms`).
    - `1440p/overview`: **17 spikes of `24–61.6 ms` at `2.45 s` / `0.62 s` intervals** (`p99 FT = 62.2 ms`).
    - `1080p/mountain`: **`175.6 ms` `Tickables` spike** (frame 734, `FT = 196.0 ms`) + `45.0 ms` (frame 723) + `28–31 ms` every `2.45 s`.
    - `1440p/mountain`: **`218.1 ms` `Tickables` spike** (frame 699, `FT = 239.8 ms`) + `61.7 ms` / `56.3 ms` + `39–41 ms` every `2.44 s`.
  - Exact mechanism:
    1. On Hard (`Difficulty=2`), `Prof.Think = 0.6 s` and `Prof.StrategyEvery = 2.0 s` (`VLEnemyAI.cpp:63–66`), so `ChooseStrategy()` fires every `4 × 0.6 = 2.4 s` (`2.44–2.46 s` measured!).
    2. `ChooseStrategy` calls `PlanAttack` (`VLEnemyAI.cpp:1095`), which loops up to 3× calling `RouteDefence` (`VLAISquads.cpp:685`) -> `VLAI::RouteLength` -> `UVLGrid::FindPath` -> `UVLGrid::Flood` across the **`1,096,134`-node 50 cm grid**. Each cross-map A* expands tens of thousands of 50 cm cells (`~15–30 ms`!).
    3. When `ChooseStrategy` selects `Attack`, **3 lines later on the same tick** (`VLEnemyAI.cpp:695`), `RunSquads` -> `RunField` -> `LaunchAttack` (`VLAISquads.cpp:708`) calls `PlanAttack` **a second time**, then calls `RouteLength` (`L787`) + `2 × RouteLength` per flank bridge (`L796`), then `MarchTo` -> `FindGroupPaths` (`L828, L867`) — running **6–10 synchronous cross-map 50 cm A\* searches in one frame** = the **`175–218 ms` freeze**!
    4. Inside `UVLGrid::Flood` (`VLGrid.cpp:981–1048`), the inner loop calls `Remaining.Remove(I)` (`TSet` hash lookup on every popped node, `L1023`), calls `CellOf(I)` (`/` and `%` divisions) on every push and pop (`L998`), and uses an uncached `w=1.0` A* over 50 cm cells.
- **Change:**
  1. **Eliminate duplicate `PlanAttack` & cache strategic routes:**
     - Cache the `PlanAttack` result on `FVLCommander` for the current `Think()` tick so `LaunchAttack` reuses it instead of recomputing it.
     - Cache `VLAI::RouteLength(B, From, To, &Route)` keyed by quantized 5 m `(FromCell, ToCell, GridRevision)` with a 10 s TTL (buildings and bridges don't move; only the cheap `Influence.RouteRisk` sample over the cached polyline needs to re-run!).
     - Stagger `StrategyClock` between Team 0 and Team 1 in `FVLCommander::Reset` (`StrategyClock = 1.f + Team * Prof.StrategyEvery * 0.5f`).
  2. **Add a coarse 2 m (or 4 m) navigation layer (or coarse A* mode) for strategic queries & optimize `UVLGrid::Flood`:**
     - Strategic queries (`RouteDefence`, `LaunchAttack`/`LaunchRaid` flank length comparisons) only feed `Influence.RouteRisk` (which has **10 m cells**!). Running them on a `4×4` (2 m, `16×` fewer nodes) coarse graph built alongside `UVLGrid::Build` cuts each query from `~15–30 ms` to **`< 0.4 ms`**!
     - Optimize `UVLGrid::Flood` itself for tactical `FindGroupPaths`: replace `TSet<int32> Remaining` with a stamp/flag check (`GoalMark[I] == Stamp` + `int32 RemainingCount`, zero hash lookups per pop), store `uint16 CellX, CellY` in `FNode` (eliminates `/` and `%` inside `H(I)`), and use a slightly weighted heuristic (`1.15f * H(J)`) or cap/amortize group pathing.
- **Expected gain:** **Eliminates the `175–240 ms` mountain hitches and ALL `28–62 ms` periodic hitches**; drops `p99 FrameTime` from `49.7–62.2 ms` to **`< 26 ms`** (before other GT fixes) and **`< 16 ms`** after `GN-01`/`GN-02`! Also trims mean GT by `~0.4–0.8 ms`.
- **Risk:** Low. Strategic route caching + coarse 2 m pathing for influence-risk checks preserves AI decision quality; `GoalMark` + `CellX/CellY` produces bit-identical paths (with `w = 1.0`).
- **Platforms:** Both (Windows + Mac)
- **Verify by:** Inspect `Exclusive/GameThread/Tickables` max and `p99 FrameTime` in all 6 CSV captures; confirm max `Tickables` drops from `175–218 ms` to `< 5 ms`.
- **Confidence:** High

---

### GN-05 — Switch Windows Occlusion Culling to HZB (`r.HZBOcclusion=1`) & Disable Occluder Flag on Unit Sub-Parts
- **Area:** GPU / Render thread
- **Where:**
  - `Config/Windows/WindowsDeviceProfiles.ini` (`[Windows DeviceProfile]`)
  - `Source/SovereignRealms/VLKing.cpp` (`AVLKing::BuildFigure`, per-part `UStaticMeshComponent` creation)
  - Engine reference verified: `UE_5.8/Engine/Source/Runtime/Renderer/Private/SceneVisibility.cpp:123` (`GHZBOcclusion = 0`), `SceneOcclusion.cpp:1451–1554`
- **Evidence:**
  - In UE 5.8, `r.HZBOcclusion` defaults to **`0` (Hardware Occlusion Queries)**.
  - In `overview`, `DrawCall/BeginOcclusionTests` is **`12,505–12,662` draw calls/frame** (**62% of all `20,470` RHI draw calls!**) and **`5,700–5,741` draw calls/frame** in `mountain`.
  - In `Saved/Perf/1440p/profilegpu.txt`, **`HZB / BeginOcclusionTests` is the #1 GPU pass at `4.88 ms` (`41%` of total `11.98 ms` GPU)** (`3.69 ms` / `43%` at 1080p!).
  - In a top-down RTS looking down at ~14,000 dynamic primitives (348 multi-part units + 1,750 dynamic prop actors), issuing 12,505 individual hardware occlusion query bounding-box draw calls every frame wastes massive RenderThread (`InitViews_Scene`, `RenderOther`, `RDG_Execute`), RHIThread, and GPU time while culling almost nothing.
- **Change:**
  1. Add `+CVars=r.HZBOcclusion=1` in `Config/Windows/WindowsDeviceProfiles.ini` (`[Windows DeviceProfile]`). (Also test `r.HZBOcclusion=2` if platform prefers HW queries; verify `DrawCall/BeginOcclusionTests` drops to ~0 and check whether `r.AllowOcclusionQueries=0` is even faster in overview while keeping `r.HZBOcclusion=1` for hero mode.)
  2. In `AVLKing::BuildFigure()` (`VLKing.cpp`), set `PartMesh->bUseAsOccluder = false;` on all character sub-part `UStaticMeshComponent`s (small 30 cm arms/heads/cape strips never meaningfully occlude other actors).
- **Expected gain:** **-10,000 to -12,500 draw calls/frame** (`20,470` -> `~8,000` in overview); **2.5–3.8 ms GPU** at 1440p (`4.88 ms` -> `~1.0–1.5 ms`); **2.0–3.5 ms RenderThread** + **1.0–2.0 ms RHIThread**.
- **Risk:** Low. HZB occlusion is slightly more conservative than HW queries (may draw a few extra primitives behind cliffs/buildings in hero view — verify BasePass/PrePass draw calls in `base` and hero view). Zero visual change.
- **Platforms:** Windows only first (test on Mac before enabling in `DefaultEngine.ini`, as Metal TBDR occlusion behavior differs).
- **Verify by:** `profilegpu` + CSV capture in `base`, `mountain`, `overview`, and hero mode: verify `DrawCall/BeginOcclusionTests` collapses near 0, GPU `HZB` drops from `4.88 ms` to `~1.0–1.5 ms`, and `Basepass` draw calls do not regress noticeably.
- **Confidence:** High

---

### GN-06 — Fix `DrawCall/CustomDepth` Explosion in `mountain` View (`4,505–5,323` mean / `11,030` max Draw Calls)
- **Area:** Render thread / GPU
- **Where:**
  - `Source/SovereignRealms/VLKingRig.cpp`: `CVarUnitDepthFar` (`L38`), `AVLKing::RigLate()` (`L564–L584`)
  - `Source/SovereignRealms/VLKing.cpp`: `VLTeamLook()` (`L229–L240`), `AVLKing::UpdateCustomDepth()`
  - Material reference verified: `Tools/ue/build_special_materials.py:355–388` (`M_Silhouette`)
- **Evidence:**
  - `mountain` view has **40–58% higher RenderThreadTime (`14.34–16.12 ms`) than `overview` (`10.21–10.24 ms`)** despite drawing `3×` fewer triangles (`9.4M` vs `30.2M`).
  - CSV shows `DrawCall/CustomDepth` = **`4,505` mean / `9,712` max (1080p)** and **`5,323` mean / `11,030` max (1440p)** in `mountain` (vs `0` in `overview`).
  - `CVarUnitDepthFar` is **`40000.f` (400 m)**, so every troop, enemy, ambient farmer (`36` `AVLFarmer`s), and tower guard within 400 m renders all **~20–30 separate `UStaticMeshComponent` parts** into the CustomDepth pass!
  - `M_Silhouette` (`build_special_materials.py:362`) only draws a 2×2 dithered gold silhouette for `Stencil == 1` (player units) behind trees/buildings; `Stencil == 2` only prevents a player unit directly behind an enemy/other unit from showing through that unit.
- **Change:**
  1. **Exclude non-occluding/non-silhouette actors:** Never enable `CustomDepth` on `bAmbient` (`AVLFarmer`) or `bTowerGuard` (10.5 m up on towers).
  2. **Write CustomDepth only on core body parts (torso, head, legs — ~5–6 parts instead of ~25–30):** Skip `CustomDepth` on bow strings (`StringU`/`StringL`), held arrows, quiver arrows, small accessories, and individual cape strips (`VLKing.cpp:229`, flag core parts in `BuildFigure`). Because `M_Silhouette` is a coarse 2×2-pixel dithered outline through trees, the core silhouette is visually indistinguishable while cutting `CustomDepth` draw calls by **~75%** at ALL distances!
  3. **Tighten `CVarUnitDepthFar` from `40000.f` (400 m) to `18000.f` (180 m):** Normal overview zoom is ~91 m (completely unaffected); beyond 180 m, `AVLHUD::DrawFarPips` already represents units with screen-space pips and a 1.7 m unit is `< 12 px` tall.
  4. **Gate enemy `Stencil == 2` CustomDepth:** For enemy units (`Team != 0`), enable `CustomDepth` only when in Hero mode or within `800 cm` of a player unit (queried cheaply via `UVLBattle::UnitsNear` at 2–4 Hz) — an enemy 200 m from all player units can never occlude a player silhouette!
- **Expected gain:** Cuts `DrawCall/CustomDepth` in `mountain` from **`5,323` (11,030 max) to `< 300`** (`> 94%` reduction!); saves **3.5–5.5 ms RenderThread** (`16.1 ms` -> `~10.5–12.5 ms`) and **0.4–0.8 ms GPU**.
- **Risk:** Very low. Verify player silhouettes behind forest canopies and castle walls at close/normal overview zoom (`<= 150 m`) and hero view look identical.
- **Platforms:** Both (Windows + Mac)
- **Verify by:** CSV capture in `mountain` view (`DrawCall/CustomDepth` and `RenderThreadTime`) + visual screenshot check of player troops behind trees and behind enemy troops at normal zoom.
- **Confidence:** High

---

### GN-07 — Instance Building Props (`SM_Wheat`, `SM_Sheep`) in `UVLConstruction::SpawnProps` (~1,750 Fewer `StaticMeshActor`s)
- **Area:** Render thread / GPU / Memory & assets
- **Where:**
  - `Source/SovereignRealms/VLConstruction.cpp`: `UVLConstruction::SpawnProps()` (`L1300–L1350`), `Rotate()` (`L1873–L1888`), `TickSites()` (`L2217–L2227`)
  - `Source/SovereignRealms/VLBuildingProps.inl`: `GBuildingProps[]` (`L3`: `SM_Farmstead*` = **86 props/farm**: `84 × SM_Wheat` + `2 × SM_Sheep`)
- **Evidence:**
  - All 6 CSVs report **`ActorCount/StaticMeshActor = 2,192`**, yet `SourceArt/realmv2.json` only places **`335`** non-forest `StaticMeshActor`s (+ ~100 terrain tiles = ~435).
  - The other **~1,750 `AStaticMeshActor`s** are spawned at runtime by `UVLConstruction::SpawnProps()` — **84 individual `Movable` `AStaticMeshActor`s for `SM_Wheat` per farm** × ~20 farms!
  - Each individual wheat actor creates a separate `Movable` scene proxy, separate `GPUScene` dynamic instance (`13,973` dynamic instances), separate `Basepass` (`2,613`) & `Prepass` (`2,399`) draw call, separate hardware occlusion query, and separate `UObject` for GC — whereas `AVLForest` already instances all `14,760` forest grass/flower tufts cleanly!
- **Change:**
  - In `UVLConstruction::SpawnProps()` (`VLConstruction.cpp:1300–1350`), keep `SM_TrainingDummy` as individual `Movable` actors (swords knock them about), and batch all identical static props per building (all 84 `SM_Wheat` tufts and 2 `SM_Sheep`) into **one `UInstancedStaticMeshComponent` per prop mesh** attached to the building actor (or a single per-building prop container actor), with:
    - `SetMobility(EComponentMobility::Static)` (or `Stationary`; recreated cleanly on `Rotate()` and destroyed on collapse just as `Props` is today)
    - `SM_Wheat`: `SetCollisionEnabled(ECollisionEnabled::NoCollision)`, `SetCastShadow(false)`, `WorldPositionOffsetDisableDistance = 6000`.
    - Also fix `VLConstruction.cpp:1384`: only call `Grid->RebuildArea(...)` after `SpawnProps` if at least one spawned prop actually has blocking collision (not for farms with `NoCollision` wheat!).
- **Expected gain:** **-1,600 to -1,750 `AStaticMeshActor`s**, **-1,600+ `Basepass` and `Prepass` draw calls** in `overview` (`2,613` -> `~1,000`), **1.5–2.5 ms RenderThread**, faster farm completion/TestWorld startup, and lower GC cost — **100% identical visuals**.
- **Risk:** Very low. `M_VoxSway` (`MI_Sway_wheat`) already supports `InstancedStaticMeshes` (used by `AVLForest` for `SM_GrassTuft`/`SM_Flowers` — double-check `SM_Wheat`'s material usage flag on `M_VoxSway` via `build_special_materials.py` just in case, and add `MATUSAGE_INSTANCED_STATIC_MESHES` if missing).
- **Platforms:** Both (Windows + Mac)
- **Verify by:** Confirm `ActorCount/StaticMeshActor` drops from `~2,192` to `~450–500`, `DrawCall/Basepass` drops by `~1,500+` in `overview`, and farm wheat fields render and sway identically.
- **Confidence:** High

---

### GN-08 — Stop `AVLAmbience` and `AVLSky` from Rebuilding ISM Scene Proxies Every Frame (`574–1,099` Instances Churned/Frame)
- **Area:** Render thread / Game thread
- **Where:**
  - `Source/SovereignRealms/VLAmbience.cpp`: `L115`, `L174`, `L215`
  - `Source/SovereignRealms/VLSky.cpp`: `L20`, `L116`, `L132`, `L177`
  - Engine reference verified: `UE_5.8/Engine/Source/Runtime/Engine/Private/InstancedStaticMesh.cpp:2544–2565, 4317–4368` and `ISMInstanceDataManager.cpp:274–278`
- **Evidence:**
  - Every single frame across all captures, CSVs record **`SceneCulling/NumAddedInstances = 574` and `NumRemovedInstances = 574`** in `base`, and **`1,099` added + `1,099` removed** in `mountain`/`overview`!
  - Both `AVLAmbience` (`Motes`, `Smoke`) and `AVLSky` (`Clouds`, `Birds`) call `UpdateInstanceTransform(i, Xf, false, /*bMarkRenderStateDirty=*/ bLast, false)` every tick.
  - Verified in UE 5.8 engine source: `UpdateInstanceTransform` **always** calls `PrimitiveInstanceDataManager.TransformChanged(InstanceIndex)` -> `MarkComponentRenderInstancesDirty()`, which automatically pushes a fast in-place delta update on the RT via `SendRenderInstanceData_Concurrent()` -> `UpdatePrimitiveInstances(this)`. Passing `bMarkRenderStateDirty = true` calls `MarkRenderStateDirty()`, which **destroys and recreates the entire `FInstancedStaticMeshSceneProxy` every frame**!
  - Furthermore, `VLSky.cpp:116` exempts `!bLast` from early-out, forcing a full proxy teardown even when all clouds are hidden (`S <= 0.002f`), and both files park hidden instances at `Z = -100000.f` (1 km underground, bloating bounding boxes).
- **Change:**
  1. Pass `bMarkRenderStateDirty = false` (or use `BatchUpdateInstancesTransforms(0, Transforms, false, /*bMarkRenderStateDirty=*/ false, true)`) in `VLAmbience.cpp:174, 215` and `VLSky.cpp:132, 177`.
  2. Park hidden instances at the actor/source origin with `FVector::ZeroVector` scale instead of `Z = -100000.f` (same fix already applied to `VLFootDust`).
  3. Remove `&& !bLast` in `VLSky.cpp:116` so hidden/unchanged clouds perform zero ISM updates.
- **Expected gain:** `SceneCulling/NumAddedInstances` & `NumRemovedInstances` drop from **`574–1,099/frame` to `0`**; saves **0.4–1.0 ms RenderThread** (`UpdateGPUScene`, `Add/RemovePrimitiveSceneInfos`, `PostSceneUpdate`) and **0.1–0.3 ms GT**.
- **Risk:** Very low. Verified directly in UE 5.8 `InstancedStaticMesh.cpp:2555–2565` that `bMarkRenderStateDirty=false` still updates GPU Scene transforms and bounds cleanly every frame.
- **Platforms:** Both (Windows + Mac)
- **Verify by:** Confirm `SceneCulling/NumAddedInstances == 0` and `NumRemovedInstances == 0` in steady-state CSVs, and verify chimney smoke, lantern motes, clouds, and bird flocks animate identically.
- **Confidence:** High

---

### GN-09 — Optimize `AVLKing::RigLateUpdate` (`WorldTickMisc = 2.18–2.80 ms`, Max `6.29 ms`) for Distant & Stationary Units
- **Area:** Game thread / Render thread
- **Where:** `Source/SovereignRealms/VLKingRig.cpp`: `AVLKing::RigLate()` (`L555–L649`), `AVLKing::RigFlush()`
- **Evidence:**
  - `Exclusive/GameThread/WorldTickMisc` is **`0.16 ms`** in `base` (units outside frustum) and jumps **15× to `2.18–2.80 ms` (max `6.29 ms`)** in `mountain` and `overview` where all ~348 units pass frustum culling.
  - At overview altitude (`500–680 m`, where units are 4–8 px tall), `VLKingRig.cpp:624` clamps the pose stride `Every` to at most **`4` frames** (`15–20 Hz`), so ~90 units still run full `PoseNow` + `RigFlush` (transforming ~25 scene components each = ~2,250 component transform updates/frame!).
  - Stationary/idle troops far from the camera still run `PoseNow` + `RigFlush` for sub-pixel breathing animation.
- **Change:**
  1. **Skip `PoseNow`/`RigFlush` for stationary distant units:** When `!bDead && !bRigStale && !bRigForce && GetVelocity().SizeSquared() < 4.f && !IsFighting() && CmPerPx > 3.5` (unit is `> ~100 m` away, where 1–2 cm breathing sway is `< 0.5 px`), skip `PoseNow` and `RigFlush` completely (only flush when it starts moving, turns, attacks, or gets closer).
  2. **Relax `Every` upper clamp at overview distances:** In `VLKingRig.cpp:624`, raise the clamp from `4` to `10` when `CmPerPx > 12.0` (the existing `StepPx` guard at `L625–L629` already guarantees a moving unit never steps more than `0.75 px` between updates!).
  3. **Skip `RigLocal` / `SetComponentToWorld` on unchanged rigid child components** when `bHoldCape` is active (already frozen cape panels need zero matrix recalculation while held).
- **Expected gain:** **1.2–1.8 ms/frame GT** in `mountain` and `overview`, plus **0.4–0.8 ms RT** from fewer `UpdatePrimitiveTransform` / `UpdateGPUScene` updates.
- **Risk:** Low. Sub-pixel idle breathing is imperceptible at `> 100 m`; the `0.75 px` motion guard prevents any stutter on marching units.
- **Platforms:** Both (Windows + Mac)
- **Verify by:** Check `Exclusive/GameThread/WorldTickMisc` in `mountain`/`overview` CSVs (target `< 1.0 ms`) and visually verify smooth troop marching at all zoom levels.
- **Confidence:** High

---

### GN-10 — Replace Scanline-Loop Diamond Pips in `AVLHUD::DrawFarPips` & Remove Per-Frame Minimap Trace / Builder Actor Scan
- **Area:** Game thread
- **Where:**
  - `Source/SovereignRealms/VLHUD.cpp`: `AVLHUD::DrawFarPips()` (`L1521–L1535`)
  - `Source/SovereignRealms/VLHUDGame.cpp`: `AVLHUD::DrawMinimap()` (`L876`)
  - `Source/SovereignRealms/VLConstruction.cpp`: `UVLConstruction::TickSites()` (`L2187–L2194`)
- **Evidence:**
  - `Exclusive/GameThread/UI` is **`1.15–2.26 ms` mean (max `4.59 ms`)**.
  - `AVLHUD::DrawFarPips()` (`VLHUD.cpp:1521–1535`) draws every diamond pip with two nested `for (float dy = -H; dy <= H; dy += 1.f)` loops emitting **~22–28 1-px-tall `RectLinear` quads per unit** (`~5,500–7,000` quads / `11,000–14,000` triangles/frame in overview!). `Docs/Optimization/PLAN.md` item B4 called for single-quad/triangle pips, which was not implemented.
  - `AVLHUD::DrawMinimap()` (`VLHUDGame.cpp:876`) executes a 1 km `LineTraceSingleByChannel` every single frame to estimate the ground plane `Z` under screen center.
  - `UVLConstruction::TickSites()` (`VLConstruction.cpp:2187`) runs a full `TActorIterator<AVLKing>` (~348 actors) every single frame just to count Builders at work (typically 0–6).
- **Change:**
  1. **Diamond pips as 4 triangles (2 quads) per unit:** Replace the `dy` scanline loop in `VLHUD.cpp:1521–1535` with 2 rotated diamond quads (rim + fill = 4 `FCanvasUVTri` triangles per unit) pushed into a single `FCanvasTriangleItem` (11× fewer primitives, sharper diagonal edges).
  2. **Cache minimap `PlaneZ`:** In `VLHUDGame.cpp:876`, only re-trace when camera transform changed by `> 10 cm` / `0.5°` (or sample `UVLGrid::NodeAt` at camera focus).
  3. **Avoid `TActorIterator<AVLKing>` in `TickSites`:** Iterate `UVLBattle::AllUnits()` (or maintain a tiny cached `Builders` array updated on spawn/death) and skip the loop entirely when no building is a site or below full health.
- **Expected gain:** **0.6–1.2 ms/frame GT** (`UI` drops from `1.8–2.3 ms` to `~0.8–1.2 ms`), plus lower `SlateUI` RHI overhead.
- **Risk:** Very low. Visually cleaner diamonds and identical minimap frustum.
- **Platforms:** Both (Windows + Mac)
- **Verify by:** Check `Exclusive/GameThread/UI` and `DrawCall/SlateUI` in `overview` CSV; visually inspect far pips and minimap viewport quad.
- **Confidence:** High

---

### GN-11 — Disable `r.Nanite=0` & Test `r.VelocityOutputPass=1` / `r.EarlyZPass` on Windows DX12/SM6 (Zero Nanite Meshes Exist)
- **Area:** GPU / Render thread / Build, cook & package
- **Where:**
  - `Config/Windows/WindowsEngine.ini` (`[/Script/Engine.RendererSettings]`)
  - `Config/Windows/WindowsDeviceProfiles.ini` (`[Windows DeviceProfile]`)
- **Evidence:**
  - `Tools/ue/voxel_lods.py:55` sets `build_nanite = False` — **the project has zero Nanite meshes**.
  - Yet `r.Nanite` remains enabled (`1`) on Windows, causing `Saved/Perf/1440p/profilegpu.txt` to show:
    - **`PrePass DDM_AllOpaqueNoVelocity (Forced by Nanite)`: `1.66 ms` GPU** (`1.15 ms` at 1080p) and **`2,399–2,415` draw calls/frame**!
    - **`RenderVelocities`: `1.03 ms` GPU** (`0.68 ms` at 1080p) and **`215` draw calls/frame**!
    - Compare against **`BasePass`: only `0.86 ms` GPU** at 1440p! The voxel pixel shader is so light that paying **`2.69 ms` GPU + `2,630` RT draw calls** for a forced full PrePass + separate Velocity pass is dramatically more expensive than `BasePass` itself!
  - `Saved/Cooked/Windows/SovereignRealms/Metadata/ShaderTypeStats-PCD3D_SM6.csv` also shows `30` Nanite shaders, `28` RayTracing shaders, `487` Lumen shaders (`4.84 MB`), and `205` VSM shaders (`4.53 MB`) cooked unnecessarily on Windows.
- **Change:**
  1. In `Config/Windows/WindowsEngine.ini` (`[/Script/Engine.RendererSettings]`):
     ```ini
     r.Nanite.ProjectEnabled=False
     r.VelocityOutputPass=1          ; write velocity in BasePass instead of a separate RenderVelocities pass (A/B test!)
     r.EarlyZPass=1                  ; A/B test 1 (opaque-only masked/minimal) vs 0 vs 2 (opaque) without Nanite forcing full PrePass
     r.RayTracing=False
     ```
     (Verify `r.EarlyZPass=1` vs `2` vs `0` in `profilegpu`: with `BasePass` at `0.86 ms` and TSR needing depth, `r.EarlyZPass=0` or `1` + `r.VelocityOutputPass=1` should eliminate most of the `1.66 ms` PrePass + `1.03 ms` RenderVelocities while adding `< 0.3–0.5 ms` to BasePass!)
  2. Keep `r.Nanite=0` in `Config/Windows/WindowsDeviceProfiles.ini` to match.
- **Expected gain:** **1.2–2.2 ms GPU** at 1440p (`11.98 ms` -> `~9.8–10.8 ms`, before `GN-05` HZB win) and **1.0–2.0 ms RenderThread** (`-2,400` PrePass + `-215` Velocity draw calls), plus fewer cooked shaders.
- **Risk:** Medium — requires an A/B `profilegpu` + CSV check on RX 9070 GRE (and an NVIDIA GPU if available) to confirm TSR motion vectors remain crisp with `r.VelocityOutputPass=1` and that disabling full PrePass doesn't increase BasePass overdraw more than it saves in dense forests.
- **Platforms:** Windows only (Mac already sets `r.Nanite=0` in `Config/Mac/MacDeviceProfiles.ini`).
- **Verify by:** `profilegpu` + CSV in `overview`, `mountain`, and dense forest close-up; check `PrePass + RenderVelocities + BasePass` GPU sum and `RenderThreadTime`, plus visual TSR ghosting check on moving troops.
- **Confidence:** Medium-High

---

### GN-12 — Windows PSO Pipeline Cache Collection, Precache Hygiene, and Fix `M_Voxel` `InstancedStaticMeshes` Flag (`MI_Vox_smoke` & `MI_Vox_mote`)
- **Area:** Startup & hitches / Memory & assets
- **Where:**
  - `Config/Windows/WindowsEngine.ini`
  - `Tools/windows/package.ps1`
  - `Tools/ue/import_assets.py` (`build_materials()`, `L74–L112`) — **`ASSET`**
- **Evidence:**
  - `Saved/Perf/1080p/game.log:794`: `LogRHI: Could not open FPipelineCacheFile: .../Content/PipelineCaches/Windows/SovereignRealms_PCD3D_SM6.stable.upipelinecache`.
  - **34–44 PSO misses** logged (`PSO/PSOMisses = 1.05–1.18` mean / `2–3` max during `mountain`/`overview`).
  - **Important UE 5.8 finding (`WindowsD3D12PipelineState.cpp:29`):** `D3D12.PSO.DiskCache` is **deprecated/disabled by Epic** (`// D3D12RHI PSO file cache doesn't work anymore. Use FPipelineFileCacheManager instead`) — do **not** enable `D3D12.PSO.DiskCache=1`. Also `PSOPrecacheMaterial.cpp:43` notes `KeepInMemoryForActiveMaterials=1` (already set in `BaseWindowsEngine.ini:71`) is mutually exclusive with `KeepInMemoryUntilUsed=1` — do **not** set both.
  - Both **`MI_Vox_smoke`** (`1080p/game.log:2020`) **AND `MI_Vox_mote`** (`1080p/game.log:3579`, missed in `BASELINE.md`) warn `missing usage flag InstancedStaticMeshes! Default Material will be used` because `build_level.py:306–307` parents both to `M_Voxel`, and `import_assets.py:74–112` never sets `MATUSAGE_INSTANCED_STATIC_MESHES` on `M_Voxel`!
- **Change:**
  1. In `Config/Windows/WindowsEngine.ini` (`[SystemSettings]`):
     ```ini
     r.PSOPrecaching=1
     r.PSOPrecache.GlobalShaders=1
     r.PSOPrecache.ProxyCreationStrategy=1
     r.PSOPrecache.DrawnComponentBoostStrategy=1
     r.ShaderPipelineCache.Enabled=1
     r.ShaderPipelineCache.StartupMode=3
     r.ShaderPipelineCache.BatchTime=16.0
     r.ShaderPipelineCache.BackgroundBatchTime=2.0
     ```
  2. Add a repeatable Windows PSO capture & expand step to `Tools/windows/package.ps1` (run Development build with `-logPSO` across title/base/mountain/overview/combat/hero, then `UnrealEditor-Cmd.exe SovereignRealms.uproject -run=ShaderPipelineCacheTools expand` into `Content/PipelineCaches/Windows/SovereignRealms_PCD3D_SM6.stable.upipelinecache`).
  3. (**`ASSET`**) In `Tools/ue/import_assets.py` (`build_materials()`, before `L110`): add `mel.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)` on `M_Voxel`, re-run `Tools/ue_py.py -c "PARTS=['materials']; exec(open('Tools/ue/import_assets.py').read())"` to resave `M_Voxel.uasset` (and also verify `M_VoxSway` has `MATUSAGE_INSTANCED_STATIC_MESHES` for `GN-07`).
- **Expected gain:** Eliminates `PSO/PSOMisses` (`2–3` -> `0`) and first-appearance DX12 shader hitches; fixes chimney smoke & lantern motes falling back to WorldGridMaterial.
- **Risk:** Low. `M_Voxel` compiles one additional ISM vertex-factory shader permutation (already needed for trees/smoke/motes).
- **Platforms:** Config/pipeline: Windows only (Mac already has its pipeline); `ASSET` (`M_Voxel` ISM flag): Both (Windows + Mac).
- **Verify by:** Confirm `FPipelineCacheFile` opens cleanly in `game.log`, `PSO/PSOMisses == 0` in all 3 views, and zero `missing usage flag InstancedStaticMeshes` warnings.
- **Confidence:** High

---

### GN-13 — Batch `UVLGrid::RebuildArea` in `SetupTestWorld` & Localize Region Updates on Building Placement/Completion
- **Area:** Startup & hitches
- **Where:**
  - `Source/SovereignRealms/VLGrid.cpp`: `UVLGrid::RebuildAreas()` (`L612–L803`), `LabelRegions()` (`L463–L605`)
  - `Source/SovereignRealms/VLBattle.cpp`: `SetupTestWorld()`
  - `Source/SovereignRealms/VLConstruction.cpp`: `PlaceBuilding()`, `Finish()` (`L1384–L1394`)
- **Evidence:**
  - `Saved/Perf/1080p/game.log:988–1418` logs **`68` consecutive `GRID area` calls at `22.0–32.5 ms` each (`~1.8 seconds` frozen!)** on frame 1 of `TestWorld=1`.
  - `1080p/game.log:2122, 2134, 2167` logs **3 mid-match `25.0–28.1 ms` `GRID area` hitches** during gameplay whenever a building is placed or finished.
  - Inside `UVLGrid::RebuildAreas()`, **~80% of the 25–28 ms** is spent running full-map `LabelRegions()` over all **`1,096,134` nodes** (`L780`) plus scanning all ~2,800 world actors (`L654`), even though only ~2,700 cells (`0.25%` of the map) were resampled!
- **Change:**
  1. Add `BeginBatchRebuild()` / `EndBatchRebuild()` on `UVLGrid` that accumulates dirty `FBox2D` rects and executes a single `RebuildAreas(PendingRects)` on `EndBatchRebuild()`; wrap `SetupTestWorld()` and `ClearStartTrainers()` in it.
  2. Cache the `Ground` component set on `UVLGrid` during `Build()` instead of iterating `TActorIterator<AActor>` on every `RebuildAreas()`.
  3. **Fast local region relabel:** Before running global `LabelRegions()`, check the 1-cell border ring around the rebuilt box. If all live border nodes already belong to `Main` and a local BFS over the newly-sampled nodes connects them to `Main` without splitting the border ring into disconnected components, assign `Region = Main` locally in **`< 0.5 ms`** and skip the `20 ms` full-map `LabelRegions()` pass! Fall back to global `LabelRegions()` only when border connectivity actually changes.
- **Expected gain:** Cuts `TestWorld` startup by **`~1.7 seconds`** and eliminates **`25–30 ms` mid-match hitches** on every building placement/completion/destruction.
- **Risk:** Low (border-ring connectivity check is exact when conservative: any border node that lost a neighbor or belongs to a non-`Main` region falls back to full `LabelRegions()`).
- **Platforms:** Both (Windows + Mac)
- **Verify by:** Check `GRID area` timing in `game.log` (drops from `25–32 ms` to `< 3 ms`) and run `vl.Opt.GridChecksum 1` before/after to verify identical grid checksums.
- **Confidence:** High

---

### GN-14 — Eliminate Mid-Match `FlushAsyncLoading` Stalls & 40–76 Startup `SkipPackage` Sound Probes
- **Area:** Startup & hitches
- **Where:**
  - `Source/SovereignRealms/VLBattle.cpp:3391` (`UVLBattle::Sounds`), `VLArrow.cpp:42`, `VLSwordsmanCombat.cpp:45`, `VLKing.cpp:4200`, `VLConstruction.cpp:187`
- **Evidence:**
  - `1080p/game.log` has **40 `SkipPackage` warnings**; `1440p/game.log` has **76 `SkipPackage` warnings** (`/Game/Voxel/Audio/S_<name>_<n>`).
  - Both logs show synchronous **`FlushAsyncLoading` calls mid-capture** (`1080p/game.log:4101`, `1440p/game.log:3920, 4215, 4248`) when sound sets or materials (`MI_Vox_cloth_Enemy`, building meshes) are lazily loaded via `LoadObject<>` on first combat/payout/collapse event.
- **Change:**
  1. In every sound variant loader (`VLBattle.cpp`, `VLSwordsmanCombat.cpp`, `VLArrow.cpp`, `VLKing.cpp`), check `FPackageName::DoesPackageExist(Pkg)` before `LoadObject<USoundBase>` and `break` on the first missing variant index.
  2. Preload all match sound sets (`S_Death`, `S_BuildingHit`, `S_BuildingCollapse`, `S_CoinPayout`, `S_GrainPayout`, `S_AttackAlert`, `S_BuildPlace`, sword/arrow/footstep sets), `MI_Vox_cloth_Enemy`, and the 7 buildable static meshes once during `UVLBattle::StartMatch()` / `BeginPlay()` (or via a `UPrimaryDataAsset` referenced by the level/GameMode).
- **Expected gain:** Eliminates all mid-match `FlushAsyncLoading` stalls (`5–25 ms` each) and removes 40–76 startup `SkipPackage` stalls/warnings.
- **Risk:** Very low (slight increase in steady-state RAM for audio/meshes that are already loaded during any normal match).
- **Platforms:** Both (Windows + Mac)
- **Verify by:** Confirm zero `SkipPackage` warnings and zero `FlushAsyncLoading` log lines after match start in `game.log`.
- **Confidence:** High

---

### GN-15 — Trim Distant Unit Shadow Casters & Sub-Pixel Parts (Plus Phase-2 LOD2 Single-Mesh / ISM Proxy for Units)
- **Area:** Render thread / GPU
- **Where:**
  - `Source/SovereignRealms/VLKing.cpp` (`BuildFigure`), `Source/SovereignRealms/VLKingRig.cpp` (`RigLate`)
  - `Tools/ue/build_realmv2.py:138` (`dynamic_shadow_distance_movable_light = 110000.0`)
- **Evidence:**
  - Even after `GN-05`, `GN-06`, and `GN-07`, `348` units × `~20–30` individual `UStaticMeshComponent`s = **`~8,000–9,500` dynamic primitives** still feed `ShadowDepths` (`1,844` draw calls, `1.70 ms` GPU at 1440p), `Basepass`, and `Prepass`, and `RHI/PrimitivesDrawn` reaches **`30.2M` tris/frame** in overview.
  - Because `dynamic_shadow_distance_movable_light = 110,000 cm` (1.1 km) on `L_RealmV2`, every tiny unit arm, cape strip, and bow string casts directional shadows even from `680 m` altitude where each unit is `~4 px` tall.
- **Change:**
  1. **Phase 1 (C++ only, zero asset changes):**
     - In `AVLKing::BuildFigure()`, set `bCastShadow = false` on tiny non-silhouette sub-parts (bow strings `StringU`/`StringL`, held arrows, quiver arrows, minor trim/accessories — keep shadows on torso/head/legs/arms/weapon/shield/cape).
     - In `AVLKing::RigLate()`, when `Dist > 26000 cm` (260 m, where a unit's shadow is `< 2 px` wide and `bHoldCape` is active), hide micro-parts (strings/arrows) and optionally disable `CastShadow` on distant units' limb/cape parts (keeping torso shadow or none past `350 m` where overview far pips dominate).
     - Ensure `PartMesh->bReceivesDecals = false;`, `PartMesh->bGenerateOverlapEvents = false;`, `PartMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);` on all figure part meshes.
  2. **Phase 2 (larger architectural win, `ASSET` + C++):**
     - At `LOD 2` (`> 158 m`, already defined in `Tools/ue/voxel_lods.py`), swap each `AVLTroop`'s 25 individual `UStaticMeshComponent`s for **1 combined low-poly static mesh** (or 1 instance in a shared per-kind/team `UInstancedStaticMeshComponent`), reducing `312 × 25 = 7,800` scene proxies in overview/mountain to **~6–10 ISM draw calls**!
- **Expected gain:** Phase 1: **0.6–1.2 ms RT + 0.5–0.9 ms GPU** (`ShadowDepths`); Phase 2: **additional 2.5–4.0 ms RT** and **-5,000+ draw calls** across all passes in `mountain`/`overview`!
- **Risk:** Phase 1: Very low (visually imperceptible at `> 260 m`). Phase 2: Medium (requires generating one merged LOD2 mesh per troop kind in `Tools/blender/assets/voxel_lods.py` and clean visibility handoff at `160 m`).
- **Platforms:** Both (Windows + Mac)
- **Verify by:** CSV `DrawCall/ShadowDepths`, `DrawCall/Basepass`, `RenderThreadTime`, and `profilegpu` `ShadowDepths` + screenshot comparison at normal zoom and overview.
- **Confidence:** High (Phase 1) / Medium (Phase 2)

---

### GN-16 — Enable Win64 Shipping LTCG (`bAllowLTCG = true`)
- **Area:** Build, cook & package / Game thread
- **Where:** `Source/SovereignRealms.Target.cs`
- **Evidence:**
  - `1080p/game.log:23` reports `ltoenabled="0"` (and `Docs/Optimization/Windows/PROPOSAL.md` §4 flags Win64 Shipping LTCG as unmeasured).
  - Because Sovereign Realms is heavily CPU-bound in tight C++ loops (`CharacterMovement`, `VLGrid`, `VLKingRig`, `AVLHUD`, `FVLCommander`), Link-Time Code Generation (whole-program inlining & devirtualization across translation units) directly accelerates both GameThread and RenderThread.
- **Change:**
  - In `Source/SovereignRealms.Target.cs`:
    ```csharp
    if (Configuration == UnrealTargetConfiguration.Shipping && Platform == UnrealTargetPlatform.Win64)
    {
        bAllowLTCG = true;
    }
    ```
  - Keep `Development` and `Editor` builds unchanged (`bAllowLTCG = false`) so iteration builds stay fast.
- **Expected gain:** **5–10% CPU speedup** in Shipping (`~0.8–1.8 ms` GT + `~0.5–1.0 ms` RT at zero runtime risk).
- **Risk:** Very low (longer Shipping link time only; no gameplay/look impact).
- **Platforms:** Windows only (Shipping).
- **Verify by:** Compare Shipping build with `bAllowLTCG = false` vs `true` on the same `L_RealmV2` 3-view capture (note: measure via `stat unit`/frame-time logging or Test config with `bAllowLTCG=true`).
- **Confidence:** High

---

### GN-17 — Strip Unused Windows Shader Permutations & Editor Plugins + Scale Presets for Mid/Low Windows PCs
- **Area:** Build, cook & package / Presets & scalability
- **Where:**
  - `Config/Windows/WindowsEngine.ini`, `Config/DefaultEngine.ini` (`L45–L57`), `SovereignRealms.uproject`
  - `Source/SovereignRealms/VLGraphics.cpp` (`PresetVars`, `ApplyConsoleVariables`)
- **Evidence:**
  - Windows Shipping package is **`1,407 MB`** vs Mac's **`1,062 MB`**.
  - `ShaderTypeStats-PCD3D_SM6.csv` cooks **`10,014` shaders (`105.43 MB`)**, including unused `FScreenProbeIntegrateCS` (`9.56 MB`), `FVirtualShadowMapProjectionCS` (`4.31 MB`), `FDistanceFieldShadowingCS` (`3.03 MB`), `FScreenSpaceShortRangeAOCS` (`2.67 MB`), `FLumen*` (`4.84 MB`), and `RayTracing` (`0.12 MB`).
  - `DefaultEngine.ini:45–57` enables `AndroidFileServerEditor`, and `SovereignRealms.uproject` enables `PythonScriptPlugin`, `ModelContextProtocol`, and `EditorToolset` without checking if any runtime binaries stage into Shipping.
  - `VLGraphics.cpp` Medium/Low presets currently do not scale `vl.Opt.UnitDepthFar`, `vl.Opt.RigFarDist`, or Windows-specific shadow distance / cascade count (`r.Shadow.CSM.MaxCascades`, `r.Shadow.DistanceScale`).
- **Change:**
  1. In `Config/Windows/WindowsEngine.ini` (`[/Script/Engine.RendererSettings]`): explicitly disable unused rendering features to stop cooking dead shader permutations (mirroring `MacEngine.ini` where safe):
     ```ini
     r.RayTracing=False
     r.Lumen.HardwareRayTracing=False
     r.GenerateMeshDistanceFields=False    ; verify no DFAO/DFShadow/Lumen depends on mesh distance fields (Lumen & DFAO are off!)
     r.AllowStaticLighting=False           ; all lights in build_level.py are Movable/Stationary with dynamic shadows, no lightmaps baked
     r.Shadow.Virtual.Enable=0
     ```
     *(Verify in a dry cook that no material/feature requires MeshDistanceFields — e.g. `M_VoxWater` does not sample DistanceToNearestSurface, verified in `build_special_materials.py:88–147`!)*
  2. Audit `SovereignRealms.uproject` plugin `TargetAllowList` (`["Editor"]` for `PythonScriptPlugin`, `ModelContextProtocol`, `EditorToolset`) and move `AndroidFileServerEditor` out of `DefaultEngine.ini` if unused on Windows/Mac.
  3. In `VLGraphics.cpp` (`PresetVars`): keep **High** visually identical; on **Medium** / **Low**, add scaling for `vl.Opt.UnitDepthFar` (`12000` / `6000`), `vl.Opt.RigFarDist` (`5000` / `3000`), `r.Shadow.DistanceScale` (`0.65` / `0.35`), and `r.Shadow.CSM.MaxCascades` (`3` / `2`) so weaker GPUs/CPUs scale smoothly.
- **Expected gain:** **20–35% smaller cooked shader library** (`~25–35 MB`), faster cook times, **~50–150 MB** smaller Shipping build, and **+30–50% fps** on Medium/Low presets for weaker Windows PCs.
- **Risk:** Low-Medium (`r.GenerateMeshDistanceFields=False` and `r.AllowStaticLighting=False` must be verified against `L_RealmV2` lighting/water/fog screenshots to ensure zero look delta on High).
- **Platforms:** Config: Windows only (align with `MacEngine.ini` where shared); `VLGraphics.cpp` presets & plugin `TargetAllowList`: Both (Windows + Mac).
- **Verify by:** Compare `ShaderTypeStats-PCD3D_SM6.csv` total shaders/MB, `Builds/Windows/` Shipping size, and side-by-side High/Medium/Low screenshots.
- **Confidence:** Medium-High

---

## Ranked Implementation Order (Grouped into Build / Measure Batches)

Implement and measure **one batch at a time** against `Docs/Optimization/Windows/BASELINE.md` using the same 1080p + 1440p 3-view capture:

### Batch 1 — Game Thread & Hitch Elimination (Biggest Immediate Win: GT `25 ms -> ~11 ms`, Max Hitch `240 ms -> < 25 ms`)
1. **`GN-01`** — Keep `ECC_Pawn=ECR_Ignore` on AI troops, set `bAlwaysCheckFloor=false`, `bEnablePhysicsInteraction=false`, `bUseFlatBaseForFloorChecks=false` (troops), disable CMC tick when garrisoned/dead. *(-5.0 to -7.5 ms GT, 0 stuck warnings)*
2. **`GN-03`** — Set `bRunPhysicsWithNoController=true` and disable `AutoPossessAI` on `AVLTroop`/`AVLFarmer`, eliminating 348 `AAIController`s and 348 actor ticks/frame. *(-0.8 to -1.5 ms GT)*
3. **`GN-04`** — Cache `PlanAttack` per tick + cache strategic `RouteLength` + coarse 2 m graph for `RouteDefence` + optimize `UVLGrid::Flood` (`GoalMark` + cached `CellX/Y`). *(Eliminates `175–240 ms` mountain freeze and all `28–62 ms` periodic hitches)*
4. **`GN-13`** — Batch `UVLGrid::RebuildArea` in `SetupTestWorld` + local border-ring region relabel in `RebuildAreas` + skip rebuild for `NoCollision` farm props. *(-1.7 s TestWorld start, eliminates `25–30 ms` building-placement hitches)*

### Batch 2 — Render Thread & GPU Draw-Call Collapse (RT `16 ms -> ~6–8 ms`, GPU `12 ms -> ~7–8 ms`)
5. **`GN-05`** — Enable `r.HZBOcclusion=1` in `WindowsDeviceProfiles.ini` + `bUseAsOccluder=false` on unit parts. *(-10,000–12,500 occlusion draw calls, -2.5 to -3.8 ms GPU, -2.0 to -3.5 ms RT)*
6. **`GN-06`** — Fix `CustomDepth` explosion: core body parts only, exclude farmers/tower guards, `vl.Opt.UnitDepthFar=18000`, gate enemy stencil=2 by proximity. *(-4,500–5,300 draw calls in `mountain`, -3.5 to -5.5 ms RT)*
7. **`GN-07`** — Instance `SM_Wheat`/`SM_Sheep` per farm in `UVLConstruction::SpawnProps`. *(-1,700 `StaticMeshActor`s, -1,600+ BasePass/PrePass draw calls, -1.5 to -2.5 ms RT)*
8. **`GN-08`** — Fix `AVLAmbience`/`AVLSky` `bMarkRenderStateDirty=false` + zero-scale hiding. *(Eliminates `574–1,099` GPUScene instance churn/frame, -0.4 to -1.0 ms RT)*

### Batch 3 — Remaining GT Polish (Target: GT `< 8–10 ms` Everywhere = 100+ fps Headroom)
9. **`GN-02` (Phase A)** — Sleep idle grounded `AVLTroop` CMCs + safe 30 Hz throttle on off-screen/distant walking troops (and cap `AVLFarmer` CMC interval at `0.05 s`). *(-2.5 to -4.0 ms GT)*
10. **`GN-09`** — Skip sub-pixel idle `RigLate`/`PoseNow` at `> 100 m` and relax overview pose stride clamp (`4 -> 10` with `0.75 px` motion guard). *(-1.2 to -1.8 ms GT, -0.4 to -0.8 ms RT)*
11. **`GN-10`** — Replace `DrawFarPips` scanline loops with 4-triangle diamonds, cache minimap `PlaneZ`, remove `TActorIterator<AVLKing>` in `TickSites`. *(-0.6 to -1.2 ms GT)*

### Batch 4 — Windows DX12 Pipeline, PSOs, Assets & Shipping Polish
12. **`GN-12`** — Windows `FPipelineFileCacheManager` (`.stable.upipelinecache`) collection + `DrawnComponentBoostStrategy=1` + **`ASSET`** fix `M_Voxel` `MATUSAGE_INSTANCED_STATIC_MESHES` (fixes both `MI_Vox_smoke` and `MI_Vox_mote`). *(0 PSO misses, fixes broken smoke/mote materials)*
13. **`GN-14`** — Preload match sound sets/materials at match start + `DoesPackageExist` early-break in variant loops. *(0 mid-match `FlushAsyncLoading` stalls, 0 `SkipPackage` warnings)*
14. **`GN-11`** — A/B test `r.Nanite.ProjectEnabled=False` + `r.VelocityOutputPass=1` + `r.EarlyZPass` in `WindowsEngine.ini`. *(-1.2 to -2.2 ms GPU, -1.0 to -2.0 ms RT)*
15. **`GN-15` (Phase 1) + `GN-16` + `GN-17`** — Trim distant unit micro-part shadows, enable Win64 Shipping `bAllowLTCG=true`, strip unused Windows shader permutations (`DistanceFields`/`StaticLighting`/`RT`), and add Medium/Low preset scaling in `VLGraphics.cpp`. *(+5–10% Shipping CPU, -0.6–1.2 ms RT/GPU, smaller cook/package, strong Medium/Low scaling)*
