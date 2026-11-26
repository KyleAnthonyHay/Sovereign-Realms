# Multiplayer, stage one: what is replicated and how

Two players, head to head, on a home network. Stage one of the plan agreed on 2026-11-26: the conventional Unreal
set-up (a listen server and the engine's replication), nothing custom underneath, no backend. How to test it:
`TESTING.md` beside this file.

## The shape of it

- **One player's game hosts.** Hosting opens the map with `?listen`: that game is a *listen server*. It runs every
  rule exactly as the single-player game does (the battle, the economy, orders, fights, construction). It is the only
  game that decides anything.
- **The other player's game joins** by address (`ip:7777`) and is a plain Unreal client. It runs no rules. It shows
  what the host sends, and asks the host for whatever its player does.
- **Teams.** The host is team 0 (green, the single-player side). The joining player is team 1 (red, the side the
  commander plays in single player). The enemy commander is off in a multiplayer match.
- **Behind a switch.** All of it hangs on the net mode. A single-player game is `NM_Standalone`: every unit has
  authority, `UVLBattle::Mine()` is team 0, no RPC is sent, and the code paths below are not entered.

The code: `VLNet.h / VLNet.cpp` (the session, the game state, the shared types), `VLKingNet.cpp` (a unit's
replication), `VLPlayerController.*` (the RPCs), and small, marked edits where the single-player code had to ask "whose
is this?" or "am I the copy?".

## What is replicated

| What | How | Where |
| --- | --- | --- |
| A unit's place and motion | the engine's replicated movement (`SetReplicatingMovement`), 10 updates a second, lowered by the engine for a unit that is not changing (adaptive net update frequency, down to 2 a second); the joining game's `CharacterMovementComponent` simulates between updates | `AVLKing` constructor |
| A unit's side, kind, name | replicated properties (kind and name once, with the unit) | `AVLKing::GetLifetimeReplicatedProps` |
| Health, death, stance | replicated properties with `OnRep` functions: a drop in health shows the white flash, death shows the fall | `OnRep_Health`, `OnRep_Dead` |
| Sword swings | a small counter + the swing's kind (`NetSwing`), `ForceNetUpdate` at each swing; the joining game starts the same swing | `AVLKing::StartSwing`, `OnRep_NetSwing` |
| The bow | one byte (drawing, bow up, quick shot, a count of shots), what it aims at (an actor, else a point); the joining game runs the same draw animation and lets go when the count changes | `UVLArcherCombat::NetFill / NetMirror` |
| Arrows | not actors: each arrow loosed on the host is sent as a small struct (tip, velocity, gravity, side), a frame's worth in one unreliable Client RPC; the joining game flies and lands it with the same code, harmless | `UVLArrows::NetTell / NetShow`, `ClientArrows` |
| Buildings | the battle's building list as a **fast array** (`FFastArraySerializer`) on the game state: only entries that changed are sent. The joining game keeps its own copy of every building and raises, finishes, fells or re-sides it from that list, through the same code that restores a saved game | `AVLGameState::Buildings`, `UVLConstruction::NetApplyBuilding` |
| Gold, food, the counts, the match's state and clock | plain replicated structs on the game state | `AVLGameState::Kingdoms`, `Match` |
| Alerts, 2D sounds, the battle's 3D sounds, "+14" payout numbers | Client RPCs to the player they concern | `UVLBattle::PushAlertTo`, `Play2DTo`, `PlayAt`; `ClientAlert`, `ClientSound`, `ClientPopup` |
| Rocks cleared by Builders | a reliable Client RPC naming the level's rock | `ClientRockCleared` |

Not replicated, on purpose: the farms' hands (scenery; each game has its own), the selection, the cameras, platoons
(see *Limits*), the fog of war (each game works out its own player's from the units it has).

### Why these tools

- **Units are `ACharacter`s and a battle has hundreds**, so each is cheap rather than clever: 10 Hz, adaptive
  frequency, no per-frame RPCs, state packed into a few bytes. 185 units fighting were smooth on one PC with both
  games. `MaxClientRate` is raised to 400 kB/s in `DefaultEngine.ini` for a home network.
- **Every unit is always relevant.** The minimap and the fog need all of them, and with two players there is nobody to
  cull for. (Fog-based relevancy is the natural next step, and would also stop a cheat seeing through fog.)
- **Net dormancy is not used for units**: an idle unit's cost is already near nothing under adaptive frequency, and
  dormancy needs a flush at every state change, which is easy to get wrong. Buildings need none either: they are not
  actors on the wire at all, only entries of the fast array, which sends nothing while nothing changes.
- **The fast array is used for buildings, not troops**: buildings are records in `UVLBattle` already (not replicated
  actors), few, and change slowly. Troops are real pawns the engine already knows how to move and smooth.
- **Smoothing.** The engine smooths a simulated character by offsetting its skeletal mesh; this game's figures are
  voxel parts, so `AVLKing::NetEase` applies the same offset (and eases the turn) to the figure.

## Orders: how the joining player does anything

Every function that gives an order or spends something (`UVLCommand::OrderMove`, `OrderChain`, `OrderAttackMove`,
`OrderGuard`, `OrderPatrolRoute` ..., `UVLBattle::Train`, `Upgrade`, `SetRally`, `BuyJonathan`,
`UVLConstruction::PlaceBuilding`, `CancelSite`, `Demolish`, `Rotate`, `OrderWork`, `ClaimMine`, `UVLRocks::OrderClear`)
starts with a few lines: *in the joining player's game, send this to the host and return*. So the input code and the
HUD are untouched: they call the same functions as ever.

The RPCs are on `AVLPlayerController`: `ServerOrder` (one struct for every unit order), `ServerBuilding`,
`ServerPlace`. **The host validates**: the units are alive and that player's own, the building is theirs, the target
is a foe, the numbers are finite; then it calls the very same function. Prices, housing, placement and limits are
checked on the host by the single-player code (the joining game also checks what it can see, so most refusals are
immediate and local).

## The hero

The joining player possesses its own King David, an *autonomous proxy*: `CharacterMovementComponent`'s built-in client
prediction moves him at once and the host confirms. Around that:

- his pace (walk / run) is told to the host (`ServerSetPace`) so both simulate at the same speed;
- a click of the sword swings locally at once and asks the host (`ServerSwing`); the host's swing is the one that
  deals damage;
- when he is given a walk by the host (an order in the overview, the approach to a fight), the path is sent to his
  own game (`ClientFollowPath`), which walks it with prediction and reports the end (`ServerOrderDone`);
- which view he is played in is told to the host (`ServerSetHero`): in the overview he takes orders and fights by
  himself, as the host's own King does.

## The joining game's world

- `UVLBattle` there does not tick the rules (`TickNetClient`): its building list and kingdoms are filled by
  `AVLGameState::Tick` from what arrived, so the HUD reads `UVLBattle` exactly as in single player.
- Units there are *copies* (`AVLKing::IsNetCopy()`): animated and shown, never ordered, never dealing damage.
- A client has no game mode. `AVLGameMode::Local()` returns a local stand-in there (spawned by `UVLBattle`) that does
  only a game mode's local work: music, ambience, the marching shuffle, the command inbox.
- `UVLBattle::Mine()` is 1 there: "the player's" in the HUD, the selection and the fog means this game's own player.
  On the host, alerts and refusals for team 1 go to the joining player (`IsHuman`, `PushAlertTo`).

## Hosting, joining, versions

`UVLNetSession` (a game-instance subsystem) is the only code that knows how two games find each other: `Host(map)`
travels to `map?listen?MP=1`, `Join(address)` travels to `address:7777?VLVer=<version>`, `Leave()` goes back to the
title. **EOS goes in here later**: create or find a session through the engine's online subsystem and travel to what
it resolves to; nothing else in the game needs to know.

The host compares versions in `AVLGameMode::PreLogin` and refuses another build with a readable message, which the
joining game shows on its title screen. The version is `<ProjectVersion>-mp<VLNet::Protocol>`; **bump
`VLNet::Protocol` (VLNet.h) whenever what the two games send each other changes.**

## Rules decided for multiplayer (defaults: change any of them)

- The match **starts when the joining player is in** (the host waits on a banner showing its address). Nobody can join
  a match that has started, and a player who drops cannot come back.
- Each side starts as in single player: its castle, 3 swordsmen, 2 archers, a Builder, its King David.
- **A player leaving ends the match**: if the joiner leaves or drops, the host wins; if the host leaves, the joiner
  returns to the title with the reason.
- **No pause** (the menu opens over the running match), **no saves**, no restart from inside a match.
- **No troop ships** yet (a ship and its passengers are not replicated).
- **Jonathan**: each player may buy theirs at castle level 3.
- Both sides' troops carry plain names (no "Enemy" prefix); each player's own units are the ones outlined through
  walls on their own screen.
- The frame-rate throttle for an unfocused window or an open menu is off in a multiplayer match (the other player
  depends on the host's pace).

## Limits and what is next

See *Known limits of stage one* in `TESTING.md`. In code terms the larger ones are:

- **Platoons live in `UVLCommand` once**, for the host's player. The joining game keeps its own as local selection
  groups. Making them per side (and replicating membership) is the fix.
- **`TakeControlOf` is refused for the joining player**: possessing another unit needs the possession moved on the
  host, and the played archer's bow (`UVLArcherCombat::TickHands`) made to shoot through the host.
- **Order display for the joining player** (routes, chains, guard posts, a Builder's task) lives in host-only
  structures; a compact replicated summary per unit would bring it back.
- **Troop ships** need `AVLTroopShip` replicated and boarding expressed as replicated state.
- **Relevancy by fog**, then **EOS** for internet play (`TESTING.md`, *Next steps*).

## Testing hooks

- `Tools\windows\mp_test.ps1`: host + joining game on one PC, driven through their inboxes, compared step by step.
- `-VLInbox=<file>`: a game's own command inbox, so two games can run from one folder.
- `vl.Host <map>`, `vl.Join <address>`, `vl.Leave`, `vl.Net` (one line of state), `vl.NetDump <name>` (this game's
  units, buildings and kingdoms to `Saved/<name>.txt`), `-VLHost=`, `-VLJoin=`, `-VLFakeVersion=` (pretend to be
  another build, to see the refusal).
