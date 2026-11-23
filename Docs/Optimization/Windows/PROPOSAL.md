# Windows (Direct3D 12) port and optimization: what was done

Date: 2026-11-23. Target: Windows 10 / 11, 64-bit, a Direct3D 12 GPU with SM6 (the development machine: Ryzen 5 7600X
6C/12T, 31 GB, Radeon RX 9070, Windows 11, Visual Studio 2026 / MSVC 14.52). The Mac's pass is
`Docs/Optimization/AppleSilicon/PROPOSAL.md`; the cross-platform one is `Docs/Optimization/PLAN.md`. The same rules
hold here: the default **High** preset keeps the Mac's look, behaviour stays identical, anything visible goes behind
the lower presets.

**Status of the numbers.** The build, the cook and the game are confirmed on Unreal 5.8.4 and measured as they stand:
`BASELINE.md` beside this file (Direct3D 12, SM6, the RX 9070 chosen; the game thread, not the GPU, is the limit on
this PC). The gains marked "expected" below are still estimates: none of the settings has been A/B-tested on
Windows. *How to measure* at the end lists the runs.

## 1. What carries over from the earlier passes untouched

Everything in `PLAN.md` and most of the Apple Silicon pass is platform-neutral code or `Config/DefaultEngine.ini`, so
Windows has it already: the batched rig and animation significance (`VLKing`, `VLKingRig`), the battle's spatial hash,
the parallel path grid, the HUD and minimap caches, the mesh LODs, the Low / Medium / High presets with render scale
and the far-fog coarsening (`UVLGraphics`), dynamic resolution (`vl.Gfx.DynRes`; Direct3D 12 supports it as Metal
does), the frame-rate choices, the menu / background throttle (`vl.Opt.IdleThrottle`), music loaded on demand, the
coarser Lumen gather, `r.TSR.History.ScreenPercentage=100`, `r.IndirectLightingCache=0`,
`r.MegaLights.Supported=False`, `r.DBuffer=False`, the NNE plugins off, the never-cooked old king meshes.

The Mac-only parts are all behind `#if PLATFORM_MAC` and compile to nothing on Windows: the P/E-core worker sizing
and thread QoS (`SovereignRealms.cpp`), the thermal / Low Power guard (`VLGraphics.cpp`). `Config/Mac/*` is not read
on Windows.

## 2. Changed for Windows

| # | Item | Where | Gain | Risk to the High look |
|---|---|---|---|---|
| W1 | Direct3D 12 as the default RHI; SM6 the only cooked shader format (no D3D11 / SM5, no Vulkan) | `Config/Windows/WindowsEngine.ini` | Expected: about half the shader cook and shader library (the engine's default cooks `PCD3D_SM5` for both D3D11 and D3D12 next to SM6); one renderer to test | None: Lumen and virtual shadow maps, which are the look, need SM6 anyway. A machine without Direct3D 12 gets the engine's message instead of a different-looking game |
| W2 | `r.TranslucencyLightingVolume=0` in the Windows device profile | `Config/Windows/WindowsDeviceProfiles.ini` | Expected: about 1 ms of GPU a frame (1.34 ms measured on the M5 Pro; the pass is the same work on any GPU) | None: no lit translucent material exists (the placement ghost is Unlit); the fog's Lumen bounce is a separate switch and stays on |
| W3 | PSO precaching said explicitly (`r.PSOPrecaching=1`, `r.PSOPrecache.GlobalShaders=1`) | `Config/Windows/WindowsEngine.ini` | No first-sight hitch when a new troop, effect or building appears. The engine's defaults for `PCD3D_SM6` should already be this: the lines pin it | None |
| W4 | Hardware ray tracing stays off (nothing to change: the project never sets `r.RayTracing`) | - | No ray tracing shaders cooked, no acceleration structures built | None: the Mac build has it off too, so Lumen traces distance fields on both |
| W5 | The HUD and the controls screen write **Alt** where the Mac writes **Option** (`VL_ALT_KEY`) | `SovereignRealms.h`, `VLHUDGame.cpp`, `VLHUDMenus.cpp` | Correct key names on a PC keyboard | Mac strings are byte-for-byte what they were |
| W6 | Packaging: Shipping by default (Development beside it in its own folder), `-nodebuginfo`, `.pdb` files kept out of the game's folder, staging manifests dropped, the Visual C++ runtime installer included | `Tools/windows/package.ps1` | The folder to hand out has no debug files; symbols are kept beside it for crash dumps | - |
| W7 | The tools find the engine, the editor's log, Python and Blender on either OS; text files are read and written as UTF-8 explicitly | `Tools/vl_env.py`, `Tools/windows/_env.ps1`, `Tools/pie.py`, `gpuprof.py`, `aivsai.py`, `ue_py.py`, `ue_py_bridge.py`, `Content/Python/init_unreal.py` | The PIE tools and the AI-against-AI runs work on Windows; no behaviour change on the Mac (its default encoding is UTF-8 already) | - |
| W8 | MSVC build fixes: locals that hid a class member (`ACharacter::Mesh`, `AActor::Owner`) renamed; MSVC treats that as an error (C4458), clang does not | `VLKing.cpp`, `VLKingRig.cpp` | Compiles with MSVC | Renames only |

## 3. Deliberately not taken from the Mac's profile

| Mac setting | Why not on Windows |
|---|---|
| `r.Nanite=0` (removes the depth prepass that Nanite forces) | On Apple's tile-based GPU hidden-surface removal makes that prepass redundant. A desktop GPU is immediate-mode: the prepass is what gives it early-Z rejection in the base pass, so removing it can cost more than it saves. An A/B to run, not a default (see below) |
| `r.Shadow.Virtual.MaxPhysicalPages=2048` | A unified-memory saving (128-256 MB). A desktop card has its own memory; the engine's default stays |
| `[TextureStreaming] PoolSizeVRAMPercentage=0`, `r.Streaming.PoolSize=256` | The same: with textures of about 0.5 MB that do not stream, the Windows default (a ceiling of 70 % of the card's memory) costs nothing |
| `r.SceneColorFormat=2` | Off on the Mac too (banding risk); a bandwidth saving that matters on tile memory |
| Metal cvars (`rhi.Metal.*`, `r.Metal.*`), `MetalLanguageVersion`, metallib stripping | Metal only |
| Worker count and thread QoS (`vl.Opt.MacWorkers`, `vl.Opt.MacQoS`) | The Mac needs it because the generic platform code caps a packaged game at 4 workers and macOS schedules by QoS class. Windows has its own `NumberOfWorkerThreadsToSpawn` (sized from the logical cores, no cap of 4) and no P/E split on this CPU. To confirm: the worker count in the packaged Development build's log |
| Thermal / Low Power guard (`vl.Opt.ThermalGuard`) | `NSProcessInfo`; a desktop has no equivalent signal worth acting on. On a Windows laptop the frame cap, dynamic resolution and the idle throttle (all present) are the tools |
| ThinLTO for Shipping (`bAllowLTCG`) | See "Not done" |

## 4. Not done, and why

- **Link-time code generation for Win64 Shipping** (`bAllowLTCG` in `SovereignRealms.Target.cs`): with an installed
  engine the engine's objects are prebuilt, so `/LTCG` only reaches this module, the link takes several times longer,
  and it needs `bOverrideBuildEnvironment`. Expected gain 2-5 % of game-thread time in the module's hot loops, as on
  the Mac; the game thread is not the limit on this machine. Worth a measured try once the plain build is confirmed.
- **A bundled PSO cache** (`.upipelinecache` recorded from a play session): the logical precache (W3) comes first;
  record one only if first-launch hitches are still seen in the packaged build.
- **Upscalers** (FSR, DLSS, XeSS plugins): TSR with the game's render scale and dynamic resolution is the same path
  as on the Mac and keeps the two looks comparable. Third-party plugins would be a separate decision.
- **A Windows application icon** (`Build/Windows/Application.ico`): the Mac build has no custom icon either; the
  engine's default is used on both. Drop a 256 px `.ico` there when there is one.
- **Windows counterparts of the level rebuild scripts** (`Tools/mac/*_rebuild.sh`, `blender_build_all.sh`): they
  import into the editor and save assets; the art is authored on the Mac.

## 5. How to measure (once Unreal 5.8 is on the Windows machine)

1. `Tools\windows\editor.ps1 build`, then `Tools\windows\package.ps1 Development` (the test build: console, log,
   command inbox) and `Tools\windows\package.ps1` (Shipping).
2. In the packaged Development build's log (`Builds\Windows\SovereignRealms-Development\SovereignRealms\Saved\Logs`): the RHI line
   (`D3D12`, `SM6`), the adapter chosen (the discrete card, not the integrated one), the number of task workers.
3. Shader formats: `Saved\Cooked\Windows\SovereignRealms\Metadata\ShaderTypeStats-PCD3D_SM6.csv` should be the only
   `ShaderTypeStats` file. Size of the packaged folder against the Mac's 1,062 MB.
4. Frame times: `Tools\windows\perf_capture.ps1` (the packaged Development build, a Test World battle that plays
   itself; the method of `BASELINE.md`). In the editor, the same three views as the Mac's figures: open on `L_RealmV2`,
   `Tools\windows\realmv2_perf.ps1 profile` (PIE; `vl.Perf` and a `ProfileGPU` summary).
5. A/B in one session (`~` console of the Development build, the same scene): `r.TranslucencyLightingVolume 1` / `0`
   (W2), `r.Nanite 1` / `0` with `stat gpu` (the prepass question of section 3), `vl.Gfx.DynRes 1`.
6. The Mac's balance run for comparison: `python Tools\aivsai.py run HvH` (headless, the game thread alone).
