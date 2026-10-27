"""Scoped native ownership latch for the typed-confirmation retirement await.
X11 events deny only. This never activates, chooses or authorizes a recipient.
"""
from Xlib import display, X
class Watch:
 def __init__(self,loop,owner):
  self.loop=loop;self.d=display.Display();self.changed=False;self.closed=False;self.events=[]
  try:
   self.root=self.d.screen().root;self.atom=self.d.intern_atom('_NET_ACTIVE_WINDOW')
   self.pid_atom=self.d.intern_atom('_NET_WM_PID');self.xid=int(owner['x11_client_id']);self.pid=int(owner['pid'])
   self.root.change_attributes(event_mask=X.PropertyChangeMask)
   self.client=self.d.create_resource_object('window',self.xid)
   self.client.change_attributes(event_mask=X.PropertyChangeMask|X.StructureNotifyMask)
   # Server roundtrip establishes subscription before any asynchronous native read.
   self.d.sync();self.drain()
   if self.active()!=self.xid or self.client_pid()!=self.pid:self.changed=True
   loop.add_reader(self.d.fileno(),self.drain)
  except Exception:
   self.close();raise
 def active(self):
  p=self.root.get_full_property(self.atom,0)
  return int(p.value[0]) if p is not None and len(p.value)>=1 and not any(p.value[1:]) else None
 def client_pid(self):
  p=self.client.get_full_property(self.pid_atom,0)
  return int(p.value[0]) if p is not None and len(p.value)>=1 and not any(p.value[1:]) else None
 def drain(self):
  if self.closed:return
  try:
   while self.d.pending_events():
    e=self.d.next_event();self.events.append((e.type,getattr(getattr(e,"window",None),"id",None),getattr(e,"atom",None)))
    # Any ownership-related notification latches denial, even away-return whose
    # final property value equals its start. No title/process based exceptions.
    if (e.type==X.PropertyNotify and (e.window.id==self.root.id and e.atom==self.atom or e.window.id==self.xid and e.atom==self.pid_atom)) or e.type in (X.DestroyNotify,X.UnmapNotify):self.changed=True
  except Exception as exc:self.changed=True;self.events.append(str(exc))
 def valid(self):
  if self.closed:return False
  try:
   self.d.sync();self.drain()
   same=self.active()==self.xid and self.client_pid()==self.pid
   self.d.sync();self.drain()  # include notifications arriving during the property reads
   return same and not self.changed
  except Exception:return False
 def close(self):
  if self.closed:return
  self.closed=True
  try:self.loop.remove_reader(self.d.fileno())
  except Exception:pass
  try:self.d.close()
  except Exception:pass
