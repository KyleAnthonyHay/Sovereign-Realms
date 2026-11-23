# Windows optimization pass: results

Date: 2026-11-23, branch `windows-support`, commits `dfd874f` (batch 0) to `832abd4`. Plan: `PLAN.md`; audits:
`findings_fable52_pc.md`, `findings_gemini4neon.md`; the first measurements: `BASELINE.md`.

Machine: Ryzen 5 7600X, Radeon RX 9070 GRE, Windows 11, UE 5.8.4. Every figure is the packaged **Development**
build on `L_RealmV2`, Test World, both sides played by the Hard commander, High, `-FIXEDSEED`, 30 s a view
(`Tools\windows\perf_capture.ps1`; 2560 x 1440 with `-Fullscreen`). Two runs of one build differ by about 2 % at the
base and the overview, and by up to 1.5 ms at the mountain view (its render thread).

## Before and after

fps / mean frame / 99th / worst / game / draw / GPU, in ms. Before: `bc883c7` with the corrected capture
(`BASELINE.md`, section 4). After: `832abd4`.

| View | Before | After |
|---|---|---|
| 1920 x 1080, base | 68.7 / 14.56 / 18.52 / 28.7 / 14.55 / 5.18 / 3.81 | 97.7 / 10.23 / 13.35 / 29.5 / 10.21 / 4.93 / 4.03 |
| 1920 x 1080, mountain | 46.4 / 21.54 / 28.37 / 277.4 / 21.13 / 18.73 / 6.99 | 55.2 / 18.11 / 27.70 / 172.7 / 15.35 / 17.93 / 5.88 |
| 1920 x 1080, overview | 41.1 / 24.30 / 52.41 / 60.6 / 24.28 / 10.06 / 11.62 | 64.2 / 15.59 / 26.84 / 54.7 / 15.58 / 10.04 / 8.94 |
| 2560 x 1440, base | 65.4 / 15.29 / 19.10 / 29.4 / 15.28 / 5.30 / 4.38 | 94.0 / 10.64 / 13.68 / 24.6 / 10.62 / 5.09 / 4.62 |
| 2560 x 1440, mountain | 45.8 / 21.83 / 28.26 / 271.5 / 21.63 / 15.92 / 7.56 | 55.8 / 17.92 / 28.03 / 155.4 / 15.72 / 17.74 / 6.40 |
| 2560 x 1440, overview | 41.3 / 24.22 / 58.76 / 65.9 / 24.20 / 10.34 / 12.42 | 62.5 / 16.00 / 28.47 / 56.2 / 15.99 / 10.09 / 9.58 |

- The base view gained 42-44 % in fps, the overview 51-56 %, the mountain view 19-22 %.
- The overview holds 60 fps at both sizes; it is bound by the game thread (15.6-16.0 ms). The mountain view is bound
  by the render thread (about 18 ms) and does not hold 60.
- Game thread at the 1080p overview: `CharacterMovement` 14.1 -> 7.3 ms, `Tickables` 0.88 -> 0.34 ms, ticks a frame
  1,005 -> about 600. `UI` is 2.1 ms as before (see the far pips below).
- GPU at the overview: 11.6 -> 8.9 ms (1080p), 12.4 -> 9.6 ms (1440p).

## Each batch (fps / frame / game / draw / GPU; 1080p)

| | base | mountain | overview |
|---|---|---|---|
| Baseline | 68.7 / 14.56 / 14.55 / 5.18 / 3.81 | 46.4 / 21.54 / 21.13 / 18.73 / 6.99 | 41.1 / 24.30 / 24.28 / 10.06 / 11.62 |
| Batch 1 | 94.7 / 10.56 / 10.55 / 4.81 / 3.80 | 51.6 / 19.37 / 14.22 / 19.19 / 6.95 | 58.0 / 17.24 / 14.44 / 17.17 / 11.87 |
| Batch 2 | 96.8 / 10.33 / 10.32 / 4.63 / 3.77 | 55.7 / 17.95 / 14.37 / 17.77 / 5.94 | 68.8 / 14.54 / 14.53 / 10.04 / 9.29 |
| Batch 3 | 98.5 / 10.16 / 10.14 / 4.67 / 4.01 | 54.3 / 18.41 / 14.93 / 18.23 / 5.81 | 70.2 / 14.25 / 14.24 / 9.39 / 8.88 |
| Batch 4 | 97.5 / 10.25 / 10.24 / 4.77 / 4.03 | 53.6 / 18.65 / 15.31 / 18.47 / 5.88 | 67.5 / 14.82 / 14.81 / 9.19 / 8.90 |
| Final (pips as rows) | 97.7 / 10.23 / 10.21 / 4.93 / 4.03 | 55.2 / 18.11 / 15.35 / 17.93 / 5.88 | 64.2 / 15.59 / 15.58 / 10.04 / 8.94 |

The 2560 x 1440 rows are in the commit messages of each batch.

## Each item

| Item | Status | Measured effect |
|---|---|---|
| Batch 0: capture fixes (real base view, `-Fullscreen`, `-FIXEDSEED`, metadata line) | Kept | The baseline above |
| FP-08 / GN-11 `r.Nanite=0` | Not taken | A/B at the overview: GPU 12.26 against 12.28 ms, draw 11.26 against 10.44 ms |
| `r.HZBOcclusion=1` | Not taken | GPU -3.1 ms, draw +3.6 ms, RHI thread +1.9 ms |
| `r.VelocityOutputPass=1` | Not tried | Read-only at run time (needs a cook) |
| FP-03 + FP-12 (standing units keep their floor, no physics interaction, no capsule overlap events, AI controller ticks off, farmhand log at Verbose) | Kept | Measured with FP-02 as one group: `CharacterMovement` 14.1 -> 5.4 ms at the 1080p overview in batch 1's run, ticks a frame 1,005 -> 597 |
| FP-02 garrisoned units asleep (`vl.Opt.GarrisonSleep`) | Kept | 60 of 313 movement components not ticking |
| FP-05 route memo and the tighter search loop (`vl.Opt.RouteMemo`, `vl.Opt.FastFlood`) | Kept | `Tickables` 99th percentile at the overview 30.5 -> 3.7 ms; frame 99th 52.4 -> 20.9 ms in batch 1's run |
| FP-10 foe scan (`vl.Opt.FoeScan`) | Kept | Not isolated (in batch 1's group) |
| GN-10 minimap ground trace cached, `TickSites` over the registry | Kept | Not isolated |
| GN-10 far pips as triangles (`vl.Opt.PipTris`) | Written, **off** by default | `UI` 2.1 -> 1.0-1.2 ms at the overview with it on. A screenshot leaves the HUD out, so the diamonds could not be compared pixel for pixel; switch it on after a look by eye |
| GN-04 (1) `PlanAttack` cached, strategy clocks staggered | Not done | The squads change between the two calls; the stagger changes the commanders' timing (accepted by the coordinator) |
| FP-07 unit parts: approximate occlusion (`vl.Opt.PartOcclusion`) | Kept, changed from the plan | Occlusion queries at the 1080p overview 12,700 -> 4,480 a frame, RHI draws 20,400 -> 11,900. Batch 2 as a whole at that view: GPU 11.9 -> 9.3 ms, draw 17.2 -> 10.0 ms |
| FP-07 as planned (never occluded, mode 2) | Rejected | Overview GPU 8.3 ms, but mountain frame 18.8 -> 21.4 ms (45 % more triangles drawn behind the massif) |
| GN-08 no render-state rebuild for sky, ambience and dust instances | Kept | Instances added and removed a frame 574 / 1,099 -> 0 |
| FP-14 battle sound sets at match start | Kept | `SkipPackage` lines in a capture run 76 -> 33 |
| GN-12 (3) instanced-mesh usage flag on `M_Voxel` and `M_VoxSway` | Kept (ASSET) | The "missing usage flag InstancedStaticMeshes" warnings are gone: smoke and motes no longer draw with the default material |
| GN-07 farm wheat instanced (`vl.Opt.PropInstances`) | Kept, wheat only | Static mesh actors 2,192 -> 842. Frame time within the noise. A farm screenshot with it on and off shows the same picture (not pixel-exact: the wheat sways) |
| FP-01 ground collision at LOD 2 | **Reverted** | `CharacterMovement` 6.1 / 7.6 / 6.9 -> 5.8 / 7.4 / 8.0 ms (no gain), and the path grid changed (1,096,156 nodes for 1,096,134, every checksum different). The pass stays in `realmv2_lods.py` with `COLLISION_LOD = 0` |
| FP-06 a raid's routes searched side by side (`vl.Opt.ParallelRoutes`) | Kept | The frame at clock 2:24: `Tickables` 175 -> 102 ms, frame 203-207 -> 155-173 ms. `vl.Opt.RouteMemo 2` logged no difference from the sequential searches over a whole run |
| FP-04 general movement sleep (`vl.Opt.MoveSleep`) | Written, **off** by default | Components ticking 253 -> 137; game thread -0.3 to -0.4 ms at the base view, within the noise elsewhere |
| FP-11 rig posed on worker threads | Not done | - |
| FP-13 / GN-13 grid rebuild without the full relabel | Not done | - |
| FP-15 instanced unit parts | Deferred | The mountain view's render thread (about 18 ms) is what it would address |

## Assets changed

Two, through `Tools/ue/material_usage.py` in UE 5.8.4:
- `Content/Voxel/Materials/M_Voxel.uasset`
- `Content/Voxel/Materials/M_VoxSway.uasset`

The 387 Realm v2 ground tiles were changed by `realmv2_lods.py` for FP-01 and reverted with git; none is committed.

## Checks

- **Path grid:** checksum `a3c58f10f8123da6` (1,096,134 nodes) before the pass and at the end.
- **Routes:** `vl.Opt.RouteMemo 2` (search anyway and compare with the memo, the prewarmed routes included) over a
  full capture run: no difference logged.
- **AI-vs-AI match:** the commanders' log lines follow the baseline's to the second up to the raids at 2:24 in every
  batch; no new warning or error in any batch's log. Two baseline warnings are gone (the smoke's and the motes'
  material).
- **`Tools/realmv2_test.py`:** not run. It needs numpy, and this PC has neither `Tools/.venv` nor a Python with numpy
  (the engine's has none).
- **Screenshots against the baseline build:** not done. The old Shipping build takes no commands (no command inbox,
  no console), so no view could be set in it, and it was overwritten without a capture. What was compared: a farm with
  the wheat instanced and as actors (same picture), and the final build's views by eye.

## Shipping build

`Builds\Windows\SovereignRealms\` (Shipping, from `832abd4`), 1,342 MB (the baseline's was 1,407 MB).

**The 60 s launch check failed on this PC:** Windows Smart App Control blocks the new
`SovereignRealms-Win64-Shipping.exe` (Code Integrity event 3077 at 07:37:37, and again at 07:40:48 after one rebuild).
The bootstrap `SovereignRealms.exe` starts and the game process never does. The Development build of the same code ran
every capture. Smart App Control was not touched.

## Incidents

- **Watchdog:** no thermal trip. The old watchdog crashed once (03:09:43, in its sensor library); 1 min 46 s later
  the game hit `DXGI_ERROR_DEVICE_REMOVED` once during a warm-up. It did not recur after the watchdog was replaced,
  so no capture was run with a frame cap. Peaks: GPU 55 C, CPU die 44 C (new sensors); GPU hotspot 81 C once (old).
- **Smart App Control** blocked `UnrealEditor-SovereignRealms.dll` twice (03:04-03:07 and 04:10) and the Shipping
  executable twice (above).
- **An unintended resave (04:20):** `UnrealEditor-Cmd -run=ResavePackages -help`, meant as a load check, resaved
  7,600 engine assets and 1,665 project assets before it was stopped. The project was reverted with git; the
  coordinator verified all engine files against Epic's manifests (only timestamps changed).

## Mac

Not built or run on the Mac in this pass.
- All code changes are platform-neutral C++ (no `PLATFORM_WINDOWS` branch was added) and no config file changed, so
  the Mac gets the same behaviour: the movement settings, the route memo, approximate occlusion for unit parts, the
  instanced wheat.
- The two material assets were saved by UE 5.8.4; the Mac is on 5.8. Their new usage flag adds the instanced-mesh
  shader permutations to the Mac's cook as well.
- `Tools/ue/material_usage.py` and the builders' changes run on either OS.

## Left to do

1. Get a Shipping executable past Smart App Control (or run it on another PC) and do the 60 s check.
2. Look at the far pips with `vl.Opt.PipTris 1`; if they look right, make it the default (about 1 ms at the overview).
3. Decide on `vl.Opt.MoveSleep 1` after a longer played match.
4. FP-11, FP-13 / GN-13, and FP-15 for the mountain view's render thread.
5. Run `Tools/realmv2_test.py` where numpy is available, and build and run on the Mac.
