# Realm v2 — terrain plan (owner's brief, 2026-11-22)

A new battlefield, **Realm v2** (level `L_RealmV2`). The original Realm (`L_Realm`) stays as it is and separate.

## References
- `layout_annotated.png` sets the strategic placement and the geography: bases, mines, towers, contested zones,
  buildable areas, the rivers, bridges, the central mountain and the ruins plateau.
- `visual_inspiration.png` sets the look.

## Scale
- Fable decides the map's size and elevations, based on the actual sizes of the characters and buildings.
- The central mountain must feel colossal. It towers over soldiers and settlements, has a broad footprint and has
  several substantial peaks.

## Terrain character
- High peaks, deep valleys and ravines, and sharp rocky cliffs, with gentler slopes for the approaches uphill.
- Broad terraces and open areas for building, to support gameplay.

## Research (it informs the terrain maths; using the libraries themselves is optional)
- Luanti's Carpathian map generator, as a reference for shaping mountains.
- FastNoiseLite, for layered noise and domain warping that give natural variation.

## Constraints
- Variation stays within the planned geography, keeping the strategic locations and routes.
- Mines sit physically inside hillsides or mountains.
- No additional major mountain ranges.
- The standing rules in `VoxelLab/README.md` all apply:
  - no hard edges on open ground;
  - no coarse LODs at the distances the game is played at;
  - the original tree set;
  - mines are pre-placed per map and never built;
  - islands, where there are any, are big enough to build on.

## The owner's answers (2026-11-22)
- **Mines:** five in all. The **W** mine is the player's home mine and the **NE** mine is the enemy's home mine.
  The **NW**, **centre-east** and **SE** mines are neutral; a Builder claims them in place.
- **Watch towers:** both arrangements, so each side has two towers:
  - one beside its home mine, as on the Realm;
  - one on its own hill as drawn, **W** for the player and **E** for the enemy.
- **Contested zones** (the north crossing, the south crossing and the central ruins plateau): terrain only for now,
  shaped as strategic ground (chokepoints and high ground). No capture mechanics.
- **Each side starts with:** its castle, its home mine, its towers, the hero and one Builder. No farm and no
  cottages.

## Delivery
- A fixed, editable Unreal level. Procedural techniques are used while developing it.
- Fable owns the artistic composition and the implementation choices.

## Who does what
- **Fable 5.2:** the map design, terrain and art.
- **Opus 5.5:** testing movement and gameplay on the map.

## Housekeeping
- The **Town** (`L_Town`) and **Village** (`L_VoxelVillage`) maps are removed from the game. Any code that other
  maps still import, such as `town_layout.py`, stays.
