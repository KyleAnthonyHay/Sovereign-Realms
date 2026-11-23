# Windows baseline (before any Windows-specific optimization pass)

Date: 2026-11-23, branch `windows-support`. What the game does on this PC as it is built today, measured so that the
next pass has something to compare with. The settings in `Config/Windows/` at this commit are part of the baseline
(Direct3D 12 / SM6 only, `r.TranslucencyLightingVolume=0`, PSO precaching on).

| | |
|---|---|
| CPU | AMD Ryzen 5 7600X (6 cores / 12 threads) |
| GPU | AMD Radeon RX 9070 GRE, 12 GB (driver Adrenalin 26.10.1); the integrated Radeon is present and not chosen |
| RAM, OS | 31 GB, Windows 11 Home (26200) |
| Display | LG HDR 4K (3840 x 2160, 60 Hz); the game in a window |
| Engine, compiler | Unreal 5.8.4 (launcher build, CL 58902052); Visual Studio 2026, MSVC 14.52.37029 (newer than the engine's preferred 14.50: one warning in an engine header, nothing else) |
| Build measured | packaged **Development** (`Builds\Windows\SovereignRealms-Development`), quality High, render scale 100 %, frame cap and background throttle off for the measurement |

## 1. Does it run

| Step | Result |
|---|---|
| `Tools\windows\editor.ps1 build` (`SovereignRealmsEditor Win64 Development`) | Succeeded, 67 s (the module's first full compile: 9 actions) |
| `Tools\windows\package.ps1 Development` | Succeeded, 14 min 38 s in all: build 62 s, **cook 12 min 39 s** (a cold derived-data cache: every shader compiled; peak 16.9 GB of RAM), stage + pak about 1 min |
| `Tools\windows\package.ps1` (Shipping, straight after) | Succeeded, 2 min 16 s: build 59 s, cook 23 s (everything cached) |
| Development build, `L_RealmV2`, 1280 x 720 window, 75 s | No fatal error, no ensure, no crash. `LogRHI: Using Default RHI: D3D12`, `Using Highest Feature Level of D3D12: SM6`, `Chosen D3D12 Adapter Id = 0` (the RX 9070; feature level 12_2, shader model 6.7), shader platform `PCD3D_SM6`, device profile `Windows`, ray tracing 0 |
| Shipping build, default start (the title screen), 1280 x 720 window, 40 s | Runs; the process was alive and drawing at the end (1.5 GB working set), no crash reporter, no crash folder |

Shaders cooked: `PCD3D_SM6` alone (`Saved\Cooked\Windows\SovereignRealms\Metadata\ShaderTypeStats-PCD3D_SM6.csv` is the
only one). Global library 8,123 unique shaders, 84.7 MB; the game's 1,684 unique, 14.5 MB.

### Sizes

| | Size |
|---|---:|
| `Builds\Windows\SovereignRealms` (Shipping, what a player gets) | **1,407 MB** (1.31 GiB): content 1.2 GB (`SovereignRealms-Windows.ucas` + `global.ucas`), executable and DLLs 170 MB, engine files and the Visual C++ runtime installers 87 MB |
| `Builds\Windows\SovereignRealms-Development` | 1,620 MB (1.51 GiB): the same content, executable and DLLs 329 MB |
| Symbols, beside the builds (`Builds\Windows\Symbols\Shipping`, `\Development`) | 223 MB, 364 MB |
| For comparison, the Mac's Shipping app (`README.md`, Performance) | 1,062 MB |

### Start-up (packaged Development, straight onto `L_RealmV2`; the files in the OS cache)

| | Seconds |
|---|---:|
| Engine initialization, as the log gives it (`(Engine Initialization) Total time`), of which `LoadMap(L_RealmV2)` 3.7 s | 4.9 |
| Process start to the engine up, wall clock | 5.7 |
| Process start to the match running and taking commands | about 11 |
| The very first start after packaging (cold): engine initialization, `LoadMap` 6.7 s | 8.6 |

## 2. Frame times

### Method

`Tools\windows\perf_capture.ps1` (new with this baseline). For each resolution it starts the packaged Development
build on `L_RealmV2?Match=1?Difficulty=2?AIvsAI=2?TestWorld=1`: the **Test World** (both sides at their most: castle
level 7, 126 troops a side, every building) with **both sides played by the Hard commander**, so the battle runs with
no hands. Through the command inbox (`Saved\VLCommands.txt`) it sets `t.MaxFPS 0`, `vl.Opt.IdleThrottle 0`,
`r.VSync 0` and the window size, waits 75 s, then at each of three views (the ones of `Tools/mac/realmv2_perf.sh`)
settles 8 s and records 30 s of Unreal's CSV profiler (`csvprofile start` / `stop`), whose `FrameTime`,
`GameThreadTime`, `RenderThreadTime`, `GPUTime` and `RHIThreadTime` are the numbers `stat unit` shows. The match clock
during the captures runs from about 1:30 to 3:30: 252 troops alive, the first raids out, the main armies not yet in
contact (no losses on either side yet). `Tools/perf_csv.py` averages the captures.

```
powershell -ExecutionPolicy Bypass -File Tools\windows\package.ps1 Development
powershell -ExecutionPolicy Bypass -File Tools\windows\perf_capture.ps1 -Width 1920 -Height 1080 -Tag 1080p -ProfileGpu
powershell -ExecutionPolicy Bypass -File Tools\windows\perf_capture.ps1 -Width 2560 -Height 1440 -Tag 1440p -ProfileGpu
python Tools\perf_csv.py --md "1080p base=Saved\Perf\1080p\base.csv" ...
python Tools\gpuprof.py Saved\Perf\1080p\game.log
```

Views: **base** the hero's follow camera at the player's castle; **mountain** a free camera south-west of the massif
(`vl.View free -15000 12000 6000 2 -52 70`); **overview** the postcard camera, the whole map.

### Results (`stat unit` numbers, mean over 30 s; milliseconds)

| Run | Frames | fps | Frame | median | 99th | worst | Game | Draw | GPU | RHIT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1920 x 1080, base | 1939 | 64.5 | 15.51 | 15.18 | 19.74 | 28.0 | 15.49 | 4.06 | 3.88 | 1.46 |
| 1920 x 1080, mountain | 1390 | 46.1 | 21.67 | 21.02 | 27.13 | 196.0 | 21.65 | 14.34 | 6.77 | 1.84 |
| 1920 x 1080, overview | 1269 | 42.1 | 23.75 | 23.20 | 32.09 | 53.8 | 23.72 | 10.21 | 11.66 | 1.83 |
| 2560 x 1440, base | 1811 | 60.2 | 16.62 | 16.18 | 32.88 | 43.3 | 16.60 | 4.10 | 4.17 | 1.46 |
| 2560 x 1440, mountain | 1291 | 42.9 | 23.32 | 22.38 | 41.54 | 239.8 | 23.30 | 16.12 | 7.09 | 1.86 |
| 2560 x 1440, overview | 1203 | 39.9 | 25.08 | 24.15 | 62.22 | 85.4 | 25.06 | 10.24 | 11.96 | 1.82 |

`vl.Perf` at the end of each capture (the engine's smoothed figures) agrees: 63.0 / 47.2 / 42.1 fps at 1080p,
56.6 / 41.8 / 35.8 fps at 1440p.

### What the numbers say

- **The game thread is the limit, at every view and both resolutions.** Frame time equals game-thread time; the GPU
  is at 4-12 ms (a quarter to a half of the frame) and going from 1080p to 1440p costs 1-1.5 ms. With the game's
  default 60 fps cap the base view just holds it; the two wide views do not (42-46 fps).
- **Where the game thread goes** (the CSV profiler's exclusive game-thread timers, mean ms a frame):

  | View (1080p) | CharacterMovement | TickActors | WorldTickMisc | UI | Tickables |
  |---|---:|---:|---:|---:|---:|
  | base | 10.90 | 1.64 | - | 1.15 | 0.44 |
  | mountain | 12.22 | 2.65 | 2.18 | 1.92 | 0.89 |
  | overview | 13.69 | 2.43 | 2.77 | 2.01 | 1.05 |

  `UCharacterMovementComponent` for the 252 troops (and the farmhands) is 11-14 ms, 60-70 % of the frame, whatever
  the camera sees (1440p: 11.8 / 12.8 / 14.4). The log of these runs also has 616 `LogCharacterMovement: ... is stuck
  and failed to move!` lines in four minutes (troops pushing against something), and the first frames after the map
  loads log `GetSimulationTimeStep() - Max iterations 8 hit` for the farmers. This is the first thing for the next
  pass to look at; it is not Windows-specific code, but the Mac's figures in `README.md` (a game thread of 1.6 ms in
  an `L_Realm` AI-against-AI match) were taken on another map with fewer troops, so the two are not comparable as
  they stand.
- **The render thread** ("Draw") is 4 ms at the base and 10-16 ms in the wide views; in the wide views most of it is
  waiting (`EventWait` 13-15 ms: it is waiting for the game thread), so it is not the limit either.
- **GPU**, a `ProfileGPU` capture of the overview (the passes over 0.6 ms; `Saved\Perf\<tag>\profilegpu.txt`):

  | Pass | 1080p ms | 1440p ms |
  |---|---:|---:|
  | Whole frame | 11.59 | 16.08 |
  | HZB / `BeginOcclusionTests` | 3.69 | 4.88 |
  | BasePass | 3.57 | 4.82 |
  | PrePass (`Forced by Nanite`) | 1.15 | 1.66 |
  | RenderDeferredLighting | 0.82 | 1.12 |
  | RenderVelocities | 0.68 | 1.03 |
  | ShadowDepths (virtual shadow maps) | 0.64 | 1.03 |
  | PostProcessing | under 0.6 | 0.79 |

  (A single frame each; the 1440p one is a heavier frame than that run's 30 s mean of 11.96 ms.) Occlusion queries
  cost as much as the base pass: the second thing worth a look. Lumen and the fog do not appear over 0.6 ms.
- **Hitches**: worst frames of 196 and 240 ms once in each mountain capture (the camera jumping to a part of the map
  not yet drawn). The log counts 36 `Encountered a new graphics PSO ... (PSOPrecacheState: Missed)` at start-up: there
  is no bundled pipeline cache (`SovereignRealms_PCD3D_SM6.stable.upipelinecache` is looked for and not found).

### In the editor (PIE), for comparison with the Mac's `realmv2_perf.sh` figures

`Tools\windows\editor.ps1 start`, then `Tools\windowsealmv2_perf.ps1 profile`: PIE in a floating window, a fresh
Easy match (`vl.StartMatch 0`: the starting troops only, not the Test World), `vl.Perf` at each view. The game's
60 fps cap is on, as in the Mac's runs.

| View | fps | Game ms | GPU ms |
|---|---:|---:|---:|
| base | 60.0 (capped) | 8.97 | 4.14 |
| mountain | 60.0 (capped) | 8.93 | 5.17 |
| overview | 60.0 (capped) | 9.51 | 6.82 |

(The render thread's time reads 0.00 in PIE.) An editor that is not the window in front idles at 3 fps: `editor.ps1`
starts it with that switched off; the first try, with the editor behind the terminal, measured exactly 3.0 fps.
Even with a handful of troops the game thread is 9 ms in the editor.

### Raw data (not in the repo: `Saved/` is ignored)

`C:\Dev\SovereignRealms\Saved\Perf\1080p\` and `...\1440p\`: `base.csv`, `mountain.csv`, `overview.csv` (the CSV
profiler's captures, every timer), `game.log` (the game's whole log of the run: RHI, `vl.Battle` at each capture,
`vl.Perf`, the `ProfileGPU` tables), `profilegpu.txt`, `summary.txt`. Packaging logs: `Saved\package_development.log`,
`Saved\package.log` (Shipping). Editor build: `Saved\build_editor.log`.

## 3. Found on the way (not fixed: content, or not this phase)

- `LogMaterial: Warning: Material /Game/Voxel/Materials/MI_Vox_smoke missing usage flag InstancedStaticMeshes! Default
  Material will be used in game.` The chimney smoke is drawn with the default material in a packaged build. The fix
  is a flag on the material and a save of the asset: for the Mac (the authoring machine), and worth checking there,
  since it is not a Windows matter.
- 33 `LoadPackage: SkipPackage: /Game/Voxel/Audio/S_<name>_<n>` warnings at start-up: the game asks for numbered sound
  variants until one is missing. Harmless; each is a failed lookup at load.
- The game restores its own window size at start (1600 x 900 at most), over `-ResX` / `-ResY`; `r.SetRes` afterwards
  works, and that is what `perf_capture.ps1` does.
- `python` on this PC is the Microsoft Store's stub; the scripts use the engine's Python
  (`Engine\Binaries\ThirdParty\Python3\Win64\python.exe`).
