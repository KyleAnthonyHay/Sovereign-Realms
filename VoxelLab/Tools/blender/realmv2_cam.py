"""The Realm v2 postcard camera: the highlands' view, further back for the 640 m map.

World: metres, +X east, +Y north, +Z up (Blender axes). Picture: 1672 x 941 pixels, origin top-left.
The camera looks at the ground point TARGET, which sits at the middle of the picture. Same conventions as village_cam.py.
"""
import math

W, H = 1672, 941
AZ = -30.0           # camera position, degrees clockwise from south seen from above: taken from the south-west, so
                     # every building shows its front (-Y) and its left (west) side, as in the picture
EL = 38.0            # elevation above the ground
DIST = 990.0         # metres from the target
FOCAL_PX = 2150.0    # focal length in pixels at 1672 wide (the whole map)
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
    """World point -> picture pixel (px, py). Works on numpy arrays too."""
    d = (x - POS[0], y - POS[1], z - POS[2])
    depth = _dot(d, FWD)
    return (W / 2.0 + FOCAL_PX * _dot(d, RIGHT) / depth, H / 2.0 - FOCAL_PX * _dot(d, UP) / depth)


def unproject(px, py, z=0.0):
    """Picture pixel -> the world point on the horizontal plane at height z."""
    cx, cy = (px - W / 2.0) / FOCAL_PX, (H / 2.0 - py) / FOCAL_PX
    ray = tuple(FWD[i] + RIGHT[i] * cx + UP[i] * cy for i in range(3))
    t = (z - POS[2]) / ray[2]
    return (POS[0] + ray[0] * t, POS[1] + ray[1] * t)
