# Windows PC optimization: merged plan

Sources:
- `findings_fable52_pc.md` (FP-xx, Fable 5.2)
- `findings_gemini4neon.md` (GN-xx, Gemini 4 Neon)

Both audited the same code (`bc883c7`) and the same baseline (`BASELINE.md`) independently. The orchestrator (Opus 5.5)
merged them, spot-checking the disputed claims in the code.

**Implementer: Fable 5.2.** Its audit was the more accurate one:
- It checked its engine claims in the 5.8.4 source.
- It corrected three faults in the baseline itself: the "base" view is empty, "1440p" was 2194 x 1234, and the CSV rows are
  offset by one frame.
- It traced the 196-240 ms freeze to both commanders planning Raid #5 in one frame.
- It saw that the 616 "stuck" warnings come from one jammed squad, so they are a symptom, not the cost.

Gemini contributed items Fable missed, verified in the code:
- **Farm props (GN-07):** each farm spawns 84 wheat tufts as movable `AStaticMeshActor`s.
- **ISM render-state churn (GN-08):** `UpdateInstanceTransform(..., bMarkRenderStateDirty = true)` on the last instance every
  frame in `VLAmbience` / `VLSky`.
- **HUD costs (GN-10):** the scanline far pips, the per-frame minimap trace and the `TActorIterator` in `TickSites`.
- **The M_Voxel ISM usage flag (GN-12):** missing for both smoke and motes.
- **Duplicated `PlanAttack` (GN-04):** it runs twice in the same tick.

Rules (unchanged): gameplay and the look at High are identical, the Mac keeps working, every change says its platforms,
and each batch is measured against the baseline before the next starts.

## Rejected

| Item | Why |
|---|---|
| GN-01 (1): troop capsules always ignore pawns | Changes movement outcomes: troops would stand inside one another. That is a gameplay change for the owner to decide (FP-09 agrees). |
| GN-02 Phase B: kinematic grid walking | Replaces the engine movement for most units, with high behaviour risk. Revisit only if the game thread is still the limit after batch 4. |
| GN-06 (2)-(4): fewer custom-depth parts, a 180 m depth cutoff, a proximity gate on enemies | Visible changes to the silhouettes at High. Only allowed if a screenshot diff at the three views shows no difference. |
| GN-03: no AI controllers at all | Same gain as FP-12's ticks-off approach, with more risk (`TakeControlOf`, `GetController` users). |
| GN-12 (1)-(2): bundled PSO cache | FP-16: all 36 misses are in frame 0, before the match is visible, so it isn't worth the upkeep yet. Revisit if hitches remain. |

## Batches

**Batch 0: measure first (no code)**
- Fix the capture: a real base view (the king on the map, or a free camera at the castle), true 1920x1080 and
  2560x1440 output, and the CSV row offset.
- Re-baseline with the fixed capture.
- One Insights CPU trace at the overview, to size FP-01.
- Console A/Bs (`r.Nanite 0`, `r.HZBOcclusion 1`, `r.VelocityOutputPass 1`), recorded in `BASELINE.md`.

**Batch 1: game thread, low risk (C++)**
- FP-02: movement asleep for garrisoned units and tower guards.
- FP-03: `bAlwaysCheckFloor = false`.
- FP-12: AI controller ticks off, physics interaction off, capsule overlap events off, the farmhand log at Verbose.
- FP-05 + GN-04 (1): the route memo, the tighter `Flood` loop, `PlanAttack` once per think, the strategy clock staggered
  between teams if the outcome is unchanged.
- FP-10: the auto-combat scan.
- GN-10: the far pips as triangles, the minimap plane trace cached, no actor iterator in `TickSites`.

**Batch 2: render thread and GPU (C++ and config)**
- FP-07 (non-occludable unit parts) or `r.HZBOcclusion=1`, whichever batch 0's A/B favours. Not both blindly.
- FP-08 / GN-11: `r.Nanite=0` on Windows (and `r.VelocityOutputPass`) if the A/B wins.
- GN-08: no render-state rebuild in `VLAmbience` / `VLSky`, and hidden instances parked at zero scale.
- GN-07: farm wheat and sheep as one ISM per mesh per building. Same transforms, sway, LODs and collision behaviour; the
  training dummies stay actors.
- FP-14: sound sets loaded at match start.

**Batch 3: assets, via the `Tools/ue` builders only, in UE 5.8.4 (the Mac is on 5.8)**
- GN-12 (3): `MATUSAGE_INSTANCED_STATIC_MESHES` on `M_Voxel` through `import_assets.py`. This fixes the smoke and motes
  falling back to the default material.
- FP-01: `lod_for_collision = 2` on the Realm v2 tiles through `realmv2_lods.py`, only if batch 0's trace shows sweeps
  are more than a third of `CharacterMovement`. Check the grid identity (node count and checksum) and the footstep
  surfaces.

**Batch 4: larger changes, each behind a `vl.Opt.*` cvar (default on only if verified)**
- FP-06: raid and flank searches in parallel.
- FP-04: general movement sleep.
- FP-11: parallel rig posing.
- FP-13 + GN-13: grid rebuild without the full relabel, and a batched rebuild in `SetupTestWorld`.

**Later**: FP-15 (instanced unit parts), only if the render thread is still the limit.

**Done when**: a Shipping Win64 build in `Builds/Windows/` packaged from the final code, and a `RESULTS.md` with
before/after numbers at the same views and resolutions. Also: the route and stuck tests unchanged, an AI-vs-AI match
with no new warnings, and screenshots at the three views matching the baseline.
