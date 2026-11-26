# Sovereign Realms showreel: the shot list

**Edit:** `SovereignRealms_Showreel.mp4`, 31.9 s, 957 frames, 1920 x 1080, 30 fps, H.264 + AAC 48 kHz stereo.
**Music:** *Ruach* (`SourceArt/Audio/Music/Ruach.mp3`), from **187.55 s** to 219.45 s: the build after the breakdown
(hits at 187.97 and 191.33), the full section from 197.0 s, and the drop into the quiet tail at 218.7 s, which lands
under the logo. The beat is 0.42 s (about 143 bpm); the cuts are on beats, and on the section's entry at 9.45 s.
The song fades in over 0.35 s and out over the last 1.2 s. The picture fades up from black over the first beat.

**Clips:** `clips/NN_<name>.mp4`, each take whole as captured, with no sound (the raw frames are in `frames/<name>/`).

## How it was captured

- The packaged Development build (`Saved/StagedBuilds/Windows/SovereignRealms.exe`), started straight into a match:
  `SovereignRealms.exe /Game/Maps/L_RealmV3?Match=1?Difficulty=0 -windowed -ResX=1920 -ResY=1080 -VLNoEnter`. It
  runs console commands dropped into its own `Saved/VLCommands.txt`. The HUD is hidden with `ShowHUD`, fog is off with
  `vl.Fog 0` (except shot 10), the music is off with `vl.Music 0`. High quality, render scale 100 %.
- **Frame by frame:** `vl.Record` pins the world's frame time to 1/30 s and saves one screenshot per frame, so the
  motion is perfectly even however slowly the frames render (about 4.5 frames a second here). Each frame's camera is
  a `vl.At <frame> vl.View free X Y Z Pitch Yaw FOV` (or `vl.Orbit Yaw Pitch Dist` for the hero's own camera).
- **Camera paths** (`Tools/showreel.py`): Catmull-Rom splines through the position, look-at and FOV keys, the clock
  eased in and out (smootherstep blended with linear); `ahead` aims the camera along its own path (the FPV shots).
- **Shots** (`Tools/showreel_shots.py`): each shot's keys (plan metres, +Y north), its staging commands and its
  length. Redo one with `Tools/.venv/Scripts/python Tools/showreel.py rec <name>` (the game on that shot's map).
  The battle shots restart the match (`vl.Restart 0`) and spawn fresh armies first.
- **Edit** (`Tools/showreel_edit.py`): `clips` encodes each folder of frames; `edit` composes the cut (the EDL in the
  file, a light grade of +10 % saturation and +6 % contrast, the fade from black, the picture darkening under the
  logo, the logo `References/Branding/sovereign_realms_logo_full.png` at 900 px wide) and encodes it with the song
  through Blender 5.3's sequencer.

## The clips

| # | Clip | What it shows | Frames (s) | In the edit | Source frames used | Captured |
|---|---|---|---|---|---|---|
| 01 | `01_island_push` | Realm v3 from far out over the sea: a long push in and down across the island to the player's plateau, its castle and towers | 150 (5.0) | 0.00-3.77 | 37-149 | free camera, 3 keys from (-40,-700,330) to (165,-262,48), FOV 46 to 62 |
| 02 | `02_mountain_orbit` | Realm v2's 184 m mountain: a slow rising orbit from the south-west, the peaks turning against the sea | 165 (5.5) | 3.77-7.13 | 40-140 | free camera orbiting (28,146): radius 300 to 270 m, 105 to 150 m up, -140 to -96 degrees |
| 03 | `03_parallax_castle` | A sideways glide half a metre over the flowers south of the player's castle: foreground parallax, the castle and its flag behind | 135 (4.5) | 7.13-9.47 | 60-129 | free camera at 14.6-15.2 m (the plateau is at 14 m) |
| 12 | `12_canopy_fly` | FPV over the north-east ridge's rocks and the forest, rising to reveal the basin | 150 (5.0) | 9.47-11.33 | 70-125 | free camera along 5 keys, aimed along its own path, FOV 80-86 |
| 04 | `04_fpv_pass` | FPV down the player's ramp and through the pass into the basin, fast and low | 150 (5.0) | 11.33-13.03 | 45-95 | free camera along 8 keys, aimed along its path, FOV 84-90 |
| 05 | `05_king_run` | King David runs from his castle to the ramp's head; the hero camera swings round him, low | 150 (5.0) | 13.03-14.70 | 40-89 | `vl.Walk 8000 7600 run`, `vl.CamLag 0`, `vl.Orbit` keys yaw 85 to 220, pitch -3 to -8, 300 to 460 cm |
| 06 | `06_troop_ship` | The troop ship, 21 troops aboard, sails up the east coast; the camera skims the water beside it, the sea cliff behind | 240 (8.0) | 14.70-16.37 | 150-199 | `vl.Ship #1 put selection`, `moor 27200 21500 -107`, `sail 25200 15000` at frame 0; the camera follows the course logged in a dry run (deterministic at the fixed step) |
| 10 | `10_fog_towers` | The fog of war from the player's plateau: the enemy's towers and the ridges poking over the mist | 150 (5.0) | 16.37-17.63 | 60-97 | `vl.Fog 1`, long lens (FOV 34 to 32), a slow push |
| 07 | `07_battle_line` | The clash in the basin, side on and long-lensed: the player's 30 swordsmen and King David charge the enemy's 30 under the archers' arrows | 240 (8.0) | 17.63-19.73 | 120-182 | `vl.SpawnTeam` 30 swordsmen + 20 archers a side, `vl.Formation smart`, `vl.AttackMove selection ... run`; a dolly along the basin's south side |
| 09 | `09_archer_volley` | Behind the player's 20 archers (held in place) as they shoot over the swordsmen's charge | 180 (6.0) | 19.73-21.00 | 100-137 | `vl.Hold archers`, swordsmen on attack-move; low camera pushing in |
| 08 | `08_king_charge` | King David at the head of the charge, sword drawn, the army behind him | 180 (6.0) | 21.00-22.67 | 20-69 | the battle staging, hero camera `vl.Orbit` keys low in front of him (yaw 10 to 80), `vl.Attack` at frames 100-166 |
| 11 | `11_raze_farm` | The enemy's farm razed: it shudders and sinks into the ground, the enemy castle and tower behind | 150 (5.0) | 22.67-24.77 | 40-102 | a fresh match; waits for the enemy commander's first farm (`BUILD Farm of team 1 finished at ...` in the log), 10 swordsmen on `vl.AttackAt troops Farm enemy`, `vl.Damage Farm enemy 3000` at frame 45 |
| 13 | `13_king_castle` | The close: King David before his castle, sword drawn; the camera rises and draws back to the castle and its flag; the logo comes in | 180 (6.0) | 24.77-31.90 | 0-179 (its last frame held from 30.77 s, under the logo, at 8 % brightness) | `vl.Teleport 12400 13200 1600 -90`, `vl.Orbit -90 -10 400` (to face the camera), troops sent away |

Logo: fades in at 27.30 s (on a bar) over 1 s; the picture goes down to black from 28.6 s to 30.2 s; logo and
music fade out over the last second (30.9-31.9 s).

**Re-recorded 2026-11-24** (the owner's call): every shot again, the same keys, staging and edit, with the gold
see-through outline off (`vl.Opt.Silhouette 0`) and the white hit flash off (`vl.Opt.HitFlash 0`), from the packaged
build in `Builds/Windows/SovereignRealms-Development` (driver: `Saved/Showreel/work2/redo_reel1.py`). The raw frames
were deleted afterwards; the clips are in `clips/`.
