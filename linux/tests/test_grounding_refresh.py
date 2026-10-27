import asyncio
from tiptour_linux.grounding_refresh import GroundingRefresh
async def run():
 published=[];entered=asyncio.Event();release=asyncio.Event()
 async def refresh(reason,ticket):
  entered.set()
  try:await release.wait()
  except asyncio.CancelledError:await release.wait() # simulate a worker which cannot be stopped
  g.publish(ticket,lambda:published.append(reason))
 g=GroundingRefresh(False,lambda:published.clear(),refresh)
 assert g.ticket() is None
 g.schedule('off',0);await asyncio.sleep(.01);assert not entered.is_set()
 g.set_enabled(True);old=g.ticket();await entered.wait();g.set_enabled(False);g.set_enabled(True);new=g.ticket();assert old!=new and not g.publish(old,lambda:published.append('stale'))
 release.set();await asyncio.sleep(.03);assert 'enabled' in published and len(published)==1,published
 g.set_enabled(False);assert published==[]
 assert not g.publish(new,lambda:published.append('late'))
 g.close();g.set_enabled(True);assert g.ticket() is None
 print('PASS off/no work, held stale worker, rapid off/on epoch, fresh publication, disable clear, close')
asyncio.run(run())
async def reschedule():
 published=[];entered=asyncio.Event();release=asyncio.Event();tickets=[]
 async def refresh(reason,ticket):
  tickets.append(ticket)
  if reason=='old':
   entered.set()
   try:await release.wait()
   except asyncio.CancelledError:await release.wait()
  g.publish(ticket,lambda:published.append(reason))
 g=GroundingRefresh(True,lambda:None,refresh)
 g.schedule('old',0);await entered.wait();g.schedule('new',0)
 assert not g.publish(tickets[0],lambda:published.append('stale'))
 release.set();await asyncio.sleep(.04)
 assert published==['new'],published
 g.post_action();await asyncio.sleep(.6)
 assert published==['new','action changed UI','action settle'],published
 g.close();print('PASS same-epoch reschedule immediately revokes held worker; postaction two refreshes')
asyncio.run(reschedule())
