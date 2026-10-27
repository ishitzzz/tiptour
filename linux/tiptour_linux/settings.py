"""Settings file for the Linux port: ~/.config/tiptour-linux/settings.json (override dir with TIPTOUR_CONFIG_DIR). CLI: python3 -m tiptour_linux.settings [list|get K|set K V].
Keys mirror Utilities/TipTourDefaults.swift where the Linux port has the feature. Only the keys below exist; the others (autopilot/CUA driver, detection overlay,
accurate grounding, panel pin, onboarding, permissions, JEV) have no Linux implementation or are deliberately not exposed. In particular the Mac default
isAutopilotEnabled=true is NOT mirrored: actions stay behind the explicit --act flag on the command line and are never enabled from this file.
Settings are applied as env vars by apply_env() (explicit environment wins)."""
import json, os, sys
DEFAULTS = {"isNekoModeEnabled": False,
            "isScreenshotStreamingEnabled": True,   # Mac key: 1 fps frame streaming -> TIPTOUR_STREAM
            "useAtspi": True,                        # Linux: AT-SPI resolver -> TIPTOUR_USE_ATSPI
            "useCdp": True,                          # Linux: Chrome DevTools DOM stage -> TIPTOUR_USE_CDP
            "askTargetWmClass": ""}                  # Linux analogue of the Mac askTargetWmClass: WM_CLASS of the app Ask inserts into; empty = the window focused at press
ENV = {"isNekoModeEnabled": "TIPTOUR_NEKO", "isScreenshotStreamingEnabled": "TIPTOUR_STREAM", "useAtspi": "TIPTOUR_USE_ATSPI", "useCdp": "TIPTOUR_USE_CDP"}
def path(): return os.path.join(os.environ.get("TIPTOUR_CONFIG_DIR") or os.path.expanduser("~/.config/tiptour-linux"), "settings.json")
def load():
    s = dict(DEFAULTS)
    try:
        for k, v in json.load(open(path())).items():
            if k in DEFAULTS and type(v) is type(DEFAULTS[k]): s[k] = v
    except (OSError, ValueError): pass
    return s
def save(k, v):
    if k not in DEFAULTS: raise KeyError(k)
    cur = load(); d = DEFAULTS[k]
    cur[k] = (str(v).lower() in ("1", "true", "yes", "on")) if isinstance(d, bool) else str(v)
    os.makedirs(os.path.dirname(path()), exist_ok=True); json.dump(cur, open(path(), "w"), indent=1)
def apply_env():
    for k, v in load().items():
        if k in ENV and ENV[k] not in os.environ: os.environ[ENV[k]] = "1" if v else "0"
def gtk_window(on_close=None, standalone=True, on_neko_changed=None):
    """Supported toggles. In-app Neko may be live; standalone changes are saved only."""
    import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk
    w = Gtk.Window(title="TipTour Linux settings"); w.set_wmclass("tiptour-settings", "TipTourSettings"); w.set_keep_above(True); b = Gtk.VBox(spacing=6, margin=10); w.add(b); cur = load()
    for k, label in (("isNekoModeEnabled", "Neko cursor (original pixel-art cat)"), ("isScreenshotStreamingEnabled", "Stream screenshots to the model (~1 fps)"), ("useAtspi", "Use AT-SPI element lookup"), ("useCdp", "Use Chrome DevTools DOM stage")):
        c = Gtk.CheckButton(label=label); c.set_active(cur[k]); 
        def changed(x,k=k):
            save(k,x.get_active())
            if k == 'isNekoModeEnabled' and on_neko_changed:on_neko_changed(x.get_active())
        c.connect("toggled", changed); b.pack_start(c, False, False, 0)
    b.pack_start(Gtk.Label(label="Actions (--act) are command-line only. Bounded X11 tests pass; full-platform validation is incomplete."), False, False, 0)
    b.pack_start(Gtk.Label(label="Ask insert target: choose in the Ask preview (stored: %s)" % (cur["askTargetWmClass"] or "window focused at press")), False, False, 0)
    b.pack_start(Gtk.Label(label=("Neko changes this session. Other settings apply to new app/Ask launches.\nExplicit environment settings override saved values." if on_neko_changed else "Changes apply to new app/Ask launches, not this running session.\nExplicit environment settings override saved values.")), False, False, 0)
    for label in b.get_children():
        if isinstance(label, Gtk.Label):
            label.set_line_wrap(True); label.set_max_width_chars(62); label.set_xalign(0)
    if standalone: w.connect("destroy", Gtk.main_quit)
    if on_close: w.connect("destroy", lambda *_: on_close())
    w.show_all(); return w

if __name__ == "__main__":
    a = sys.argv[1:] or ["list"]
    if a[0] == "gui":
        gtk_window(); import gi; from gi.repository import Gtk; Gtk.main(); sys.exit(0)
    if a[0] == "list": print(json.dumps(load(), indent=1))
    elif a[0] == "get": print(load()[a[1]])
    elif a[0] == "set": save(a[1], a[2]); print("ok")

