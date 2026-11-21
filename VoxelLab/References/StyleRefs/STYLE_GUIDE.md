# Sovereign Realms: voxel style guide

For prompting AI image generators so new art matches the game. Attach two or three of the PNGs in this folder as image
references (a character three-quarter view plus a building three-quarter view works best) and use the prompt template
below. The renders come from `Tools/blender/render_style_refs.py`; the scene we match is `References/village.png`.

## The look in one line
A warm, cosy, Minecraft-like **voxel diorama**: everything is built from cubes with crisp pixel-art textures, seen from
a high three-quarter RTS angle under a low golden sun. Chunky and a little toy-like, never realistic and never smooth.

## Blocks and shapes
- **Mixed block sizes.** Big structural blocks (a 50 cm "block" made of 12.5 cm voxels) carry small detail blocks:
  6 cm pixel pieces for emblems, trim, studs, flowers and faces. It is *not* a uniform grid of tiny cubes and *not*
  one big blocky mesh: large readable masses with small stepped detail on top.
- **Real depth everywhere.** Frames stand proud of walls, sills and eaves overhang, beams cross, roofs step out in
  terraced rows, stone walls swell with blocks sticking out irregularly, footings are wider than walls.
- **Stepped silhouettes.** Curves and slopes are staircases of cubes (roof edges, capes, tree crowns, the windmill cap).
- **Lived-in detail.** Ivy and leaf voxels creeping up walls, moss specks on stone and roofs, tiny pixel flowers at
  the base, lanterns by doors, barrels, crates, hay, awnings, banners.

## Palette
- **Olive and leaf greens**: roof tiles, capes, banners, foliage (`#2f6b25` banner green, `#4f861c`-`#a4d23c` leaves).
- **Warm timber**: orange-brown planks and beams (`#a8682a`, dark `#6a4220`, light `#c88a3c`).
- **Grey stone**: warm light-grey cut and rubble stone with mossy specks.
- **Gold trim**: crowns, buckles, emblems, trim edges (`#e9b62c`, light `#f8d75a`).
- **Cream cloth**: tunics, awnings, sails, fur, canvas (`#eadfc0`, `#e6d7a6`).
- Accents: amber glowing windows and lanterns (`#ffb347`), iron/charcoal (`#4c4a50`, `#2a2622`), warm brown skin
  (`#b06a3a`), white wool, red-and-white targets.
- Saturated and warm overall, with no neon, no cold blues except water and steel.

## Materials
Each cube face carries a small pixel-art texture (nearest-neighbour, visible texels, a little noise and edge variation)
multiplied by a flat tint, plus baked corner shading in the creases. Wood has grain lines, stone has mortar joints and
chips, roofs have tile rows with lighter mossy patches, cloth is flat and soft. Glass is glowing amber panes. Metals are
flat iron grey; gold is a flat warm yellow-orange. There are no glossy or reflective surfaces.

## Architecture
- **Roofs**: steep green tiled roofs in stepped rows with lighter moss patches, edged with **stepped timber barge
  boards and timber trim with dark iron studs**; ridge beams, flag poles and stone chimneys on top.
- Walls: stone or rubble footings, cream plaster or timber boarding above, a dark timber frame, glowing amber windows
  with timber frames and flower boxes, heavy plank doors with iron bands.
- **Banners**: hanging green banners with a swallow-tail or notched bottom and a **gold tree emblem** (the realm's
  sign); unit buildings use gold crossed swords or crossed arrows on the same green.
- Small square plots: fenced yards, wheat fields, vegetable beds, cobbled paths, lantern posts on stone feet.

## Characters
- **Chunky heads** (large, square, about a quarter of the height), **stocky bodies**, short thick legs, big blocky
  hands and boots. Simple pixel faces: dark square eyes with a white highlight, a block nose, heavy brows.
- Layered clothing built from blocks: a dark tunic or jerkin, green cape stepping down in panels with gold-trimmed edges,
  cream fur or cloth collars, brown leather belts and straps, gold buckles and studs.
- King David: gold crown, cream fur mantle, green cape, sword. Swordsman: curly dark hair and beard, cream padded tunic, brown leather, green cape, sword.
  Archer: green shoulder mantle and cape, cream tunic, bushy hair, longbow and a quiver of white-fletched arrows.

## Lighting and mood
Warm **golden-hour** light: a low warm sun with long soft shadows, cool soft fill, glowing amber windows and lanterns,
a little haze. In the game it is a cosy late-afternoon diorama; the reference renders here use an even warm studio
light on a grey backdrop so the colours read truthfully.

## Camera
High RTS three-quarter view: about 35 degrees down, from the front-left, slight perspective. Characters: full figure,
three-quarter front view.

---

## Prompt template (paste and fill the brackets)

```
[SUBJECT, e.g. "a blacksmith's forge with an open workshop and anvil"], in the style of a cozy Minecraft-like voxel
diorama. Built entirely from cubes of mixed sizes: large chunky blocks with small pixel-sized detail blocks on top,
crisp pixel-art textures on every face, stepped blocky silhouettes, real depth (overhanging eaves, protruding beams,
uneven stone blocks). Palette: olive and leaf greens, warm orange-brown timber, warm light-grey stone, gold trim,
cream cloth, glowing amber windows and lanterns. Steep green tiled roof in stepped rows with moss patches, stepped
timber barge boards and timber trim with dark iron studs, stone footing, cream plaster walls with dark timber frames,
green banner with a gold tree emblem, ivy and moss creeping up the walls, small pixel flowers, barrels and crates.
[For characters: chunky oversized square head, stocky short body, blocky hands and boots, simple pixel face, layered
blocky clothing with a green cape and gold trim.] High three-quarter isometric RTS view about 35 degrees down from the
front-left, warm golden-hour sunlight, soft long shadows, cosy fantasy medieval village mood, game asset, centred on a
plain light-grey background, whole subject in frame.
```

## Negative prompt

```
smooth surfaces, realistic, photorealistic, high-poly, rounded edges, bevels, curved geometry, uniform tiny cubes,
micro-voxels, low-detail flat blocks, blurry or smooth textures, painterly brush strokes, anime, cel-shaded outlines,
glossy plastic, metallic reflections, neon colours, cold blue lighting, night, dark gloomy, sci-fi, modern, cluttered
background, text, watermark, cropped, cut off, multiple views, tilted horizon, fisheye
```
