"""X11 action driver (counterpart of ActionExecutor/TipTourActionDriver, minimal): one step per call, via xdotool.
Gated by the caller (CUA toggle, default OFF = point-only). Refuses obvious secret fields."""
import subprocess, re
SECRET = re.compile(r"password|passcode|\bpin\b|card number|cvv|cvc|verification code|one[- ]time", re.I)
def _x(*a): return subprocess.run(["xdotool", *map(str, a)], capture_output=True, text=True, timeout=10)
def execute(step, px):
    t = (step.get("type") or "click"); label = step.get("label", "")
    if SECRET.search(label) and t in ("type", "setValue"): return {"ok": False, "error": "refused: secret field"}
    if t in ("click", "doubleClick", "rightClick"):
        if px is None: return {"ok": False, "error": "no coordinates"}
        _x("mousemove", px[0], px[1]); _x("click", {"click": "1", "doubleClick": "--repeat 2 1", "rightClick": "3"}[t].split()[-1]) if t != "doubleClick" else _x("click", "--repeat", "2", "1")
        return {"ok": True, "status": "performed " + t, "at": list(px)}
    if t == "type": _x("type", "--delay", "20", step.get("value", "")); return {"ok": True, "status": "typed"}
    if t in ("keyboardShortcut", "pressKey"): _x("key", label.replace("command", "ctrl").replace("+", "+")); return {"ok": True, "status": "key " + label}
    if t == "scroll": _x("click", "--repeat", "3", "5" if step.get("value", "down") == "down" else "4"); return {"ok": True, "status": "scrolled"}
    return {"ok": False, "error": "unsupported step type " + t}
