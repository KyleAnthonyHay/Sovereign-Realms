"""Builder: team-coloured hood, leather apron, a big mallet, planks on the back. A troop (trained at the castle)
that raises buildings outside the castle's reach and repairs damaged ones; "attack" is the mallet swing. See
char_worker.py."""
import char_worker as W

NAME = "builder"
BODY_HEIGHT_CM = W.BODY_HEIGHT_CM
P = W.P
PROPS = W.PROPS
bones = W.bones


def build_mesh(b):
    W.build_mesh(b, NAME)


def animate(rig):
    W.animate(rig, NAME)
