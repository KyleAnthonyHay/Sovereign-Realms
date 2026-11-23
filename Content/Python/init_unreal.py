"""Runs when the editor's Python plugin starts: launches the Tools/ue_py.py bridge.

The bridge (Tools/ue_py_bridge.py) is inert unless something drops a script into Saved/PyInbox, so starting it
with every editor session costs nothing and means the art pipeline never has to be armed by hand.
"""
import os
import unreal

_bridge = os.path.join(os.path.abspath(unreal.Paths.project_dir()), "Tools", "ue_py_bridge.py")
if os.path.exists(_bridge):
    with open(_bridge, encoding="utf-8") as _f:
        exec(compile(_f.read(), _bridge, "exec"), {"__name__": "__main__", "__file__": _bridge, "unreal": unreal})
