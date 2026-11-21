"""Medic: a field medic / barber-surgeon. Knee-length linen work tunic with the sleeves rolled, a leather bib apron,
team sash, armbands, neckerchief and headband, a big leather medical bag slung across the body, rolled bandages on
the strap, a flask on the belt and a rolled bandage in the right hand. Bare-headed; no staff, no weapon. A troop that
does not fight: "attack" is the heal, he drops to one knee and binds a wound in front of him on frame 4, looped by
the game while it heals. Same body, rig and sheet layout as the Builder. See char_worker.py."""
import char_worker as W

NAME = "medic"
BODY_HEIGHT_CM = W.BODY_HEIGHT_CM
P = W.P
PROPS = W.PROPS
bones = W.bones


def build_mesh(b):
    W.build_mesh(b, NAME)


def animate(rig):
    W.animate(rig, NAME)
