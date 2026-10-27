"""Derive execution apps only from the exact approved sequence, never model followups."""
def destination(args, index):
    target = None
    transition = None
    for i, step in enumerate((args.get('steps') or [])[:index]):
        if step.get('type') == 'openApp':
            target = (step.get('label') or '').strip()
            transition = i
    return transition, target


def context_matches(context, name, captured_identity=None):
    if not context or not name or context.get('app', '').strip().casefold() != name.strip().casefold():
        return False
    if not all(context.get(k) for k in ('pid', 'x11_client_id', 'window_path', 'window_name', 'mapping')):
        return False
    return captured_identity is None or (str(context['x11_client_id']) == captured_identity[0] and
                                        context['window_name'] == captured_identity[1])


def same_window(before, now):
    return all(before.get(k) == now.get(k) for k in ('app', 'pid', 'x11_client_id', 'window_path'))
