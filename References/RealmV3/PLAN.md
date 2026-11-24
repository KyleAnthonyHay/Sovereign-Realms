# Realm v3 — the map designer's plan (the owner's brief, 2026-11-23)

A new battlefield, **Realm v3** (level `L_RealmV3`). `L_Realm` and `L_RealmV2` stay as they are.

## References
- `concept_plan.png` sets the layout: the two starts, the one connection, the central contention zone, the six mines.
- `concept_threequarter.png` sets the look: plateaus with cliffs all round, long sharp ridges, forest to the shore.

## The brief
- An island. Two starts: **A north-west** (the player) against **B south-east** (the enemy), each castle on a raised
  plateau with cliffs all round.
- **One connection only.** Each plateau has one base ramp, which leads to a single road through a central mountain
  pass. No bridges, no coastal bypass; the forests along the coast and the ridges are not a way round.
- **Central contention zone:** a basin enclosed by impassable ridges, with two neutral mines (Neutral 1 on its
  north-east side, Neutral 2 on its south-west side, set into the rock) and shared ground to build on; the lane
  through it stays clear.
- **Per base:** two protected home mines on the plateau, either side of the castle. Six mines in all.
- **Balance rule:** the same plateau size, ramp width and travel time to the centre for both sides.
- The owner's verdict on Realm v2: *"not enough forest and too much space"*. So: forest fills everything that is not
  plateau, basin, road or cliff, right to the shore; and the island is sized to the gameplay and no more.
- The frame time stays in line with Realm v2's.

## The owner's feedback on the first build (2026-11-23, the same day), and what changed
1. **The base ramps looked like stairs** ("it should feel like the terrain is naturally going up, not just a bare
   pathway"). They were cuts 12 m wide and 47 m long (1 in 4.7) with terraced banks. Now each is a **spur of the
   hillside**: 18 m of walking ground (24 m where it meets the plateau and the pass), 73 m long for its 10 m (1 in
   7.3, eased at both ends), its shoulders falling 1 in 2 to the forest's floor and rising 1 in 2 to the plateau's
   top, so the cliff tapers into it. And it is **smooth**: the voxel ground can only rise in quarter-block shelves,
   which is what read as steps, so the stepping is taken out at the source: the spur and its shoulders are a sloping
   sheet (`SM_RealmV3Ramps`: the ground's own top faces, the same texture and tint, on the true slope) with the
   voxels just under it. Grass, a worn and broken track up the middle, rocks and bushes along it, forest to its edges.
2. **Bigger, deeper plateaus**: 120 x 108 m (they were 112 x 80), 9,090 m² of level top (6,400), 7,185 m² free to
   build on (4,690), 92 m deep from the ramp's top to the back rim (70).
3. **A port for each side**, Realm v2's set, on the far side of its plateau from the middle: the player's on the
   west coast, the enemy's on the east. A stone stair comes down a cleft in the sea cliff to the quay; it joins
   nothing but its own plateau.
4. **The sea**: depth is the shared water material's to fake (the boat's agent owns it; this map uses the same `water`
   slot as every other, so it takes whatever that material becomes). Nothing is sculpted for it. The sea round the
   island and at both quays is open: the coast's rocks stop 3 m out, the six islets are 4 to 5 m rocks 16 to 20 m
   off the cliffs.
To make room the world grew from 384 m to 416 m square; the island is still a third of Realm v2's land.

## The owner's second round (2026-11-23, the evening), and what changed
1. **"Make the rock walls less tall, they are blocking my view."** The ridges' crests were 25 to 50 m over the basin
   and the spines 66 m at the corners; now the crests stand **14 to 22.5 m** over the basin's floor (18 to 26.5 m
   over the plan's zero), dipping to a saddle of 8 to 12 m by each pass, and the highest point of the island is
   **29 m** (it was 66). The home mines' crags were up to 15 m over the plateau and are now up to 9 m (23 m). Still
   impassable: the faces stand straight from the basin's edge and the forest (a wall of 3 m and more), and the hidden
   walls and lid are unchanged. The rock no longer reads as terraces: it was cut into shelves of 1 to 6 m at the same
   levels all along a face (contour lines); now it stands in columns 2 and 4.5 m across, each pushed up or down a
   metre or so, cut into steps of 0.5 to 2 m that begin at a different height in every 3 m block. The same voxels,
   no new meshes or materials; the ground is 6.70 M triangles at LOD 0 (2.63 / 2.32 M at LODs 1 and 2).
2. **"Make the platform area twice as big."** Each plateau is now **164 x 148 m** (it was 120 x 108), squarer in the
   corners: **19,350 m² of level top** (9,090) and **16,981 m² free to build on** (7,185), 132 m deep from the ramp's
   top to the back rim. The castle, its two home mines in their crags, the towers, the plaza, the rally point and the
   port moved out with it (the table below). The ramp, the pass and the basin are where they were. To make room the
   world grew from 416 m to **512 m square** (the coast about 219 m from the middle, was 182): the island only as big
   as the two plateaus need, the forest filling the rest as before.

## The design in one paragraph
The island is **point-symmetric about its middle**: every place (x, y) of the player's side is (-x, -y) of the
enemy's, turned half round. That is true of the plan's shapes, of every noise the ground is made from (the plan's
`noise2`, `shash` and `warp` are symmetric by construction; the plan counts the cells that differ from their twin: 0),
and of every tree, rock and bush. The balance rule is therefore kept by construction, and measured as well. Only
**48,700 m² of the island's 183,400 m² can be walked on**: the two plateaus with their ports, the two ramps, the two
passes and the basin. Everything else is forest (99,800 m²), ridge (30,600 m²) and cliff, behind hidden walls: the
forest is scenery, thick, and no way round anything.

## Scale (from the real sizes)
A unit is about 1.8 m; the castle 14 x 11 m, a mine 16 x 11 m, a watch tower 11 x 13 m, a barracks yard 19 x 18 m, a
farmstead 23 x 19 m, an archery hall 20 x 14 m, a granary 13 x 10 m, a treasury 13 x 9 m. A small tree (`SM_Tree2_D`)
is 8 m high with a crown 4.4 to 5 m across.

| | Realm v2 | Realm v3 |
|---|---|---|
| The world | 640 m square | **512 m square** |
| The land | about 340,000 m² | **183,400 m²** (a little over half) |
| Ground a unit can reach | most of it | **48,700 m²** |
| Trees | 3,621 (about 110 per hectare of land) | **5,722**, 5,678 of them forest: **569 per hectare of forest** |
| Summit | 184 m | 29 m |

- **A plateau**: a rounded table 164 x 148 m, 19,350 m² of level top, 16,981 m² of it free to build on once the
  castle, the two mines in their crags, the two towers, the stair and the roads are counted. A full base: a barracks yard,
  an archery hall, three farmsteads, a granary, a treasury and four or five more, with 4 m lanes between them,
  take about 5,500 m².
- **The basin**: a lens 132 x 60 m, 6,600 m² of floor, 5,130 m² of it free to build on: an expansion either side of
  the lane.
- **Ways**: a base ramp 18 m wide, 73 m long, 10 m of rise; a pass 12 m wide, 27.5 m long, level; a port's stair
  4.5 m wide, 46 m long, 19 m of rise.

## Elevations (metres over the plan's zero; the sea is at -6)
| Place | Level |
|---|---|
| The sea | -6 (its bed -8); the quays and piers -5 |
| The forest's floor | 1 to 4.5, a slow roll in half-block shelves; sea cliffs of 7 to 10 m round the coast |
| The basin, the passes, the ramps' feet | 4 |
| The plateaus | 14 (cliffs of 10 m and more over the forest, 19 m over the quay) |
| The home mines' crags | up to 23 (9 m over the plateau) |
| The ridges | walls of 3 m and more straight from the basin's edge and the forest; crests 14 to 22.5 m over the basin (18 to 26.5) in peaks and saddles, 8 to 12 m over it by the passes; the highest point 29 m |

## Layout (metres; +X east, +Y north; the enemy's twin of every player's place is its negative)
The island's own frame is diagonal: **u** runs north-east, **v** north-west (`u = (x + y) / √2`, `v = (y - x) / √2`).

| What | Player (A, north-west) | Enemy (B, south-east) |
|---|---|---|
| Plateau (centre; 82 x 74 m half sizes) | (-130, 130) | (130, -130) |
| Castle | (-130, 148), facing south | (130, -148), facing north |
| Plaza and banner | (-130, 134) | (130, -134) |
| Home 1 mine, in the west crag (A) | (-187, 150), facing east | (187, -150), facing west |
| Home 2 mine, in the east crag (A) | (-73, 150), facing west | (73, -150), facing east |
| Watch towers | (-168, 100) over the port's stair, (-84, 100) over the ramp's head | (168, -100), (84, -100) |
| The base ramp: head (14 m) to foot (4 m) | (-78, 72) to (-67.4, 3.7) | (78, -72) to (67.4, -3.7) |
| The pass: mouth to the basin | (-67.4, 3.7) to (-47.9, -15.7) | (67.4, -3.7) to (47.9, 15.7) |
| The port: the quay (13 x 40 m) | x -229 to -216, y 102 to 142 (the west coast) | x 216 to 229, y -142 to -102 (the east coast) |
| The port's stair: head (14 m) to quay (-5 m) | (-172, 123) to (-218, 123) | (172, -123) to (218, -123) |
| The pier (the ship moored off its head) | from (-229, 133), running west | from (229, -133), running east |
| The hero and the Builder start | (-130, 138) | (130, -138) |
| Rally point | (-108, 108) | (108, -108) |

| Neutral | Where |
|---|---|
| The basin | a lens about the middle (0, 0): 66 m either way along u, 30 m either way along v |
| The lane | straight across it, from (-47.9, -15.7) to (47.9, 15.7) |
| Neutral 1 (north-east side) | (31.5, 48.5), facing south, its back in the rock of the basin's northern end |
| Neutral 2 (south-west side) | (-31.5, -48.5), facing north |
| Ground to build on | north of the lane about (-2, 25), south of it about (2, -25) |
| The ridges | rock 22 m wide along either side of the basin; beyond its ends the two join into one spine 44 m wide that runs on to the sea cliffs of the north-east and the south-west corner |
| The coast | a rounded square about 219 m from the middle, wobbling; straight at the two ports; six islets off it |

Each side is 61 m nearer one neutral mine than the other (the player Neutral 2, the enemy Neutral 1), and the other
side's nearer mine is the one it must cross the lane for: a natural first expansion each, and a contested second.

## How it answers the brief
- **One connection.** The ridges are one piece of rock from coast to coast, and the two plateaus lie on opposite
  sides of it. The only gaps are the two passes, and each pass opens only onto a base ramp and the basin. The
  plan's own check shuts a pass and looks for a route between the castles: there is none.
- **No coastal bypass, no way through the woods, none by the ports.** The forest stands on ground nobody can walk
  on: the hidden walls (`SM_RealmV3Barrier`) run round each plateau's rim, down both sides of each ramp, each pass
  and each stair, round the quays and the piers, and round the basin; and a hidden lid lies over the ground behind
  them, so the game's path grid has no place to stand in the forest, on the coast or on the ridges at all. A quay
  touches the sea and its own stair, nothing else.
- **Central contention.** The basin is the only ground between the bases; both neutral mines and all the shared
  ground to build on are in it; the lane crosses its middle and is kept clear (a road; nothing stands on it).
- **Protected home mines.** Both are on the plateau, which has cliffs all round, one ramp and one stair to its own port.
- **Balance.** Point symmetry. Measured (the plan, without trees): castle door to the middle of the basin 237.2 m
  for the player and 236.7 m for the enemy; to the other castle 474.0 m both ways; plateau tops 19,350 m² each.
- **Forest.** 5,678 trees on 10 hectares of forest floor: a tree in every 4 m, crowns 4.4 to 5 m across, so
  the canopy is closed from the plateaus' cliffs and the ridges' feet to the sea cliffs. On Realm v2 the trees
  stood about 110 to the hectare.
- **Tighter.** A little over half of Realm v2's land, a seventh of it walkable; the walk from a castle to the middle
  is 237 m (on Realm v2 the ruins were 415 m from the player's castle).

## What each side starts with
As on Realm v2: the castle, its home mines (two here), the watch towers, its port (scenery, as on Realm v2: the
quay, the warehouse, the crane, the arch, the harbour tower, the pier and the ship), the hero and one Builder. No
farm, no cottages. **Towers:** Realm v2 gives each side two; here one stands over the ramp's head and one over the
port's stair, the plateau's two ways in, both on the level ground (the tower rule: never on a drum of rock).

## Standing rules (README)
- No hard edges on open ground: the walkable ground is level (the plateaus, the basin, the passes) or a smooth slope
  (the ramps). The plan counts cells of open ground with a drop of a metre to open ground: 0.
- No coarse LODs at play distances: the trees' and the ground's levels of detail and their switch distances are
  Realm v2's, unchanged.
- The original tree set: `SM_Tree2_A/B/C/D` only (93 % D, 6 % C, some forty giants deep in the wood).
- Mines pre-placed, never built: six, all in rock (`Mounded`).
- Islands big enough to build on: the island is one; the six islets are scenery nobody reaches.

## How it is made (Realm v2's pipeline, copied)
- `Tools/blender/realmv3_layout.py`: the plan (`--debug` draws `Saved/realmv3_plan.png`; `--balance` prints the
  routes). Writes `SourceArt/realmv3.json` and `SourceArt/realmv3_terrain.npz`.
- `Tools/blender/realmv3_cam.py`: the postcard camera. `Tools/blender/assets/realmv3_terrain.py`: the ground tiles
  with their far levels, the ramps' sheet, the sea, the barrier and its lid.
- `Tools/ue/build_realmv3.py`: the level. `Tools/ue/realmv3_lods.py`: the ground's levels of detail.
- `Tools/windows/realmv3_rebuild.ps1` (and `Tools/mac/realmv3_rebuild.sh`): everything, end to end.
- `Tools/realmv3_test.py`: the PIE checks. `Tools/realmv3_shots.py`: the screenshots.
  `Tools/windows/realmv3_perf.ps1` (and `Tools/mac/realmv3_perf.sh`): the frame times at three views.
- The game: map 5 of `AVLHUD` (New Game shows it third, after Realm v2), `vl.Map realmv3`, `realmv3.json` for the
  AI's markers, `MapsToCook`. The overview's furthest zoom (de76f37) takes its distance from the path grid's bounds,
  so it frames this island as it does the others.
