# Sovereign Realms

> **DEPRECATED: superseded by VoxelLab.** This first draft of Sovereign Realms (sprite troops on a lit terrain, C++ in
> `Source/SovereignRealms`) is no longer developed. The game now lives in [`VoxelLab/`](VoxelLab/README.md) (voxel
> diorama, Unreal 5.8), whose game logic was reimplemented from this code on 2026-11-21. Nothing here was deleted or
> moved, and this project still builds.
>
> **Ported** (rebuilt on the VoxelLab classes, see `VoxelLab/README.md`, "The battle"):
> teams and team colours; health, damage, death and the combat numbers (Shieldbearer = the Swordsman, Archer, buildings'
> health, archers' 0.35x against buildings) from `SRFeelSettings`, `SRUnit`, `SRBuilding` -> `VLBattle.*`,
> `VLSwordsmanCombat.*`, `VLArcherCombat.*`, `VLArrow.*`; the economy (farms' food and mines' gold every 6 s, stores,
> housing and the troop ceiling) and recruitment (costs, train times, no queue limit, batches of 5 / 10, rally points,
> recruits joining a platoon) from `SREconomySubsystem`, `SRBuilding` -> `VLBattle.*`; building levels (Citadel 1-7,
> watch tower, farm, mine, barracks / range, granary / treasury 1-3); the watch tower's and the castle's own archers;
> the enemy commander with Easy / Normal / Hard from `SRAISubsystem` -> `VLEnemyAI.*`; platoon stances from
> `SRPlatoonSubsystem` -> `VLCommand.*`; the game flow (match start, the castle falling ends it, the victory / defeat
> screen) from `SRGameFlowSubsystem`, `SRBattleSubsystem` -> `VLBattle.*`; the menus (main menu, New Game with map and
> difficulty, pause, settings, end screen) and the in-game HUD (resource bar, alerts, health bars, building panel,
> minimap) from `SRHUD*` -> `VLHUD.*`; the event sounds (recruit ready, attack alert, victory, defeat, UI click / error,
> hits, collapse, deaths, payouts).
>
> **Not ported: these remain only in this old code** (`Source/SovereignRealms`): the Builder and building construction
> (placement, sites, repair, demolishing, relics and old towers, the Relic and Siege Towers), the Scout, the Medic,
> the Catapult and the Siege Workshop, the Horseman (cavalry) and the Stable, the guard order, patrols, march-together,
> fog of war, saved games and the autosave, the power / battery-saver subsystem, the menu film, wildlife, birds, leaves,
> fire and the other sprite effects, the sprite pipeline and its tools, the four-kingdom map and the old maps.

A top-down fantasy RTS with compact kingdoms, responsive armies, and a detailed miniature world lit by mystical golden-hour sunlight.

This repository is the documentation and setup starting point for a fresh **Unreal Engine** project, with **Blender** for asset creation. It does not yet contain a playable game or an Unreal project. The earlier Unity/C# direction is superseded.

## Start here

1. Read [PLAN.md](PLAN.md), the authoritative design brief, including all three visual references.
2. Follow [SETUP.md](SETUP.md) for the Windows implementation handoff, local tools, Git LFS, and Windows/Mac workflow.
3. Establish a small visual sample and menu/HUD concepts before expanding the map and gameplay. Choose the implementation structure based on the actual engine and workflow.

The first playable has **one map, two troop types with multiple soldiers each, one buildable tower type, and automatic gold/food production from mines and farms**. It includes recruitment, construction, selection, movement, combat, and core animation states. No workers or full strategic enemy AI are required. Exact troop identities and recruitment location remain open.

Use one source project on Windows and Apple Silicon Mac, with the same exact stable Unreal version and compatible plugins. Engine version, new Mac specifications, and performance budgets have not been selected. Smooth 60 FPS is a measured target.

Local Claude Code with the user's intended Opus 5.5 model and an Unreal MCP connection is the planned implementation workflow; configure and verify it separately on each machine. This repository installs none of those tools.

The supplied screenshots are [third-party design references](references/README.md), not shippable game assets. Reference C is the approved menu/interface style direction; translate it into an original main menu and HUD.
