# Gameplay Proposal: First Playable

Status: **proposal for review**, not approved. It answers the gameplay questions [PLAN.md](../PLAN.md) leaves open, within the first-playable scope. Nothing here adds troop types, buildings or systems beyond that scope. Numbers are starting values for playtesting and should be tuned with data, not defended.

Units: 1 tile = 2 m = 200 Unreal units. Times are in seconds.

## 1. Troop identities

| | **Shieldbearer** (melee) | **Slinger** (ranged) |
| --- | --- | --- |
| Role | Holds the line, protects ranged units, takes buildings down | Damage from behind the line, punishes unprotected melee |
| Look | Bronze-rimmed round shield, short spear, faction-coloured tunic and crest | Linen tunic, faction sash and headband, leather sling, stone pouch |
| Health | 120 | 65 |
| Damage / attack interval | 12 / 1.1 s (10.9 DPS) | 8 / 1.5 s (5.3 DPS) |
| Range | 0.5 tile (contact) | 6 tiles |
| Sight / auto-acquire | 7 tiles | 8 tiles |
| Speed | 3.0 tiles/s | 3.3 tiles/s |
| Damage vs buildings | ×1.5 | ×0.5 |
| Cost / recruit time | 35 gold, 40 food / 7 s | 30 gold, 50 food / 8 s |

The slinger fits the setting's subtle biblical theme without naming anyone.

**Why these numbers.** Time-to-kill (TTK) is health divided by the attacker's DPS:

| Attacker → target | TTK |
| --- | --- |
| Shieldbearer → Shieldbearer | 11.0 s |
| Shieldbearer → Slinger | 6.0 s |
| Slinger → Shieldbearer | 22.6 s |
| Slinger → Slinger | 12.3 s |

Slingers lose a straight fight to melee that reaches them. They win when the melee has to cross 6 tiles under fire: at 3 tiles/s that is about 2 s, or 10.6 damage per slinger. A front line of shieldbearers with slingers behind it is the intended composition, and readable at tactical zoom.

**Damage timing.** Damage applies on the animation's contact frame (spear thrust) or when the projectile lands (stone), never on the order. A hit reaction plays at most once per 1.5 s per unit and never cancels a move or attack order.

## 2. Recruitment location: the Keep

Each side starts with a **Keep**. The Keep recruits both troop types, through a queue of up to 5 with a progress bar and a rally point. This meets PLAN's rule to avoid adding buildings just to recruit. A dedicated barracks can come later if a second production site turns out to be needed.

## 3. Buildings and economy

| Building | Footprint | Cost | Build time | Health | Output |
| --- | --- | --- | --- | --- | --- |
| Keep (starting, not buildable) | 3×3 | n/a | n/a | 2000 | 4 gold + 3 food / 5 s; recruits troops |
| Gold mine | 2×2 | 120 gold (+20 per mine already owned) | 12 s | 500 | 10 gold / 5 s |
| Farm | 2×2 | 70 gold | 9 s | 350 | 9 food / 5 s |
| Watchtower | 2×2 | 130 gold, 20 food | 15 s | 650 | 9 damage / 1.2 s, range 7.5 tiles, auto-targets |

Placement rules:
- Snaps to the grid.
- Every cell must be flat, open, buildable ground.
- The building must be within **10 tiles** of one of your existing buildings (your territory).
- There must be no enemy troops on the footprint.
- The preview is green when valid and red when not. When red, it states the reason (blocked, outside territory, can't afford).
- Under construction, the building rises from its foundation and gains health as it builds.

"Gold mines can be built anywhere suitable" is read here as any valid footprint. The +20 gold for each extra mine is a soft cap, so stacking mines is not automatically the best play.

**Pacing check:**
- The starting Keep alone yields 48 gold and 36 food per minute.
- A mine yields 120 gold per minute, so it pays for itself in about 60 to 75 s.
- A farm yields 108 food per minute.
- Recruiting nonstop from one Keep costs about 300 gold and 340 food per minute (Shieldbearers every 7 s). Two mines and three farms (288 gold, 360 food per minute) sustain that. A player should reach it around minutes 4 to 5. That is the point where economy decisions give way to army decisions.

Starting resources: 300 gold and 200 food. That is enough for one farm plus one mine, or a fast tower.

## 4. Opposing force and win rule

Scope is a minimal scripted opponent, not a strategic AI:
- The enemy starts with a Keep, one Watchtower and 4 troops (2 of each type) guarding the Keep.
- The enemy does not build. Its Keep releases attack waves on a timer:
  - wave *n* arrives at 150 + 75 × (n − 1) s
  - wave *n* has 3 + 2n troops, two shieldbearers for every slinger
  - waves attack-move toward the player's nearest building
- **Victory:** destroy the enemy Keep. **Defeat:** lose your Keep.
- One difficulty knob for tuning: a wave-size multiplier (0.75 / 1.0 / 1.25).

## 5. Commands in the first playable

These come from PLAN: select individually or in groups, move, attack, stop.
- **Selection:** click, shift-click, drag box, double-click for all of a type on screen, and control groups (Ctrl/Cmd + number).
- **Right-click:** moves on ground and attacks on an enemy.
- **Group moves:** troops spread into a block formation at the destination, shieldbearers in front and slingers behind.
- **Idle troops:** they auto-acquire enemies in sight and fight back when hit.
- **Move orders:** they ignore enemies until the troops arrive, so the player can retreat.
- **Not included:** patrol, hold or defend, and advanced formations, which PLAN puts in later phases.

## 6. Unit budget

- Population cap: 30 per side. The tested load is therefore up to 60 troops, plus about 15 towers and projectiles.
- Raise the cap only after measuring 60 FPS in a packaged Mac build with that load, as PLAN step 6 requires.

## 7. Proposed technical shape (Unreal)

This is a proposal, to confirm once the engine is installed:
- **C++ simulation layer:**
  - world subsystems for the economy, the construction grid, and the queues for recruitment and waves
  - unit combat state and order handling in a component
- **Data:** troop and building stats in `UPrimaryDataAsset`s, so balance is tuned without code changes.
- **Movement:** Unreal NavMesh with Detour crowd avoidance for movement and local separation, plus formation slot assignment in C++. A custom grid A* is only worth writing if crowd behaviour falls short at 60 units.
- **Blueprints and art:** Blueprints and assets handle presentation: animation blueprints, Niagara, materials and UMG.
- **Rendering:** lighting, materials, post-processing and effects are a separate track (golden hour, Lumen evaluation, fog and light shafts). They do not block this gameplay layer.

## Decisions requested

1. Shieldbearer and Slinger as the two troop types?
2. Recruit from the Keep (no barracks in the first playable)?
3. Scripted waves against an enemy Keep as the opposing force, with "destroy the Keep" as the win rule?
4. Starting numbers above, or different pacing (faster or slower games)?
