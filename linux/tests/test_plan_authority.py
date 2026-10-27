import copy, hashlib, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tiptour_linux.plan_authority import canonical, approved_step
A = {'goal':'Find binary search tree', 'app':'Google Chrome', 'steps':[{'type':'click','label':'Search'}, {'type':'type','value':'binary search tree'}, {'type':'pressKey','value':'Return'}]}
h = hashlib.sha256(canonical(A).encode()).hexdigest()
P = {'state':'approved','displayed':True,'rev':4,'hash':h,'args':copy.deepcopy(A),'id':'tool4'}
C = {'rev':4,'hash':h,'args':copy.deepcopy(A),'v':{'id':'tool4'},'idx':0}
assert approved_step(P,C,A,0,A['steps'][0])
for i in range(3):
    c=copy.deepcopy(C);c['idx']=i
    assert approved_step(P,c,A,i,A['steps'][i])
for key,value in [('state','pending'),('state','revoked'),('displayed',False),('rev',3),('hash','unbound'),('id','model-asserts-approved')]:
    p=copy.deepcopy(P);p[key]=value
    assert not approved_step(p,C,A,0)
for key,value in [('rev',3),('hash','unbound'),('idx',1),('v',{'id':'old'})]:
    c=copy.deepcopy(C);c[key]=value
    assert not approved_step(P,c,A,0)
for target in ('proposal','current','provided'):
    p,c,a=copy.deepcopy(P),copy.deepcopy(C),copy.deepcopy(A)
    (p['args'] if target=='proposal' else c['args'] if target=='current' else a)['steps'][1]['value']='unexpected value'
    assert not approved_step(p,c,a,0)
assert not approved_step(P,C,A,0,{'type':'rightClick','label':'Search'})
for bad in (-1,3,False,'0',None):assert not approved_step(P,C,A,bad)
assert not approved_step(P,{},A,0)
print('approved plan exact revision/hash/args/id/index/step negative checks PASS')
