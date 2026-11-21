# Port audit: orders, unit behaviours, selection and their interface

What the first version (`../Source/SovereignRealms`: `SRPlayerController`, `SRBattleSubsystem`, `SRPlatoonSubsystem`,
`SRUnit`, `SRHUD*`; `../Docs/GAMEPLAY.md`, `../Docs/UI.md`) had for commanding units, set against this game
(`Source/VoxelLab`: `UVLCommand` in `VLCommand.*`, `UVLBattle` in `VLBattle.*`, `AVLKing` in `VLKing.*`, `AVLHUD` in
`VLHUD*.cpp`). Audited and restored 2026-11-21.

Status:

- **ported**: it was already here.
- **restored**: brought back in this pass (behaviour, command-card button, hotkey, tooltip, help entry).
- **changed**: here, but on purpose not as it was (the reason is given).
- **other agent**: building construction and repair belong to the construction agent.
- **n/a**: the feature's units or systems are not in this game (catapult, horseman, medic, fog of war, ruins, saves).
  Their logic is left out, not stubbed.

## Orders

| Old feature (old key) | Status | Here (key) | Notes |
| --- | --- | --- | --- |
| Move in formation (RMB) | ported | RMB | `UVLCommand::OrderMove`; RMB twice: at a run (this game's) |
| Attack a foe's unit / building (RMB, or A + click on it) | ported | RMB / LMB on it, or A + click | `OrderAttack` |
| Attack-move (A, then click) | restored | A (tap), then LMB | `OrderAttackMove`: they march fighting what they meet and march on after each fight (the old units kept their destination through a fight; here the route re-issues the leg, up to 3 times). Shift + LMB adds a point. A + click on a foe attacks it |
| Attack ground (this game's) | ported | A, then LMB (archers alone); A A with others | A cycles attack-move / attack ground (pure archer selections start on attack ground, as before) |
| Stop (S, a tap; a hold pans) | restored | S (tap) | `OrderStop`: drops the order, the pathway, the attack, any standing order; one walking to the tower stays down, one on the lookout stays up. The old tap rule: with units selected a tap under 0.17 s is the order, a hold pans; with nobody selected S pans at once |
| Hold (H) | restored | H | `OrderHold`: a one-off order (`AVLKing::bHoldOrder`) that lasts until the next order; strikes only what is in reach, and (new, for the Hold stance too) lets go of a foe that leaves reach and steps back to its spot |
| Patrol (P, then click; Shift + click more points) | restored | P, then LMB; Shift + LMB | `OrderPatrol` / `ExtendPatrol`: from where they stand through the points and back, round and round, attack-moving, the next leg once nobody walks or fights. P is the pause key only when nobody is selected (or in the hero view) |
| Pathway (Option / Shift + RMB) | ported | Shift + RMB | per unit (`AVLKing::QueueLeg`) |
| Guard (V then click, or RMB): a Builder or a building | restored | V, then LMB; or RMB | `OrderGuard`: posts in a ring round the ward (230 cm round a unit, 170 cm outside a building's walls, rings 120 cm apart); fights foes within `GuardLeash` (18 m; the old 14 m plus the +30% sight) of the ward, archers within their bow's reach; a foe that struck the guard or the ward is run down to 1.8 times that; the chase is dropped beyond it. A struck ward calls its guards in. Ends when the ward falls. Wards: own buildings, Builders and (new) King David; never troops. Builders do not guard (RMB on a building: the troops guard, Builders walk there). V is the camera angle when no troops are selected or in the hero view |
| Roam (O, the Scout) | restored | O | `OrderRoam` (the Spy): spots 20-70 m off, ground it has not been to lately first (there is no fog to explore), never inside a foe's tower or castle reach; a leg over 40 s is dropped. Struck (a tower's arrow too): runs to its castle's door, with an alert |
| March together (M; on by default, per platoon and loose selections) | restored | M | in a formation the slowest always sets the pace (as before); Loose: the setting. Matters now: King David (5.2 / 9.5 m/s) and the Spy are faster than troops. `AVLKing::PaceCap`; a fight on the way is at full speed |
| Dismiss (K twice) | restored | K K | `Dismiss`: troops gone for good, quietly, no refund, not counted as lost; King David cannot be dismissed |
| Repair (X) | other agent | | building repair is the construction agent's |
| Build / repair a site (RMB with Builders) | other agent | | the RMB guard branch leaves Builders to walk to the building (`AVLKing::OrderAt`), for that agent to hook |
| Heal (RMB a troop with Medics) | n/a | | no Medic |
| Repair a ruin (RMB with Builders) | n/a | | no ruins / relics here |
| Formation (F: on / off; RMB its button: next shape) | changed | F / the button / RMB on it: next shape | this game cycles Line > Column > Wedge > Square > Loose (Loose = the old "off") |
| Stances (G: Aggressive > Defensive > Hold Ground) | ported | G | per platoon or per unit. Medics' Assertive / Passive: n/a |
| Reform in place when formation goes on | changed | | the shape applies at the next move |
| Units answer whoever strikes them, friends nearby help, troops before buildings | ported | | `UVLBattle::TickAutoCombat` / `Damage` |

## Selection, platoons, buildings

| Old feature (old key) | Status | Here (key) | Notes |
| --- | --- | --- | --- |
| Click, Shift + click toggles, box (Shift: add) | ported | same | |
| Double-click: every troop of that type on screen | restored | Alt / Option + LMB (Shift: add) | the double click takes control of a unit here (Enter too), so the old action moved to Alt / Option |
| Click an enemy: inspect (read only) | ported | | |
| Space / Home: centre the view on the selection | restored | Space / Home (overview) | the selected building if no units |
| Esc: cancel, then deselect, then pause | changed | Esc / P: cancel an armed click, then pause | clicking the ground deselects; not changed in this pass |
| Platoons: Ctrl+N make, N select (twice: go to it), Shift+N add | ported | Ctrl / Cmd / Alt + N, N, Shift + N | |
| Platoon: formation, stance, march together, name, kind | ported (march restored) | | march together per platoon is new state in `FPlatoon` |
| Platoon struck off when its last troop falls, with an alert | restored (alert) | | "Platoon N has fallen" (not for a dismissal) |
| "Recruits join here" flag on a platoon | changed | | here each barracks / range has its own Joins chips (and Ctrl + N with it selected) |
| Platoon colours: a ring under every member | not restored | | the user asked for fewer rings under feet; the platoon's colour is on its tag and its far pips |
| Rally points (RMB with a barracks / range selected, or the minimap) | ported | | |
| A training building feeds a platoon (its Joins row, Ctrl + N) | ported | | |
| U: upgrade the selected building, else the Citadel | restored (the "else") | U | nothing selected: the castle |
| Recruit hotkeys Q / E / R / T / Y / J / N | changed (not ported) | the recruit buttons (Shift 5, Ctrl 10) | Q / E turn the camera here; R T Y J N trained units this game does not have |
| Delete: disband the platoon | ported | Delete | |
| Delete: cancel construction / demolish | other agent | | |

## Interface

| Old feature | Status | Notes |
| --- | --- | --- |
| Command card: Attack, Stop, Hold, Patrol, Guard, Roam, Stance, Form, March, Disband, Repair, Dismiss | restored | in the old order, plus this game's Attack ground and Control; the row packs tighter past 9 and 11 buttons (52 / 46 / 42 px) and the portraits shrink to stay clear of it. Each button: its key on the cap, a label (Together / Free, Sure?), a lit state when armed or on, and the old tooltip text. Repair: other agent |
| Selection panel: title, platoon line, portraits and counts, health, "N fighting", circles' key | ported | the line under the title now leads with the standing order: "Patrolling (3 points)", "Guarding the Castle", "Holding its ground", "Roaming", "Attack-move" |
| Hint under the top bar while an order is armed | restored | attack-move, attack ground, patrol, guard, each with how to cancel |
| Crosshair pointer while an order is armed | restored | |
| Route lines: a patrol's loop (orange), the way still to walk (blue) | restored | the pathway's legs blue (as before), a patrol's loop orange, an attack-move's points red |
| Rally line | ported | |
| Order markers | ported | |
| Selection ring under selected units, hover ring | changed (removed) | the user's call: the platoon tag over their heads and the health bars (always up while selected) show the selection. The team-coloured ring under every unit went too (the user asked for no circles under feet; `vl.TeamRings 1` brings it back); the building outlines stay |
| Health bars, platoon tags, far pips, sight and bow-range circles | ported | sight / range numbers follow the +30% |
| Alerts (attack, lost, done, housing, info), their minimap pings | ported | clicking an alert to go there: the old HUD did not do it either |
| Controls overlay (F1) | restored entries | every new key; the camera's and Esc's rows say when V and P are orders |
| Build button, build menu, placement hint, Builders / Scout counters | other agent | |

## Not applicable (no units or systems here)

Catapult (siege, minimum range, building preference), Horseman / Rider, Medic (heal, Assertive / Passive), fog of war
(roam's "unexplored first", the Scout half-seen), ruins and relics, saved games. Their logic is not ported and not
stubbed.

## For the enemy-AI rework

The calls on `UVLCommand` (`VLCommand.h`, class comment) work for either side's units and replace what the units were
doing: `OrderStop`, `OrderHold`, `OrderPatrol(Units, Points, bRun, Shape)`, `ExtendPatrol`, `OrderAttackMove(Units,
Ground, bRun, Shape, bQueue)`, `OrderGuard(Units, Ward)` (returns how many took posts; `CanBeGuarded(Ward, Team)`),
`OrderRoam`, `Dismiss`, `ClearStanding`. Queries: `GuardWardOf(Unit, &Leash)`, `GetGuards(Ward, Out)`, `IsRoaming`,
`GetRoute(Unit, Points, bLoop, Next)`, `DescribeOrders`. `UVLBattle::AttackMove` (the commander's present call) is
unchanged: it does not resume after a fight; `OrderAttackMove` does. An order given on a unit's own account (a fight
it picks, an archer walking into range, a defensive unit going back) runs with `bInnerOrder` set and leaves its
standing order alone.
