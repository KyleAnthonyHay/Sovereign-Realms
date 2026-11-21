# Voxel village: how to build an asset

We are rebuilding the look of the game as a **Minecraft-like voxel diorama**, matching the owner's reference pictures as
closely as possible (ideally one-to-one). Everything is made of cubes with pixel-art textures: chunky stone blocks,
timber frames, green tiled roofs with stepped wooden barge boards, warm glowing windows and lanterns, green banners
with gold emblems, puffy trees made of leaf cubes. The engine supplies the light (low golden sun, glow, haze).

Project root: `/Users/kyle-anthonyhay/Documents/MY FILES/CODE/Games/Sovereign-Realms/VoxelLab` (paths below are relative to it).

## Read first
- `References/*.png` and `References/crops/*.png`: the owner's pictures. `village.png` is THE scene we are matching;
  the crops are 2x enlargements of parts of it. `barracks.png`, `castle.png`, `rocks.png`, `forest.png`, `king.png`
  are close-ups that show the style in detail. **Look at your references before you write any code, and again after
  every render.**
- `References/*.glb`: rough untextured meshes of some subjects (melted AI meshes: use only for proportions).
- `Tools/blender/voxlib.py` (the library: read all of it), `voxkit.py` (shared roofs, windows, doors, lanterns, banners,
  barrels, crates), `voxmats.py` (materials and the shared palette `PAL`), `test_style.py` (a small worked example) and
  its render `SourceArt/Previews/test_style.png`.
- `SourceArt/Previews/textures.png`: what the tiling textures look like.

## The model
- A model is one or more `voxlib.Vox` grids, joined with `V.join([...], "SM_Name")` into one mesh.
- **Voxel sizes** (one texel is 6.25 cm everywhere):
  0.125 m for buildings and props (4 voxels = one 50 cm "block"), 0.25 m for leaf cubes, 0.0625 m for pixel-art pieces
  (banners, emblems, small flowers), 0.5 m only for terrain. Grids of different sizes are joined with `.at(x, y, z, rot)`.
- **Axes**: +X right/east, +Y away/north, +Z up. A building's FRONT (door side) faces **-Y**. The mesh origin is the
  centre of the footprint at ground level (z = 0 is the ground it stands on) unless your task says otherwise.
- **Scale**: King David is 1.7 m tall. Doors about 1 m x 1.75-2 m, a storey about 2.5 m, a lantern post 1.25-1.5 m to
  the lamp. The reference is chunky and a little toy-like: when in doubt keep things compact and thick.
- Materials come from `voxmats.MATS`: stone, brick, cobble, grass, dirt, plank, beam (grain along X/Y), post (grain
  vertical), log (bark + end grain), roof, plaster, leaves, wheat, hay, wool, paint (any flat colour via `color=`),
  glow (lamp light; `color="lantern"`), window (glowing panes), metal, gold, moss, mossy_stone, ore, gravel, water.
  Any voxel can take a tint: `v.box(..., "paint", "#c23a2a")`, `v.box(..., "leaves", "#d8e8a0")` (the texture is
  multiplied by it; white = unchanged). Use `PAL` names where they fit ("banner", "gold", "cream", ...).
- Every connected lump of `glow` voxels becomes a real lamp in the engine automatically (the exporter writes their
  positions), so put glow exactly where light should come from: lantern boxes, forge mouths, mine lamps. Windows use
  `window` (they glow but are not lamps).

## Making it look right (this is where the quality comes from)
- **Chunky, not flat.** Real depth everywhere: frames stand proud of walls, sills stick out, roofs overhang, beams
  cross, stones swell (`v.chunky("stone", p=0.3)`), footings are wider than walls. No large flat untextured faces.
  The mesher bakes corner shading, so recesses and overhangs read strongly: use them.
- **Silhouette first.** Get the big shapes and proportions of the reference right before the details.
- **Detail density like the reference**: lanterns by the doors, flower boxes, vines (leaf voxels creeping up walls and
  hanging from eaves), moss on roofs and stones (`scatter`), barrels, crates, sacks, signs, banners, steps.
- **Colour**: warm and saturated: orange-brown wood, green roofs, warm grey stone, amber windows. Vary it (tints).
- Keep interiors solid (nobody goes inside), but doors/windows/arches are modelled in depth.
- Budget: aim under about 60k voxel faces per building and 30k per prop or tree (the exporter prints the count);
  repeated small things (fence pieces, flowers) should be a few hundred to a few thousand.

## Workflow
1. Write ONE script per task in `Tools/blender/assets/<task>.py` (create the folder if needed). It must start with
   ```python
   import os, sys
   sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
   import numpy as np
   import voxlib as V
   import voxkit as K
   from voxlib import Vox
   ```
   and be re-runnable from scratch:
   `/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python Tools/blender/assets/<task>.py -- [--no-render]`
   (parse `sys.argv` after `--`). One `build_<thing>()` function per asset returning the Blender object.
2. Export every asset with `V.export_gltf(ob)` (writes `SourceArt/Meshes/<ob.name>.gltf/.bin/.json`). Use exactly the
   asset names your task lists. Pass `collision="none"` for things the king walks through (leaves, flowers, grass, cloth,
   small clutter); everything else keeps the default (he walks on and bumps into the exact voxels).
3. Render previews with `V.render(path, target=..., az=..., el=..., dist=..., lens=...)` into
   `SourceArt/Previews/<task>_*.png` (Cycles, about 10-40 s; one Blender scene per render call: build the object(s),
   call `V.render`; call `V.reset_scene()` before building the next thing). `az` is the camera's position in degrees
   clockwise from the south: `az=28, el=32` is the village picture's view (front and right side visible).
   If the Metal kernels are still compiling, the first render can sit for several minutes: wait, do not kill it.
4. **Read your render and the reference side by side and fix what differs. Do at least four rounds of this per main
   asset**; also check a view from behind/the other side so nothing is unfinished. Stop when it holds up next to the
   reference at the same size, not when it merely runs.
5. Do NOT edit `voxlib.py`, `voxkit.py`, `voxmats.py` or `voxtex.py` (shared, others are using them at the same time):
   put any helper you need in your own script (you may copy a kit function and change it). Do not touch the Unreal
   project or other agents' files. If a shared file truly blocks you, work around it and say so in your report.

## Report back (short)
The asset names you exported with their size in metres and face counts, where their origin is, anything the scene
builder must know (which way it faces, where the door / path connects, how pieces are meant to be laid out), and the
preview PNG paths. Say plainly what is still weak.
