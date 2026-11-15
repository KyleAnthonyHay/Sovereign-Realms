"""Scout: a deep team-coloured hood, a long cloak, a light spear on the shoulder. A troop (trained at the castle from
level 3, one at a time) that outruns cavalry, sees a long way and is only noticed from close by; it is no fighter,
"attack" is a two-handed jab down with the spear. Same body, rig and sheet layout as the Builder; its run cycle
covers 192 cm instead of 124. See char_worker.py."""
import char_worker as W

NAME = "scout"
BODY_HEIGHT_CM = W.BODY_HEIGHT_CM
P = W.P
PROPS = W.PROPS
bones = W.bones


def build_mesh(b):
    W.build_mesh(b, NAME)


def animate(rig):
    W.animate(rig, NAME)
