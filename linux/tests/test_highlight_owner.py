from tiptour_linux.highlight_owner import Owner
s=Owner();a=s.begin();f=s.job(a);s.invalidate();assert f.result()==(None,False) and not s.valid(a) and s.begin() is None
s.released();b=s.begin();assert b!=a and s.valid(b)
g=s.job(b);assert not s.publish(a,('old',False));assert s.publish(b,('new',True));assert s.take(b).result()==('new',True)
s.invalidate(close=True);s.released();assert s.begin() is None and not s.publish(b,('late',False))
print('PASS stopinvalidatesfuture/heldblock/newreleasedgesture/tokenpair/closedgate')

s=Owner(); a=s.begin(); assert s.commit(a, {'id':'A'})
s.invalidate(retire_context=False); assert s.committed()=={'id':'A'}
s.released(); b=s.begin(); assert s.committed() is None
assert not s.commit(a, {'id':'staleA'})
assert s.commit(b, {'id':'B'}) and s.committed()=={'id':'B'}
c=s.cancellation(b); assert not c.done(); s.invalidate(); assert c.done() and s.committed() is None
print('PASS committedA/typedpreserves/Bbeginretires/stalepublishrefused/Bcommit/Stopretires+cancelwake')
