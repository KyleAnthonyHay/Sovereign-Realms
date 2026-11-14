# Sovereign Realms: design and art review

Reviewed on branch `dev` from the docs, the map generator, the feel settings, existing captures and 11 fresh
captures (`Saved/Screenshots/SR/rv_*.png`), including a 12-minute AI-vs-AI match at Normal. Not covered: real-mouse
play (everything was scripted) and a close look at a troop-vs-troop melee (none was in frame when I captured).
Effort tags: S = under a day, M = a few days, L = a week or more.

## Where it stands

The systems are well ahead of the experience. Orders, formations, stances, platoons, a commander AI that scouts and
adapts, building states, a full HUD and 87 fps are all there. The look is recognisably HD-2D at close range: the
buildings are the best thing in the game (`rv_siege.png`, `rv_enemy_out.png`) and the sprites sit well in the light
(`rv_fight_close.png`).

Three things hold it back:

1. **Matches stall into a trickle.** At 12:38 of AI vs AI the armies were 11/36 and 4/36, one side had 1,519 gold
   unspent, food sat under 100, and the log was a column of "reinforces its attack with 3". There is no mass, no
   decisive battle, and gold has nothing to buy late.
2. **The map is uniform noise.** 95 terraces, 70 knolls, 46 boulders and 70 firs are Poisson-scattered by
   `plan_field()`. Every screen of the middle looks like every other (`rv_centre_out.png`), with no chokepoints,
   regions or landmarks.
3. **The look falls apart when zoomed out, where an RTS is played.** Troops are about 15 px tall at full zoom-out
   (`rv_map_far.png`), shadows are long near-black masses, terrace edges read as cracks, and the lake is a flat tiled
   sheet (`rv_lake.png`).

## 1. Game experience and design

| # | Issue and suggestion | Effort |
| --- | --- | --- |
| 1 | **Food starves the game; gold floods it.** A farm gives 90 food/min, about one Shieldbearer, so ten farms sustain a trickle while gold piles up. Raise farm yield (9 to about 14 per 6 s) or cut troop costs about 30%, and give gold a military sink: an elite unit or upgrades at the Barracks, and building repair. Target 25+ troops a side by minute 8. | S |
| 2 | **Reinforcements arrive piecemeal.** `USRAISubsystem` tops up a winning attack with 3 every 20 s; they walk across the map alone and die to towers. Gather reinforcements at a staging point and send them in groups of at least 6, or only when the group is 0.5x the attack's strength. | S |
| 3 | **Two units make no decisions.** Shieldbearer and Archer have no counter triangle. Add one fast unit (chariot or skirmisher) that beats archers and raids mines, and a spearman that beats it. Add a +25% damage and +2 m bow range bonus on higher ground: the terraces already exist and currently only block. | M |
| 4 | **No fog of war for the player.** The AI plays by sight memory (26 m, 90 s) but the minimap shows every enemy building from 0:00. Hiding unseen enemies (units at least) makes scouting, towers and raids matter. The grid subsystem can carry the visibility mask. | M |
| 5 | **Sieges are flat.** Troops stand at a wall and chop (`rv_fight_close.png`); there is no siege unit and no fire or smoke, and with armies this small the citadel's 12,000 HP is rarely reached. Add a ram (a gold sink, strong against buildings only), and burning or smoke on the Damaged state. | M |
| 6 | **Nothing is at stake in the middle.** Centre veins are the only objective. Add one or two capturable sites (a shrine giving +population or a sight radius, a ford) so armies meet in the field instead of at towers. | M |
| 7 | **Troops vanish behind buildings.** The barracks is about 12 m wide and there is no occlusion treatment (`rv_fight.png`: the attackers are hidden by the roof). Draw a team-colour silhouette for occluded sprites, or fade the roof. | M |
| 8 | **Combat juice is thin outside the hit itself.** Hit-stop, flash and shake exist; there are no dust puffs, no arrows sticking in the ground, no blood or debris decals, and corpses expire. Small sprite effects on hit, death and footfall would do a lot. | S-M |

## 2. Graphics and polish

| # | Issue and suggestion | Effort |
| --- | --- | --- |
| 1 | **Unreadable at far zoom.** `ZoomDistanceMax` is 11000 (the visual contract still says 3600) and the pitch reaches -58 degrees. Past zoom of about 0.7, draw a team-colour pip or banner over each troop or platoon, and thicken the blob shadow into a team-colour disc. Consider capping the zoom near 7000. | S |
| 2 | **Shadows crush the image.** Sun pitch -33 gives tree and castle shadows longer than the objects, nearly black (`rv_centre_out.png`, `rv_player_out.png`); blue troops disappear in them. Raise the sun to about -42, lift the sky fill, and aim for shadow about 35-40% of lit ground value. The golden mood survives. | S |
| 3 | **Ground is noisy where sprites stand.** The grass texture is per-texel salt-and-pepper at high contrast (`rv_centre.png`, `rv_fight_close.png`), competing with the sprite's own pixels. Cut grass albedo contrast by about a third, and use larger colour clusters (4-8 texel patches) rather than per-texel noise. | S |
| 4 | **Water is the weakest asset.** Visible tile repeat, no shore gradient, no reflection, hard polygon bank (`rv_lake.png`). Add depth-fade shallows, a foam line at the bank, two scrolling layers at different scales, a sun glint, and reeds on the shore. | M |
| 5 | **Terrace lips read as dark cracks from above.** From -58 degrees the 40 cm steps show only their shadow line. Give the lip a light stone or dry-grass rim texel band and a darker face so the step reads as a step. | S |
| 6 | **Damage dither is harsh.** The Damaged state's holes and soot are edged with a checker dither that shimmers (`rv_fight.png` roof and wall). Use a hand-cut pixel edge in the texture. | S |
| 7 | **Both kingdoms are the same kit recoloured.** Red against blue on identical sandstone. A different stone tone and roof or awning shape for the enemy would make screenshots readable at a glance. | M |
| 8 | **HUD is clean but generic.** Roboto on black panels fights the Bronze-Age art. A pixel or serif display face for headings and numbers, and a parchment or bronze panel tint, would tie it together. Also 36 px of the frame is the editor title bar: review in standalone. | S-M |
| 9 | **Sprite angle mismatch.** Sheets are rendered at 30 degrees elevation but the camera now goes to 58; the contract judged 46 acceptable. Re-check at the new limit or re-render at about 40 (`build_all.sh --elev`). | S |

## 3. Map design

| # | Issue and suggestion | Effort |
| --- | --- | --- |
| 1 | **Replace uniform scatter with authored structure.** In `plan_field()` keep scatter only as dressing. Author 3 lanes (the king's road plus the two branch roads) separated by two long ridges or wood belts with 2-3 gaps each of about 12-15 m. That creates chokepoints for towers and flanking routes for raids. | M |
| 2 | **Give the map regions.** Today it is one olive meadow. Distinct zones (a dense fir wood, a dry rocky upland around the far-corner veins, marsh around the lakes, wheat-gold plain near the kingdoms) via the splat fields and prop density would aid orientation and add colour variety inside the muted palette. | M |
| 3 | **No landmark at the centre.** The road crossing at (0,0) is bare grass (`rv_centre.png`); the ruins nearby are a few blocks. Put a large ruin, standing stones or a bridge there, big enough to read on the minimap. | S-M |
| 4 | **Lakes do not shape play.** At (-2600, 6600) and (2600, -6600) they sit off every route. Move them to pinch the branch roads, or join them to the centre with a river and two fords: natural chokepoints and the best showcase for water. | M |
| 5 | **The map may be too big for 36 population.** 240 m square, with 11-troop armies, is mostly empty walking. Either shrink the play bound to about +/-9000 or raise `MaxPopulation` to 60 once the economy is fixed. | S |
| 6 | **Kingdoms have no walls or gate.** The 34 m flat apron sprawls. Low walls with two gates round the start, even as pure dressing with blockers, would give bases a shape and the siege a focus. | M |

## Quick wins (under an hour each)

- Raise farm yield and AI reinforcement size (two numbers and one condition).
- Sun pitch -33 to about -42 and brighter sky fill in the `LOOK` table of `Tools/build_battlefield_visuals.py`.
- Lower grass albedo contrast.
- Cap `ZoomDistanceMax` near 7000, or add far-zoom troop pips.
- At `ZoomDefault` 0.35 the opening shot is filled by a blurred castle parapet (`rv_home.png`): start the camera on the army, a little farther out.
- "Enemy ready in 3:56" gives away the AI's timer; show it only on Easy, or after a scout has seen the army.
- Minimap: draw gold veins as a diamond and distinguish taken from free; draw the roads brighter.
- Update `Docs/VISUAL_CONTRACT.md` (bounds +/-3000, zoom 3600, pitch -46 are all stale).

## Next three milestones

1. **A battle worth watching (1-2 weeks).** Economy retune, grouped reinforcements, far-zoom readability, shadow and
   grass tuning, occlusion silhouettes, hit and death effects. Exit test: AI vs AI reaches 25+ troops a side and ends
   between 12 and 20 minutes; a real-mouse playtest is done.
2. **A map with a shape (1-2 weeks).** Lanes, ridges and gaps, a river with fords, regions, a centre landmark, the
   water shader, the high-ground bonus, one capturable site.
3. **Decisions (2-3 weeks).** Fog of war, a third and fourth unit with counters, a ram, a gold sink (upgrades or
   elite), a distinct enemy kit, HUD theming.
