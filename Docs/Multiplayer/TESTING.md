# Multiplayer: how to test it on the PC and the Mac

Stage one of multiplayer is a two-player match over your home network: one computer hosts, the other joins by typing
the host's address. This page is the test to run on the Windows PC and the Mac together, what to look for, and what
to send back. How it is built is in `DESIGN.md` beside this file.

**Status (2026-11-26).** Built and tested on the Windows PC only, with two copies of the game on the one machine
(`Tools\windows\mp_test.ps1`, all eight checks pass). **The Mac has not compiled or run this code yet**: step 1 below is
where a Mac problem would show first.

## 1. Get the same build on both machines

Both games must be the same build, or the host refuses the other one (the message says so).

1. **PC**: nothing to do, the builds in `Builds\Windows\SovereignRealms\` (Shipping) and
   `Builds\Windows\SovereignRealms-Development\` already have multiplayer.
2. **Mac**: say "sync with dev" to the agent there (or `git checkout mac && git fetch origin && git merge origin/dev`),
   then build and package:

   ```sh
   sh Tools/mac/editor.sh build          # compiles; a compile error here is the first thing to report
   sh Tools/mac/package.sh Development   # Builds/Mac/SovereignRealms.app, with the ~ console and a log
   ```

3. On each machine start the game and open **MULTIPLAYER** on the title screen. The small line at the bottom of that
   panel reads `This game: version 1.0.0.0-mp1`. It must be the same text on both.

Use the **Development** build on both machines for the first test (it writes a log and has the `~` console). Shipping
with Shipping should work the same; Shipping on one and Development on the other is untested.

## 2. Host on the PC

The PC should host first: the host's game runs the whole battle for both players, and the PC is the faster machine.

1. PC: title screen > **MULTIPLAYER** > pick a map (Realm v3 is the smallest and loads quickest) > **HOST**.
2. The first time, Windows asks whether to allow the game through the firewall: tick **Private networks** and press
   **Allow access**. (If that box was dismissed earlier: Windows Security > Firewall & network protection > Allow an
   app through firewall > find `SovereignRealms` > tick Private.)
3. The map opens with a banner: **WAITING FOR THE OTHER PLAYER** and the line
   `They choose Multiplayer > Join and type: 192.168.x.x`. That number is the PC's address on your network. Nothing
   in the match moves until the other player is in.

If the banner shows two addresses, use the one that starts like the Mac's own address (usually `192.168.` or `10.`).
To look the address up by hand: Windows key, type `cmd`, Enter, type `ipconfig`, read **IPv4 Address**.

## 3. Join from the Mac

1. Both computers must be on the same network (the same Wi-Fi, or one on Wi-Fi and one on cable to the same router).
2. Mac: title screen > **MULTIPLAYER** > type the PC's address into the box under **JOIN A MATCH** (digits and dots;
   Cmd + V pastes) > **JOIN** (or Enter). Leave the port alone: it is 7777 unless the host's log says otherwise.
3. The first time, macOS may ask **"SovereignRealms would like to find and connect to devices on your local
   network"**: press **Allow**. If you pressed Don't Allow, the join fails with "No game answered": turn it on in
   System Settings > Privacy & Security > Local Network, then try again.
4. The Mac shows "Connecting to ...", loads the host's map, and the match starts on both. The Mac's player is the
   **red** kingdom on the far side of the map, with its own King David, troops, gold and fog of war.

If it sits on "Connecting ..." for more than about twenty seconds, press **CANCEL** and check: the PC is still on its
waiting banner, the address was typed right, the firewall box on the PC was allowed, both are on the same network.
(A guest Wi-Fi network often blocks computers from seeing each other.)

**The other way round** (Mac hosts, PC joins) is the second test. To find the Mac's address: it is on the Mac's
waiting banner, or System Settings > Network > Wi-Fi > Details > IP address, or in Terminal `ipconfig getifaddr en0`.
When the Mac hosts for the first time macOS may ask whether the app may accept incoming connections: Allow.

## 4. What to try

Play a few minutes on both machines, in this order (each line is something that was built for this stage):

| Try | What should happen |
| --- | --- |
| Both: look at the top bar | each player sees their own gold, food and housing; the clock runs the same on both |
| Mac (red): select troops, right-click the ground | they walk there; the PC sees them walk too (once in its sight) |
| Mac: Tab into the hero view, WASD, Shift, Space, left click | King David moves at once under your hands, no rubber-banding; the PC sees him move and swing |
| Both: build a Barracks (B), train swordsmen and archers | the site rises on both screens as the Builder works; gold is taken from the right player |
| Both: upgrade the castle (U) | the level and the stores change for that player only |
| Send an army at the other player | both screens show the same fight: the same troops fall, health bars agree, arrows fly on both |
| Attack a watch tower and a building | it takes damage and collapses on both; each player gets the right alert ("Your ... has been destroyed" / "The enemy's ...") |
| Walk troops out of sight of the other player | they vanish into that player's fog, and stay visible to their owner |
| Esc on either machine | the menu opens but the match keeps going (a multiplayer match never pauses); Save, Load, Restart are greyed out |
| Destroy a castle | VICTORY on one machine, DEFEAT on the other |
| New match: one player picks Esc > LEAVE THE MATCH | the other is told at once; if the joiner leaves, the host wins the match; if the host leaves, the joiner goes back to the title with "The host left the match" |
| New match: pull the network cable / turn Wi-Fi off on one machine | within about 30 seconds the other is told and the match ends |

## 5. What to report back

For anything that looks wrong, note **which machine was the host**, what you did, and what each screen showed. Then:

- **Screenshots or a phone photo of both screens** at the same moment are the most useful thing.
- **The logs** of both machines from that session:
  - PC, Development build: `Builds\Windows\SovereignRealms-Development\SovereignRealms\Saved\Logs\SovereignRealms.log`
  - Mac, Development build: `~/Library/Logs/SovereignRealms/SovereignRealms.log` (if it is not there: in Finder,
    Go > Go to Folder, `~/Library/Application Support/Epic/SovereignRealms/Saved/Logs`)
- If the two screens **disagree** (a troop alive on one and dead on the other, a building missing): on both machines
  press `~`, type `vl.NetDump mine` and Enter. Each game writes what it holds to `Saved/mine.txt` next to its log
  folder. Send both files: comparing them shows exactly what differs.
- `vl.Net` in the `~` console prints one line: host or joining game, the version, how many units and buildings.

Things worth saying even if nothing broke: how smooth the other player's troops look (they are sent ten times a second
and smoothed in between), whether the joiner's hero ever snaps back while walking, and how a big fight (100+ troops)
runs on the Mac.

## 6. The scripted test (PC only)

`powershell -ExecutionPolicy Bypass -File Tools\windows\mp_test.ps1` starts a host and a joining game side by side on
the PC from the Development build, has the joining player move troops, fight a battle of swordsmen and archers, lay a
barracks and walk its King, fells a castle, and compares what the two games hold at every step. It prints PASS or FAIL
per step. Result on 2026-11-26: all eight pass (join, state, move, fight, build, hero, end, leave).

To drive a match by hand from scripts or the console: `vl.Host realmv3`, `vl.Join 192.168.1.20`, `vl.Leave`; or start
the game with `-VLHost=realmv3` / `-VLJoin=192.168.1.20`.

## Known limits of stage one

- **Home network or direct address only.** No internet play, no invites, no list of matches. (Over the internet it
  would need the host's router to forward UDP port 7777; untested and not the plan: see Next steps.)
- **The joining player plays King David only.** They command every unit they own, but cannot take control of another
  unit (Enter / double click) or of Jonathan. The host can, as in single player.
- **The joining player's platoons are selection groups only.** Ctrl + 1-6 and 1-6 work; the platoon's leader, "follow
  me", platoons keeping together and "recruits join this platoon" are the host's only for now. In the hero view's
  command mode the joiner has no king's guard: select troops first.
- **The joining player's screen shows less about its own orders**: no route lines or numbered order plates, no guard
  shields, a Builder's row always reads Idle, a watch tower's panel does not list who is on it. The orders themselves
  work.
- **No troop ships** in a multiplayer match (neither player has one). No pause. No saving or loading. A player who
  drops out cannot come back into the same match.
- **The joining player's hero does not pass through its own troops** (in single player they step aside for him).
- Training dummies of a barracks built during the match cannot be attacked by the joining player.
- **Fog of war is per player but not enforced**: both games are sent every unit, and each hides what its player cannot
  see. Fine between friends; it is not cheat-proof.
- **Not yet tested**: the Mac build (compiling and running), a real network (only one PC with two games so far), a very
  large battle over Wi-Fi (185 units was fine on one machine), Shipping against Development.

## Next steps

1. **This test**, both ways round (PC hosts, then Mac hosts), and the fixes it turns up.
2. **A full match** on both machines from start to castle, for balance and feel with a human on the red side.
3. **Internet play through Epic Online Services** (free; it gives a relay so no router set-up, and invites). The code
   that hosts and joins is in one place (`UVLNetSession`), written so EOS slots in behind the same Host and Join
   buttons. Before that work can start, **you need to create the product in Epic's developer portal**:
   1. Sign in at <https://dev.epicgames.com/portal> with your Epic account and create an **organization** if you have
      none (free).
   2. **Create Product**, named Sovereign Realms.
   3. In the product's **Product Settings** note the **Product ID**, the **Sandbox ID** and the **Deployment ID**
      (the Live sandbox's are fine to start with).
   4. Under **Product Settings > Clients** add a **client policy** of the "Peer2Peer" type (it allows sessions,
      lobbies and peer-to-peer connections), then add a **client** that uses it. Note its **Client ID** and
      **Client Secret**.
   5. Send those five values (Product ID, Sandbox ID, Deployment ID, Client ID, Client Secret). Nothing else is needed
      for a first version: players can sign in anonymously per device, so no Epic account log-in screen and no store
      page.
4. The limits above, in the order they annoy most (probably: the joiner playing any unit, platoons for the joiner,
   troop ships).
