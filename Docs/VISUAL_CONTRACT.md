# Visual contract — command & combat slice

What the gameplay code builds, what it expects from art, and where the seam is.
Gameplay owns behaviour and greybox shapes. The visual pass owns lighting, fog,
post-process, terrain shape and materials, and can restyle everything below
without touching C++.

## Map and game mode

| Thing | Value |
| --- | --- |
| Map | `/Game/Maps/L_Battlefield` (editor startup map and game default map) |
| Game mode | `/Script/SovereignRealms.SRGameMode` (global default) |
| Map contents | Dressed by the visual pass, see "Visual pass" at the end: outliner folders `Terrain`, `Props`, `Water`, `Lighting`. The open ground is at Z = 0; terraces step up from it. |
| Playable bounds | +/-3000 cm in X and Y around the origin (`MapHalfExtent` in Sovereign Feel). Camera focus and move orders are clamped to it. |
| Spawned at runtime | Units, arrows, order markers, camera pawn. The three grey test blocks (tag `SRGreyboxObstacle`) are switched off in `Config/DefaultGame.ini`; boulders in the map stand in the same places. |

The empty map was first made by `Tools/create_battlefield_map.py`; everything in it now comes from the
visual pipeline described under "Visual pass". Leave **Project Settings > Game > Sovereign Feel > Scenario >
Spawn Greybox Obstacles** off: the map has its own obstacles.

## Collision rules the gameplay depends on

Units have **no collision components**. They find the world with line traces
against the **WorldStatic** object type only:

- **Ground**: a vertical trace per unit per frame. Anything that should be walked
  on must be WorldStatic with collision (a Landscape, or static meshes with the
  default `BlockAll` profile). Units follow uneven terrain.
- **Walls**: a horizontal trace at knee height (`StepHeight` + 5 cm). Rocks,
  trunks and walls that should stop units need WorldStatic blocking collision.
  Ledges up to `StepHeight` (45 cm) are climbed, taller ones block, drops over
  `MaxDropHeight` (140 cm) are refused. Ramps connect terraces.
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

The sun travels toward screen right and slightly up-screen (actor rotation pitch -33, yaw 75; travel
direction about (0.22, 0.81, -0.54)). So the lit side of everything is its **screen-left** side, shadows
fall to the right and a little up-screen, and faces turned toward the camera sit half in warm grazing light,
half in cool sky fill.

## Actor classes

| Class | What it is |
| --- | --- |
| `ASRUnit` | One troop. Origin at the feet. `VisualRoot` scene component carries all animated parts. |
| `ASRProjectile` | Arrow, about 80 cm long (oversized for readability). |
| `ASROrderMarker` | Ground-click marker (two rings), lives 0.55 s. |
| `USRRingComponent` | Flat procedural ring used for selection, hover, target flash and order markers. |
| `ASRCameraPawn`, `ASRPlayerController`, `ASRHUD`, `ASRGameMode` | Camera, input, overlay (box select, health bars), rules. |
| `USRBattleSubsystem` | World subsystem that steps units and loads the materials below. |

## Material contract

Every greybox part gets its own dynamic material instance. The parent material
is looked up **once per play session**:

### Units, arrows, test blocks: `/Game/SR/Materials/M_UnitGreybox`

If the asset exists it is used; otherwise the code falls back to
`/Engine/BasicShapes/BasicShapeMaterial`.

| Parameter | Type | Meaning |
| --- | --- | --- |
| `Color` | vector | Albedo of this part (team colour for team-coloured parts, otherwise skin / steel / bronze / leather / wood). |
| `TeamColor` | vector | The owning team's colour, set on **every** part, for accents, rim light or outlines. |
| `HitFlash` | scalar 0..1 | 1 on the frame the unit is hit, fading to 0 over `HitFlashTime` (0.16 s). Blend toward white / emissive. |
| `Fade` | scalar 1..0 | 1 while alive; goes 1 to 0 while a corpse sinks. Use for opacity / dither fade. |

Notes:

- With the **fallback** material there is no `HitFlash` input, so the code fakes
  the flash by lerping `Color` toward `HitFlashColor`. With `M_UnitGreybox`
  present the code leaves `Color` alone and only drives `HitFlash`, so the
  material must implement the flash itself.
- The fallback is opaque, so `Fade` does nothing and corpses just sink.
- Parts are engine basic shapes (`/Engine/BasicShapes/Cube|Sphere|Cylinder|Cone`),
  one material slot each, all casting shadows.

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

## Silhouettes (for when real meshes replace the greybox)

- **Shieldbearer**: 44 cm radius, about 142 cm tall. Broad team-coloured torso,
  steel helm with a fore-and-aft crest, large round shield on the left arm,
  upright blade on the right (the tallest point, reads from above).
- **Archer**: 36 cm radius, about 134 cm tall. Slim leather body, team-coloured
  cape disc and pointed hood, tall bow in the left hand, quiver on the back.
- Team colours: player `(0.05, 0.22, 0.80)`, enemy `(0.72, 0.07, 0.05)` (linear),
  editable under Sovereign Feel > Scenario.

Animation is procedural (transforms on `VisualRoot` and `WeaponPivot`): spawn
pop-in, breathing, walk bob / lean / waddle, melee raise-swing-lunge, bow
draw-release, hit squash, order-acknowledge hop, death topple and sink.
Damage lands on the frame the swing reaches full extension (melee) or when the
arrow arrives (ranged).

## Visual pass (what exists now)

The look is "pixel-art textures on real 3D geometry, lit and lensed like a photographed miniature":
hand-pixelled textures at one texel density, chunky stepped terraces, a low warm sun with cool fill, lit
haze with light shafts past the focus point, bloom, and a tilt-shift band of sharp focus.

### Pipeline (all re-runnable, nothing is hand-placed)

| Step | Command | Produces |
| --- | --- | --- |
| 1. Textures | `Tools/.venv/bin/python Tools/textures/gen_world_textures.py` | `SourceArt/Textures/*.png`: drawn in code from small fixed palettes (placed blade marks, laid stone courses, set cobbles). Preview sheet in `Saved/TexturePreview/`. |
| 2. World | `Tools/.venv/bin/python Tools/world/gen_battlefield.py` | `SourceArt/Meshes/battlefield.gltf` (every static mesh), `SourceArt/Textures/T_Splat.png` (ground blend map), `SourceArt/World/layout.json` (placements), `Saved/WorldPreview/map.png` (top-down preview). |
| 3. Import | `Tools/ue_py.py Tools/import_world_assets.py` | `/Game/SR/Textures`, `/Game/SR/Meshes` (re-imports in place, deletes meshes the generator dropped). |
| 4. Materials | `Tools/ue_py.py Tools/build_visual_materials.py` | `/Game/SR/Materials` (graphs cleared and rebuilt in place, references survive). |
| 5. Level | `Tools/ue_py.py Tools/build_battlefield_visuals.py` | Rebuilds the outliner folders `Terrain`, `Props`, `Water`, `Lighting`. Anything placed by hand belongs in another folder. |

The offline steps need `python3 -m venv Tools/.venv && Tools/.venv/bin/pip install pillow numpy scipy shapely mapbox-earcut`
(the venv is git-ignored). The editor steps need `Tools/ue_py_bridge.py` running in the editor (see its
docstring). While a material is being rebuilt the log shows transient "Failed to compile ... missing input"
warnings; they are the half-wired graph and stop once the script finishes. To retune only the lighting:
edit `LOOK` in `Tools/build_battlefield_visuals.py` and run it with `PARTS=['lighting']`.

### Texel density: 4 cm per texel, everywhere

Every world texture is authored for **4 cm per texel** (a 128 px tile covers 512 cm; a 140 cm troop is 35
texels tall). The troop sprites are 4 cm per pixel, so they match one-to-one. Meshes carry UV0 in
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
| `T_Grass`, `T_GrassMoss`, `T_GrassDry` | 128 x 128 | Turf: authored blade marks laid like shingles; five close olive tones. Moss and straw variants take over tuft by tuft through the splat map. |
| `T_Dirt` (+`_N`), `T_Cobble` (+`_N`) | 128 x 128 | Packed earth with pebbles; old road stones in uneven rows. |
| `T_Cliff` (+`_N`) | 128 x 128 | Terrace face: a thin soil band under the turf, then coursed stone. v = depth below the turf. |
| `T_Lip` | 128 x 24 | The turf hanging over a cliff top (alpha 1 = grass, about 0.4 = its contact shadow). |
| `T_Rock` (+`_N`), `T_Sandstone` (+`_N`) | 64 x 64, 128 x 64 | Boulder skin; weathered ashlar for the ruin. (Their normal maps are imported but `M_Prop` does not use them yet.) |
| `T_Needles`, `T_Bark` | 64 x 48, 32 x 64 | One conifer bough tier (dark body, lit tips, ragged alpha rim); trunk. |
| `T_Tufts` | 96 x 24 | Sprite strip: tall grass, short grass, dry reeds (16 px cells), fern, flowers (24 px cells). |
| `T_Wood`, `T_LogEnd`, `T_Banner`, `T_Water` | 64 x 32, 16 x 16, 16 x 40, 64 x 64 | Planks, sawn log end, cloth banner, pond ripples. |
| `T_Splat` | 1024 x 1024 | Ground blend map over the world square with origin (-5600, -6144) and size 12288 cm: R = road (0 turf, 0.5 bare earth, 1 set stones), G = moss, B = dry straw, A = shade baked at cliff feet. |

### Materials (`/Game/SR/Materials`)

| Asset | Used for | Parameters worth knowing |
| --- | --- | --- |
| `M_UnitGreybox` | Units, arrows (contract above, unchanged) | Contract: `Color`, `TeamColor`, `HitFlash`, `Fade`. Look: `HitFlashColor`, `HitFlashGlow`, `RimStrength` / `RimExponent`, `ShadowLift`, `PaintSaturation`, `Roughness`. Masked with a temporal dither on `Fade`. |
| `M_SelectionRing` | Rings and order markers (contract above, unchanged) | Contract: `Color`, `Opacity`. Look: `Glow`, `DarkEdge`. Unlit, translucent, two-sided, drawn after depth of field so it stays sharp; depth-tested. |
| `M_Terrain` | Every `SM_T_*` mesh | Top faces (normal Z > 0.5): world-aligned turf, blended to moss / straw / earth / road stones texel by texel from `T_Splat` (never a soft blend). Side faces: `T_Cliff` by UV0 (u = distance along the outline, v = depth below the turf, cm), the turf lip over the top (`LipFraction` of the wall at most), darker at the foot (`FootShade`). World-space normal output from the `_N` maps (`NormalStrength`). `TexelSize`, `SplatRect`, `StoneRoughness`, `LipShadow`, `TintRange`, `Tint`. |
| `M_Prop` + `MI_Prop_Rock`, `MI_Prop_Sandstone`, `MI_Prop_Wood`, `MI_Prop_Log` | Boulders, standing stones, the ruin, fences, logs, stumps | UV0 in cm. `TexA` / `SizeA` where vertex colour B = 1, `TexB` / `SizeB` where it is 0 (log: ends / bark). `Moss` + `MossSlope`: turf on up-facing facets, a whole facet at a time. `FootShade`, `Tint`, `Roughness`. |
| `M_Foliage` | Conifers (`SM_Conifer_*`) | Masked, two-sided foliage shading with subsurface. Needles or bark by vertex colour B; UV1.x = baked shade (dark under each tier and at the base, lit toward the crown: `ShadeFloor`, `TipTint`), UV1.y = sway weight (`SwayAmount`, `SwaySpeed`). Per-instance random tint. |
| `M_Card` + `MI_Card_Banner` | Grass, fern and flower cards; the banner cloth | Masked, two-sided, normal forced to world up so a card is lit like the turf it stands in. UV0 is 0..1 into `Tex` (`Size` in texels). `RootShade`, `Tint`, sway. |
| `M_Water` | Pond | Two layers of `T_Water` sliding past each other a whole texel at a time (`ScrollTexelsPerSecond`), `Deep` / `DeepMix`, `Glint`. Opaque, low roughness, so Lumen reflects the haze. |

### Level contents

| Folder | Contents | Collision |
| --- | --- | --- |
| `Terrain/Ground` | 64 ground chunks covering X -5200..12600, Y -9600..9600 (the low camera sees far up-screen), with the pond cut out. | WorldStatic, blocks (render mesh used as collision) |
| `Terrain/FieldTerraces` | Twelve irregular terraces inside the field. Each starts with one or two **40 cm steps** units climb (`StepHeight` is 45); eight of them carry a taller bluff (60 to 100 cm tiers, with firs on top) that blocks. All clear of both spawn areas, the lane between them, the road and the blocking rocks. | WorldStatic; aprons walkable, bluffs block |
| `Terrain/Knolls` | Ten small blocking outcrops (96 to 140 cm) near the field edges, each with a fir or two. | WorldStatic, blocks |
| `Terrain/Plateaus` | Stepped plateaus framing the field: tall and many-tiered on the far side (+X, two ranks) and the flanks, one low step on the camera side so nothing hides the field. Each starts with a walkable 34 to 40 cm apron that may lap into the field; every taller tier stays at least 95 cm outside the +/-3000 bound. | WorldStatic, blocks |
| `Terrain/Backdrop` | Eight big simple hills at X 7000..12000 that only ever show through the haze. | WorldStatic |
| `Terrain/Shore` | The pond's bank wall and bed (far-left corner, X > 3150, outside the bound). | WorldStatic |
| `Props/Rocks` | Five blocking boulders: `Rock_Centre`, `Rock_East`, `Rock_West`, `Rock_SW`, `Rock_NE` (same positions and footprints as before). Each has one invisible convex box `<name>_Collision` (tag `SRBlocker`); the visible stone has no collision. Standing stones by the water. Instanced actors `Stones` (scree, outcrops) and `Deadwood` (logs). | Only the `_Collision` boxes |
| `Props/Ruin` | The landmark: a sandstone ruin by the lane at about (-560, -900) (two pillars, a broken wall, fallen blocks, standing stones, a banner pole), and a ruined gate where the road leaves the field at about (3560, 860). In-field pieces have `<name>_Collision` boxes. | Only the `_Collision` boxes |
| `Props/Foliage` | Instanced actors `Conifers` (about 380 firs, five sizes 4.3 to 12.5 m) and `Grass` (about 15,000 blade / fern / flower cards, no shadows). 24 firs stand inside the field off the lane; each has a 46 x 46 cm box `Fir_NN_Collision` (tag `SRBlocker`). Two stand just behind the player's start so their tops blur into the bottom of the opening view. | Only the `_Collision` boxes |
| `Props/Fences`, `Props/Logs` | Fence runs, stumps and logs along the road and behind the player's start. Dressing only. | none |
| `Water` | `Pond` at Z = -48. | none |
| `Lighting` | `Sun`, `SkyLight`, `SkyAtmosphere`, `HeightFog`, `PostProcess`. Values below. | n/a |

### Lighting, haze, post (the `LOOK` table in `Tools/build_battlefield_visuals.py`)

| Thing | Value |
| --- | --- |
| `Sun` | Movable directional, pitch -33, yaw 75, 11 lux, warm (255, 214, 165), source angle 1.8 for soft miniature-scale penumbrae, volumetric scattering 11 (the light shafts). Virtual shadow maps. |
| `SkyLight` | Movable, real-time capture of the `SkyAtmosphere`, intensity 7.5, cool tint (205, 225, 255), volumetric scattering 0.3 (low, so shadowed haze stays dark and the shafts show). |
| `HeightFog` | Density 0.55, height falloff 0.3, **volumetric** (albedo (255, 242, 224), scattering distribution 0.35, view distance 16000). Its start distance is driven by the camera, see "Haze". |
| `PostProcess` (unbound) | Manual exposure (bias -0.6, never adapts). Bloom 1.3 with a wide kernel and a lens-dirt mask (`T_LensDirt`, intensity 6), light lens flare, vignette 0.5, fringe 0.35, grain 0.12. Grade: saturation 0.9, contrast 1.0, shadow gain (0.88, 1.0, 1.12) = teal-cool, highlight gain (1.08, 1.0, 0.88) = warm, small positive offset so blacks are lifted, film toe 0.4 / slope 0.84 / shoulder 0.3. Motion blur 0. |
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
| `TiltShiftBlur` | 1.6 | Blur when fully zoomed out: blur-disc diameter, in % of screen width, of something infinitely far behind the focus point. Low, so the whole tactical view reads. |
| `TiltShiftBlurZoomedIn` | 1.5 | Same, fully zoomed in. With the close, low camera this gives strongly blurred foreground props and distance around a sharp band through the focus point. |
| `TiltShiftFocusOffset` | 0 | Moves the sharp plane nearer (-) or farther (+) than the focus point, cm. |
| `TiltShiftFstop` | 1.4 | Bokeh shape only. |

The focal distance is the camera-to-focus distance, so the sharp band follows pan and zoom. Do not add
depth-of-field overrides to a post-process volume: the camera's values win.

`Config/DefaultEngine.ini` `[SystemSettings]` adds `r.Lumen.ScreenProbeGather.DownsampleFactor=32`,
`r.DOF.Gather.RingCount=4`, `r.Tonemapper.Sharpen=0.5`, and for the shafts
`r.VolumetricFog.GridPixelSize=6`, `r.VolumetricFog.GridSizeZ=128`, `r.VolumetricFog.HistoryWeight=0.92`.
Do not set both `r.DOF.Scatter.*Compositing` cvars to 0: that removes the depth-of-field pass altogether.

### For the troop sprites

- **Density**: 4 cm per texel in the world; a sprite drawn at 4 cm per pixel needs no scaling.
- **Camera**: yaw 0 always; pitch -30 (zoomed in) to -46 (zoomed out), -38 at the default zoom; FOV 50
  horizontal. A card that faces -X and leans back about 38 degrees from vertical faces the default camera.
- **Light**: key from screen left, slightly from behind the camera, 33 degrees up, warm; cool sky fill.
  Shadows fall to screen right and a little up-screen, about 1.5 times the caster's height long.
- **Recommended**: keep sprites in the opaque / masked pass (lit, masked, not translucent), so depth of
  field, haze and cast shadows treat them like everything else, and give them a fixed world-space normal
  (about halfway between up and toward the camera) so a whole sprite takes the warm key or the cool shade
  evenly instead of shading as a flat card. Sample with the same anti-aliased texel filter (`SRPix.S`) to
  avoid crawl. A camera-facing card is edge-on to this sun, so cast the shadow from a second, shadow-only
  card turned to face the sun (yaw about -105), or use a blob. `M_UnitGreybox` and `M_SelectionRing` are
  untouched and still honour the contract above.
