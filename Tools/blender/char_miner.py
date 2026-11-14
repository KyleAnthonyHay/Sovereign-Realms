"""Miner: leather cap, pickaxe, a basket of ore with gold flecks. See char_worker.py."""
import char_worker as W

NAME = "miner"
BODY_HEIGHT_CM = W.BODY_HEIGHT_CM
P = W.P
PROPS = W.PROPS
bones = W.bones


def build_mesh(b):
    W.build_mesh(b, NAME)


def animate(rig):
    W.animate(rig, NAME)
