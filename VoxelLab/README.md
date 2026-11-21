# VoxelLab: the voxel-style sandbox

A separate Unreal 5.8 project inside the Sovereign Realms repo for trying the Minecraft-like look before porting it to
the game. Nothing here touches the main game. Three levels, switched from the Esc menu (or M while it is open: the
next one round); the packaged game starts in the town:

- `L_Town`: the island town of `References/Remake/town.png`: the castle and its plaza in the middle, the barracks and
  its yard to the east, the archery range on the west terrace, the mine and the watch tower on the high ground behind
  it, two cottages with their paddocks by the plaza, the farmstead, the fenced plots (`References/Remake/farmland.png`),
  the lily pond and the windmill on the east terrace, a river off that terrace over two falls to the sea, the bridge,
  and the dock with its boat under the west cliff.
- `L_VoxelVillage`: the village of `References/village.png` in its forest. The castle now stands at the head of the
  plaza and the town hall across the river at the end of the road (`SWAP` in `village_layout.py` puts them back).
- `L_Flatlands`: every building side by side on flat grass along one road, at its village size, each with its name in
  front, for reviewing them and checking the look. Same controls as the village.

Reference renders of each building on flat ground, King David beside it for scale, are in `References/Buildings/`
(`<Name>.png` three-quarter view, `<Name>_front.png`, `Lineup.png` all of them at one scale).

## Play

- Packaged app: `Builds/Mac/VoxelLab.app` (first time: right-click > Open).
- Or open `VoxelLab.uproject` and press Play.

There are two ways to play, switched with **Tab**.

**Hero** (the camera follows King David at the diorama angle)

| Input | Does |
| --- | --- |
| W A S D / arrows / left stick | walk (relative to the view) |
| Mouse | look around: left/right turns the view, up/down tilts it (the pointer is hidden; a crosshair shows where swings and arrows go). Esc, Tab or C bring the pointer back. Speed: Esc menu > Look speed (or L there), 25-150%, default 50%; calmer when zoomed out. Esc menu > Invert look (or I there): Off / Left-right / Up-down / Both |
| Shift, or double-tap a direction | run (after a double tap he runs until the keys are let go) |
| Space | jump |
| F | draw / sheathe the sword |
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
| Shift + right click | a point on the selection's pathway (as in the main game): units already on an order walk there after it, in order; idle ones start at once. A plain right click replaces the pathway |
| Right click on the Watch Tower | the archers of the selection walk to its door and appear on the lookout (8 posts); anyone else waits by the door |
| Select the Watch Tower | its panel (bottom right) shows who mans it; **Send them out** brings them down. An archer on the lookout can also be selected and sent somewhere: it comes down first |
| F | the next formation: Line, Column, Wedge, Square, Loose (melee in front, archers behind) |
| A, then left click on the ground | attack-ground: the selection's archers shoot at that spot three times (walking into range first). It lapses after 5 s or on a right click |
| Left click on a training dummy (archers selected) | they walk to within about 21 m with a clear shot, face it and shoot every 2.4 s until given another order. Archers on the watch tower shoot from the lookout (to 42 m) |
| Ctrl / Cmd / Alt + 1..6 | make the selection platoon N (a platoon keeps its own formation; they are listed top left) |
| 1..6 | select platoon N (twice quickly: look at it). Shift + 1..6 adds the selection to it |
| Enter / double click on a unit | take control of it (back to hero) |

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

Her aim (`AVLKing::GetAimPoint`, which the king's swing uses too) is where the crosshair's ray meets the world **ahead of
her**: the ray is followed only from the point level with her onwards, so a tree, roof or fence between the camera and
her, although drawn under the crosshair, never catches it and she never turns round to shoot at the camera. Units and
the tree crowns the camera cuts away (`Canopy`) do not catch it either; a crosshair on the sky aims `SkyAimDistance`
(30 m) along its ray. With the pointer shown: what the pointer is over, else the ground at her feet.

Arrows (`UVLArrows`, `VLArrow.*`) are pooled mesh components: one sticks in what it hits (a dummy rocks and carries it),
fades out and is taken back 2 s after landing (`vl.Arrow.Life`, `vl.Arrow.Fade`, `vl.Arrow.Pool`; volumes
`vl.Arrow.ReleaseVolume` 0.3, `FlyVolume` 0.1, `HitVolume` 0.26). Their material is `M_VoxArrow`
(`python3 Tools/ue_py.py Tools/ue/build_arrow_material.py`). The archer's tunables are on the component (Voxel > Archer):
`ArrowSpeed` 2300, `ArrowGravity` 980, `ReachSeconds` / `NockSeconds` / `DrawSeconds` / `LooseSeconds`, `Range` 2400,
`TowerRange` 4200, `ShotInterval` 2.4, `ShotJitter`, `SpreadYaw` 1.2, `SpreadPitch` 0.8, `GroundShots` 3, `DrawMoveScale` 0.55,
and the pose (`CarryArmPitch`, `BowCant`, `ChestTwist`, `Anchor`, ...). Console: `vl.Archers` (state and how each holds the
bow), `vl.Arrows`, `vl.ArcherLog 1`, `vl.Bow draw 0|1 | shoot | lock | cancel | bash | aim X Y [Z] | off`, `vl.ShootAt <who> X Y`,
`vl.ArmGround`, `vl.AttackDummy archers [N]`.

**Both**: mouse wheel zooms (the view steepens as it pulls back; far out to 95 m in the hero view and 195 m in the
overview: `ArmFar`, `PitchFar`, `OverviewFar`, `OverviewPitchFar`, `ZoomStep` on the actor, Voxel > Camera; zooming
while the postcard view is up goes back to the view that zooms), Q / E or a right-button drag turn the view, R turns
it back, V cycles the camera angle (Classic steep / Low / Battlefield shallow, as in the main game; saved), C shows the postcard view (the reference picture's camera), Esc (or P) opens the menu (Resume / the other
two maps / Quit; Enter resumes, M goes to the next map, X quits).

**Trackpad**: pinch zooms, a two-finger twist turns the view. Two-finger scroll pans the overview (the ground follows
the fingers) and in hero mode turns the view (sideways) and zooms (up / down). A two-finger click is a right click;
Ctrl- or Cmd-click also sends the selected king.

**Sound underfoot.** Each time one of King David's feet comes down a recorded step plays, chosen by what the foot is
on: dirt (grass, earth, farm soil, the yards), cement (stone, cobble, gravel, the castle steps, the plaza) or wood (the
bridge, the dock, plank paths, decks, the tower's lookout); softer at a walk, louder and a little higher at a run, and
a firm one when he lands. Troops on the march make a soft shuffle as a group, and a move order given by hand in the
overview (right click, Ctrl / Cmd + click, "Send them out") clicks. See *Sounds* below.

At a run his feet raise puffs of dust (also on landing and on braking hard out of a run). When he is hurt he flashes
white and his pose holds for a moment, while the game carries on (there is nothing in the sandbox that hurts him yet:
`vl.Hurt` in the console, below).

**Troops** (the swordsman and the archer, `Tools/blender/assets/troop_*.py`): in the overview select the **Barracks**
(swordsmen) or the **Archery Range** (archers) and click **Train** in the bottom-right panel; each takes 3 s, several
can be queued, and they walk out through the yard's gate and line up outside. Select troops and right click to send
them somewhere, Enter or a double click to take control of one (walk, run, jump). A swordsman you control fights as the king does:
left click swings, through the same three-swing combo and battle stance, and the dummies take the blows; his sword has
no scabbard and is always in his hand, so F does nothing. To go back to the king,
Tab to the overview, select him and press Enter. Console: `vl.Train Barracks 3`, `vl.Control Swordsman 1`,
`vl.Control king`. Troops are imported like the king:
`python3 Tools/ue_py.py -c "KING='SM_Swordsman'; DST='/Game/Voxel/Troops/Swordsman'; DA='DA_Swordsman'; exec(open(r'<abs>/Tools/ue/import_king.py').read())"`
(and `SM_Archer` / `Archer` / `DA_Archer`).

Where a tree or a building hides the king, his gold silhouette shows through it. Banners, flags, grass, flowers and
wheat sway in the wind.

## How it is made

Everything is generated by scripts, so any change can be rebuilt end to end.

| Step | Command | Writes |
| --- | --- | --- |
| Pixel textures | `../Tools/.venv/bin/python Tools/blender/voxtex.py` | `SourceArt/Textures/T_Vox_*.png` |
| All assets + terrain + layout | `sh Tools/blender/build_all.sh` | `SourceArt/Meshes/*.gltf`, `SourceArt/layout.json` |
| Import into Unreal (editor open) | `python3 Tools/ue_py.py Tools/ue/import_assets.py` | `/Game/Voxel/...` |
| Step sounds from the recordings | `../Tools/.venv/bin/python Tools/audio/slice_steps.py` | `SourceArt/Audio/S_Step_<Surface>_<n>.wav` |
| Import the sounds (editor open) | `python3 Tools/ue_py.py Tools/ue/import_audio.py` | `/Game/Voxel/Audio` |
| Water material | `python3 Tools/ue_py.py Tools/ue/build_special_materials.py` | `M_VoxWater` |
| King David | `python3 Tools/ue_py.py -c "KING='SM_KingB'; exec(open(r'<abs>/Tools/ue/import_king.py').read())"` | `/Game/Voxel/King/DA_King` |
| The level | `python3 Tools/ue_py.py Tools/ue/build_level.py` | `/Game/Maps/L_VoxelVillage` |
| Flatlands plan + ground | `Blender -b --factory-startup --python Tools/blender/assets/flatlands.py` | `SourceArt/flatlands.json`, `SM_Flat_*` |
| Flatlands level | `python3 Tools/ue_py.py Tools/ue/build_flatlands.py` | `/Game/Maps/L_Flatlands` |
| Town: ground, water, plan | `Blender -b --factory-startup --python Tools/blender/assets/town_terrain.py -- --no-render` | `SM_TownGround_*`, `SM_TownWater`, `SM_TownSea`, `SourceArt/town.json` |
| Town: its own assets | `Blender -b --factory-startup --python Tools/blender/assets/windmill.py` (and `dock.py`, `hay_cart.py`) | `SM_Windmill`, `SM_Windmill_Sails`, `SM_Dock`, `SM_Boat`, `SM_HayCart` |
| Town level (after importing those meshes) | `python3 Tools/ue_py.py Tools/ue/build_town.py` | `/Game/Maps/L_Town` |
| Town, all of the above but its own assets | `sh Tools/town_rebuild.sh` (`layout`: only the plan changed) | |
| Building renders | `Blender -b --factory-startup --python Tools/blender/render_buildings.py [-- NAME ... LINEUP]` | `References/Buildings/*.png` |
| Package | `sh Tools/package.sh` | `Builds/Mac/VoxelLab.app` |

- `Tools/blender/voxlib.py`: the voxel mesher (culled cube faces, baked corner shading, per-block colour variation,
  lamp positions from `glow` voxels). `voxkit.py`: shared roofs, windows, lanterns, banners. `voxmats.py`: materials.
- `Tools/blender/assets/*.py`: one generator per asset group (town hall, barracks, range and mine, farm, nature,
  props, castle, terrain, king). `ASSET_BRIEF.md` is the style guide they were written to.
- `Tools/blender/village_cam.py`: the postcard camera. `village_layout.py`: the village plan, given as **pixels of the
  reference picture** and unprojected through that camera, so things land where they are in the picture.
  `fit.py` solves each building's position and scale against its box in the picture.
- `Tools/blender/town_cam.py`, `town_layout.py`: the town's postcard camera and its plan, in world metres (heights,
  the coast, the river, paths that carry a height at every point so that a change of height becomes a flight of steps,
  buildings, fences, plots, trees, scatter). `python town_layout.py --debug` (the `../Tools/.venv` python) draws the
  plan through the camera over the picture (`Saved/town_plan.png`). `Tools/compare.py <shot> <out> References/Remake/town.png`
  compares a postcard shot with the town's picture.
- `Tools/pie.py` drives Play-In-Editor from the shell (`start`, `run "vl.View postcard"`, `shot <name>`), and
  `Tools/compare.py <shot>` puts a screenshot next to the reference.
- `Source/VoxelLab`: `AVLKing` (the character: rigid voxel parts posed in code, the diorama camera, the canopy
  cut-away), `UVLFootDust` (the dust of his running feet), `AVLGameMode` (console commands `vl.*`), `AVLHUD` (the Esc
  menu, the selection rings, the platoon list, the training and tower panels), `AVLAmbience` (cube motes and chimney
  smoke), `UVLGrid` (where units can walk, and routes), `UVLCommand` (selection, platoons, formations, orders, the
  watch tower's garrison).

## Orders: paths, platoons, the tower

Reimplemented here from the main game's ideas (`SRGridSubsystem`, `SRFormation`, `SRPlatoonSubsystem`,
`SRPlayerController`, `SRBattleSubsystem::CommandMove`); nothing was migrated.

- **`UVLGrid`** (`VLGrid.*`) samples the level once at the start of play on 50 cm cells (about 0.15 s). Because the
  voxel world has floors over floors (the bridge over the river bed, ground under eaves and gate beams, the tower's
  lookout), a cell holds a stack of nodes, one per floor: found by tracing down through the cell until the ground
  (actors tagged `Ground`, or `SM_Terrain*` / `SM_Flat_*` meshes) is reached; kept if there is air with headroom over
  it, a unit's capsule fits there clear of everything taller than a step, and it is not under water (meshes on actors
  tagged `Water` are asked where their surface lies). Neighbouring nodes are joined where the step is at most 58 cm
  (`MaxStepHeight`), diagonals only where both sides are joined. Then, as in the main game: regions of connected
  ground, one A* outward from the goal for a whole group, routes that keep off walls where there is room and are
  pulled straight to a few corners, clicks on a roof / cliff / water taken to the nearest ground the unit can reach,
  formation slots moved onto standable ground.
- **Units** (`AVLKing::FollowPath / AutoSteer`): walk their corners in turn, keep a little apart from each other,
  pass through one another while on the march (capsules that block jam a gate), and plan afresh from where they stand
  if they stop making way. The king ordered from the overview, troops, and troops leaving a building after training
  all go this way. A unit that falls in the water is put back where it last stood on land.
- **`UVLCommand`** (`VLCommand.*`): the selection, six platoons, `VLFormation::ComputeSlots` (the main game's ranks:
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

## King David

`Tools/blender/assets/king_b.py` builds him as a tree of rigid parts (`SM_KingB.json` lists each part's pivot and
parent): pelvis (`Body`) > `Chest` > `Head`, upper arms > forearms (> `HandR`, the sword hand, turning at the wrist),
thighs > shins, the cape's yoke > 5 columns of 4 hinged panels (`Cape<col><row>`), `Sword`, `Sheath`. The sword is
modelled in the closed fist (grip through the fist, guard beyond the thumb, pommel behind) and never turns in it: the
blade is aimed with the arm and the wrist. `--face K|A|B|C` picks the face (K is the approved one), `--views
face,grip,head,hero,sides,...` the preview renders, `--search-sheath` re-runs the scabbard search (it is pinned).

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
  stride / (2 x speed) seconds (about 0.21 s at a walk, 0.16 s at a run). A short trace down under that foot hits the
  mesh's own triangles; the material of the one hit (`MI_Vox_<slot>`) is looked up in `FootstepSurfaces`. A random
  clip of that surface, never the same twice running. On the actor (Details, category Voxel > Footsteps):
  `bFootsteps`, `FootstepWalkVolume` 0.32, `FootstepRunVolume` 0.6, `FootstepRunPitch` 1.1, `FootstepPitchJitter` 0.06,
  `FootstepVolumeJitter` 0.15, `FootstepSurfaces` (slot -> Dirt / Cement / Wood), `FootstepDefault` Dirt.
- **The troops' shuffle** (`AVLGameMode::TickShuffle`, the Carpet steps): troops that are moving are gathered into
  groups (within `ShuffleGroupRadius` 700 cm of a group's first member); each group makes steps at
  `ShuffleRate` 2.2 a second x sqrt(its size), at most `ShuffleMaxRate` 6.5, from a random member's feet (`ShuffleRunBoost`
  1.3: faster and louder at a run). `ShuffleVolume` 0.2 within `ShuffleNear` 900 cm of where the player is looking (the
  hero, or the overview's focus), fading to nothing at `ShuffleRange` 4500 cm. Nothing when nobody moves.
  `bTroopShuffle` turns it off. On the game mode (Voxel > Audio > Shuffle).
- **Swords** (`UVLSwordFx`, `VLSwordsmanCombat.*`): a whoosh as each swing starts (`S_SwordSwing*`) and a thunk for each
  blow on a dummy (`S_TargetThunk*`), the king's and the swordsmen's; copies of the main game's sounds in
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
| `vl.Look X Y [Zoom] [Yaw]`, `vl.Map town\|flatlands\|village` | the overview camera over a point; open a map |
| `vl.Input click\|rclick [U V]`, `vl.Input wheel D`, `vl.Input pinch D`, `vl.Input scroll DX DY`, `vl.Input key NAME` | a real mouse / trackpad / key event, put in where the operating system's would be (through Slate, the pointer moved to the middle of the game's view or to U V: it moves the real pointer). It logs what is under the pointer; the game's window has to be in front. `vl.InputLog 1` logs the clicks, wheel steps and gestures the player's unit sees, with the zoom |
| `vl.StepLog 0\|1` | log the step sounds (see *Sounds*) |
| `vl.Record Name Frames [Fps]`, `vl.At Frame <cmd>` | save a frame sequence at a fixed time step, running commands at given frames |

Motion previews: with PIE running, `sh Tools/rec.sh <name> <frames> "<frame> <command>" ...` records
`Saved/Screenshots/VL/<name>_NNN.png` (30 frames a second of game time whatever the real frame rate), and
`../Tools/.venv/bin/python Tools/sheet.py gif|strip|sheet ...` turns them into a GIF or a contact sheet. The ones made
for this pass are in `Saved/Previews/KingDavid/`.

## Look settings

Sun, sky, fog, exposure and lamp strength are the `P` table at the top of `Tools/ue/build_level.py`; texture colours
are the palettes in `voxtex.py`; how much blocks differ from each other is `jitter` in `voxmats.py`.
