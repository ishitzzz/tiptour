"""Offline cases ported from pinned TipTourTests/JevTests.swift. No requests."""
import copy
from tiptour_linux.jev import *

def candidate(id='save', label='Save', centre=(0,0)):
 return Candidate(id,label,'ocr',1,centre)
def answers(choice='save', absent=.1, probability=.9, kind='click'):
 return dict(pick=dict(choice=choice,probabilities={choice:probability}),done=dict(noul=.1),absent=dict(noul=absent),kind=dict(choice=kind))
def rejects(data,pool=None):
 try: grounding_decision(data,pool or [candidate()])
 except ValueError: return
 raise AssertionError(data)
r=grounding_request('Save',[candidate('id-'+str(i),'Button '+str(i)) for i in range(300)])
assert len(r['pool'])==200 and len(r['questions']['pick']['criteria'])==201 and NONE_KEY in r['questions']['pick']['criteria']
assert {x['id'] for x in r['state']['screen_elements']} == set(r['questions']['pick']['criteria'])-{NONE_KEY}
r=grounding_request('Save',[candidate(),candidate(label='Other'),candidate(NONE_KEY),candidate('')])
assert len(r['pool'])==1
assert grounding_request('Save',[]) is None
assert grounding_request('Save',[candidate()],excluding=['save']) is None
r=grounding_request('Save',[candidate('a'),candidate('b'),candidate('b','Other')])
assert len(r['pool'])==1 # description duplicate reserves b, as Swift short-circuit inserts ID
assert candidate(centre=(-3.7,4.9)).description=='Save [ocr] at (-3,4)'
a=answers(NONE_KEY);a['pick']['probabilities']={NONE_KEY:.9,'save':.1}
d=grounding_decision(a,[candidate()]);assert d.best[0].id=='save' and d.stop_reason=='target_absent'
assert grounding_decision(answers(absent=.9),[candidate()]).stop_reason is None
assert grounding_decision(answers(probability=.2),[candidate()]).best[0].id=='save'
rejects(answers('invented'));rejects(answers(kind='type'));rejects({})
a=answers();del a['pick']['probabilities'];rejects(a)
for prob in (1.5,-.1,float('nan'),float('inf'),10**400,True,'0.8'):
 rejects(answers(probability=prob))
a=answers();a['pick']['probabilities']={'save':.3,'cancel':.7};rejects(a,[candidate(),candidate('cancel','Cancel')])
rejects(answers(absent=1.4))
a=answers();a['pick']['probabilities']={'save':.9,'invented':.1};rejects(a)
a=answers('b');a['pick']['probabilities']={'a':.5,'b':.5};d=grounding_decision(a,[candidate('a','Alpha'),candidate('b','Beta')]);assert d.best[0].id=='b'
assert request_body('typesafeDirect',{}, {})['model']=='jev-latest'
assert request_body('openRouter',{}, {})['model']=='~typesafe/jev-latest'
try: request_body('typesafeDirect',{}, {'x':dict(type='choice',criteria={str(i):str(i) for i in range(256)})})
except ValueError: pass
else: raise AssertionError('choice cap')
assert response_metrics({'model':4,'usage':{'input_tokens':'x','cost':'bad'},'provider':7},'typesafeDirect',12)==dict(milliseconds=12,inputTokens=0,model='jev-latest',cost=None,provider=None)
assert response_metrics({'usage':{'input_tokens':7,'cost':.02},'provider':'TypeSafe'},'openRouter',9)['cost']==.02
print('JEV offline contract: pass (bounded requests, none escape, current-pool validation, ties, malformed/unknown/nonfinite rejection, independent provider metadata)')

import json
for bad in ('NaN','Infinity','-Infinity','1e999',str(10**400)):
 try: parse_response('{"answers":{},"usage":{"cost":'+bad+'}}')
 except ValueError: pass
 else: raise AssertionError(bad)
for bad in (float('nan'),float('inf'),10**400):
 try: response_metrics({'usage':{'cost':bad}},'typesafeDirect',1)
 except ValueError: pass
 else: raise AssertionError(bad)
assert parse_response('{"answers":{},"usage":{"cost":0.2}}')['usage']['cost']==.2
print('strict JEV response numeric boundary and huge probability: pass')
