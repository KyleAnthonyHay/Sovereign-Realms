# Sovereign Realms

A top-down fantasy RTS in a Minecraft-like voxel diorama (Unreal 5.8, C++ in `Source/SovereignRealms`, art from the
Blender voxel generators in `Tools/blender`). This project began as the VoxelLab sandbox inside the repo and replaced
the first draft (sprite troops on a lit terrain) on 2026-11-23, when the first draft was removed: its code, art and
design documents (`PLAN.md`, `Docs/GAMEPLAY.md`, `Docs/UI.md` and so on) are in git history, last at commit `8d5aa621`
(`git show 8d5aa621:Docs/UI.md`). "The first draft" below means that project.

Four levels, chosen on the New Game screen (or M while the Esc menu is
open: the next one round), and a fifth entry there, the **Test World** (Realm v2 with both sides at their most: see
*The battle > The Test World*); the packaged game starts on the realm's title screen. The town (`L_Town`) and the village
(`L_VoxelVillage`) were removed on 2026-11-22 (their maps, and the assets only they used: see *Realm v2*, the end).

- `L_RealmV2`: **Realm v2**, the third and biggest battle map, an island 640 m square: a mountain 184 m high with the
  sea's arms round it, five gold mines, the ruins plateau, a port for each side (see *Realm v2*).
- `L_RealmV3`: **Realm v3**, the fourth battle map, a compact island 416 m square: each castle on a plateau with
  cliffs all round, one ramp down to one pass, the basin between the ridges with two neutral mines, a port for each
  side, and forest everywhere else (see *Realm v3*).
- `L_Highlands`: the second battle map, 540 m square: a bluff to build on behind each castle, the river's gorge, and
  the Crown, a mesa in the middle with two neutral gold mines (see *The highlands*). `L_Realm` is the first.
- `L_Flatlands`: every building side by side on flat grass along one road, at its village size, each with its name in
  front, for reviewing them and checking the look (the Treasury and the Granary too). Across the road: King David and
  every troop in a line (the farmer woman and man too; static, in their modelled pose), the harbour (the dock running
  out into a pond, the grain ship moored at it), and the newest props (Realm v2's ruins and port pieces).

Reference renders of each building on flat ground, King David beside it for scale, are in `References/Buildings/`
(`<Name>.png` three-quarter view, `<Name>_front.png`, `Lineup.png` all of them at one scale).

## Platforms

The game is made on a Mac (Apple Silicon) and also builds and runs on Windows. One project, one engine version on
both: **Unreal 5.8** (`EngineAssociation` in `SovereignRealms.uproject`). An asset saved by a newer editor cannot be
opened by an older one, so no machine saves assets from another engine version; the scripts say so when the engine
they find is not 5.8 (building and packaging with a newer engine is harmless: cooking saves nothing in `Content`).

| | macOS (Apple Silicon) | Windows 10 / 11 (64-bit) |
| --- | --- | --- |
| Needs | Unreal 5.8, Xcode; for the art tools Blender and `python3` (`Tools/.venv` for numpy / scipy / Pillow) | Unreal 5.8 (Epic launcher), Visual Studio 2022 or later with *Game development with C++*, git with git-lfs; a Direct3D 12 GPU. For the art tools Blender and Python 3 (without one on the `PATH`, the Windows scripts use the engine's own) |
| Engine found at | `$UE_ROOT`, else `/Users/Shared/Epic Games/UnrealInstall/UE_5.8` | `%UE_ROOT%`, else the launcher's 5.8 (`C:\Program Files\Epic Games\UE_5.8`), else the newest `UE_5.*` there |
| Open the editor | `sh Tools/mac/editor.sh rebuild` (build the editor target, start it), or open `SovereignRealms.uproject` | double-click `Tools\windows\Editor.bat` (`editor.ps1`: builds `SovereignRealmsEditor Win64 Development`, then opens the project), or open `SovereignRealms.uproject` |
| Package | `sh Tools/mac/package.sh [Shipping or Development]` | double-click `Tools\windows\Package.bat`, or `powershell -ExecutionPolicy Bypass -File Tools\windows\package.ps1 [Shipping or Development]` |
| The build lands in | `Builds/Mac/SovereignRealms.app` | `Builds\Windows\SovereignRealms\SovereignRealms.exe` (the whole folder is the game; `Development` lands in `Builds\Windows\SovereignRealms-Development`; the symbols of each beside them in `Builds\Windows\Symbols`) |
| Packaging log | `Saved/package.log` | `Saved\package.log` |
| Renderer | Metal, SM6 shaders alone (`Config/Mac/`) | Direct3D 12, SM6 shaders alone, no Direct3D 11 fallback (`Config/Windows/`) |

Where the tools are:

- `Tools/mac/*.sh`: the Mac's shell scripts (the editor's lifecycle, packaging, the levels' rebuilds, `rec.sh`,
  `realmv2_perf.sh`, `blender_build_all.sh`).
- `Tools/windows/`: their PowerShell counterparts, `package.ps1`, `editor.ps1` (`open` / `quit` / `build` / `start` /
  `rebuild`), `rec.ps1` and `realmv2_perf.ps1`, with `Package.bat` and `Editor.bat` to double-click; and
  `perf_capture.ps1`, which measures the packaged Development build in a battle that plays itself. The levels'
  rebuilds (`*_rebuild.sh`, `blender_build_all.sh`) have no Windows counterpart: the art is authored on the Mac.
- `Tools/*.py`, `Tools/ue/`, `Tools/blender/`: Python, the same files on both (`Tools/vl_env.py` finds the engine, the
  editor's log and Blender on either). Where this README writes `python3 Tools/...`, Windows says `python Tools\...`.

On Windows the keys are the same; the Mac's **Option** key is **Alt** (the game's own hints say Alt there), and Cmd is
Ctrl. What was done for Windows performance: `Docs/Optimization/Windows/PROPOSAL.md`; what the game measures on a
Windows PC today: `Docs/Optimization/Windows/BASELINE.md`.

**Display settings.** The Mac starts in a window (16:9, at most 1600 x 900) and its Settings have one **Window** row
(Windowed / Full screen). Windows starts in **borderless full screen at the desktop's own resolution**
(`Config/Windows/WindowsGameUserSettings.ini`; an install from before is moved there once, `[SovereignRealms.Video]
FullscreenByDefault`), and its Settings have **Display mode** (Windowed / Borderless / Full screen, the exclusive
kind), **Resolution** (the display's own modes in exclusive full screen, the usual sizes up to the desktop in a window,
the desktop's size shown in borderless) and **VSync**; an exclusive mode asks "Keep this display mode?" and goes back
after 15 s without an answer. F11 / Alt+Enter toggle full screen on both, and the choice is saved however it was made.
The Windows game is DPI-aware (`bAllowHighDPIInGameMode` in `Config/Windows/WindowsEngine.ini`): it draws in the
monitor's real pixels (3840 x 2160 on a 4K display at 175 %, where it used to be told 2194 x 1234), the HUD keeps its
size on the screen (it is laid out from the view's height), and the 3D picture is the engine's automatic share of the
output (1920 x 1080 upscaled by TSR at 4K) times Render scale. A change of mode or size is made by `UVLGraphics` in
its next tick, never inside the HUD's draw (the engine redraws the viewport in the middle of a resize, which crashed
the Settings screen). On Windows the pointer stays inside a full-screen game; there is no edge scrolling (the view
pans with WASD / the arrows). The panels fit any aspect: the selection panel, the top bar and the menus are drawn
smaller where the view is narrower or lower than their design (4:3, 3:2, a 1280 x 720 window; `AVLHUD::FFit`).
`Tools\windows\hud_shots.ps1` takes screenshots with the interface at a list of sizes and clicks through the display
settings (`Saved\HUDShots`).

## Play

- Packaged game: `Builds/Mac/SovereignRealms.app` (first time: right-click > Open), or on Windows
  `Builds\Windows\SovereignRealms\SovereignRealms.exe`.
- Or open `SovereignRealms.uproject` and press Play.

There are two ways to play, switched with **Tab**.

**Hero** (the camera follows King David at the diorama angle)

| Input | Does |
| --- | --- |
| W A S D / arrows / left stick | walk (relative to the view) |
| Mouse | look around: left/right turns the view, up/down tilts it (the pointer is hidden; a crosshair shows where swings and arrows go). Esc, Tab or C bring the pointer back. Speed: Esc menu > Look speed (or L there), 25-150%, default 50%; calmer when zoomed out. Esc menu > Invert look (or I there): Off / Left-right / Up-down / Both |
| Shift, or double-tap a direction | run (after a double tap he runs until the keys are let go) |
| Space | jump |
| F | draw / sheathe the sword |
| Option (Alt) + left click on one of your units (the crosshair on it) | **nobody selected** (or the unit is one of the selection): select it. **Troops selected and it is not one of them: they guard it** (`UVLCommand::OrderGuard`): they take posts round it, keep with it as it moves and fight whatever comes within 18 m of it or strikes it; **a unit in a platoon: the whole platoon is guarded** (`OrderGuardPlatoon`: the ward is its leader, and when the ward falls the guard passes to another member; it ends only with the platoon). An alert says "3 guard platoon 2" / "3 guard Swordsman 4", the order marker closes on the ward, and **a gold-edged shield floats beside the head of every guarded unit** while the guard lasts (both views); the selection panel reads "Guarding platoon 2". Shift + Option: add it to / take it out of the selection (to pick a different troop while others are selected: Shift + Option, or let go with Esc first); twice quickly: take control of it. Option + click on a platoon's row of the platoon panel (the pointer shown) guards that platoon too. **A plain left click never selects: it is always your own blow** |
| Option + left click on a foe's unit or building | those under your command attack it: the selection (never the unit you play), else the troops following you (they fall in behind you again when the attack is done), else your platoon. Shift + Option + click: **queued** after what they are doing (attack unit 1, then unit 2, then a building, then walk: each in turn, the next as soon as the target falls or is razed; one fallen meanwhile is passed over) |
| Option + left click on the ground | they go there in formation (twice quickly: at a run); Shift + Option: queued after the attacks (or a point of their pathway when they have no chain) |
| Option + left click on the sky, Esc, or (pointer shown) on King David himself | let the selection go (Esc first lets go, a second Esc opens the menu) |
| | The crosshair says what a click does there (gold "Option+click: select ..." or "Option+click: guard ...", red "Option+click: attack ..."), the mode box top left whom you command; a queue shows small numbered plates over its targets and points (no lines across the hero view) |
| (minimap, platoon panel) | **both stay up in the hero view** (bottom left and bottom right, as in the overview; the line of controls and the health bar sit between them). The pointer is hidden while the mouse looks round, so they are for reading; with the pointer shown (C's postcard) their clicks work as in the overview: a platoon's row selects it, a click on the minimap goes to the overview there |
| (enemy diamonds) | every enemy troop from 5 m of the unit you play (full from 12 m: `vl.HeroPips.Near` / `.Full`, cm) carries the red diamond the overview shows from afar, so foes read among trees and at a distance. Your own troops carry none here |
| Right click (Ctrl / Cmd + click; an archer or spy played: Ctrl / Cmd + click only) | the selected troops (never the unit you play) go where the crosshair points, or attack the foe's unit or building under it, with the overview's order marker and click; twice quickly: at a run; Shift: queued as with Option (on a foe: after what they are doing; on the ground: their pathway, or the walk after their attacks; Builders: their queue). On one of your troops: the others follow it. 1..6 select platoon N; **G**: follow me (the selection, or else your platoon, falls in behind you) |
| Left click | attack (draws first if need be): the training dummies by the barracks rock when hit. He drops into a battle stance (`References/king_stance.png`: a lunge, the sword across his body) for the swing and holds it 1 s after the last one, then carries the sword low at his side; 4 s later he sheathes it. Clicks while he is in the stance go through a combo: a side slash, a diagonal cut, then an up-down-up (three blows); a click during a swing queues the next. Once the stance has lapsed the next click starts at the side slash again |

**Overview** (a bird's-eye camera that roams freely)

| Input | Does |
| --- | --- |
| W A S D | pan |
| Left click | select a unit (the king, a troop) or a building; click the ground to let go |
| Shift + click | add a unit to the selection, or take it out |
| Drag a box | select every unit in it (Shift: add them) |
| Left click on a training dummy | the swordsmen of the selection attack it (Shift: they go at a run): each takes a place on a ring round it, walks there by the usual routes, turns to it and swings, each on its own beat, until given another order. A unit standing in front of the dummy is still selected by the click; with no fighter selected the click is the usual one |
| Right click (or Ctrl / Cmd + click) | the selection goes there: by a route round fences, buildings, cliffs and water, through gates, over the bridge, up and down steps, and forms up in its formation. A double right click: at a run |
| Right click on one of your troops | the rest of the selection follows it (falls in behind it in its formation, re-sent as it moves, fights what it meets, lets go of a chase 24 m from it); its platoon's members following it make it the platoon's leader |
| Shift + right click | a point on the selection's pathway (as in the first draft): units already on an order walk there after it, in order; idle ones start at once. A plain right click replaces the pathway. **On a foe's unit or building: queued** (`UVLCommand::OrderChain`): they attack it after what they are doing, then the next foe, a building, a walk (Shift + right click on the ground after an attack is the chain's next walk); a dashed line through the chain (red attacks, blue walks) with numbered plates, as the Builders' queue |
| Right click on the Watch Tower | the archers of the selection walk to its door and appear on the lookout (8 posts); anyone else waits by the door |
| Select the Watch Tower | its panel (the selection panel, bottom middle) shows who mans it; its **Lookout** button brings them down. An archer on the lookout can also be selected and sent somewhere: it comes down first |
| F | the next formation: Line, Column, Wedge, Square, Loose (melee in front, archers behind) |
| A (a tap), then left click | attack-move: the selection marches there fighting what it meets, and marches on after each fight (Shift + click: one more point of the way; a click on a foe attacks it). **No attack-ground for archers any more** (the owner's call, 2026-11-22: no key, no button; `vl.ArmGround` and `UVLCommand::OrderAttackGround` are kept for tests) |
| S (a tap) | stop (drop every order). With units selected a tap of A or S is the order and a hold (over 0.17 s) pans, as in the first draft; with nobody selected they pan at once. **H (hold ground) is gone**: the stance cycle (G) has Hold ground. Neither A nor S has a button on the command card now |
| Option (Alt), held | **the cards over buttons** (the tooltip of whatever the pointer is on: "Upgrade the Castle [U]" with what it brings and costs, a build card, a command) **show only while Option is held**; without it hovering shows nothing |
| P, then left click | patrol between where they stand and there, round and round, fighting what they meet; Shift + click: one more point of the loop (P stays armed). P is the pause key only when nobody is selected |
| V, then left click (or right click on it) | guard one of your buildings, a Builder or King David: posts in a ring round it, fighting what comes within 18 m of it; the order ends when it falls. **V + left click on a troop guards it too** (one in a platoon: the whole platoon, as the hero view's Option + click); a right click on a troop is still "follow it". With no troops selected V is the camera angle |
| O | the selected Spy roams (struck, it runs home to the castle) |
| M | march together on / off (the slowest sets the pace; in a formation always, so it only matters with Loose) |
| K K | dismiss the selected troops (the first press asks; no refund; not King David) |
| Alt / Option + click | every unit of that kind in view (Shift: added) |
| Space / Home | centre the view on the selection (or the selected building) |
| Left click on a training dummy (archers selected) | they walk to within about 27 m with a clear shot, face it and shoot every 2.4 s until given another order. Archers on the watch tower shoot from the lookout (to 55 m) |
| Ctrl / Cmd / Alt / Shift + 1..6 | **the selection joins platoon N, which keeps the members it has** (an empty slot: they form it; a troop already in another platoon leaves that one). It was: Ctrl + N re-formed the platoon of the selection alone, putting everyone else out. (A platoon keeps its own formation; they are listed in the platoon panel, bottom right) |
| Assign (command card) | the same, by mouse: the button opens a picker of the six platoons over it (a formed one shows "5 in it", an empty one "new"); a click on one and the selection joins it. A click anywhere else, or Esc, puts the picker away |
| 1..6 | select platoon N (twice quickly: look at it) |
| Builders / Spy (top bar) | a click on the count opens **a list of them under the bar**: a row each with its portrait, name, health and what it is doing ("Idle" in amber, "Walking", "Walking to build the Farm", "Building the Farm (42%)", "Repairing the Barracks", "Claiming the Gold Mine (10%)", "+2 queued"; the Spy: "Roaming", "Walking", "Fighting", "Idle"). **A click on a row takes the camera to it and selects it; hovering a row marks it in the world** (a pulsing gold ring at its feet and an arrow over it). "All N Builders" selects the lot. The chip again, a click elsewhere or Esc closes it |
| Delete | disband the selected platoon (the troops stay selected) |
| (platoon leaders) | a platoon gets a leader when it is formed (King David if he is in it, else its longest-serving troop that is not a Builder); the platoon's tag floats over the leader with a crown, the platoon panel's row and the selection panel show it ("led by ..." / "no leader"). The leader takes the front-middle slot of its ranks on every move, so the formation forms up on it. **If it falls the platoon has no leader** ("The leader of platoon N has fallen"): nobody steps up. A member becomes leader when you take control of it (the platoon's idle members then fall in behind it) or when the platoon's members are ordered to follow it. Troops added with Ctrl + N leave the leader as he is |
| U | upgrade the selected building (nothing selected: the castle) |
| F1 | the controls overlay (every key; also the **?** button top right) |
| Enter / double click on a unit | take control of it (back to hero) |

**Making way for the unit you play** (`AVLKing::MakeWay` / `YieldTo` / `TickYield`): your own units in its path, or
about to be, step aside smoothly as it comes (its moves pass through them meanwhile), then go back to where they
stood once it has passed (one on an order is nudged off its line and walks on); one in a fight gives way at half the
push. A foe that is not fighting is shouldered aside at half the push and stays solid; a foe in a fight (attacking, or
struck in the last 3 s) does not give way at all. They step only onto ground the path grid can walk, of their own
region, never into water; terrain, buildings and walls still stop the unit you play. Units are found through the
battle's spatial hash. Logs: "X makes way", "X is back at its spot", "X stays where it made way".

**Playing an archer** (Enter / double click on her; `UVLArcherCombat`, `VLArcherCombat.*`)

| Input | Does |
| --- | --- |
| Hold right mouse (right trigger) | she takes an arrow from the quiver, nocks it and draws, and holds it as long as the button is held: she faces her aim, W A S D strafe at 55 % of the walking speed, no running |
| Let go of right mouse | she shoots where the crosshair points (on a ballistic arc). Let go early: she finishes the draw and shoots |
| Left click (left shoulder) while right mouse is held | locks the draw: she stays drawn and aiming with the right button let go |
| Right mouse while locked | shoots; the lock ends with the shot (let go and hold again for a fresh draw) |
| Left click while locked | lets the string down, no shot (so to cancel a held draw: left click twice). The Esc menu, the overview and giving her away let it down too |
| Left click otherwise | a bash with the bow: a short swipe that knocks a dummy within 1.9 m (damage 4 against an arrow's 10; the dummy rocks 7 degrees, not 24) |
| Q / E | turn the view (the right button does not, while she is played) |

**Playing a spy** (Enter / double click on it; `UVLSpy`, `VLSpy.*`)

| Input | Does |
| --- | --- |
| Hold right mouse (right trigger) | it raises the spyglass to its right eye and turns to face the way the view looks; the view looks 26 m ahead of it through a narrower lens (`LookAhead`, `ZoomFOV`); W A S D creep at 30 % of its walking speed. Let go: the glass comes down and the view comes back |
| Left click | a light blow (8 damage) |
| Q / E | turn the view (the right button does not, while a spy is played) |

Her aim (`AVLKing::GetAimPoint`, which the king's swing uses too) is where the crosshair's ray meets the world **ahead of
her**: the ray is followed only from the point level with her onwards, so a tree, roof or fence between the camera and
her, although drawn under the crosshair, never catches it and she never turns round to shoot at the camera. Friendly
units and the tree crowns the camera cuts away (`Canopy`) do not catch it either; a foe's body does (the aim is in its
middle). With the pointer shown: what the pointer is over, else the ground at her feet. The arrow is solved to pass
exactly through that point; her spread (`HeroSpread` 0.3) is put in the aim, not the launch: a point of the same
surface within distance x tan(0.3 deg) of it (2.6 cm at 5 m, 26 cm at 50 m), so a flat arrow is never carried metres
along the ground or over the top of a target. A crosshair on the sky: the arrow is loosed along the crosshair's ray.
`vl.Bow look X Y [Z]` turns the camera until the crosshair is on a point; with `vl.ArcherLog 1` each played shot logs
`aimtest` (the crosshair's point, the aim, the arrow's point) for measuring; `vl.Bow spread D` sets `HeroSpread`.

**The draw bar**: while she draws, a small bar just under the crosshair fills over the reach, the nock and the draw
(0.86 s; `UVLArcherCombat::GetDrawState`, drawn in `AVLHUD::DrawHeroBits`), white as it fills. Full, it turns green with a tick
under it: the bow is fully drawn, and letting go looses at once (earlier, she finishes the draw first). A locked draw
keeps the full bar, with a paler frame. It only shows the shot's state: an arrow flies the same however long it is held.

**Streaks**: every arrow in flight draws a thin pale-gold line along the stretch it has just flown, tapering to
nothing over `vl.Arrow.TrailLength` 0.4 s of flight, `vl.Arrow.TrailWidth` 5 cm wide at the arrow (never under a pixel
and a half on screen, so it reads from the overview); when the arrow lands the streak runs out behind it.
`vl.Arrow.Trail 0` turns them off. All of them are one camera-facing ribbon mesh (`UVLArrowTrailComponent`,
`VLArrowTrail.*`) on the arrows' actor, worked out from each arrow's parabola (nothing stored per frame), depth tested
and drawn in Shipping; the material is a dynamic instance of `M_PlacementGhost`, made at runtime (no asset of its own).

Arrows (`UVLArrows`, `VLArrow.*`) are pooled mesh components: one sticks in what it hits (a dummy rocks and carries it),
fades out and is taken back 2 s after landing (`vl.Arrow.Life`, `vl.Arrow.Fade`, `vl.Arrow.Pool`; volumes
`vl.Arrow.ReleaseVolume` 0.3, `FlyVolume` 0.1, `HitVolume` 0.26). Their material is `M_VoxArrow`
(`python3 Tools/ue_py.py Tools/ue/build_arrow_material.py`). The archer's tunables are on the component (Voxel > Archer):
`ArrowSpeed` 2300, `ArrowGravity` 980, `ArrowDamage` 40, `ReachSeconds` / `NockSeconds` / `DrawSeconds` / `LooseSeconds`, `Range` 3120,
`TowerRange` 5460 (both the old 2400 / 4200 plus 30%), `ShotInterval` 2.4, `ShotJitter`, `SpreadYaw` 1.2, `SpreadPitch` 0.8, `GroundShots` 3, `DrawMoveScale` 0.55,
and the pose (`CarryArmPitch`, `BowCant`, `ChestTwist`, `Anchor`, ...). Console: `vl.Archers` (state and how each holds the
bow), `vl.Arrows`, `vl.ArcherLog 1`, `vl.Bow draw 0|1 | shoot | lock | cancel | bash | aim X Y [Z] | off`, `vl.ShootAt <who> X Y`,
`vl.ArmGround`, `vl.AttackDummy archers [N]`.

**Both**: mouse wheel zooms (the view steepens as it pulls back; far out to 219 m in the hero view and 680 m in the
overview, which takes in most of the realm: `ArmFar`, `PitchFar`, `OverviewFar`, `OverviewPitchFar`, `ZoomStep` on the actor, Voxel > Camera; zooming
while the postcard view is up goes back to the view that zooms), Q / E or a right-button drag turn the view (**Q turns
it clockwise seen from above, to the right, and E the other way**: each the opposite of what it did before 2026-11-22, the
owner's call, in both views; `vl.Cam.KeyTurn -1` is the old way round), R turns
it back, V cycles the camera angle (Classic steep / Low / Battlefield shallow, as in the first draft; saved), C shows the postcard view (the reference picture's camera), Esc (or P) opens the pause menu (an armed
attack-ground is cancelled first; see *The interface*; in it Enter resumes, M goes to the next map, U music, V camera
angle, L look speed, I invert look, X quits).

**Trackpad**: pinch zooms, a two-finger twist turns the view. Two-finger scroll pans the overview (the ground follows
the fingers) and in hero mode turns the view (sideways) and zooms (up / down). A two-finger click is a right click;
Ctrl- or Cmd-click also sends the selected king.

**Sound underfoot.** Each time one of King David's feet comes down a recorded step plays, chosen by what the foot is
on: dirt (grass, earth, farm soil, the yards), cement (stone, cobble, gravel, the castle steps, the plaza) or wood (the
bridge, the dock, plank paths, decks, the tower's lookout); softer at a walk, louder and a little higher at a run, and
a firm one when he lands. **His steps fade with distance as the troops' do**: full within 9 m of where you are looking
(the overview's focus), silent from 45 m; in the hero view the unit you play is always at full volume. Troops on the march make a soft shuffle as a group, and a move order given by hand in the
overview (right click, Ctrl / Cmd + click, "Send them out") clicks. See *Sounds* below.

At a run his feet raise puffs of dust (also on landing and on braking hard out of a run). When he is hurt he flashes
white and his pose holds for a moment, while the game carries on (there is nothing in the sandbox that hurts him yet:
`vl.Hurt` in the console, below).

**Troops** (the swordsman, the archer and the spy, `Tools/blender/assets/troop_*.py`): in the overview select the **Barracks**
(swordsmen), the **Archery Range** (archers) or the **Castle** (the Spy, from castle level 3) and click the recruit button of the selection panel (bottom middle); several
can be queued (Shift 5, Ctrl 10). A barracks or range is raised by Builders first (*Building*). A trained troop **waits in the
building's yard**, in ranks (the barracks' fenced yard in front of its hall, the range's yard inside its rail fence;
facing the gate), until sent somewhere. Where it goes instead, the first that applies: the platoon the building's
**Joins** chips name; the **recruits' platoon** (the flag on a platoon panel row: one platoon at a time, up to 24
troops; click the flag again to clear it, and it clears itself when the platoon is disbanded or wiped out); the
building's rally point (right click on the ground with the building selected; a right click on the building itself
clears it, and its dashed line is only drawn while one is set). One that joins a platoon falls in behind the platoon's
leader and keeps with it (no leader: it walks to where the platoon stands). Select troops and right click to send
them somewhere, Enter or a double click to take control of one (walk, run, jump). A swordsman you control fights as the king does:
left click swings, through the same three-swing combo and battle stance, and the dummies take the blows; his sword has
no scabbard and is always in his hand, so F does nothing. To go back to the king,
Tab to the overview, select him and press Enter. Console: `vl.Train Barracks 3`, `vl.Control Swordsman 1`,
`vl.Control king`. Troops are imported like the king:
`python3 Tools/ue_py.py -c "KING='SM_Swordsman'; DST='/Game/Voxel/Troops/Swordsman'; DA='DA_Swordsman'; exec(open(r'<abs>/Tools/ue/import_king.py').read())"`
(and `SM_Archer` / `Archer` / `DA_Archer`, `SM_Spy` / `Spy` / `DA_Spy`).

**Levels of detail** (units and buildings). A swordsman is 63 000 triangles in 34 parts and a barracks 139 000; far
away they are a few dozen pixels. `Tools/blender/assets/voxel_lods.py` reads every unit part and building back from
its exported mesh and builds it again out of plain cubes on a coarser grid, joining like faces: units get LOD 1 of
2.5 cm cubes and LOD 2 of 5 cm cubes (swordsman 63k / 14k / 7k triangles, archer 55k / 15k / 7k, king 54k / 19k / 8k),
17 buildings a LOD 1 of 0.25 m cubes (castle 116k / 25k). What is thinner than a cube (bow strings, cape panels,
blades, banners) stays one cube thick. `Tools/ue/voxel_lods.py` makes them the LODs of the meshes in the editor (the
files in `SourceArt/Meshes/LOD` are imported, copied in and deleted again) and checks that every level's sections
sit on the mesh's own material slots (the enemy's red cloth, the placement ghost and the hurt flash go by slot).
Each part picks its level by itself, so its switch sizes are set from how tall a whole unit stands on the screen
(`UNIT`, `KING_SHARE`, `BUILDING` in that script): troops change to LOD 1 below 9 % of the screen's height (70 m in the
overview, 39 m in the hero view) and to LOD 2 below 4 % (158 m / 88 m); King David at half those sizes; buildings
from 317 m in the overview (zoom 0.67). The hero view of the played unit and those round it is always LOD 0.
Collision, distance fields and Lumen cards stay on LOD 0. Run:
`Blender -b --factory-startup --python Tools/blender/assets/voxel_lods.py -- [--set units,buildings] [--only <mesh>,..] [--render]`
(previews `SourceArt/Previews/lods_*.png`), then `python3 Tools/ue_py.py Tools/ue/voxel_lods.py 900` (editor open, not
in PIE). **Importing a mesh again drops its levels**: `import_king.py` gives them back itself at its end (from the
files in `SourceArt/Meshes/LOD`: run the Blender step first when the figure itself changed); after `import_assets.py`
of a building run `python3 Tools/ue_py.py -c "ONLY=['SM_Castle']; exec(open(r'<abs>/Tools/ue/voxel_lods.py').read())"`.

**The Builder** (`Tools/blender/assets/troop_builder.py`, reference `References/Remake/builder.png`, previews
`SourceArt/Previews/builder_*.png`): a bearded craftsman in a long navy robe with a stone-headed hammer in his right
fist (part `Hammer`, held and swung as the swordsman's sword is; `sword` / `hammer` in `SM_Builder.json`) and a frame
pack on his back (part `Pack`, on the chest: blueprints, rolled plans, a coil of rope, a glowing lantern). The
reference holds the hammer in the left hand; the rig's weapon hand is the right, so the model is its mirror image.
No cape: the robe's skirt swings with the thighs. In the game he is an `AVLTroop` of kind `Builder` ("Builder 1",
...): he walks, runs and jumps, is selected and ordered like any troop, and can be taken over (Enter / double click);
played by hand, a left click swings the hammer (the sword's swings; it knocks the training dummies). He is no fighter:
he picks no fights, cannot be ordered to attack, and the enemy commander counts him as nothing. Spawn some for testing
with `vl.SpawnUnit Builder [count] [enemy]` (in front of that side's castle; any kind works). Import:
`python3 Tools/ue_py.py -c "KING='SM_Builder'; DST='/Game/Voxel/Troops/Builder'; DA='DA_Builder'; exec(open(r'<abs>/Tools/ue/import_king.py').read())"`.
As in the first draft he is trained at the **castle** (its panel's Builder button): 120 gold + 80 food, 28 s, 110 health,
no housing but a limit of his own by the castle's level (2, 3, 3, 4, 4, 5, 6); he joins no platoon from recruitment.
**Only Builders build**: see *Building* below. At his work he swings the hammer (the up-down-up blows) and the main
game's hammer and saw sounds play.

## Building (`UVLConstruction`, `VLConstruction.*`; HUD `VLHUDBuild.cpp`)

The first draft's construction (`SRBuilding.cpp` site / StepConstruction / CancelConstruction / Demolish,
`SRPlacementPreview`, `SREconomySubsystem::PlaceBuilding`, the builders' `OrderBuild` / `StepBuild` / `LookForWork`, the
build menu of `SRHUDGame.cpp`), without the castle's building zone: the player builds where he wants, and every site rises
only while a Builder works at it.

| Building (menu tab) | Model | Cost | Time (one Builder) | Limit |
| --- | --- | --- | --- | --- |
| Farm (Economy) | `SM_Farmstead_A/B/C` in turn (each side round robin, so neighbours differ; `SM_Farmstead` while they are not imported) | 90 gold | 28 s | 3, +1 a castle level |
| Treasury (Economy) | `SM_Treasury` (gold vault, `Tools/blender/assets/treasury.py`) | 140 gold | 32 s | - |
| Granary (Economy) | `SM_Granary` (thatched food storehouse, `Tools/blender/assets/granary.py`, after `References/Remake/granary.png`) | 120 gold | 28 s | - |
| Gold Mine (Economy) | `SM_MineCliff`, on a gold vein only: a neutral mine (taken over) or the ruin of a fallen one | 140 gold | 32 s | - |
| Barracks (Military) | `SM_BarracksYard` | 110 gold | 32 s | - |
| Archery Range (Military) | `SM_ArcheryHall` | 125 gold | 32 s | - |
| Watch Tower (Defence) | `SM_WatchTower` (its lookout tag added when done) | 160 gold | 54 s | 2, +1 a castle level |

Limits count only what a side raised in the match (the map's own farms and tower are its endowment). The first draft
never built a town hall, so it is not in the menu. Prices are the first draft's (`GranaryStats` 120 gold, `TreasuryStats`
140). **Every time is twice the first draft's** (the owner's call, 2026-11-22: "if something takes 30 seconds, it should
take 1 minute"): every site, every troop's training and every level raised; the Watch Tower takes three times as long
(54 s, was 18: "archer towers need a lot longer to build"). The build menu's cards and tooltips, the recruit buttons
and the upgrade tooltips read the times from the rules (`VLBuild::Specs`, `VLRules::Troop`, `VLRules::Level`), so
they show the new ones.

| | Was | Now |
| --- | --- | --- |
| Farm, Granary (site, one Builder) | 14 s | 28 s |
| Treasury, Barracks, Archery Range, a mine's claim | 16 s | 32 s |
| Watch Tower | 18 s | 54 s |
| Swordsman / Archer (level-1 trainer) | 9 s / 8 s | 18 s / 16 s |
| Builder / Spy (at the castle) | 14 s / 12 s | 28 s / 24 s |
| Castle to level 2 ... 7 | 40, 45, 55, 65, 75, 90 s | 80, 90, 110, 130, 150, 180 s |
| Any other building to level 2 / 3 | 30 s / 40 s | 60 s / 80 s |
| King David rises again after | 20 s | 100 s (five times) |

The enemy commander builds and trains by the same rules, so it is slowed as much; its two "the army has had time to
form" marks (150 s: regroup when outnumbered, a second barracks / range when its army is behind) are 300 s. Its
attack and raid times per difficulty are unchanged (they are the earliest it may go; it still waits for its odds).
Each side may raise one of each storehouse, as in the first draft (`StoreLimitBase` 1). Each side may raise one of each storehouse, as in the first draft (`StoreLimitBase` 1). The
storehouse adds its level's storage on top of the castle's stores, so a side holds more by raising it a level. The
enemy builds each storehouse once its stock of that resource reaches 80% of what it can hold.

**The storehouses** (the first draft's `FSRStoreLevel`, `VLBattle.cpp` `FTables`; health / holds / upgrade price / castle
level the upgrade needs):

| Level | Granary (food) | Treasury (gold) |
| --- | --- | --- |
| 1 | 900 hp, holds 400 | 1100 hp, holds 400 |
| 2 | 1200 hp, holds 900; 180 gold, 60 s; castle 2 | 1450 hp, holds 900; 200 gold, 60 s; castle 2 |
| 3 | 1500 hp, holds 1600; 320 gold + 80 food, 80 s; castle 3 | 1800 hp, holds 1600; 340 gold + 80 food, 80 s; castle 3 |

What they hold is added to the castle's own stores (600 food and 600 gold at castle level 1, 1000 / 1500 / 2200 / 3000
/ 4000 / 5500 at levels 2 to 7), and income beyond the total is lost (`UVLBattle::GetStorage` / `AddStock`). A side
starts with 300 food and 400 gold; a farm brings 14 food every 6 s (20 / 27 at levels 2 / 3), so three farms fill the
castle's 600 food in well under a minute. A level-1 Granary (120 gold) lifts that to 1000; at level 3 it holds 1600,
a little more than a level-3 castle's own 1500, so one fully raised Granary doubles a mid-game kingdom's food stores.

- **The menu**: the Build button left of the selection panel (or **B**); tabs Economy / Military / Defence (clicked; Tab is
  the hero view's key here), cards with the price, the limit used, the key 1-6, the refusal (limit, gold, no Builder).
- **Placing**: a ghost of the building follows the pointer (`M_PlacementGhost`, `Tools/ue/build_ghost_material.py`: green
  glass where it fits, red where not), snapped to the half-metre blocks, **its front (gate, yard) toward the view**: turn
  the view (Q / E) to turn it, in steps of 90 degrees, and **T** turns the ghost a quarter turn clockwise on top of that
  (R stays the view's "back to north"); the footprint, its plates, the ghost's colour and the site laid all follow the
  turn, and it is kept for the next ghost of a Shift placing and the next placing of the same kind (`vl.Place turn`).
  Mines are never placed or turned. Plates of a metre on the ground show
  which ground refuses it (red: uneven by more than 30 cm, water, something standing there; a pale fringe of 2 m round
  it, red where blocked); a pill at the pointer says why, or how many trees it clears. Also refused: within 1 m of another
  building, enemy troops on it, the map's edge, a gate opening onto ground nobody can walk to. LMB places it (paid
  then), Shift + LMB places another, RMB / Esc cancels.
- **The site**: the trees in its footprint and 1.5 m round it are cleared (`AVLForest::ClearTreesAround`), the path grid
  is sampled again there (`UVLGrid::RebuildArea`), one's own troops on it step aside. Its own mesh stands hidden with its
  collision up while a copy rises course by course (14 steps, as the first draft's walls); its health rises from 15%
  with it. The selected Builders go to it, else the nearest free one. Each Builder beyond the first adds 100% speed (two build twice as fast), up
  to 4. A site does nothing (no training, housing, payouts, shots, upgrades). When done: its props (the barracks'
  training dummies, a farm's wheat, sheep, chickens or pigs: `VLBuildingProps.inl`, written by
  `python3 Tools/ue/gen_building_specs.py` from the jsons), an alert and the first draft's bell.
- **The Builders' queue (Shift)**: with Builders selected, Shift + right click on the ground (or the minimap) queues a
  walk, on a site or a damaged building of yours queues work on it, on a free mine queues its claim (paid at once),
  and Shift + click while placing lays the site at once and queues it (the ghost stays up for the next). The selected
  Builders all get the same queue and work through it together (two on a site: twice as fast); an item that has
  lapsed by its turn (the site cancelled or fallen, the building mended) is passed over. A plain order replaces the
  queue, **Esc** (after a placing or an armed click) or **Stop** clears it; a Builder with a queue is never taken for
  an idle Builder's own work or as "the nearest free Builder". While they are selected (overview only) a dashed path
  shows the order: from each Builder along the way he walks to what he is on now (**1**: the building he works on, or
  the walk he is on), then on to each queued order in turn (**2**, **3**, ...), walks blue and buildings gold, each
  numbered on a plate over its point; lapsed orders drop out and the numbers close up as items are done. A crew
  sharing one queue draws the chain once. With **Shift held while placing**, a pale pulsing segment runs from the end
  of the chain to the ghost with the number the site would get (red where it cannot go). The panel says "N orders
  queued (Esc clears)". A site laid over a queued Builder steps him aside and keeps his queue.
- **Builders at work**: right click one of your sites or damaged buildings with Builders selected (the rest of the
  selection takes the order as usual); **X**: the nearest damaged building. An idle Builder goes to work by himself on a
  site or a building below 90% health within 26 m (the enemy's: anywhere), but not on one hit in the last 10 s. A
  **building under repair is out of action** (no training, payouts or shots) until they finish (28 health a second each).
  A move order ends the job.
- **Cancel / Demolish**: a site's panel has Cancel (or Delete): 75% of its price back. A finished building of yours (not
  the castle) has a Demolish tab on the panel's top edge (or Delete): twice within 3 s, 30% of its price and its levels
  back, its training queue in full; it slumps into the ground with its props.
- **Rotate**: a finished building of yours that you raised in the match turns a quarter turn clockwise where it stands:
  the **Rotate** tab on the panel's top edge, left of Demolish, or **T** with it selected (R is the view's "back").
  Free. `UVLConstruction::Rotate` turns it about the middle of its footprint (taken on the half-metre blocks, so four
  turns bring it back exactly) and checks the turned footprint as a placement would, with the same reasons (a
  neighbour within 1 m, trees, uneven ground, water, the map's edge, enemy troops, a gate nobody can walk to); refused,
  nothing moves. Everything turns with it: collision, the props (raised again in their new places), the yard's ranks
  and whoever waits or walks in them, the archers on a tower's lookout, a Builder at its walls, and the door and
  default rally point (read from the actor); a rally point you set stays where you put it unless the walls now stand
  on it. The path grid is sampled again over the old footprint and the new. Not turned, and the tab says why: the
  castle, a site, a mine (part of its map), the map's own buildings.
- **Mines are claimed, not built**: every mine is part of its map (set into a mountain or a hill by the layout), so
  the build menu has none. A free mine (a neutral one, or one that has fallen: it is not taken away, it stands
  **abandoned**) is claimed by Builders: select them and **right-click the mine**, or select the mine and press
  **Claim** on its panel (the nearest free Builder goes). `UVLConstruction::ClaimMine` charges the old mine price (140
  gold) and makes it a site by the usual rules: it does nothing until Builders have worked it through (32 s with one,
  each further Builder adds `ExtraSpeed`, up to 4), Cancel gives 75% back and it is free again. Nothing rises and the
  mesh never moves: the map's mine stands as it is, and takes its new side's look when the claim is done. The enemy
  commander claims through the same calls (`FVLCommander::TryBuild` > `CheckPlacement` + `PlaceBuilding`); its build
  order no longer has a mine step. `vl.Build mine X Y [enemy]` claims the free mine nearest that point;
  `vl.Construction` lists every mine and whose it is.
- **The match's start**: a battle starts with no barracks or archery range on either side (the level's, if the map
  still has them, are taken away with their dummies and lamps: `ClearStartTrainers`); training starts once one is built.
- **Console**: `vl.Build barracks|range|farm|mine|tower X Y [yaw] [enemy] [near]` (a site, paid; `near`: the nearest good
  spot within 40 m), `vl.Place <kind> | menu | off` (the player's placing), `vl.Construction` (sites, Builders and what
  each does, yards), `vl.Work <building> [enemy]`, `vl.Demolish <building> [enemy]`, `vl.TrainAt Castle Builder [enemy] [n]`,
  `vl.Rotate <building> [enemy] [times]` (as T; logs its place, door, rally point, yard and a digest of the walkable
  ground round it). Test: `python3 Tools/buildings_test.py` (every building raised, working, at its limit, turned).
- **Not ported**: the first draft's site / damaged / ruin meshes and scaffold (none in voxel yet: the walls rise from the
  ground instead), the building fires, the castle's building zone, relics and old towers, the builders' list under the
  top bar's counter, the lamps (point lights) of the level's buildings on ones raised in the match.

Where a tree, a building or the ground hides the king or one of the player's troops, a gold silhouette shows through
it; another unit in front, friend or foe, does not bring it out, and the enemy's units never show through anything.
Every unit writes custom depth with its side in the stencil (1 the player's, 2 the enemy's: `VLTeamLook` in
`VLKing.cpp`, again through `AVLKing::RefreshSilhouette` after a change of `Team`); `M_Silhouette`
(`build_special_materials.py`) draws only where the nearest custom-depth pixel has stencil 1 and lies behind the scene
depth. (Where an enemy stands between a wall and one of the player's units, that part of the silhouette is missing.)

**The enemy wears red.** The units' materials `MI_King_<slot>` sit on `M_VoxUnit` (`build_special_materials.py`, part
`unit`): `M_Voxel` plus a `TeamMix` scalar that turns green vertex colours (hue about 50 to 170 degrees, olive to
leaf green: capes, cowls, hoods, tunic panels) to a red of like brightness, keeping their shading; skin, hair,
leather, cream, gold and metal are untouched (so is the Builder's navy robe: an enemy Builder looks like the
player's). The slots with cloth have an enemy twin, a child instance with `TeamMix` 1: `MI_King_paint_Enemy` and
`MI_King_sway_Enemy` (the spy's hood tail on `M_VoxSway`, where `TeamHue` 1 selects the same swap in place of the
banners' flat `TeamTint`). `import_king.py` makes the twins; `VLTeamLook` gives a unit of team 1 the `<name>_Enemy`
twin of each of its materials where one exists, at spawn and on training (`UVLBattle::SpawnTroop`). `M_Voxel` and the
world's materials are unchanged. Banners, flags, grass, flowers and
wheat sway in the wind.

## How it is made

Everything is generated by scripts, so any change can be rebuilt end to end.

| Step | Command | Writes |
| --- | --- | --- |
| Pixel textures | `Tools/.venv/bin/python Tools/blender/voxtex.py` | `SourceArt/Textures/T_Vox_*.png` |
| All assets + terrain + layout | `sh Tools/mac/blender_build_all.sh` | `SourceArt/Meshes/*.gltf`, `SourceArt/layout.json` |
| Import into Unreal (editor open) | `python3 Tools/ue_py.py Tools/ue/import_assets.py` | `/Game/Voxel/...` |
| Step sounds from the recordings | `Tools/.venv/bin/python Tools/audio/slice_steps.py` | `SourceArt/Audio/S_Step_<Surface>_<n>.wav` |
| Import the sounds (editor open) | `python3 Tools/ue_py.py Tools/ue/import_audio.py` | `/Game/Voxel/Audio` |
| Water material | `python3 Tools/ue_py.py Tools/ue/build_special_materials.py` | `M_VoxWater` |
| King David | `python3 Tools/ue_py.py -c "KING='SM_KingB'; exec(open(r'<abs>/Tools/ue/import_king.py').read())"` | `/Game/Voxel/King/DA_King` |
| A mine's hill, as a mesh (then import: `ONLY=['SM_MineMound']`) | `Blender -b --factory-startup --python Tools/blender/assets/mine_mound.py -- --no-render` | `SM_MineMound` |
| The grain ship (moored at the docks), with its far level of detail | `Blender -b --factory-startup --python Tools/blender/assets/boat.py -- --lod` (then import `ONLY=['SM_Boat']` and `ONLY=['SM_Boat']` of `Tools/ue/voxel_lods.py`); `dock.py` makes the dock's mooring | `SM_Boat`, `LOD/SM_Boat_L1` |
| Flatlands plan + ground | `Blender -b --factory-startup --python Tools/blender/assets/flatlands.py` | `SourceArt/flatlands.json`, `SM_Flat_*`, `SM_FlatPond` |
| Flatlands level | `python3 Tools/ue_py.py Tools/ue/build_flatlands.py` | `/Game/Maps/L_Flatlands` |
| Realm: ground, water, sea, backdrop, barriers, plan | `Blender -b --factory-startup --python Tools/blender/assets/realm_terrain.py -- --no-render` | `SM_RealmGround_*`, `SM_RealmWater`, `SM_RealmSea`, `SM_RealmBackdrop`, `SM_RealmBarrier`, `SourceArt/realm.json` |
| Tall trees: their further levels of detail | `sh Tools/mac/realm_rebuild.sh trees` (`assets/tree_lods.py`, import, `Tools/ue/tree_lods.py`; again after importing the trees again) | `SM_Tree2_*_Leaves_L1`, `_Leaves_L2`, `_Trunk_L2`; LOD 1, 2 of `SM_Tree2_*` |
| Units' and buildings' far levels of detail | `Blender -b --factory-startup --python Tools/blender/assets/voxel_lods.py`, then `python3 Tools/ue_py.py Tools/ue/voxel_lods.py 900` (again after importing a building again; `import_king.py` does it for its parts) | LOD 1 / 2 of `SM_KingB_*`, `SM_<Troop>_*`, LOD 1 of `SM_Castle`, `SM_BarracksYard`, ... |
| Realm level (after importing those meshes) | `python3 Tools/ue_py.py Tools/ue/build_realm.py` | `/Game/Maps/L_Realm` |
| Realm, all of the above | `sh Tools/mac/realm_rebuild.sh` (`layout`: only the plan changed) | |
| Highlands: ground, water, sea, backdrop, barriers, plan | `Blender -b --factory-startup --python Tools/blender/assets/highland_terrain.py -- --no-render` (`--only backdrop,sea` for some of them) | `SM_HighlandGround_*`, `SM_HighlandWater`, `SM_HighlandSea`, `SM_HighlandBackdrop`, `SM_HighlandBarrier`, `SourceArt/highland.json` |
| Highlands, everything (import and level too) | `sh Tools/mac/highland_rebuild.sh` (`layout`: only the plan changed; `blender`: no editor) | `/Game/Maps/L_Highlands` |
| Realm v2: ground, water, backdrop, barriers, plan | `Blender -b --factory-startup --python Tools/blender/assets/realmv2_terrain.py -- --no-render` (`--only ground,water,backdrop,barrier` for some of them) | `SM_RealmV2Ground_*`, `SM_RealmV2Water`, `SM_RealmV2Backdrop`, `SM_RealmV2Barrier`, `SourceArt/realmv2.json` |
| Realm v2: the ruins | `sh Tools/mac/realmv2_rebuild.sh ruins` (`assets/ruins.py`, import) | `SM_Ruin_Arch`, `SM_Ruin_Pillar_A/B/C`, `SM_Ruin_Block` |
| Realm v3, everything (plan, ground, ramps' sheet, sea, barriers, import, level) | `powershell -ExecutionPolicy Bypass -File Tools\windows\realmv3_rebuild.ps1` or `sh Tools/mac/realmv3_rebuild.sh` (`layout`: only the plan changed; `blender`: no editor) | `SM_RealmV3Ground_*`, `SM_RealmV3Ramps`, `SM_RealmV3Sea`, `SM_RealmV3Barrier`, `SourceArt/realmv3.json`, `/Game/Maps/L_RealmV3` |
| Realm v2, everything (import and level too) | `sh Tools/mac/realmv2_rebuild.sh` (`layout`: only the plan changed; `blender`: no editor) | `/Game/Maps/L_RealmV2` |
| Building renders | `Blender -b --factory-startup --python Tools/blender/render_buildings.py [-- NAME ... LINEUP]` | `References/Buildings/*.png` |
| Package | `sh Tools/mac/package.sh` (Windows: `Tools\windows\Package.bat`) | `Builds/Mac/SovereignRealms.app` (`Builds\Windows\SovereignRealms\`) |

- `Tools/blender/voxlib.py`: the voxel mesher (culled cube faces, baked corner shading, per-block colour variation,
  lamp positions from `glow` voxels). `voxkit.py`: shared roofs, windows, lanterns, banners. `voxmats.py`: materials.
- `Tools/blender/assets/*.py`: one generator per asset group (town hall, barracks, range and mine, farm, nature,
  props, castle, terrain, king). `ASSET_BRIEF.md` is the style guide they were written to.
- `Tools/blender/village_cam.py`: the postcard camera. `village_layout.py`: the village plan, given as **pixels of the
  reference picture** and unprojected through that camera, so things land where they are in the picture.
  `fit.py` solves each building's position and scale against its box in the picture.
- `Tools/blender/town_cam.py`, `town_layout.py`: the town's postcard camera and its plan, in world metres (heights,
  the coast, the river, paths that carry a height at every point so that a change of height becomes a flight of steps,
  buildings, fences, plots, trees, scatter). `python town_layout.py --debug` (the `Tools/.venv` python) draws the
  plan through the camera over the picture (`Saved/town_plan.png`). `Tools/compare.py <shot> <out> References/Remake/town.png`
  compares a postcard shot with the town's picture.
- `Tools/pie.py` drives Play-In-Editor from the shell (`start`, `run "vl.View postcard"`, `shot <name>`), and
  `Tools/compare.py <shot>` puts a screenshot next to the reference.
- `Source/SovereignRealms`: `AVLKing` (the character: rigid voxel parts posed in code, the diorama camera, the canopy
  cut-away), `UVLFootDust` (the dust of his running feet), `AVLGameMode` (console commands `vl.*`), `AVLHUD` (the
  whole interface: the first draft's HUD and menus, see *The interface*), `AVLAmbience` (cube motes and chimney
  smoke), `UVLGrid` (where units can walk, and routes), `UVLCommand` (selection, platoons, formations, orders, the
  watch tower's garrison).

## Terrain rule: no hard edges in open ground (owner's rule, 2026-11-21)

- **No abrupt ledges on open ground.** Where the landscape rises in the open (meadow, fields, the plain round a
  town), it must rise gradually.
  - Use shelves of one block that wander and step back, or a soft slope.
  - Never a long, straight, sheer bank of exposed dirt a metre or more high cutting across flat grass.
  - Bad example: `References/Remake/terrain_hard_edge_bad.png`.
- **Sheer faces only where there is clearly a wall or a mountainside.** A cliff of rock or stone that reads as a
  mountain, a gorge or a bluff, with terraces stepping up it, may stand sheer.
  - Good example: `References/Remake/terrain_cliff_ok.png`.
- **Applies to every map.** Every layout (`realm_layout.py`, `highland_layout.py`, `town_layout.py`, `flatlands.py`)
  and every new map keeps to this. The same spirit as the mine hills, which roll off in wandering one-metre shelves.
  - How: `Tools/blender/softground.py` `soft_rise` turns an edge into four shelves of a quarter block, each 1.4 to
    3.2 m deep and wandering on its own, centred on the old edge: walkable, and a building may stand across one
    (`VLBuild::LevelTolerance` is 30 cm). The realm's west terrace and the enemy's plateau (both a metre up) use it;
    they were the straight one-metre banks of the bad example. Left sheer on purpose: the mountain, the highland, the
    ridge, the gorges, the sea cliffs, the highlands' bluffs and the Crown. (The watch towers' round mounds were left
    sheer too: no more, see the tower rule below.)
  - Check: `Tools/.venv/bin/python` on a plan's `heights()` and look for drops of a metre or more between
    neighbouring cells where both are open ground (not `wild`, water, hazard or steps). On the realm and the
    highlands only the towers' mounds are left.
- **No coarse version where the player normally looks** (owner, same day). Bad: `References/Remake/lod_coarse_bad.png`
  (an island of big flat leaf cubes on a blocky base: the backdrop's 2 m rock stacks at sea). Good:
  `References/Remake/lod_detail_good.png`, `References/Remake/lod_detail_good_2.png` (an island in full detail: a
  proper tree, a grassy top, a band of dirt and stone, rocks at the waterline). The same goes for the coarse forest of
  `References/Remake/trees_wrong_set.png` (the mountain's baked 1 m block trees, and the tall trees' half-metre far
  version, which the overview drew from 61 m, nearer than its usual zoom).
  - Trees: one forest everywhere (the wild woods too, `Tools/blender/wildwoods.py`); LOD 1 is the crown at its own
    0.25 m scale without the lace, LOD 2 the half-metre version only from 280 m (D, C; 320 m A, B) from the hero
    camera, 373 m in the overview (`Tools/ue/tree_lods.py`).
  - Plants: their reduced far version from 170 m (grass), 180 m (flowers), 260 m (bushes) (`Tools/ue/plant_lods.py`).
  - Units (LOD 1 of 2.5 cm cubes from 70 m in the overview) and buildings (0.25 m cubes from 317 m) are well under a
    pixel's difference there and stay as they are.
  - The backdrops have no rock stacks at sea any more, and no 2 m leaf blocks within 70 m of the playable edge.
- **A watch tower never stands on a drum** (owner, 2026-11-22: "this is bad, remember that, stop doing that").
  Bad: `References/Remake/tower_cylinder_bad.png` (a tower on a round plinth with sheer walls of dirt and stone and a
  stone stair up its side). A tower stands on **level ground**, or on a **natural mound** that rolls off gradually in
  wandering, irregular shelves, as the mine hills do (`minehill.hill`): not a circle, no sheer walls, no stair needed.
  - Realm v2: the towers by the home mines stand on the level ground; the two hill towers on `KNOLLS` (4 m, a level top
    of 10 m, the slope 22 m long in quarter-block shelves from a wandering foot: anyone walks up from any side).
  - The realm (`L_Realm`): its two towers stood on such drums (3 m); they now stand on their side's level ground
    (`realm_layout.py` `SHELF`, `KNOLL`: the terrace and the plateau, +1), and their flights of steps are gone.
  - The highlands and the Flatlands still have the old mounds (test grounds; not rebuilt).
- **Islands are big enough to build on** (owner, same day). Rounded squares, flat on top at the land's level, a band
  of dirt over stone and rocks at the waterline; a tree at one edge, not a grove. Each map has one big islet per side
  (about 30 m across, 550 to 590 m2 of walkable top: a barracks' or a farm's footprint fits) reached by a footbridge
  (`SEA_BRIDGES`) from a little bay in its side's coast; the smaller ones (14 to 20 m) nobody reaches. The realm's
  divider island is flat, open ground from 42 m south of the crossing to 70 m north of it (two lobes of 760 and
  980 m2, each takes a barracks); only its two points are bare rock.

## The realm (`L_Realm`): the battle map

After `References/Remake/battlefield.png`, at twice its size each way: 416 m square, the same buildings twice as far apart. `Tools/blender/realm_layout.py` is the plan (built on
`town_layout.py`), `realm_cam.py` its postcard camera, `assets/realm_terrain.py` the meshes, `Tools/ue/build_realm.py`
the level. `Tools/.venv/bin/python Tools/blender/realm_layout.py --debug` draws the plan from above
(`Saved/realm_plan.png`: hazard edges in red) and prints the balance table.

- **South-west**: the player's town on the plain: the castle and its plaza, the dock under the west cliff. Nothing
  else stands at the start but its mine and the mine's tower: no farm, no cottages, no second mine, no barracks and no
  archery range on either side: Builders put them up in the game, and the ground round the castle is open, level
  meadow for them. **North-west**: the mountain: the player's one gold mine is set into the mountain's foot at the
  north end of the west terrace (136 m from the castle's door), its watch tower on the level terrace 19 m from the
  mine's mouth, beside the last stretch of the mine road; a neutral mine in the mountain's east face.
- **Middle**: the river from the highland in the north to the sea in the south-east: the upper reach, a fall into the
  gorge (water 2.25 m under the banks), the divider island that splits it into two channels, two footbridges over the
  island (the only crossing), a second fall into the lower gorge (4 m down), a third into the sea. The island is
  open, level grass from 42 m south of the crossing to 70 m north of it (`ISLAND_FLAT`; two broad lobes either side
  of its narrow waist at the bridges, each with room for a barracks); only its two points are bare rock.
- **Off the coast**: five islets (`ISLETS`), flat-topped rounded squares at the land's level. The two big ones (30 m)
  are each reached by a footbridge (`SEA_BRIDGES`): the player's from a little bay in the south cliff below its town,
  the enemy's from its south coast east of the river's mouth; the three smaller (18 to 20 m) nobody reaches.
- **North-east**: the enemy's base on a plateau one metre up: the same, laid out differently (the castle faces west,
  its mine set into the east ridge to the south-east, 131 m from its door, the tower on the level plateau beside that mine, as
  the player's). **South-east**: the hill with the second neutral mine.
- **Mines are set into the ground they stand by, and nobody builds one**: every mine is placed by the plan (a Builder
  claims a neutral or fallen one where it stands). Two ways, both in `Tools/blender/minehill.py`:
  - **in a wall** (`References/Remake/mine_in_wall.png`; `minehill.embed`): no level pad round the mine and no trench.
    The cliff stands as it is beside the mine and over it, its terraces run on over the mine's rock, and only the
    portal's bay (the landing, the rail ramp, the steps) is cut out of the rock, with 2 m of level ground before it for
    the road. The home mines: the realm's in the mountain's foot and the east ridge (whose wall comes out to it), the
    highlands' in the foot of each side's bluff (which comes out to it); the mine stands 2.5 m proud of the face.
    The realm's neutral mine in the mountain's east face likewise.
  - **in a hill** (`References/Remake/mine_mound.png`; `minehill.hill`, `HILLS` in the layouts): the neutral mines of
    the realm's east bank, of the highlands' two tors and of the Crown's rock. Those rocks are hills now, rolling off in
    shelves of a metre from a wandering foot (they were drums with sheer sides), and each mine has the hill's shoulders
    round it: highest behind it, down both its sides in terraces (a 1 m bank at the foot, which no unit steps onto, then
    0.5 m and 1 m), open before its mouth. The town's mine has the same hill; the Flatlands' stands in `SM_MineMound`
    (`assets/mine_mound.py`), the mesh of that hill.
  Every mine actor carries the tag `Mounded` (it is reached, worked and struck at its front).
- **Roads** (`PATHS` in `realm_layout.py`): only each castle's road to the bridge, to its mine (with the steps up
  to the tower by it; the player's mine road also steps up onto the west terrace) and the player's to the dock. None to the neutral mines or anywhere else: that ground is
  grass to build on, and the lanterns stand only along the roads that are left.
- **Beyond the edge** (`SM_RealmBackdrop`, 2 m voxels, no collision): slopes and snowy mountains to the north and the
  east, wooded from 70 m out (no rock stacks at sea any more: see the terrain rule). Nobody gets there: the map's edge has the usual hidden walls.
- **Barriers** (`SM_RealmBarrier`, tag `Barrier`): hidden walls half a metre thick on the edge of the plan's hazard
  map: both banks of the whole river and the tops of the falls, the island's two rocky points, the rim of the cliff
  over the sea all along the west and south coasts and round the islets, the sea round the dock's planks. They block
  pawns only (the path grid's capsule test sees them; clicks, arrows and the camera do not). The bridges (the sea
  bridges too) and the dock are open.
  `UVLGrid::ApplyLevelCollision` enforces this when play starts in every level (barriers and the hidden walls round
  the map's edge: pawns only; `Water`: nothing; `Backdrop`: no collision), and the builders now clear the components'
  "use default collision", without which the mesh asset's BlockAll came back when the level was loaded again (hidden
  walls then stopped clicks, sending move orders to the cliff's rim, and arrows).
- **Sides** (the contract with the game code, also in `SourceArt/realm.json` under `teams`): every building actor has
  the tags `Selectable`, `Name:<kind>` and `Team:0` (player), `Team:1` (enemy) or `Team:Neutral` (the two contested
  mines, the bridges). `TargetPoint` actors carry `TeamStart:0` / `TeamStart:1` (in front of each castle; the
  PlayerStart is at `TeamStart:0`) and `Rally:0` / `Rally:1` (where a side's first troops stand: `RALLY0` / `RALLY1`, open ground by its road to the bridge). The enemy's cloth is
  `MI_Vox_cloth_Enemy` (red: `TeamMix` / `TeamTint` of `M_VoxSway`).
- **Balance**: `realm_layout.balance()` measures the walking distances from each castle's door (to the bridge, its
  mine `own_mine`, its tower, the neutral mines, the other castle; and from the mine to its tower and to the bridge)
  on the plan; they are in `realm.json` under `balance` (player / enemy: bridge 122.8 / 137.5, own mine 123.6 / 130.6,
  tower 123.4 / 130.2, mine to the bridge 156.3 / 170.0; the terrace and the plateau can be walked onto anywhere
  since their edges became shelves, which shortened the player's way to its mine by 13 m). Move a building in `BUILD` and run the script with `--balance`
  to see them again.
- **Ground to build on**: `MEADOWS0` / `MEADOWS1` in `realm_layout.py` are the flat, open meadows round each side's
  buildings (about 14 000 m2 a side); the forest between them can be cleared. `balance()` also measures this
  (`realm.json`, `balance.buildable_m2`: level ground a side can walk to and is nearer to than its foe, less roads,
  buildings, plots: total / meadow / open / wooded).
- **The forest** (`AVLForest`, `VLForest.*`; the level's actor `Forest`): every tree and all the undergrowth are
  instances of one hierarchical instanced component per mesh, not an actor each (12 900 instances).
  Budget: `TREES` in `realm_layout.py` (8 A, 8 B, 110 C, 1350 D) and the wild woods on the mountain, the highland and
  the ridge (`Tools/blender/wildwoods.py`: about 360 more D and C, the same trees; they were `SM_RealmWoods`, one
  mesh of 1 m block trees, 45k faces, which read as a coarse wrong forest): 1739 trees, 23.2 M faces if all were near,
  8.8 M at LOD 1, 1.9 M at LOD 2 (`realm.json` `trees.lod_faces_m`). The tall trees' levels of detail
  (`assets/tree_lods.py`): LOD 1 the crown at its own 0.25 m scale without the 0.125 m lace (D leaves 8.6k -> 2.1k
  faces, the trunk its own), from 60 m (D) to 95 m (A) from the hero camera (80 to 127 m in the overview); LOD 2
  half-metre blocks (D 0.9k faces in all) from 280 m (D, C) and 320 m (A, B). Estimated tree faces in a view (the
  plan's trees through the overview's camera): over the woods at the usual zoom 0.07 M before (all at the old half-metre
  version) -> 0.38 M, halfway out over the middle 0.18 -> 0.72 M, pulled all the way back 1.16 -> 1.31 M; grass and flowers are not drawn beyond 400 / 440 m (`build_realm.CULL`; it was 230 / 260 m,
  and they went as soon as the overview pulled back a little: it is 190 m from what it looks at halfway out, and the top of the view is
  further), the bushes always are. To pay for that the small plants have a cheap far version, an eighth of the triangles, from 170 m
  (grass), 180 m (flowers), 260 m (bushes) from the hero camera (it was 110 / 120 / 170 m; the overview switches at 4/3 of these): `Tools/ue/plant_lods.py` (in `realm_rebuild.sh trees`; again after importing them again). The
  farms' wheat, sheep and vegetable beds are single actors with no cull distance, here and in `L_Town` / `L_Flatlands`: drawn at any zoom. Where nobody can go
  (the mountain, the highland, the ridge) the trees are the forest's own (see above); nothing builds there.
  The ground's flat faces are joined two by two where nothing tells them apart (`realm_terrain.merge_quads`).
- **Clearing trees for a building** (for the building mechanics to come): `AVLForest::ClearTrees(World, Centre,
  HalfExtent, YawDegrees, Margin = 150, bPoof = true, bDryRun = false)` (world cm; also `ClearTreesIn(World, FBox2D,
  Margin)` and `ClearTreesAround(BuildingActor, Margin)`, which uses the building's own mesh bounds as it stands)
  removes every tree whose trunk is within `Margin` + its reach (A 3.6 m, B 3.4, C 2.2, D 1.3, times its scale) of
  the footprint: trunk, crown and so their shadow; and the undergrowth inside the footprint. It then samples the path
  grid again just there (`UVLGrid::RebuildArea`: floors, joins, regions; a few ms) so units walk there at once, and
  puffs dust where the trees stood. It returns the number of trees; `bDryRun` only counts (what a placement preview
  would show). Console: `vl.ClearTrees X Y [Radius]`, `vl.ClearTrees <building name> [Margin]`, `vl.ClearTrees
  buildings`, each with `count` at the end to only count; `vl.ClearTrees` alone logs the forest's size. The level is
  built by the same rule (`realm_layout.tree_blocked`): no tree within 1.5 m + its reach of a building or its gate.
  Test: `Tools/realm_test.py trees`.
- **Cost** (PIE in the editor, 1612 x 830 rendered, M5 Pro): about 50 fps as the king and in the overview at its usual
  zoom, the same as the town measures that way; 38 fps with the overview pulled all the way back (680 m, most of the
  map in view: the base pass is what grows). The path grid takes 1.5 s to sample when play starts (832 x 832 cells).
  The sun's shadows reach 1100 m here (`build_realm.far_shadows`), or the far overview would have none.

## The highlands (`L_Highlands`): the second, bigger battle map

540 m square (the realm's 416 m and 30 % more each way, 1.7 times the ground), made the same way by its own scripts,
written from the realm's: `Tools/blender/highland_layout.py` (the plan; `--debug` draws `Saved/highland_plan.png` and
prints the balance table), `highland_cam.py`, `assets/highland_terrain.py`, `Tools/ue/build_highland.py`,
`Tools/mac/highland_rebuild.sh`, `Tools/highland_test.py`. In the New Game menu as "Highlands" (map 3 of `AVLHUD`;
`vl.Map highlands`); the realm is still the default. It carries the realm's contract (the tags, `TeamStart:0/1`,
`Rally:0/1`, the PlayerStart; `SourceArt/highland.json` with `teams`, `markers`, `balance`, `meadows`, `buildable`).

- **Two sides, balanced but not mirrored.** Each has the same kinds of things, laid out its own way (`GROUND`, `HOMES`,
  `side_paths`, `MEADOWS0/1`, `GROVES0/1` in the plan), and the plan was tuned until the walks from the two castles
  agree within 5 % (the table below). Only the middle, the river and the Crown, is the same from both sides. Castles,
  farms and cottages all front south or west, towards the camera. No barracks and no archery range: those are built.
  Beyond the edge: sea to the west, the south and the south-east; the highland (to 44 m, the backdrop's mountains to
  150 m) to the north, the ridge to the north-east.
- **The player's home** (south-west): the castle (facing south) on the plain, the dock under the west cliff (stairs
  down 6.5 m). Nothing else at the start but the mine and its tower (no farm, no cottage, no second mine: Builders
  raise what is wanted). In the map's corner, over the sea, **the bluff**: a flat-topped hill 6 m up, 6260 m2 to
  build on, climbed by one stair (a flight west along its north face to a landing at 3 m, a turn, a flight south onto
  the top), a peak on its corner (to 32 m; nobody climbs it). The one gold mine is cut into the bluff's east foot,
  94 m from the castle's door, the watch tower on a mound (3 m) before its mouth. North of the home a spur of rock (to
  24 m) runs in from the west coast, its pass near the coast; behind it the north vale with the neutral mine (facing
  south) in its tor.
- **The enemy's home** (north-east): the castle faces west; the dock under the east cliff. Its bluff is **the shelf**,
  a long terrace under the highland's wall (6221 m2 on top), climbed straight from the south by two flights in a line
  with the landing between. The one mine is cut into the shelf's south foot, 91 m from the castle's door, its tower
  on a mound east of it. South-east of the home **the Horn**, a lone rock (24 m), stands over the pass of a spur that
  runs in from the east coast at a slant, the pass in its middle; behind it the south-east with the neutral mine
  (facing west) in its tor.
- **The middle: the Crown.** The river runs from the great fall off the highland (12 m) down a gorge 4 m deep, with
  palisades of rock up to 8 m high along stretches of both banks, and parts round a mesa 73 x 110 m and 5 m over
  the banks (9 m over the water). One bridge from each bank, then a stair of ten metres' run up through the rim. On top:
  5600 m2 of flat open ground (towers, buildings), a ring of sixteen standing stones round the rim, and in the middle
  a rock with **two neutral gold mines back to back** (the twin lode, tagged `Rich`; their doors face north and south,
  as far from one bridge as from the other). They are gold veins for `UVLConstruction`: any actor tagged
  `Name:Gold Mine` and `Team:Neutral` is one, so a Builder raises a Gold Mine on either and takes it (tried:
  `vl.Build mine 0 1000` lays the site on the south one and sends a Builder; nothing reads `Rich` yet). A
  `TargetPoint` tagged `Crown` marks the mesa for rules to come.
- **The long way round**: a bridge far up the river (28, 170) and one far down (-28, -170), on tracks. Each side has
  one about 132 m from its castle; the other is 320 m away.
- **The rest of the ground**: lone crags, meadows at the places worth holding, and groves rather than one forest:
  1541 trees (A 8, B 8, C 124, D 1401; 115 of them the wild woods on the peaks, the spurs, the highland and the ridge,
  which were `SM_HighlandWoods`, 1 m block trees: `Tools/blender/wildwoods.py`), 11 440 plants. Tree faces: 20.6 M
  if all were near, 7.9 M at LOD 1, 1.7 M at LOD 2.
- **Off the coast**: nine islets (`ISLETS`), flat-topped rounded squares at the land's level. One big one (30 m) off
  each side's coast, each other's half turn, reached by a footbridge (`SEA_BRIDGES`) from a little bay in the cliff:
  the player's off the west coast north of the dock (-253, 15), the enemy's off the east coast (253, -15); about
  550 m2 of walkable top each, a barracks or a farm fits. The seven smaller (14 to 20 m) nobody reaches.
- **Roads**: castle to plaza, to the Crown's bridge, to the mine (and the tower's steps), up the bluff, to the dock; dirt tracks through the pass to the neutral mine and to the two far bridges.
- **Barriers** (`SM_HighlandBarrier`, 5003 m of wall): the realm's rule (sea, cliff rim, river banks) and one more: the
  rim of every drop where people walk (`rim` in `heights()`: ground with something more than 1.5 m lower within a
  metre, roads and steps left open): the bluffs, the landings, the mounds, the Crown. A drop of 1.5 m or less (the top
  of a stair's cutting) has none.
- **Balance** (`highland_layout.py --balance`, metres walked from the castle's door, player / enemy): the Crown's
  bridge 122.7 / 121.0, its top 147.0 / 145.6, its mines 173.3, 172.0 / 171.0, 171.9, own mine 94.4 / 91.1,
  bluff top 89.2 / 89.9, tower 101.4 / 100.8, dock 133.4 / 137.7, neutral mine
  on its own bank 245.7 / 239.8, on the far bank 329.3 / 325.6, near bridge 131.1 / 131.3, far bridge 322.0 / 319.8,
  castle to castle 342.7; own mine to the Crown's bridge 212.2 / 212.1. Ground to build on (m2): total 52 486 /
  52 495, of it open meadow 34 704 / 33 432, the bluff's top 6709 / 6579, its half of the Crown 2676 / 2774 (the
  realm: about 16 000 of meadow a side).
- **Tests** (`Tools/highland_test.py`). With a match running (`vl.StartMatch 0` first, or the king does not move):
  `routes` (30 found by the path grid, as long as the plan says; two of them out to the islets) and `barriers` (27
  edges he runs at and stops short of, 4 on the dock, 10 crossings: the four bridges, the two sea bridges, the Crown's
  stair, the bluff's two flights, the dock). Without a
  match (in one the enemy fights the test's troops and its Builders fell trees): `trees` (the count, none against a
  building, clearing) and `march` (over the Crown both ways, 340 m in 52 s at a run; an archer up the tower). A match
  starts there as a battle (12 buildings, 6 a side).
- **Cost**: ground 3.74 M faces in 398 tiles of 27 m (the realm 1.93 M), water 0.28 M, backdrop 0.21 M; the path grid
  1080 x 1080 cells, sampled in 2.4 s. PIE, a match running, measured one after the other in one editor session:
  overview over the home at its usual zoom 40 to 42 fps (the realm 37), over the middle 31 to 39 (33), pulled all the
  way back 36 to 38 (33), as the king 36 to 44 (37): the same as the realm within what the measure wanders. (That session gave the realm
  less than the 50 fps noted above.)

## Realm v2 (`L_RealmV2`): the third, biggest battle map

An island, 640 m square with the sea round it. After `References/RealmV2/`: `PLAN.md` (the owner's brief),
`layout_annotated.png` and `layout_island_suggestion.png` (the layout: the second is the later word), and for the look
and the scale `visual_inspiration.png`, `scale_and_clouds.png`, `terrain_pockets.png`, `port.png`. Made by its own
scripts, written from the highlands': `Tools/blender/realmv2_layout.py` (the plan; `--debug` draws
`Saved/realmv2_plan.png` and prints the balance table), `realmv2_cam.py`, `assets/realmv2_terrain.py`,
`assets/ruins.py`, `assets/ports.py`, `Tools/ue/build_realmv2.py`, `Tools/ue/realmv2_lods.py`,
`Tools/mac/realmv2_rebuild.sh`, `Tools/realmv2_test.py`, `Tools/mac/realmv2_perf.sh`. In the New Game menu as "Realm v2"
(map 0 of `AVLHUD`; `vl.Map realmv2`). The level is fixed; the scripts are the tool that makes it (everything is
seeded). It carries the realm's contract (the tags, `TeamStart:0/1`, `Rally:0/1`, the PlayerStart;
`SourceArt/realmv2.json` with `teams`, `markers`, `balance`, `buildable`, `sky`).

- **Scale** (why these sizes): a soldier is 1.8 m, the castle 12 m high on 14 x 11 m, a watch tower 21 m, a farmstead
  23 x 19 m, a tall tree 8 to 17 m; a unit walks 4.2 m/s and runs 7.6. The map is 640 m (the realm 416, the highlands
  540), the island about 590 m across: castle to castle is 580 m on foot (76 s at a run, 2 min 20 s at a walk), each
  home mine 95 to 100 m from its castle (as on the other maps), a neutral mine 150 to 560 m. Bigger would make marches
  a chore; smaller would not hold five mines, three contested places and a mountain that reads as colossal. **The
  mountain is 184 m high** (15 castles, 100 soldiers) on a massif 200 x 225 m, a third of the island's width; it was
  first 95 m, and the owner asked for about twice that. The ruins plateau is 12 m up (a castle's height), the upper
  terrace 22 m, the bluffs 7 m, the hill towers' knolls 4 m; the sea and the channels lie 6 m under the land.
- **The island.** `COAST` (a rounded square that wobbles; straight at the two ports): sea cliffs 6 to 9 m with ragged
  ledges and rocks at their foot, five coves with a beach (`BEACHES`: the land comes down in shelves), five islets
  (`ISLETS`: rocks with a tree, nobody reaches them). The sea is `SM_RealmV2Sea`, one sheet 1200 m square; nothing
  lies beyond it (no backdrop).
- **Channels round the mountain** (`RIVER_LOW`): two arms of the sea come in from the north coast, run down either
  side of the massif in **ravines 6 m deep and 26 m wide** (15 m of water, terraced walls a metre and a half a step)
  and meet south of the ruins; a third comes in from the west coast. Nobody crosses them but by the **nine bridges**
  (`BRIDGES`; all at level 0, each on a neck of land that comes out to a narrow channel 5 m wide).
- **The massif** (the land between the arms). The mountain (`mountain()`, `M_POLY`, `PEAKS`): eleven peaks, the
  summit in the middle, benches 10 m apart on its shoulders up to about 100 m (grass and the forest's own trees on the
  treads, cliffs between), crags of 2, 4 and 8 m, bare rock above, snow from 150 m. Nobody climbs it. On its south
  shoulder the **upper terrace** (22 m: the old arch) and under that the **ruins plateau** (12 m, 8500 m2 of level
  ground, pillars round a paved court): climbed by three ramps (south, west, east; a shelf of a quarter block every
  1.2 m and more) and a stair between the terraces. A creek falls 30 m out of the mountain's wall onto the plateau,
  crosses it (a stone slab carries the road over) and falls 18 m off its south edge into the east arm. Round the
  mountain's feet: the west foot's pocket, the **north crossing** (the saddle between the west arm and the mountain's
  north-west buttress), the ground behind the mountain (50 m to the north coast, a pocket to build in), the east shelf.
- **Pockets, forest, hills** (owner: "too much open land"): the level, open ground is the plan's pockets (`FLATS` of
  kind `build`, 1800 to 9000 m2 each: the two homes, three more round each, six neutral ones) and the zones; everything
  else that can be walked is forest (`wood()`: four places in five) with roads through it, twelve low rounded hills
  (`HILLOCKS`, 3 to 5 m, wooded, walked over from any side) and five rock plateaus with trees on top (`MESAS` of
  top `wild`).
- **Layout** (player south-west, enemy north-east, as both layout pictures):
  - `castle0` (-176, -118), facing south; `castle1` (246, 152), facing west.
  - mines: **W** `mine0`, the player's, in the west bluff's east face; **NE** `mine1`, the enemy's, in the north
    bluff's south face (both `minehill.embed`, in a wall); **NW** `mine_nw` and **SE** `mine_se`, neutral, each in its
    tor (`minehill.hill`); **centre-east** `mine_c`, neutral, in the mountain's east wall (`embed`). The island's
    shape moved none of them.
  - watch towers (the tower rule: no drums): `tower0` / `tower1` on the level ground beside the home mines;
    `tower0b` (W) and `tower1b` (E) on their knolls (`KNOLLS`), over the ways north and south along each coast.
  - **ports** (`PORTS`, scenery; reference `port.png`): the player's on the west coast 120 m from its castle, the
    enemy's on the east coast 50 m from its castle. Each: a quay cut into the cliff's foot 1 m over the sea (the
    island's own rock, 13 x 40 m), a stone stair down the cliff to it (5 m), the pier (`SM_Dock`) with a boat moored
    (`SM_GrainBoat` when that mesh exists, else `SM_Boat`; the instance is tagged `Moored`), and from `assets/ports.py`
    `SM_Port_Warehouse` (green roof, awning, anchor banner), `SM_Port_Crane`, `SM_Port_Arch` (the tunnel's mouth in
    the cliff) and `SM_Port_Tower` (the harbour tower on the cliff: green roof in two tiers, a lit lantern room).
  - contested zones (terrain only; `TargetPoint`s tagged `NorthCrossing`, `SouthCrossing`, `Ruins`, which the enemy's
    commander reads as markers): the north crossing, the south crossing (the double bridge over the joined arm, on a
    rock in midstream, and the open ground before it), the ruins plateau.
  - crossings: `nw` and `n` (round the mountain's north), `w` and `s` (the player's ways onto the massif), `e` and
    `se` (the enemy's), `big_w` + `big_e` (the south crossing), `trib` (the player's way to the north-west).
- **Terrain maths** (`realmv2_layout.py`; the ideas, not the code, are Luanti's Carpathian mapgen's and
  FastNoiseLite's): `fbm` (layered value noise), `ridged` (each octave 1 - |n| squared and weighted by the octave
  before: sharp crests, smooth feet), `warp` (domain warping: the massif's outline and the peaks are looked up at
  places pushed about by two layers of noise), `steps` (Carpathian's stepped mountains: a height cut into risers and
  treads). The mountain = a shoulder that rises quickly from the foot + the peaks' envelope (a 4-norm of cones with
  hollow flanks, so ridges join the peaks) x a ridged sum + finer ridges, then benches, then crags (heights rounded to
  1, 2, 4 or 8 m by a slow noise). The lowland = one slow noise (0 to 3.6 m), blended to its level at every place of
  the plan (`FLATS`), rounded to quarter blocks: it rises in shelves of a quarter block 2.5 m and more deep (the
  terrain rule; `hard_edges()` counts drops of a metre between open cells). A ramp (`RAMPS`) is a floor rising evenly,
  the hillside beside it stepping away in one-metre terraces.
- **The sky** (`AVLSky`, `VLSky.*`; `realmv2_layout._sky()`): 32 voxel clouds (14 small puffs low round the
  mountain's flanks at 58 to 120 m, 12 banks beyond the coast, 6 wisps over the channels), each fourteen white boxes
  drifting about its place, unlit (`M_VoxSky`). A cloud is puffed away when the camera comes within 70 m of it or rises
  to 12 m under it, so none ever lies between the overview camera and the ground; they are not on the minimap. 7 flocks
  of 6 birds (three cubes each: a body and two wings that beat and glide) wheel at 62 to 226 m: some at the clouds'
  height, some under, some over. No collision, no shadows; two instanced components, 574 cubes. (The project had no
  birds; the loops and the beat-and-glide are after the first draft's `SRBirds`.)
- **Balance** (`--balance`, metres walked from the castle's door, player / enemy): own mine 99 / 95, its tower 75 /
  82, hill tower 200 / 154, the ruins 415 / 315, north crossing 346 / 426, south crossing 197 / 443, the north-west
  mine 352 / 561, the centre-east mine 436 / 152, the south-east mine 455 / 367, castle to castle 582. The plan is not
  symmetric (it is the layout pictures'): the enemy is nearer the massif and the centre-east mine, the player has more
  ground and the nearer way to the north-west mine.
- **Cost.** Ground: 387 tiles of 32 m (`SM_RealmV2Ground_*`, tagged `Ground`), 5.40 M faces after joining (the realm
  1.95 M, the highlands 3.86 M), each tile with **two further levels of detail that are the same shape**
  (`merge_far`: flat faces of one plane and one material joined into quads of up to 1 m, from 110 m from the hero
  camera, and up to 4 m, from 280 m; the overview at 4/3 of these; what goes is the block-to-block tint and the corner
  shading; `Tools/ue/realmv2_lods.py`, run by the rebuild after every import): 2.02 M faces at LOD 1, 1.64 M at
  LOD 2. Water 0.43 M (its undersides left out), the sea 937 faces, the barrier's walls. Forest (`TREES`): 3621 trees
  (A 12, B 12, C 231, D 3366; 339 of them the wild woods of the mountain's benches and the rock plateaus): 45.7 M faces
  if all were near, 17.4 M at LOD 1, 3.8 M at LOD 2; 14 760 plants; the sky 574 cubes; the path grid 1280 x 1280 cells.
  Measured (`sh Tools/mac/realmv2_perf.sh`: PIE in the editor, a match running, GPU ms; M5 Pro): before the LODs (the
  valley with its backdrop) at the base 26.5, the mountain in view 24.1 (its base pass 10.3), the whole map 59.1; with
  them 19.0 / 20.8 (base pass 5.3) / 25.7; the island as it is now 18.3 / 21.1 / 25.0. `L_Realm` measured the same
  way in the same session: 18.1 at its base, 23.2 over the whole map. (The realm's 15.5 ms is a packaged build's
  figure; this map has not been measured packaged.)
- **Checks** (`Tools/realmv2_test.py`, PIE with a match running): `routes` (from the two castles to every mine, tower,
  zone and buildable area: all found, as long as the plan says), `build` (a barracks laid in every buildable area and
  zone and on the plateau and the bluffs, a tower on the upper terrace), `stuck` (every unit on the plan's ground).
  Movement and battles are tested apart.
- **Town and Village removed** (2026-11-22): `L_Town` and `L_VoxelVillage`, their menu entries, `MapsToCook`, the
  town's level builder (`Tools/ue/build_town.py`, `Tools/town_rebuild.sh`, `assets/town_terrain.py`) and the 76 assets
  only they used (`Saved/town_village_only.json` lists them: the village's `SM_Terrain_*`, the town's
  `SM_TownGround_*`, `SM_TownWater`, `SM_TownSea`, the windmill and its sails, the hay cart, the old `SM_Tree_A..D`,
  the banner posts, the arrow barrel, the weapon rack, the sacks, the stone steps). Kept: `town_layout.py` /
  `town_cam.py` (the battle maps' plans are built on them), `village_layout.py` and `SourceArt/layout.json` (the
  Flatlands take the buildings' sizes from it), `build_level.py` (the other builders run on it), the four fence
  meshes (the plans' plot code places them), and every asset another map or the code names.

## Realm v3 (`L_RealmV3`): the fourth battle map, the compact island

An island 416 m square, after `References/RealmV3/`: `concept_plan.png` and `concept_threequarter.png` (the owner's
concept), `PLAN.md` (the design: sizes, elevations, every coordinate, how it answers the brief) and `PROGRESS.md`
(the state, the checks and their numbers). Made by Realm v2's pipeline, copied: `Tools/blender/realmv3_layout.py`
(the plan; `--debug` draws `Saved/realmv3_plan.png`, `--balance` prints the routes), `realmv3_cam.py`,
`assets/realmv3_terrain.py`, `Tools/ue/build_realmv3.py`, `Tools/ue/realmv3_lods.py`,
`Tools/windows/realmv3_rebuild.ps1` / `Tools/mac/realmv3_rebuild.sh`, `Tools/realmv3_test.py`,
`Tools/realmv3_shots.py`, `Tools/windows/realmv3_perf.ps1` / `Tools/mac/realmv3_perf.sh`. In the New Game menu as
"Realm v3" (map 5 of `AVLHUD`; `vl.Map realmv3`).

- **The map.** Point-symmetric about its middle: the player's plateau in the north-west, the enemy's in the
  south-east (14 m, 120 x 108 m, cliffs all round), each with its castle, two home mines in crags, two towers, one
  base ramp and a stone stair down the sea cliff to its own port. The ridges run from the north-east corner to the
  south-west corner, coast to coast; a pass 12 m wide through each side of them leads into the basin (4 m, 132 x
  60 m), where the two neutral mines and the shared ground to build on are, with the lane straight across.
  Everything else is forest to the sea cliffs, and nobody walks in it.
- **Only 28,500 m² of its 127,400 m² can be walked on.** The hidden walls (`SM_RealmV3Barrier`) stand round the
  plateaus' rims, along the ramps, the passes, the stairs and the quays, and round the basin. The same mesh carries
  a **lid**: a sheet at chest height over the ground behind the walls. The path grid takes the largest connected
  piece of standable ground for the map, and without the lid that is the forest's floor.
- **The base ramps are smooth.** Voxel ground rises in quarter-block shelves, which read as a stair; each ramp and
  its shoulders are covered by a sheet on the true slope (`SM_RealmV3Ramps`, tagged Ground: the mesher's own top
  faces, lifted), the voxels just under it. A ramp is a spur of the hillside 18 m wide and 73 m long (1 in 7.3).
- **Checked in PIE** (`Tools/realmv3_test.py routes around times build stuck`): every route between the sides by
  both ramps and both passes, no ground for the grid anywhere else, the two sides' routes to the middle 199.3 m
  and 199.9 m, the hero's run between the middle and each ramp 16.9 s both ways. The numbers: `PROGRESS.md`.

## The battle: teams, combat, economy, the enemy, the menus

The first draft's rules (the first draft's `Source/SovereignRealms`, see the top), reimplemented on this project's units:
`UVLBattle` (`VLBattle.*`: teams, health and damage, buildings, economy, training, upgrades, towers, the match),
`FVLCommander` (`VLEnemyAI.*`: the enemy commander), the combat components, and `AVLHUD` (`VLHUD.*`: the menus and the
in-game HUD). Every number is the first draft's (`SRFeelSettings`); per-hit damage is scaled so damage per second is the
first draft's, the voxel troops keeping their own swing (1.25 s) and shot (2.4 s) rhythm.

- **The match.** The game opens on the title screen (New Game, How to Play, Settings, Quit). New Game: the map (**The Realm**, the
  battle; **Realm v2** and Highlands, the bigger battles; Flatlands is a sandbox) and the enemy's difficulty (Easy / Normal / Hard); Start opens the
  map with `?Match=1?Difficulty=N`. Each side starts with 400 gold, 300 food, its castle and whatever else the map places
  (on the two battle maps: one gold mine and the watch tower beside it; **no farm**, **no barracks and no archery range**: the
  Builder raises them, and the enemy's commander lays a farm first, then the trainers), 3 swordsmen and 2 archers in front of its
  castle by its `TeamStart:<team>` (the player's are platoon 1; King David stands at the PlayerStart), and **1 Builder**
  beside them. **The side whose castle falls loses**: the victory
  or defeat screen comes 1.6 s later (time, map, difficulty, troops recruited / lost, enemies slain, buildings lost /
  razed; Play Again, Main Menu, Keep Watching). Esc pauses (Resume, Restart, New Game, Controls, Settings, Quit to Main
  Menu, Quit Game; those that end something ask first). A map with no enemy castle is a sandbox: the economy runs, no commander.
- **The Test World** (New Game > Test World; `UVLBattle::SetupTestWorld`; the owner's call, 2026-11-22). Realm v2
  opened with `?TestWorld=1`: a match that starts with both sides at their most, for trying the balance. Each side: its
  castle at level 7; two barracks, two archery ranges, a Granary, a Treasury, and farms and watch towers up to their
  limits (9 and 8), on rings round the castle by the construction's own placing (`FindPlacementNear`,
  `PlaceBuilding`, finished at once with `UVLConstruction::FinishNow`); every building at its top level, the map's
  own mine and tower too; its stores full; troops up to the ceiling of 120, three swordsmen to two archers (the
  player's in six platoons of 20); all six Builders. Neutral mines stay neutral. The enemy commander plays on as
  usual, at the difficulty chosen. A test ground: its layout is not tidied (a building with no room at its place on its
  ring goes anywhere round the castle). With eight level-3 towers a side, the commander reckons the defence high: on
  Easy it attacks when its first attack is due (housing full), on Hard it held the crossing for the 11 minutes tried. Console: `vl.Map test`, or `vl.TestWorld
  [0|1|2]` on any battle map.
- **The enemy's clock** (the HUD's "Enemy ready in 3:12"). While an attack is out the commander's next one has no
  time yet (`NextWaveTime` is the clock plus `FVLCommander::WaveHeld`, a million seconds), and the attack's end sets
  it. On Hard, the one difficulty that flanks, an attack whose flank party ended while the main body was not out
  never set it: the HUD read "Enemy ready in 16650:28" and the commander never attacked again. Fixed in
  `FVLCommander::EndAttack` (a flank's end ends the attack when the main body is not out). And with no attack out the
  wait is never longer than the longer of its first attack's time and its pause between two
  (`FVLCommander::MaxWaveWait`: 7:00 Easy, 4:00 Normal, 2:24 Hard), in `FVLCommander::Step` and in the HUD's text.
- **Teams.** `AVLKing::Team` (0 the player, 1 the enemy); buildings by their tag `Team:0|1|Neutral` (a game building
  without one is the player's). Health bars on hurt or selected units and on damaged buildings (the ring of the side's
  colour under every unit is off by default, `vl.TeamRings 1` brings it back). The player selects, commands and takes control of only their own units.
- **Troops.** Swordsman (the Shieldbearer): 280 health, 29 a swing (split over its blows), 100 food, 18 s at the
  Barracks. Archer: 125 health, 40 an arrow (x0.5 against buildings: 20; raised from the first draft's 29, +38%, so
  archers are worth fielding: 17 damage a second against a swordsman's 23), 85 food, 16 s at the Archery Range, bow
  range 31 m. **Her shot comes every 2.4 s from the start of one to the start of the next** (`UVLArcherCombat`, the
  balance runs of 2026-11-22): the wait used to run only while she stood at rest, not through the 1.1 s draw, so she
  shot every 3.5 s and dealt 11 damage a second, not 17; ten swordsmen then beat twelve archers without a loss (see
  *Computer against computer and the balance*). King David: 600 health, 45 a swing, no housing, a troop's pace (4.2 m/s on the march, 7.6 at a run; it
  was 5.2 / 9.5); **if he falls he rises again at his castle 100 s later** (not if it has fallen;
  `VLRules::KingRespawnSeconds`, five times the 20 s it was: the owner's call, 2026-11-22. It is his only cooldown:
  he has no ability on a timer, and his sword's swing is as it was).
  Troops not on an order go for any foe within their reach (`Acquire`: 40 m, archers 42 m; raised from 16.9 / 19.5 m,
  about 2.4x / 2.15x, on 2026-11-22; on a lookout the bow's reach), troops before buildings, and answer whoever strikes
  them; friends within 12 m (13 m of a building) come to help, and an idle troop with no foe in its reach goes for the
  foe of a friend fighting within its reach (up to 10 m beyond it). Sight (the Spy's notice, fog of war) stays 16.9 /
  19.5 m. Stance per platoon or unit (G): Aggressive (40 / 42 m; lets a chase go at 1.5 times that unless struck, and
  goes no further than 50 m from where it took the fight up, `VLRules::AggressiveLeash`: then, and after letting a chase
  go, it walks back there; a fight taken up within 6 s of another keeps the first one's post, so one foe after another
  does not lead it into the enemy's base), Defensive (only what it can strike within its leash of 20 m from its post: a
  swordsman goes for foes within 22.4 m, an archer within her 42 m; past the leash, and once no foe is left in its
  reach, it walks back to its post), Hold ground (only what is in reach; it does not help friends). Units on an
  attack-move, following, guarding or on a chain of orders are brought back by that order instead of a post. A plain move ignores foes (a march too, until it arrives); a left or right
  click on a foe's unit or building attacks it. Swordsmen run a moving foe down (a fresh route every 0.6 s, given up
  after a dozen that get no closer) and go for a building's walls; archers lead a moving foe and walk into range
  again when it leaves it. Arrows strike the bodies of foes they pass (never friends). The dead topple and are gone.
- **The Spy** (the first draft's Scout, `ESRUnitType::Scout`; `VLRules::Troop("Spy")`, `UVLSpy`): 90 health, 8 a blow
  (x0.2 against buildings), 350 gold + 200 food, 24 s at the **Castle**, 1 housing. Three rules, checked when it is
  queued (`UVLBattle::SpyRefusal`): the castle at **level 3**, **one at a time** (alive or in training), and a
  **5-minute wait** between two, counted from the moment the last was queued and paid for; no batches. The castle's
  panel has its recruit button (the Scout's: "Castle level 3" / "In training" / "In the field · 3:12" / "Ready in
  3:12"), the upgrade button one slot to its left. **Very fast**: 8.75 m/s on the march and 11 m/s at a run (a
  swordsman 4.2 / 7.6), a 2.6 m stride. **Picks no fights**: no sight of its own to go for foes, it answers no calls
  for help and joins no recruit platoon; played, a left click is a light blow. **Hard to notice** (`FTroop::Notice`
  0.45): enemy troops go for it only within 45% of their sight (a swordsman at 7.6 m instead of 16.9 m, an archer at
  8.8 m) and let it go at 45% of their usual chase; towers and the castle's walls shoot it only inside 45% of their
  reach; the enemy commander sees it (its memory, its "foes at my buildings" alarm) only at 45% of its 26 m. A direct
  order is not affected. **Sees far**: 33.8 m (`FTroop::Sight`, the first draft's 26 m plus 30%: the dashed ring when selected), and the spyglass (see
  *Playing a spy*). A spy standing idle raises its spyglass now and then. Its hood's tail (`HoodA` > `HoodB`) trails
  behind it as it runs and flutters in the wind; its cloak is its own (short, narrow, split into two tails), on the
  King's jointed cape panels; the lantern on its back glows and lights the ground.
  The enemy commander (Normal, Hard) trains its one Spy once it has six troops, keeps it out of attacks and defence,
  and sends it every 16-28 s to a look-out beside one of your buildings (the castle most often), just outside the
  distance at which it would be noticed; below 60% health it goes home and stays. Console: `vl.Spies`,
  `vl.Spyglass 0|1`, `vl.SpyCooldown [seconds] [enemy]`, `vl.TrainAt Castle`, `vl.SpawnTeam Spy 0|1 X Y`.
  Deferred with the fog of war: lifting the fog over what it sees, hiding the enemy's Spy from the player until one
  of the player's troops is within 45% of its sight, drawing it half seen; Its Roam order (O) is in (see *Standing orders*), choosing
  ground it has not been to lately instead of unexplored ground.
- **Buildings** (health, then by level): Castle 12000 (houses 8, troop ceiling 36, stores 600 each, 1 archer on its
  walls: 36 every 1.4 s to 10 m; 7 levels to 64 / 120 / 5500 and 4 archers), Barracks 1600, Archery Range 1400 (levels:
  training x1.35 / x1.8), Farm 1000 (14 food every 6 s, houses 4; levels 20 / 27, 6 / 8), Gold Mine 1250 (10 gold
  every 6 s; levels 16 / 23), Watch Tower 1800 (shoots 35 every 1.2 s to 24 m; levels 60 / 85, 0.95 / 0.8 s, 27 / 30 m; it was 50 / 85 / 120
  until the balance runs of 2026-11-22;
  archers on its lookout shoot too; **its own archers**: see below), Granary 900 / 1200 / 1500 and Treasury 1100 / 1450 / 1800 (+400 / 900 / 1600 storage; built from the Economy tab). The selected
  building's panel (bottom middle): health, what it does, the recruit button (Shift 5, Ctrl 10: each paid for and
  housed when queued, no queue limit), the upgrade button (U), its lookout. Right click with a barracks / range selected: its rally point;
  Ctrl+1..6: its recruits join that platoon. A fallen building sinks into the ground (its queue lost; a storehouse's
  stock beyond what is left is lost).
- **The watch towers' own archers** (`UVLBattle::TickTowerGuards`, `AVLKing::bTowerGuard`; the owner's call,
  2026-11-22). Every watch tower of either side, the map's and those raised in the match, has archers of its own on
  its lookout: 1 at level 1, 2 at level 2, 3 at level 3 (`VLRules::TowerGuards`; 2 / 3 / 4 until the balance runs of
  2026-11-22: with them a level-3 tower held off 16 swordsmen and took 24 to raze; now 13-14); one more steps up the moment the
  tower is raised a level, and a finished tower is manned at once. They take no housing and are not counted in the
  troops (the top bar, the cap, the commander's army or squads), cannot be selected, ordered or played (a click on
  one is a click on its tower), and stay up when the Lookout button sends the others down. They shoot as far as the
  tower does (its level's reach plus 3 m: 27 / 30 / 33 m), so the tower's reach is what the enemy commander reckons
  with; enemy archers (and the towers) can shoot them down, and one that falls is replaced **40 s** later, one at a
  time (`VLRules::TowerGuardRestock`; not while the tower is under repair). They go with their tower (razed, pulled
  down, changing hands); their deaths are not counted as troops lost. The tower's panel shows them ("archers 1 / 1",
  "next in 31 s"); its own shot is as before. On the commander's side they count as manning the tower (its
  `TowerArchers` 2 / 3 are mostly met by them).
- **The enemy commander** (`FVLCommander`; the first draft's `SRAISubsystem` grown into a commander of three layers over
  its economy). It plays by the player's rules (no extra resources; Easy gets less of its income) and knows only what
  it has seen. Files: `VLAIWorld.*` (perception: influence map, the map's points, events), `VLEnemyAI.*` (the profile,
  perception, strategy, economy and building, the report and console), `VLAISquads.cpp` (squads, their tasks, micro).
  1. **Perception and world model.** Sightings of the player's troops within 26 m of its troops, Builders and
     buildings (its Spy 33.8 m; a Spy of the player's only at 45% of that), remembered 90 s; the foe's army estimated
     from what it saw at its largest (the unseen part assumed round the foe's castle); the **foe's bodies** (sightings
     grouped within 18 m: exposed in the open, or at its door); an **influence map** of 10 m cells over the path grid's
     ground (each side's strength spread 22 m round each troop, towers and castles over their reach); **events**: its
     buildings struck or lost, raids on its outlying farms and mines, troops lost. **The map's points** (`FVLAIMap`, read
     once a match starts from the level's tags, plus `SourceArt/<map>.json`'s `markers` and `teams.<t>.bridge_end` when the
     file is there, i.e. in the editor): the Crown (`TargetPoint` tagged `Crown`), crossings and flank bridges (actors
     tagged `Name:Bridge`, bridges within 30 m taken as one; off the line between the castles by over 24% of the gap: a
     flank), neutral mines (`Team:Neutral`; `Rich`: the Crown's twin lode), each side's gathering point (`TeamStart:<t>`,
     else `Rally:<t>`), the middle. No coordinates are hard-coded: a sandbox (`vl.TestBase` on `L_Flatlands`) has its
     castles and a middle.
  2. **Strategy.** Every few seconds a posture is chosen by utility: **Expand** (claim veins, farms, mines; the field
     army holds its side of the crossing), **Defend** (foes at its buildings for longer than its reaction time; strong
     enough that the patrol and guard cannot cope), **Contest** (hold the best point it can: the Crown, the crossing, a
     neutral mine; worth x the odds there against the foe's influence x its own half first), **Harass** (raids on the
     foe's outlying farms and mines, more when it is behind on mines), **Attack** (the attack body's strength against
     the defence it expects at the best target and on the way there; at once when its housing is full; Normal and Hard
     also at near-even odds after waiting 150 s), **Regroup** (over 30% of its army lost within a minute, or clearly
     outnumbered: back under its towers). The present posture keeps a bonus and at least 8 s (no flip-flopping); a field
     army in the middle of a fight keeps its posture; only a real threat at home overrides that.
  3. **Squads.** The army is split by role; new troops fill the guard, then the patrol, then the field army:
     - **Patrol**: `OrderPatrol` in a column round its buildings within the patrol radius (in front of each mine, farm,
       tower, trainer: the mine roads; sorted round the castle), defensive stance; it meets foes on its own beat first.
     - **Guard**: `OrderGuard` on the castle, on each Builder working over 35 m out (Normal 1, Hard 2 guards, the
       healthiest), on Hard its furthest mine on its half; troops pulled out of fights end up here.
     - **Field army**: holds the posture's point in a Line, defensive stance (its end of the crossing, a little back on
       its own bank and on the highest ground near; the Crown from its side; beside a vein, never on it; under its towers
       when regrouping); never inside the foe's tower or castle reach. Attacks with `OrderAttackMove` at the building's
       door, knocks it down, moves on to the next target if it can take it, falls back (a plain move at a run) when
       outmatched, too few, making no headway for 160 s, or called home. **Intercepts** a foe body caught in the open
       (away from the foe's castle and towers) within its reach when it has the odds.
     - **Reserve**: troops trained while the field army is out; they hold its forward point and **reinforce** an attack
       that is going well (Normal, Hard), as a body of 5 or more.
     - **Picket**: a field army at home of 12 / 10 / 9 or more (Easy / Normal / Hard) sends a third (3-8) to hold a
       second point: its end of a flank bridge, a mine it claimed, a vein on its half, an outlying mine.
     - **Raid** parties (Normal, Hard): the fastest swordsmen, at a run in a column, at an outlying farm or mine (or a
       site) with next to no defence, not past the foe's castle or army on the way (Hard: round by a flank bridge when
       that way is much safer); home after one target, or recalled to defend.
     - **Flank** (Hard, maps with flank bridges): an attack of 8 or more sends two fifths round by a flank bridge when
       that way is less than 1.7x as long; the main body leaves later so both arrive together; a flank near the target
       first waits out of reach.
     - **Micro** every 1 / 0.5 s (Normal / Hard): **focus fire** (Normal its archers, Hard its swordsmen too: the hurt,
       archers, a Spy, King David only when nearly down; the squad leaning toward one foe), **archers step back** 7.5 m
       behind their own swords from a swordsman at their throat (every 3 s at most), **troops badly hurt pulled out**
       (below 22% / 30%): an archer up a tower with room, else to guard the castle; a **tower in the way** of an attack
       is taken down first with 2.2x its strength, else the target is dropped. A troop that has made no way for 25 s
       leaves the attack (and the squads while it stands there).
     - **In force, and to the end** (the balance runs of 2026-11-22, when no match between two commanders ever ended,
       not in 90 minutes; `FVLCommander::AttackWant`, `FinalPush`, `IsPushing`): a main attack waits until it has
       its wave's size (`AttackCap` + `AttackCapGrowth` a wave, at most 60% of its housing) unless its housing is full
       or the odds are twice what it wants (attacks of four or five into a defended base bled both armies). From
       `PushAfter` of the clock (Hard 20 min, Normal 25, Easy 40; `vl.AI.PushAfter S` for tests), with an army about
       the foe's or better (`ArmyRatio` 0.9), it makes its **final push**: its attacks go for the foe's castle, with
       the patrol, the picket, the reserve and all but two of the guard; it is not turned aside by a tower on the way,
       not called home by a raid on an outlying farm or mine (only by foes at its castle), its hurt are not pulled
       out, it falls back only when down to two fifths, and its reserve joins it in bodies of ten. Swordsmen at the
       castle's walls (`AVLKing::bSiege`) are drawn off them only by a foe at their side or one that struck them, not
       by every troop within 40 m. An attack makes headway while its side is knocking down the foe's buildings, not
       only its target (a siege that razed the barracks round the castle was called off as "no headway"). With the
       foe's army 1.5 times smaller and the body a match for its defence, the castle is worth twice as much as a
       target at any time.
  4. **Economy and building** (`ManageBuilding`, `TryBuild`): the first draft's build order (barracks and range first,
     then farm, tower, mine, farm) and wants, one site per Builder, driven by the strategy: a **tower by a farm or mine
     that was raided**, a tower when attacked early and often, a **second barracks / range when its army is behind**
     (and a longer training queue), **mines on the safest free veins** (near, rich, the Crown's while it holds it; none
     where the foe is stronger or under its towers; within 380 m of its castle, it was 260: on Realm v2 the west castle
     then had no neutral vein it would ever claim, its nearest being 325 m off while the east castle's is 154),
     **farms, trainers and storehouses where there is room** (behind the castle first, then either side of it, then
     anywhere within 75 m: Realm v2's east castle has its port behind it, and its commander laid one farm in twenty
     minutes while the west one laid four), **no site where the foe is clearly stronger**; trains toward a
     swordsman share that answers the player's army; raises its castle when housing runs short or gold piles up, then
     its mines and barracks / range (a tower first while pressed); mans its towers (hurt archers first, counting those
     on their way); its Spy (Normal, Hard) as before.

| | Easy | Normal | Hard |
| --- | --- | --- | --- |
| Income (share of its farms' and mines') | 60% | 90% | 100% |
| Earliest attack | 7:00 | 4:00 | 2:24 |
| Odds it waits for | 2.0x | 1.5x | 1.15x |
| Regroup between attacks | 153 s | 90 s | 40 s |
| Attack size (first, +per attack, max) | 5, +2, 14 | 8, +3, 24 | 10, +4, 30 |
| Raids | none | every 120 s from 6:00, 3 troops, 1 out | every 60 s from 2:24, 4 troops, 2 out |
| Adapts its army to yours | no | 60% | fully |
| Reinforces, attacks at even odds after waiting, upgrades | no | yes | yes |
| Archers on each tower, economy decisions every | 0, 1.5 s | 2, 1 s | 3, 0.6 s |
| Strategy every, reaction to foes at home | 6 s, 5 s | 3.5 s, 2 s | 2 s, 0.6 s |
| Patrol (troops, radius) | 2-3, 90 m | 2-3, 130 m | 2-4, 150 m |
| Guard (castle; per far Builder; far mine) | 1; none; no | up to 3; 1; no | up to 4; 2; yes |
| Picket from a field army of | 12 | 10 | 9 |
| Intercepts a foe body at, within | never | 1.6x, 60 m | 1.25x, 90 m |
| Flank by the side bridges | no | no | yes |
| Final push on the castle from (army 0.9x the foe's or more) | 40:00 | 25:00 | 20:00 |
| Micro: every, focus fire, step back, pull out below | none | 1 s, archers, yes, 22% | 0.5 s, all, yes, 30% |

  The knobs are `FVLAIProfile` (`VLEnemyAI.h`, one comment each; set per difficulty in `FVLAIProfile::For`):
  `StrategyEvery`, `ReactionDelay`, `Commitment`, `ContestWeight`, `ExpandWeight`, `PatrolMax` / `PatrolShare` /
  `PatrolRadius`, `GuardMax` / `GuardShare`, `BuilderGuards`, `PicketFrom`, `MaxRaids`, `RaidSize`, `bFlank`,
  `InterceptOdds` / `InterceptRange`, `MicroEvery`, `FocusFire`, `bKite`, `PullBack`, `bAvoidTowers`, `PushAfter`, and the main
  game's (`FirstAttack`, `Advantage`, `Regroup`, `AttackCap*`, raids, `AdaptWeight`, `IncomeScale`, `RecruitQueue`,
  `Think`, `RetreatHold`, `TowerArchers`, `Builders`, `BuildCadence`, ...).
- **Watching the commander**: `vl.AIDebug 1` logs every look at the strategy (`AI 1 [Normal 4:03] posture ATTACK
  (expand 0.30 defend 0.00 contest 0.52 ...) army 22.5 vs ~11.2 (x2.00) threat 0.0 | Patrol#1 3 patrol ... | Field#2 8
  attack Farm | ...`), focus-fire orders and steps back; always logged: posture changes with their reasons, squads'
  new tasks, attacks, raids, flanks, interceptions, retreats, pull-backs, events. `vl.AIDebug 2` also draws the squads
  and their goals, the map's points and the influence map in the world. `vl.AI [team] [nomap]` logs the full picture:
  posture and utilities, the micro counts, each squad and each troop in it (health, where, its standing order), the
  foe's bodies, recent events, the map's points and the influence map as text (+X up: `o O` its strength, `x X` the
  foe's, `#` both, `C` / `K` the castles, `P G F R L W` its squads, `*` the points). `vl.AIvsAI 1 [0|1|2]` gives the
  player's side a commander (at its own difficulty); `vl.TimeScale N` runs the game N times as fast for whole-match
  tests. Tested (PIE, 4-5x, logs): AI against an idle player and AI against AI on `L_Realm` and `L_Highlands` at each
  difficulty, and on `L_Flatlands` with `vl.TestBase`.
- **Computer against computer and the balance** (2026-11-22; `VLMatchLog.*`, `Tools/aivsai.py`). `vl.AIvsAI 1 [d]`, or
  `?AIvsAI=<d>` on the map's URL, gives the player's side a commander of its own (`FVLCommander` is written for either
  team). For an even match **King David is benched** (team -1, which nobody fights or counts, hidden, still, off the
  map's corner: the enemy has no hero and no commander plays him; `vl.AIvsAI.King 1` keeps him) and the player's
  platoons are disbanded (their cohesion would pull troops about under the commander's squads). The rest of the URL:
  `?Difficulty=<d of team 1>?MaxMinutes=N` (a draw then) `?Quit=1` (quit when the log is written; never the editor)
  `?TimeScale=N` `?Tag=name` `?King=1`. **The match log** (`vl.MatchLog 1`, on by itself with AI against AI): every 10 s
  of the match's clock both sides' gold and food (in stock, earned, lost to full stores, spent), income, housing,
  castle level, troops by kind (alive, trained, lost), buildings by kind, sites, the commander's posture and power;
  every second the sites laid, buildings finished, levels raised, mines claimed, buildings lost, attacks, flanks and
  raids sent and back; and at the end damage to units and to buildings and kills by who dealt them (sword, bow, a
  tower's own archer, a building's shot). Written to `Saved/Balance/<id>.json`, `<id>_series.csv` and a line of
  `Saved/Balance/matches.csv`. **The runner**: `python3 Tools/aivsai.py run --tag base --minutes 45 HvHx3 NvN HvN NvH`
  (team 0 first; each a headless run of the editor's binary, `-game -nullrhi -benchmark -fps=30`: a fixed step of
  1/30 s as fast as the machine goes, a 45-minute match in 2-3 minutes; take `Saved/editor.lock` and quit the editor
  first) and `python3 Tools/aivsai.py report --tag base`. **Duels** (`vl.Duel S0 A0 S1 A1 [repeats] [s]`, `vl.Duel
  standard`, `vl.Duel at X Y`; or `?Duels=1` / `?Duels=10.0.0.12_t3.16.0.2?DuelAt=12400,18800` on the URL, then quit):
  bodies of troops 36 m apart on open ground, the commanders off, fighting it out by themselves, each duel fought
  with the sides swapped; `t<level>.S.A.n` is S swordsmen and A archers against a watch tower of that level (its own
  archers on it). Results in `Saved/Balance/duels.csv`. Test hooks: `vl.AIForce <team> attack | flank X0 Y0 X1 Y1 |
  killflank | killfield | state | off | on`, `vl.AI.PushAfter S`. **What the runs found** is under *Balance (2026-11-22)*
  below. The batch's own checks (cohesion, the march's pace, mixed attacks, archers' attack-move, guard, Ctrl + N,
  Assign, the minimap, the Hard clock with a flank struck down): `python3 Tools/feedback_test.py` in PIE.
- **Balance (2026-11-22)**: 67 computer-against-computer matches on Realm v2 (Hard and Normal, each side of the map,
  45-90 minutes) and ~200 duels. What they showed, what was changed, and what is left:
  - **The doubled times are not what slows the game.** The same matches with every time halved back gave the same
    curves to within noise (gold earned by 20 min 2970 against 2618 doubled, food 7046 against 6622, housing, castle
    level, buildings): gold (one mine, 100 a minute, 150-290 by the end) sets the pace, not the sites' and recruits'
    times. The opening is not dead: first farm 0:33, barracks 1:35, range 2:50, first recruit about 1:55, Hard's
    first attack 2:26. So every time stays twice the first draft's and the tower's three times.
  - **Each side's commander was crippled by the map** (fixed): the east castle has its port behind it and its
    commander found no room for farms (one farm in twenty minutes against four), and the west castle had no neutral
    vein within its 260 m. Before: the west side lost no building in five matches, the east nine a match. After: 10.5
    against 11.2 (kills 165 / 170), and in the last batch 10.5 against 12.4. The map itself is uneven for mines: the
    east castle's nearest neutral vein is 154 m off, the west's 325 m (for the map's designer).
  - **Archers were under their own numbers** (fixed, `UVLArcherCombat`): a shot every 3.5 s, not 2.4. Duels at equal
    food (36 m apart, no orders): before, 10 swordsmen beat 12 archers without a loss and 6 + 5 mixed lost to 10
    swordsmen; after, the swords still win but with 4-7 of 10 left, 20 swordsmen against 24 archers win 3 of 4, the
    mixed bodies (6 + 5, 12 + 10) beat pure archers every time and pure swordsmen 3 of 4 and 4 of 4, and about 13
    archers hold 10 swordsmen. In matches (with the commander's micro) an archer deals three times a swordsman's
    damage to troops; the swordsman is the wall that lets her.
  - **Towers were too much** (`VLRules::Level`, `TowerGuards`): a level-1 tower with its two archers held off five
    swordsmen and took about seven, a level-3 one sixteen (24 to raze: 2400 food of troops against 780 gold, and no
    housing). Now 35 / 60 / 85 a shot (was 50 / 85 / 120) and 1 / 2 / 3 archers of its own (was 2 / 3 / 4): about
    4-5, 8 and 13-14 swordsmen. Price (160, +250, +370 gold) and times (54 s, 60 s, 80 s) unchanged: still well
    worth it, not a wall.
  - **No match ended** (all 59 before the last batch drew, the 90-minute ones too, and with the old times): the
    commanders traded small attacks at the outlying mines (a mine fell 15-50 times a match) and never went for a
    castle. The commander's rules above (in force, the final push, the siege at the walls, headway) bring the
    castles under attack (35 attacks on a castle in the last eight matches, none before) and two castles fell (at
    38:45 and 45:03, one each side); six of eight still drew at 50 minutes, and Hard did not beat Normal (one win to
    Normal, three draws). What holds a castle now: the defenders fight at home, beside their towers and their
    barracks' new recruits, at the end of a 580 m march, and a push that wins the field reaches the walls with a
    third of itself. Not yet changed (for the next pass): the commander's own defence at home (the guard, the
    patrol, towers manned) against its push, and Hard's edge over Normal in a long game (its income is 100% against
    90%, its odds 1.15 against 1.5: not enough to tell over 50 minutes).
- **HUD**: see *The interface* below.
- **Console** (`Tools/pie.py run "..."`): `vl.StartMatch [0|1|2]`, `vl.Restart [d]`, `vl.Menu main|new|pause|settings|controls|end|0`,
  `vl.UIClick U V [right]` (a click on the interface at that point of the view), `vl.HUD` (the buttons drawn, by id; the route lines drawn, the Builders' chains and numbers, the Shift preview, hidden in the hero view; whom the mode box shows; the minimap's rect, world box and up yaw, and where its view box's middle and the player's castle are drawn on it),
  `vl.Battle` (both sides, every building), `vl.Give gold|food N [enemy]`, `vl.TrainAt <building> [enemy] [n]`,
  `vl.Upgrade <building> [enemy]`, `vl.Damage <building> [enemy] N`, `vl.Kill <unit> | castle enemy|player`,
  `vl.SpawnTeam Swordsman|Archer 0|1 X Y [n]`, `vl.SetTeam <building> 0|1|neutral`, `vl.TestBase [DX DY]` (an enemy
  base on any map: copies of its buildings, mirrored), `vl.TestWorld [0|1|2]`, `vl.Cohesion`, `vl.AIvsAI 1`, `vl.BattleLog 1`. `vl.Order`, `vl.SelectUnits`,
  `vl.Units` and the like take `enemy` for the enemy's units; the group words mean the player's own.
- **Not ported** (the user's to design): the Medic, the Catapult,
  the Horseman (no voxel model yet); also deferred: fog of war, saved games. (Guard, patrol, march together and the
  other orders are back: *Standing orders*, `Docs/PORT_AUDIT.md`.)

## The interface

The first draft's interface (the first draft's `Player/SRHUD*.cpp` and `Docs/UI.md`, see the top) ported one to one: the same
layout, panels, colours, fonts, icons, wording and behaviour, drawn immediate-mode on the HUD canvas by `AVLHUD` (no
widgets), on this project's battle (`UVLBattle`), orders (`UVLCommand`) and units (`AVLKing`).

| What | Where |
| --- | --- |
| Frame, input, primitives (panel, text, icon, button, slider, tooltip), world-space feedback | `Source/SovereignRealms/VLHUD.{h,cpp}` |
| In-game HUD | `Source/SovereignRealms/VLHUDGame.cpp` |
| Menus and shared screens | `Source/SovereignRealms/VLHUDMenus.cpp` |
| Palette, world colours, button ids | `Source/SovereignRealms/VLHUDStyle.h` |
| Icon atlas and title lettering (the first draft's) | `SourceArt/UI/*.png` -> `/Game/Voxel/UI` (`python3 Tools/ue_py.py Tools/ue/import_ui.py`) |
| Unit portraits (the voxel characters' heads) | `Tools/blender/render_portraits.py` -> `SourceArt/UI/T_UI_Portraits.png` (King, Swordsman, Archer, Spy, Builder; 128 px cells) -> the same import |

**Look.** Dark navy translucent panels with a bronze edge, a thin gold rule and gold corner brackets; parchment text,
gold headings, parchment tooltips with dark ink; team blue / enemy red. The engine's Roboto through the Slate font
cache (sharp at every size); 16 px pixel-art icons drawn point-filtered. Everything is laid out in design units
(pixels at 1080p) times `UI = max(view height / 1080, 0.8) x Interface scale`, capped so the bottom row fits.

**While playing** (overview):

    +---------------------------------------------------------------------------+
    | [mode]   [ gold | food | troops | clock | enemy ]                [?] [||] |
    |                    attack-ground hint, alerts (newest first)              |
    |                                                                PLATOONS   |
    |  +---------+ +--------- selection panel ---------+               1 ...     |
    |  | minimap | +-----------------------------------+               2..6      |
    +---------------------------------------------------------------------------+

- **Resource bar**: gold and food (amount / what the stores hold, income a minute; shakes red on a refused purchase, the
  icon swells when income lands, amber when the stores are full), troops `alive+training/cap` (amber at the cap), the
  then the **hero, Builders and Spy chips** (`T_UI_Portraits`: King David's health, or "back in 0:12" while fallen; the
  Builders alive/limit and +in training; the Spy 0/1, the wait before the next, greyed below castle level 3; **a click
  on the Builders' or the Spy's chip opens the list of them** (`AVLHUD::DrawChipList`: what each is doing; click a row to
  go to it and select it, hover to mark it in the world); a click on the hero's chip selects him and a double click
  enters his hero view, as Enter with him selected), the clock, the enemy ("Enemy ready in 3:12" dim, amber under a
  minute; "Enemy watching"; "Enemy attacking!" pulsing). Tooltips on each, **shown only while Option (Alt) is held**
  (every tooltip of the interface: `AVLHUD::DrawTooltip`). Top right: Controls (F1) and Pause.
- **Build button and menu** (left of the selection panel, B): see *Building*. **A click off the menu** (the world, or
  another panel) **puts it away** and the Build button goes dark; the click is still the usual one, so on the ground it
  also lets the selection go. Sites show a hammer bar over them (red
  "needs a Builder" while nobody works at one), repairs a green one.
- **Alerts**: plates with an icon and an accent per kind (attack / lost red, done green, housing amber, info gold);
  in over 150 ms, out over the last second of six. Those with a place ping the minimap.
- **Minimap** (bottom left): a picture of the map from straight above (its unlit colours, captured once when the overview
  first shows, units hidden), your buildings blue and the enemy's red (castles larger with a gold core), contested mines gold, troops
  as dots (selected white, King David with a gold rim), alert pings, and the camera's view of the ground. **Up the map is
  the way the default camera looks**, to the nearest quarter turn (`AVLHUD::MapYaw` from `AVLKing::GetHomeYaw`, the
  postcard camera's yaw: the picture, the dots, the pings, the view box and the clicks all go through one pair of
  functions); it was +X up, a quarter turn off the view. The map is fixed: Q / E turn the view box on it, not the map.
  Left click (drag): look there. Right click: the selection goes there (a barracks / range selected: its rally point).
- **Selection panel** (bottom middle, with a selection): troops (portrait and count per kind, health, how many are
  fighting, the circles' key, the standing order it is on ("Patrolling", "Guarding the Castle", ...), and the main
  game's command card, trimmed on 2026-11-22: **Assign** (to a platoon: a picker of the six over the button), Patrol [P], Guard [V],
  Roam [O] with a Spy, Stance [G], Formation [F; right click too], March together [M] (Together / Free), Disband [Del]
  for a platoon, Dismiss [K] (asks first: Sure?), Control [Enter] for one unit; the row packs tighter when long. No
  Attack, Attack ground, Stop or Hold buttons: attacking is a right click, hold is a stance; A and S keep their keys); an enemy's units read-only; a building (icon,
  name, side, level of N, health and "badly damaged" below half, what it does) with its buttons on the right: the
  **upgrade button** (next level, gold / food price in red when short, what it brings in a few words and in full in its
  tooltip, a progress meter and time while it is raised, "Castle level N" when a storehouse's level waits for the
  castle; U), a barracks' / range's **recruit button** (portrait, price, "Trains in 18 s" / "Housing full"; Shift 5,
  Ctrl 10; flashes gold or red) with the queue, its progress and the **Joins** chips (none / 1-6) on the left, and the
  watch tower's **Lookout** (who mans it; click: send them out). Farms and mines show their payout meter, storehouses
  the kingdom's stores, the castle its archers.
- **Platoon panel** (bottom right): six slots; a formed platoon shows its number in its colour, its kind, counts,
  health, a burning edge while it fights, and buttons for formation, stance, **the recruits' flag** (lit on the one
  platoon new troops join; a click sets it there, a second clears it; the platoon's tag over the troops carries a small
  flag too) and disband; click selects, twice within 0.35 s also looks at it; **Option + click: the selection guards
  that platoon**; empty slots read "Ctrl+N to form". The
  header folds it away (remembered). **It and the minimap stay up in the hero view.**
- **Castle card**: raising the castle a level shows what the level brings (14 s, or **Onward**).
- **Portraits**: every troop portrait (selection panel, queue, recruit and lookout buttons, training bars, platoon rows,
  the hero's bar) is a render of the voxel character's head and shoulders; an enemy's is reddened.
- **World**: no rings under units' feet (the user's call: the platoon diamond over their heads, in the platoon's
  colour, **grey for the player's units in no platoon**, and the health bars mark them; the side-coloured ring under every unit is behind `vl.TeamRings 1`, off by default; the first draft's green
  ring under the selected and the pale one under the pointer are left out); the selected
  building's footprint; health bars over units of both sides in
  every view: always in the red (under 34 %), else for 3 s after a hit or a heal and fading over 0.8 s, and always while
  selected; on buildings lately hurt or selected and damaged; training and upgrade bars with icons over buildings at work; "+N" payouts with the coin or grain;
  numbered platoon tags; **a shield beside every unit your troops guard**; **no diamond over a tower's own archers and no
  outline of them through walls** (they never leave the lookout: stencil 2, `AVLKing::RefreshSilhouette`); **the enemy's
  diamonds in the hero view too** (from 5 m of the unit played); dashed blue pathways (**a platoon, or one group order,
  of more than 7 walkers draws one line, its leader's, a little heavier, not one each**: `vl.RouteLines.GroupOver`) and rally lines, a patrol's loop in orange and an attack-move's way in
  red, the Builders' numbered queue (all of these overview only: the hero view hides every pathway, follow and queue
  line, and keeps the order markers); while an order is armed, its hint under the top bar and a crosshair pointer; the selected troops' sight (dashed blue) and bow range
  (solid orange) and a tower's / the castle's reach; team-coloured pips over troops zoomed far out; the order markers;
  the green selection box.
- **This game's own**: the mode box top left (HERO / OVERVIEW; the unit in focus with its portrait, name and health:
  the first selected troop, "+N selected" for a group, in the hero view the first besides the unit played, else an
  enemy's unit looked at, else the unit played, so King David when nothing is selected; who is played, King David's
  fall), the hero view's
  crosshair, its line of controls along the bottom and, over it, the played unit's health bar (portrait, name, bar,
  numbers; it flashes red on a hit).
- **Title backdrop**: the overview camera circles the middle of the map's ground (`UVLGrid` bounds, so any size of map)
  from 1.6 x its width at -38 degrees (`AVLKing::SetTitleShot`, past the overview's zoom limits); the units' see-through
  silhouettes (`M_Silhouette` on the post-process volume) are off while it shows and back when the match starts.
- **Cameras and the ground** (`VLCameraGround.*`: `UVLCameraGround`, `UVLHeroBoom`). No camera's eye comes nearer
  the ground under it than its clearance (overview 1.5 m, hero 0.6 m): an eye that would be lower is lifted straight
  up and turned down to what it was looking at, never pulled in. The ground is the terrain (tag `Ground`,
  `SM_Terrain*` / `SM_Flat_*`) and the water's surface; trees, units, buildings and hidden walls do not count. Under
  terrain that hangs over open air (an arch, an overhang) the floor is the ground below, so a camera may go under a
  mountain but not into it; beyond the terrain's edge it is the edge's height. The overview turns about a point on the
  ground's surface (it was height 0 everywhere, which put the whole view under high ground). The lift is smoothed
  (up fast, down slowly, looking 0.35 s along the eye's way), so 50 cm steps of the ground do not jolt it. Cost: none
  while the eye is higher than everything on the map, else one to two line traces against the terrain tile under it.
  The title shot, the postcard and the free camera are left alone. Console: `vl.Cam.Ground 0|1`,
  `vl.Cam.Clearance <cm>`, `vl.Cam.Overhang 0|1`, `vl.Cam.Log 1` (logs a camera being held up).

**Menus.** Title screen (the live map drifting behind; crown, title lettering, NEW GAME, HOW TO PLAY, SETTINGS, QUIT;
Enter: New Game). New Game: the map (The Realm, Realm v2, Highlands, Flatlands, Test World) and Easy / Normal / Hard, BEGIN. Pause (Esc):
RESUME, RESTART, NEW GAME (another map), CONTROLS, SETTINGS, QUIT TO MAIN MENU, QUIT GAME; restart and the quits ask
first (CANCEL / yes). Settings: master volume, effects, music (sliders; music on, 100 %, until the player turns it
down), interface scale (applied when the slider is let go), Graphics (Quality High / Medium / Low, Render scale 100-50 %,
dynamic resolution), frame-rate limit, **Window** (Windowed / Full screen; the editor's play window says "Editor
window"; on Windows **Display mode**, **Resolution** and **VSync** in its place: see *Platforms*), camera angle (V), look speed (L), invert look (I). **Every setting is kept across launches** in
`GameUserSettings.ini` (`Saved/Config/Mac/` packaged): `[SovereignRealms.Audio] MasterVolume`, `Effects`, `MusicV2` (a new key:
the old `Music` could hold the 0 of the days it was off by default), `[SovereignRealms.Interface] Scale`, `PlatoonsCollapsed`,
`[SovereignRealms.Video] Quality`, `RenderScale`, `DynamicRes`, `FrameCapV2`, `WindowX` / `WindowY` (the window's own size, to
come back to from full screen), `[SovereignRealms.Camera] CameraAngle`, `LookSpeed`, `LookInvertV2`, `[SovereignRealms.Game]
Difficulty`, and the engine's `[/Script/Engine.GameUserSettings] FullscreenMode`, `ResolutionSizeX / Y`. Each is
written when it changes (the sliders and choices when Settings is left, or the game quits with it open); the window's
mode and size however they change (the Window row, F11 / Alt+Enter, the green button, dragging an edge: looked at once a
second, `UVLGraphics::KeepWindowState`). An explicit choice (the music off, a window) survives a restart. See
*Performance* below. Controls
(F1, or HOW TO PLAY): every key, two columns. Victory / defeat: the match's numbers, PLAY AGAIN, MAIN MENU, KEEP WATCHING.

**Input.** `AVLKing::OverviewCommands` hands every left press (and a right click let go without dragging) to
`AVLHUD::OnMousePress` first: over a panel drawn last frame (or with a menu or the controls overlay up) it is queued and
answered by the `Button()` under it while the HUD draws, and never reaches the world. `vl.UIClick U V [right]` takes the
same path; `vl.HUD` lists the buttons drawn last frame with their ids (`VLHUDStyle.h`, `VLId`).

**Changed from the first draft** (layout): the mode box top left and the hero view's help line and health bar are new;
the top bar's chips show the hero as well as the Builders and the Spy (the Builders' and the Spy's open a list), and the enemy's status after
the clock; the build menu's tabs are clicked (no Tab key); the castle's panel is wider (Builder, Spy, upgrade); the recruit buttons have no hotkey cap; the platoon rows have the main
game's four small buttons (formation, stance, the recruits' flag, disband; a building's own Joins chips come before the
flag); the watch tower's panel has a Lookout button; the castle's panel has the Spy's recruit button; the
pause menu has New Game and Quit Game instead of Save / Load; the victory screen adds Keep Watching; unit portraits are
the voxel characters, not the pixel icons.

**Not ported** (their features are not in this game; their buttons are left out, not shown dead): the castle's building
zone; the Medic, the Rider and the Catapult (recruit buttons, portraits); the command card's Build and Repair buttons
(B and X do it, and the Build button); fog of war on the minimap; saved games (Continue, Load, Save, the save list); the title
screen's film; the recruit buttons' Q / E keys (Q / E turn the view here); the sandbox match of the first draft's New Game.

## Orders: paths, platoons, the tower

Reimplemented here from the first draft's ideas (`SRGridSubsystem`, `SRFormation`, `SRPlatoonSubsystem`,
`SRPlayerController`, `SRBattleSubsystem::CommandMove`); nothing was migrated.

- **`UVLGrid`** (`VLGrid.*`) samples the level once at the start of play on 50 cm cells (about 0.15 s). Because the
  voxel world has floors over floors (the bridge over the river bed, ground under eaves and gate beams, the tower's
  lookout), a cell holds a stack of nodes, one per floor: found by tracing down through the cell until the ground
  (actors tagged `Ground`, or `SM_Terrain*` / `SM_Flat_*` meshes) is reached; kept if there is air with headroom over
  it, a unit's capsule fits there clear of everything taller than a step, and it is not under water (meshes on actors
  tagged `Water` are asked where their surface lies). Neighbouring nodes are joined where the step is at most 58 cm
  (`MaxStepHeight`), diagonals only where both sides are joined. Then, as in the first draft: regions of connected
  ground, one A* outward from the goal for a whole group, routes that keep off walls where there is room and are
  pulled straight to a few corners, clicks on a roof / cliff / water taken to the nearest ground the unit can reach,
  formation slots moved onto standable ground.
- **Units** (`AVLKing::FollowPath / AutoSteer`): walk their corners in turn, keep a little apart from each other,
  pass through one another while on the march (capsules that block jam a gate), and plan afresh from where they stand
  if they stop making way. The king ordered from the overview, troops, and troops leaving a building after training
  all go this way. A unit that falls in the water is put back where it last stood on land.
- **`UVLCommand`** (`VLCommand.*`): the selection, six platoons, `VLFormation::ComputeSlots` (the first draft's ranks:
  melee in front, archers behind, everyone keeping their side), `OrderMove`, and the tower: `build_town.py` tags the
  watch tower `Lookout:z;x0;y0;x1;y1` from `SM_WatchTower.json`; an archer that reaches its door is put on one of
  eight posts on the platform (there are no stairs), and put back at the door when ordered out.
- **Attacks** (`UVLCommand::DummyAt / OrderAttack / StopAttack`): a left click on a training dummy (an actor tagged
  `Dummy`, picked by its outline on the screen) hands an attack order to the selection's fighters; the fighting is
  each kind's own component. Swordsmen: `UVLSwordsmanCombat` (`VLSwordsmanCombat.*`, made on a swordsman at its
  first attack order): places on rings round the dummy (`RingRadius` 150, `RingSpacing` 105, `RingStep` 65 cm), a
  route for each to its own place, then facing it (`TurnRate` 540 deg/s) and a swing every `SwingInterval` 1.25 s
  (`SwingJitter` 0.12, the first after a random part of it) through `AVLKing::Attack`, so the combo and the battle
  stance are the king's. Out of reach (`Reach` 205) it steps closer for `CloseInSeconds` 2.5; crowded out beyond
  `BlowReach` 228 it waits and tries again every `RetrySeconds` 3; if its walk ended more than `GiveUpBeyond` 600 cm
  away it drops the attack. Any move order ends an attack, as does taking the unit over. The dummies' rocking and the
  sword sounds are `UVLSwordFx`, one place for every sword.
- Levels need nothing else: the village and the flatlands get their grid from their terrain meshes.

### Standing orders

The first draft's Stop, Hold, Patrol, Guard, Roam, attack-move, March together and Dismiss (`SRPlayerController`,
`SRBattleSubsystem::CommandPatrol / ExtendPatrol / StepPatrols`, `ASRUnit::OrderGuard / OrderRoam`), on `UVLCommand`
(`VLCommand.*`) for any commander: the player's keys and command card, and the enemy's AI. Each call replaces what the
units were doing; any other order (a move, an attack, attack-ground, the tower) ends a standing order. A unit's own
doings on one (a fight it picks up, an archer walking into range, a defensive unit going back to its post) run with
`UVLCommand::bInnerOrder` set and leave it alone. `UVLBattle::Tick` calls `UVLCommand::TickOrders`.

| Call | Does |
| --- | --- |
| `OrderStop(Units)` | drops the order, the pathway, the attack and any standing order (a unit on the tower stays up) |
| `OrderHold(Units)` | stands fast until the next order (`AVLKing::bHoldOrder`, `IsHolding()`: the Hold stance too): strikes only what is in reach, lets go of a foe that leaves it and steps back |
| `OrderPatrol(Units, Points, bRun, Shape)`, `ExtendPatrol(Units, Point, Shape)` | from where they stand through the points and back, round and round, attack-moving; the next leg once nobody walks or fights, a leg cut short by a fight walked again (up to 3 times) |
| `OrderAttackMove(Units, Ground, bRun, Shape, bQueue)` | march there fighting what they meet, on again after each fight; bQueue: one more point. (`UVLBattle::AttackMove`, the commander's, does not resume.) |
| `OrderGuard(Units, Ward, bTroops, Platoon)`, `OrderGuardPlatoon(Units, N)`, `CanBeGuarded(Ward, Team, bTroops)` | posts in rings round a building (170 cm outside its walls), a Builder or King David (230 cm), 120 cm between rings; foes within `GuardLeash` 18 m of the ward (an archer: her bow's reach), 1.8 times that for one that struck the guard or the ward; a struck ward calls its guards in; the order ends when the ward falls. Builders do not guard. `bTroops` (the hero view's Option + click on a friend, V + left click, `vl.Guard`): any unit of their side may be the ward, not a tower's own archer; the enemy's commander and a right click still guard only buildings, Builders and the king. `Platoon`: the ward is that platoon's leader (else the member nearest its middle), the platoon's own members are left out of the guard, and when the ward falls it passes to the leader or the nearest member: it ends only when the platoon has nobody left. `GetGuardedUnits`, `GuardPlatoonOf` for the HUD |
| `OrderRoam(Units)` | the Spies wander 20-70 m at a time, to ground not visited lately, clear of foes' towers and castles; a leg over 40 s is dropped; struck: to the castle's door at a run, with an alert |
| `Dismiss(Units)` | troops gone for good, quietly, not counted as lost (never King David) |
| `MarchTogether(Units, Shape)`, `ToggleMarchTogether()` | in a formation the slowest always sets the pace and the march closes up as it goes (`AVLKing::PaceCap`; see *Marching together* below); Loose: per platoon / loose-selection setting, on by default; fights are at full speed |
| `GuardWardOf`, `GetGuards`, `IsRoaming`, `GetRoute`, `DescribeOrders`, `ClearStanding` | what a unit is on; ends it |

**Marching together** (`UVLCommand::UpdateMarchPace`, four times a second). Every troop walks 4.2 m/s and runs 7.6,
so "the slowest sets the pace" alone kept nobody together: a gap that was there when the order came (members standing
apart, some just back from a chase, a file through a narrow way) stayed for the whole march. So a march also
**closes up along its way**. By the way each has left to walk: the body's place is halfway between its middle member
and its rearmost; a unit more than 2.5 m ahead of that slows down, to 40% of the pace by 10.5 m ahead; a unit more
than 2.5 m behind hurries, up to its run by 8.5 m behind. One more than 60 m behind the middle is not waited for (it
runs to catch up). Nothing changes over the last 9 m, where each walks to its own place in the formation. A unit in a
fight, a chase or the player's hands is at its own speed and counts for nobody's. It holds for every order that
marches together (a move, the legs of a patrol or an attack-move, a Shift pathway, followers sent after their leader;
the enemy's squads too). `vl.Orders` shows each unit's speed and pace.

**Attacking together.** Fighters sent at a foe (an attack order, or a fight they pick up) go at a run when they have
more than 7 m to go (`UVLSwordsmanCombat::ChargeBeyond`): the swordsmen's first walk and every fresh route of their
chase, and the archers' walk into range. So archers and swordsmen sent at the same foe travel together; the archers
stop at their range (26-28 m) and shoot, the swordsmen go on. (Before, the archers walked unless the order said run,
while the swordsmen ran a moving foe down: the archers fell behind.) An attack also takes the place of the walk an
archer is on (`UVLArcherCombat::OrderAttack`), as it always did for a swordsman: an archer on an attack-move used to
walk on to the end of it before she shot, the fight she picked up being dropped every quarter of a second.

**Platoons keep together** (`UVLBattle::TickCohesion`, twice a second; the owner's call, 2026-11-22: "a platoon
should operate as a group"). The rule, for each member of a platoon that stands idle (no order, no fight):

- **To the fight.** If a member of its platoon is fighting further than 20 m away (`VLRules::CohesionLeash`), it runs
  to the nearest such member, fighting what it meets on the way (an attack-move), and joins in. It goes no further
  than 50 m from where it stood (`AggressiveLeash`), and that spot stays its post, so its own leash is measured from
  there.
- **Back to the body.** With no fight on, a member further than 30 m (`RegroupLeash`) from the platoon's body walks
  back to it. The body is the member with the most of the others within 15 m of it (the leader on a tie).

Who is left alone:

- **Defensive and Hold** platoons: a defensive member stays by its post and fights what it can strike within its
  20 m leash, as before; one holding its ground stands. Only an Aggressive member is moved.
- **Members ordered apart.** A member given an order without the rest of its platoon (a move, an attack, a patrol, a
  guard, the tower: anything that is not the unit's own doing) is apart on purpose. It is not pulled back, and its
  fights do not draw the platoon. It is one of the platoon again once it stands idle within 20 m of a member that is
  not apart, or when the whole platoon is ordered together.
- **Members far off when they join**: a platoon formed from troops standing apart, a recruit on its way from the
  barracks. Each is apart on purpose until it has come to the body.
- Anyone **on an order** (walking, on a patrol or attack-move route, a chain, following, guarding, roaming), on a
  **lookout** or on the way to one, a tower's own archers, **Builders and Spies**, the unit the player plays, and
  **King David** (he counts as part of the body, but is never sent anywhere by himself).

`vl.Cohesion` logs each platoon's members, its spread, who is apart on purpose and who is on its way to a fight;
`vl.BattleLog 1` logs each move it makes ("cohesion: ... runs to join ...").

Console (the four of 2026-11-21's second pass): `vl.Leaders` (each platoon's leader and who follows whom),
`vl.Follow <who> <unit name | king>`, `vl.HeroAim <unit name> | X Y [Z] [seconds]` (the hero view's crosshair taken to
be there), `vl.HeroOrder [run] [queue] | click | select [add]` (the hero view's right click / plain left click, always a
swing / Option + click at the crosshair, add: with Shift), `vl.Chains` (every order chain: its units, its items, what it
rejoins), `vl.Queue <who> X Y | work <building name> | clear | log`, `vl.Build ... queue`.

Console: `vl.Stop [who]`, `vl.Hold [who]`, `vl.Patrol <who> X Y [X Y ...] [run]`, `vl.AttackMove <who> X Y [queue]
[run]`, `vl.Guard <who> <building name | unit name | platoon N>`, `vl.Roam [who]`, `vl.Dismiss [who]`, `vl.March`, `vl.Orders`
(every unit's standing order, speed and pace). The audit of what the first draft had and where each is now:
`Docs/PORT_AUDIT.md`.

## King David

`Tools/blender/assets/king_b.py` builds him as a tree of rigid parts (`SM_KingB.json` lists each part's pivot and
parent): pelvis (`Body`) > `Chest` > `Head`, upper arms > forearms (> `HandR`, the sword hand, turning at the wrist),
thighs > shins, the cape's yoke > 5 columns of 4 hinged panels (`Cape<col><row>`), `Sword`, `Sheath`. (The spy,
`troop_spy.py`, adds `Spyglass` on `HandR` and the hood's tail `HoodA` > `HoodB` on `Head`, posed by `UVLSpy`; its
lantern is on the material slot `glow` and the tail on `sway`, which `import_king.py` gives an emissive instance and
an instance of the wind material `M_VoxSway`, the vertex alpha being how far a corner moves.) The sword is
modelled in the closed fist (grip through the fist, guard beyond the thumb, pommel behind) and never turns in it: the
blade is aimed with the arm and the wrist. **Faces** (2026-11-22): every figure's face is the archer's, built by one
function copied into each script, `archer_face`: one smooth skin plate, a 6 x 4 u white with a 3 x 4 u pupil centred
in it and a glint, a level brow above each eye, a small nose with a shadow under it, a short mouth line. Each figure
keeps its own touches through its arguments (a bigger or prouder nose, thicker brows, brows dipping toward the nose)
and its own beard of big plain blocks: King David's square black beard and moustache, the swordsman's short one, the
builder's full one, the farmer man's brown one. `--views
face,grip,head,hero,sides,...` the preview renders, `--search-sheath` re-runs the scabbard search (it is pinned).

**His pace** (`VLRules::Troop("King")`, applied in `AVLKing::BeginPlay`): a troop's, 420 cm/s walking and 760 running
(the owner's call, 2026-11-22: he walks with his men; it was 520 / 950). The code that made a quicker pace half a longer
stride and half a quicker step (`StrideScale` = sqrt(his walk / 420), acceleration, braking and the camera's lag scaled
by his run / 760) is kept for any other pace; at a troop's pace all of it is 1. With troops in a formation he keeps
their pace (March together).

`AVLKing::Animate` poses him each frame: a gait whose feet are placed on the ground and reached by a two-bone leg
solver, a jump with an airborne pose and a sprung landing, the three swings as runs of whole-body key poses
(`Swings` / `SwingPose` in `VLKing.cpp`), the cape as chains of damped pendulums (`UpdateCape`), the draw with the hand
reaching the hilt (`UpdateSword`). Tuning is on the actor (Details, category Voxel): `HitPauseSeconds`,
`HitFlashSeconds`, `HitFlashStrength`, `HitCatchUp`, `LandImpulse`, `LandDepth`, `LandSpring`, `LandDamping`, `RunLean`,
`RunElbow`, `CapeTrail`, `CapeInertia`, `CapeFall`, `CapeStiffTop`, `CapeStiffHem`, `CapeDamping`, `CapeFlutter`,
`CapeYawLag`, `bFootDust`; and on his `Dust` component: `PuffsPerStep`, `Size`, `Growth`, `Lifetime`, `Drift`, `Rise`,
`Color`, `Glow`. Other code hurts him with `ReceiveDamage(Amount)` (or Unreal's `ApplyDamage`).

## Sounds

- **The recordings** (`SourceArt/Audio/Raw/Footsteps{Dirt,Cement,Wood,Carpet}.wav`, one take of many steps each) are
  cut by `Tools/audio/slice_steps.py` into one-shots `S_Step_<Surface>_1..8` (mono, 48 kHz): a step is a burst of the
  loudness envelope (heel and toe together), cut from 8 ms before its onset to where it has died away, faded out, and
  brought to one loudness (the same for every surface). Weak steps, doubled ones and ones that run into the next are
  left out; the 8 most typical are kept (`KEEP`, `LEAD`, `TARGET_DB`, ... at the top of the script; `-v` lists every
  step it found). `Tools/ue/import_audio.py` imports them (not `Raw/`) with the order click `S_OrderMove`, as
  non-looping sounds held in memory, and deletes step assets whose `.wav` is gone.
- **The hero's steps** (`AVLKing::PlayFootstep`, `SurfaceUnder`): a foot comes down at the end of the half of the
  gait's cycle in which it is lifted, so the sound is on the visible foot at any speed: one step every
  stride / (2 x speed) seconds (about 0.16 s at his walk, 0.12 s at his run). A short trace down under that foot hits the
  mesh's own triangles; the material of the one hit (`MI_Vox_<slot>`) is looked up in `FootstepSurfaces`. A random
  clip of that surface, never the same twice running. Its volume fades with the distance from where the player is
  looking (`GetListenFocus`: the overview's focus) exactly as the shuffle's does, by the game mode's `ShuffleNear` 900 /
  `ShuffleRange` 4500 cm, and a step out of range is not played; the unit played in the hero view is always at full
  volume (`vl.StepLog 1` logs the distance and the fade). On the actor (Details, category Voxel > Footsteps):
  `bFootsteps`, `FootstepWalkVolume` 0.32, `FootstepRunVolume` 0.6, `FootstepRunPitch` 1.1, `FootstepPitchJitter` 0.06,
  `FootstepVolumeJitter` 0.15, `FootstepSurfaces` (slot -> Dirt / Cement / Wood), `FootstepDefault` Dirt.
- **The troops' shuffle** (`AVLGameMode::TickShuffle`, the Carpet steps): troops that are moving are gathered into
  groups (within `ShuffleGroupRadius` 700 cm of a group's first member); each group makes steps at
  `ShuffleRate` 2.2 a second x sqrt(its size), at most `ShuffleMaxRate` 6.5, from a random member's feet (`ShuffleRunBoost`
  1.3: faster and louder at a run). `ShuffleVolume` 0.2 within `ShuffleNear` 900 cm of where the player is looking (the
  hero, or the overview's focus), fading to nothing at `ShuffleRange` 4500 cm. Nothing when nobody moves.
  `bTroopShuffle` turns it off. On the game mode (Voxel > Audio > Shuffle).
- **Swords** (`UVLSwordFx`, `VLSwordsmanCombat.*`): a whoosh as each swing starts (`S_SwordSwing*`) and a thunk for each
  blow on a dummy (`S_TargetThunk*`), the king's and the swordsmen's; copies of the first draft's sounds in
  `SourceArt/Audio`. Console variables: `vl.Sword.SwingVolume` 0.3, `vl.Sword.HitVolume` 0.42, `vl.Sword.TroopVolume`
  0.65 (troops on orders, as a share of those), `vl.Sword.SoundGap` 0.12 s (a whoosh or thunk within that of the last
  is left out, so a company does not pile them up; the player's own are always heard), `vl.Sword.Near` 900 /
  `vl.Sword.Range` 4500 cm (the fade with distance from where the player is looking, as for the shuffle).
- **The order click**: `OrderVolume` 0.6, `OrderPitchJitter` 0.03 on the game mode (Voxel > Audio). Not played for
  `vl.Order` / `vl.RightClick`.
- `vl.StepLog 1` logs every step (surface, material, clip, volume, pitch), every shuffle step and every order click.

Console commands for testing (in the game's console, or `Tools/pie.py run "<cmd>"`):

| Command | Does |
| --- | --- |
| `vl.Attack` | a click: the next swing of the combo |
| `vl.Attack 1` / `2` / `3` | that swing: side slash / diagonal cut / up-down-up |
| `vl.Draw 0\|1` | sheathe / draw |
| `vl.Jump` | jump |
| `vl.Move Forward Right Seconds [run]` | as if the keys (and Shift) were held |
| `vl.Hurt [Amount]` | he takes damage: the white flash and the held pose |
| `vl.HitTune Pause [Flash [Strength]]` | set the pause and the flash (seconds, seconds, 0..1) |
| `vl.CamLag 0\|1` | the follow camera keeps him dead centre / trails him as usual |
| `vl.Order <who> X Y [Z] [run]` | an order to a world point (cm). who: `selection`, `all`, `troops`, `king`, `archers`, `swordsmen`, or a name (`Swordsman_2`) |
| `vl.SelectUnits <who> [add]`, `vl.Formation line\|column\|wedge\|square\|loose`, `vl.Platoon assign\|add\|select N` | the selection, its formation, the platoons |
| `vl.Dummies`, `vl.AttackDummy <who> [N] [run]` | log the training dummies (number, place, where each shows in the view: for `vl.Click`) / order units to attack dummy N (default: the nearest), as a left click on it does. `vl.CombatLog 1` logs every swing, blow and sword sound |
| `vl.Garrison <who> [building]`, `vl.EmptyTower [building]` | onto the watch tower / everyone down |
| `vl.Click U V [shift]`, `vl.Box U0 V0 U1 V1 [shift]`, `vl.RightClick U V [run]` | the overview's mouse at a point of the view (fractions 0..1); `vl.Screen <who \| X Y Z>` logs where things show |
| `vl.Spawn Swordsman\|Archer X Y [count]` | troops without training |
| `vl.Units` | log every unit: position, state, distance to its goal (each finished order also logs `arrived` / `GAVE UP`) |
| `vl.Path X0 Y0 X1 Y1`, `vl.ShowPaths [s]`, `vl.Grid [X Y [R]] \| rebuild` | log and draw a route / the units' routes / the grid's nodes |
| `vl.Look X Y [Zoom] [Yaw]`, `vl.Map realm\|realmv2\|highlands\|flatlands` | the overview camera over a point; open a map |
| `vl.Input click\|rclick [U V]`, `vl.Input wheel D`, `vl.Input pinch D`, `vl.Input scroll DX DY`, `vl.Input key NAME`, `vl.Input chord MOD KEY` (a modifier held while a key is pressed: `vl.Input chord LeftControl Five` is Ctrl + 5) | a real mouse / trackpad / key event, put in where the operating system's would be (through Slate, the pointer moved to the middle of the game's view or to U V: it moves the real pointer). It logs what is under the pointer; the game's window has to be in front. `vl.InputLog 1` logs the clicks, wheel steps and gestures the player's unit sees, with the zoom |
| `vl.StepLog 0\|1` | log the step sounds (see *Sounds*) |
| `vl.Record Name Frames [Fps]`, `vl.At Frame <cmd>` | save a frame sequence at a fixed time step, running commands at given frames |

Motion previews: with PIE running, `sh Tools/mac/rec.sh <name> <frames> "<frame> <command>" ...` records
`Saved/Screenshots/VL/<name>_NNN.png` (30 frames a second of game time whatever the real frame rate), and
`Tools/.venv/bin/python Tools/sheet.py gif|strip|sheet ...` turns them into a GIF or a contact sheet. The ones made
for this pass are in `Saved/Previews/KingDavid/`.

## Look settings

Sun, sky, fog, exposure and lamp strength are the `P` table at the top of `Tools/ue/build_level.py`; texture colours
are the palettes in `voxtex.py`; how much blocks differ from each other is `jitter` in `voxmats.py`.

## Performance

The optimization pass of 2026-11-21 (plan, decisions and before/after numbers: `Docs/Optimization/PLAN.md`).

- **Graphics settings** (`VLGraphics.*`, Esc > Settings > GRAPHICS). High is the look as approved, plus changes that
  do not show: TSR history at 100 %, no indirect lighting cache, a coarser volumetric-fog grid once the overview camera
  is high above everything the fog can reach, lamps fading out from 220 m to 300 m. Medium: Lumen final gather and
  scene detail 1.0 (the maps' post-process volume keeps 2.0 for High), a coarser fog grid (16 px, 64 slices), render scale 85 %.
  Low: Lumen off (sky light with distance-field AO), no volumetric fog, render scale 70 %. Virtual shadow maps stay on
  at every level. "Render scale 100 %" is the engine's own choice for the window size (about 78 % in the packaged
  game's window); lower values are that share of it. Console: `vl.Gfx.Quality 0|1|2`, `vl.Gfx.Scale N`,
  `vl.Gfx.Lamps <draw cm> <fade cm>`.
- **Units** (`VLKingRig.cpp`). Each unit's pose is computed into a buffer and written to its parts once a frame, after
  the camera moves; `Figure` is absolute, so capsule moves no longer drag 70 components. Units out of view are not
  posed (their gameplay clocks run on), far ones pose at 30 / 20 Hz with the cape held beyond 150 m, and a part is only
  re-sent to the renderer once it moved 0.25 px. King David and the unit you play are always full rate. Read a part's
  place with `AVLKing::RigWorld(RigFind(Name))`, never from its component (it is only current while in view). Only a
  pawn you have played has a spring arm and cameras. Custom depth is off on the title screen and beyond 400 m.
- **Unit registry** (`UVLBattle::AllUnits`, `UnitsNear`, `Selectables`, `Dummies`; `EVLUnitKind`): every unit in spawn
  order and a 4 m spatial hash rebuilt once a frame, used by separation steering, target acquisition, defences, arrows,
  the HUD and the commander instead of scanning every actor.
- **Load**: the path grid samples its rows in parallel (Realm 1.06 s -> 0.18 s, Highlands 1.96 s -> 0.30 s); the
  placement ghost reuses its ground samples per cell; a building laid among trees rebuilds the grid once.
- **Apple Silicon pass** (merged 2026-11-21 from `t3/apple-silicon-optimization`, `Docs/Optimization/AppleSilicon/` on
  that branch): `Config/Mac/MacDeviceProfiles.ini` (runtime `r.Nanite=0`, which no mesh here uses, so the forced depth
  prepass goes; `r.TranslucencyLightingVolume=0`, our two translucent materials being unlit; VSM pool 2048 pages),
  `r.DBuffer=False`, `r.MegaLights.Supported=False`, no ray-tracing shaders, Metal 3.0, stripped metallibs, PSO
  precaching for METAL_SM6, a 256 MB streaming pool, arm64-only builds, Shipping ThinLTO; P/E-core worker sizing
  (`vl.Opt.MacWorkers`: 4 -> 12 workers on an M5 Pro, packaged only) and user-interactive QoS on the game, render and
  RHI threads (`vl.Opt.MacQoS`); a 40 fps frame-rate choice and Settings > Dynamic resolution (Off / 60 / 40 / 30 fps,
  `vl.Gfx.DynRes`); packaged only: 30 fps in menus and 15 fps while the window is not in front (`vl.Opt.IdleThrottle`),
  40 fps under Serious heat or Low Power Mode and 30 fps + dynamic resolution under Critical heat (`vl.Opt.ThermalGuard`).
  The branch's `r.Lumen.Reflections.MaxRoughnessToTrace=0.55` was left out: the engine's default here is 0.4, so it
  would trace more surfaces, not fewer. Measured (packaged Development, L_Realm, Hard, AI against AI, overview 0.45,
  10 min each, M5 Pro on mains, window uncapped): before 61.8 fps (GPU 15.5 ms, game thread 1.6 ms), after 61.3 fps
  (GPU 15.7, 1.6): the same within the battles' variation; the runtime GPU settings flipped in one scene: within
  0.2 ms. No thermal or performance warning in either run, no drift beyond the battle growing. Content 861 -> 806 MB.
- **Music** is not loaded at all while its setting is 0; above 0 one song at a time is loaded in the background.
- **Packaging**: `sh Tools/mac/package.sh` builds Shipping (no console, no log, no command inbox, symbols stripped);
  `sh Tools/mac/package.sh Development` for tests (on Windows `Tools\windows\package.ps1`, the same two builds: see
  *Platforms*). Only Metal SM6 shaders are cooked (`Config/Mac/MacEngine.ini`), on Windows only Direct3D 12 SM6
  (`Config/Windows/WindowsEngine.ini`); the NNE plugins are off; the old `SM_King_*`, `SM_KingA_*`, `SM_KingB_*` (in Meshes), `SM_KingT_*` meshes are never cooked.
- **Switches** for comparing old and new paths in one session (all default to the new path):
  `vl.Opt.RigBatch`, `vl.Opt.RigLOD`, `vl.Opt.RigPixelError`, `vl.Opt.RigFarDist`, `vl.Opt.RigCullMargin`,
  `vl.Opt.UnitDepth`, `vl.Opt.UnitDepthFar`, `vl.Opt.UnitGI`, `vl.RigStats 1`, `vl.RigCheck`; `vl.Opt.Registry`,
  `vl.Opt.Hud`, `vl.Opt.Ambience`, `vl.Opt.RegistryCheck 1`, `vl.Opt.Timing`; `vl.Opt.FarFog`, `vl.Opt.MinimapFast`;
  `vl.Opt.ParallelGrid`, `vl.Opt.FastRegions`, `vl.Opt.Placement`, `vl.Opt.GridChecksum 1`, `vl.PlacementLog`,
  `vl.PlacementBench <kind> X Y [n]`, `vl.Music [0..1]`.
