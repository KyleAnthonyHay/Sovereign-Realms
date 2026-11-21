# Visual audit and the natural-world pass (phase 1, 2026-11-19)

What the world looked like after the heightfield rebuild, what this pass changed, how it was measured, and what is
left for phase 2. The standing description of the pipeline and every parameter is `Docs/VISUAL_CONTRACT.md`
("Natural-world pass" there); the outside assets are in `Docs/ASSET_CREDITS.md`.

## Audit: what was weak

| Area | Before | Why it read as flat |
| --- | --- | --- |
| Turf | One 128 px pixel-art tile (5 m) in three variants chosen by the splat map; normal straight up. | No variation above 5 m, no relief under the raking sun: a field was one olive tone with a visible repeat at max zoom-out. |
| Roads, banks | Bare-earth tile wherever the splat's road channel passed a threshold; "mud" at the water was the same tile. | Hard-edged, the same colour everywhere, nothing wet about a bank. |
| Rock | One 128 px tile (a crushed photograph) on every mountainside, laid from above or from the side by the dominant axis, flat normal. | A diamond repeat on every face, no strata, no lip where turf met rock, no moss. |
| Rock props | `M_Prop` with a 64 px tile through UV0. | Boulders did not match the faces they lay under. |
| Water | Opaque, two layers of pixel streaks sliding along **one direction for the whole map** (`Flow` from the layout), three stepped shallow bands from bank distance, a dashed foam line. | One flat teal, no depth, every river drifting the same way (wrong on three of the Four Marches' four rivers), nothing to reflect because the surface normal was flat. |
| Waterfalls | One layer of streaks, a white foot; nothing in the pool, no spray. | A ribbon stuck on a wall. |
| Mist | Two raised copies of the river sheet and level discs under the far mountains and over some pools. | Good over water; nothing in dips or hollows on land; the discs read as discs. |
| Lighting and post | Late-afternoon sun (42 degrees), cool sky fill, volumetric haze past the focus, bloom, a held-back grade (saturation 0.9). | Sound. With a one-tone ground the low saturation made it greyer still. |
| Sky | `SkyAtmosphere` + real-time sky light; cloud shadows from a light function. | The camera never sees the sky, so its only jobs are the fill light and the reflections; both fine. |
| FX | Sprite FX for combat (dust, impact, debris, fire, smoke), birds, deer. | Out of scope here; fire on buildings is phase 2. |

## What changed

### Terrain (`M_Terrain`, `TERRAIN_CODE` in `Tools/build_visual_materials.py`)

The pixel art stays the base and every edge is still decided texel by texel; photographic layers (CC0, Poly Haven)
are laid **on the same 4 cm texel grid** (`SRNat.Q`: the SRPix seam as a coordinate), so they come out as crisp
texels and do not crawl.

- **Turf**: the tile is modulated by a real grass photograph at texel density (41 m before it repeats), an aerial
  photograph at 190 m, and three sizes of value noise (52 m meadows, 13 m patches, 2.3 m tussocks) that push it
  lusher or more parched; straw now creeps into the parched patches and moss over level high ground and damp banks
  as well as where the splat map says. Clover drifts (a deeper, bluer green) carry scattered white, yellow and violet
  flowers (2 x 2 texels). A grass normal map gives the surface relief under the low sun.
- **Roads**: the verge yellows before the earth starts; the earth carries pebble detail and normal, and drifts warmer
  / greyer along its length.
- **Wet banks**: `T_WaterFlow.a` (new, from the generator: 1 at the water's edge to 0 three metres back) darkens the
  ground, lowers its roughness (a wet sheen) and, right at the edge, replaces it texel by texel with mud and leaf litter.
- **Rock**: an aerial photograph of crags from above, strata from the side where the face stands up (by the
  triangle's own lean, because a cliff's vertex normals lean back), a fine grain over both, beds and ledges that
  follow the contours (warped, never ruled), normal maps throughout. Lichen and then moss settle where the rock looks
  at the sky.
- **The broken lip**: above the rock's edge the turf darkens and breaks into scree texel by texel; the generator
  scatters loose stones along every crest (`Dressing.rubble`: 4,383 on the Riverlands, 11,085 on the Four Marches) and
  pebbles on the banks (435 / 1,402). Its own random stream: nothing else on the maps moved.
- **Rock props** (`M_Rock`, new; `MI_Rock_Ruin` for standing stones and dolmens): the same stone from three sides
  with lichen and moss, so a boulder on a mountainside is the mountain's own rock.

### Water (`M_Water`)

Still opaque and lit (Lumen gives it the sky and the banks to reflect; nothing sorts wrong over it; it costs what a
ground pixel costs). Depth is **not** read from the screen: the generator writes it.

- `T_WaterFlow` (new, 2048 px, per map): RG = the current as a world direction **along each river's own bed**
  (strength dying away in lakes and tarns), B = depth, A = damp ground. The Four Marches' rivers now run outward
  from the High Moor on all four arms; the Riverlands' follow their beds downstream.
- **Depth colour**: the bed (pebbles; pale gravel on a ford) shows clear through the shallows, bent by the ripples
  and with light playing on it, then turquoise, then dark in the channel.
- **Ripples**: a generated normal map carried down the current in two phases (a flow map, so the pattern never
  stretches) under two layers of wind chop; rougher over fords and under falls.
- **Foam**: a ragged edge at the bank, lines that lap in and die, white streaks drawn out downstream over fords and
  fast shallows, faint lines of current everywhere it runs. A still marsh pool has none.
- **Falls**: boiling white at the foot and rings running out across the pool (`Fall0..3`, from the layout's new
  `falls[].foot`); `M_Waterfall` has a glassy lip, three speeds of streak and ragged sides; three sheets of fast fine
  spray (`MI_Mist_Spray`) stand at each foot inside a Local Fog Volume.
- Sparkles: a few sun glints winking on the crests.

**Water plugin or custom material?** Custom. The Water plugin's rivers and lakes are spline water-body actors
that carve and read a Landscape and bring their own meshing, collision and buoyancy; this world is generated static
meshes with gameplay that already knows the water (the grid measures depth under `SRWater` sheets). Single Layer
Water as a shading model on our own meshes would work in principle, but it wants scene depth and a separate pass, the
forums carry unresolved Mac / Metal reports for it across 5.x (broken visuals, a bake crash on 5.6.1, distance
culling), and it would not give the texel look. Baked depth + flow costs two texture reads and behaves the same
everywhere.

### Mist (not the fog of war)

- **Ground mist** (`MI_Mist_Ground`, new): the land's own meshes drawn again, lifted 75 cm, showing only where mist
  pools: `T_WaterMap.a` (new: hollows at two sizes, the water's margins, none on the kingdoms' tables or on steep
  ground). It lies in dips, follows every slope and drifts in curling wisps. Peak opacity 0.24: troops stand in it
  to the waist and stay readable.
- River mist and valley sheets: the same material with better wisps (three octaves, curled); valley sheets a little
  thinner (0.42 -> 0.3).
- **Local Fog Volumes** over each mere and at each fall's foot: real depth of lit haze for almost nothing.

### Lighting and post

Sun a shade more golden (255, 209, 154) and 11 lux; saturation 0.9 -> 0.98 and contrast 1.0 -> 1.05 (the ground now
has colour worth letting through); highlights a touch warmer; vignette 0.5 -> 0.42. Sun angle, sky fill, haze,
bloom, exposure and the tilt-shift are unchanged: they were sound, and the haze is tied to the camera in C++.

### Water as a wall (gameplay)

The grid already blocked deep water and orders already snapped to walkable ground. One hole was found and closed:
`ASRUnit::CanStep` and `ASRUnit::Nudge` asked only a probe point ahead of the troop, so a step or a shove **along a
bank** could clear the corner of a water cell with the probe and land in it. Both now also ask the spot stepped
onto (the same for steep ground). `USRBattleSubsystem::SpawnUnit` moves a spawn that would land in deep water to the
nearest walkable ground. Test: `Tools/water_wall_test.py` (see Results).

## A trap worth remembering

`smoothstep(hi, lo, x)` with the edges reversed is **undefined on Metal** (it came out as a constant). Write
`1.0 - smoothstep(lo, hi, x)`. The rock's top / side blend and two foam terms were wrong until this was found.

A full `Tools/build_visual_materials.py` run straight after a PIE session crashed the editor once
(`DeleteAllMaterialExpressions`, "!IsRooted", on one of the materials built after the buildings'). Rebuild only what changed:
`ONLY=['terrain','water','rock','atmosphere']`.

## Results

**Frame rate** (`sr.Perf`, PIE at 1920 x 1080, this Mac, 60 fps cap). The editor paces PIE down to 30-40 fps whenever
another application is in front, so only samples taken with the editor frontmost count; GPU time is the number to
compare either way.

| Map | Before | After (editor frontmost) |
| --- | --- | --- |
| The Riverlands | GPU 12.9 ms over the kingdom (42.7 fps logged with the editor behind another window) | **60 fps** at all six views (kingdom, max zoom-out, falls, ford, ford close-up, mere): GPU 14.6 to 15.4 ms |
| The Four Marches | not measured | **60.0 fps** at kingdom, max zoom-out and falls before the last water change (GPU 14.8 to 16.0 ms). After it, the editor lost the front during the run (someone was using the Mac): 46 to 59 fps logged, GPU 12.7 to 15.0 ms, which is inside the 16.7 ms a 60 fps frame allows. **Not re-measured cleanly frontmost in the final state.** |

The pass costs about 2 ms of GPU. One thing was bought back: Lumen traced a reflection ray per water pixel (about 4 ms
with a river filling the view, GPU 17.5 ms); `r.Lumen.Reflections.DownsampleFactor=2` (`Config/DefaultEngine.ini`)
and fords kept too rough to trace (`FordRoughness`) bring the worst water view to about 15 ms.

**Water as a wall** (`Tools/water_wall_test.py`: six troops spawned 13 m from the bank, ordered as a formation into
the middle of the water, then to the far side, then back at the water, then five enemies spawned at their backs;
`sr.Status` `inwater=` sampled throughout, game speed x3).

| Run | Result |
| --- | --- |
| The Riverlands, before the fix (21 of 56 cases run) | **2 cases put a troop in deep water**: a mere bank at (-14367, 323) on the third order, a tarn bank at (-10491, 18105) during the fight |
| The Riverlands, after | 0 of 28 cases; the two failing cases three more times each: 0 of 6 |
| The Four Marches, after | 0 of 44 cases (rivers, meres, tarns, the edge lakes) |

Not covered by the script: building placement on water (the grid's footprint check refuses water cells; read, not
re-tested) and the Scout's wandering (its goals are already filtered for water).

**`sr.GridCheck`** after the regeneration (the land's meshes are byte-identical: only textures, rubble instances and
layout fields changed): the Riverlands 153,650 open cells, 6,969 deep water, every gate, vein, relic and old tower
reachable; the Four Marches 333,883 open cells, 21,380 deep water, all reachable.

**Screenshots** (`Saved/Screenshots/SR/`): `before_two_*` against `final_two_*` (kingdom, ford, ford_close, falls,
mountain, mere, shrine, out; `final_two_marsh`, `final_two_crag` are new views); `final_four_*` (kingdom, ford,
ford_close, falls, moor, mere, bridge, out, cliff, cliffclose, edge) against the lead's `four_*`.

## Not done, and why

- **True soft shorelines**: the water is opaque, so the edge is softened by the bed showing through, the wet bank and
  the foam, not by alpha. Where a sheet lies almost level with flat ground (the marsh pools) its polygon edge can
  still be seen close up.
- **Rock on mid slopes (about 40 to 50 degrees)**: laid from above, so its texels run a little down the face. Fixing it
  fully means blending three projections (four more texture reads per rock pixel); left out for frame time.
- **Ford foam** is on the heavy side at close zoom (`final_two_ford.png`); `StreakTile` / the `fast` threshold in
  `WATER_CODE` are the knobs.
- **`M_Prop` normal maps**, the masonry and timber props: untouched.
- **The intro / loading film and the main-menu backdrop** still show the old look (phase 2 re-records it).
- **The minimap base** is the generator's own picture and does not know the new colours (it still reads correctly).

## Notes for phase 2

- **Forests and groves**: `T_N_Forest_D/_N` (Poly Haven `forrest_ground_01`, CC0) is already imported for a forest
  floor. `M_Terrain` has no "under the trees" channel yet; the splat map's G (moss) already rises under the woods
  (`build_splat`: `wood`), so the cheapest floor is one more texel-by-texel takeover keyed on a wood mask (the splat
  has no free channel: put it in a new data map, or in `T_WaterFlow` if the damp channel is merged into the pool
  channel). New trees must keep the trunks' blocker boxes (`Fir_<wood>_NNNN`) or re-run `gen_battlefield.py`'s
  checks. Broadleaf sprites or meshes should go through `M_Foliage` (UV1.x = baked shade, UV1.y = sway weight).
- **Falling leaves**: there is no Niagara in the project; the FX are `ASRFXSprite` cards and the birds are a
  procedural mesh (`ASRBirds`). A leaf fall can be either: a camera-following procedural mesh like the birds is the
  cheapest. Keep it out of depth of field's way (draw after DoF like the rings, or keep it near the focus plane).
- **Fire on damaged buildings**: `MI_FX_Fire`, `MI_FX_Smoke` exist (sprite sheets). A Local Fog Volume with a warm
  `fog_emissive` gives a glow in the haze for nothing; `local_fog()` in `Tools/build_battlefield_visuals.py` shows
  the properties, but fire is spawned at run time, so do it from C++ (`ULocalFogVolumeComponent`).
- **Mist and troops**: ground mist is a translucent shell 75 cm up. If phase 2 adds tall translucent things (smoke,
  leaves), check `translucency_sort_priority` (ground mist -1, river mist 0 / 1, spray 2..4).
- **Frame time**: the terrain pixel reads about two dozen textures. If phase 2 needs headroom, the first things to
  drop are the ground-mist shells on chunks with no pool (they are drawn everywhere now) and `RockDetail`.
- **Intro film**: record after forests; the falls (two on the Riverlands at (+/-8900, -/+17900), four on the Four
  Marches at 6700 from the centre on the axes) and the Black Meres are the best new shots.
- **Views used for before / after**: `Tools/visual_shots.sh <prefix> <two|four>` (needs PIE on that map).


---

# Phase 2 (2026-11-19): forests, falling leaves, fire, and phase 1's loose ends

## What changed

### Forests (`Tools/world/props.py`, `dressing.py`, `gen_battlefield.py`, `Tools/textures/gen_forest_textures.py`)

The woods were stands of one kind of fir. They are forests now, in the same places (nothing the plan keeps clear was touched).

- **Species**: oak (three sizes), maple (two, autumn reds and ambers), birch (two, white stems), a dead snag, beside the
  five firs. Each wood has a character by its index (`Dressing.WOODS`: pine, mixed, oak, autumn). The species of the
  trees `scatter()` already placed is picked from a hash of the spot, so no random stream was drawn on: boulders,
  ruins and every other placement are where they were.
- **Trees**: made in code in the firs' idiom (`broadleaf`, `leaf_clump`: a bark trunk and boughs under clumps of three
  short leaf skirts each, the skirt textured like a fir's bough tier). Each tree has a far-view mesh (`<name>_LOD1`,
  about a third of the triangles; `import_world_assets.py` makes it LOD 1 under 0.3 of the screen). The firs got one too.
- **Density**: `Dressing.groves()` (its own random stream, seed + 7777) adds trees between the stands until the crowns
  close: 302 on the Riverlands, 712 on the Four Marches. Each has the same 46 cm trunk box; none stands nearer than
  2.5 to 3.2 m to another trunk, and a wandering ride 3.4 m wide is left open through every wood.
- **Undergrowth** (no collision): bracken, dead bracken, bramble, toadstools, bluebell drifts, saplings (cards from
  `T_Undergrowth`), shrubs along the edges (`SM_Bush_*`), mossy logs, broken logs and stumps (`SM_Log_*`). 4,713 pieces
  on the Riverlands, 9,115 on the Four Marches. Meadow grass is thinned to a quarter under the canopy.
- **Forest floor**: a new data map, `T_Forest` / `T_Forest4` (R = how closed the canopy is, G = its shade), from the
  trees' own positions. `M_Terrain` lays Poly Haven's `forrest_ground_01` texel by texel where the canopy closes (blade
  tips hold out, so the edge is ragged grass) and darkens the ground under and round a wood (`ForestShade` 0.8).
- **Close views**: a crown nearer than 23 m to the camera thins away in a dither and is gone at 9 m (`M_Foliage`
  `CameraFade`), so the close zooms look in under the trees. Trunks never fade. Troops under a canopy still show
  through as the team-coloured silhouette (`M_Occlusion`).

### Falling leaves (`Source/SovereignRealms/FX/SRLeaves.*`, `M_Leaves`)

`ASRLeaves`: one procedural mesh, one quad a leaf, rebuilt each frame like the birds. It reads the trees once from the
level's instanced foliage (actors tagged `SRTrees`), keeps the ones within about what the screen shows of the camera's
focus, and lets leaves go from their crowns: they side-slip and tumble down the wind, lie a few seconds and shrink away.
A broadleaf sheds 14 at a time and a fir a fifth of that, up to 600, so a wood is thick with them and a lone tree sheds a
few. Colour follows the species. Lit, masked, two-sided, so depth of field treats a leaf like anything else. Settings:
Sovereign Feel > World > Leaves. `sr.Leaves` logs the counts.

### Fire (`Source/SovereignRealms/FX/SRFire.*`, `SRBuilding.cpp`, `Tools/build_fx_materials.py`)

The old fire was two flipbook sprites and a smoke sprite once a building fell under half health. The first version of
the new one (four tall cones on the corners) was rejected by the user as candles on a cake; what stands now:

- **Where**: `ASRBuildingFire::Seat` reads the building mesh's own vertices (kept in memory: `allow_cpu_access`, set by
  `import_buildings.py`), finds roof lines, wall heads and the lips of breaches, and roots up to 44 small flames on them
  in up to 8 clusters. It works on any building without authoring.
- **Size**: a tongue is 0.16 of the building's height, never under 45 cm nor over 85 cm before its own variation, so
  flames are a fraction of a storey on a hut and on a keep alike. They grow 0.8 to 1.2 with damage and no further.
- **Damage**: nothing above 80 % health (`FireStartFraction`), one cluster just under it, all of them near 10 %.
  Clusters catch one after another and each flame joins its cluster a little late, so the fire spreads rather than
  switches on.
- **Smoke carries it at distance**: up to 56 puffs rise fast, slow, swell from under a metre to five and lean downwind,
  sorted far to near, dark, lit orange from beneath while young. Sparks climb over each cluster.
- **Light**: an unshadowed point light (150 cd at full strength, flickering) on the walls and ground, and a faint glow in
  a local fog volume. `sr.Fire.Flame`, `sr.Fire.Glow`, `sr.Fire.Haze`, `sr.Fire.Smoke` tune them live.
- **Soot**: `M_Building` and `M_BuildingCard` take a `Burn` value per building (custom primitive data 4). Walls blacken
  from their heads down in whole texels, a few texels glow, cloth and thatch singe. It clears slowly under repair.
- **Collapse**: a ring of dust rolls out along the ground, dark smoke and sparks are thrown up, the light flares; the
  ruin smoulders for 32 s (`RuinSmoulderTime`).
- **Fallback, kept on purpose**: if the three materials are missing from a build, or `bBuildingFire` is off,
  `ASRBuilding::UsesNewFire()` is false and the building burns with the old sprites exactly as before.
- `sr.HurtBuilding <fraction> [X Y | all]` and `sr.Fires` are the test commands.

### Phase 1's loose ends

- **Ford foam**: the streak threshold was 1.04 - 0.3 x fast at strength 0.8; it is 1.09 - 0.17 x fast, broken up by the
  foam noise, at 0.26 to 0.6. A riffle, most of the bed left clear.
- **Marsh pools**: shallow water lying level with its bank silts up texel by texel into the land's own wet mud
  (`SiltWidth` 85 cm, ragged), and is peat-stained close in under the bank (`MarshTint`). The sheet's outline is gone.
- **Ground mist**: both levels were rebuilt, so only chunks with somewhere for mist to lie carry a mist shell
  (141 sheets on the Riverlands, 260 on the Four Marches, river and valley sheets included).
- **Shrine isle mist at max zoom-out**: looked at with deer and troops on the isle; they read through it. Left as it was.

## Results

**`sr.GridCheck`**: the Riverlands 153,041 open cells (153,650 before: the new trunks), 6,969 deep water, both gates on
the main ground, all 75 checks (veins, relics, old towers) reachable. The Four Marches 332,771 open cells (333,883
before), 21,380 deep water, both gates on the main ground, all 110 checks reachable. The cells cut off from the main
ground (11,131 and 23,315) are the same with and without the new trees: mountain tops and marsh pockets.

**Pathing**: six Shieldbearers sent from the south edge of the Riverlands' largest wood, (-1500, -16500), to its north
edge, (-1500, -10600): five arrived in formation within 27 s of game time. The sixth had been spawned by the test
inside a trunk's box and was still working its way out; that is the test's spawn point, not the route.

**Frame time** (`sr.Perf`, PIE at 1920 x 1080). The editor could not be brought to the front from a script, so PIE was
paced at 30 fps throughout and **no 60 fps figure was measured in phase 2**. GPU time, which is the number to compare:

| View | The Riverlands | The Four Marches |
| --- | --- | --- |
| Kingdom, five or six buildings burning | 13.8 ms | 14.3 ms |
| Kingdom, default zoom | 10.7 ms | not measured |
| A wood, mid zoom | 14.5 ms | 14.3 ms |
| A wood, close zoom | 14.6 ms | not measured |
| Max zoom-out | 12.5 ms | 13.0 ms |
| Ford | 13.2 ms | 14.0 ms |
| Falls | 12.5 ms | 13.3 ms |

All under 16 ms. A caution about these numbers: in one earlier session the same counter read 21 to 23 ms for every view
and did not move when the screen percentage was halved, so in that state it was not measuring the scene. The table is
from sessions where it varied with the view, but it wants repeating with the editor in front.

## Traps found

- **A mesh re-import resets the meshes' material slots.** After `import_world_assets.py` with `PARTS=['meshes']`, the
  whole world draws in the default grey until the materials are put back: run `build_battlefield_visuals.py` with
  `PARTS=['materials']` (new) for each map. This cost an hour here; it looks like missing textures and is not.
- **Do not touch texture properties just before PIE.** A texture whose property was just changed has no resource for a
  moment; the HUD drawing one asserts (`CanvasItem.cpp`, `InTexture != nullptr`) and takes the editor down.
- After an editor crash the MCP port can fail to bind on the next start: quit and start again.
- `sr.Camera` followed at once by `sr.Shot` can catch the previous view. Wait two seconds; ten for leaves to fill a view.

## Not done

- **`M_Prop` masonry and timber** (normal maps, the beauty pass over what is still flat): not started.
- **A 60 fps measurement with the editor frontmost**, on either map.
- **Leaves are subtle in a still**: a handful show in a close screenshot. They read in motion; nobody has watched them
  in motion at the desk yet. `LeavesPerTree` and `LeafSize` are the knobs.
- **Fire seats on low, flat buildings**: the mine's flames sit on its bluff and timber because that is where its
  vertices are high. Not wrong, not ideal.
- **Before / after of the fire at exactly one view** was not possible: the camera's pitch setting changed between the
  two (the new Camera angle option). `fire_before_castle40.png` and `fire_after_castle40.png` are the same castle at
  the same health from nearly the same place.
- The intro film still shows the old look.

## Notes for the film

- Forests: the autumn wood on the Riverlands at (-16500, 12500) runs down to the river and is the best single shot;
  the mixed wood at (-1500, -13500) from zoom 0.6 to 0.8; on the Four Marches (-19500, -27500) and (-20500, -11500).
  A slow push in under a canopy shows the fade and the leaves.
- Fire: burn a kingdom with `sr.HurtBuilding 0.2` and wait 25 s for the smoke columns to stand; hold on a collapse
  (`sr.HurtBuilding 0 X Y`) for six seconds for the pall and the smouldering ruin.
- The shallow camera angle (`sr.CameraAngle 2`) at max zoom-out gives a horizon with haze and is the most filmic view
  the game has; keep the fog of war off for it (the fog plane's edge shows at the map's border).
- The falls and the meres as in phase 1's notes.


---

# Phase 3 (2026-11-19): camera angles, smaller fire, leaves that show, props, the film

## What changed

- **Fog of war has no edge** (`Tools/build_fog_material.py`). Past the grid the material used to switch to "explored",
  which showed as a pale band and a grey wedge at the map's border from the Low and Battlefield camera angles. Now the
  nearest cell's state carries on (the sampler clamps), the sky takes 0.85 of the fog of the border under it, and the
  fog thins by 0.7 between 260 m and 900 m (`DistanceFade`).
- **Masonry and timber fade near the camera** (`near_fade` in `Tools/build_visual_materials.py`; `M_Building`,
  `M_BuildingCard`, `M_Prop`, all masked now): gone within 4.5 m of the camera, whole beyond 8 m, dithered like the
  tree crowns. Only the closest zooms come that near, so at the shallow angles the view looks through a wall standing
  between the camera and its focus. Nothing fades from zoom 0.17 outward.
- **Fire** (`SRFire.cpp`): `FlameShare` 0.16 -> 0.11, `FlameMin` / `FlameMax` 45 / 85 -> 32 / 60, tongues 1.05 to 1.45
  times as tall as wide (was 1.25 to 1.7), sizes squared toward small, up to 72 flames (was 44), sparks column 6.2 m ->
  4.6 m. Tallest lick about 40 % lower; smoke unchanged.
- **Leaves** (`SRLeaves.cpp`): three in four let go of the outside of the crown (a leaf that starts inside falls hidden
  under the canopy, which is why only specks were ever seen); each has its own drift out from the tree on top of the
  wind, half of them turn over and over, and a leaf brightens face-up and dulls edge-on so the tumbling shows. The
  trees gathered are those within 0.8 of the camera's distance (was 1.25: most leaves fell off screen). `LeafSize` 22 ->
  30, `LeavesPerTree` 14 -> 30, `LeafCount` 600 -> 800.
- **`M_Prop`**: relief from the texture itself (each texel tilted by the light and dark of its neighbours, through the
  face's UV frame), a slow blotch of tone, damp climbing from the turf in three texel steps, sky-facing faces bleached,
  lichen in the joints near the ground on the stone instances (`Lichen`). No new textures.
- **The film**: see `Docs/GAMEPLAY.md` ("The film behind the main menu"). Six shots: the falls, the enemy host coming
  down the road, both hosts and the ford with the hamlet burning, the clash low across the water, the hamlet, a
  pull-back.

## Traps found

- **The engine's movie dump (`GIsDumpingMovie`) misses frames in PIE**: 264 frames for 378 ticks here, so the old
  film stuttered. `sr.Film` asks for each frame itself and holds the game's clock (a fixed step of a millionth of a
  second) until it has been saved.
- **Do not open the main menu while `Tools/film.py` is still writing the film**: the media player fails on the
  half-written file ("Failed to load video tracks") and that HUD falls back to the live realm for good.
- **The ford at (-9262, 6474) on the Riverlands cannot be reached from its south-west bank** (`sr.PathTest`: 356 m
  round by the King's Bridge). The bank there is a bluff. The film's hosts both come along the north-east bank. Worth a
  look by whoever owns the map: it is listed as a crossing.
- The default zoom is 0.285 (`Config/DefaultGame.ini`), not the class default of 0.5.
- One editor crash on stopping PIE straight after a screenshot (`SceneViewport.cpp` 196, `IsInGameThread`); not seen
  again in three more stops.

## Not done

- Leaves over a closed canopy seen from above still do not read (leaf on leaf); they read at the wood's edges, over
  ground and under the crowns at close zoom. Fir stands shed few, by design.
- The fight in the film is on the bank and in the shallows at the bank, not in mid-ford.
- A 60 fps measurement, and the cost of the three materials being masked now, were not measured.
- The menu film was checked in PIE only, not in a packaged app.
