"""One owned read job. Queued cancellation cannot strand busy state.

A running operation is cooperative: cancellation stops publication and later
stages, not a native call already in flight. No replacement starts until exit.
"""
import threading
from concurrent.futures import Future


class ReadWorker:
    def __init__(self, schedule):
        self.schedule = schedule
        self.lock = threading.RLock()
        self.current = None
        self.local = threading.local()

    def check(self):
        job = getattr(self.local, 'job', None)
        if job is None or job['cancel'].is_set(): raise RuntimeError('read expired')

    def publish(self, fn):
        with self.lock:
            self.check()
            return fn()

    def cancel_current(self):
        with self.lock:
            job = self.current
            if job is None: return
            job['cancel'].set()
            if job['state'] == 'queued':
                job['state'] = 'cancelled'
                self.current = None
                if not job['future'].done(): job['future'].set_exception(RuntimeError('queued read cancelled'))

    def invoke(self, fn, eligible=lambda: True, timeout=15):
        with self.lock:
            if self.current is not None: raise RuntimeError('read worker busy')
            job = dict(state='queued', cancel=threading.Event(), future=Future())
            self.current = job
        def launch():
            with self.lock:
                if self.current is not job or job['cancel'].is_set(): return
                if not eligible():
                    self.current = None; job['state']='cancelled'
                    job['future'].set_exception(RuntimeError('runtime active')); return
                job['state']='running'
                def run():
                    self.local.job=job
                    try:
                        self.check(); result=fn()
                        with self.lock:
                            self.check()
                            if self.current is not job: raise RuntimeError('read ownership lost')
                            if not job['future'].done(): job['future'].set_result(result)
                    except BaseException as error:
                        if not job['future'].done(): job['future'].set_exception(error)
                    finally:
                        with self.lock:
                            job['state']='finished'
                            if self.current is job: self.current=None
                        self.local.job=None
                threading.Thread(target=run,daemon=True,name='owned-read-worker').start()
        self.schedule(launch)
        try: return job['future'].result(timeout)
        except BaseException:
            with self.lock:
                job['cancel'].set()
                if job['state']=='queued' and self.current is job:
                    job['state']='cancelled';self.current=None
            raise
