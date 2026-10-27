import threading,time
from tiptour_linux.read_worker import ReadWorker
queue=[]; worker=ReadWorker(queue.append); result=[]
def call(fn, timeout=.05):
 try: result.append(worker.invoke(fn,timeout=timeout))
 except Exception as e: result.append(type(e).__name__)
# Actual queued timeout before launcher runs: old launcher cannot clear a new job.
t=threading.Thread(target=call,args=(lambda:'never',));t.start();t.join();assert worker.current is None
old=queue.pop(0)
t=threading.Thread(target=call,args=(lambda:'fresh',1));t.start()
while not queue:time.sleep(.001)
old();queue.pop(0)();t.join();assert result[-1]=='fresh'
# Running timeout keeps ownership/backpressure until actual worker exit, blocks late publication.
started=threading.Event();release=threading.Event();published=[]
def slow():
 started.set();release.wait();worker.check();published.append(1)
t=threading.Thread(target=call,args=(slow,));t.start()
while not queue:time.sleep(.001)
queue.pop(0)();started.wait();t.join();assert worker.current['state']=='running'
try: worker.invoke(lambda:'overlap')
except RuntimeError:pass
else:raise AssertionError('overlap')
release.set()
for _ in range(100):
 if worker.current is None:break
 time.sleep(.005)
assert not published and worker.current is None
# Queued explicit cancellation also frees ownership.
t=threading.Thread(target=call,args=(lambda:'cancelled',1));t.start()
while not queue:time.sleep(.001)
worker.cancel_current();t.join();assert worker.current is None
queue.pop(0)();assert worker.current is None
print('owned read worker: queued timeout/cancel, old launcher, running timeout/backpressure/no late publication pass')

# Cancel precisely after the worker produced a value but before final response.
ready=threading.Event();finish=threading.Event()
def before_response():
 ready.set();finish.wait();return 'stale payload'
t=threading.Thread(target=call,args=(before_response,1));t.start()
while not queue:time.sleep(.001)
queue.pop(0)();ready.wait();worker.cancel_current();finish.set();t.join()
assert result[-1]=='RuntimeError',result
for _ in range(100):
 if worker.current is None:break
 time.sleep(.005)
assert worker.current is None
print('cancel before response: no stale result, atomic final check/completion pass')
