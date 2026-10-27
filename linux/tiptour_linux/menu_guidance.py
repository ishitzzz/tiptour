"""Private native proof for one explicitly requested Edit menu teaching target.

No action-mode exemption, provider fields, generic destructive-label exception or
fallback from unavailable menu semantics. This is read-only native evidence.
"""
import copy,json,math,re

def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False)

def eligible(text,args):
    affirmative=re.split(r"\b(?:do not|don't|dont|never|without)\s+",(text or '').lower(),maxsplit=1)[0]
    negative=re.findall(r"\b(?:do not|don't|dont|never|without)\s+([^.!?;]+)",(text or '').lower())
    if any(re.search(r'\bmenu\b',clause) for clause in negative):return False
    steps=args.get('steps') or []
    if not re.search(r'\bedit menu\b',affirmative) or len(steps)!=1:return False
    s=steps[0]
    return (s.get('type','click')=='click' and s.get('label','').strip().lower()=='edit' and
            s.get('targetContext','visibleElement')=='visibleElement' and not
            re.search(r'\b(modify|delete|erase|remove|cut|paste|clear|reset|replace|discard|save|send|submit|publish)\b',s.get('hint',''),re.I))

def capture(text,args,ar):
    if not eligible(text,args):return None
    before=ar.active_context()
    if ar.modal_title(args.get('app'),expected_pid=before.get('pid'))!=('ok',None):return None
    targets=ar.resolve('Edit',args.get('app'))
    same=[t for t in targets if (t.get('label') or '').strip().lower()=='edit']
    # Never collapse a neighboring same-label destructive control into the menu.
    if len(same)!=1:return None
    t=same[0];m=t.get('coordinate_mapping') or {};n=t.get('native_identity') or {};r=t.get('rect')
    if (t.get('role')!='menu' or not t.get('menu_header') or
        not n.get('path') or n.get('pid')!=before.get('pid') or m.get('pid')!=before.get('pid') or
        m.get('window_path')!=before.get('window_path') or t.get('app')!=before.get('app') or
        (args.get('app') or '').casefold()!=before.get('app','').casefold() or
        not isinstance(r,list) or len(r)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in r) or r[2]<=0 or r[3]<=0):return None
    if ar.modal_title(args.get('app'),expected_pid=before.get('pid'))!=('ok',None):return None
    after=ar.active_context()
    if canonical(before)!=canonical(after):return None
    return copy.deepcopy({'text':text,'args':args,'context':before,'target':t})

def valid_record(proof,text,args):
    return bool(proof and eligible(text,args) and proof.get('text')==text and canonical(proof.get('args'))==canonical(args))

def revalidate(proof,ar):
    if not proof:return False
    try:return canonical(capture(proof['text'],proof['args'],ar))==canonical(proof)
    except Exception:return False
