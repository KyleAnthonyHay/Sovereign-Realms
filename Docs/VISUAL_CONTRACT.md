# Visual contract — command & combat slice

What the gameplay code builds, what it expects from art, and where the seam is.
Gameplay owns behaviour and decides which sprite frame a troop shows. The visual
pass owns lighting, fog, post-process, terrain shape, materials and the sprite
sheets, and can restyle everything below without touching C++.

## Map and game mode

| Thing | Value |
| --- | --- |
| Maps | `/Game/Maps/L_Battlefield` (THE RIVERLANDS, two kingdoms; editor startup map and game default map) and `/Game/Maps/L_Battlefield4` (THE FOUR MARCHES). Each carries an `ASRMapInfo` (folder `Map`) with its bounds, starts, camera height and minimap; see `Docs/GAMEPLAY.md` > The match. |
| Game mode | `/Script/SovereignRealms.SRGameMode` (global default) |
| Map contents | Dressed by the visual pass, see "Visual pass" at the end: outliner folders `Terrain`, `Props`, `Water`, `Buildings`, `Lighting`, `Atmosphere`, `Map`. The land is one smooth heightfield surface (chunk meshes `SM_T_Land_*`): rivers at Z = 0, the kingdoms' tables at 1750, mountains above. |
| Playable bounds | Per map, from its `ASRMapInfo`: +/-24000 cm (the Riverlands), +/-36000 cm (the Four Marches). Camera focus and move orders are clamped to it (`MapHalfExtent` in Sovereign Feel is overwritten from the level when it starts). |
| Spawned at runtime | Units, arrows, order markers, camera pawn. The three grey test blocks (tag `SRGreyboxObstacle`) are switched off in `Config/DefaultGame.ini`; boulders in the map stand in the same places. |

The empty map was first made by `Tools/create_battlefield_map.py`; everything in it now comes from the
visual pipeline described under "Visual pass". Leave **Project Settings > Game > Sovereign Feel > Scenario >
Spawn Greybox Obstacles** off: the map has its own obstacles.

## Collision rules the gameplay depends on

Units have **no collision components**. They find the world with line traces
against the **WorldStatic** object type only:

- **Water** is found by depth, not height: water sheets are static mesh actors tagged `SRWater` (no collision in
  the level; the grid traces each sheet by itself). Ground more than 14 cm under a sheet is deep water, a wall.
- **Steep ground**: the grid closes a 1 m cell whose corners differ by more than a step; troops are not pushed or
  lured onto such cells. The terrain material draws them as rock (surface normal Z under 0.86).
- **Ground**: a vertical trace per unit per frame. Anything that should be walked
  on must be WorldStatic with collision (a Landscape, or static meshes with the
  default `BlockAll` profile). Units follow uneven terrain.
- **Walls**: a horizontal trace at knee height (`StepHeight` + 5 cm). Rocks,
  trunks and walls that should stop units need WorldStatic blocking collision.
  Ledges up to `StepHeight` (45 cm) are climbed, taller ones block, drops over
  `MaxDropHeight` (140 cm) are refused. (The land has no ledges now: slopes, which the grid judges.)
- **Things units should ignore** (grass, canopies, decals, fog cards, banners):
  give them `NoCollision`, or any object type other than WorldStatic. A canopy
  with WorldStatic collision more than 4 m above a unit is ignored; lower than
  that it would be treated as ground.
- There is no pathfinding yet, only slide-around steering. Keep obstacles convex
  and leave lanes wider than about 3 m.

## Camera, so lighting and sprites can be composed for it

`ASRCameraPawn` (pawn origin sits on the ground at the focus point). The camera is low and fairly wide, so
terraces show their faces, props in front of the focus point blur into the bottom of the frame, and the
hazy distance sits in the top of it. Values live in `Config/DefaultGame.ini` (Sovereign Feel > Camera) and
the header defaults match.

| Setting | Value |
| --- | --- |
| Yaw | 0, fixed (looks along +X; +X is up the screen, +Y is screen right) |
| FOV | 50 degrees horizontal (about 30 vertical at 16:9) |
| Distance to focus | 950 cm (zoomed in) to 3600 cm (zoomed out), geometric; default zoom 0.5 = about 1850 cm |
| Pitch | -30 degrees zoomed in, -38 at the default zoom, -46 zoomed out (linear in zoom). **Sprites must read across -30 to -46.** |
| Camera height above ground | about 475 cm (in), 1140 cm (default), 2590 cm (out) |
| Ground in frame at the default zoom | about 1700 cm wide at the focus point; from about 600 cm in front of it to 1200 cm beyond it. Tall things farther up-screen (trees, bluffs) still reach into the top of the frame. |
| Start focus | player army at (-1300, 0); enemy group at (1500, 200) |

The camera pawn overrides three things on its own post-process settings and nothing else:

- `MotionBlurAmount = 0` (motion blur smears units while panning). Untick **Sovereign Feel > Camera >
  Disable Motion Blur** to hand that back to post-process volumes.
- The tilt-shift depth of field (focal distance, f-stop, sensor width; see "Tilt-shift" below).
- It also moves the level's Exponential Height Fog start distance every frame (see "Haze" below).

The sun travels toward screen right and slightly up-screen (actor rotation pitch -42, yaw 75; travel
direction about (0.19, 0.72, -0.67)). So the lit side of everything is its **screen-left** side, shadows
fall to the right and a little up-screen, and faces turned toward the camera sit half in warm grazing light,
half in cool sky fill.

## Actor classes

| Class | What it is |
| --- | --- |
| `ASRUnit` | One troop: a pixel-art sprite on a camera-facing card, a hidden shadow card and a contact-shadow decal. Origin at the feet. See "Troop sprites". |
| `ASRProjectile` | Arrow: a 44 x 9 px sprite, 77 cm long (oversized for readability), on a card along the flight direction. |
| `ASROrderMarker` | Ground-click marker (two rings), lives 0.55 s. |
| `USRRingComponent` | Flat procedural ring used for selection, hover, target flash and order markers. |
| `ASRCameraPawn`, `ASRPlayerController`, `ASRHUD`, `ASRGameMode` | Camera, input, overlay (box select, health bars), rules. |
| `USRBattleSubsystem` | World subsystem that steps units and loads the materials below. |

## Material contract

Parent materials are looked up **once per play session** by `USRBattleSubsystem`.

### Troops and arrows: `/Game/SR/Materials/M_UnitSprite` (+ `M_UnitSpriteShadow`, `M_UnitBlob`)

Described under "Troop sprites" below. Units and arrows own **no material instances**: the frame, team
colour, hit flash and fade reach the material as custom primitive data on the card component.

| Slot | Parameter | Meaning |
| --- | --- | --- |
| 0 | `FrameCol` | Sheet column of the cell to show (0-23). |
| 1 | `FrameRow` | Sheet row (0-15): animation block row + facing index. |
| 2 | `HitFlash` | 1 on the frame the unit is hit, fading to 0 over `HitFlashTime` (0.16 s). The whole sprite goes toward `HitFlashColor`. |
| 3 | `Fade` | 1 while alive; 1 to 0 while a corpse dissolves (dithered; the shadow dissolves texel by texel). |
| 4-6 | `TeamColor` | The owning team's colour, applied through the sheet's team mask. |

If the sprite assets are missing the log says so (`Missing sprite asset ...`) and units draw with the engine
default material: run the import and material steps of the pipeline.

### Test blocks: `/Game/SR/Materials/M_UnitGreybox`

Only the three optional grey obstacle blocks use it now (**Sovereign Feel > Scenario > Spawn Greybox
Obstacles**, off). Parameters `Color`, `TeamColor`, `HitFlash`, `Fade`; falls back to
`/Engine/BasicShapes/BasicShapeMaterial` if the asset is missing.

### Rings and markers: `/Game/SR/Materials/M_SelectionRing`

Falls back to `/Engine/BasicShapes/BasicShapeMaterial` (lit, opaque).

| Parameter | Type | Meaning |
| --- | --- | --- |
| `Color` | vector | Ring colour (selection green, hover cream, enemy / attack red; all tunable in Sovereign Feel). |
| `Opacity` | scalar 0..1 | 1 for unit rings; order markers fade it 1 to 0 over their life. |

The mesh is a flat annulus generated in code, 3 to 4 cm above the ground, both
windings, no shadow. UV0 maps the ring's bounding square to 0..1 with the centre
at (0.5, 0.5), so a material can do radial gradients or dashes. An unlit,
translucent or emissive material will read much better than the lit fallback.
Rings are flat, so on steep slopes they clip; a decal-based ring would be the
upgrade path.

## Troops

- **Shieldbearer**: 44 cm radius, about 142 cm tall. Bronze helmet with a team plume, scale cuirass, large
  round team-coloured shield on the left arm, short bronze sword.
- **Archer**: 36 cm radius, about 134 cm tall. Team headcloth, linen tunic with a team sash and hem, tall
  bow in the left hand, quiver on the back.
- Team colours: player `(0.05, 0.22, 0.80)`, enemy `(0.72, 0.07, 0.05)` (linear),
  editable under Sovereign Feel > Scenario.

Both are sprite sheets rendered from Blender (`SourceArt/Characters/SPRITE_SPEC.md`). Radii, body heights,
ring sizes and health bars are gameplay values and did not change with the art. How the sheets are shown and
animated is under "Troop sprites" below.

## Visual pass (what exists now)

The look is "pixel-art textures on real 3D geometry, lit and lensed like a photographed miniature":
hand-pixelled textures at one texel density, chunky stepped terraces, a low warm sun with cool fill, lit
haze with light shafts past the focus point, bloom, and a tilt-shift band of sharp focus.

### Pipeline (all re-runnable, nothing is hand-placed)

| Step | Command | Produces |
| --- | --- | --- |
| 1. Textures | `Tools/.venv/bin/python Tools/textures/gen_world_textures.py` | `SourceArt/Textures/*.png`: drawn in code from small fixed palettes (placed blade marks, laid stone courses, set cobbles). Preview sheet in `Saved/TexturePreview/`. |
| 1b. Mountain textures | `Tools/.venv/bin/python Tools/textures/gen_mountain_textures.py` | `T_MountainRock.png`, `T_Snow.png`: two CC0 Poly Haven photos (`SourceArt/Textures/Sources/PolyHaven`, with `CREDITS.md`) crushed to 128 px tiles in the game's palette. Only needed when the sources change. |
| 1c. Mountain shapes | `Blender -b --python Tools/blender/build_mountains.py` | `SourceArt/World/Mountains/peak_<n>.npy`: height grids from Blender's A.N.T. Landscape extension (noise + its eroder), which step 2 turns into the sculpted peaks at the field's far edge. Only needed to change the peaks' shapes (`CREDITS.md` there has the install line). |
| 2. World | `Tools/.venv/bin/python Tools/world/gen_battlefield.py --map two` (or `four`, `all`; `--plan`: previews only) | Map `two`: `SourceArt/Meshes/battlefield.gltf` (every static mesh), `SourceArt/Textures/T_Splat.png` (ground blend map), `T_WaterMap.png` (water data map), `T_MinimapBase.png`, `SourceArt/World/layout.json` (placements, the map's own numbers, veins, ruins, roads), `Saved/WorldPreview/map.png`, `Saved/MapPreview/layout.png` + `report.txt` (the plan as the walkability grid will read it, with its checks; a map that fails one is not written). Map `four`: the same names with a `4` before the extension. Plans: `Tools/world/maps.py`. |
| 3. Import | `Tools/ue_py.py Tools/import_world_assets.py` (`MAP='four'` or `'all'` for the other map's meshes) | `/Game/SR/Textures`, `/Game/SR/Meshes` (map `two`), `/Game/SR/Meshes4` (map `four`); re-imports in place, deletes meshes the generator dropped. |
| 4. Materials | `Tools/ue_py.py Tools/build_visual_materials.py` | `/Game/SR/Materials` (graphs cleared and rebuilt in place, references survive), with the second map's instances `MI_Terrain4`, `MI_Water4`, `MI_Mist4` (its splat map, water map and their world squares). |
| 5. Level | `Tools/ue_py.py Tools/build_battlefield_visuals.py` (`MAP='four'` for `/Game/Maps/L_Battlefield4`) | Opens (or makes) the map's level and rebuilds the outliner folders `Terrain`, `Props`, `Water`, `Buildings`, `Lighting`, `Atmosphere`, `Map` (the `ASRMapInfo`). Anything placed by hand belongs in another folder. |
| 6. Troop sheets | `Tools/blender/build_all.sh` | `SourceArt/Characters/<name>_color / _teammask / _normal.png`, `<name>.json` (see `SPRITE_SPEC.md`). |
| 7. Cards, arrow | `Tools/.venv/bin/python Tools/sprites/gen_sprite_cards.py` | `SourceArt/Characters/cards.gltf` (`SM_UnitCard`, `SM_ArrowCard`), `arrow_color.png`, `arrow_teammask.png`. |
| 8. Sprite import | `Tools/ue_py.py Tools/import_character_sprites.py` | `/Game/SR/Characters` (textures and the two card meshes). Then step 4 again, or only its sprite part: `ONLY=['sprite']`. |

The offline steps need `python3 -m venv Tools/.venv && Tools/.venv/bin/pip install pillow numpy scipy shapely mapbox-earcut`
(the venv is git-ignored). The editor steps need `Tools/ue_py_bridge.py` running in the editor (see its
docstring). While a material is being rebuilt the log shows transient "Failed to compile ... missing input"
warnings; they are the half-wired graph and stop once the script finishes. To retune only the lighting:
edit `LOOK` in `Tools/build_battlefield_visuals.py` and run it with `PARTS=['lighting']`. Rebuild one material family
with `ONLY=['terrain']` (or `water`, `atmosphere`, ...) in step 4: a full run re-saves every material, and
`M_Terrain`, `M_Water` and `M_Mist` (and the second map's instances of them) must be rebuilt whenever the generator's
splat / water map rectangle changes (they read it from `layout.json` / `layout4.json`). A data map re-imported in a
running editor can stay an empty placeholder in memory (cobbles everywhere, pale water): the import script changes
a property and saves again to make it build; if a level still looks like that, run the texture import once more.

### Texel density: 4 cm per texel, everywhere

Every world texture is authored for **4 cm per texel** (a 128 px tile covers 512 cm). The troop sprites are
finer, **1.75 cm per pixel** (a troop is about 80 px tall), because they are what the player looks at; at the
default zoom a sprite pixel is about two screen pixels and a world texel about four and a half. Meshes carry UV0 in
**centimetres** (or the material uses world XY) and the material divides by `TexelSize`, so there is no
per-mesh UV scale to get wrong. Do not scale props non-uniformly, and keep uniform scale near 1.

Texture assets are imported uncompressed (BGRA8, sRGB), **nearest** filtered, in the `Pixels2D` group.
The world materials do not use the asset's sampler: they sample through `SRPix.S` (in
`build_visual_materials.py`), which snaps to the texel grid but anti-aliases each texel edge over one screen
pixel, and uses the mip chain only once texels are smaller than a pixel. The result looks point-sampled but
does not crawl when the camera pans. `*_N` normal maps and `T_Splat` are linear data; sprite strips
(non-power-of-two) and the splat map have no mips. `T_LensDirt` is the one ordinary (filtered, compressed) texture.

| Texture | Size | What it is |
| --- | --- | --- |
| `T_Grass`, `T_GrassMoss`, `T_GrassDry` | 128 x 128 | Turf: authored blade marks laid like shingles; five close olive tones. Kept calm so sprites read on it: the palette is drawn toward its middle tone (`GRASS_CALM` 0.74), a blade mark spans three neighbouring tones, and light and dark come in clumps 6 to 10 texels across rather than texel by texel (a third less step between neighbouring texels than the first pass). Moss and straw variants take over tuft by tuft through the splat map. |
| `T_Dirt` (+`_N`), `T_Cobble` (+`_N`) | 128 x 128 | Packed earth with pebbles; old road stones in uneven rows. |
| `T_Cliff` (+`_N`) | 128 x 128 | Terrace face: a thin soil band under the turf, then coursed stone. v = depth below the turf. |
| `T_Lip` | 128 x 24 | The turf hanging over a cliff top (alpha 1 = grass, about 0.4 = its contact shadow). |
| `T_Rock` (+`_N`), `T_Sandstone` (+`_N`) | 64 x 64, 128 x 64 | Boulder skin; weathered ashlar for the ruin. (Their normal maps are imported but `M_Prop` does not use them yet.) |
| `T_Needles`, `T_Bark` | 64 x 48, 32 x 64 | One conifer bough tier (dark body, lit tips, ragged alpha rim); trunk. |
| `T_Tufts` | 96 x 24 | Sprite strip: tall grass, short grass, dry reeds (16 px cells), fern, flowers (24 px cells). |
| `T_Wood`, `T_LogEnd`, `T_Banner` | 64 x 32, 16 x 16, 16 x 40 | Planks, sawn log end, cloth banner. |
| `T_Water`, `T_Gravel` | 128 x 128 | Running water: broad pools of two close teals with sparse ripple streaks lying along the current (2 texels across per 3 down, `FLOW_TEXELS`; must agree with `FLOW_DIR` in the world generator). The pale pebble bed of a ford. |
| `T_WaterMap` | 2048 x 2048, linear data | World-aligned over the splat map's square (`layout.json` `water.map`). R = distance in from the bank (0 .. 1 over 256 cm), G = ford, B = current (0 in the still lake). Sampled bilinear and clamped; `build_visual_materials.py` sets those texture properties itself (the importer brings new PNGs in as pixel art), so run it after every texture import. |
| `T_Splat` | 4096 x 4096 | Ground blend map over the world square in `layout.json` `splat` (map 3: origin (-27400, -30720), size 61440 cm, 15 cm a texel): R = road (0 turf, 0.5 bare earth, 1 set stones), G = moss, B = dry straw, A = shade baked at cliff feet. The regions are painted here: straw-gold on the centre plain, parched and stony on the highlands, moss under the fir belts and along the river, mud at the water's edge, gravel bars at the fords, set stone on the bridges and the shrine's dais. |

### Materials (`/Game/SR/Materials`)

| Asset | Used for | Parameters worth knowing |
| --- | --- | --- |
| `M_UnitSprite` + `MI_UnitSprite_Shieldbearer`, `MI_UnitSprite_Archer`, `MI_ArrowSprite` | Troop and arrow cards | See "Troop sprites". Per unit (custom primitive data): `FrameCol`, `FrameRow`, `HitFlash`, `Fade`, `TeamColor`. Sheet: `SpriteSheet`, `TeamMask`, `NormalSheet`, `SheetCells`, `CellPx`, `PivotV`. Look: `Relight`, `BakedLight`, `NormalStrength`, `EdgeSoftness`, `HitFlashColor` (these five are driven from Sovereign Feel at run time), `HitFlashMix`, `HitFlashGlow`. Billboard: `Billboard` (0 for the arrow), `GroundLift`. |
| `M_UnitSpriteShadow` + `MI_UnitSpriteShadow_Shieldbearer`, `MI_UnitSpriteShadow_Archer`, `MI_ArrowShadow` | The hidden shadow cards | Masked, unlit: only the frame's alpha, point sampled. Same custom primitive data slots (`FrameCol`, `FrameRow`, `Fade`). |
| `M_UnitBlob` | Contact shadow decal under each troop | Deferred decal, three flat bands on a grid of `Cells`; `Color`, `Strength`; the per-unit strength arrives in the decal colour's alpha. |
| `M_UnitGreybox` | The optional grey test blocks only | `Color`, `TeamColor`, `HitFlash`, `Fade`; look: `HitFlashColor`, `HitFlashGlow`, `RimStrength` / `RimExponent`, `ShadowLift`, `PaintSaturation`, `Roughness`. |
| `M_SelectionRing` | Rings and order markers (contract above, unchanged) | Contract: `Color`, `Opacity`. Look: `Glow`, `DarkEdge`. Unlit, translucent, two-sided, drawn after depth of field so it stays sharp; depth-tested. |
| `M_Terrain` | Every `SM_T_*` mesh | Top faces (normal Z > 0.5): world-aligned turf, blended to moss / straw / earth / road stones texel by texel from `T_Splat` (never a soft blend). Side faces: `T_Cliff` by UV0 (u = distance along the outline, v = depth below the turf, cm), the turf lip over the top (`LipFraction` of the wall at most), darker at the foot (`FootShade`). World-space normal output from the `_N` maps (`NormalStrength`). `TexelSize`, `SplatRect`, `StoneRoughness`, `LipShadow`, `TintRange`, `Tint`. |
| `M_Prop` + `MI_Prop_Rock`, `MI_Prop_Sandstone`, `MI_Prop_Wood`, `MI_Prop_Log` | Boulders, standing stones, the ruin, fences, logs, stumps | UV0 in cm. `TexA` / `SizeA` where vertex colour B = 1, `TexB` / `SizeB` where it is 0 (log: ends / bark). `Moss` + `MossSlope`: turf on up-facing facets, a whole facet at a time. `FootShade`, `Tint`, `Roughness`. |
| `M_Foliage` | Conifers (`SM_Conifer_*`) | Masked, two-sided foliage shading with subsurface. Needles or bark by vertex colour B; UV1.x = baked shade (dark under each tier and at the base, lit toward the crown: `ShadeFloor`, `TipTint`), UV1.y = sway weight (`SwayAmount`, `SwaySpeed`). Per-instance random tint. |
| `M_Card` + `MI_Card_Banner` | Grass, fern and flower cards; the banner cloth | Masked, two-sided, normal forced to world up so a card is lit like the turf it stands in. UV0 is 0..1 into `Tex` (`Size` in texels). `RootShade`, `Tint`, sway. |
| `M_Water` | The river sheet (`SM_Water`) | Per world texel, from `T_WaterMap` (`MapRect`): two layers of `T_Water` streaks carried downstream (`Flow`, `ScrollTexelsPerSecond` x / y) a whole texel at a time; `Deep` / `DeepMix`; **shallows** in three stepped, dithered bands within `ShallowWidth` (150 cm) of a bank (`Shallow`, A = strength); a broken **foam line** that laps in and out along every bank (`Foam`, `FoamWidth`, `FoamSpeed`, `FoamBreak`) with a fainter second line; **fords** drawn as `T_Gravel` wetted by `FordTint` under quick bright ripples (`ScrollTexelsPerSecond` z, `FordRippleLevel`); `Glint` on the brightest crests plus winking sun sparkles (`Sparkle`). Opaque, roughness 0.1 (0.7 on foam), so Lumen reflects the haze. |

### Natural-world pass (2026-11-19; supersedes the `M_Terrain`, `M_Water`, mist and waterfall notes above)

Why and how it was judged: `Docs/VISUAL_AUDIT.md`. Outside assets and licences: `Docs/ASSET_CREDITS.md`.

**New inputs**

| Asset | Made by | What it is |
| --- | --- | --- |
| `/Game/SR/Textures/Nature/T_N_<Name>_D` / `_N` | `import_world_assets.py` > `import_nature` from `SourceArt/Textures/PolyHaven/<id>/` | Photographic CC0 textures (Poly Haven): ordinary filtered, mipped, compressed textures; normal maps BC5 with green flipped. The materials lay them on the 4 cm texel grid themselves (`SRNat.Q` + `SRNat.T2` in `build_visual_materials.py`), so they show as crisp texels like the pixel art. |
| `T_N_WaterWaves_N`, `T_N_WaterNoise` | `Tools/textures/gen_nature_textures.py` -> `SourceArt/Textures/Nature` | Tileable ripple normals; foam breakup (R), cloud (G), grain (B), streaks drawn out along +X (A). |
| `T_WaterFlow`, `T_WaterFlow4` (2048, linear data) | `gen_battlefield.py` > `build_flow_map` | Over the splat map's square. RG = the current, world XY, 0.5 = still, **along each river's own bed** (`W.current_lines`), its length the strength (0 out in a lake); B = water depth / 200 cm; A = damp ground (1 at the water's edge, 0 three metres back). |
| `T_WaterMap` / `T_WaterMap4` alpha | `gen_battlefield.py` > `build_water_map` | Where ground mist pools: hollows at two sizes, the water's margins; little on the kingdoms' tables, none on steep ground. |
| `layout*.json` > `water.falls[].foot`, `.width` | `gen_battlefield.py` > `fall_mesh` | Where each fall meets its pool (spray sheets, the pool's churn). |
| `layout*.json` > `instances` | `dressing.py` > `Dressing.rubble` | Loose stones along every crest where turf gives way to rock, pebbles on the banks. Its own random stream (seed + 4242): tuning it moves nothing else. |

**Materials**

| Asset | Used for | What it does / parameters worth knowing |
| --- | --- | --- |
| `M_Terrain` (+ `MI_Terrain4`: `Splat`, `FlowMap`, `SplatRect`, relief lines) | Every `SM_T_*` mesh | Turf: the pixel tile x a grass photograph (`GrassDetail`, `GrassTile`), an aerial photograph (`MacroStrength`, `MacroTile`) and three sizes of noise (`Variation`, `LushTint`, `ParchedTint`); clover drifts with flowers (`CloverTint`, `Flowers`, `FlowerBright`); a grass normal (`GrassNormal`). Roads: yellowed verge, pebble detail. Wet banks from `T_WaterFlow.a` (`WetDark`, `WetRough`, `MudTint`). Rock where normal Z < `RockSlope` or above `RockLine`: crags from above, strata from the side, grain, beds and ledges along the contours (`RockTile` X / Y / Z / W = cm each spans, `RockTopGain`, `SideTint`, `RockFaceTint`, `RockNormal`, `Strata`, `LedgeCm`, `LedgeDark`), lichen and moss on sky-facing rock (`MossSlope`, `LichenTint`). The broken lip above the rock's edge (`LipWidth`, `LipDark`, `ScreeTint`). Outputs normal, roughness and specular. Deck sides (bridges) are unchanged. |
| `M_Rock` + `MI_Rock_Ruin` | `SM_Rock_*` (boulders, scree, rubble), `SM_Cairn`; standing stones and dolmens | The mountains' rock from three sides on the world's texels, lichen and moss on top (`Tile`, `Moss`, `MossSlope`, `Tint`). World-aligned: for static pieces only. `MI_Prop_Rock` (on `M_Prop`) still dresses relics, barrows and bones. |
| `M_Water` (+ `MI_Water4`: `WaterMap`, `FlowMap`, `MapRect`, `Fall0..3`) | Every water sheet | Opaque, lit, world normal out. Depth colour from `T_WaterFlow.b`: the bed (`Bed`, `BedTint`; `Gravel` on a ford) clear to `ClearDepth`, `Shallow` turquoise, `Deep` by `DeepDepth`; `Refraction`, `Caustics`. Ripples: `Waves` carried by the flow map in two phases (`FlowSpeed` cm/s, `FlowRate`) under two wind layers (`WindScroll`, `WaveTile`), `NormalStrength`, `FordChop`. Foam on the texel grid: bank edge (`EdgeFoam`), lapping lines (`LapSpacing`, `LapSpeed`, `LapReach`), current streaks (`StreakTile`, `StreakSpeed`), churn and rings under the falls (`Fall0..3`: XY, Z = reach). `Sparkle`, `Glint`, `WaveShade` (the ripples' lit and shaded sides), `FordRoughness` (0.45: keeps fords out of Lumen's reflection traces). The old single `Flow` direction is gone. |
| `M_Waterfall` | `SM_Waterfall_n` | Glassy lip, three speeds of streak, white foot, ragged sides (`Columns`, `CellCm`, `Speed`, `Bright`). |
| `M_Mist` + `MI_Mist4`, `MI_Mist_Valley`, `MI_Mist_Ground` (+ `MI_Mist_Ground4`), `MI_Mist_Spray` | River mist, valley sheets, ground mist, fall spray | One material, three ways of being laid: `UseMap` 1 (over water, thins at the banks), `Ground` 1 (the land's meshes lifted `Lift` cm, shown where `T_WaterMap.a` says mist pools, none on slopes), neither (a level sheet fading to its rim). `Scale`, `Cover`, `Soft`, `Strength`, `Wind`, `FadeDistance`, `Colour`. |

**Level** (`build_battlefield_visuals.py`, part `atmosphere`): folder `Atmosphere/Mist/Ground` (a `GroundMist_NNN` actor per
land chunk, no collision, no shadow, out of Lumen's scene), `Atmosphere/Mist/Falls` (three `FallSpray` sheets per
fall), `Atmosphere/Mist/Haze` (Local Fog Volumes `FallHaze_n`, `MereHaze_n`). **Lighting**: sun (255, 209, 154) at
11 lux, saturation 0.98, contrast 1.05, highlight gain (1.1, 1.01, 0.87), vignette 0.42; the rest as in the table below.

**Rules**: never write `smoothstep(hi, lo, x)` in a material (undefined on Metal: use `1.0 - smoothstep(lo, hi, x)`).
Rebuild only the families you changed (`ONLY=['terrain','water','rock','atmosphere']`). After changing the generator's
maps: `gen_battlefield.py --map all`, `import_world_assets.py` with `PARTS=['textures']`, then the materials, then the level.

### Forests, leaves and fire (phase 2, 2026-11-19)

Why and how it was judged: `Docs/VISUAL_AUDIT.md`, "Phase 2".

**Pipeline additions.** `Tools/textures/gen_forest_textures.py` (the woods' pixel art) before step 2. Step 2 now also
writes `T_Forest.png` / `T_Forest4.png`. After **any** mesh import (step 3) run step 5, or at least
`PARTS=['materials']` of it, for each map: an import resets the meshes' materials to the default grey.
`Tools/ue_py.py Tools/build_fx_materials.py` builds the fire's and the leaves' materials (`ONLY=['fire']` / `['leaves']`).
`Tools/perf_front.sh` samples frame times at a list of views; `Tools/sheet.py` makes a contact sheet of screenshots.

| Asset | Used for | What it does / parameters worth knowing |
| --- | --- | --- |
| `T_Forest`, `T_Forest4` (2048, linear data) | `M_Terrain` `ForestMap` | Over the splat map's square. R = how closed the canopy is, G = the same spread wider (shade). |
| `M_Terrain` > Forest | the forest floor | `ForestTile`, `ForestTint`, `ForestShade` (0.8: the ground's brightness in a wood's shade). |
| `M_Foliage` + `MI_Foliage_Oak`, `_Birch`, `_Maple` | `SM_Tree_*`, `SM_Bush_*` | The firs' material; `Needles` is the leaf clump (`T_Leaves*`, 64 x 48 like `T_Needles`), `Bark` the stem. New on the parent: `CameraFade` (X = cm from the camera at which leaves are gone, Y = at which they are whole: 900, 2300). |
| `MI_Card_Under` | `SM_Under_*` | `M_Card` on `T_Undergrowth` (160 x 32: bracken 32, bramble 32, toadstools 16, bluebells 16, sapling 32, dead bracken 32). |
| `MI_Prop_LogMossy` | `SM_Log_*` | `M_Prop` with moss on up-facing facets. |
| `M_Water` | marsh pools, fords | New: `SiltWidth`, `MudTint`, `MudTile`, `MarshTint`. The ford's streak foam is lighter (in the code, not a parameter). |
| `M_Building`, `M_BuildingCard` | every building | New: `Burn` (custom primitive data **4**, 0..1): soot from the wall heads down, glowing texels, singed cloth. Set by `ASRBuilding::StepFire`. |
| `M_FX_Flame`, `M_FX_Smoke`, `M_FX_Embers` | `ASRBuildingFire` | Unlit, translucent, procedural. Quad data: UV1 = (seed, flame's share alight / smoke's age / spark count); colour R = strength or opacity, G = heat from below (smoke), B = 0 dust .. 1 smoke. `Glow`, `Cells`, `Speed`; smoke's colours are screen colours under the level's 11 lux sun, not albedos. |
| `M_Leaves` | `ASRLeaves` | Lit, masked, two-sided; the leaf's colour is the vertex colour. |

**Level.** Instanced families added: `Broadleaves` (`SM_Tree_*`), `Shrubs` (`SM_Bush_*`), `Undergrowth` (`SM_Under_*`: no
shadow, out of Lumen's scene, culled at 130 m), and `SM_Log_*` under `Deadwood`. The `Conifers` and `Broadleaves` actors
carry the tag **`SRTrees`**: `ASRLeaves` finds its trees by it. Trunk boxes are named `Fir_<wood>_NNNN` (the plan's) and
`Fir_<wood>_gNNNN` (added by `groves()`), whatever the species.

**Runtime contract.**
- `ASRBuildingFire` needs the building meshes' vertex data at run time (`allow_cpu_access`, set by `import_buildings.py`).
  Without it the flames fall back to spots over the footprint at roof height.
- Custom primitive data on a building's mesh: 0..3 team colour, **4 burn**.
- Without `M_FX_Flame`, `M_FX_Smoke` and `M_FX_Embers`, or with Sovereign Feel > Buildings > Fire off, buildings burn with
  the old sprites (`ASRBuilding::UsesNewFire`). This fallback is permanent.
- Translucency sort priorities: ground mist -1, river mist 0 / 1, spray 2..4, **smoke 6, flames 7, embers 8**.

### Level contents

Both levels are built the same way from their layout (`layout.json`, `layout4.json`); what is in a map is listed in
`Docs/GAMEPLAY.md` > The match.

| Folder | Contents | Collision |
| --- | --- | --- |
| `Terrain/Land` | The land: one smooth heightfield surface dealt out into 64 m chunks (`SM_T_Land_NNN`; about 194,000 triangles on the Riverlands, 395,000 on the Four Marches). An irregular triangle mesh cut from a 1 m raster: within 6 cm of it where troops walk, looser on mountainsides, under water and beyond the field. Smooth normals; UV0 = world (Y, -X) in cm, UV1 = (0, 2), which tells `M_Terrain` this is the land: turf / road by the splat map where it is gentle, living rock where the normal's Z falls under 0.86 (a slope of 0.6), bare rock and snow by height. It runs on under the water as the beds. | WorldStatic, blocks (render mesh used as collision) |
| `Terrain/Bridges`, `Terrain/Shrine` | Bridge slabs on piers over the rivers and brooks (7 m and 6.4 m wide, 62 cm over the water; the banks are level with them), and the shrine's round paved dais on the Riverlands' island (24 cm). | WorldStatic, walkable |
| `Water` | `River`: one sheet for the rivers and the lakes they run into (Z = -16). `Tarn_n`, `Mere_n`: a sheet each for the tarns on the hills and the Black Meres, at their own heights. All tagged `SRWater`. `Waterfall_n`: a ribbon from each tarn's lip down the rock face to its pool (`M_Waterfall`). | none in the level; the grid traces each `SRWater` sheet by itself to measure the water's depth |
| `Props/Rocks` | Blocking boulders (`Rock_NN`, `Rock_NN_b` .. for the other kingdoms' copies), each with one invisible convex box `<name>_Collision` (an instance in the `Blockers` actor, tag `SRBlocker`) under a mesh of its own; standing stones, dolmens, cairns, barrow doors; gold veins (`Props/Veins`). | boxes only |
| `Props/Ruin` | The old kingdom's masonry: arches, walls, pillars, obelisks, the colossus, the aqueducts (`SM_Aqueduct_n`, a mesh per aqueduct), the bridges' pillars and parapets, the fallen bridge, the fallen keeps. `Relic_NN` (tag `SRRelic`) and `RuinTower_NN` (tag `SRRuinTower`) are the ruins towers can be raised on. | One box per blocking piece |
| `Props/Bones`, `Props/Relics`, `Props/Structures` | The wyrm's bones (`MI_Prop_Bone`); the field of swords (swords, spears, shields, a cart, banner poles); timber watch posts and jetties. | Boxes under the big pieces |
| `Props/Foliage` | Instanced actors `Conifers` (firs, five sizes 4.3 to 12.5 m) and `Grass` (blade / fern / flower cards and the reeds along the banks, no shadows). In the woods every fir has a 46 x 46 cm trunk box (`Fir_<wood>_NNNN`); the firs on the mountainsides and beyond the field have none. | trunk boxes |
| `Props/Fences`, `Props/Logs` | Fence runs, stumps and logs round the kingdoms. Dressing only. | none |
| `Buildings` | The kingdoms' starting castle, farm and mine (`ASRBuilding`), on their tables. | their own |
| `Lighting` | `Sun`, `SkyLight`, `SkyAtmosphere`, `HeightFog`, `PostProcess`. Values below. | n/a |
| `Atmosphere` | `Mist`: the river sheet twice more, 52 and 96 cm above the surface, in `M_Mist` (soft drifting wisps that thin out at the banks by `T_WaterMap`), and level sheets of `MI_Mist_Valley` over the lakes, the falls' pools, the water meadows, the Black Meres and the landmarks' hollows. | none |
| `Map` | `MapInfo` (`ASRMapInfo`): the map's id, bounds, starts, camera height, trace range and minimap. | n/a |

### Lighting, haze, post (the `LOOK` table in `Tools/build_battlefield_visuals.py`)

| Thing | Value |
| --- | --- |
| `Sun` | Movable directional, pitch -42, yaw 75, 10.5 lux, warm (255, 214, 165), source angle 1.8 for soft miniature-scale penumbrae, volumetric scattering 11 (the light shafts). Virtual shadow maps. At 42 degrees a shadow is 1.1x its caster's height (1.5x at the old 33), so trees and castles no longer lay black bars across the lanes. |
| `SkyLight` | Movable, real-time capture of the `SkyAtmosphere`, intensity 9.5, cool tint (208, 226, 255), volumetric scattering 0.3 (low, so shadowed haze stays dark and the shafts show). Raised with the sun so shadowed ground sits near 35-40% of lit ground. |
| `HeightFog` | Density 0.55, height falloff 0.3, **volumetric** (albedo (255, 242, 224), scattering distribution 0.35, view distance 16000). Its start distance is driven by the camera, see "Haze". |
| `PostProcess` (unbound) | Manual exposure (bias -0.7, never adapts). Bloom 1.3 with a wide kernel and a lens-dirt mask (`T_LensDirt`, intensity 6), light lens flare, vignette 0.5, fringe 0.35, grain 0.12. Grade: saturation 0.9, contrast 1.0, shadow gain (0.88, 1.0, 1.12) = teal-cool, highlight gain (1.08, 1.0, 0.88) = warm, small positive offset so blacks are lifted, film toe 0.4 / slope 0.84 / shoulder 0.3. Motion blur 0. |
| Lumen | Global illumination and reflections (project default). |

Exposure, sun, sky and grade are tuned as a set; change them together.

### Haze (Sovereign Feel > Visuals > Haze)

`ASRCameraPawn` finds the level's Exponential Height Fog and, every frame, sets its start distance (and the
volumetric fog start / fade-in) from the camera-to-focus distance. The haze therefore begins just past the
focus point at every zoom: troops in the sharp band are clear, everything up-screen sinks into lit haze,
and the trees there cut shafts through it. That is why the fog can be this dense.

| Setting | Default | Meaning |
| --- | --- | --- |
| `bHazeTracksFocus` | on | Off leaves the fog actor's own start distance alone (it would then sit on the troops). |
| `HazeStartFraction` | 1.05 | Haze start, as a fraction of the camera-to-focus distance. |
| `HazeFadeFraction` | 0.7 | Fade-in distance past the start, same unit. |

### Tilt-shift depth of field (Sovereign Feel > Visuals > Tilt Shift)

Owned by `ASRCameraPawn::ApplyView`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `bTiltShift` | on | Master switch. Off removes the most expensive post pass. |
| `TiltShiftBlur` | 0.6 | Blur when fully zoomed out: blur-disc diameter, in % of screen width, of something infinitely far behind the focus point. Low, so the whole tactical view reads. |
| `TiltShiftBlurZoomedIn` | 0.8 | Same, fully zoomed in. Props between the camera and the bottom of the frame and the hazy distance still blur; the ground the troops stand on does not. |
| `TiltShiftFocusOffset` | 0 | Moves the sharp plane nearer (-) or farther (+) than the focus point, cm. |
| `TiltShiftFocusBias` | -0.04 | The same as a fraction of the camera-to-focus distance, so it holds at every zoom. Slightly nearer shares the sharp band with the troops in the bottom of the frame. |
| `TiltShiftFstop` | 1.4 | Bokeh shape only. |

These were 1.6 / 1.5 with no bias before the troops became sprites: at those values a troop in the bottom third of
the default view was blurred by a disc about nine screen pixels wide, three to four of its own sprite pixels. The
blur of a point at distance D is `Blur * |1 - S / D|` for focus distance S, so it grows fast toward the camera
and levels off behind the focus point. At the current values a troop at the bottom edge of the default view is
blurred by about 3 px (one sprite pixel) and one at the top edge by about 5 px, while a prop at half the focus
distance still gets about 12 px and the far backdrop about 10 px plus the haze (computed from the formula for a
1920 px wide view, then checked by eye in captures).

The focal distance is the camera-to-focus distance, so the sharp band follows pan and zoom. Do not add
depth-of-field overrides to a post-process volume: the camera's values win.

`Config/DefaultEngine.ini` `[SystemSettings]` adds `r.Lumen.ScreenProbeGather.DownsampleFactor=32`,
`r.DOF.Gather.RingCount=4`, `r.Tonemapper.Sharpen=0.5`, and for the shafts
`r.VolumetricFog.GridPixelSize=6`, `r.VolumetricFog.GridSizeZ=128`, `r.VolumetricFog.HistoryWeight=0.92`.
Do not set both `r.DOF.Scatter.*Compositing` cvars to 0: that removes the depth-of-field pass altogether.

## Troop sprites (what is implemented)

Source art, sheet layout and the animation rules are in `SourceArt/Characters/SPRITE_SPEC.md`. This is how
the game shows them. Code: `Units/SRSprite.*` (sheet tables, facing), `Units/SRUnitVisuals.cpp` (state to
frame, card placement), `USRBattleSubsystem::UpdateSpriteView` (camera and sun, once per frame).

### Assets (`/Game/SR/Characters`, made by `Tools/import_character_sprites.py`)

| Asset | Settings |
| --- | --- |
| `T_<Troop>_Color` (3840 x 2560), `T_Arrow_Color` (44 x 9) | sRGB, uncompressed BGRA8 (`UserInterface2D`), nearest, no mips, never streamed, group 2D Pixels, clamped. |
| `T_<Troop>_TeamMask`, `T_Arrow_TeamMask` | Linear, 8-bit grey (`Grayscale`), otherwise the same. |
| `T_<Troop>_Normal` | Linear, uncompressed BGRA8 (`VectorDisplacementmap`), **not** a normal map: BC5 would smear the pixel edges. R = screen right, G = screen down, B = toward the viewer; green is not flipped. |
| `SM_UnitCard` | 280 x 280 cm quad in the plane X = 0, +Y = sprite right, +Z = sprite up, origin at the sprite pivot (the feet, UV v = 0.7375). Cut along the pivot row: three rows of vertices. Generated from the sheet metadata by `Tools/sprites/gen_sprite_cards.py`. |
| `SM_ArrowCard` | 77 x 15.75 cm quad in the plane Z = 0, +X toward the arrowhead. |

No mips: the sheets are not powers of two and a sprite pixel is never much smaller than a screen pixel (about
3.8 px zoomed in, 2 at the default zoom, 1 zoomed out).

### One troop on screen

| Component | What it does |
| --- | --- |
| `SpriteCard` | `SM_UnitCard` with `MI_UnitSprite_<Troop>`, given the camera's rotation every frame, so it is parallel to the view plane and the sprite keeps its proportions anywhere on screen. Its world size is the sheet's (1.75 cm per pixel), so the figure stands at its gameplay height. Casts no shadow, receives no decals, is kept out of Lumen's scene and the distance fields. |
| `ShadowCard` | The same mesh with `MI_UnitSpriteShadow_<Troop>`, hidden in game, `bCastHiddenShadow`. Shows the **frame as the sun sees it**: the facing row is chosen from the unit's yaw relative to the sun's yaw instead of the camera's (the sheets were rendered from 30 degrees above the horizon and the sun stands at 42, so that row is close to the true silhouette, a little long). |
| `Blob` | `M_UnitBlob` decal projected straight down under the feet, for contact in shade. |
| `Ring` | Unchanged (`USRRingComponent`). |

**Depth.** A card parallel to the view plane leans back with the camera: its head would cut into a wall behind
the unit and everything below the pivot would be under the ground. The material's world position offset slides
each vertex along its own view ray (which does not move it on screen): the top row onto an upright plane
through the feet, the pivot and bottom rows onto the ground, `GroundLift` (4 cm) above it. The picture is
exactly the flat sprite; the depth is that of a standing figure with its feet, or a corpse, lying on the
ground. Sorting against props, grass, other troops, received shadows, haze and depth of field all follow from
that. `BoundsScale` is 2 because the offset is not in the mesh bounds.

**Light.** Masked, lit, two-sided, specular 0, roughness 1. Colour = sheet colour with the team tint
(`lerp(c, c * TeamColor * 2, mask)`), then the hit flash. `Relight` splits it: `colour * Relight` is the base
colour, lit by the sun, sky and Lumen and shadowed by the world; `colour * (1 - Relight) * BakedLight` is
emissive, the baked look that is always there. The normal is the sheet's per-pixel normal turned into world
space through the view axes, blended toward one even normal (halfway between up and the viewer) by
`NormalStrength`. Tuned by eye in the level (Sovereign Feel > Visuals > Sprites): `Relight` 0.6,
`BakedLight` 3, `NormalStrength` 0.7. In full shade a troop is clearly darker and cooler than in the sun, but
loses less than the turf around it (the emissive share), which keeps it readable.

**Sampling.** `Sheet` is sampled bilinearly at a UV snapped to texel centres, each texel edge anti-aliased over
`EdgeSoftness` (0.5) screen pixels; mask and normal are point sampled at the texel centre. The frame's cell is
clamped, so a neighbouring frame never bleeds in.

**Shadow.** The exact caster would be the sun-view frame on a card facing the sun. Sliding every point of
that card along the light does not change the shadow it throws on flat ground, so the card may lie in any
plane through the feet. `USRBattleSubsystem::UpdateSpriteView` lays it in a plane leaning
`SpriteShadowLean` (78 degrees) from upright, away from the sun. Lying that low it cannot shade the troop's
own sprite (an upright card through the feet would darken the sprite's sun-side half) and the shadow stays
crisp along its whole length. The price: a troop's shadow only climbs about 20 cm up a neighbour or a wall.
The card's shadow cache invalidation is `Always`, because the silhouette changes with the frame.

### Frame selection

Facing row: `index = round(((FacingYaw - ViewYaw + 180) mod 360) / 45) mod 8` into S, SW, W, NW, N, NE, E, SE,
kept until the yaw is `FacingHysteresisDeg` (8) past a boundary. Frozen at death.

| State (first that applies) | Frame |
| --- | --- |
| dead | `death`: `floor(DeathClock / DeathAnimTime * 8)`, holding frame 7 (the corpse). The body is carried `DeathKnockDistance` along the killing blow while it falls; after `CorpseLingerTime` it dissolves over `CorpseFadeTime`. |
| not yet active | `spawn`: `floor(P * 6)` over `SpawnPopTime`, hidden before the unit's spawn delay; a scale pop (`SpawnPopAmount`) in the first half. The unit becomes active as the last (guard) frame ends. |
| wind-up | `attack`: the last wind-up frame whose `windup_phase_map` value is at most `PhaseTime / WindupTime`. |
| recovery | `attack`: the same with `recovery_phase_map`. `Strike()` runs on the frame recovery begins, whose frame is the authored strike (Shieldbearer 3) or release (Archer 5) frame; hit-stop holds it. Melee adds `MeleeLungeDistance` forward, easing back. |
| hit less than `HitAnimTime` ago, standing | `hit`: three flinch frames. Never shown over an attack or while running, and it changes nothing in the simulation. |
| moving faster than `WalkSpeedThreshold` | `walk`: `floor(frac(distance / WalkCycleDistance) * 8)`, where distance is the ground the unit actually covered since it started moving, so the feet do not slide. Each run starts on a contact frame, alternating feet. |
| otherwise | `idle`: `floor(AnimTime * IdleFps) mod 8`, each unit starting at a random point. |

On top: hit flash, hit squash (`HitSquash`), the acknowledge hop, hit-stop. The procedural breathing, walk bob,
lean, waddle, weapon swing and death topple are gone: the frames do that.

Because the card shows a 30 degree render at any camera pitch, a point at authored height H above the feet
appears where a world point at `H * cos(30) / cos(pitch)` would. The arrow origin (62 cm forward, 98 up, from
`archer.json`), the aim point and the pick capsule use that; health bars sit just above the sprite's top.

### Arrows

`ASRProjectile` draws `T_Arrow_Color` on `SM_ArrowCard`: the card's long axis is the flight direction and it
turns about that axis to face the camera, so the arrow foreshortens like a real shaft. `MI_ArrowSprite` is
`M_UnitSprite` with one 44 x 9 cell, the even normal and no billboard offset; the fletching takes the team
colour. A second, hidden card turned toward the sun casts its shadow. An arrow that misses stands in the
ground for 1.6 s and dissolves.

### Knobs (Project Settings > Game > Sovereign Feel, saved in `Config/DefaultGame.ini`)

| Where | Settings |
| --- | --- |
| Animation | `SpawnPopTime`, `SpawnStagger`, `SpawnPopAmount`, `IdleFps`, `WalkCycleDistance`, `WalkSpeedThreshold`, `FacingHysteresisDeg`, `MeleeLungeDistance` |
| Combat > Hit Reaction | `HitFlashTime`, `HitFlashColor`, `HitSquash`, `HitAnimTime`, `KnockbackDecayTime` |
| Combat > Death | `DeathAnimTime`, `DeathKnockDistance`, `CorpseLingerTime`, `CorpseFadeTime` |
| Visuals > Sprites | `SpriteRelight`, `SpriteBakedLight`, `SpriteNormalStrength`, `SpriteEdgeSoftness`, `bSpriteShadows`, `SpriteShadowLean`, `SpriteBlobStrength` |
| Units | `WindupTime`, `RecoveryTime` per troop: the attack frames follow them |

### Debug

`sr.Status` logs each unit's sprite cell (`sprite=attack:3:SE`). `sr.Fan [distance]` sends every player unit
off in its own direction, 45 degrees apart, to see all eight facings at once. `sr.ShotOn <strike|hit|death>
<name> [type] [team]` waits for that event, freezes the battle on that frame, centres the camera on the unit,
lets the image settle and saves `Saved/Screenshots/SR/<name>.png`; the log line names the cell on screen.

### Known limits

- The image is temporally anti-aliased, so a running troop is a little softer than a standing one, and the
  frame after a sprite frame change carries a trace of the previous one.
- The sprites are a 30 degree render shown at every pitch. At the far zoom (46 degrees) the figures stand
  slightly more upright than the ground they are on; judged acceptable at that size, so the sheets were not
  re-rendered (`Tools/blender/build_all.sh --elev N` if the camera changes).
- Shadows on other troops and on walls are short (see Shadow above).
- The sprite's below-pivot part is laid on a flat plane at the unit's ground height; on a ledge it overhangs.

## Buildings (castle, farm, mine)

Real 3D meshes modelled by script in Blender, textured with the same code-drawn pixel art at 4 cm per texel, lit by
the level like the terrain. How to rebuild them: `SourceArt/Buildings/README.md`.

### Pipeline (after steps 1-5 above; all re-runnable)

| Step | Command | Produces |
| --- | --- | --- |
| B1. Textures | `Tools/.venv/bin/python Tools/textures/gen_building_textures.py` | `SourceArt/Textures/T_Bld_*.png` (+ `_N`). Alpha is a mask: 0.6 = team-coloured or glinting texel; 0 = hole on card textures. |
| B2. Models | `Blender -b -P Tools/blender/build_building.py -- castle` (also `farm`, `mine`, `tower`, `barracks`, `range`, `rallyflag`; `--state site,damaged` for some states only) | `SourceArt/Buildings/SM_Bld_<Name>.gltf` and its states `_Site`, `_Damaged`, `_Ruin`, `<name>.json` (footprint, sockets; `states`), `blender/<name>.blend`, previews in `Saved/BuildingPreview/`. Kit: `Tools/blender/bldkit.py`; one module per building, `bld_<name>.py`. |
| B3. Import | `Tools/ue_py.py -c "PARTS=['textures']; TEX_PREFIX='T_Bld_'; exec(open(r'<repo>/Tools/import_world_assets.py').read())"`, then `ONLY=['building']` with `build_visual_materials.py`, then `Tools/ue_py.py Tools/import_buildings.py` | `/Game/SR/Textures/T_Bld_*`, `/Game/SR/Materials/M_Building`, `M_BuildingCard`, `MI_Bld_<slot>`, `/Game/SR/Buildings/SM_Bld_*`. |
| B4. Placement | `BUILDINGS` in `Tools/world/gen_battlefield.py` (step 2), then step 5, or only `PARTS=['buildings']` | `ASRBuilding` actors in the outliner folder `Buildings`. Step 2 also clears terraces and dressing under the footprints and paints packed earth, the castle court and footpaths into `T_Splat`. |

The editor's Python bridge now starts by itself (`Content/Python/init_unreal.py`). `Tools/editor.sh quit|build|start|rebuild`
wraps the C++ cycle; `Tools/pie.py start|run|shot|log|stop` drives PIE and the `sr.*` commands from the shell.

### Mesh and material contract

- Authored in Unreal cm, front (gate, adit, yard) toward local -X, origin on the ground. No collision on the mesh.
- UV0 in centimetres (walls: distance round the footprint, v = -z, so courses meet at corners). UV1.x = cm below the
  head of the wall (opaque slots) or sway weight 0..1 (card slots). Vertex colour R = baked shade.
- One material slot per surface, named `Bld_<slot>`, mapped to `MI_Bld_<slot>` at import. The table is
  `BUILDING_SLOTS` in `Tools/build_visual_materials.py`, mirrored by `MATERIALS` in `bldkit.py`.
- **Custom primitive data 0..2 = team colour** on the building's mesh component (`TeamColor`, masked by texture
  alpha 0.6 on slots with `TeamMask` 1: friezes, banners, awnings). The same assets serve both teams.

| Material | Parameters worth knowing |
| --- | --- |
| `M_Building` (opaque) | `Tex`, `Size`, `NormalTex`, `NormalStrength`; `TeamMask`, `TeamBoost`; `GlowMask`, `Glow` (gold ore glints); weathering in whole texels: `Damp`, `DampHeight`, `DampTint` (dark foot), `Bleach`, `BleachDepth`, `BleachTint` (pale wall heads, from UV1.x), `Moss`, `MossHeight` (creeps up from the turf, joints first), `MossTop`, `MossSlope` (turf on up-facing rock); `WorldTop` (world-aligned turf on the mine's ledges); `Tint`, `Roughness`, `Specular`. Height is measured from the actor origin. |
| `M_BuildingCard` (masked, two-sided) | `Tex`, `Size`, `TeamMask`, `Glow` (flames: emissive, flickering), `RootShade`, `UpNormal` (1 = lit like the ground: crops), `SwayAmount`, `SwaySpeed`. |

### The three buildings

| Asset | Footprint (blocks movement) | Height | Triangles | Notes |
| --- | --- | --- | --- | --- |
| `SM_Bld_Castle` | 1120 x 1320 cm | about 8.6 m roofs, 11.6 m with standards | 7,298 | Battered sandstone curtain, four towers, gatehouse with a 2.56 m gate, plastered upper hall. Sockets: `gate` (-600, 0), `rally` (-780, 800), `label`. |
| `SM_Bld_Farm` | 880 x 960 cm | 4.6 m | 3,937 | Barley field (card rows 32 cm apart), stubble with stooks, cottage, granary, haystack, cart, olives. |
| `SM_Bld_Mine` | 820 x 840 cm | 5.4 m, 6.9 m with standard | 2,757 | Stepped bluff in the terraces' own cliff / turf, timber adit, track and ore cart, awning with crated gold, windlass, spoil. |
| `SM_Bld_RallyFlag` | none | 2.1 m | 96 | The castle's rally marker. |
| `SM_Bld_Barracks` | 920 x 880 cm | 4.4 m ridge, 5.7 m armoury tower | 3,452 | Trains Shieldbearers. Stone-and-timber hall under terracotta tiles, armoury tower with frieze, walled drill yard: spear racks, practice posts, striped shields, awning. Sockets: `gate` (-520, 0), `rally` (-820, 0), `label`, `popup`. |
| `SM_Bld_Range` | 800 x 800 cm | 3.9 m ridge, 4.1 m with standard | 3,408 | Archery Range: trains Archers. Thatched bowyer's lodge with frieze, shooting line under a striped awning, three painted straw butts, bow rack, fletching bench, fenced yard. Sockets: `gate` (-460, -190), `rally` (-760, -190), `label`, `popup`. |

### Building states

Each building (castle, farm, mine, tower, barracks, range) is four meshes sharing origin, orientation and footprint;
`<name>.json` lists the three extra ones under `states`. How they are built: `SourceArt/Buildings/README.md`, "States".

| Mesh | When | Content |
| --- | --- | --- |
| `SM_Bld_<Name>_Site` | under construction, drawn round the finished mesh while it rises from the ground | Footings and packed earth on the footprint, an open pole scaffold with plank walkways and ladders up to wall height, stacked stone, timber, a lifting pole. Within the footprint + 60 cm. |
| `SM_Bld_<Name>_Damaged` | health below 50 % | The finished building with breaches, lost merlons, burnt roofs showing charred rafters, soot, fallen stone, torn banners and awnings. Same silhouette and team colour. |
| `SM_Bld_<Name>_Ruin` | destroyed | Wall stumps, rubble heaps, charred timbers, soot on the ground; at most a quarter of the finished height. |

Slots added for these and the two new buildings: `Bld_RoofTile` (opaque, terracotta pan tiles, has a normal map),
`Bld_Target` (opaque, the painted face of a straw butt, 128 cm, not tiled), `Bld_Char` (opaque, charred timber and
burnt thatch), `Bld_Scorch` (card, soot marks from an atlas: no sway, no team mask, `RootShade` 0).

Placed by `BUILDINGS`: player castle (-2000, -1300), mine (-2570, -2550), farm (-2500, 620); enemy castle (2250, -1100).

### Gameplay (what the code does with them)

- `ASRBuilding` (`Source/SovereignRealms/Buildings`): type, team, mesh, footprint, sockets. One WorldStatic box over
  the footprint blocks troops; ground and cursor traces ignore buildings. Selection outline: a rounded rectangle
  round the footprint (`USRRingComponent::BuildRoundedRect`).
- `USREconomySubsystem` (`Battle/SREconomySubsystem`): gold and food per team, building registry, payout popups,
  refusal feedback, `RoutePath` (waypoints round footprints; recruits and player move orders use it through
  `ASRUnit::OrderMovePath`). Stepped by `USRBattleSubsystem`, reset with the battle.
- Farms pay food, mines pay gold, on timers. The castle recruits for **food only**; gold is kept for buildings.
- Controls: click a building to select it (never box-selected); castle selected: `Q` Shieldbearer, `E` Archer or
  the panel buttons, right-click sets the rally point. HUD: resource bar top centre, building panel bottom centre,
  "+N" popups, a training bar over a working castle.
- Settings: Project Settings > Game > Sovereign Feel > Economy (`StartingGold`, `StartingFood`, `FarmFoodPerPayout`,
  `FarmPayoutInterval`, `MineGoldPerPayout`, `MinePayoutInterval`, `ShieldbearerCost`, `ArcherCost`,
  `ShieldbearerBuildTime`, `ArcherBuildTime`, `MaxRecruitQueue`, `BuildingRouteMargin`, popup / flash / outline values).
- Console: `sr.Give gold|food N`, `sr.Recruit shield|archer`, `sr.SelectCastle [farm|mine|enemy|none]`,
  `sr.Rally X Y`, `sr.Economy`. Log lines: `PAYOUT`, `RECRUIT queued / refused / ready`, `RALLY`, `ECONOMY`.
