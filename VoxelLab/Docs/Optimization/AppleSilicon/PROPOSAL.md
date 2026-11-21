# Apple Silicon & Metal Performance Audit — VoxelLab (UE 5.8.4)

**Project:** `VoxelLab` (Unreal Engine 5.8.4 Installed Engine, C++ voxel RTS)  
**Target hardware:** Apple Silicon Macs (M1–M5 family, Metal SM6, TBDR GPUs, unified memory, P/E-core CPUs, ProMotion/VRR laptops & desktops)  
**Baseline host:** Apple M5 Pro (18 cores: 6 P-cores + 12 E-cores), 24 GB unified memory, macOS 27.2.1, Apple Clang 21.0.0  
**Rule:** The default **High** look and gameplay behaviour stay identical unless explicitly flagged below. No live project files were modified; every actionable change is provided as a standalone, file-disjoint patch in this directory.

---

## 1. Baseline & Scope (What Is Already Done)

The 2026-11-21 optimization pass (`Docs/Optimization/PLAN.md`, `README.md` § Performance) already landed major cross-platform and initial Mac wins, bringing a 100v100 battle (PIE, 3224×1660) on M5 Pro to:

- **L_Realm battle, overview 0.45:** `9.2 ms GT / 19.7 ms GPU / 38.0 fps` (down from `32.7 / 28.4 ms / 28.8 fps`)
- **L_Realm battle, far overview 1.0:** `7.4 ms GT / 20.5 ms GPU / 46.7 fps` (down from `36.6 / 37.1 ms / 24.7 fps`)
- **L_Highlands battle, overview 0.45:** `17.5 ms GT / 19.0 ms GPU / 48.1 fps` (down from `30.2 / 31.4 ms / 31.9 fps`)
- **Packaged Shipping app (`Builds/Mac/VoxelLab.app`):** `1,062 MB` (`VoxelLab-Mac.ucas` 816 MB, stripped arm64 executable 166 MB, `libmetalirconverter.dylib` 56 MB)

Already done and **not** re-proposed here: Metal SM6-only (`-TargetedRHIs=SF_METAL_SM5`), `r.TSR.History.ScreenPercentage=100`, `r.IndirectLightingCache=0`, `r.Lumen.ScreenProbeGather.DownsampleFactor=32`, `r.Lumen.TraceMeshSDFs=0`, `r.Shadow.Virtual.UseReceiverMaskDirectional=0`, `NNEDenoiser`/`NNERuntimeORT` disabled, Shipping strip & re-sign, `UVLGraphics` Low/Medium/High + RenderScale + far-fog coarsening, `VLKingRig` batched poses + LOD + custom-depth gating, `UVLBattle` spatial hash, `VLGrid` `ParallelFor`, and mesh LODs.

This audit targets **Apple Silicon and Metal specifics** uncovered directly against UE 5.8.4's Mac/Metal source and `VoxelLab`'s cooked shader stats (`Saved/Cooked/Mac/VoxelLab/Metadata/ShaderTypeStats-METAL_SM6.csv`).

---

## 2. Ranked Proposals (Ordered by Value)

### Summary Matrix

| Rank | Item | Focus Area | Expected Gain | Risk (High Look / Behaviour) | Effort | Recommendation | Patch |
|---:|---|---|---|---|---|---|---|
| **1** | TBDR GPU wins: disable unused `TranslucencyLightingVolume`, cap Lumen reflection roughness (`0.55`), disable runtime Nanite + DBuffer to remove forced full depth prepass | TBDR / Lighting / Metal | **~2.0–3.2 ms GPU** (10–16% at 19–20 ms) + eliminates redundant vertex pass | Low (verify water/gold reflections & fog) | Low | **Apply with testing** | `01`, `02` |
| **2** | Native MetalRHI Dynamic Resolution + TSR (`Target 60 / 40 / 30 fps`) in `VLGraphics.*` | Upscaling / VRR / Settings | **Locks 60 or 40 fps** under heavy battles/zooms without manual scale tweaking; **20–40% GPU** during spikes | Low (opt-in; default **Off** preserves High 1:1) | Low–Med | **Apply now** | `04` |
| **3** | Metal PSO precaching (`METAL_SM6` manager entry + `r.PSOPrecache.*`) & MetalRHI driver fixes (`ResourcePurgeOnDelete=0` UE 5.8 bug, `PersistentMappingMetallib=1`) | Metal RHI / Hitches | **Eliminates 15–80 ms first-sight PSO hitches**; removes per-allocation `setPurgeableState()` kernel calls | Very Low | Low | **Apply now** | `01` |
| **4** | Prune unused SM6 shader features (`RayTracing`, `MegaLights`, `DBuffer`), Metal 3.0 shader target (`MetalLanguageVersion=8`), and `StripIndividualMetalLibs=True` | Metal Shaders / Cook / Size | **~45–55 MB less uncompressed shaders** (~20–35 MB smaller `.ucas`), faster cooks & smaller PSO load | Very Low | Low | **Apply now** | `01` |
| **5** | Apple Silicon CPU threading: lift UE's 4-worker game cap with P/E-core sizing (`FScheduler::RestartWorkers`) + XNU `QOS_CLASS_USER_INTERACTIVE` on Game/Render/RHI threads | CPU / P-E Cores | **2–4× parallel throughput** (`VLGrid`, culling, render prep); prevents XNU from migrating Game/Render/RHI onto E-cores under thermal load | Low (`!GIsEditor` guard + runtime toggle cvars) | Low | **Apply with testing** | `05` |
| **6** | ProMotion 40 fps cap (`120 Hz / 3`), macOS `NSProcessInfo` thermal & Low Power Mode guard, and menu/unfocused throttling | Frame Pacing / Thermal / Battery | **Smooth 3-refresh ProMotion pacing**; **40–65% lower idle/menu power**; avoids sudden thermal clock collapse on fanless MacBook Air | Low (default 60 fps cap unchanged; thermal guard triggers only at Serious/Critical or Low Power Mode) | Low–Med | **Apply now** | `04` |
| **7** | 32-bit HDR SceneColor (`r.SceneColorFormat=2`, `PF_FloatR11G11B10`) on Apple Silicon TBDR | TBDR Bandwidth | **~0.8–1.8 ms GPU** (halves SceneColor tile/DRAM traffic) | **Medium (visual flag!)** — check sky & volumetric fog for subtle colour banding | Low | **Apply with testing** | `02` |
| **8** | Unified-memory pool budgets (`PoolSizeVRAMPercentage=0`, `r.Streaming.PoolSize=256`, VSM `MaxPhysicalPages=2048` High / `1024` Med-Low) | Unified Memory | **~128–256 MB lower GPU residency** (VSM) + sane streaming ceiling on 8–16 GB Macs | Very Low (only 1 shadow-casting sun; ~0.5 MB textures) | Low | **Apply now** | `01`, `02`, `04` |
| **9** | Strict arm64-only Mac build/package flags + Shipping ThinLTO (`bAllowLTCG=true`) | Build / Package | Prevents accidental x86_64 universal fat builds; **~2–5% CPU** in `VoxelLab` hot loops via cross-TU inlining | Very Low (compile & ThinLTO link verified) | Low | **Apply with testing** | `03` |
| **10** | ARM64 game-thread micro-hotspots (`AVLKing::PoseFigure` redundant `Cos`/`Pow`, `UpdateCape` invariant `Exp`/division hoisting) | ARM64 CPU | **~0.1–0.3 ms GT** at 200 active units (eliminates 600–2,000 transcendental calls/frame) | Very Low (algebraically identical) | Low | **Apply now** | `05` |
| **11** | TBDR depth-prepass experiment (`r.EarlyZPass=1` vs `0` + `r.VelocityOutputPass=1`) | TBDR / Metal | **0–1.5 ms GPU** (scene-dependent: HSR vs overdraw/shadow/TSR velocity) | Medium (can regress GPU in heavy foliage/overdraw) | Low | **Apply with testing** (manual CVar A/B, not patched) | — |
| **12** | Custom MetalFX Temporal / Spatial Upscaler plugin (`MTLFXTemporalScaler` / `MTLFXSpatialScaler`) | MetalFX vs TSR | **~1–2 ms GPU** vs TSR (Temporal); Spatial regresses voxel-edge AA | High (no UE 5.8 built-in plugin; Spatial shimmers on high-contrast voxel edges) | High | **Skip** (for now; use TSR + DynRes first) | — |
| **13** | PGO (Profile-Guided Optimization), `-ffp-contract=fast`, `UseFastIntrinsics=True`, and `MinArm64CpuTarget` | Build / Compiler | Minimal on Installed Engine (Engine `.o` files are prebuilt; `-ffp-contract=off` is UBT-hardcoded for DDC determinism) | Medium–High (NaN/INF shader bugs with `UseFastIntrinsics`; breaks UE DDC determinism) | High | **Skip** | — |
| **14** | Keep `NSHighResolutionCapable=false` vs Retina 2× backing store & `SM6` M1 OS floor (`macOS 15+` vs `14.00`) | Metal RHI / Packaging | Documents an existing ~2.5–3× GPU saving and prevents M1 macOS 14 crash surprise | Info / release-matrix check | Low | **Document / Keep** | — |
| **15** | Deferred items reviewed for Apple Silicon (Memoryless targets, `r.Lumen.TranslucencyVolume.Enable=0`, `VLHUD` `Lin()` LUT, `libmetalirconverter.dylib`) | Architecture Notes | Clarifies UE 5.8 Mac constraints so effort isn't wasted | N/A | N/A | **Skip / Optional** | — |

---

### Detailed Item Breakdown

#### Rank 1 — TBDR GPU Wins: `TranslucencyLightingVolume=0`, Lumen Reflection Roughness Cap, and Removing Forced Nanite/DBuffer PrePass
- **Patches:** `01-mac-metal-target-and-shaders.patch` (`r.DBuffer=False`), `02-tbdr-lighting-and-bandwidth.patch` (`Config/Mac/MacDeviceProfiles.ini`)
- **What & Why on Apple Silicon:**
  1. **`r.TranslucencyLightingVolume=0`:** Every world material in `VoxelLab` (including water) is Opaque or Masked; the sole translucent material (`M_PlacementGhost`) is Unlit and ignores the translucency lighting volume. Previous `ProfileGPU` captures (`Docs/Optimization/findings_opus55.md`) measured `TranslucencyVolumeLighting` at **1.34 ms GPU** on M5 Pro. On TBDR GPUs, computing and writing 3D volume cascades wastes both compute ALU and unified-memory bandwidth for zero visible pixels.
  2. **`r.Lumen.Reflections.MaxRoughnessToTrace=0.55` (High) + `r.Lumen.Reflections.DownsampleFactor=2` (Medium/Low):** Almost all voxel surfaces (terrain, stone, wood, foliage, cloth) have roughness `0.85–0.95`. Only water (`0.15`), gold (`0.42`), metal (`0.50`), and windows (`0.50`) need dedicated Lumen reflection rays. Capping trace roughness at `0.55` preserves every glossy reflection on High while skipping wasted rays across matte voxel blocks.
  3. **`r.Nanite=0` (runtime) + `r.DBuffer=False`:** `ProfileGPU` previously showed `PrePass ... (Forced by Nanite)` costing **0.65–0.75 ms**. Apple Silicon GPUs implement hardware Hidden Surface Removal (HSR) inside on-chip tile memory, sorting opaque fragments front-to-back *before* running pixel shaders — meaning a full opaque depth prepass often duplicates vertex shading and tiler parameter-buffer traffic needlessly on opaque voxel scenes.
     > **Critical UE 5.8.4 Engine Trap Verified in Source:** `Engine/Source/Runtime/RenderCore/Private/RenderUtils.cpp:1274,1504` makes `DoesPlatformSupportVirtualShadowMaps()` depend on `DoesPlatformSupportNanite()`, which reads `r.Nanite.ProjectEnabled`. **Do NOT set `r.Nanite.ProjectEnabled=0`** — doing so silently disables Virtual Shadow Maps! Setting runtime `r.Nanite=0` in `MacDeviceProfiles.ini` (`ECVF_Scalability`) keeps VSM fully active while clearing the Nanite forced-prepass trigger, and `r.DBuffer=False` clears the DBuffer forced-prepass trigger (and drops decal base-pass fetches).
- **Expected Gain:** **~2.0–3.2 ms GPU** on High (1.34 ms from `TranslucencyLightingVolume=0` + 0.4–1.0 ms from reflection roughness cap + 0.3–0.8 ms from dropping forced PrePass/DBuffer base-pass work), plus an extra **~0.5–1.0 ms** on Medium/Low from `r.Lumen.Reflections.DownsampleFactor=2`.
- **Risk to Look & Behaviour:** **Low.** Default High visuals stay identical (water, gold, metal, and windows remain below 0.55 roughness; `r.Lumen.TranslucencyVolume.Enable` remains `1` so `VolumetricFog` keeps its Lumen indirect bounce). Verify with before/after screenshots on `L_Realm` (river + gold roofs + fog).
- **Effort:** Low (config-only).
- **Recommendation:** **Apply with testing** (A/B `ProfileGPU` + screenshot check on `L_Realm` and `L_Highlands`).

---

#### Rank 2 — Native MetalRHI Dynamic Resolution + TSR (`Target 60 / 40 / 30 fps`) in `VLGraphics.*`
- **Patch:** `04-mac-graphics-vrr-thermal.patch` (`VLGraphics.h/.cpp`, `VLHUD.h/.cpp`, `VLHUDMenus.cpp`)
- **What & Why on Apple Silicon:** Verified in UE 5.8.4 `MetalRHI.cpp:405,531`: MetalRHI natively sets `GRHISupportsDynamicResolution = true` and `GSupportsTimestampRenderQueries = true`, driving UE's closed-loop GPU frame-time heuristic directly into TSR without any external plugin. Because M-series GPU budgets vary wildly across M1 (7–8 core GPU) through M5 Pro/Max — and because `VoxelLab`'s GPU time swings from ~16.8 ms (hero start) to ~20.5 ms (far overview battle) — a fixed `RenderScale` either wastes sharpness in calm moments or drops below 60 / 40 fps during 100v100 clashes.
  - Exposes **Dynamic resolution** in `Esc > Settings > GRAPHICS` (`Off`, `Target 60 fps` = 16.6 ms budget, `Target 40 fps` = 25.0 ms budget, `Target 30 fps` = 33.3 ms budget) and console command `vl.Gfx.DynRes 0|1|2|3`.
  - Respects the player's `RenderScale` as the upper ceiling (`MaxScreenPercentage`), with a `50%` floor (`MinScreenPercentage`), and persists cleanly in `GameUserSettings.ini`.
- **Expected Gain:** **20–40% GPU savings during heavy battles/zooms** (automatically holding 60 fps on M3/M4/M5 Pro or 40 fps on base M1/M2/M3 without dropping quality presets).
- **Risk to Look & Behaviour:** **Low.** Defaults to `Off`, so out-of-the-box **High** look is 100% untouched. When enabled, TSR temporally smooths resolution transitions cleanly on voxel edges.
- **Effort:** Low–Medium (already implemented and compile-verified in Patch 04).
- **Recommendation:** **Apply now.**

---

#### Rank 3 — Metal PSO Precaching (`METAL_SM6`) & MetalRHI Driver Overhead Fixes
- **Patch:** `01-mac-metal-target-and-shaders.patch` (`Config/Mac/MacEngine.ini`)
- **What & Why on Apple Silicon:**
  1. **Missing `METAL_SM6` PSO precache entry:** `BaseEngine.ini`'s `[/Script/Engine.PSOPrecacheSettingsManager]` defines entries for `PCD3D_SM6` and mobile `ES3_1`, but has **no entry for `METAL_SM6`**. Furthermore, `Saved/Cooked/Mac/VoxelLab/Metadata/PipelineCaches/` is currently empty. When a new unit type, archer volley, placement ghost, or building enters view for the first time, Metal compiles the `MTLRenderPipelineState` synchronously on the RHI/driver thread, causing 15–80 ms hitches. Patch 01 registers `ShaderPlatform="METAL_SM6"` (`MaxCPUThreadCount=255, GlobalShaderMode=1`) and enables `r.PSOPrecaching=1`, `r.PSOPrecache.GlobalShaders=1`, `r.PSOPrecache.ProxyCreationStrategy=1` (delay proxy creation until precache finishes rather than hitching mid-frame), and bounded retention (`KeepInMemoryUntilUsed=1`, `2048` graphics / `512` compute PSOs).
  2. **UE 5.8.4 `rhi.Metal.ResourcePurgeOnDelete` bug:** Verified in `Engine/Source/Runtime/Apple/MetalRHI/Private/MetalDevice.cpp:60`: `GMetalResourcePurgeOnDelete` is initialized to **`1`** even though its own CVar help text says `(Default: 0, Off)`. Every transient non-heap texture/buffer creation and destruction calls `[resource setPurgeableState:]` into the Metal driver/kernel. Setting `rhi.Metal.ResourcePurgeOnDelete=0` eliminates this overhead on macOS.
  3. **`r.Metal.PersistentMappingMetallib=1`:** Defaults to `0` (`MetalShaderLibrary.cpp:20`), causing repeated `mmap`/`munmap` calls when paging shader libraries on unified memory.
  4. **Already-optimal MetalRHI defaults in UE 5.8 (verified, no patch needed):** `r.Metal.Parallel=1`, `rhi.Metal.ConcurrentDispatch=1`, `rhi.Metal.UseEventForGPUFence=1`, `rhi.Metal.CacheShaderPipelines=1`, and `rhi.Metal.RuntimeDebugLevel=0` (Shipping).
  5. **Note on `-MetalPSOCache=append` (`MTLBinaryArchive`):** Binary archives are compiled GPU-ISA blobs tied to exact Apple GPU family + macOS build version; they are useful as a per-user local cache on disk (Metal already maintains a system shader cache in `~/Library/Caches`), but **cannot** be shipped inside `VoxelLab.app` across M1–M5 Macs or OS updates. Bundled precaching must rely on UE's logical `r.PSOPrecaching` + optional collected `.rec.upipelinecache` (FShaderPipelineCache) per release if first-launch hitches remain.
- **Expected Gain:** Eliminates **15–80 ms first-sight gameplay hitches**; saves **~0.2–0.5 ms RHI/RenderThread CPU** from removing `setPurgeableState()` churn and repeated metallib remaps.
- **Risk to Look & Behaviour:** **Very Low.** Zero visual change. Slight increase in initial map-load CPU work while PSOs compile in parallel on background cores (typically 100–300 ms once per cold OS cache).
- **Effort:** Low (config-only).
- **Recommendation:** **Apply now.**

---

#### Rank 4 — Prune Unused SM6 Shaders (`RayTracing`, `MegaLights`, `DBuffer`), Metal 3.0 Target, and Metallib Stripping
- **Patch:** `01-mac-metal-target-and-shaders.patch` (`Config/DefaultEngine.ini`, `Config/Mac/MacEngine.ini`)
- **What & Why on Apple Silicon:** Inspecting the actual cooked `Saved/Cooked/Mac/VoxelLab/Metadata/ShaderTypeStats-METAL_SM6.csv` (**11,904 shaders, 179.50 MB uncompressed / 98.99 MB compressed**) revealed massive unused shader payloads:
  - **Hardware Ray Tracing (`BaseEngine.ini` defaults `bEnableRayTracing=True`, `RayTracingMode=Full`):** Cooks **1,243 unused RT shaders (23.70 MB uncompressed)** — including `FHardwareRayTraceLightSamplesCS` (10.27 MB) and `FLumenReflectionHardwareRayTracingCS` (5.98 MB). Setting `bEnableRayTracing=False` and `RayTracingMode=Disabled` in `MacEngine.ini` strips them cleanly.
  - **MegaLights (`r.MegaLights.Supported` defaults `True` in `RenderUtils.cpp:2645`):** Cooks `FShadeLightSamplesCS` (9.57 MB), `FGenerateLightSamplesCS` (7.95 MB), `FHardwareRayTraceLightSamplesCS` (10.27 MB), and 37 `MegaLights*` shaders (0.89 MB) — **~28 MB uncompressed total** (overlapping 10.27 MB with HWRT above, so **~18.4 MB additional** net). Setting `r.MegaLights.Supported=False` in `DefaultEngine.ini` omits them at cook time (note: `r.MegaLights.Allowed` is runtime-only and does *not* prune shaders!).
  - **DBuffer Decals (`r.DBuffer=False`):** VoxelLab places zero decals; disabling DBuffer removes **107 decal/DBuffer shaders (~1.0 MB)** and removes DBuffer sampling from opaque base-pass pixel shaders.
  - **Metal 3.0 Shader Standard (`MetalLanguageVersion=8` = `MacMetalSLStandard_3_0`):** UE 5.8 defaults Mac to `7` (Metal 2.4 / macOS 12). Raising to `8` (Metal 3.0 / macOS 13+, well below the app's `LSMinimumSystemVersion=14.00`) lets Apple's offline `metal` compiler emit Metal 3 IR/optimizations.
  - **`StripIndividualMetalLibs=True`:** Runs `metal-strip -T` on individual `.metallib` archives during cook to strip unused symbol/reflection metadata.
- **Expected Gain:** **~43–45 MB less uncompressed shader data** (~20–35 MB smaller `VoxelLab-Mac.ucas`), **15–25% faster shader cook**, smaller runtime shader-library memory footprint, and slightly cleaner base-pass shaders.
- **Risk to Look & Behaviour:** **Very Low.** None of HWRT, MegaLights, or DBuffer decals are used anywhere in `VoxelLab`. Requires a recook to realize size savings.
- **Effort:** Low (config-only).
- **Recommendation:** **Apply now.**

---

#### Rank 5 — Apple Silicon CPU Threading: P/E-Core Worker Scaling & XNU Thread QoS
- **Patch:** `05-arm64-cpu-qos-and-hotspots.patch` (`Source/VoxelLab/VoxelLab.cpp`)
- **What & Why on Apple Silicon:**
  1. **UE 5.8's hardcoded 4-worker cap on packaged Mac games:** `FMacPlatformMisc` does not override `FGenericPlatformMisc::NumberOfWorkerThreadsToSpawn()`, which caps `MaxGameThreads = 4` (`2` foreground + `2` background workers) in standalone/Shipping games — even on an 18-core M5 Pro (6P + 12E) or 10–16 core M-series Pro/Max! `VLGrid`'s `ParallelFor`, visibility culling, PSO precaching, and async render prep are all throttled to 4 workers in `Builds/Mac/VoxelLab.app` (whereas PIE in the Editor gets up to 26 workers, masking this bug during Editor profiling!).
  2. **Missing XNU QoS classes:** UE 5.8's Mac `FRunnableThreadPThread` calls `pthread_setschedparam()` but **never** calls `pthread_set_qos_class_self_np()`. On Apple Silicon macOS, XNU's asymmetric scheduler uses QoS classes—not POSIX priority alone—to decide P-core vs E-core placement. Without `QOS_CLASS_USER_INTERACTIVE`, sustained GPU/thermal pressure can demote the GameThread, RenderThread, or RHIThread onto E-cores, causing sudden 2× CPU frame-time spikes.
  3. **Fix in `FVoxelLabModule`:** On first world init, promotes GameThread, RenderThread, and RHIThread to `QOS_CLASS_USER_INTERACTIVE`. In standalone Game/Shipping runs (`!GIsEditor && IsRunningGame()`), queries `sysctlbyname("hw.perflevel0.physicalcpu")` (P-cores) and `hw.perflevel1.physicalcpu` (E-cores) and calls `LowLevelTasks::FScheduler::Get().RestartWorkers(FG, BG)` with `FG = clamp(PCores - 2, 2, 6)` and `BG = clamp(ECores, 2, 8)` (leaving 2 P-cores dedicated to Game/Render/RHI). Guarded by `vl.Opt.MacWorkers` and `vl.Opt.MacQoS` for instant A/B testing.
- **Expected Gain:** **2–3× faster parallel map/path-grid builds in Shipping** (e.g., `L_Highlands` path grid back to PIE-equivalent speed), smoother PSO background compilation, and elimination of E-core demotion stutters on MacBooks under sustained play.
- **Risk to Look & Behaviour:** **Low.** Strictly skipped in Editor/PIE (`!GIsEditor`) so editor worker pools are untouched. Calling `RestartWorkers` at `OnPostWorldInitialization` occurs once during startup before gameplay ticks; verify clean startup/shutdown on packaged `Development` and `Shipping` builds.
- **Effort:** Low (already implemented and compile-verified in Patch 05).
- **Recommendation:** **Apply with testing** (verify `apple-silicon: workers ...` log line and `L_Highlands` match load + Instruments Thread State trace in a packaged Development build).

---

#### Rank 6 — ProMotion 40 fps Cap, macOS Thermal / Low Power Mode Guard, and Idle/Menu Throttling
- **Patch:** `04-mac-graphics-vrr-thermal.patch` (`VLGraphics.h/.cpp`, `VLHUD.h/.cpp`, `VLHUDMenus.cpp`)
- **What & Why on Apple Silicon:**
  1. **ProMotion 120 Hz & 40 fps divisor:** MacBook Pro (14"/16") and Studio Display XDR panels run 120 Hz ProMotion. UE 5.8's `MetalViewport.cpp:1125` forces `displaySyncEnabled = YES` in windowed mode. When a heavy battle runs at 42–52 fps under a 60 fps cap, frames bounce unevenly between 16.7 ms and 33.3 ms (judder). Adding **40 fps** (`120 Hz / 3` = exact 25.0 ms cadence, cleanly synced on ProMotion) gives players on base M1–M4 or High quality a tear-free, rock-solid middle ground between 30 and 60 fps. Existing `FrameCap` configs migrate transparently to `FrameCapV2`.
  2. **macOS `NSProcessInfo` thermal & Low Power Mode awareness:** Verified in UE 5.8.4 Core source: `IOSPlatformMisc.cpp` implements `GetDeviceThermalState()` and `IsInLowPowerMode()` via `NSProcessInfo`, but `MacPlatformMisc.cpp` omits both! On fanless MacBook Airs or MacBook Pros on battery, running uncapped/60 fps until SoC thermal saturation causes abrupt clock throttling and loud fan spin. Patch 04 polls `[NSProcessInfo processInfo]` every 2 s (`#import <Foundation/NSProcessInfo.h>`, avoiding `<Foundation/Foundation.h>`'s CarbonCore `FVector` clash):
     - `NSProcessInfoThermalStateSerious` (2) or **Low Power Mode**: caps effective frame rate to `40 fps`.
     - `NSProcessInfoThermalStateCritical` (3): caps to `30 fps` and engages `Dyn30` dynamic resolution automatically until thermals recover.
  3. **Menu & Unfocused Throttling:** Revisits deferred item R-13 specifically for MacBooks (`vl.Opt.IdleThrottle=1`): lowers `t.MaxFPS` to `30 fps` on menu screens (`SetMenuThrottle(bMenu)`) and `15 fps` when the window is unfocused (`!FPlatformApplicationMisc::IsThisApplicationForeground()`). Unlike R-13's concern about in-game feel, pause/title menus remain responsive at 30 fps while cutting GPU wattage dramatically when the player Cmd-Tabs away or pauses.
- **Expected Gain:** Eliminates ProMotion judder on 40–55 fps workloads; **40–65% lower GPU power & heat** while paused or unfocused; sustained thermal stability on MacBook Air / battery play.
- **Risk to Look & Behaviour:** **Low.** Default user cap remains `60 fps`; thermal guard is dormant at `Nominal`/`Fair` thermal states; both guards have runtime disable cvars (`vl.Opt.ThermalGuard 0`, `vl.Opt.IdleThrottle 0`) and never activate in PIE (`!GIsEditor`).
- **Effort:** Low–Medium (already implemented and compile-verified in Patch 04).
- **Recommendation:** **Apply now.**

---

#### Rank 7 — 32-bit HDR SceneColor (`r.SceneColorFormat=2`, `PF_FloatR11G11B10`) on Apple Silicon TBDR
- **Patch:** `02-tbdr-lighting-and-bandwidth.patch` (`Config/Mac/MacDeviceProfiles.ini`)
- **What & Why on Apple Silicon:** UE 5.8 defaults `r.SceneColorFormat=4` (`PF_FloatRGBA`, 64 bits/pixel = 8 bytes/pixel). On a 3224×1660 framebuffer, every full-screen write/read of 64-bit SceneColor touches ~42.8 MB in unified memory — and TBDR tile memory (`32–64 KB/tile`) spills far earlier when GBuffer + 64-bit SceneColor compete for on-chip tile storage. Verified in `Engine/Source/Runtime/Apple/MetalRHI/Private/MetalRHI.cpp:1084`: UE 5.8 explicitly grants `TypedUAVLoad | TypedUAVStore` for `PF_FloatR11G11B10` (`r.SceneColorFormat=2`, 32 bits/pixel = 4 bytes/pixel) on Apple Silicon (`GRHISupportsAtomicUInt64`). Switching to `2` cuts SceneColor memory and tile bandwidth in half while keeping HDR range (no alpha channel is needed in deferred SceneColor).
- **Expected Gain:** **~0.8–1.8 ms GPU** (proportional to resolution; largest win at 100% RenderScale / high-res monitors and base M1–M3 memory bandwidth of 68–150 GB/s).
- **Risk to Look & Behaviour:** **Medium — explicit High visual check required.** `R11G11B10` has 6/6/5-bit mantissas (vs 10-bit in FP16) and drops SceneColor alpha. On smooth sky gradients or dense volumetric fog at dusk/low brightness, subtle colour banding or slight tint shifts can occasionally appear. Compare side-by-side screenshots against `r.SceneColorFormat=4` on `L_Realm` and `L_Highlands`; if any banding is visible, revert this single line in `MacDeviceProfiles.ini` to `4` (or move `2` into `UVLGraphics` Medium/Low only).
- **Effort:** Low (1 line in `MacDeviceProfiles.ini`).
- **Recommendation:** **Apply with testing** (mandatory visual A/B screenshot check).

---

#### Rank 8 — Unified-Memory Streaming Pool & VSM Physical Page Budgets
- **Patches:** `01-mac-metal-target-and-shaders.patch`, `02-tbdr-lighting-and-bandwidth.patch`, `04-mac-graphics-vrr-thermal.patch`
- **What & Why on Apple Silicon:**
  1. **Texture streaming pool:** `BaseMacEngine.ini` sets `PoolSizeVRAMPercentage=70`, which reserves 70% of macOS's recommended GPU working set (4–12 GB on 8–24 GB unified-memory Macs!). VoxelLab's textures are tiny (~0.5 MB total, mostly palette atlases and non-streaming UI textures). Setting `PoolSizeVRAMPercentage=0` and `r.Streaming.PoolSize=256` keeps memory accounting realistic and avoids over-allocating streaming budgets on 8–16 GB MacBooks where CPU and GPU share one physical RAM pool.
  2. **VSM physical page pool:** Defaults to `r.Shadow.Virtual.MaxPhysicalPages=4096` (~256–512 MB of 128×128 physical shadow pages + HZB). VoxelLab has **one** shadow-casting light (the directional sun; lamps do not cast shadows). Setting `2048` on High (`MacDeviceProfiles.ini`) and `1024` on Medium/Low (`VLGraphics.cpp`) saves **128–256 MB of unified memory** and improves L2/SLC cache hit rates during shadow projection.
- **Expected Gain:** **~128–256 MB lower unified-memory GPU residency** (prevents macOS memory compression / swap pressure on 8 GB M1/M2/M3 MacBook Airs) + minor L2 cache win (~0.1–0.3 ms GPU).
- **Risk to Look & Behaviour:** **Very Low.** Verify with `r.Shadow.Virtual.ShowStats 1` in a 100v100 battle that allocated physical pages stay well below 2048 (typically 400–900 for a single directional clipmap). If page overflow warnings ever occur on `L_Highlands` at extreme zoom, raise High to `2560`.
- **Effort:** Low.
- **Recommendation:** **Apply now.**

---

#### Rank 9 — Strict arm64-Only Build/Package Flags & Shipping ThinLTO
- **Patches:** `01-mac-metal-target-and-shaders.patch` (`MacEngine.ini`), `03-apple-silicon-build-flags.patch` (`Source/VoxelLab.Target.cs`, `Tools/package.sh`)
- **What & Why on Apple Silicon:**
  1. **arm64-only enforcement:** UE 5.8 defaults `TargetArchitecture=MacTargetArchitectureUniversal` and `bBuildAllSupportedOnBuildMachine=True`. While local dev builds happened to emit arm64, CI or Distribution builds can silently compile universal (`arm64 + x86_64`) fat binaries, doubling executable size and compile time. Locking `TargetArchitecture`, `EditorTargetArchitecture`, and `DefaultArchitecture` to `MacTargetArchitectureAppleSilicon`, `bBuildAllSupportedOnBuildMachine=False`, and passing `-specifiedarchitecture=arm64` in `Tools/package.sh` (verified in UE 5.8 UAT `ProjectParams.cs:1062` as the exact UAT flag) guarantees arm64-only builds everywhere.
  2. **Shipping ThinLTO (`bAllowLTCG = true` + `bOverrideBuildEnvironment = true`):** UE 5.8 defaults `bPreferThinLTO = true` on Mac. Because UE 5.8 Installed Engine ships precompiled native Mach-O arm64 Engine `.o` files (not LLVM bitcode), ThinLTO optimizes cross-translation-unit inlining and dead-code elimination across `VoxelLab`'s own ~30 C++ files without rebuilding the Engine. Note: `bAllowLTCG = true` flips `bDefineForceInlineHintToInline` internally, which requires `bOverrideBuildEnvironment = true` on an Installed Engine (verified by building & linking `VoxelLab Mac Shipping` cleanly in our isolated scratch copy).
- **Expected Gain:** Zero risk of accidental universal fat binaries; **~2–5% faster `VoxelLab` game-thread code** (cross-TU inlining across `VLKing`, `VLKingRig`, `VLBattle`, `VLGrid`, `VLHUD`); slightly smaller stripped game code section. Link time increases by ~10–25 s in Shipping only (Development/Editor untouched).
- **Risk to Look & Behaviour:** **Very Low.** Tested and verified to compile and link cleanly with Apple Clang 21 / ld64 on UE 5.8.4. (Because `bOverrideBuildEnvironment = true` bypasses UE's shared-environment check, verify `sh Tools/package.sh Shipping` succeeds end-to-end on the full project before committing.)
- **Effort:** Low.
- **Recommendation:** **Apply with testing** (run one `sh Tools/package.sh Shipping` build and smoke test).

---

#### Rank 10 — ARM64 Game-Thread Micro-Hotspots (`VLKing.cpp`)
- **Patch:** `05-arm64-cpu-qos-and-hotspots.patch` (`Source/VoxelLab/VLKing.cpp`)
- **What & Why on Apple Silicon:** Auditing `Source/VoxelLab` for ARM64 CPU costs (transcendentals, divisions, pointer chasing):
  1. `AVLKing::PoseFigure` computed `FMath::Cos(Phase + 0.3f)` **three times** per unit per posed frame and called `FMath::Pow(0.f, 1.2f)` unconditionally on whichever foot was grounded (plus both feet when standing still). Hoisting `LiftCos` and short-circuiting `Lift > 0 && LiftCos > 0` eliminates 2 `cosf` + 1–2 `powf` calls per unit per frame.
  2. `AVLKing::UpdateCape` recomputed `FMath::Exp(-AnimDt * 18.f)`, `FMath::Exp(-AnimDt * 10.f)`, and two divisions by `AnimDt` inside the `CapeCols × CapeRows` inner loop. Hoisting `InvDt`, `VelAlpha`, and `AccAlpha` out of the loop replaces repeated `expf`/FP-div with scalar FMULs.
  3. **Audited and skipped (`VLHUD.cpp`):** `Lin()` sRGB-to-linear `powf` is already hoisted outside the per-unit pip/healthbar inner loops (`RectLinear` at `VLHUD.cpp:1350`), so adding a LUT saves <0.01 ms and is not worth the complexity.
- **Expected Gain:** **~0.1–0.3 ms GameThread** during 200-unit battles (removes ~600–2,000 `libm` transcendental calls/frame).
- **Risk to Look & Behaviour:** **Very Low.** Mathematically identical results.
- **Effort:** Low (already implemented and compile-verified in Patch 05).
- **Recommendation:** **Apply now.**

---

#### Rank 11 — TBDR Depth-PrePass & Velocity Pass Experiment (`r.EarlyZPass`, `r.VelocityOutputPass`)
- **Patch:** None (manual CVar A/B only)
- **What & Why on Apple Silicon:** Once Patch 01 (`r.DBuffer=False`) and Patch 02 (`r.Nanite=0`) remove the two forced-prepass triggers, UE defaults to `r.EarlyZPass=3` (auto/opaque-and-masked prepass). On Apple Silicon TBDR GPUs, hardware HSR already eliminates opaque pixel-shader overdraw *within* the base pass without a separate vertex pass — **unless** masked foliage (`M_Foliage`), heavy TSR motion vectors (`r.VelocityOutputPass=1` outputs velocity in BasePass instead of a separate pass), or distance-field/AO depth reads outweigh vertex cost.
- **Expected Gain:** **0 to 1.5 ms GPU** depending on camera zoom and tree density — or a **regression** if masked canopy overdraw spikes.
- **Risk to Look & Behaviour:** **Medium** (performance regression risk; verify TSR ghosting on moving troops/swaying trees if changing `r.VelocityOutputPass`).
- **Effort:** Low (2 console commands to test).
- **Recommendation:** **Apply with testing** — benchmark `r.EarlyZPass 1` (opaque-only) and `r.EarlyZPass 0` + `r.VelocityOutputPass 1` in `L_Realm` overview 0.45 and `L_Highlands` dense forest before adding to `MacDeviceProfiles.ini`.

---

#### Rank 12 — MetalFX Upscaling (Temporal & Spatial) vs TSR
- **Patch:** None
- **What & Why on Apple Silicon:**
  - **Engine Reality in UE 5.8.4:** Checked the Installed Engine tree (`/Users/Shared/Epic Games/UnrealInstall/UE_5.8/Engine/Plugins`): UE 5.8.4 ships **no built-in MetalFX plugin** — only the low-level C++ header `ThirdParty/MetalCPP/MetalFX/MetalFX.hpp`. Using `MTLFXTemporalScaler` or `MTLFXSpatialScaler` requires writing and maintaining a custom `ITemporalUpscaler` / `ISpatialUpscaler` RHI plugin that marshals UE's RDG colour/depth/motion-vector textures into `id<MTLTexture>` via `IMetalDynamicRHI`.
  - **MetalFX Spatial:** Cheaper than TSR (~0.3–0.5 ms vs ~2–3 ms), **but** replaces temporal anti-aliasing with single-frame Lanczos/edge-directed upscaling. VoxelLab's crisp high-contrast voxel edges and distant tree/roof silhouettes shimmer severely without temporal accumulation. **Not suitable for High.**
  - **MetalFX Temporal:** Runs Apple-tuned tiled/ANE-assisted temporal upscaling on M-series GPUs and can save **~1.0–2.0 ms GPU** over UE's TSR at high output resolutions while maintaining comparable temporal stability. Worth revisiting *only* if future profiling shows TSR remains a top-3 GPU bottleneck after Ranks 1–2 and 7.
- **Expected Gain:** **~1–2 ms GPU** (Temporal); Spatial hurts visual quality.
- **Risk to Look & Behaviour:** **High** (custom RHI plugin maintenance across UE point releases; temporal rejection tuning for voxel silhouettes/arrows/WPO grass).
- **Effort:** High (multi-day RDG + MetalRHI plugin engineering).
- **Recommendation:** **Skip** for now — Rank 2 (native TSR + Dynamic Resolution) delivers larger practical gains at a fraction of the risk.

---

#### Rank 13 — PGO, `-ffp-contract=fast`, `UseFastIntrinsics`, and `MinArm64CpuTarget`
- **Patch:** None
- **What & Why on Apple Silicon:**
  - **PGO (Profile-Guided Optimization):** On an Installed Engine, >90% of CPU instructions live in precompiled Engine `.o` libraries (`UnrealGame` static libs). Instrumenting only `VoxelLab`'s ~30 C++ files requires custom toolchain overrides and training workflows for <1% net frame-time gain.
  - **`-ffp-contract=fast` (FMA fusion):** UE 5.8 `MacToolChain.cs:209` explicitly passes `-ffp-contract=off` globally to preserve cross-platform floating-point/DDC determinism. Overriding it risks subtle FP divergence for minimal gain on `VoxelLab`'s memory/pointer-bound RTS ticks.
  - **`UseFastIntrinsics=True` (`MacTargetSettings`):** Already `EnableMathOptimisations=True` (passes `-ffast-math` to Metal shader compiler). Turning on `UseFastIntrinsics=True` enables Metal fast-math intrinsics with undefined NaN/INF behaviour that can cause black NaN fireflies in Lumen/TSR history buffers.
  - **`MinArm64CpuTarget`:** Inspected UE 5.8 `ClangToolChain.cs` — `MinArm64CpuTarget` is Linux/Graviton-only and ignored by `MacToolChain.cs` (which already targets Apple Silicon ARMv8.5-A via `-arch arm64 -mmacosx-version-min=14.00`).
- **Expected Gain:** <1% CPU/GPU.
- **Risk to Look & Behaviour:** **Medium–High** (shader NaN artefacts; build fragility).
- **Effort:** High (for PGO) / Low (for unsafe flags).
- **Recommendation:** **Skip.**

---

#### Rank 14 — Packaging & Hardware Matrix Findings (`NSHighResolutionCapable`, M1 OS Floor, `libmetalirconverter.dylib`)
- **What & Why on Apple Silicon:**
  1. **`NSHighResolutionCapable = false` (already set in `Builds/Mac/VoxelLab.app/Contents/Info.plist`):** This means the packaged app renders into a **1× logical backing store** (e.g., 1512×982 on a 14" MacBook Pro rather than 3024×1964 Retina 2×), giving an accidental **~2.5–3× GPU speedup** compared to PIE's 3224×1660 Retina window! **Keep `false`** unless sharper 2× HUD text is explicitly prioritized (in which case pair `NSHighResolutionCapable = true` with default `RenderScale = 67–75%` or Dynamic Resolution so 3D pixel count stays flat while 2D HUD stays Retina-crisp).
  2. **SM6 on M1 Macs requires macOS 15+:** Verified in `Engine/Source/Runtime/Apple/MetalRHI/Private/MetalRHI.cpp:419-431`: UE 5.8 gates `SF_METAL_SM6` on Apple7 (M1) GPUs to **macOS 15.0+**, whereas `Info.plist` declares `LSMinimumSystemVersion = 14.00`. Since `VoxelLab` is SM6-only, either document **macOS 15+ required on M1** (macOS 14+ on M2–M5) or bump `MinimumOSVersion` to `15.0` before public release.
  3. **`libmetalirconverter.dylib` (56 MB in `VoxelLab.app`):** Staged by UE 5.8 for Metal IR conversion (`MetalShaderConverter`). Do not delete manually unless verified that Shipping never invokes runtime IR conversion (some engine global shaders / Niagara / MetalRHI paths link it dynamically at load time).
- **Recommendation:** **Keep / Document** (no code patch required).

---

#### Rank 15 — Architecture Notes on Reviewed / Skipped Apple Silicon Topics
- **Metal Memoryless Render Targets (`MTLStorageModeMemoryless`):** Verified in UE 5.8 `MetalTexture.cpp` — UE gates `MTLStorageModeMemoryless` behind mobile-renderer paths (`bIsMobile` / iOS/tvOS). The macOS desktop deferred renderer does not use memoryless targets, so no CVar can enable them without modifying Engine RHI source.
- **`r.Lumen.TranslucencyVolume.Enable=0`:** Verified in `VolumetricFog.cpp:1926` that volumetric fog gracefully falls back when disabled, saving an additional **~0.5–1.0 ms GPU**, **but** removes Lumen's indirect colour bounce inside fog (visible softening/darkening of sunlit mist). Kept at `1` on High; safe candidate for `UVLGraphics` Medium if extra GPU headroom is needed.
- **Nanite on Static Voxel Meshes (deferred in `PLAN.md`):** Remains a separate content-pipeline experiment; given `VoxelLab`'s low-poly blocky meshes and existing LODs, runtime `r.Nanite=0` (Rank 1) is the faster win today.

---

## 3. How to Measure Each Optimization on a Mac

Run all measurements in a **packaged `Development` build** (`sh Tools/package.sh Development`) — not PIE — whenever evaluating worker threads, QoS, PSO hitches, or thermal behaviour, because PIE runs at 2× Retina resolution, uses Editor worker pools, and competes with the Editor Slate UI.

### A. In-Game Telemetry & Pass Breakdown
1. **CPU / GPU / Draw / RHI split:** Press `~` and run `stat unit` + `stat unitgraph` (or `vl.Perf` for averaged numbers).
   - If `GPU > Game` and `GPU > Draw`: GPU-bound (test Ranks 1, 2, 7, 11).
   - If `Game` spikes during 100v100 combat or map load: CPU-bound (test Ranks 5, 9, 10).
   - If `RHI` spikes on camera pan/new unit spawn: PSO / Metal driver bound (test Rank 3).
2. **Per-pass GPU timing:** Run `stat gpu` live, or capture a frame with `ProfileGPU` and summarize with `python3 Tools/gpuprof.py`:
   - Check `TranslucencyVolumeLighting` drops to `0.00 ms` (Rank 1).
   - Check `PrePass` is no longer tagged `(Forced by Nanite)` or `(DBuffer)` (Rank 1).
   - Check `LumenReflections` and `BasePass` / `TSR` deltas with `r.SceneColorFormat=2` vs `4` (Ranks 1, 7).
3. **`r.ScreenPercentage` Scaling Test (GPU Bandwidth vs ALU Diagnostic):**
   - On a paused or steady `L_Realm` overview camera, compare `stat gpu` at `r.ScreenPercentage 100`, `75`, and `50`.
   - Passes that drop nearly linearly with pixel count (`0.56×` at 75%, `0.25×` at 50%) are pixel/TBDR-bandwidth bound → strong signal for **Dynamic Resolution (Rank 2)** and **`r.SceneColorFormat=2` (Rank 7)**.
   - Passes that barely move (e.g., `VirtualShadowMap` page renders, `LumenSceneUpdate`) are geometry/scene-update bound → **VSM `MaxPhysicalPages` (Rank 8)** and `r.Nanite=0` / `EarlyZPass` (Ranks 1, 11).
4. **VSM & Dynamic Resolution Verification:**
   - `r.Shadow.Virtual.ShowStats 1` — confirm physical page usage stays safely under `2048` (High) / `1024` (Med/Low).
   - `stat DynamicResolution` (or `vl.Gfx.DynRes 1`) — confirm screen percentage dynamically adapts between `50%` and `100%` to hold `16.6 ms` (60 fps) or `25.0 ms` (40 fps).
5. **Runtime A/B Switches Included in Patches:**
   - `vl.Opt.MacWorkers 0|1` and `vl.Opt.MacQoS 0|1` (check `apple-silicon:` log lines at startup).
   - `vl.Opt.ThermalGuard 0|1`, `vl.Opt.IdleThrottle 0|1`, `vl.Gfx.DynRes 0|1|2|3`.

### B. Xcode Instruments & macOS System Tools
1. **Metal System Trace (Instruments):**
   - Launch `Instruments` → **Metal System Trace** → attach to `VoxelLab.app`.
   - Inspect **GPU Timeline** (vertex/tiler vs fragment overlap on TBDR), **Command Buffer / Encoder gaps** (RHI stalls), and **Shader/Pipeline Compilation** lanes (verify PSO precaching eliminates mid-gameplay compilation bars — Rank 3).
   - Inspect **Memory / Bandwidth** counters to compare `r.SceneColorFormat=2` vs `4` (Rank 7).
2. **Time Profiler + Thread States (Instruments):**
   - Verify `GameThread`, `RenderThread`, and `RHIThread` execute on **P-cores** with `User Interactive` QoS and that `ForegroundWorker` / `BackgroundWorker` pools expand beyond 4 threads during `L_Highlands` `GRID built` and battle ticks (Rank 5).
   - Compare `AVLKing::PoseFigure` and `AVLKing::UpdateCape` self-time (Rank 10) and ThinLTO cross-TU hot functions (Rank 9).
3. **Thermal & Power (`powermetrics`):**
   ```bash
   sudo powermetrics --samplers cpu_power,gpu_power,thermal -i 2000 -n 30
   ```
   - Compare **GPU Power (mW)** and **Thermal Pressure** across: active gameplay (60 fps vs 40 fps ProMotion cap), pause menu (`vl.Opt.IdleThrottle=1` vs `0`), and unfocused window (Rank 6).
4. **Shader Cook & Package Size Verification:**
   - After applying Patch 01 and recooking, inspect `Saved/Cooked/Mac/VoxelLab/Metadata/ShaderTypeStats-METAL_SM6.csv` and `du -sh Builds/Mac/VoxelLab.app` to verify `RayTracing`, `MegaLights`, and `DBuffer` shaders dropped out and `.ucas` shrank accordingly (Rank 4).

---

## 4. Patch Files & Apply Instructions

All five patches are **file-disjoint**, unified diffs against the current working tree, verified with `git apply --check` from the `VoxelLab/` directory. All C++ and `Target.cs` patches (03, 04, 05) were additionally applied cumulatively to an isolated scratch copy outside the repository and compiled + ThinLTO-linked cleanly with UE 5.8.4 (`VoxelLab Mac Shipping`, arm64, Apple Clang 21.0.0).

| Patch File | Files Touched | Covered Ranks | Recommendation |
|---|---|---|---|
| `01-mac-metal-target-and-shaders.patch` | `Config/DefaultEngine.ini`, `Config/Mac/MacEngine.ini` | Ranks 1 (DBuffer), 3, 4, 8, 9 | **Apply now** |
| `02-tbdr-lighting-and-bandwidth.patch` | `Config/Mac/MacDeviceProfiles.ini` *(new)* | Ranks 1, 7, 8 | **Apply with testing** (check `r.SceneColorFormat=2` visually) |
| `03-apple-silicon-build-flags.patch` | `Source/VoxelLab.Target.cs`, `Tools/package.sh` | Rank 9 | **Apply with testing** (verify full Shipping package) |
| `04-mac-graphics-vrr-thermal.patch` | `Source/VoxelLab/VLGraphics.{h,cpp}`, `VLHUD.{h,cpp}`, `VLHUDMenus.cpp` | Ranks 2, 6, 8 | **Apply now** |
| `05-arm64-cpu-qos-and-hotspots.patch` | `Source/VoxelLab/VoxelLab.cpp`, `Source/VoxelLab/VLKing.cpp` | Ranks 5, 10 | **Apply with testing** (verify Shipping worker logs) |

### Applying Patches (from `VoxelLab/`)
```bash
# Dry-run check any patch (or all of them):
git apply --check Docs/Optimization/AppleSilicon/01-mac-metal-target-and-shaders.patch

# Apply individually or all together:
for p in Docs/Optimization/AppleSilicon/*.patch; do
    git apply "$p"
done
```
