"""Editor-side half of Tools/ue_py.py: runs Python files dropped into <Project>/Saved/PyInbox.

The built-in MCP server has no "run editor Python" tool, so bulk scene / material building
goes through this instead. Start it once per editor session, either by launching with
  UnrealEditor <project>.uproject -ExecCmds="py <repo>/Tools/ue_py_bridge.py"
(the path must not contain spaces; symlink the repo if it does) or by typing
  py "<repo>/Tools/ue_py_bridge.py"
into the editor's Cmd box. It is inert unless something writes to Saved/PyInbox.
Each <name>.py is executed on the game thread and its stdout / traceback is written to
<name>.out (first line OK or ERR).
"""
import contextlib, gc, glob, io, os, sys, traceback
import unreal

_INBOX = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), "PyInbox")
os.makedirs(_INBOX, exist_ok=True)
_state = {"t": 0.0}


def _tick(dt):
    _state["t"] += dt
    if _state["t"] < 0.2:
        return
    _state["t"] = 0.0
    for path in sorted(glob.glob(os.path.join(_INBOX, "*.py"))):
        try:
            with open(path) as f:
                src = f.read()
            os.remove(path)
        except OSError:
            continue
        buf = io.StringIO()
        status = "OK"
        ns = {"__name__": "__main__", "__file__": path, "unreal": unreal}
        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(src, path, "exec"), ns)
        except BaseException:
            status = "ERR"
            buf.write(traceback.format_exc())
        # Free the script's objects NOW. Functions and their globals form reference cycles, and if
        # Python's cycle collector releases Unreal wrappers later, in the middle of an engine garbage
        # collection, the editor crashes (SIGSEGV in the PreGarbageCollect broadcast).
        ns.clear()
        sys.last_traceback = sys.last_value = sys.last_type = None
        gc.collect()
        tmp = path[:-3] + ".tmp"
        with open(tmp, "w") as f:
            f.write(status + "\n" + buf.getvalue())
        os.replace(tmp, path[:-3] + ".out")


if getattr(unreal, "_sr_py_bridge", None) is not None:
    unreal.unregister_slate_post_tick_callback(unreal._sr_py_bridge)
unreal._sr_py_bridge = unreal.register_slate_post_tick_callback(_tick)
unreal.log("SR py bridge listening on " + _INBOX)
