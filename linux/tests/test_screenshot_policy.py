import asyncio
from tiptour_linux.screenshot_policy import ScreenshotPolicy
async def main():
 class Client:
  def __init__(self):self.calls=0;self.started=asyncio.Event();self.hold=False;self.release=asyncio.Event()
  async def send_screenshot(self,j):
   self.calls+=1;self.started.set()
   if self.hold:await self.release.wait()
 c=Client();p=ScreenshotPolicy(False)
 assert not await p.send(c,b'x',p.ticket()) and c.calls==0
 p.set_enabled(True);assert await p.send(c,b'x',p.ticket()) and c.calls==1
 c.hold=True;c.started.clear();t=asyncio.create_task(p.send(c,b'x',p.ticket()));await c.started.wait()
 p.set_enabled(False);assert not await t and c.calls==2
 # The second write entered before off. This proves cancellation, not recall.
 assert not await p.send(c,b'x',p.ticket()) and c.calls==2
 p.set_enabled(True);c.hold=False;assert await p.send(c,b'x',p.ticket())
 p.set_enabled(False);t=asyncio.create_task(p.send(c,b'x',p.ticket()));p.set_enabled(True)
 assert not await t # off ticket remains invalid after on
 old=p.ticket();p.set_enabled(False);p.set_enabled(True)
 before=c.calls;assert not await p.send(c,b'x',old) and c.calls==before
 # External cancellation must still cancel the surrounding workflow coroutine.
 c.hold=True;c.started.clear();t=asyncio.create_task(p.send(c,b'x',p.ticket()));await c.started.wait();t.cancel()
 try:await t
 except asyncio.CancelledError:pass
 else:raise AssertionError('external cancel swallowed')
 print('PASS off no dispatch, stale ticket refuses after reenable, in-flight best-effort cancel/no recall, external cancellation propagates')
asyncio.run(main())
