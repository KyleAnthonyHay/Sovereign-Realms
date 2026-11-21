# VoxelLab optimization audit — GPT 6.1 Sol

2026-11-21. Findings only. Paths below are relative to `VoxelLab/` unless explicitly stated otherwise. No code, configuration, or assets were changed, and no editor session was started.

## Summary

The largest scalable frame costs are the rigid-part character renderer, unconditional procedural posing, all-unit separation/target/arrow scans, and full-detail world geometry. The strongest smaller changes are to coalesce navigation rebuilds, extend the existing plant optimizations to wheat, stop redundant minimap captures, avoid construction's per-frame component searches, and capture the static skylight once. The game also needs usable graphics quality/resolution controls.

The package has several independent size opportunities: two unused-looking ONNX runtime dylibs total **96.75 MiB**, both Metal shader formats are cooked, the release command defaults to Development, and the whole voxel asset directory is forced into the cook. Music source size is substantial, but it must **not** be equated with cooked or decoded runtime memory: the importer already sets music to `RETAIN_ON_LOAD`.

Findings are ordered approximately by impact relative to effort: localized improvements first, then structural changes and secondary costs. GPU/CPU milliseconds below are not claimed unless explicitly attributed to existing measurements. Recommendations that alter appearance or simulation timing need the listed checks.

## Measurements and evidence method

This is a static audit, supplemented by **existing project logs**, not a new profile. I read the README, source, configs, generation/import/packaging scripts, mesh metadata and glTF accessors, and inspected existing artifact sizes. Existing logs and the package can predate the current working tree; they establish prior observations, not current performance guarantees. The working tree already contains extensive changes/untracked assets; I did not alter them or consult the other auditors' findings.

- README `351–354`: prior Realm PIE result at 1612×830 on M5 Pro, approximately 50 fps normally and 38 fps fully zoomed out (20.0 vs 26.3 ms/frame); README `417–421` records another session at roughly 31–44 fps. These varied enough that they should not be used as current controlled benchmarks.
- Existing `Saved/realm_test.log:51–52`: a 1,634-cell local navigation resample took **27.9 ms**, total tree clear 31.2 ms. `Saved/highland_test.log:85–86`: 1,521 cells took **21.1 ms**, total clear 22.2 ms. The Highlands log also contains a failing tree-count assertion at line 89; these are historical timings, not a claim that this test suite currently passes.
- Current metadata: Realm ground **1,923,089 faces / 255 tiles**; Highlands **3,736,818 / 398 tiles**. Actual glTF index-accessor triangle totals: **3,846,178** and **7,473,636**. Summed material primitives: **1,370** and **2,270** respectively. These are source geometry/section counts, not measured visible draw calls.
- Current character glTF counts, summing the meshes referenced by each character's `parts` dictionary:

| Character | Mesh parts | Material primitives | Triangles |
|---|---:|---:|---:|
| KingB | 35 | 74 | 53,750 |
| Swordsman | 34 | 59 | 63,262 |
| Archer | 38 | 70 | 54,969 |
| Spy | 36 | 58 | 42,350 |
| Builder | 14 | 25 | 61,009 |

- Counts above come from `SourceArt/Meshes/SM_<character>.json`, each referenced `.gltf`'s `meshes[].primitives[]`, and `accessors[indices].count / 3`. Quad metadata differs slightly from glTF because a few non-quad primitives exist. Builder has **14** parts, not the approximately 35–38 of most fighters.
- Current `realm.json` / `highland.json`: 12,831 / 15,108 layout instances; 12,061 / 14,334 satisfy the forest generator's tree-or-plant predicate, in 20 mesh kinds. Wheat is excluded from that predicate: **288 / 258 wheat actors**, or **1,275,264 / 1,142,424 source triangles** at 4,428 triangles per wheat mesh.
- Existing `Builds/Mac/VoxelLab.app`: **1,566.02 MiB** logical file bytes; game `.ucas` **957.85 MiB**, executable **413.41 MiB**, Metal shader converter **55.51 MiB**, each of two distinct regular ONNX dylibs **48.38 MiB**. This counts logical sizes, not APFS physical allocation/RAM. `file` reports an arm64 Mach-O executable, so this is not a universal-binary duplication issue.
- `Saved/package.log:1124–1133` independently records the game container at **4,562.34 MiB raw -> 957.85 MiB stored**, already Oodle-compressed, plus **62.52 MiB compression block padding**. Do not recommend simply enabling compression: it is already enabled.
- Source Content totals **588.72 MiB**: `Voxel/Meshes` 303.3 MiB, `Voxel/Audio` 239.3 MiB, maps 26.3 MiB, troops 13.3 MiB, king 5.3 MiB; world textures only about **0.4 MiB**. These are editor/source asset sizes, not per-category cooked sizes.

## Findings

### 61S-01 — A local navigation change traverses the full graph, and building placement can do it twice

- **Area:** game-thread spikes; navigation memory.
- **Evidence:** `Source/VoxelLab/VLGrid.cpp:357–418` leaves old floors in `Nodes` with `Region=-1` and appends replacements. Lines `484–525` reset/flood-fill regions across **all** nodes and reinitialize all four node-sized scratch arrays after every local edit. `VLForest.cpp:198–202` calls `RebuildArea` after clearing trees; `VLConstruction.cpp:913–919` then resamples the building footprint separately. Historical 21.1–27.9 ms local resamples are cited above.
- **Estimated impact:** **High** for construction/clearing stutters: one recorded resample already exceeds a 16.7 ms frame budget. Combining the two edits can remove one full connectivity pass when trees are cleared. Every superseded node also retains about 64 bytes of node + search-array storage (48-byte naturally aligned `FNode` plus four 4-byte search fields), before capacity overhead; 100,000 accumulated obsolete nodes is approximately 6.1 MiB.
- **Effort:** Medium for coalescing; High for incremental connectivity/recycling.
- **Risk:** Behaviour risk around disconnected regions, gates, bridges and outstanding node indices. Existing callers retain indices, so arbitrary compaction is unsafe.
- **Recommended fix:** collect the union of cleared-trunk and building-footprint bounds, mutate collision/instances, then perform one rebuild. Cache ground/collision context. Follow with chunked connectivity or a budgeted region update, and a free-list/generation scheme for dead nodes or safe compaction at a controlled synchronization point. Re-run terrain, clearing, formation and bridge routes.

### 61S-02 — Farm wheat bypasses forest instancing, LOD and wind-distance optimizations

- **Area:** draw submission, GPU geometry/WPO, actor/load overhead.
- **Evidence:** `Tools/ue/build_realm.py:115–116` only puts trees or `group == plants` into HISM; lines `199–205` spawn the rest individually. Highlands repeats this at `build_highland.py:196–202`. `plant_lods.py:15–17` covers grass, flowers and bushes, not wheat. The 60 m WPO-disable distance only applies to grass/flowers (`build_realm.py:143–144`). `import_assets.py:160,191–192` gives wheat the sway material. Current Realm/Highlands wheat totals are 288/258 actors and 1.28/1.14 million source triangles. The README explicitly confirms crops have no cull distance (`README.md:337–338`).
- **Estimated impact:** **High** potential in farm views, **Medium** overall; hundreds of actors and over a million potentially visible triangles survive at overview distances where they contribute very few pixels.
- **Effort:** Low–Medium.
- **Risk:** Visual popping/wind changes; runtime farm props must remain removable with their parent building. Do not put gameplay trees and crops into the same clearing semantics accidentally.
- **Recommended fix:** add wheat-specific HISM components grouped by farm/plot ownership; generate a low-poly far wheat LOD or field proxy; add distance-based WPO disable and a screen-size-based fade/cull. Apply the same treatment to wheat spawned by construction, not only level generation.

### 61S-03 — There is no graphics quality or render-resolution escape hatch for an expensive default renderer

- **Area:** GPU frame time and hardware scalability.
- **Evidence:** `Config/DefaultEngine.ini:8–15` enables distance fields, Lumen GI/reflections, VSM and stencil custom depth. Existing gather tuning at `22–26` already reduces cost and must be preserved. `Tools/ue/build_level.py:120–124,148–149` enables volumetric fog and overrides Lumen scene/final-gather quality to 2.0. `VLHUD.cpp:89–101` applies only audio volume and `t.MaxFPS`; the settings menu at `VLHUDMenus.cpp:347–400` has volume, UI scale, frame cap and camera/input settings, but no quality/resolution controls. No project screen-percentage/dynamic-resolution/scalability code/config was found.
- **Estimated impact:** **High** user-facing opportunity: a frame cap cannot improve the underlying 20–30+ ms render cost in prior observations. For resolution-dependent passes, 80% linear resolution has 64% of the pixels (36% less pixel work), though whole-frame savings will be smaller and GPU dependent. The 8–12 ms Lumen figure in the config describes the **old**, pre-tuned setup, not current measured cost.
- **Effort:** Low–Medium.
- **Risk:** Visual quality; disabling Lumen without replacement lighting changes the look substantially. Post-process quality overrides can defeat intended preset tuning.
- **Recommended fix:** expose saved Low/Medium/High presets and render scale, with an appropriate upscaler on Metal; optionally add supported dynamic resolution after validation. Tune GI/reflection quality, fog grid quality, shadows and geometry budgets together. Make the PP quality overrides preset-aware. Benchmark fixed cameras and resolutions with GPU timings before selecting defaults.

### 61S-04 — The unlit minimap re-renders the whole map for 1.5 seconds

- **Area:** startup/first-overview GPU and render-thread burst.
- **Evidence:** `VLHUDGame.cpp:431–450` creates a 512×512 orthographic `SCS_BaseColor` capture with fog/post effects disabled and `bCaptureEveryFrame=false`, but `493–495` explicitly calls `CaptureSceneDeferred()` **each drawn frame for 1.5 seconds**. The justification is exposure settling, although base colour is unlit and exposure-independent. Rendering state persists (`443`) after the snapshot is kept.
- **Estimated impact:** **Medium–High transient**: approximately 45/90 complete extra captures at 30/60 fps, instead of one or a few; the small target does not eliminate map submission/geometry cost. No steady-state repeated capture after 1.5 s is claimed.
- **Effort:** Low.
- **Risk:** Low; allow map/streaming resources to become ready and avoid a blank first capture.
- **Recommended fix:** issue one capture when resources are ready (at most a small bounded warm-up if demonstrated necessary), show its result immediately, and destroy the capture component/release persistent state while keeping the render target. A generated map texture could eliminate the runtime scene capture entirely.

### 61S-05 — Construction searches every unit's component list every frame, including non-Builders

- **Area:** game-thread housekeeping/allocation.
- **Evidence:** `VLConstruction.cpp:1447–1455` constructs a temporary `TMap`, iterates every live `AVLKing`, and calls `FindComponentByClass<UVLBuilderWork>()` without first checking Builder kind. Fighters own two components per rigid part (`VLKing.cpp:294–313`), so negative searches can walk dozens of joints/mesh components. It runs every playing frame (`VLConstruction.cpp:1442`). `TickDefence` similarly constructs a fresh live-unit array every frame before checking building shot timers (`VLBattle.cpp:1486–1505`).
- **Estimated impact:** **Medium**, particularly with 100–240 fighters; unnecessary component examinations and heap churn scale with army size even when there is no construction work. At 200 units × roughly 70 figure components × 60 fps, construction alone can approach 840,000 component-type examinations/second before other systems.
- **Effort:** Low for a kind check; Medium for maintained registries.
- **Risk:** Low if worker registration is updated on spawn, reassignment, death and job completion.
- **Recommended fix:** immediately gate by Builder kind, then maintain registered Builder/work-component lists and per-job worker counts. Reuse unit snapshots/scratch arrays and only gather defence candidates when a tower is ready to shoot. Share an authoritative live-unit registry with combat/HUD rather than repeatedly rebuilding it.

### 61S-06 — A static sky is recaptured continuously

- **Area:** GPU/render-thread recurring lighting work.
- **Evidence:** `Tools/ue/build_level.py:108–111` creates a movable Skylight with `real_time_capture=True`. Sun orientation, intensity, sky tint and atmosphere are configured once (`87–113`); no runtime day/night/weather update was found. The generator comment itself ties the option to prior capture cost.
- **Estimated impact:** **Medium potential**, low implementation cost: removes recurring environment capture/filtering when the lighting is unchanged. UE time-slices this work, so do not assume a full cubemap render every single frame or quote old cloud costs as the current saving.
- **Effort:** Low.
- **Risk:** Low visual risk if the sky is truly static; atmospheric effects must match the initial capture.
- **Recommended fix:** disable real-time capture and explicitly recapture once after initialization, and only after future sky/light changes. Compare before/after skylight reflections and indirect light on Metal.

### 61S-07 — The shipped bundle contains almost 97 MiB of ONNX runtime without project use

- **Area:** package size / dependency load surface.
- **Evidence:** `Builds/Mac/VoxelLab.app/Contents/UE/Engine/Plugins/NNE/NNERuntimeORT/Binaries/ThirdParty/Onnxruntime/Mac/` contains `libonnxruntime.dylib` and `libonnxruntime.1.24.dylib`, each **50,727,400 bytes**, distinct regular files/inodes. No NNE/ONNX reference was found in `Source/`, `Config/` or `VoxelLab.uproject`; `VoxelLab.Build.cs:9–10` lists the game dependencies. Enabled editor tooling/default plugin dependency closure may pull it in; that exact chain still needs checking.
- **Estimated impact:** **Medium**, approximately **96.75 MiB** logical bundle reduction if the runtime dependency closure is unnecessary. This is not a 97 MiB resident-memory claim.
- **Effort:** Low–Medium.
- **Risk:** Packaging/startup failure if another required plugin actually needs NNE.
- **Recommended fix:** trace build receipts/plugin dependencies, explicitly disable unused NNE/neural runtime plugins in the game target/project, and keep editor-only tooling outside the runtime closure. Rebuild and test packaged startup. Do not manually delete linked dylibs from the finished app.

### 61S-08 — Both Metal shader formats are cooked for the same Mac build

- **Area:** package/cook time; shader permutations.
- **Evidence:** `Saved/package.log:475–508,618–651` builds both `SF_METAL_SM5` and `SF_METAL_SM6`. `1075–1085` reports their grouped stored shader sizes: SM5 Global **31,368 KB** plus project **5,009 KB**; SM6 Global 98,991 KB plus project 11,013 KB. `Saved/Cooked/Mac/VoxelLab/Content/` likewise contains both formats' archives. The game uses modern Lumen/VSM and targets Apple Silicon, but supported hardware/RHI requirements have not been formally narrowed in project config.
- **Estimated impact:** **Medium**, roughly **35.5 MiB** of compressed SM5 shader payload, plus associated cache/metadata, if only SM6 is required. Fewer permutations also reduce cook work. Do not count the duplicate Metadata/ShaderLibrarySource files as duplicated shipping payload.
- **Effort:** Low–Medium.
- **Risk:** Loses fallback hardware/RHI support; confirm actual minimum macOS/GPU support before removing a format.
- **Recommended fix:** explicitly configure the intended Mac targeted shader format(s); ship only the required format for the supported hardware matrix. Audit unused renderer/plugin permutations next, preserving those needed for Lumen, VSM, WPO and custom depth. Verify a clean cook and packaged launch on the minimum supported Mac.

### 61S-09 — Distribution builds default to Development, retaining a large executable and diagnostic paths

- **Area:** package size and baseline CPU/runtime overhead.
- **Evidence:** `Tools/package.sh:8` defaults to Development; `Config/DefaultGame.ini:12` also selects Development. Existing package metadata confirms `config=Development` (`Saved/package.log:288`); the executable is **413.41 MiB**. `xcrun size -m` reports approximately **165.19 MiB in __LINKEDIT**; not all of that is removable. Debug/recording console paths and the filesystem command inbox remain in game code (`VLGameMode.cpp:1070–1122`), including a filesystem existence poll every 0.05 s.
- **Estimated impact:** **Medium** package reduction and some runtime improvement; no exact Shipping-vs-Development delta was measured. The executable is already arm64-only.
- **Effort:** Low–Medium.
- **Risk:** Shipping loses console/debug workflows; symbol stripping must preserve useful external crash symbols and signing.
- **Recommended fix:** make the distributable release path explicitly Shipping, keep Development as a separate developer command, strip through supported UE/Xcode packaging, and retain dSYMs separately. Compile developer command-inbox/recording instrumentation only into development builds or behind an explicit opt-in. Compare sizes and packaged frame timings.

### 61S-10 — Each troop is dozens of independently rendered mesh parts, often with multiple material sections

- **Area:** render-thread submission, GPU geometry/shadow/custom-depth passes, component memory.
- **Evidence:** `VLKing.cpp:271–313` creates a scene joint and `UStaticMeshComponent` for each part; all meshes cast shadows/contact shadows, and `VLTeamLook` enables custom depth (`230–234`). Source counts are in the table above: a swordsman is **34 mesh components / 59 material primitives / 63,262 triangles**, an archer **38 / 70 / 54,969**. `Tools/ue/import_king.py:30–49` imports with Nanite disabled and does not create character LODs. Current troop cap can reach 120 a side (`README.md:478–479`).
- **Estimated impact:** **High** at army scale. A hypothetical 100-swordsman view starts with **3,400 mesh primitives, 5,900 material sections and 6.33 million source triangles**, before additional depth/shadow/overlay work. Engine batching/culling means these are not literal measured draw calls; component/material granularity still presents a substantial submission burden.
- **Effort:** High for a skeletal representation; Medium for coarse proxies/LODs.
- **Risk:** Visible posing/material/team-colour changes, cape/weapon attachment fidelity, picking and death animation regressions.
- **Recommended fix:** bake rigid pieces into a skinned mesh with rigid bone weights and consolidated material slots/atlas; use the existing procedural transforms as bone poses. Add mesh LODs and simplified far shadow/custom-depth representations. For very distant units consider a merged proxy or VAT/instanced representation. Profile Metal alternatives before treating Nanite as a universal fix for animated characters.

### 61S-11 — All units receive full procedural animation regardless of visibility or screen size

- **Area:** game-thread animation and transform propagation.
- **Evidence:** `VLKing.cpp:3322–3362` always calls `Animate` for every living unit when unpaused. `2924–2968` writes body/arm/leg transforms; `3010–3012` advances dust, sword and cape; `3106–3204` integrates 20 cape panels for caped units, substepping at up to 90 Hz (`3163–3171`) and updating world rotations. No visibility/distance animation-rate gate exists. Builders correctly have no cape, and troops already disable per-foot steps/dust (`VLTroop.cpp:10–12`). Crucially, damage/swing timing is embedded in `Animate` (`2696–2704`).
- **Estimated impact:** **High** with large armies, particularly idle/offscreen units. At 200 caped fighters there are 4,000 cape-panel integrations plus figure pose/transform work each frame; at 60 fps, 240,000 panel updates/second before substeps.
- **Effort:** Medium.
- **Risk:** **High behaviour risk if simply skipping Animate**: blows could stop landing or timers change. Low-frequency cape updates can become unstable if large accumulated timesteps are fed into the current solver.
- **Recommended fix:** separate gameplay combat clocks/hit events from visual pose evaluation. Use significance tiers: full rate for the controlled/near units, 15–30 Hz visual posing for middle distance, simplified cape or static proxy far away, and suspend invisible cosmetic work. Keep deterministic combat/movement clocks running, interpolate visible poses, and bound/cap cape catch-up work.

### 61S-12 — Movement separation performs an all-unit scan for every moving unit every frame

- **Area:** game-thread crowd movement.
- **Evidence:** `VLKing.cpp:541–620`: `AutoSteer` iterates every `AVLKing` for each auto-walker, computes distance with `Size()`, and only then applies a **115 cm** personal-space threshold. It is invoked from non-player `PollInput` each frame (`1643–1655`).
- **Estimated impact:** **High scaling**, O(moving units × all units): 200 movers among 200 units perform about **39,800 other-unit checks/frame**, approximately 2.39 million/second at 60 fps, mostly rejecting units much farther than 1.15 m.
- **Effort:** Medium.
- **Risk:** Medium crowd behaviour risk: preserve current vertical tolerance, sideways bias and near-overlap rules.
- **Recommended fix:** update a shared spatial hash/grid of live units once per frame and query only overlapping nearby buckets. Use squared distance for rejection and take square roots only for true neighbours. Snapshot positions consistently so iteration order does not change steering unpredictably.

### 61S-13 — Auto-acquisition repeats global actor scans in one synchronized 0.25-second burst

- **Area:** combat game-thread spikes; AI perception.
- **Evidence:** `VLBattle.cpp:1638–1659` gates acquisition at **0.25 s**, collects all units, then calls `FindFoe` for eligible units (`1732–1734`), which independently uses `TActorIterator<AVLKing>` (`1573–1590`) and then scans buildings. `VLEnemyAI.cpp:667–696` separately performs own-eyes × enemy-unit visibility checks; observation already runs on its Think cadence (`561–568,626`), not each frame. `GetUnits` itself always reconstructs an actor-iterator snapshot (`VLBattle.cpp:1555–1564`).
- **Estimated impact:** **Medium–High** at troop cap: up to roughly 40,000 unit comparisons in one acquisition tick for 200 idle eligible units, plus buildings/other systems. This is a periodic O(N²) workload, **not** a full N² targeting scan every frame.
- **Effort:** Medium.
- **Risk:** Preserve nearest-target choice, unit-before-building priority, Spy notice multiplier, garrison/height exclusions, guard leashes and explicit orders.
- **Recommended fix:** reuse the live-unit spatial index and per-team registries; query ranges, then apply the existing exact filters. Stagger acquisition phases or budget units across frames while maintaining comparable reaction latency. Use the same broad phase for AI eyes without allowing the commander to read unseen foes.

### 61S-14 — Every flying arrow scans every unit every frame in addition to its world trace

- **Area:** projectile game-thread CPU.
- **Evidence:** `VLArrow.cpp:506–554` traces each flying arrow and calls `UnitOnPath`; that function iterates all units (`387–413`) and performs capsule-distance/segment work. Pooling is already present and limits object churn; it does not remove these per-flight scans. The broad-distance test even recomputes `Seg.Size()` inside the unit loop (`398`).
- **Estimated impact:** **Medium–High scaling** with volleys: 80 active arrows × 200 units = **16,000 candidate checks/frame** plus 80 world traces. These are workload examples, not measured typical arrow concurrency.
- **Effort:** Medium; Low for hoisting invariant segment length.
- **Risk:** Preserve friendly pass-through, nearest-hit ordering against world collision, tower launch ignores and fast-arrow tunnelling protection.
- **Recommended fix:** query the shared spatial index with the swept segment's expanded bounds, then run the existing exact capsule test only on candidates. Alternatively use a dedicated query collision channel/broad phase with team filtering. Hoist per-arrow invariants outside the candidate loop and retain continuous segment tests.

### 61S-15 — Navigation samples the complete static map synchronously even before a match begins

- **Area:** load/title startup latency and navigation RAM.
- **Evidence:** `VLGameMode.cpp:899–901` calls `EnsureBuilt` in BeginPlay. `VLGrid.cpp:168–205,299–334` allocates per-cell arrays and performs downward traces/headroom/body overlap tests for every cell, then joins/flood-fills the graph. README `353,417–418` reports **1.5 s at 832² cells** and **2.4 s at 1080²**. Title backdrop code also requests the built grid just to obtain bounds (`VLHUD.cpp:520–528`). `VLGrid.h:63–70,134–144` stores eight neighbours plus node state and four node-sized search arrays.
- **Estimated impact:** **High startup**: 1.5–2.4 seconds previously spent rebuilding deterministic static data. Grid storage is tens of MiB: using only the historical Highlands main region's 731,882 nodes as a lower-bound example, 64 bytes/node plus nine bytes × 1,166,400 cells is approximately **54.7 MiB**, excluding other regions/capacity/temporary searches.
- **Effort:** Medium–High.
- **Risk:** Cache invalidation after map/collision/unit-dimension changes; collision queries should not be moved naively to an unsafe background thread.
- **Recommended fix:** bake/serialize the base navigation graph in the generation/build pipeline, keyed by map and grid/collision settings; load it and apply runtime building/clearing deltas. Store map bounds separately so the title does not require navigation. If runtime generation remains, chunk/time-budget safe queries under a loading state. Investigate chunk-local neighbour encoding after measuring actual memory.

### 61S-16 — Terrain/buildings keep dense geometry and complex collision at all gameplay distances

- **Area:** GPU base/shadow passes, render submission, mesh/collision memory and load time.
- **Evidence:** ground/section totals are in Measurements. Buildings include Castle **58,030 faces**, BarracksYard **69,338**, ArcheryHall **68,216**, Farmstead **55,506** (`SourceArt/Meshes/<name>.json:1`). `Tools/ue/import_assets.py:147,152,202–204` disables Nanite, requests full-precision UVs and uses complex-as-simple collision for complex assets. Existing LOD scripts target only trees/small plants. `assets/realm_terrain.py:52–100` already merges compatible **2×2** coplanar quads, but not arbitrary larger runs. Levels place terrain tile actors individually (`build_realm.py:184–187`, `build_highland.py:181–184`).
- **Estimated impact:** **High** overview/world-memory opportunity: Highlands source ground alone is 7.47 million triangles and 2,270 material sections before visibility filtering. Source glTF has 14.95 million position-accessor entries for Highlands / 7.69 million Realm. Switching one UV channel from float32 to float16 would save an upper-bound **57.0 / 29.3 MiB** at those source counts; UE vertex welding/build settings can lower actual counts, so inspect built buffers before claiming that saving.
- **Effort:** Medium–High.
- **Risk:** Simplification can move stairs/cliff edges, alter baked corner shading or UV alignment, and break navigable gaps if visual/collision meshes change together. Large world-space tiled UVs may need full precision; do not switch blindly.
- **Recommended fix:** generate screen-size LODs/far HLOD proxies for buildings/terrain/backdrops, preserve collision as an independent representation, and extend coplanar merging where material/colour/UV continuity allows. Split terrain collision from rendering and simplify safe regions. Validate half-precision UVs or tile-local UV generation on representative distant/close surfaces. Trial Nanite only on supported static opaque meshes using the actual Metal hardware matrix; retain fallback assets.

### 61S-17 — Placement preview does expensive physical sampling and a full forest traversal on snap changes

- **Area:** game-thread placement interaction and AI building spikes/logging.
- **Evidence:** `VLConstruction.cpp:1801–1808` reruns checks on **every changed half-metre snap/yaw**, with a 0.3 s refresh only when stationary. `CheckPlacement` samples each metre plate plus a two-cell fringe (`690–718`), potentially up to six world traces per sample (`657–680`), and invokes dry-run tree clearing (`768–770`). `VLForest.cpp:122–169` scans every HISM instance; `177–211` constructs arrays and always logs, including dry runs. Current forests contain 12,061/14,334 tree/plant instances. AI can synchronously call `FindPlacementNear` repeatedly: up to 90 candidates by default (`VLConstruction.h:176`), or 6×30 attempts for a tower (`VLEnemyAI.cpp:1471,1493`).
- **Estimated impact:** **Medium–High episodic**: a roughly 20×19 m building plus fringe needs about 552 samples per check, potentially at input-frame frequency while moving the pointer; actual failures may short-circuit AI checks. Dry-run scans/logs can occur dozens of times a second.
- **Effort:** Medium.
- **Risk:** Placement validity must stay authoritative as units/buildings/trees change.
- **Recommended fix:** cache static terrain/footprint results by kind, snapped location, rotation and terrain revision; recheck dynamic occupancy separately. Use HISM overlap/spatial-index candidates and only tree trunks for the preview count; omit poof/plant output allocations and routine logs in dry runs. Budget AI candidate search over ticks, throttle preview work with latest-result replacement, and always perform a final authoritative validation when placing.

### 61S-18 — Full-resolution A* searches and duplicate route queries can accumulate in one game-thread decision

- **Area:** command/combat/AI frame spikes and search allocations.
- **Evidence:** `VLGrid.cpp:708–774` runs a synchronous heap-based search to completion and allocates `TSet Remaining` and a fresh heap (`730–732`). Group movement already shares one reverse search and visited-stamp arrays, which is good; it should not be replaced with one A* per group member. Individual melee chases still call `FindPath` (`VLSwordsmanCombat.cpp:483–497`); replans are jittered, but repeated. `VLAIWorld.cpp:62–81` computes full routes for distance estimates. A Hard raid explicitly computes the exact same direct route twice (`VLAISquads.cpp:1221,1224`) and then two more paths per flank candidate (`1232`); `RouteDefence` also pathfinds during target evaluation (`VLEnemyAI.cpp:460–465`).
- **Estimated impact:** **Medium–High spikes** on long routes/large decisions. At 60 chasing swordsmen with a nominal 0.6 s replan interval, the potential request rate is about 100 path searches/second; actual chasing/gating lowers this. Duplicate direct-route elimination saves one full search per qualifying raid evaluation immediately.
- **Effort:** Low for duplicate reuse; Medium–High for budgeting/hierarchy.
- **Risk:** Stale cached routes after building edits; budgeted replans can change responsiveness.
- **Recommended fix:** use the return length from the first raid query; cache route geometry/length by quantized endpoints plus navigation revision, separately from influence risk which changes more often. Reuse scratch storage, add a per-frame search/expansion budget, and use a coarser portal/chunk graph for strategic routes with fine-grid refinement near obstacles. Preserve shared group searches and invalidate affected caches on navigation edits.

### 61S-19 — Full-detail custom depth remains enabled for every unit, even while title silhouettes are muted

- **Area:** GPU geometry/custom-depth bandwidth; title-screen power.
- **Evidence:** `VLKing.cpp:227–234,308–311` writes all unit mesh parts into custom depth with team stencil 1/2. The silhouette post effect samples scene/custom depth and stencil across the image (`Tools/ue/build_special_materials.py:349–379`). Title handling only sets blendable weight to zero (`VLHUD.cpp:541–553`), while every part remains flagged to render custom depth. Title camera covers approximately the entire map at 1.6× map width and drifts continuously (`VLHUD.cpp:525–528`, `VLKing.cpp:1680–1687`).
- **Estimated impact:** **Medium** pass reduction, increasingly important with army count/resolution. Main-menu scene still pays applicable unit depth rendering even though the effect is unused; movement/shadow/lighting renders also continue. Exact pass cost needs GPU capture.
- **Effort:** Low for title toggling; Medium for proxy/zoom tiers.
- **Risk:** Simply disabling enemy depth during play changes the intended unit-vs-unit occlusion rule; do not do that. Silhouette should not become visible through other units.
- **Recommended fix:** disable custom-depth rendering on all unit parts while the title effect is suppressed and restore it on gameplay transition. For gameplay use simplified per-unit proxies at distant zoom while retaining both team stencil semantics. Consider a lower-quality/capped or prerecorded title backdrop as an optional power-saving path, and avoid full pose/cosmetic updates behind menus.

### 61S-20 — Lantern lighting scales to over a hundred dynamic lights, including volumetric contribution

- **Area:** deferred lighting/fog GPU work.
- **Evidence:** `Tools/ue/build_level.py:241–257` spawns one stationary PointLight for each qualifying glow cluster, with up to **480 cm** attenuation radius (`P` at line 50), no shadows, and volumetric scattering **0.6**. `build_realm.py:227` / `build_highland.py:224` call this per placed instance. Applying the generator's `vol>=0.004` threshold to current layout/mesh metadata yields **122 / 154** lights respectively. These are generated-input counts, not a live actor dump; rebuild logs may reflect older layouts. Spy also has a local lantern, but there are at most a few Spies.
- **Estimated impact:** **Medium** potential in broad/low views and fog volumes. Shadows are already disabled, so shadow-map savings must not be claimed here; lights are small and engine light culling limits cost.
- **Effort:** Low–Medium.
- **Risk:** Visual loss of lantern pools and night/fog atmosphere.
- **Recommended fix:** add quality/distance-based maximum draw distance/fades for actual light sources; keep distant emissive lantern geometry. Set negligible small-light volumetric scattering to zero where visually acceptable, merge very nearby glow sources, and use high-quality lights only in the near view. Compare lighting/fog pass GPU timings at fixed camera angles.

### 61S-21 — Cosmetic motes/smoke and dust update instances on the CPU without visibility significance

- **Area:** game/render-thread cosmetic work and transient render-state rebuilds.
- **Evidence:** `VLAmbience.cpp:68–115` loops all mote/smoke instances every frame, recomputes hashes/trigonometry, writes transforms individually, and dirties component render state on the last instance; no view/distance gate. `VLAmbience.h:35,44` defaults to 7 motes/centre and 9 puffs/chimney. `VLFootDust.cpp:76–107` updates active puffs and calls `MarkRenderStateDirty()` every active frame. Forest dust is pooled/shared and actor ticking correctly turns off after the effect (`VLForest.cpp:81–90`); ordinary troop foot dust is already disabled, so there is no basis to claim 40 active dust puffs per troop.
- **Estimated impact:** **Medium** for large maps/cosmetic-heavy frames, lower than core unit rendering. CPU math and transform uploads remain even for invisible swarms. The ISM render-state dirty path warrants a trace to establish actual proxy/update cost in UE 5.8.
- **Effort:** Medium.
- **Risk:** Cosmetic phase/popping changes; bounds must include shader-displaced particles for correct culling.
- **Recommended fix:** move deterministic smoke/mote motion to GPU instance custom data + shader animation or Niagara; use world chunks and distance significance. If staying CPU-based, precompute immutable hashes, update lower-rate distant effects, batch transform updates with supported instance-data APIs, and avoid a full render-state recreation where a data update suffices. Keep the existing shared pool and inactive early-outs.

### 61S-22 — Far-unit HUD markers are rasterized as many one-pixel Canvas rectangles

- **Area:** HUD game-thread primitive construction/submission.
- **Evidence:** `VLHUD.cpp:1175–1218` iterates all troops for far pips and builds each rim/diamond using two `dy` loops, one `Fill` call per scanline. At UI scale 1, default S=4 and rim half-height about 5.5 produce roughly **21 Fill calls/unit**, about 4,200 for 200 visible units each frame; higher UI scales increase this. Selection/range/route rendering separately scans units and projects ring endpoints (`1280–1290,1329–1338,1374–1380`); rings already cache ground points, cap displayed units at 12, and do not perform trace-per-point ground queries (`GroundZ`, `860–869`).
- **Estimated impact:** **Medium CPU** in large overview battles; Canvas can batch rectangles, so 4,200 Fill calls are not necessarily 4,200 GPU draw calls. Static HUD strings/panels also rebuild each frame, but no measured ranking puts them ahead of world rendering.
- **Effort:** Low for pip geometry; Medium for shared snapshots/caching.
- **Risk:** Low visual risk; preserve screen-space scale, selection colours and clipping.
- **Recommended fix:** draw a pip as one textured quad or a few triangles with its rim, and batch markers by texture/material. Build one live/visible unit snapshot and project each unit once for bars/pips/tags, reject offscreen markers, and cache slow-changing labels/layout. Keep animated health/fades responsive and the existing ring limits.

### 61S-23 — Muted music still synchronously loads every track and starts a playlist

- **Area:** startup I/O, audio resources and memory residency.
- **Evidence:** `VLGameMode.cpp:868,878–886` forces music off but `LoadObject`s all eight tracks synchronously and invokes `NextSong`. `930–948` creates/starts music at zero/nearly zero volume; `1059–1061` advances the playlist whenever it is no longer playing. The importer correctly assigns `RETAIN_ON_LOAD` (`Tools/ue/import_audio.py:56–60`), which retains a stream chunk, not necessarily the entire decoded song. Source WAVs total **363.98 MiB**; the eight `.uasset` source files total approximately 230.3 MiB. Neither number is an established runtime/cooked music footprint.
- **Estimated impact:** **Medium startup**, **Low–Medium runtime**: eight synchronous asset loads, retained audio resource metadata/chunks, and possibly silent playback work even when the default setting is off. UE virtualization may suppress silent voice work; a memory/audio capture is needed to quantify that part.
- **Effort:** Low–Medium.
- **Risk:** Avoid audible startup latency when the user enables music; preserve pause/menu playback and song transitions.
- **Recommended fix:** store soft track references; do not create/advance music while the music setting is off. Asynchronously preload the selected/next song and release old references/chunks as appropriate. Inspect actual SoundWave codec, quality, chunk sizes and cooked payload before changing compression; keep long tracks streamed and use measured listening tests to choose quality.

### 61S-24 — A blanket always-cook rule includes prototypes and source LOD meshes without a runtime manifest

- **Area:** package size/cook time/content maintenance.
- **Evidence:** `Config/DefaultGame.ini:6` forces **all `/Game/Voxel`** into the cook, in addition to all five maps (`7–11`). `Tools/ue/import_assets.py:165` imports every source glTF by default, while runtime unit assets use a separate dedicated import path. Current generic `Content/Voxel/Meshes/SM_King*.uasset` files total **13.03 MiB across 30 files**, while active KingB has dedicated `Content/Voxel/King` parts (`import_king.py:19,25`); eight standalone tree `_L1` import-source assets total another **1.16 MiB**. Those source sizes only bound candidates: confirm actual references/cooked bytes before removing any. Runtime assets also load by constructed strings (e.g. `VLTroop.cpp:35–38`, enemy twins in `VLKing.cpp:204–215`, sounds), so ordinary reference-only cooking is insufficient without explicit roots.
- **Estimated impact:** **Medium cumulative**, immediately identifiable dead/prototype candidates over 14 MiB in source assets; total cooked saving unknown. Sandbox maps are intentionally selectable, so removing them would be a product scope change rather than a free optimization.
- **Effort:** Medium.
- **Risk:** Missing cooked troop kinds, enemy material twins, UI/sounds or dynamically constructed building assets.
- **Recommended fix:** create an explicit Primary Asset/asset-label cook manifest for runtime dynamically loaded resources, retain intended maps, then remove blanket directory cooking and exclude verified prototypes/intermediate LOD-source meshes. Use cooked asset-size reporting/IoStore listing to prioritize actual shipped contributors and launch every map/train every kind in a clean packaged build.

## Coverage notes and validation priorities

- **Already optimized:** forest HISM, a tree LOD and reduced plant LODs, grass/flower WPO disable distance, disabled crown distance-field participation, no shadows on tiny grass/flowers/lilies, shared arrow pooling, throttled auto combat/AI, pooled dust and inactive early-outs, cached/limited range circles, ordinary troop steps/dust disabled, and existing Lumen coarse-gather/global-SDF tuning. Preserve these.
- **Materials:** `M_Voxel` is a small texture/vertex-colour material; `M_VoxUnit` adds colour swapping, and `M_VoxSway` WPO is more relevant when applied to high vertex counts. The water builder (`build_special_materials.py:119–145`) makes animated texture/glint/roughness output without enabling translucent blending; do not label the current water a proven translucent-overdraw problem. Flash overlays add temporary mesh work (`VLKing.cpp:2295–2301`) but are conditional; mesh/section reduction addresses their multiplicative cost too. Tiny world textures are not the main memory opportunity.
- **Shadows:** config enables VSM; generators set `dynamic_shadow_distance_movable_light=110000` (`build_realm.py:148–152`, Highlands equivalent). That is a CSM-associated property and is not evidence by itself of a 1,100 m VSM cache/render cost. UE's local `Engine/Source/Runtime/Engine/Private/Components/DirectionalLightComponent.cpp:510–516` explicitly bypasses cascade-distance fading for VSM. Measure actual VSM clipmaps/page allocations/invalidation before tuning; do not assume reducing that one property fixes VSM cost. Leaf crown WPO is already off by default (`build_special_materials.py:385–387`); avoid reintroducing its documented shadow redraw cost.
- **AI:** the influence grid uses 10 m cells (`VLEnemyAI.cpp:601`) and local-radius stamps (`920–948`), making it much smaller than the path grid. No evidence makes influence-map arithmetic the first optimization target; repeated pathfinding, perception candidates and allocations are stronger opportunities. Keep fairness/sighting restrictions when optimizing.
- **Package:** the 958 MiB game container is already compressed, and 62.52 MiB is alignment padding. Investigate block/alignment changes only after platform streaming benchmarks; this audit does not recommend disabling alignment blindly. Shader formats, dependency closure, release configuration and content roots offer safer first reductions. Texture source sizes and WAV sizes must not be substituted for cooked per-asset attribution.
- **Next controlled profile:** benchmark a packaged Development build with fixed render resolution/quality at hero, home overview, centre overview and max zoom on both battle maps; include idle/marching/fighting at 20/100/200 units and a separate 80-arrow stress case. Record game/render/GPU times, p50/p95/p99 frame times, draw/section/triangle counts, VSM invalidations, memory and cold startup time; capture construction/clearing and first overview separately. Compare one change at a time. Then validate Shipping separately, with music kept off unless testing the audio change.
