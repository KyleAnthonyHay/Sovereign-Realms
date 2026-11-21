"""Hind (the red deer's doe): the stag without antlers or ruff, a little slighter. See char_deer.py."""
import char_deer as D

NAME = "doe"
BODY_HEIGHT_CM = 118.0
IK_CHAINS = D.IK_CHAINS
IK_PREFIXES = D.IK_PREFIXES
bones = D.bones
animate = D.animate


def build_mesh(b):
    D.build_mesh(b, stag=False)
