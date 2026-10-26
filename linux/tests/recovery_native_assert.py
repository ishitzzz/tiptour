import json,time,os,threading,subprocess
from pathlib import Path
from tiptour_linux import actions as a,atspi_resolver as ar
D=Path(os.environ['FIXTURE_DIR']);rows=[];counter=0
def cmd(**kw):
 global counter
 counter+=1;kw['seq']=counter;(D/'command.json').write_text(json.dumps(kw));time.sleep(.15)
def state():return json.loads((D/'state.json').read_text())
def run(name,step,want):
 r=a.execute(step,None,'Recovery Native Target');time.sleep(.12);rows.append({'name':name,'result':r,'state':state()});assert r['ok']==want,(name,r);return r
cmd(field='first',focus=True,text='hello old world',selection=[6,9]);run('selected-type',{'type':'type','value':'NEW'},True);assert state()['first']['text']=='hello NEW world',state();assert state()['first']['caret']==9,state()
run('next-caret-insert',{'type':'type','value':'!'},True);assert state()['first']['text']=='hello NEW! world'
cmd(field='first',focus=True,text='aé😀z',selection=[1,3]);run('unicode-selected-type',{'type':'type','value':'好'},True);assert state()['first']['text']=='a好z';assert state()['first']['caret']==2
run('setValue',{'type':'setValue','value':'whole'},True);assert state()['first']['text']=='whole'
for field in ['secret','readonly','button']:
 cmd(field=field,focus=True);before=state();run(field+'-refusal',{'type':'type','value':'NEVER'},False);assert state()==before
cmd(field='first',focus=True);f=ar._sub(['--focus','Recovery Native Target'],5)['focus'];x=subprocess.check_output(['xdotool','getactivewindow'],text=True).strip();cmd(field='second',focus=True)
r=json.loads(a._run([os.sys.executable,'-m','tiptour_linux.atspi_resolver','--focused-write'],7,'stale field test',json.dumps({'operation':'type','text':'NEVER','app':'Recovery Native Target','identity':f['identity'],'xwindow':x})));rows.append({'name':'stale-native-field','result':r,'state':state()});assert not r['ok'];assert state()['second']['text']==''
# Force focus to change AFTER one of the actual repeated scroll key dispatches.
cmd(field='first',focus=True);real_x=a._x;sent=[]
def x(*v):
 r=real_x(*v)
 if v[0]=='key':
  sent.append(v);cmd(field='second',focus=True)
 return r
a._x=x
r=run('continuation-focus-drift',{'type':'scroll','direction':'down','amount':5},False);a._x=real_x;assert len(sent)==1,sent
cmd(field='first',focus=True,modal=True);run('modal-refusal',{'type':'type','value':'NEVER'},False);cmd(field='first',modal=False)
# Unavailable modal check is a refusal, not no-dialog. Shim is explicitly labelled simulated.
real_m=ar.modal_title;ar.modal_title=lambda *args:('unavailable',None);run('simulated-modal-unavailable',{'type':'pressKey','label':'Escape'},False);ar.modal_title=real_m
# Cancel after first real key and assert no further dispatch.
cmd(field='first',focus=True);ev=threading.Event();sent=[]
def xc(*v):
 r=real_x(*v)
 if v[0]=='key': sent.append(v);ev.set()
 return r
a._x=xc;r=a.execute({'type':'scroll','direction':'down','amount':50},None,'Recovery Native Target',None,ev);a._x=real_x;assert not r['ok'] and len(sent)==1,(r,sent);rows.append({'name':'direct-cancel-after-real-key','result':r,'keys':len(sent)})
(D/'assertions.json').write_text(json.dumps(rows,indent=2));print('ASSERTED',len(rows),'direct cases (no model; drift/cancel hooks explicitly test-only)')
