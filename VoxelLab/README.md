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
- `L_Highlands`: the second battle map, 540 m square: a bluff to build on behind each castle, the river's gorge, and
  the Crown, a mesa in the middle with two neutral gold mines (see *The highlands*). `L_Realm` is the first.
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
| Left click on one of your units (the crosshair on it) | select it (Shift: add it / take it out; twice quickly: take control of it). Not while a foe is within 4 m of you or a bow is drawn: then the click is your own blow. Alt / Option + click: always a selection (on the ground: let the selection go). The crosshair says what a click does there (gold "Click: select ...", red "Right click: attack ...") and the mode box top left whom you command |
| Right click (Ctrl / Cmd + click; an archer or spy played: Ctrl / Cmd + click only) | the selected troops (never the unit you play) go where the crosshair points, or attack the foe's unit or building under it, with the overview's order marker and click; twice quickly: at a run; Shift: on their pathway (Builders: their queue). On one of your troops: the others follow it. 1..6 select platoon N; **G**: follow me (the selection, or else your platoon, falls in behind you) |
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
| Shift + right click | a point on the selection's pathway (as in the main game): units already on an order walk there after it, in order; idle ones start at once. A plain right click replaces the pathway |
| Right click on the Watch Tower | the archers of the selection walk to its door and appear on the lookout (8 posts); anyone else waits by the door |
| Select the Watch Tower | its panel (the selection panel, bottom middle) shows who mans it; its **Lookout** button brings them down. An archer on the lookout can also be selected and sent somewhere: it comes down first |
| F | the next formation: Line, Column, Wedge, Square, Loose (melee in front, archers behind) |
| A (a tap), then left click | attack-move: the selection marches there fighting what it meets, and marches on after each fight (Shift + click: one more point of the way; a click on a foe attacks it). Archers alone: A arms attack-ground first; with others, A twice |
| A (archers), then left click on the ground | attack-ground: the selection's archers shoot at that spot three times (walking into range first). It lapses after 5 s or on a right click |
| S (a tap) / H | stop (drop every order) / hold ground (until the next order, strike only what is in reach). With units selected a tap of A or S is the order and a hold (over 0.17 s) pans, as in the main game; with nobody selected they pan at once |
| P, then left click | patrol between where they stand and there, round and round, fighting what they meet; Shift + click: one more point of the loop (P stays armed). P is the pause key only when nobody is selected |
| V, then left click (or right click on it) | guard one of your buildings, a Builder or King David: posts in a ring round it, fighting what comes within 18 m of it; the order ends when it falls. Troops cannot be guarded. With no troops selected V is the camera angle |
| O | the selected Spy roams (struck, it runs home to the castle) |
| M | march together on / off (the slowest sets the pace; in a formation always, so it only matters with Loose) |
| K K | dismiss the selected troops (the first press asks; no refund; not King David) |
| Alt / Option + click | every unit of that kind in view (Shift: added) |
| Space / Home | centre the view on the selection (or the selected building) |
| Left click on a training dummy (archers selected) | they walk to within about 27 m with a clear shot, face it and shoot every 2.4 s until given another order. Archers on the watch tower shoot from the lookout (to 55 m) |
| Ctrl / Cmd / Alt + 1..6 | make the selection platoon N (a platoon keeps its own formation; they are listed in the platoon panel, bottom right) |
| 1..6 | select platoon N (twice quickly: look at it). Shift + 1..6 adds the selection to it |
| Delete | disband the selected platoon (the troops stay selected) |
| (platoon leaders) | a platoon gets a leader when it is formed (King David if he is in it, else its longest-serving troop that is not a Builder); the platoon's tag floats over the leader with a crown, the platoon panel's row and the selection panel show it ("led by ..." / "no leader"). The leader takes the front-middle slot of its ranks on every move, so the formation forms up on it. **If it falls the platoon has no leader** ("The leader of platoon N has fallen"): nobody steps up. A member becomes leader when you take control of it (the platoon's idle members then fall in behind it) or when the platoon's members are ordered to follow it. Re-forming with Ctrl + N gives the new platoon its senior member |
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
while the postcard view is up goes back to the view that zooms), Q / E or a right-button drag turn the view, R turns
it back, V cycles the camera angle (Classic steep / Low / Battlefield shallow, as in the main game; saved), C shows the postcard view (the reference picture's camera), Esc (or P) opens the pause menu (an armed
attack-ground is cancelled first; see *The interface*; in it Enter resumes, M goes to the next map, U music, V camera
angle, L look speed, I invert look, X quits).

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

**Troops** (the swordsman, the archer and the spy, `Tools/blender/assets/troop_*.py`): in the overview select the **Barracks**
(swordsmen), the **Archery Range** (archers) or the **Castle** (the Spy, from castle level 3) and click the recruit button of the selection panel (bottom middle); several
can be queued (Shift 5, Ctrl 10). A barracks or range is raised by Builders first (*Building*). A trained troop **waits in the
building's yard**, in ranks (the barracks' fenced yard in front of its hall, the range's yard inside its rail fence;
facing the gate), until sent somewhere; with a rally point set (right click with the building selected) it walks out to
it instead, and one that joins a platoon (the Joins chips) marches to the platoon. Select troops and right click to send
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
As in the main game he is trained at the **castle** (its panel's Builder button): 120 gold + 80 food, 14 s, 110 health,
no housing but a limit of his own by the castle's level (2, 3, 3, 4, 4, 5, 6); he joins no platoon from recruitment.
**Only Builders build**: see *Building* below. At his work he swings the hammer (the up-down-up blows) and the main
game's hammer and saw sounds play.

## Building (`UVLConstruction`, `VLConstruction.*`; HUD `VLHUDBuild.cpp`)

The main game's construction (`SRBuilding.cpp` site / StepConstruction / CancelConstruction / Demolish,
`SRPlacementPreview`, `SREconomySubsystem::PlaceBuilding`, the builders' `OrderBuild` / `StepBuild` / `LookForWork`, the
build menu of `SRHUDGame.cpp`), without the castle's building zone: the player builds where he wants, and every site rises
only while a Builder works at it.

| Building (menu tab) | Model | Cost | Time (one Builder) | Limit |
| --- | --- | --- | --- | --- |
| Farm (Economy) | `SM_Farmstead_A/B/C` in turn (each side round robin, so neighbours differ; `SM_Farmstead` while they are not imported) | 90 gold | 14 s | 3, +1 a castle level |
| Gold Mine (Economy) | `SM_MineCliff`, on a gold vein only: a neutral mine (taken over) or the ruin of a fallen one | 140 gold | 16 s | - |
| Barracks (Military) | `SM_BarracksYard` | 110 gold | 16 s | - |
| Archery Range (Military) | `SM_ArcheryHall` | 125 gold | 16 s | - |
| Watch Tower (Defence) | `SM_WatchTower` (its lookout tag added when done) | 160 gold | 18 s | 2, +1 a castle level |

Limits count only what a side raised in the match (the map's own farms and tower are its endowment). Granary and
Treasury have no voxel model, and the main game never built a town hall, so they are not in the menu.

- **The menu**: the Build button left of the selection panel (or **B**); tabs Economy / Military / Defence (clicked; Tab is
  the hero view's key here), cards with the price, the limit used, the key 1-6, the refusal (limit, gold, no Builder).
- **Placing**: a ghost of the building follows the pointer (`M_PlacementGhost`, `Tools/ue/build_ghost_material.py`: green
  glass where it fits, red where not), snapped to the half-metre blocks, **its front (gate, yard) toward the view**: turn
  the view (Q / E) to turn it, in steps of 90 degrees (the main game had no rotation). Plates of a metre on the ground show
  which ground refuses it (red: uneven by more than 30 cm, water, something standing there; a pale fringe of 2 m round
  it, red where blocked); a pill at the pointer says why, or how many trees it clears. Also refused: within 1 m of another
  building, enemy troops on it, the map's edge, a gate opening onto ground nobody can walk to. LMB places it (paid
  then), Shift + LMB places another, RMB / Esc cancels.
- **The site**: the trees in its footprint and 1.5 m round it are cleared (`AVLForest::ClearTreesAround`), the path grid
  is sampled again there (`UVLGrid::RebuildArea`), one's own troops on it step aside. Its own mesh stands hidden with its
  collision up while a copy rises course by course (14 steps, as the main game's walls); its health rises from 15%
  with it. The selected Builders go to it, else the nearest free one. Each Builder beyond the first adds 100% speed (two build twice as fast), up
  to 4. A site does nothing (no training, housing, payouts, shots, upgrades). When done: its props (the barracks'
  training dummies, a farm's wheat, sheep, chickens or pigs: `VLBuildingProps.inl`, written by
  `python3 Tools/ue/gen_building_specs.py` from the jsons), an alert and the main game's bell.
- **The Builders' queue (Shift)**: with Builders selected, Shift + right click on the ground (or the minimap) queues a
  walk, on a site or a damaged building of yours queues work on it, on a free mine queues its claim (paid at once),
  and Shift + click while placing lays the site at once and queues it (the ghost stays up for the next). The selected
  Builders all get the same queue and work through it together (two on a site: twice as fast); an item that has
  lapsed by its turn (the site cancelled or fallen, the building mended) is passed over. A plain order replaces the
  queue, **Esc** (after a placing or an armed click) or **Stop** clears it; a Builder with a queue is never taken for
  an idle Builder's own work or as "the nearest free Builder". While they are selected a numbered chain of markers
  shows it (walks blue, buildings gold); the panel says "N orders queued (Esc clears)". A site laid over a queued
  Builder steps him aside and keeps his queue.
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
  gold) and makes it a site by the usual rules: it does nothing until Builders have worked it through (16 s with one,
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
- **Not ported**: the main game's site / damaged / ruin meshes and scaffold (none in voxel yet: the walls rise from the
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
| Pixel textures | `../Tools/.venv/bin/python Tools/blender/voxtex.py` | `SourceArt/Textures/T_Vox_*.png` |
| All assets + terrain + layout | `sh Tools/blender/build_all.sh` | `SourceArt/Meshes/*.gltf`, `SourceArt/layout.json` |
| Import into Unreal (editor open) | `python3 Tools/ue_py.py Tools/ue/import_assets.py` | `/Game/Voxel/...` |
| Step sounds from the recordings | `../Tools/.venv/bin/python Tools/audio/slice_steps.py` | `SourceArt/Audio/S_Step_<Surface>_<n>.wav` |
| Import the sounds (editor open) | `python3 Tools/ue_py.py Tools/ue/import_audio.py` | `/Game/Voxel/Audio` |
| Water material | `python3 Tools/ue_py.py Tools/ue/build_special_materials.py` | `M_VoxWater` |
| King David | `python3 Tools/ue_py.py -c "KING='SM_KingB'; exec(open(r'<abs>/Tools/ue/import_king.py').read())"` | `/Game/Voxel/King/DA_King` |
| The level | `python3 Tools/ue_py.py Tools/ue/build_level.py` | `/Game/Maps/L_VoxelVillage` |
| A mine's hill, as a mesh (then import: `ONLY=['SM_MineMound']`) | `Blender -b --factory-startup --python Tools/blender/assets/mine_mound.py -- --no-render` | `SM_MineMound` |
| Flatlands plan + ground | `Blender -b --factory-startup --python Tools/blender/assets/flatlands.py` | `SourceArt/flatlands.json`, `SM_Flat_*` |
| Flatlands level | `python3 Tools/ue_py.py Tools/ue/build_flatlands.py` | `/Game/Maps/L_Flatlands` |
| Town: ground, water, plan | `Blender -b --factory-startup --python Tools/blender/assets/town_terrain.py -- --no-render` | `SM_TownGround_*`, `SM_TownWater`, `SM_TownSea`, `SourceArt/town.json` |
| Town: its own assets | `Blender -b --factory-startup --python Tools/blender/assets/windmill.py` (and `dock.py`, `hay_cart.py`) | `SM_Windmill`, `SM_Windmill_Sails`, `SM_Dock`, `SM_Boat`, `SM_HayCart` |
| Town level (after importing those meshes) | `python3 Tools/ue_py.py Tools/ue/build_town.py` | `/Game/Maps/L_Town` |
| Town, all of the above but its own assets | `sh Tools/town_rebuild.sh` (`layout`: only the plan changed) | |
| Realm: ground, water, sea, backdrop, far woods, barriers, plan | `Blender -b --factory-startup --python Tools/blender/assets/realm_terrain.py -- --no-render` | `SM_RealmGround_*`, `SM_RealmWater`, `SM_RealmSea`, `SM_RealmBackdrop`, `SM_RealmWoods`, `SM_RealmBarrier`, `SourceArt/realm.json` |
| Tall trees: their second level of detail | `sh Tools/realm_rebuild.sh trees` (`assets/tree_lods.py`, import, `Tools/ue/tree_lods.py`; again after importing the trees again) | `SM_Tree2_*_L1`, LOD 1 of `SM_Tree2_*` |
| Units' and buildings' far levels of detail | `Blender -b --factory-startup --python Tools/blender/assets/voxel_lods.py`, then `python3 Tools/ue_py.py Tools/ue/voxel_lods.py 900` (again after importing a building again; `import_king.py` does it for its parts) | LOD 1 / 2 of `SM_KingB_*`, `SM_<Troop>_*`, LOD 1 of `SM_Castle`, `SM_BarracksYard`, ... |
| Realm level (after importing those meshes) | `python3 Tools/ue_py.py Tools/ue/build_realm.py` | `/Game/Maps/L_Realm` |
| Realm, all of the above | `sh Tools/realm_rebuild.sh` (`layout`: only the plan changed) | |
| Highlands: ground, water, sea, backdrop, far woods, barriers, plan | `Blender -b --factory-startup --python Tools/blender/assets/highland_terrain.py -- --no-render` (`--only backdrop,sea` for some of them) | `SM_HighlandGround_*`, `SM_HighlandWater`, `SM_HighlandSea`, `SM_HighlandBackdrop`, `SM_HighlandWoods`, `SM_HighlandBarrier`, `SourceArt/highland.json` |
| Highlands, everything (import and level too) | `sh Tools/highland_rebuild.sh` (`layout`: only the plan changed; `blender`: no editor) | `/Game/Maps/L_Highlands` |
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
  cut-away), `UVLFootDust` (the dust of his running feet), `AVLGameMode` (console commands `vl.*`), `AVLHUD` (the
  whole interface: the main game's HUD and menus, see *The interface*), `AVLAmbience` (cube motes and chimney
  smoke), `UVLGrid` (where units can walk, and routes), `UVLCommand` (selection, platoons, formations, orders, the
  watch tower's garrison).

## The realm (`L_Realm`): the battle map

After `References/Remake/battlefield.png`, at twice its size each way: 416 m square, the same buildings twice as far apart. `Tools/blender/realm_layout.py` is the plan (built on
`town_layout.py`), `realm_cam.py` its postcard camera, `assets/realm_terrain.py` the meshes, `Tools/ue/build_realm.py`
the level. `../Tools/.venv/bin/python Tools/blender/realm_layout.py --debug` draws the plan from above
(`Saved/realm_plan.png`: hazard edges in red) and prints the balance table.

- **South-west**: the player's town on the plain: the castle and its plaza, the dock under the west cliff. Nothing
  else stands at the start but its mine and the mine's tower: no farm, no cottages, no second mine, no barracks and no
  archery range on either side: Builders put them up in the game, and the ground round the castle is open, level
  meadow for them. **North-west**: the mountain: the player's one gold mine is set into the mountain's foot at the
  north end of the west terrace (136 m from the castle's door), its watch tower on a mound (3 m up) 19 m from the
  mine's mouth, beside the last stretch of the mine road; a neutral mine in the mountain's east face.
- **Middle**: the river from the highland in the north to the sea in the south-east: the upper reach, a fall into the
  gorge (water 2.25 m under the banks), the divider island that splits it into two channels, two footbridges over the
  island (the only crossing), a second fall into the lower gorge (4 m down), a third into the sea.
- **North-east**: the enemy's base on a plateau one metre up: the same, laid out differently (the castle faces west,
  its mine set into the east ridge to the south-east, 131 m from its door, the tower on a mound beside that mine, as
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
- **Beyond the edge** (`SM_RealmBackdrop`, 2 m voxels, no collision): wooded slopes and snowy mountains to the north
  and the east, rock stacks out at sea. Nobody gets there: the map's edge has the usual hidden walls.
- **Barriers** (`SM_RealmBarrier`, tag `Barrier`): hidden walls half a metre thick on the edge of the plan's hazard
  map: both banks of the whole river and the tops of the falls, the island's two rocky points, the rim of the cliff
  over the sea all along the west and south coasts, the sea round the dock's planks. They block pawns only (the path
  grid's capsule test sees them; clicks, arrows and the camera do not). The bridges and the dock are open.
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
  on the plan; they are in `realm.json` under `balance` (player / enemy: bridge 122.8 / 137.5, own mine 136.2 / 130.6,
  tower 136.0 / 130.2, mine to the bridge 156.3 / 176.6). Move a building in `BUILD` and run the script with `--balance`
  to see them again.
- **Ground to build on**: `MEADOWS0` / `MEADOWS1` in `realm_layout.py` are the flat, open meadows round each side's
  buildings (about 14 000 m2 a side); the forest between them can be cleared. `balance()` also measures this
  (`realm.json`, `balance.buildable_m2`: level ground a side can walk to and is nearer to than its foe, less roads,
  buildings, plots: total / meadow / open / wooded).
- **The forest** (`AVLForest`, `VLForest.*`; the level's actor `Forest`): every tree and all the undergrowth are
  instances of one hierarchical instanced component per mesh, not an actor each (12 000 instances in 23 components).
  Budget: `TREES` in `realm_layout.py` (8 A, 8 B, 110 C, 1301 D). The tall trees have a second level of detail of
  half-metre blocks, a tenth of the faces (`assets/tree_lods.py`: A 101k -> 8k faces, D 10k -> 0.9k), which the engine
  draws from about 46 m (D) to 75 m (A) away; grass and flowers are not drawn beyond 400 / 440 m (`build_realm.CULL`; it was 230 / 260 m,
  and they went as soon as the overview pulled back a little: it is 190 m from what it looks at halfway out, and the top of the view is
  further), the bushes always are. To pay for that the small plants have a cheap far version, an eighth of the triangles, from 110 m
  (grass), 120 m (flowers), 170 m (bushes): `Tools/ue/plant_lods.py` (in `realm_rebuild.sh trees`; again after importing them again). The
  farms' wheat, sheep and vegetable beds are single actors with no cull distance, here and in `L_Town` / `L_Flatlands`: drawn at any zoom. Where nobody can go
  (the mountain, the highland, the ridge) there are no tree meshes: `SM_RealmWoods` is one mesh of 1 m block trees.
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
`Tools/highland_rebuild.sh`, `Tools/highland_test.py`. In the New Game menu as "Highlands" (map 4 of `AVLHUD`;
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
  1426 trees (A 8, B 8, C 110, D 1300; the realm has about as many on 0.6 of the ground), 11 440 plants.
- **Roads**: castle to plaza, to the Crown's bridge, to the mine (and the tower's steps), up the bluff, to the dock; dirt tracks through the pass to the neutral mine and to the two far bridges.
- **Barriers** (`SM_HighlandBarrier`, 5003 m of wall): the realm's rule (sea, cliff rim, river banks) and one more: the
  rim of every drop where people walk (`rim` in `heights()`: ground with something more than 1.5 m lower within a
  metre, roads and steps left open): the bluffs, the landings, the mounds, the Crown. A drop of 1.5 m or less (the top
  of a stair's cutting) has none.
- **Balance** (`highland_layout.py --balance`, metres walked from the castle's door, player / enemy): the Crown's
  bridge 122.7 / 121.0, its top 147.0 / 145.6, its mines 173.3, 172.0 / 171.0, 171.9, own mine 94.4 / 91.1,
  bluff top 89.2 / 89.9, tower 101.4 / 100.8, dock 133.4 / 137.7, neutral mine
  on its own bank 245.7 / 239.8, on the far bank 329.3 / 325.6, near bridge 131.1 / 131.3, far bridge 322.0 / 319.8,
  castle to castle 342.7; own mine to the Crown's bridge 212.2 / 212.1. Ground to build on (m2): total 50 667 /
  50 630, of it open meadow 33 313 / 31 887, the bluff's top 6260 / 6221, its half of the Crown 2734 / 2840 (the
  realm: about 14 000 of meadow a side).
- **Tests** (`Tools/highland_test.py`). With a match running (`vl.StartMatch 0` first, or the king does not move):
  `routes` (28 found by the path grid, as long as the plan says) and `barriers` (25 edges he runs at and stops short
  of, 4 on the dock, 8 crossings: the four bridges, the Crown's stair, the bluff's two flights, the dock). Without a
  match (in one the enemy fights the test's troops and its Builders fell trees): `trees` (the count, none against a
  building, clearing) and `march` (over the Crown both ways, 340 m in 52 s at a run; an archer up the tower). A match
  starts there as a battle (12 buildings, 6 a side).
- **Cost**: ground 3.74 M faces in 398 tiles of 27 m (the realm 1.93 M), water 0.28 M, backdrop 0.21 M; the path grid
  1080 x 1080 cells, sampled in 2.4 s. PIE, a match running, measured one after the other in one editor session:
  overview over the home at its usual zoom 40 to 42 fps (the realm 37), over the middle 31 to 39 (33), pulled all the
  way back 36 to 38 (33), as the king 36 to 44 (37): the same as the realm within what the measure wanders. (That session gave the realm
  less than the 50 fps noted above.)

## The battle: teams, combat, economy, the enemy, the menus

The main game's rules (`../Source/SovereignRealms`, now deprecated), reimplemented on this project's units:
`UVLBattle` (`VLBattle.*`: teams, health and damage, buildings, economy, training, upgrades, towers, the match),
`FVLCommander` (`VLEnemyAI.*`: the enemy commander), the combat components, and `AVLHUD` (`VLHUD.*`: the menus and the
in-game HUD). Every number is the main game's (`SRFeelSettings`); per-hit damage is scaled so damage per second is the
main game's, the voxel troops keeping their own swing (1.25 s) and shot (2.4 s) rhythm.

- **The match.** The game opens on the title screen (New Game, How to Play, Settings, Quit). New Game: the map (**The Realm**, the
  battle; Town, Flatlands, Village are sandboxes) and the enemy's difficulty (Easy / Normal / Hard); Start opens the
  map with `?Match=1?Difficulty=N`. Each side starts with 400 gold, 300 food, its castle and whatever else the map places
  (on the two battle maps: one gold mine and the watch tower beside it; **no farm**, **no barracks and no archery range**: the
  Builder raises them, and the enemy's commander lays a farm first, then the trainers), 3 swordsmen and 2 archers in front of its
  castle by its `TeamStart:<team>` (the player's are platoon 1; King David stands at the PlayerStart), and **1 Builder**
  beside them. **The side whose castle falls loses**: the victory
  or defeat screen comes 1.6 s later (time, map, difficulty, troops recruited / lost, enemies slain, buildings lost /
  razed; Play Again, Main Menu, Keep Watching). Esc pauses (Resume, Restart, New Game, Controls, Settings, Quit to Main
  Menu, Quit Game; those that end something ask first). A map with no enemy castle is a sandbox: the economy runs, no commander.
- **Teams.** `AVLKing::Team` (0 the player, 1 the enemy); buildings by their tag `Team:0|1|Neutral` (a game building
  without one is the player's). Health bars on hurt or selected units and on damaged buildings (the ring of the side's
  colour under every unit is off by default, `vl.TeamRings 1` brings it back). The player selects, commands and takes control of only their own units.
- **Troops.** Swordsman (the Shieldbearer): 280 health, 29 a swing (split over its blows), 100 food, 9 s at the
  Barracks. Archer: 125 health, 40 an arrow (x0.35 against buildings: 14; raised from the main game's 29, +38%, so
  archers are worth fielding: 17 damage a second against a swordsman's 23), 85 food, 8 s at the Archery Range, bow
  range 31 m. King David: 600 health, 45 a swing, no housing, his own pace (5.2 m/s on the march, 9.5 at a run; a
  troop 4.2 / 7.6); **if he falls he rises again at his castle 20 s later** (not if it has fallen).
  Troops not on an order go for any foe in their sight (16.9 m, archers 19.5 m: the main game's 13 / 15 m plus 30%; on
  a lookout 55 m), troops before
  buildings, and answer whoever strikes them; friends within 6.5 m (13 m of a building) come to help. Stance per
  platoon or unit (G): Aggressive (chases, lets go at twice its sight unless struck), Defensive (no further than
  13 m from its post, then back), Hold ground (only what is in reach). A plain move ignores foes; a left or right
  click on a foe's unit or building attacks it. Swordsmen run a moving foe down (a fresh route every 0.6 s, given up
  after a dozen that get no closer) and go for a building's walls; archers lead a moving foe and walk into range
  again when it leaves it. Arrows strike the bodies of foes they pass (never friends). The dead topple and are gone.
- **The Spy** (the main game's Scout, `ESRUnitType::Scout`; `VLRules::Troop("Spy")`, `UVLSpy`): 90 health, 8 a blow
  (x0.2 against buildings), 350 gold + 200 food, 12 s at the **Castle**, 1 housing. Three rules, checked when it is
  queued (`UVLBattle::SpyRefusal`): the castle at **level 3**, **one at a time** (alive or in training), and a
  **5-minute wait** between two, counted from the moment the last was queued and paid for; no batches. The castle's
  panel has its recruit button (the Scout's: "Castle level 3" / "In training" / "In the field · 3:12" / "Ready in
  3:12"), the upgrade button one slot to its left. **Very fast**: 8.75 m/s on the march and 11 m/s at a run (a
  swordsman 4.2 / 7.6), a 2.6 m stride. **Picks no fights**: no sight of its own to go for foes, it answers no calls
  for help and joins no recruit platoon; played, a left click is a light blow. **Hard to notice** (`FTroop::Notice`
  0.45): enemy troops go for it only within 45% of their sight (a swordsman at 7.6 m instead of 16.9 m, an archer at
  8.8 m) and let it go at 45% of their usual chase; towers and the castle's walls shoot it only inside 45% of their
  reach; the enemy commander sees it (its memory, its "foes at my buildings" alarm) only at 45% of its 26 m. A direct
  order is not affected. **Sees far**: 33.8 m (`FTroop::Sight`, the main game's 26 m plus 30%: the dashed ring when selected), and the spyglass (see
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
  every 6 s; levels 16 / 23), Watch Tower 1800 (shoots 50 every 1.2 s to 24 m; levels 85 / 120, 0.95 / 0.8 s, 27 / 30 m;
  archers on its lookout shoot too), Granary / Treasury if a map has them (+400 / 900 / 1600 storage). The selected
  building's panel (bottom middle): health, what it does, the recruit button (Shift 5, Ctrl 10: each paid for and
  housed when queued, no queue limit), the upgrade button (U), its lookout. Right click with a barracks / range selected: its rally point;
  Ctrl+1..6: its recruits join that platoon. A fallen building sinks into the ground (its queue lost; a storehouse's
  stock beyond what is left is lost).
- **The enemy commander** (`FVLCommander`; the main game's `SRAISubsystem` grown into a commander of three layers over
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
  4. **Economy and building** (`ManageBuilding`, `TryBuild`): the main game's build order (barracks and range first,
     then farm, tower, mine, farm) and wants, one site per Builder, driven by the strategy: a **tower by a farm or mine
     that was raided**, a tower when attacked early and often, a **second barracks / range when its army is behind**
     (and a longer training queue), **mines on the safest free veins** (near, rich, the Crown's while it holds it; none
     where the foe is stronger or under its towers), **no site where the foe is clearly stronger**; trains toward a
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
| Micro: every, focus fire, step back, pull out below | none | 1 s, archers, yes, 22% | 0.5 s, all, yes, 30% |

  The knobs are `FVLAIProfile` (`VLEnemyAI.h`, one comment each; set per difficulty in `FVLAIProfile::For`):
  `StrategyEvery`, `ReactionDelay`, `Commitment`, `ContestWeight`, `ExpandWeight`, `PatrolMax` / `PatrolShare` /
  `PatrolRadius`, `GuardMax` / `GuardShare`, `BuilderGuards`, `PicketFrom`, `MaxRaids`, `RaidSize`, `bFlank`,
  `InterceptOdds` / `InterceptRange`, `MicroEvery`, `FocusFire`, `bKite`, `PullBack`, `bAvoidTowers`, and the main
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
- **HUD**: see *The interface* below.
- **Console** (`Tools/pie.py run "..."`): `vl.StartMatch [0|1|2]`, `vl.Restart [d]`, `vl.Menu main|new|pause|settings|controls|end|0`,
  `vl.UIClick U V [right]` (a click on the interface at that point of the view), `vl.HUD` (the buttons drawn, by id),
  `vl.Battle` (both sides, every building), `vl.Give gold|food N [enemy]`, `vl.TrainAt <building> [enemy] [n]`,
  `vl.Upgrade <building> [enemy]`, `vl.Damage <building> [enemy] N`, `vl.Kill <unit> | castle enemy|player`,
  `vl.SpawnTeam Swordsman|Archer 0|1 X Y [n]`, `vl.SetTeam <building> 0|1|neutral`, `vl.TestBase [DX DY]` (an enemy
  base on any map: copies of its buildings, mirrored), `vl.AIvsAI 1`, `vl.BattleLog 1`. `vl.Order`, `vl.SelectUnits`,
  `vl.Units` and the like take `enemy` for the enemy's units; the group words mean the player's own.
- **Not ported** (the user's to design): the Medic, the Catapult,
  the Horseman (no voxel model yet); also deferred: fog of war, saved games. (Guard, patrol, march together and the
  other orders are back: *Standing orders*, `Docs/PORT_AUDIT.md`.)

## The interface

The main game's interface (`../Source/SovereignRealms/Player/SRHUD*.cpp`, `../Docs/UI.md`) ported one to one: the same
layout, panels, colours, fonts, icons, wording and behaviour, drawn immediate-mode on the HUD canvas by `AVLHUD` (no
widgets), on this project's battle (`UVLBattle`), orders (`UVLCommand`) and units (`AVLKing`).

| What | Where |
| --- | --- |
| Frame, input, primitives (panel, text, icon, button, slider, tooltip), world-space feedback | `Source/VoxelLab/VLHUD.{h,cpp}` |
| In-game HUD | `Source/VoxelLab/VLHUDGame.cpp` |
| Menus and shared screens | `Source/VoxelLab/VLHUDMenus.cpp` |
| Palette, world colours, button ids | `Source/VoxelLab/VLHUDStyle.h` |
| Icon atlas and title lettering (the main game's) | `SourceArt/UI/*.png` -> `/Game/Voxel/UI` (`python3 Tools/ue_py.py Tools/ue/import_ui.py`) |
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
  Builders alive/limit and +in training; the Spy 0/1, the wait before the next, greyed below castle level 3; a click
  selects them, a double click also looks at them), the clock, the enemy ("Enemy ready in 3:12" dim, amber under a
  minute; "Enemy watching"; "Enemy attacking!" pulsing). Tooltips on each. Top right: Controls (F1) and Pause.
- **Build button and menu** (left of the selection panel, B): see *Building*. Sites show a hammer bar over them (red
  "needs a Builder" while nobody works at one), repairs a green one.
- **Alerts**: plates with an icon and an accent per kind (attack / lost red, done green, housing amber, info gold);
  in over 150 ms, out over the last second of six. Those with a place ping the minimap.
- **Minimap** (bottom left): a picture of the map from straight above (its unlit colours, captured once when the overview
  first shows, units hidden), your buildings blue and the enemy's red (castles larger with a gold core), contested mines gold, troops
  as dots (selected white, King David with a gold rim), alert pings, and the camera's view of the ground. +X is up.
  Left click (drag): look there. Right click: the selection goes there (a barracks / range selected: its rally point).
- **Selection panel** (bottom middle, with a selection): troops (portrait and count per kind, health, how many are
  fighting, the circles' key, the standing order it is on ("Patrolling", "Guarding the Castle", ...), and the main
  game's command card: Attack-move [A], Attack ground [A] with archers, Stop [S], Hold [H], Patrol [P], Guard [V],
  Roam [O] with a Spy, Stance [G], Formation [F; right click too], March together [M] (Together / Free), Disband [Del]
  for a platoon, Dismiss [K] (asks first: Sure?), Control [Enter] for one unit; the row packs tighter when long); an enemy's units read-only; a building (icon,
  name, side, level of N, health and "badly damaged" below half, what it does) with its buttons on the right: the
  **upgrade button** (next level, gold / food price in red when short, what it brings in a few words and in full in its
  tooltip, a progress meter and time while it is raised, "Castle level N" when a storehouse's level waits for the
  castle; U), a barracks' / range's **recruit button** (portrait, price, "Trains in 9 s" / "Housing full"; Shift 5,
  Ctrl 10; flashes gold or red) with the queue, its progress and the **Joins** chips (none / 1-6) on the left, and the
  watch tower's **Lookout** (who mans it; click: send them out). Farms and mines show their payout meter, storehouses
  the kingdom's stores, the castle its archers.
- **Platoon panel** (bottom right): six slots; a formed platoon shows its number in its colour, its kind, counts,
  health, a burning edge while it fights, and buttons for formation, stance and disband; click selects, twice within
  0.35 s also looks at it; empty slots read "Ctrl+N to form". The header folds it away (remembered).
- **Castle card**: raising the castle a level shows what the level brings (14 s, or **Onward**).
- **Portraits**: every troop portrait (selection panel, queue, recruit and lookout buttons, training bars, platoon rows,
  the hero's bar) is a render of the voxel character's head and shoulders; an enemy's is reddened.
- **World**: no rings under units' feet (the user's call: the platoon diamond over their heads and the health bars
  mark them; the side-coloured ring under every unit is behind `vl.TeamRings 1`, off by default; the main game's green
  ring under the selected and the pale one under the pointer are left out); the selected
  building's footprint; health bars over units of both sides in
  every view: always in the red (under 34 %), else for 3 s after a hit or a heal and fading over 0.8 s, and always while
  selected; on buildings lately hurt or selected and damaged; training and upgrade bars with icons over buildings at work; "+N" payouts with the coin or grain;
  numbered platoon tags; dashed blue pathways and rally lines, a patrol's loop in orange and an attack-move's way in
  red; while an order is armed, its hint under the top bar and a crosshair pointer; the selected troops' sight (dashed blue) and bow range
  (solid orange) and a tower's / the castle's reach; team-coloured pips over troops zoomed far out; the order markers;
  the green selection box.
- **This game's own**: the mode box top left (HERO / OVERVIEW, who is played, King David's fall), the hero view's
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
Enter: New Game). New Game: the map (The Realm, Town, Flatlands, Village) and Easy / Normal / Hard, BEGIN. Pause (Esc):
RESUME, RESTART, NEW GAME (another map), CONTROLS, SETTINGS, QUIT TO MAIN MENU, QUIT GAME; restart and the quits ask
first (CANCEL / yes). Settings: master volume, effects, music (sliders), interface scale (applied when the slider is let
go), Graphics (Quality High / Medium / Low, Render scale 100-50 %), frame-rate limit, camera angle (V), look speed (L),
invert look (I); saved in `GameUserSettings.ini` (`[VoxelLab.Video] Quality`, `RenderScale`). See *Performance* below. Controls
(F1, or HOW TO PLAY): every key, two columns. Victory / defeat: the match's numbers, PLAY AGAIN, MAIN MENU, KEEP WATCHING.

**Input.** `AVLKing::OverviewCommands` hands every left press (and a right click let go without dragging) to
`AVLHUD::OnMousePress` first: over a panel drawn last frame (or with a menu or the controls overlay up) it is queued and
answered by the `Button()` under it while the HUD draws, and never reaches the world. `vl.UIClick U V [right]` takes the
same path; `vl.HUD` lists the buttons drawn last frame with their ids (`VLHUDStyle.h`, `VLId`).

**Changed from the main game** (layout): the mode box top left and the hero view's help line and health bar are new;
the top bar's chips show the hero as well as the Builders and the Spy (no builders' list), and the enemy's status after
the clock; the build menu's tabs are clicked (no Tab key); the castle's panel is wider (Builder, Spy, upgrade); the recruit buttons have no hotkey cap; the platoon rows have three small buttons
(no recruit flag); the watch tower's panel has a Lookout button; the castle's panel has the Spy's recruit button; the
pause menu has New Game and Quit Game instead of Save / Load; the victory screen adds Keep Watching; unit portraits are
the voxel characters, not the pixel icons.

**Not ported** (their features are not in this game; their buttons are left out, not shown dead): the castle's building
zone; the Medic, the Rider and the Catapult (recruit buttons, portraits); the command card's Build and Repair buttons
(B and X do it, and the Build button), and the platoon panel's "recruits join here" flag (here each barracks / range
has its own Joins chips); fog of war on the minimap; saved games (Continue, Load, Save, the save list); the title
screen's film; the recruit buttons' Q / E keys (Q / E turn the view here); the sandbox match of the main game's New Game.

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

### Standing orders

The main game's Stop, Hold, Patrol, Guard, Roam, attack-move, March together and Dismiss (`SRPlayerController`,
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
| `OrderGuard(Units, Ward)`, `CanBeGuarded(Ward, Team)` | posts in rings round a building (170 cm outside its walls), a Builder or King David (230 cm), 120 cm between rings; foes within `GuardLeash` 18 m of the ward (an archer: her bow's reach), 1.8 times that for one that struck the guard or the ward; a struck ward calls its guards in; the order ends when the ward falls. Builders do not guard; troops cannot be guarded |
| `OrderRoam(Units)` | the Spies wander 20-70 m at a time, to ground not visited lately, clear of foes' towers and castles; a leg over 40 s is dropped; struck: to the castle's door at a run, with an alert |
| `Dismiss(Units)` | troops gone for good, quietly, not counted as lost (never King David) |
| `MarchTogether(Units, Shape)`, `ToggleMarchTogether()` | in a formation the slowest always sets the pace (`AVLKing::PaceCap`); Loose: per platoon / loose-selection setting, on by default; fights are at full speed |
| `GuardWardOf`, `GetGuards`, `IsRoaming`, `GetRoute`, `DescribeOrders`, `ClearStanding` | what a unit is on; ends it |

Console (the four of 2026-11-21's second pass): `vl.Leaders` (each platoon's leader and who follows whom),
`vl.Follow <who> <unit name | king>`, `vl.HeroAim <unit name> | X Y [Z] [seconds]` (the hero view's crosshair taken to
be there), `vl.HeroOrder [run] [queue] | click [add] | select [add]` (the hero view's right click / plain left click /
Alt + click at the crosshair), `vl.Queue <who> X Y | work <building name> | clear | log`, `vl.Build ... queue`.

Console: `vl.Stop [who]`, `vl.Hold [who]`, `vl.Patrol <who> X Y [X Y ...] [run]`, `vl.AttackMove <who> X Y [queue]
[run]`, `vl.Guard <who> <building name | unit name>`, `vl.Roam [who]`, `vl.Dismiss [who]`, `vl.March`, `vl.Orders`
(every unit's standing order, speed and pace). The audit of what the main game had and where each is now:
`Docs/PORT_AUDIT.md`.

## King David

`Tools/blender/assets/king_b.py` builds him as a tree of rigid parts (`SM_KingB.json` lists each part's pivot and
parent): pelvis (`Body`) > `Chest` > `Head`, upper arms > forearms (> `HandR`, the sword hand, turning at the wrist),
thighs > shins, the cape's yoke > 5 columns of 4 hinged panels (`Cape<col><row>`), `Sword`, `Sheath`. (The spy,
`troop_spy.py`, adds `Spyglass` on `HandR` and the hood's tail `HoodA` > `HoodB` on `Head`, posed by `UVLSpy`; its
lantern is on the material slot `glow` and the tail on `sway`, which `import_king.py` gives an emissive instance and
an instance of the wind material `M_VoxSway`, the vertex alpha being how far a corner moves.) The sword is
modelled in the closed fist (grip through the fist, guard beyond the thumb, pommel behind) and never turns in it: the
blade is aimed with the arm and the wrist. `--face K|A|B|C` picks the face (K is the approved one), `--views
face,grip,head,hero,sides,...` the preview renders, `--search-sheath` re-runs the scabbard search (it is pinned).

**His pace** (`VLRules::Troop("King")`, applied in `AVLKing::BeginPlay`): 520 cm/s walking and 950 running, against a
troop's 420 / 760. Half of the gain is a longer stride and half a quicker step (`StrideScale` = sqrt(520 / 420) =
1.11: the feet reach 11% further, the pelvis drops to let the legs reach them, and the cadence is 11% quicker), so a
planted foot stays still on the ground; his acceleration, braking and the camera's lag are scaled by 950 / 760 so he
gets going, stops and is trailed as before. With troops in a formation he keeps their pace (March together).

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
| `vl.Look X Y [Zoom] [Yaw]`, `vl.Map town\|realm\|flatlands\|village\|highlands` | the overview camera over a point; open a map |
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
- **Music** is not loaded at all while its setting is 0; above 0 one song at a time is loaded in the background.
- **Packaging**: `sh Tools/package.sh` builds Shipping (no console, no log, no command inbox, symbols stripped);
  `sh Tools/package.sh Development` for tests. Only Metal SM6 shaders are cooked (`Config/Mac/MacEngine.ini`); the NNE
  plugins are off; the old `SM_King_*`, `SM_KingA_*`, `SM_KingB_*` (in Meshes), `SM_KingT_*` meshes are never cooked.
- **Switches** for comparing old and new paths in one session (all default to the new path):
  `vl.Opt.RigBatch`, `vl.Opt.RigLOD`, `vl.Opt.RigPixelError`, `vl.Opt.RigFarDist`, `vl.Opt.RigCullMargin`,
  `vl.Opt.UnitDepth`, `vl.Opt.UnitDepthFar`, `vl.Opt.UnitGI`, `vl.RigStats 1`, `vl.RigCheck`; `vl.Opt.Registry`,
  `vl.Opt.Hud`, `vl.Opt.Ambience`, `vl.Opt.RegistryCheck 1`, `vl.Opt.Timing`; `vl.Opt.FarFog`, `vl.Opt.MinimapFast`;
  `vl.Opt.ParallelGrid`, `vl.Opt.FastRegions`, `vl.Opt.Placement`, `vl.Opt.GridChecksum 1`, `vl.PlacementLog`,
  `vl.PlacementBench <kind> X Y [n]`, `vl.Music [0..1]`.
