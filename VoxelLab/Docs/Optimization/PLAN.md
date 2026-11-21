# Optimization pass: merged plan

Sources: `findings_gpt61sol.md` (61S-xx), `findings_opus55.md` (C-, R-, P-, S-xx), `findings_fable52.md` (F-xx).
Rules for this pass: the default **High** quality keeps today's look (imperceptible changes only); visible trade-offs go
behind lower presets. Behaviour stays identical (King David, troop combat and archer aim, orders, paths, AI,
construction, sounds, silhouettes, team red cloth, health bars, the music setting and its TEMP override).

Gains are the audits' measured or estimated figures (PIE on an M5 Pro, Retina 3224 x 1660 output, about 200 troops
unless said otherwise). Risk: L low, M medium, H high.

## Do now

### Agent A: units, rig and animation (`VLKing`, `VLTroop`, `VLArcherCombat` / `VLSpy` / `VLSwordsmanCombat` poses, `VLFootDust`)

| # | Item | Sources | Expected gain | Risk |
|---|---|---|---|---|
| A1 | Batch the rig's transform writes: direct relative setters, one `UpdateComponentToWorld` per figure a frame; cape in figure-local maths (no read-back of component locations); archer and spy poses folded into the same single pass | C-01, F-01.1, 61S-11 | 8-10 ms game thread, 3-5 ms render thread at 200 units | L |
| A2 | `Figure` absolute (placed once a frame from the actor transform), so capsule moves stop cascading through about 70 children | C-02, F-02 (part) | 2-3 ms game thread | L |
| A3 | Animation significance: not recently rendered → no cosmetic pose or cape (gameplay clocks and hit timing keep running; gameplay reads of hand / bow / sword transforms stay correct); far (pips, about 75 m) → pose at a reduced rate, cape frozen; the controlled pawn and near units always full rate. `UVLArcherCombat` tick off while idle | C-03, F-01.2-4, 61S-11 | 30-70 % of what remains of A1 in the overview | L-M |
| A4 | Strip the per-troop camera rig (spring arm, camera, overview `ACameraActor`) except for the controlled pawn (created lazily in `TakeControlOf`); hidden skeletal mesh truly not ticking; foot dust only when `bFootDust` (and no kilometre-tall bounds) | C-04, F-04, P-08 (part) | 1-2 ms game thread; about 200 actors and 600 components fewer | L |
| A5 | Unit part render flags: `bAffectDynamicIndirectLighting` off, indirect lighting cache off (contact shadow flag is free: no light uses it) | F-05, R-09 | about 1 ms GPU (Lumen card captures), 0.5 ms render thread | L (screenshot) |
| A6 | Custom depth gating: off for every unit on the title screen; off for all units together when the overview is pulled far back (silhouettes stay player-only, through world, not through troops) | R-06, 61S-19 | 0.2-0.8 ms GPU plus draw calls | L |
| A7 | Hot-path logs behind `vl.BattleLog` / `vl.CombatLog`; `VLFootDust` render-state dirtied once | F-21, C-11 | small | L |

### Agent B: game-thread systems (`VLBattle`, combat-component lookups, `VLArrow`, `VLHUD*` hot paths, `VLEnemyAI` / `VLAISquads`, `VLAmbience`, `VLGameMode::TickShuffle`)

| # | Item | Sources | Expected gain | Risk |
|---|---|---|---|---|
| B1 | Unit registry in `UVLBattle` (per-team live arrays kept on spawn / death / team change), cached kind (`EVLUnitKind` or cached `FTroop` pointer instead of `FString` compares), cached combat-component pointers, buildings indexed by actor, plus a uniform spatial hash rebuilt once a frame | C-07, F-17, 61S-13 | 1-3 ms steady plus the 0.25 s spikes | L |
| B2 | Use it in `AutoSteer` (3 x 3 cells, squared-distance rejection, same rules), `FindFoe` / `TickAutoCombat` (same 0.25 s cadence, same choice rules), `TickDefence`, `TickKings`, `GetPopulation`, `GetSpyCount`, `GetUnits`, `FindBuilding`, `TickShuffle`, `HitDummies` / `GetDummies` (cached) | C-06, C-07, C-11, F-17, 61S-12, 61S-13 | 1-2 ms (AutoSteer alone) | L |
| B3 | Arrows: foes gathered once per tick and broad-phased by segment bounds; invariants hoisted | C-09, F-22 (scan only), 61S-14 | up to 2.5 ms in archer battles | L |
| B4 | HUD: picking only when the pointer or camera moved and against the cached selectable buildings; far pips as one quad / triangle item each; unit-to-platoon map built once a frame; one unit snapshot for bars / pips / tags | C-08, F-19, 61S-22 | 1-3 ms in the overview | L |
| B5 | Enemy commander: cache the muster point and vein list, static unit powers, reuse the duplicate raid route | C-10, 61S-18 (duplicate only) | spikes | L |
| B6 | `VLAmbience`: skip motes / smoke far from or outside the view | 61S-21, F-21 | small | L |

### Agent C: rendering, GPU and the Graphics settings (`Config/*.ini`, `Tools/ue/build_*.py`, materials, the minimap, a new Graphics section in the settings menu)

| # | Item | Sources | Expected gain | Risk |
|---|---|---|---|---|
| C1 | `r.TSR.History.ScreenPercentage=100` (default) | F-06 | 2.5-4 ms GPU | L (screenshot) |
| C2 | Graphics settings: quality preset (Low / Medium / High, default High), render scale, saved in the user settings; applied by code so it works in Shipping. High = today's look. Medium: Lumen final gather / scene detail 1, cheaper fog grid, render scale about 75 %. Low: Lumen off (sky light + AO fallback), no volumetric fog, lamp scattering 0, render scale about 60 %, sane shadow settings | S-01, R-01, 61S-03, F-23, R-12 | High: none (by design); Medium / Low: 30-50 % GPU | L |
| C3 | Lumen quality made preset-aware at runtime (the post-process volume's 2.0 stays for High) | R-02, F-07 | Medium / Low presets: 1.5-6 ms | L |
| C4 | Volumetric fog: off (or faded) when the overview camera is far above the ground, if the screenshot shows no difference; coarser grid on lower presets | R-03, F-09 | 1.5-5.8 ms in the far overview | L-M (screenshot) |
| C5 | Lamps: `MaxDrawDistance` and fade (neutral at sensible distances) | R-08, F-10, 61S-20 | small to 1 ms | L |
| C6 | `r.IndirectLightingCache=0` (no static lighting in the project) | R-09 | 0.5 ms render thread | L |
| C7 | Minimap: two or three captures, lighting / Lumen / shadow / AO show flags off, no persistent view state | F-16, R-13, 61S-04 | start-of-match hitch, GPU memory | L |
| C8 | Sway plants (grass, flowers, wheat): one-sided via the material instance (cloth and capes stay two-sided); wheat gets the 60 m WPO-disable distance; rigid shadow-cache invalidation on swaying casters only if the shadow difference is imperceptible | R-07, 61S-02 (WPO part) | small to 1 ms | L |

### Agent D: package, memory and load (`VoxelLab.uproject`, `Config/DefaultGame.ini`, packaging target settings, `Tools/package.sh`, music, `VLGrid`, `VLConstruction`, `VLForest`, import settings)

| # | Item | Sources | Expected gain | Risk |
|---|---|---|---|---|
| D1 | Disable `NNEDenoiser` and `NNERuntimeORT` (and other unused default plugins with runtime content, after checking the cook) | P-01, F-12, 61S-07 | about 200 MB | L |
| D2 | Mac targeted shader formats: SM6 only | P-03, F-13, 61S-08 | 36-80 MB, cook time | L (Apple Silicon only) |
| D3 | `Tools/package.sh` defaults to Shipping (stripped), `sh Tools/package.sh Development` kept for tests; the command-inbox poll compiled out of Shipping | P-02, F-11, 61S-09, F-21 | 200-300 MB, a few % CPU | L |
| D4 | `DirectoriesToAlwaysCook` narrowed to the folders loaded by name at runtime (every map kept: they are selectable); legacy and source-only meshes left out; verified against every string-built asset path in `Source/` | P-04d, F-14.5, 61S-24 | 30-70 MB | M (verify the cooked listing) |
| D5 | Music: nothing loaded, created or decoded while the setting is 0 (the TEMP override stays); songs streamed / loaded on demand when music is on | P-05, F-21, 61S-23 | about 50 MB memory, startup I/O | L |
| D6 | Path grid build in parallel (`ParallelFor` over rows), with an identical grid (node count and checksum compared); `RebuildArea` likewise | P-07, F-15, 61S-15 | 1-2.4 s off every match start | L-M |
| D7 | Placement: cache the static part of `CheckPlacement` per snapped cell for the session, dry-run tree clearing without logs or allocations, one combined rebuild when trees are cleared for a building | 61S-17, 61S-01 (coalescing), C-11 | the 22-28 ms placement hitches | M |
| D8 | `UVLConstruction::TickSites` / `TickYards`: Builder-kind check before any component search, reused scratch maps | 61S-05, C-11 | small to 1 ms at 200 units | L |
| D9 | Collision: none on the backdrop; water and sea only if nothing (grid, arrows, camera, footsteps) needs their trimesh, else a simple replacement or defer | P-06 | memory, cook size | M |

### Agent E: mesh LODs (`Tools/ue/` LOD scripts, `import_king.py`, the troop / king / building assets)

| # | Item | Sources | Expected gain | Risk |
|---|---|---|---|---|
| E1 | LOD 1 and 2 for every unit part (troops, Builder, Spy, King, enemy material twins), screen sizes chosen so the hero view never leaves LOD 0; kept by the import scripts | F-03, R-05, 61S-10 | 4-8 ms GPU at 100 units in view | L-M (screenshot) |
| E2 | LOD 1 for buildings (castle, barracks, range, farmstead, ...) at overview distances | R-05, 61S-16 | 1-2 ms in the overview | L-M |

## Defer (with reasons)

| Item | Sources | Why not now |
|---|---|---|
| One rigid-skinned skeletal mesh per unit, or instanced unit parts | F-02, R-04b, 61S-10 | Structural rewrite of the rig; cape, sword in fist, flash overlay, team materials and custom-depth stencils all need re-validating. A1-A3 take most of the CPU cost first |
| Atlas / texture-array voxel material (one section per mesh) | R-04a | Touches every material and mesh; high risk to the look; needs its own pass |
| Greedy ground meshing, separate ground collision, half-precision UVs, lower distance-field resolution | P-04, F-08.3, F-14, 61S-16 | Changes the ground's look (baked corner shading, colour jitter) and the footstep surface lookup; needs a full regeneration of every map |
| Nanite on static voxel meshes | F-08.1, R-05 | Promising but a renderer-wide change on Metal 5.8; would replace E2 for buildings; its own experiment with an A/B |
| Wheat and props into HISM | 61S-02, R-04d | Farm crops are spawned and removed with their buildings; ownership semantics need care |
| Character movement tick off for idle troops; grid-height walking | C-05, F-18 | Behaviour risk (knock-backs, falls, the water rescue); A2 already removes the movement cascade |
| Baked path grid; compact grid nodes | P-07, 61S-15 | Needs invalidation on map changes; D6 gets most of the load-time win |
| Instanced arrows | F-22 | Low gain now; the scan (B3) is the costly part |
| Staggered auto-combat acquisition, 5 Hz construction ticks | F-17, 61S-13, C-11 | Changes reaction timing (behaviour must be identical) |
| Shared floods for chasers, path-search budgets, route caches | F-20, 61S-18 | Unmeasured; behaviour risk on responsiveness |
| Real-time sky capture off | R-10, 61S-06 | Measured within noise; a look risk for no gain |
| Sun shadow distance | F-10, R-12 | Measured no gain under VSM (C2 keeps lower presets sane) |
| Cap the title screen at 30 fps | R-13 | Power only; changes the menu's feel |
| Unit actor pooling / prewarming | P-08 | Low gain once A4 lands |
| Route-line caps, HUD text-width caches | C-08 | Small; visible or low value |
| Incremental grid connectivity, dead-node recycling | 61S-01 | High effort and risk on node indices |
| "VSM Log Stats And Status" bucket | R-11, F-06 | A profiler attribution artefact on Metal; check again in the Shipping package |

## Verification

- Before / after in PIE with the audits' methods: `vl.Perf`, `stat unit`, `ProfileGPU` + `Tools/gpuprof.py`,
  `csvprofile`. Armies with `vl.SpawnTeam`, `vl.AIvsAI 1`, `vl.TimeScale`. `L_Realm` and `L_Highlands`. Music off.
- Package size before / after; match load time (the `GRID built` line and map start).
- A final regression match on `L_Realm`, AI vs AI, for a few minutes.

Results are appended below when the pass is done.

## Results (2026-11-21)

All 32 "do now" items were done, except: C4 coarsens the far-overview fog grid instead of switching fog off (off was
visible); C8's rigid shadow-cache invalidation was skipped (wheat leans up to 17 cm, the frozen shadow would show);
D4 keeps `/Game/Voxel` always-cooked and excludes only the 30 legacy king meshes (L_VoxelVillage uses `SM_Terrain_*` and
`SM_Tree_*`); D9 left water / sea collision alone (a box changes the grid: the sea trimesh has holes over dry ground);
B1 is one spawn-ordered registry with inline team checks instead of per-team arrays. A added an item: a part is only
re-sent to the renderer once it moved 0.25 px (most of A's gain).

Same benchmark before and after (PIE floating window at 3224 x 1660, one editor session each; `vl.Perf` averages;
battle = 50 swordsmen + 50 archers a side, `vl.AIvsAI 1`):

| | Before | After |
|---|---|---|
| L_Realm load (LoadMap) / path grid | 2.17 s / 1,055 ms | 0.83 s / 184 ms |
| L_Highlands load / path grid | 4.70 s / 1,964 ms | 1.75 s / 311 ms |
| L_Realm hero view at start: GPU | 22.9 ms (44 fps) | 16.8 ms settled (59 fps, the 60 cap) |
| L_Realm battle, overview 0.45: game thread / GPU / fps | 32.7 / 28.4 ms / 28.8 | 9.2 / 19.7 ms / 38.0 |
| L_Realm battle, far overview 1.0 | 36.6 / 37.1 ms / 24.7 | 7.4 / 20.5 ms / 46.7 |
| L_Realm battle, near overview 0.2 | 23.5 / 22.4 ms / 44.1 | 6.7 / 18.0 ms / 53.2 |
| L_Highlands hero view: GPU | 24.7 ms | 17.4 ms |
| L_Highlands battle, overview 0.45 | 30.2 / 31.4 ms / 31.9 | 17.5 / 19.0 ms / 48.1 |
| L_Highlands battle, far overview 1.0 | 15.7 / 32.3 ms / 30.5 | 11.2 / 19.5 ms / 49.1 |

Presets (agent C, same session, GPU ms, Realm): hero view High 17.4 / Medium 13.5 / Low 9.1; battle 0.45
21.4 / 17.3 / 12.2. Per-agent same-session A/B figures are in the agents' reports (summarised in the coordinator's
final report).

Package (`sh Tools/package.sh`, now Shipping): 1,566 MB -> 1,062 MB. Executable 423 MB (Development) -> 166 MB
(Shipping, stripped); NNE 99 MB -> none; `VoxelLab-Mac.ucas` 958 MB -> 816 MB (SM6 shaders only, no NNE content, no
legacy king meshes; +7.7 MB of LODs). The cook lists every map, troop, king part, sound, UI texture and material the
code loads by name. The Shipping app was launched once: it starts and runs. `sh Tools/package.sh Development` remains
for tests (console, log, command inbox).

Regression smoke test (L_Realm, AI vs AI, 3.5 min, after all changes): both sides fought (losses 63 / 24), 639 arrows
loosed, builders laid and raised buildings, box and click selection worked, King David took control and walked;
0 errors or warnings in the log. Enemy red cloth looks the same at LOD 0 and LOD 1.
