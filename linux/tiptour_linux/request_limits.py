"""Explicit negative limits are checked independently of proposal confirmation.

Conservative restrictions, not a general semantic intent classifier. Unknown
anaphoric followups are refused by request_chain before reaching this check.
"""
import re


def forbidden_plan(text, args, menu_proof=None):
    negative = re.findall(r"\b(?:do not|don't|dont|never|without)\s+([^.!?;]+)", (text or '').lower())
    limits = ' '.join(negative)
    if not limits:
        return None
    no_edit = bool(re.search(r'\b(edit|editing|modify|modifying|change|changing|delete|deleting|erase|erasing|write|writing|type|typing)\b', limits))
    no_save = bool(re.search(r'\b(save|saving|store|storing|persist|persisting)\b', limits))
    no_send = bool(re.search(r'\b(send|sending|post|posting|publish|publishing|submit|submitting|share|sharing)\b', limits))
    for step in args.get('steps') or []:
        kind = step.get('type') or 'click'
        action = ' '.join(str(step.get(k) or '') for k in ('label','hint')).lower()
        key = str(step.get('value') or step.get('label') or '').lower().replace('command','ctrl').replace('cmd','ctrl').replace('control','ctrl').replace(' ','')
        if no_edit and kind in ('type','setValue','pressKey','keyboardShortcut'):
            return 'The original request forbids editing; this action may edit.'
        from .menu_guidance import valid_record
        menu_guidance = valid_record(menu_proof,text,args) and step is (args.get('steps') or [None])[0]
        edit_target = re.sub(r'\bedit\b','',action) if menu_guidance else action
        if no_edit and re.search(r'\b(edit|modify|delete|erase|remove|cut|paste|clear|reset|replace|discard)\b', edit_target):
            return 'The original request forbids editing; this target may edit.'
        if no_save and (re.search(r'\b(save|saving|store|storing|persist|persisting|download)\b',action) or kind=='keyboardShortcut' and key in ('ctrl+s','ctrl+shift+s')):
            return 'The original request forbids saving.'
        if no_send and (re.search(r'\b(send|sending|post|posting|publish|publishing|submit|submitting|share|sharing)\b',action) or kind=='pressKey' and key in ('enter','return') or kind=='keyboardShortcut' and key in ('ctrl+enter','ctrl+return')):
            return 'The original request forbids sending or submitting.'
    return None
