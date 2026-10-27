"""App-owned approval proof. Model text and action verbs are not consent."""
import hashlib
import json


def canonical(args):
    return json.dumps(args, sort_keys=True, ensure_ascii=False)


def approved_step(proposal, current, args, index, step=None):
    """Require the exact displayed/approved plan and current step, not a bool flag.

    The caller independently checks its operation generation at asynchronous
    boundaries. This proof does not infer permission from a request's vocabulary.
    """
    try:
        if proposal.get('state') != 'approved' or not proposal.get('displayed'):
            return False
        if not current or current.get('rev') != proposal.get('rev'):
            return False
        if current.get('hash') != proposal.get('hash'):
            return False
        if current.get('v', {}).get('id') != proposal.get('id'):
            return False
        if type(index) is not int or current.get('idx') != index:
            return False
        encoded = canonical(args)
        if canonical(proposal.get('args')) != encoded or canonical(current.get('args')) != encoded:
            return False
        if hashlib.sha256(encoded.encode()).hexdigest() != proposal.get('hash'):
            return False
        steps = args.get('steps') or []
        if index < 0 or index >= len(steps):
            return False
        return step is None or canonical(step) == canonical(steps[index])
    except (TypeError, ValueError, AttributeError):
        return False
