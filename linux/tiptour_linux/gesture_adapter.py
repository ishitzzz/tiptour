"""Synchronous batch consumer; no GTK, provider or desktop mutation by itself."""
from .gesture_arbiter import Monitor

class Adapter:
    def __init__(self, schedule, radial, begin, move, commit, cancel, error, **monitor_options):
        self.schedule = schedule
        self.radial = radial; self.begin = begin; self.move = move
        self.commit = commit; self.cancel = cancel; self.error = error
        self.points = {}; self.applied = {}; self.cleanup_errors = []; self.monitor = Monitor(self.post, **monitor_options)
    def post(self, batch):
        # Exactly one consumer call per native sample; schedule must preserve FIFO.
        self.schedule(lambda: self.monitor.deliver(batch, self.transition))
    def transition(self, event):
        if event.kind in ('error', 'cancel') and event.owner is None:
            self.retire_all(report_error=event.kind == 'error')
            return
        key = (self.monitor.generation, event.gesture)
        if event.kind == 'begin': self.applied[event.owner] = key
        elif event.kind in ('end', 'cancel'): self.applied.pop(event.owner, None)
        if event.owner == 'radial':
            self.radial(event.kind, event.point, key); return
        if event.owner != 'highlight': return
        if event.kind == 'begin':
            self.points[key] = [event.point]; self.begin(event.point, key)
        elif event.kind == 'move' and key in self.points:
            pts = self.points[key]; last = pts[-1]
            if (event.point[0]-last[0])**2 + (event.point[1]-last[1])**2 >= 9:
                pts.append(event.point); self.move(tuple(pts), key)
        elif event.kind == 'end':
            pts = self.points.pop(key, None)
            if pts is not None: self.commit(tuple(pts), event.ask_local, key)
        elif event.kind == 'cancel':
            self.points.pop(key, None); self.cancel(key)
    def retire_all(self, report_error=False):
        self.points.clear(); self.applied.clear()
        # One failed cleanup cannot suppress the other owner or the error status.
        # Store only exception type/phase, never private callback content.
        callbacks = [('radial', lambda: self.radial('cancel', None, None)),
                     ('highlight', lambda: self.cancel(None))]
        if report_error: callbacks.append(('status', self.error))
        for phase, callback in callbacks:
            try: callback()
            except Exception as exc: self.cleanup_errors.append((phase, type(exc).__name__))
    def start(self): self.monitor.start()
    def stop(self): self.monitor.stop()
    def close(self):
        # Consumer/UI thread only. Native join and callback cleanup have separate
        # outcomes; a callback fault is recorded, never silently called clean.
        result = self.monitor.close()
        self.retire_all()
        return result and not self.cleanup_errors
