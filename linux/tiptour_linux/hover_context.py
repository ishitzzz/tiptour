"""Owned native hover context. Not a painted region or an AX target override.

No provider data can supply native range metadata. Prompt uses capped selection;
action record retains the exact native text and offsets. No password text read.
"""
import copy
import os
import json
import threading
import time

MAX_AGE = 300

def alive(context, owner, clock=time.monotonic):
    return bool(context and context.get('owner') == owner and 0 <= clock() - context['at'] < MAX_AGE)

def capture(point, target, owner):
    if os.environ.get("TIPTOUR_USE_ATSPI", "1") != "1": return None
    from . import radial_target, atspi_resolver as ar
    from Xlib import display
    if radial_target.snapshot(point) != target: return None
    d = display.Display()
    try:
        w = d.create_resource_object('window', target[0]); title = w.get_wm_name() or ''
    finally: d.close()
    if not title: return None
    # The focus worker rejects password roles before fetching text (see ar).
    record = ar._sub(['--focus', title], 1.5).get('focus')
    if not record or record.get('password') or record.get('identity', {}).get('pid') != target[1]: return None
    if record['identity'].get('window_name') != title: return None
    check = ar._sub(['--focus', title], 1.5).get('focus')
    if not check or check.get('password') or any(check.get(k) != record.get(k) for k in ('identity', 'text', 'selection', 'caret')): return None
    if radial_target.snapshot(point) != target: return None
    selection = record.get('selection'); native = None; text = None
    if selection:
        a, b = selection
        full = record.get('text')
        if not isinstance(full, str) or len(full) >= 20000 or not 0 <= a < b <= len(full): return None
        text = full[a:b]
        if record.get('editable'):
            native = {'identity': record['identity'], 'text': full, 'selection': selection, 'xwindow': str(target[0])}
    return {'kind': 'hover', 'owner': owner, 'at': time.monotonic(),
            'window': {'id': str(target[0]), 'pid': target[1], 'title': title},
            'text_selection': {'text': text, 'role': record.get('role')} if text is not None else None,
            'native_range': native}

def request(point, target, owner, valid, deliver, timeout=2):
    """One worker, caller retains it after timeout; loop must also check deadline."""
    deadline = time.monotonic() + timeout
    lock = threading.Lock(); done = False
    def finish(value):
        nonlocal done
        with lock:
            if done: return
            done = True
        if valid(): deliver(value, deadline)
    timer = threading.Timer(timeout, lambda: finish(None)); timer.daemon = True; timer.start()
    def run():
        try: value = capture(point, target, owner)
        except Exception: value = None
        if time.monotonic() >= deadline: value = None
        finish(value); timer.cancel()
    worker = threading.Thread(target=run, daemon=True, name='tiptour-hover-context'); worker.start()
    return worker

def prompt(context):
    wd = context['window']
    # Quote untrusted titles/selection as data, not user intent or permission.
    # Quoting does not establish injection resistance; local intent/Yes gates remain.
    lines = ['current hover app/window context:',
             'the user\'s pointer was over window_title=%s, pid=%s when they started speaking.' % (json.dumps(wd['title'][:120]), wd['pid']),
             'treat this as the target app/window for this request unless the user explicitly asks to switch apps.']
    sel = context.get('text_selection')
    if sel:
        lines += ['active text selection in that app: selected_text=%s, source="native_atspi", focused_role=%s.' % (json.dumps(sel['text'][:900]), json.dumps(sel.get('role'))),
                  'critical selected-text rule: preserve the existing selection when editing. Do not click the selected words first. Use a direct type, pressKey, keyboardShortcut, setValue or app menu action. For a one-word change, type only the replacement word, not the surrounding paragraph.']
    return '\n'.join(lines)

def bind(args, painted, hover):
    """Pure owned-context binding BEFORE immutable approval. No implicit scope."""
    args = copy.deepcopy(args)
    steps = args.get('steps') or []
    for step in steps: step.pop('_native_range', None)
    if not any(s.get('targetContext') in ('currentHighlight', 'currentSelection') for s in steps): return args
    if any(s.get('type') in ('openApp', 'openURL') for s in steps): return args
    ctx = painted or hover or {}; wd = ctx.get('window') or {}; nr = ctx.get('native_range')
    if not nr or not wd.get('title'): return args
    args['app'] = wd['title']
    selected = ((ctx.get('text_selection') or {}).get('text') or '')
    norm = lambda s: ' '.join(s.lower().split())
    if len(steps) >= 2 and steps[0].get('type') in ('click', 'doubleClick') and steps[1].get('type') in ('type', 'setValue', 'pressKey', 'keyboardShortcut'):
        label = norm(steps[0].get('label') or '')
        if steps[1].get('targetContext') in ('currentHighlight', 'currentSelection') or (label and label in norm(selected)):
            steps = steps[1:]; args['steps'] = steps
    for s in steps:
        ctx_ok = s.get('targetContext') in (None, 'currentHighlight', 'currentSelection')
        deletion = s.get('type') == 'pressKey' and (s.get('label') or '').lower().strip('.,;: ') in ('delete', 'del', 'backspace')
        if ctx_ok and (s.get('type') in ('type', 'setValue') or deletion): s['_native_range'] = copy.deepcopy(nr)
    return args
