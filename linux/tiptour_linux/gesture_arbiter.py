"""Pure modifier arbitration for the opt-in combined Linux input mode.

Pinned genuine cross-chord transitions are preserved: end the old owner and
begin the newly matched chord on the same sample. Only explicit Stop blocks
until all modifiers release. Standalone monitors do not use this class yet.
"""
from Xlib import X

MODIFIERS = X.ControlMask | X.ShiftMask | X.Mod1Mask | X.Mod4Mask

def mode(mask):
    ctrl, shift = bool(mask & X.ControlMask), bool(mask & X.ShiftMask)
    alt, super_ = bool(mask & X.Mod1Mask), bool(mask & X.Mod4Mask)
    if ctrl and alt and super_ and not shift: return 'radial'
    if ctrl and shift and not alt and not super_: return 'highlight'
    return None

class Arbiter:
    """Returns (kind, owner, point, ask_local) tuples; tokens belong to the adapter."""
    def __init__(self):
        self.active = None; self.blocked = False; self.last = None; self.closed = False
    def stop(self, close=False):
        old = self.active
        self.active = None; self.last = None; self.blocked = True; self.closed |= close
        return [('cancel', old, None, False)] if old else []
    def sample(self, mask, point):
        if self.closed: return []
        if not (mask & MODIFIERS):
            events = [('end', self.active, point, False)] if self.active else []
            self.active = None; self.blocked = False; self.last = point
            return events
        if self.blocked: return []
        current = mode(mask)
        if self.active and current != self.active:
            old = self.active
            ask = old == 'highlight' and bool(mask & X.ControlMask and mask & X.ShiftMask and mask & X.Mod1Mask)
            self.active = current; self.last = point
            events = [('end', old, point, ask)]
            if current: events.append(('begin', current, point, False))
            return events
        if not self.active and current:
            self.active = current; self.last = point
            return [('begin', current, point, False)]
        if self.active and point != self.last:
            self.last = point
            return [('move', self.active, point, False)]
        return []

from dataclasses import dataclass

@dataclass(frozen=True)
class Transition:
    kind: str
    owner: str | None
    gesture: int
    point: tuple | None
    ask_local: bool = False

@dataclass(frozen=True)
class Batch:
    generation: int
    sequence: int
    events: tuple

class Monitor:
    """One worker-owned X display, ordered immutable batches, bounded close.

    post(batch) must enqueue quickly in FIFO order. Only Stop/error/close change
    cancellation generation. Gesture IDs distinguish legitimate end-old and
    begin-new transitions without invalidating either. deliver(batch, fn) is the
    guarded synchronous consumer, not authority for later asynchronous work.
    """
    def __init__(self, post, hz=60, display_factory=None, retire=None):
        import threading
        self.retire = retire; self.post = post; self.dt = 1 / hz; self.factory = display_factory
        self.lock = threading.RLock(); self.closed = threading.Event()
        self.state = Arbiter(); self.generation = 0; self.gesture = 0
        self.sequence = 0; self.delivered = 0; self.thread = None; self.failed = False
    def valid(self, generation):
        with self.lock: return not self.closed.is_set() and not self.failed and generation == self.generation
    def _publish(self, events):
        if not events: return
        transitions = []
        for kind, owner, point, ask in events:
            if kind == 'begin': self.gesture += 1
            transitions.append(Transition(kind, owner, self.gesture, tuple(point) if point is not None else None, ask))
        self.sequence += 1
        self.post(Batch(self.generation, self.sequence, tuple(transitions)))
    def sample(self, mask, point):
        # Shared with deterministic tests; real calls come from the sampler only.
        with self.lock:
            if not self.closed.is_set() and not self.failed: self._publish(self.state.sample(mask, point))
    def deliver(self, batch, fn):
        with self.lock:
            failure_notice = self.failed and len(batch.events) == 1 and batch.events[0].kind == 'error'
            eligible = lambda: not self.closed.is_set() and batch.generation == self.generation and (not self.failed or failure_notice)
            if not eligible() or batch.sequence <= self.delivered: return False
            # FIFO is required. Do not silently skip a missing genuine end.
            if batch.sequence != self.delivered + 1: return False
            self.delivered = batch.sequence
            for event in batch.events:
                if not eligible(): return False
                try: fn(event)
                except Exception:
                    if not failure_notice: self._fail()
                    return False
            return True
    def _fail(self):
        # One terminal error batch can retire both consumers, but valid() stays
        # false so no later async continuation can treat a dead sampler as live.
        if self.failed or self.closed.is_set(): return
        self.failed = True; self.generation += 1; self.delivered = self.sequence
        self.state.stop(close=True)
        if self.retire: self.retire(self.generation)
        self._publish([('error', None, None, False)])
    def start(self):
        import threading
        with self.lock:
            if self.thread or self.closed.is_set() or self.failed: return
            self.thread = threading.Thread(target=self.run, daemon=True, name='tiptour-gestures')
            self.thread.start()
    def stop(self):
        with self.lock:
            if self.failed or self.closed.is_set(): return
            self.generation += 1
            self.delivered = self.sequence  # stale queued generation is retired
            self.state.stop()
            self._publish([('cancel', None, None, False)])
    def close(self):
        with self.lock:
            self.closed.set(); self.generation += 1; self.state.stop(close=True)
        if self.thread: self.thread.join(.5)
        return not self.thread or not self.thread.is_alive()
    def run(self):
        from Xlib import display
        d = None
        try:
            d = (self.factory or display.Display)(); root = d.screen().root
            while not self.closed.wait(self.dt):
                q = root.query_pointer()
                self.sample(q.mask, (q.root_x, q.root_y))
        except Exception:
            with self.lock:
                if not self.closed.is_set():
                    self._fail()
        finally:
            if d:
                try: d.close()
                except Exception: pass
