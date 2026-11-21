"""The postcard camera: the view of References/village.png. Shared by the layout, the Blender preview and Unreal.

World: metres, +X east, +Y north, +Z up (Blender axes). Picture: 1600 x 900 pixels, origin top-left.
The camera looks at the ground point TARGET, which sits at the middle of the picture.
"""
import math

W, H = 1600, 900
AZ = -28.0           # camera position, degrees clockwise from south seen from above: the picture is taken from the LEFT
                     # (south-west): you see each building's front and its left side, and steps run down to the right
EL = 30.0            # elevation above the ground (a little shallower than the picture's own ~36: the owner's choice)
DIST = 100.0         # metres from the target
FOCAL_PX = 3800.0    # focal length in pixels at 1600 wide (38 px per metre at the target)
TARGET = (0.0, 0.0, 0.0)

_a, _e = math.radians(AZ), math.radians(EL)
POS = (TARGET[0] + math.sin(_a) * math.cos(_e) * DIST, TARGET[1] - math.cos(_a) * math.cos(_e) * DIST, TARGET[2] + math.sin(_e) * DIST)
FWD = (-math.sin(_a) * math.cos(_e), math.cos(_a) * math.cos(_e), -math.sin(_e))
RIGHT = (math.cos(_a), math.sin(_a), 0.0)
UP = (RIGHT[1] * FWD[2] - RIGHT[2] * FWD[1], RIGHT[2] * FWD[0] - RIGHT[0] * FWD[2], RIGHT[0] * FWD[1] - RIGHT[1] * FWD[0])
HFOV = math.degrees(2.0 * math.atan(W / 2.0 / FOCAL_PX))


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def project(x, y, z=0.0):
    """World point -> picture pixel (px, py)."""
    d = (x - POS[0], y - POS[1], z - POS[2])
    depth = _dot(d, FWD)
    return (W / 2.0 + FOCAL_PX * _dot(d, RIGHT) / depth, H / 2.0 - FOCAL_PX * _dot(d, UP) / depth)


def unproject(px, py, z=0.0):
    """Picture pixel -> the world point on the horizontal plane at height z."""
    cx, cy = (px - W / 2.0) / FOCAL_PX, (H / 2.0 - py) / FOCAL_PX
    ray = tuple(FWD[i] + RIGHT[i] * cx + UP[i] * cy for i in range(3))
    t = (z - POS[2]) / ray[2]
    return (POS[0] + ray[0] * t, POS[1] + ray[1] * t)
