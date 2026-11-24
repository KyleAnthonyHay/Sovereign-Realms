#!/usr/bin/env python3
"""The screenshots of L_RealmV3 (the editor open on L_RealmV3; starts and stops its own play session):

    python Tools/realmv3_shots.py [name ...]        -> Saved/Screenshots/VL/realmv3_<name>.png

Each view is a free camera at a place of the plan (metres, +Y north) looking at another; the postcard and the hero's
own view are the game's. Without names: all of them.
"""
import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
import pie

# name -> (camera x, y, z, target x, y, z, FOV) or a vl.View word
VIEWS = dict(
    overview="postcard",                                             # the whole island from the south-west
    plan=(0.0, -0.5, 840.0, 0.0, 0.0, 0.0, 36.0),                     # straight down, north up: the concept's plan
    threequarter=(0.0, -560.0, 370.0, 0.0, -8.0, 0.0, 44.0),         # from the south: the concept's three-quarter view
    plateau_a=(-30.0, 28.0, 110.0, -122.0, 122.0, 14.0, 60.0),         # plateau A and its ramp, from over the north-west crest
    plateau_b=(30.0, -28.0, 110.0, 122.0, -122.0, 14.0, 60.0),         # plateau B and its ramp, from over the south-east crest
    ramp_a=(-36.0, 66.0, 36.0, -74.0, 40.0, 9.0, 60.0),               # plateau A's ramp from the side: the spur and its shoulders
    ramp_b=(36.0, -66.0, 36.0, 74.0, -40.0, 9.0, 60.0),
    ramp_a_low=(-67.5, 2.0, 6.4, -75.0, 50.0, 10.5, 70.0),            # up plateau A's ramp from its foot, a soldier's height up
    ramp_b_low=(67.5, -2.0, 6.4, 75.0, -50.0, 10.5, 70.0),
    ramp_a_down=(-80.0, 80.0, 17.5, -69.0, 20.0, 5.0, 70.0),          # down it from the plateau's rim
    pass_=(-84.0, 70.0, 34.0, -52.0, -8.0, 4.0, 60.0),                # down the ramp and through the pass into the basin
    pass_floor=(-66.0, 1.0, 6.5, -50.0, -13.0, 5.5, 75.0),            # in the pass, a soldier's height up
    basin=(-76.0, -70.0, 82.0, 6.0, 6.0, 4.0, 60.0),                  # the basin from over its south-west end
    basin_mine=(14.0, 8.0, 15.0, 31.5, 46.0, 7.0, 60.0),              # Neutral 1 in the rock
    dock_a=(-276.0, 78.0, 26.0, -218.0, 124.0, 2.0, 60.0),            # the player's port from the sea
    dock_b=(276.0, -78.0, 26.0, 218.0, -124.0, 2.0, 60.0),            # the enemy's
    dock_a_stair=(-236.0, 138.0, 3.0, -200.0, 122.0, 6.0, 70.0),      # the stair up the sea cliff, from the quay
    forest=(-236.0, 10.0, 44.0, -150.0, 60.0, 8.0, 60.0),             # the forest under plateau A, from over the west coast
    forest_canopy=(90.0, 200.0, 30.0, -30.0, 110.0, 6.0, 60.0),        # along the canopy north of the ridge
    coast=(-40.0, -276.0, 24.0, -110.0, -210.0, 6.0, 60.0),             # the south coast: forest to the sea cliffs
    base="follow",                                                   # the hero's own view at the player's castle
)


def command(v):
    if isinstance(v, str):
        return "vl.View " + v
    cx, cy, cz, tx, ty, tz, fov = v
    dx, dy = tx - cx, ty - cy
    yaw = math.degrees(math.atan2(-dy, dx))                           # (Unreal's Y runs south)
    pitch = math.degrees(math.atan2(tz - cz, math.hypot(dx, dy)))
    return "vl.View free %.0f %.0f %.0f %.1f %.1f %.0f" % (cx * 100, -cy * 100, cz * 100, pitch, yaw, fov)


def main(names):
    names = names or list(VIEWS)
    pie.main(["start", "8"])
    pie.run(["vl.StartMatch 0"])
    time.sleep(6)
    pie.run(["ShowHUD"])                                              # (the engine's own switch: the pictures without the interface)
    pie.run([command(VIEWS[names[0]])])
    time.sleep(5)                                                     # (the match's opening shot is over)
    for n in names:
        pie.run([command(VIEWS[n])])
        pie.main(["shot", "realmv3_" + n.rstrip("_"), "6"])
    pie.main(["stop"])




# ---- "can I see past the rock?" (owner, 2026-11-23: the ridges blocked the view): the game's own two cameras.
#   python Tools/realmv3_shots.py walls <tag>     -> Saved/Screenshots/VL/realmv3_walls_<tag>_<name>.png
# over_*: the overview as the game opens it (zoom 0.18, yaw -62), and turned half round (yaw 118), over a place;
# hero_*: King David's own camera, standing at a place and facing a way (degrees from east, counter-clockwise).
WALL_OVER = dict(plateau_a=(-130.0, 134.0), plateau_b=(130.0, -134.0), basin=(0.0, 0.0), pass_a=(-57.6, -6.0), pass_b=(57.6, 6.0),
                 ramp_a=(-73.0, 40.0), ramp_b=(73.0, -40.0))
WALL_HERO = dict(plateau_a_rim=(-79.0, 78.0, 14.0, -80.0), ramp_a_foot=(-68.0, 10.0, 4.3, -55.0), pass_a=(-60.0, -3.0, 4.0, -45.0),
                 basin_to_nw=(0.0, 0.0, 4.0, 162.0), basin_to_se=(0.0, 0.0, 4.0, -18.0), basin_north=(-2.0, 25.0, 4.0, -90.0),
                 pass_b=(60.0, 3.0, 4.0, 135.0), plateau_b_rim=(79.0, -78.0, 14.0, 100.0))


def walls(tag):
    pie.main(["start", "8"])
    pie.run(["vl.StartMatch 0"])
    time.sleep(8)
    pie.run(["ShowHUD"])
    for n, (x, y) in WALL_OVER.items():
        for suffix, yaw in (("", -62.0), ("_back", 118.0)):
            pie.run(["vl.Look %.0f %.0f 0.18 %.0f" % (x * 100, -y * 100, yaw)])
            pie.main(["shot", "realmv3_walls_%s_over_%s%s" % (tag, n, suffix), "3"])
    pie.run(["vl.Look 0 0 0.4 -62"])
    pie.main(["shot", "realmv3_walls_%s_over_basin_far" % tag, "3"])
    # (the overview pulled right in: its shallowest look, 26 degrees down, where rock in front of the view hides most)
    for n, (x, y) in WALL_OVER.items():
        pie.run(["vl.Look %.0f %.0f 0 %.0f" % (x * 100, -y * 100, -62.0)])
        pie.main(["shot", "realmv3_walls_%s_near_%s" % (tag, n), "3"])
    pie.run(["vl.Mode hero", "vl.View follow"])
    for n, (x, y, z, face) in WALL_HERO.items():
        pie.run(["vl.Teleport %.0f %.0f %.0f %.0f" % (x * 100, -y * 100, z * 100 + 110, -face)])
        pie.main(["shot", "realmv3_walls_%s_hero_%s" % (tag, n), "3.5"])
    # (and looking along the ground the way he faces, 12 degrees down from 11 m behind him)
    for n, (x, y, z, face) in WALL_HERO.items():
        pie.run(["vl.Teleport %.0f %.0f %.0f %.0f" % (x * 100, -y * 100, z * 100 + 110, -face), "vl.Orbit %.0f -12 1100" % -face])
        pie.main(["shot", "realmv3_walls_%s_herolow_%s" % (tag, n), "3"])
    pie.main(["stop"])


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "walls":
        walls(sys.argv[2])
    else:
        main(sys.argv[1:])
