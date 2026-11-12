# Sovereign Realms

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
