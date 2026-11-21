#!/usr/bin/env python3
"""Tiny CLI client for the Unreal Editor's built-in MCP server (HTTP, default 127.0.0.1:8000/mcp).

Usage:
  ue_mcp.py toolsets                         # list toolsets
  ue_mcp.py describe <toolset_name>          # tools + input schemas in a toolset
  ue_mcp.py call <toolset_name> <tool> '<json args>'
  ue_mcp.py raw <method> '<json params>'     # any JSON-RPC method
  Add --img <path.png> to any command: base64 images in the result are written
  to that file (img.png, img_1.png, ...) and replaced by their path in the output.
The editor must be running with the SovereignRealms project open.
"""
import json, os, sys, urllib.request

URL = os.environ.get("UE_MCP_URL", "http://127.0.0.1:8000/mcp")
HDRS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

def post(body, sid=None):
    h = dict(HDRS)
    if sid: h["Mcp-Session-Id"] = sid
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        raw = r.read().decode("utf-8", "replace")
        return r.headers.get("Mcp-Session-Id"), (json.loads(raw) if raw.strip() else None)

def session():
    sid, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "ue_mcp_cli", "version": "1"}}})
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    return sid

def rpc(method, params):
    sid = session()
    _, res = post({"jsonrpc": "2.0", "id": 2, "method": method, "params": params}, sid)
    return res

IMG_OUT = None

def _strip_images(obj, saved):
    import base64
    if isinstance(obj, dict):
        mt = obj.get("mimeType", "")
        if isinstance(obj.get("data"), str) and mt.startswith("image/") and IMG_OUT and obj["data"]:
            root, ext = os.path.splitext(IMG_OUT)
            path = IMG_OUT if not saved else f"{root}_{len(saved)}{ext or '.png'}"
            with open(path, "wb") as f: f.write(base64.b64decode(obj["data"]))
            saved.append(path); return {"mimeType": mt, "savedTo": path}
        return {k: _strip_images(v, saved) for k, v in obj.items()}
    if isinstance(obj, list): return [_strip_images(v, saved) for v in obj]
    if isinstance(obj, str) and IMG_OUT and '"mimeType"' in obj and '"data"' in obj:
        try: return json.dumps(_strip_images(json.loads(obj), saved))
        except Exception: return obj
    return obj

def show(res):
    if res is not None and IMG_OUT:
        saved = []; res = _strip_images(res, saved)
        for pth in saved: print("saved image:", os.path.abspath(pth))
    if res is None: print("(no response)"); return
    if "error" in res: print("ERROR:", json.dumps(res["error"], indent=1)); sys.exit(1)
    r = res.get("result", {})
    for c in r.get("content", []):
        print(c.get("text", json.dumps(c)))
    if "content" not in r: print(json.dumps(r, indent=1))
    if r.get("isError"): sys.exit(1)

def main(a):
    if not a: print(__doc__); return
    cmd = a[0]
    if cmd == "toolsets": show(rpc("tools/call", {"name": "list_toolsets", "arguments": {}}))
    elif cmd == "describe": show(rpc("tools/call", {"name": "describe_toolset", "arguments": {"toolset_name": a[1]}}))
    elif cmd == "call":
        args = json.loads(a[3]) if len(a) > 3 else {}
        show(rpc("tools/call", {"name": "call_tool", "arguments": {"toolset_name": a[1], "tool_name": a[2], "arguments": args}}))
    elif cmd == "raw": show(rpc(a[1], json.loads(a[2]) if len(a) > 2 else {}))
    else: print(__doc__)

if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--img" in argv:
        i = argv.index("--img"); IMG_OUT = argv[i + 1]; del argv[i:i + 2]
    main(argv)
