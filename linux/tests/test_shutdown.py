import asyncio
from tiptour_linux.shutdown import retire
class Client:
 def __init__(self, mode):self.calls=0;self.mode=mode
 async def close(self):
  self.calls+=1
  if self.mode=='fail':raise RuntimeError('test')
  if self.mode=='stall':await asyncio.sleep(10)
async def main():
 for mode,expected in [('ok','closed'),('fail','failed'),('stall','pending')]:
  c=Client(mode);r=await retire(None,c,.02)
  assert c.calls==1 and r['client']==expected,(mode,r,c.calls)
 c=Client('ok');w=asyncio.create_task(asyncio.sleep(10));await asyncio.sleep(0)
 r=await retire(w,c,.02);assert r=={'writer':'cancelled','client':'closed'}
 # Cancellation-resistant fake is released after the bounded result so test loop can exit.
 release=asyncio.Event()
 async def resistant():
  while not release.is_set():
   try:await release.wait()
   except asyncio.CancelledError:continue
 w=asyncio.create_task(resistant());await asyncio.sleep(0)
 c=Client('ok');r=await retire(w,c,.02)
 assert r['writer']=='pending' and c.calls==1
 release.set();await asyncio.wait_for(w,.2)
 print('PASS resistant writer returns pending, never falsely closed; test releases it explicitly')
 print('PASS close once; closed/failure/stall distinct; writer cancellation settled')
asyncio.run(main())
