"""Conservative Linux radial Speak binding, not Mac hover target override.

Only accept a mapped, identified hovered client that is already focused. Never
activate another app or reuse a late target snapshot. Xlib calls can still hang.
"""
import threading
import time


def snapshot(point):
    from Xlib import display, X
    d = display.Display()
    try:
        root = d.screen().root
        prop = root.get_full_property(d.intern_atom('_NET_CLIENT_LIST_STACKING'), X.AnyPropertyType)
        if prop is None: return None
        focus = d.get_input_focus().focus
        if not hasattr(focus, 'id'): return None
        # Root stacking includes WM frames and override-redirect popups. Reject
        # an unknown covering surface instead of reading through decorations.
        clients = {int(wid): d.create_resource_object('window', int(wid)) for wid in prop.value}
        by_root = {}
        for wid,w in clients.items():
            top = w
            for _ in range(16):
                parent = top.query_tree().parent
                if parent.id == root.id: break
                top = parent
            by_root[top.id] = wid
        for top in reversed(root.query_tree().children):
            try:
                if top.get_attributes().map_state != X.IsViewable: continue
                g = top.get_geometry(); pos = root.translate_coords(top, 0, 0)
                if not (pos.x <= point[0] < pos.x+g.width and pos.y <= point[1] < pos.y+g.height): continue
                wid = by_root.get(top.id)
                if wid is None: return None
                w = clients[wid]
                classes = tuple(w.get_wm_class() or ())
                if any('tiptour' in str(c).lower() for c in classes): return None
                pid = w.get_full_property(d.intern_atom('_NET_WM_PID'), X.AnyPropertyType)
                if not classes or pid is None or not len(pid.value): return None
                focus_ids = set()
                f = focus
                for _ in range(12):
                    focus_ids.add(f.id)
                    if f.id == root.id: break
                    f = f.query_tree().parent
                if int(wid) not in focus_ids: return None
                return (int(wid), int(pid.value[0]), classes)
            except Exception: return None
        return None
    finally: d.close()


def request(point, deliver, valid, timeout=.4):
    """Both snapshots plus loop delivery must precede the one deadline."""
    deadline = time.monotonic() + timeout
    lock = threading.Lock(); result = {'sent': False}
    def finish(target):
        with lock:
            if result['sent']: return
            result['sent'] = True
        if valid(): deliver(target, deadline)
    timer = threading.Timer(timeout, lambda: finish(None)); timer.daemon = True; timer.start()
    def run():
        try:
            target = snapshot(point)
            if target is None or not valid() or time.monotonic() >= deadline: target = None
            elif snapshot(point) != target: target = None
        except Exception: target = None
        if time.monotonic() >= deadline: target = None
        finish(target); timer.cancel()
    worker = threading.Thread(target=run, daemon=True, name='tiptour-radial-target'); worker.start()
    return worker
