"""One process policy for provider image disclosure, separate from local capture.

Disable invalidates queued sends immediately. Already-started provider writes may
have accepted bytes and cannot be recalled. Cancellation is best effort only.
"""
import asyncio
import threading

PRIVACY_START = "Privacy mode is active: screenshot streaming is disabled for this session. You cannot see the user's screen unless the user explicitly provides visual context in text. Use voice instructions, app names, accessibility labels, workflow tools, and local action execution. Do not claim that you can see the screen."
PRIVACY_OFF = 'Privacy mode is now active: screenshot streaming has been disabled. Stop using visual assumptions from previous frames. Continue from voice instructions, local accessibility labels, and tool results only.'

class ScreenshotPolicy:
    def __init__(self, enabled):
        self._enabled=bool(enabled);self._epoch=0;self._lock=threading.Lock();self._pending={}
    @property
    def enabled(self):
        with self._lock:return self._enabled
    def ticket(self):
        with self._lock:return self._epoch if self._enabled else None
    def set_enabled(self, enabled):
        with self._lock:
            enabled=bool(enabled)
            if self._enabled==enabled:return False
            self._enabled=enabled;self._epoch+=1
            pending=list(self._pending.items()) if not enabled else []
        for revoked,loop in pending:
            def revoke(f=revoked):
                if not f.done():f.set_result(None)
            loop.call_soon_threadsafe(revoke)
        return True
    async def send(self, client, jpeg, ticket):
        loop=asyncio.get_running_loop()
        with self._lock:
            if not self._enabled or ticket is None or ticket!=self._epoch:return False
            epoch=ticket
        async def dispatch():
            # No await between the policy check and entry into the client call.
            with self._lock:
                if not self._enabled or self._epoch!=epoch:return False
            await client.send_screenshot(jpeg)
            return True
        task=loop.create_task(dispatch());revoked=loop.create_future()
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        with self._lock:
            self._pending[revoked]=loop
            if not self._enabled or self._epoch!=epoch:revoked.set_result(None)
        try:
            done,_=await asyncio.wait((task,revoked),return_when=asyncio.FIRST_COMPLETED)
            if revoked in done:
                task.cancel()
                await asyncio.wait((task,),timeout=.2)
                return False
            return task.result()
        finally:
            if not task.done():task.cancel()
            revoked.cancel()
            with self._lock:self._pending.pop(revoked,None)
