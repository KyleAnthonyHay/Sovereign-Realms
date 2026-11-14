# Interface

The whole interface (main menu, pause menu, victory / defeat screen, settings, controls, the in-game HUD) is
drawn by one class, `ASRHUD`, immediate-mode on the HUD canvas, in C++. There are no Widget Blueprints and no
Slate widgets; the only binary assets are three textures.

| What | Where |
| --- | --- |
| Frame, primitives (panel, text, icon, button, slider, tooltip), world-space feedback | `Source/SovereignRealms/Player/SRHUD.{h,cpp}` |
| In-game HUD panels | `Source/SovereignRealms/Player/SRHUDGame.cpp` |
| Menus and shared screens | `Source/SovereignRealms/Player/SRHUDMenus.cpp` |
| Palette and button ids | `Source/SovereignRealms/Player/SRHUDStyle.h` |
| Game state machine | `Source/SovereignRealms/Battle/SRGameFlowSubsystem.{h,cpp}` |
| The player's saved options | `Source/SovereignRealms/Common/SRUserSettings.{h,cpp}` |
| Icon atlas and title lettering (generated) | `Tools/ui/gen_ui_art.py` -> `SourceArt/UI/*.png` -> `/Game/SR/UI/` |
| Minimap base image (generated) | `Tools/world/gen_battlefield.py --minimap` -> `SourceArt/Textures/T_MinimapBase.png` -> `/Game/SR/Textures/` |
| Texture import | `Tools/ue_py.py Tools/import_ui_assets.py` |

## Look

Dark navy / charcoal translucent panels, a bronze edge with a thin gold rule and gold corner brackets, warm
parchment for body text and for tooltips (dark ink on parchment), gold for headings and highlights, team blue
and enemy red as accents. Icons are 16 px pixel art from one atlas, drawn point-filtered; the title is an
original chiselled-gold pixel face. Text is the engine's Roboto rendered through the Slate font cache at the
exact size asked for, so it is sharp at every scale.

Colours in `SRHUDStyle.h` (and every colour written in the HUD code) are sRGB, "as they should look"; the
primitives convert to linear on the way to the canvas.

## Scale

Everything is laid out in design units (pixels at 1080p) and multiplied by `UI`:

    UI = max(viewHeight / 1080, 0.8) * HUDScale      (HUDScale: Settings > Interface scale, 80..140 %)
    UI = min(UI, viewWidth / 1500)                   (the bottom row must fit side by side)

So 1440p and 4K are the 1080p layout at 1.33x / 2x; a 720p window lays out like 1600x900 with 14 px body text.
Use `U(designUnits)` for every size and position. Body text is 14-17 units, headings 22-32, never smaller than 13.

## Layout while playing

    +---------------------------------------------------------------------------+
    |              [ gold | food | population | clock | next wave ]     [?] [||] |
    |                        placement / attack-move hint                        |
    |                              alerts (newest first)                         |
    |                                                                            |
    |                               the battlefield                              |
    |                                                                 PLATOONS   |
    |  +---------+ [Z farm ]                                          1 ...      |
    |  | minimap | [X mine ] +--------- selection panel ---------+    2 ...      |
    |  +---------+ [C tower] +-----------------------------------+    3..6       |
    +---------------------------------------------------------------------------+

- **Resource bar**: gold and food (amount, income per minute; shakes red on a refused purchase, the icon swells
  when income lands), population `alive/cap` (+queued; amber at the cap), the match clock, and the enemy's next
  wave (dim, amber under a minute, pulsing red under 20 s). Hover for tooltips. Top right: Controls (F1), Pause.
- **Hints**: one line under the bar while placing a building or with attack-move armed.
- **Alerts**: `USREconomySubsystem::GetAlerts()` as plates with an icon and accent colour per kind; they fade in
  over 150 ms and out over their last second. The enemy-wave alert is larger and pulses. Alerts never block clicks.
- **Minimap**: generated base image, free gold veins, buildings (squares; the castles larger with a gold core),
  troops (dots; selected ones white), the camera's view of the ground (the four screen corners cast onto the
  focus plane and clipped), pings at alert locations. +X is up, +Y is right, like the camera. LMB (drag) moves
  the camera, RMB orders the selection there (or moves the rally point with a Barracks / Archery Range selected).
- **Build menu**: one tall Build button (B) beside the minimap opens a panel over the selection panel with three tabs,
  Economy (Farm, Gold Mine) / Military (Barracks, Archery Range) / Defence (Watchtower), each a card with icon, name,
  gold cost and its number key (1-6 while the menu is open; Tab changes tab, Esc closes). Unaffordable cards dim with a
  red price (a click then flashes the gold counter). Tooltip: what it does, what it trains or yields, cost, build time,
  health, placement rule. New building types appear by their `Category` in Sovereign Feel. While placing, the refusal
  reason follows the cursor.
- **Selection panel** (only with a selection): troops (portrait and count per type, average health, how many are
  fighting, command buttons Attack-move / Stop / Hold / Patrol / Stance / Form, and Disband for a platoon); a building
  (health and "badly damaged" below half, construction progress with Cancel, or the payout meter; a Barracks or Range
  shows its queue, its one recruit button and the rally hint; "Housing full" / "Queue full" states); enemies read-only.
- **Platoon panel**: six slots. A formed platoon shows number, kind icon, name, counts, health, a burning left
  edge while engaged, and four small buttons (formation, stance, "recruits join here", disband). Click selects, a
  second click within 0.35 s also centres the camera. Empty slots read "Ctrl+N to form". The header folds the panel
  away (remembered). A platoon whose troops all fall disappears with an alert.
- **World-space**: health bars (selected or recently hurt troops; damaged buildings), the box-select rectangle,
  "+N" payout popups, training progress over a working barracks / range, dashed ground lines for the selected troops'
  patrol route and the selected barracks' / range's rally point; round selected troops (up to 12), the merged
  outline of their line of sight (dashed blue) and archers' bow range (solid orange), keyed in the troop panel.
- **Top bar, enemy**: "Enemy ready in m:ss" until its first attack may leave, "Enemy watching" after, "Enemy
  attacking!" (pulsing red) while an attack or raid is out.

## Game states

`USRGameFlowSubsystem` (a world subsystem) owns the state; the HUD draws what belongs to it.

    MainMenu --New Game (difficulty)--> Playing <--Esc / pause button--> Paused
        ^                                 |  castle falls (+1.6 s)         |  Restart (confirm) -> Playing
        |                                 v                                |  Quit to main menu (confirm)
        +------- Main Menu ------------ Ended -- Play Again -> Playing <---+

- `EnterMainMenu()`: resets the battle, pauses the simulation, frames the Citadel; the controller drifts the
  camera slowly. Entries: New Game (Easy / Normal / Hard -> `AIDifficulty`), How to Play, Settings, Quit.
- `StartMatch(difficulty)`: sets the difficulty (-1 keeps it), `ResetBattle`, focuses between the Citadel and
  the troops. Restart and Play Again are the same call.
- `SetPaused(bool)`: **not** a world pause. It is `USRBattleSubsystem::SetSimPaused`: troops, buildings, the
  commanders, projectiles, workers and the battle clock hold still, while actors, input, sound, the interface
  and the debug command inbox (`Saved/SRCommands.txt`) keep running.
- `Ended`: entered 1.6 s after `USRBattleSubsystem::GetResult()` leaves `Ongoing`; the world keeps moving behind
  the screen. Stats come from `USRBattleSubsystem::GetStats()` (`FSRMatchStats`: recruited, troops lost,
  buildings built / lost, per team).
- Esc: cancel placement -> cancel attack-move -> clear selection -> pause; in a menu it closes the open
  sub-screen, then (pause menu) resumes. F1: the controls overlay while playing, the Controls screen in menus.

Settings (main and pause menu): five volumes, interface scale (applied when the slider is released), edge pan,
WASD pan. The game reads them from `USRFeelSettings` as always; `USRUserSettings` stores them per user in
`GameUserSettings.ini` (`Apply()` at start-up, `CaptureAndSave()` when the Settings screen closes).

## Input

There are no widgets, so nothing is focused and nothing eats keys. `ASRPlayerController` hands every mouse press
to `ASRHUD::OnMousePress` first:

- if a menu is up, or the press is inside a box registered last frame with `Block()` / `HudPanel()`, the press is
  queued and answered by the `Button()` that contains it during this frame's draw; the world never sees it;
- otherwise it is a world click as before (select, box, orders, placement).

While a menu is up (`IsModal()`), the controller swaps its mapping context for one with only the mouse buttons,
Esc and F1, so no hotkey, order, zoom or edge-pan gets through. Scripted input (`sr.Cursor`, `sr.Key`) goes down
the same path as a real mouse.

Layering: only one layer takes input at a time (`bInputOpen`); the in-game HUD is still drawn under a menu but
is inert.

## How to add a button

    const FBox2D Box(FVector2D(X, Y), FVector2D(X + U(58.f), Y + U(58.f)));
    Block(Box);                                              // only if it is not already inside a HudPanel()
    const FBtn B = IconButton(Box, SRId::Command + 6, ESRIcon::Swords, TEXT("K"));
    if (B.bHover) { SetTooltip(Box, TEXT("Title   [K]"), { TEXT("One line of help.") }); }
    if (B.bClicked) { Click(); PC->DoTheThing(); }

Give it an id nobody else uses this frame (`SRHUDStyle.h`, `SRId`). `Button()` is the bare hit-test (hover, press,
drag via `bHeld`); `ButtonFrame`, `IconButton`, `MenuButton`, `Slider`, `Toggle` build on it. A button inside
another clickable area (the platoon rows) must call `Button()` before its parent does.

## How to add an icon

Add a pixel map at the END of `ICONS` in `Tools/ui/gen_ui_art.py` (letters are the palette at the top; `t T u`
are team-coloured and get an enemy-red twin), add the same name at the end of `ESRIcon` in `SRHUD.h`, then

    Tools/.venv/bin/python Tools/ui/gen_ui_art.py
    Tools/ue_py.py Tools/import_ui_assets.py

The atlas holds 40 icons (8 x 5, twice); grow `ROWS` and the UV maths in `ASRHUD::Icon` together if it fills.

## Test commands

The game opens on the main menu. `Tools/pie.py start` sends `sr.StartMatch` for you (`--menu` keeps the menu).

| Command | |
| --- | --- |
| `sr.StartMatch [0\|1\|2]` | start a match now (easy / normal / hard), skipping the menus |
| `sr.Menu main\|play` | go to the main menu / start a match |
| `sr.Pause 0\|1` | resume / pause (pause menu) |
| `sr.KillCastle enemy\|player` | end the match: victory / defeat screen |
| `sr.Alert attack\|lost\|done\|wave\|pop\|info [X Y]` | push a test alert (with a position it pings the minimap) |
| `sr.WindowSize W H` | resize the game window so the view is W x H (scaling tests) |
| `sr.Cursor X Y` + `sr.Key LeftMouseButton tap` | click the interface (normalised view position) |
| `sr.Key Escape tap`, `sr.Key F1 tap` | Esc / the controls overlay |

Also: Sovereign Feel > Debug > Skip Main Menu, or the `-SRSkipMenu` command-line switch.

`Config/DefaultInput.ini` removes the engine's development binding of F1 (wireframe view) so F1 is free for the
controls overlay.
