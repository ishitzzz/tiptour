"""Owned proactive local grounding lifecycle. Request-specific resolution is separate."""
import asyncio,threading
class GroundingRefresh:
    def __init__(self,enabled,clear,refresh,log=lambda *a:None):
        self._lock=threading.RLock();self.enabled=bool(enabled);self.epoch=0
        self.clear,self.refresh,self.log=clear,refresh,log
        self.tasks=set();self.pending=None;self.closed=False;self.active=set();self.serial=0;self.task_tickets={};self.revoked=set()
    def ticket(self):
        with self._lock:return self.epoch if self.enabled and not self.closed else None
    def eligible(self,ticket):
        with self._lock:
            epoch=ticket[0] if isinstance(ticket,tuple) else ticket
            return ticket is not None and self.enabled and not self.closed and epoch==self.epoch and (not isinstance(ticket,tuple) or ticket in self.active)
    def publish(self,ticket,fn):
        with self._lock:
            if not self.eligible(ticket):return False
            fn();return True
    async def _refresh(self,reason,epoch):
        with self._lock:
            if not self.eligible(epoch) or asyncio.current_task() in self.revoked:return
            self.serial+=1;ticket=(epoch,self.serial);self.active.add(ticket);self.task_tickets[asyncio.current_task()]=ticket
        try:await self.refresh(reason,ticket)
        finally:
            with self._lock:
                self.active.discard(ticket);self.task_tickets.pop(asyncio.current_task(),None)
    def _cancel(self,task):
        with self._lock:
            self.revoked.add(task);self.active.discard(self.task_tickets.get(task))
        task.cancel()
    def _track(self,coro):
        task=asyncio.create_task(coro);self.tasks.add(task);task.add_done_callback(self.tasks.discard);task.add_done_callback(self.revoked.discard);return task
    def set_enabled(self,enabled):
        with self._lock:
            if self.closed or self.enabled==bool(enabled):return
            self.enabled=bool(enabled);self.epoch+=1;self.active.clear()
            for task in list(self.tasks):self._cancel(task)
            if not self.enabled:self.clear()
        if self.enabled:self.schedule('enabled',0)
    def schedule(self,reason,delay=.15):
        ticket=self.ticket()
        if ticket is None:return
        if self.pending and not self.pending.done():self._cancel(self.pending)
        async def run():
            try:
                await asyncio.sleep(delay)
                if self.eligible(ticket):await self._refresh(reason,ticket)
            except asyncio.CancelledError:raise
            except Exception as exc:self.log('proactive grounding unavailable',type(exc).__name__)
        self.pending=self._track(run())
    def post_action(self):
        ticket=self.ticket()
        if ticket is None:return
        old=getattr(self,'action',None)
        if old and not old.done():self._cancel(old)
        async def run():
            try:
                await asyncio.sleep(.18)
                if self.eligible(ticket):await self._refresh('action changed UI',ticket)
                await asyncio.sleep(.36)
                if self.eligible(ticket):await self._refresh('action settle',ticket)
            except asyncio.CancelledError:raise
            except Exception as exc:self.log('post-action grounding unavailable',type(exc).__name__)
        self.action=self._track(run())
    def close(self):
        with self._lock:
            self.closed=True;self.epoch+=1;self.active.clear()
            for task in list(self.tasks):self._cancel(task)
            self.clear()
