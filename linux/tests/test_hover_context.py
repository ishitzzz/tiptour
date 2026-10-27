"""Pure binding and deadlines, not native execution."""
import copy,time,threading
from tiptour_linux import hover_context as h
ctx={'owner':7,'at':time.monotonic(),'window':{'title':'owned','pid':1},'text_selection':{'text':'world','role':'text'},'native_range':{'text':'hello world tail','selection':[6,11],'identity':{'pid':1},'xwindow':'12'}}
a={'app':'wrong','steps':[{'type':'click','label':'world'},{'type':'type','value':'NEW','targetContext':'currentSelection'},{'type':'type','value':'!'}]}
r=h.bind(a,None,ctx);assert r['app']=='owned' and len(r['steps'])==2 and all(x['_native_range']==ctx['native_range'] for x in r['steps'])
r['steps'][0]['_native_range']['text']='mutated';assert ctx['native_range']['text']=='hello world tail' and a['app']=='wrong'
for kind in ['openApp','openURL']:
 b=copy.deepcopy(a);b['steps'].append({'type':kind});assert h.bind(b,None,ctx)==b
paint=copy.deepcopy(ctx);paint['window']['title']='painted';assert h.bind(a,paint,ctx)['app']=='painted'
b={'app':'original','steps':[{'type':'type','value':'hello','_native_range':{'forged':1}}]};assert h.bind(b,None,ctx)=={'app':'original','steps':[{'type':'type','value':'hello'}]}
assert h.alive(ctx,7) and not h.alive(ctx,8) and not h.alive(ctx,7,lambda:ctx['at']+300)
assert 'world' in h.prompt(ctx) and 'hello world tail' not in h.prompt(ctx)
h.capture=lambda *a:(time.sleep(.1) or ctx);got=[]
w=h.request(None,None,7,lambda:True,lambda c,d:got.append(c),timeout=.02);w.join(1);assert got==[None]
got=[];w=h.request(None,None,7,lambda:False,lambda c,d:got.append(c),timeout=.02);w.join(1);assert got==[]
print('PASS pure owned hover binding/precedence/explicitcontext/open exclusion/deepcopy/expiry/promptcap/timeout/invalidowner')
