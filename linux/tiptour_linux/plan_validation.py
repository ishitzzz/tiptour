"""Reject malformed provider plans before review. Never repair or authorize a plan."""

TYPES = {'click','rightClick','doubleClick','openApp','openURL','keyboardShortcut','pressKey','type','setValue','scroll','waitForState','observe'}
FIELDS = {'label','type','hint','value','direction','amount','by','targetContext','point_2d','box_2d'}

def structure(call):
    if not isinstance(call, dict): return 'Tool call must be an object.'
    if not isinstance(call.get('id'), str) or not call['id']: return 'Tool call needs a nonempty string id.'
    if call.get('name') != 'submit_workflow_plan': return 'Unsupported tool name.'
    a = call.get('args')
    if not isinstance(a, dict): return 'Plan args must be an object, not null or an array.'
    if set(a) - {'goal','app','steps','requestRelation'}: return 'Unknown plan fields are not executable.'
    for k in ('goal','app'):
        if not isinstance(a.get(k), str) or not a[k].strip(): return k + ' must be a nonempty string.'
    if 'requestRelation' in a and a['requestRelation'] not in ('continue','separate','ambiguous'): return 'Invalid requestRelation.'
    if not isinstance(a.get('steps'), list) or not a['steps']: return 'steps must be a nonempty array.'
    for n,s in enumerate(a['steps'],1):
        prefix = 'Step %d: ' % n
        if not isinstance(s,dict): return prefix + 'must be an object.'
        if set(s)-FIELDS: return prefix + 'unknown or private fields are not accepted from the provider.'
        for k in ('label','type','hint','value','direction','by','targetContext'):
            if k in s and not isinstance(s[k],str): return prefix + k + ' must be a string.'
        if not s.get('label','').strip(): return prefix + 'label must be nonempty.'
        if s.get('type','click') not in TYPES: return prefix + 'unsupported type.'
        if 'targetContext' in s and s['targetContext'] not in ('visibleElement','currentHighlight','currentSelection','focusedElement'): return prefix + 'invalid targetContext.'
        if 'amount' in s and (type(s['amount']) is not int): return prefix + 'amount must be an integer.'
        for k,length in (('point_2d',2),('box_2d',4)):
            if k in s and (not isinstance(s[k],list) or len(s[k])!=length or any(type(v) is not int or not 0<=v<=1000 for v in s[k])): return prefix + k + ' must contain normalized integers.'
        if 'box_2d' in s and (s['box_2d'][0]>s['box_2d'][2] or s['box_2d'][1]>s['box_2d'][3]): return prefix + 'box bounds are reversed.'
    return None

def semantics(args):
    from .actions import hotkey_tokens,normalize_token,_keysym,scroll_key
    from Xlib import XK
    def valid_key(tok):
        return len(tok)==1 or bool(XK.string_to_keysym(_keysym(tok)))
    for n,s in enumerate(args['steps'],1):
        t=s.get('type','click');label=s['label'];prefix='Step %d: '%n
        if t in ('type','setValue') and 'value' not in s: return prefix+'text action requires a literal string value.'
        if t in ('keyboardShortcut','pressKey'):
            if 'value' in s: return prefix+'key actions execute label, not value. Put the exact key or shortcut in label and omit value. Resubmit the entire corrected plan under the same original task and limits.'
            if t=='keyboardShortcut':
                try: tokens=hotkey_tokens(label)
                except Exception: return prefix+'invalid shortcut label.'
                if not valid_key(tokens[-1]): return prefix+'shortcut label contains an unknown key.'
            else:
                token=normalize_token(label)
                if token in ('cmd','ctrl','shift','option','fn') or not valid_key(token): return prefix+'pressKey needs one valid nonmodifier key in label.'
        if t=='scroll':
            if not scroll_key(s.get('direction') or label or 'down',s.get('by') or 'line'): return prefix+'invalid scroll direction/granularity.'
            if 'amount' in s and not 1<=s['amount']<=50: return prefix+'scroll amount must be within the executor range 1..50.'
    return None
