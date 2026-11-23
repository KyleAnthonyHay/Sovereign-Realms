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
    plan=(0.0, -0.5, 680.0, 0.0, 0.0, 0.0, 36.0),                     # straight down, north up: the concept's plan
    threequarter=(0.0, -450.0, 300.0, 0.0, -8.0, 0.0, 44.0),         # from the south: the concept's three-quarter view
    plateau_a=(-36.0, 30.0, 86.0, -104.0, 104.0, 14.0, 60.0),         # plateau A and its ramp, from over the north-west crest
    plateau_b=(36.0, -30.0, 86.0, 104.0, -104.0, 14.0, 60.0),         # plateau B and its ramp, from over the south-east crest
    ramp_a=(-36.0, 66.0, 36.0, -74.0, 40.0, 9.0, 60.0),               # plateau A's ramp from the side: the spur and its shoulders
    ramp_b=(36.0, -66.0, 36.0, 74.0, -40.0, 9.0, 60.0),
    ramp_a_low=(-67.5, 2.0, 6.4, -75.0, 52.0, 10.5, 70.0),            # up plateau A's ramp from its foot, a soldier's height up
    ramp_b_low=(67.5, -2.0, 6.4, 75.0, -52.0, 10.5, 70.0),
    ramp_a_down=(-80.0, 84.0, 17.5, -69.0, 20.0, 5.0, 70.0),          # down it from the plateau's rim
    pass_=(-84.0, 70.0, 34.0, -52.0, -8.0, 4.0, 60.0),                # down the ramp and through the pass into the basin
    pass_floor=(-66.0, 1.0, 6.5, -50.0, -13.0, 5.5, 75.0),            # in the pass, a soldier's height up
    basin=(-76.0, -70.0, 82.0, 6.0, 6.0, 4.0, 60.0),                  # the basin from over its south-west end
    basin_mine=(14.0, 8.0, 15.0, 31.5, 46.0, 7.0, 60.0),              # Neutral 1 in the rock
    dock_a=(-236.0, 62.0, 26.0, -178.0, 108.0, 2.0, 60.0),            # the player's port from the sea
    dock_b=(236.0, -62.0, 26.0, 178.0, -108.0, 2.0, 60.0),            # the enemy's
    dock_a_stair=(-196.0, 122.0, 3.0, -160.0, 106.0, 6.0, 70.0),      # the stair up the sea cliff, from the quay
    forest=(-200.0, 30.0, 44.0, -120.0, 70.0, 8.0, 60.0),             # the forest under plateau A, from over the west coast
    forest_canopy=(60.0, 160.0, 30.0, -40.0, 76.0, 6.0, 60.0),        # along the canopy north of the ridge
    coast=(150.0, -228.0, 24.0, 60.0, -160.0, 6.0, 60.0),             # the south coast: forest to the sea cliffs
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


if __name__ == "__main__":
    main(sys.argv[1:])
