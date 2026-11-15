# Mountain height grids (`peak_<n>.npy`)

Made here, by `Tools/blender/build_mountains.py`: nothing in this folder was downloaded. Each grid is 97 x 97 heights
(0..1) that `Tools/world/gen_battlefield.py` turns into a faceted backdrop mountain (`SM_T_Peak_*`).

| What | Tool | Source | Licence |
|---|---|---|---|
| The shape: ridged / hetero / hybrid multifractal noise, then hydraulic and thermal erosion | [A.N.T. Landscape](https://extensions.blender.org/add-ons/antlandscape/) 0.2.0 (`mesh.landscape_add`, `mesh.eroder`), a Blender extension by Jimmy Hazevoet and contributors | extensions.blender.org, installed with `Blender --online-mode --command extension install antlandscape --enable` | The tool is GPL-2.0-or-later. It is not shipped with the game and its output (these grids) carries no licence: they are this project's own. |
| Blender 5.3 | Blender Foundation | blender.org | GPL (tool only) |

## Considered and not used

| Candidate | Why not |
|---|---|
| Kenney nature and castle kits, Quaternius nature and ruins packs (all CC0) | Flat-colour low-poly models with their own palettes and smooth gradients. The field is 4 cm pixel-art texels on generated meshes with UVs in centimetres (`Docs/VISUAL_CONTRACT.md`); these would need re-texturing and would still read as another game. The ruins, watch posts, stone circles and the fallen bridge are generated in the house style instead (`build_structure_meshes` in `gen_battlefield.py`). |
| ambientCG rock and cliff sets (CC0) | Same use as the two Poly Haven photos (crushed to the palette); two sources were enough. |
| Poly Haven HDRIs and rock models | The sky is the engine's atmosphere; photogrammetry rocks do not survive the texel budget. |
| Blender extension "Erosion terrain generator" | A.N.T. Landscape's own eroder did the job. |
