import sys,os
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..'))
from tiptour_linux.request_chain import Requests,continuation
from tiptour_linux.highlight import no_action_requested
r=Requests();ctx={'rect':[1,2,30,40]}
assert r.accept('Only describe the highlighted text. Do not edit.',ctx,7)=='new'
a=r.snapshot();ctx['rect'][0]=999
assert r.accept('Yes, submit the plan now for app review.')=='continued'
assert r.snapshot()==a and no_action_requested(r.snapshot()['text'])
assert r.accept('Yes submit the plan and write secret words')=='blocked'
assert r.snapshot() is None
assert r.accept('New task: Put hello into a new document')=='new'
b=r.snapshot();assert b['id']!=a['id'] and b['context'] is None
assert r.accept('yes')=='continued' and r.snapshot()==b
r.clear();assert r.accept('submit the plan')=='blocked'
r.accept('Click the button in this highlighted area',{'rect':[1,2,3,4]},9)
a=r.snapshot();r.accept('Submit those exact steps so the app can display the plan for my separate local confirmation. Do not execute until that local confirmation.')
assert r.snapshot()==a
print('PASS original restrictions/scope kept, metacontinuation bounded, mixed ambiguous blocked, distinct goal replaces, orphan continuation blocked')

for text in ['Okay, same task.', 'Continue.', 'Do it, but keep it unsaved.', 'Yes, go ahead with that plan but do not save it.']:
    r=Requests();r.accept('Only describe the highlighted area. Do not edit.', {'rect':[1,2,3,4]}, 7)
    a=r.record.copy();assert r.accept(text)=='blocked' and r.snapshot() is None
    assert r.record==a
r=Requests();r.accept('Only describe, do not edit')
assert r.accept('Write new words')=='blocked'
assert r.accept('New task: Write new words')=='new'
print('PASS unknown/anaphoric followup cannot drop restrictions; explicit independent new-task boundary replaces')
