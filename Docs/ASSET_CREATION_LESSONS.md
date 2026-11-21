# King David lessons for characters and buildings

Use the supplied mesh as the starting point when the owner intends it to be the base. Inspect its contents, compare it with the reference, and identify what needs repair before choosing to rebuild it. Match the camera and major proportions before adding detail or producing a full asset set.

These lessons come from the November 20, 2026 T3 Code conversation, **Build Walkable Stylized Medieval Village**, the saved King David comparisons, and the VoxelLab source files. The parent conversation still showed work in progress during review. A reported improvement is not final visual approval.

**The supplied mesh was incomplete as a textured asset, but it was not ignored throughout the whole process.** The saved [King David GLB](../VoxelLab/References/king.glb) contains positions and normals, one plain gray material, and no images, textures, UV coordinates, vertex colors, skin, or animation. Those contents were checked directly. The thread initially describes the meshes as untextured shapes. It later tried preserving the character geometry and projecting colors from the reference image through [king_paint.py](../VoxelLab/Tools/blender/king_paint.py) and [king_tripo.py](../VoxelLab/Tools/blender/assets/king_tripo.py).

The thread reports that projection made the face muddy. The [saved comparison](../VoxelLab/SourceArt/Previews/king_t_sheet.png) also shows uneven color patches and weak facial detail. One photograph cannot supply reliable detail for every side of a model. A complete textured export is worth requesting before another painting or reconstruction attempt, but it still needs inspection. Missing texture data alone does not establish that the geometry must be discarded.

**The asset brief pushed the work toward rebuilding.** The existing [asset brief](../VoxelLab/Tools/blender/ASSET_BRIEF.md) describes the GLBs as rough meshes to use only for proportions, then directs builders to construct voxel grids. That guidance limited how the supplied geometry could be used. Future briefs should state whether each mesh is the base to preserve, a proportion reference, or a candidate requiring inspection. Any proposed replacement should show what the original cannot support and a comparison of the alternative before a full rebuild.

| What happened | Lesson for the next asset |
| --- | --- |
| The character repeatedly looked too blocky. Later, the owner also objected to four small blocks replacing one larger shape. | More and smaller cubes are not a universal fix. Choose block sizes by form. Preserve broad armor plates, facial planes, beams, and roof masses. Use smaller pieces where the reference has finer structure. |
| The mixed-size rebuild used slabs and strips, micro-bevels, and small accent pieces. | Treat mixed shapes as a useful technique, then compare the result. The [saved rebuild comparison](../VoxelLab/SourceArt/Previews/king_b_compare.png) still differs in fur, cape, pose, and proportions. It is not proof of a finished match. |
| The reference and comparison showed different viewing sides. Later camera changes revealed layout and scale differences. | Establish the viewing side, elevation, perspective, framing, and ground level before judging sizes or moving buildings. Compare at the same displayed scale. |
| Buildings had low walls and oversized roofs. The barracks showed too much roof and side. | Measure wall-to-roof proportions and building orientation separately. Extra surface detail cannot fix a squat silhouette or the wrong facade facing the camera. |
| Paths, lanterns, and layout felt wrong despite having the right general subjects. | Model the relationships. Paths sit slightly below the grass. Lanterns need the reference's slender proportions and must leave travel lanes open. Check empty space between buildings as carefully as the buildings themselves. |
| Armor and gold looked dark after import. | Compare the same asset in Blender and Unreal before repainting or remodeling it. Inspect material assignments, vertex colors, color conversion, normals, exposure, and lighting to isolate the cause. |
| The first packaged character walked sideways, and the owner had trouble exiting the game. | A successful build and spawn log do not establish a playable result. Check facing, walking, turning, input focus, the menu, and quitting in the packaged app. |
| The scabbard search found a clear position outside the arm, but the owner wanted it against the hip. | Establish the intended anatomical attachment first. Solve clearance around that location. An algorithm can satisfy collision constraints while producing the wrong design. |
| Sword placement required changes after the character was already in the scene. | Decide early which pieces move independently. Give the sword, sheath, limbs, and cape explicit attachment points and pivots. Check the full walk and attack motion, including draw and sheathe states. |
| Several parallel asset tasks hit rate limits after exporting initial versions. | Keep “exported,” “visually reviewed,” “approved,” “imported,” and “tested” as separate states. An interrupted refinement pass leaves unfinished assets even when files exist. |

**Match the character through proportions and materials together.** For King David, the owner's notes singled out head and neck separation, crown height, waist taper, leg and forearm length, cape flare, fur shape, and eyes. These are character-specific targets, not measurements to impose on every future unit. Record equivalent targets for each new character before modeling.

The rebuild's [generator](../VoxelLab/Tools/blender/assets/king_b.py) merges same-color regions into larger boxes and separates cloth, gold, metal, and fur material slots. This is a concrete improvement over treating every region as identical small cubes. Micro-bevels help edges catch light, but bevels and studio lighting cannot compensate for incorrect proportions. Keep presentation renders and gameplay renders as separate checks.

**Use a short approval sequence for the next character or building.**

1. Inventory the supplied files. Record mesh identity, textures, materials, UVs, vertex colors, scale, orientation, and any rig or animation. Open the supplied mesh beside the reference.
2. State the intended treatment. Preserve and repair the mesh, retopologize it, or propose a rebuild. Explain the reason for the choice. Keep the original file intact.
3. Set up a comparison camera. Match the reference's visible side and perspective. Use the same framing for later comparisons so camera changes do not hide geometry changes.
4. Review major forms before detail. For a character, compare height, head, torso, limbs, cape, and equipment. For a building, compare footprint, wall height, roof height, overhangs, door size, and front orientation.
5. Build a representative section. Check a face and armor section, or a wall, roof, and doorway, before repeating the technique across the asset. Compare block size, edge treatment, palette, and material response.
6. Plan integration. Record pivots and moving parts for characters. Record ground origin, entrances, steps, collision, placement space, and connections to paths for buildings. The [King importer](../VoxelLab/Tools/ue/import_king.py) already documents the Blender-to-Unreal axis and unit conversion; reuse that convention consistently.
7. Review front, side, back, and motion where relevant. Confirm that equipment stays in the intended position and moving parts have enough clearance. A single attractive angle is insufficient for an asset the player can walk around.
8. Inspect in Unreal under the gameplay camera and lighting. Check appearance and scale against neighboring assets. At army scale, judge group ownership, selection, movement, and battle state. Individual detail can become visible at closer zoom without requiring every soldier to be identifiable at every distance.
9. Test the packaged result. Verify basic interaction and record performance for the tested scene and machine. Label editor and packaged measurements separately.
10. Record the chosen version and remaining differences. Save the comparison images and the owner's approval status. Complete one representative asset before producing many variants.

**Keep the next brief small enough to finish.** Establish one accepted character and one accepted building before expanding the set. When work is delegated, limit concurrent asset production to what the machine and service limits can sustain. Each handoff should identify the source mesh, reference, chosen camera, exported files, review state, and unfinished items. The thread's comparison of two model-generated versions establishes a preference for this particular character, not a general ranking of the models.

For vegetation, the owner's current direction is rigid trunks with wind in foliage, grass, flags, and detached effects. Reserve paths and entrances before placing decorative objects. For a large battlefield, assess the scene with groups moving through it as well as in a still image.

This guide captures the lessons for the next asset kickoff. The running T3 Code conversation, generators, and existing asset brief were not changed during this review. Reconcile that brief's older mesh and voxel constraints with the chosen approach before using it for the next batch.
