"""Offline JEV request/decision port of pinned JevClient/JevGrounding.

No networking, credentials, automatic fallback, spending or input dispatch.
A later transport must request the selected original provider explicitly; these
pure structures are not a tested live JEV path.
"""
from dataclasses import dataclass
import math
import json

NONE_KEY = '__none__'
MAX_CANDIDATES = 200
MAX_CHOICES = 255
DONE_THRESHOLD = .70
CONNECTIONS = {
    'typesafeDirect': dict(title='TypeSafe direct', endpoint='https://api.typesafe.ai/v1/systemone', model='jev-latest', keyName='jevAPIKey'),
    'openRouter': dict(title='OpenRouter', endpoint='https://openrouter.ai/api/v1/systemone', model='~typesafe/jev-latest', keyName='openRouterJevAPIKey'),
}


@dataclass(frozen=True)
class Candidate:
    id: str
    label: str
    source: str
    confidence: float
    centre: tuple

    @property
    def description(self):
        location = '' if tuple(self.centre) == (0, 0) else ' at (%d,%d)' % (int(self.centre[0]), int(self.centre[1]))
        return (self.label or 'unlabeled element') + ' [' + self.source + ']' + location


def deduplicated(candidates):
    descriptions, identifiers, output = set(), set(), []
    for candidate in candidates:
        if not candidate.id or candidate.id == NONE_KEY or candidate.id in identifiers: continue
        # Swift inserts the id before evaluating duplicate description.
        identifiers.add(candidate.id)
        if candidate.description in descriptions: continue
        descriptions.add(candidate.description); output.append(candidate)
    return output


def grounding_request(task, candidates, history=(), excluding=()):
    pool = [c for c in deduplicated(candidates) if c.id not in excluding][:MAX_CANDIDATES]
    if not pool: return None
    criteria = {c.id: c.description for c in pool}
    criteria[NONE_KEY] = 'None of these would advance the task \u2014 the control needed is not on screen'
    state = dict(task=task, step=len(history)+1, already_done=list(history) or ['nothing yet'],
                 screen_elements=[dict(id=c.id, describes=c.description) for c in pool])
    questions = {
        'done': dict(type='noul', instructions='Judging only by what is on screen now and the actions already taken, has this task been completed: "'+task+'"?'),
        'absent': dict(type='noul', instructions='Is the control needed to make the next bit of progress on the task missing from the elements on screen?'),
        'pick': dict(type='choice', instructions='Which single element should be acted on next to make progress on the task: "'+task+'"? Consider what has already been done; do not repeat a step that already succeeded.', criteria=criteria),
        'kind': dict(type='choice', instructions='How should that element be acted on?', criteria={
            'click':'A normal single left click \u2014 the default for buttons, menus, links, list rows',
            'double_click':'Double click \u2014 opening a file or folder from a list',
            'right_click':'Right click to open a context menu'}),
    }
    return dict(state=state, questions=questions, pool=pool)


def request_body(connection, state, questions):
    """Serializes only. No request is sent and no key is read."""
    for question in questions.values():
        if question.get('type') == 'choice' and len(question.get('criteria', {})) > MAX_CHOICES:
            raise ValueError('too many choices')
    return dict(state=state, model=CONNECTIONS[connection]['model'], questions=questions)


def _probability(value):
    return type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)


@dataclass(frozen=True)
class Decision:
    done: float
    absent: float
    ranked: tuple
    action_kind: str
    chose_none: bool
    metrics: dict

    @property
    def best(self): return self.ranked[0] if self.ranked else None

    @property
    def stop_reason(self):
        if self.chose_none: return 'target_absent'
        if self.best is None: return 'no_candidates'
        return None


def grounding_decision(answers, pool, metrics=None):
    try:
        pick = answers['pick']; choice = pick['choice']; probabilities = pick['probabilities']
        done, absent, kind = answers['done']['noul'], answers['absent']['noul'], answers['kind']['choice']
        by_id = {c.id: c for c in pool}
        if (choice not in by_id and choice != NONE_KEY
                or not _probability(done) or not _probability(absent)
                or kind not in ('click','double_click','right_click')
                or not isinstance(probabilities, dict) or not probabilities
                or not all(_probability(v) for v in probabilities.values())
                or choice not in probabilities or probabilities[choice] != max(probabilities.values())
                or not all(k == NONE_KEY or k in by_id for k in probabilities)):
            raise ValueError('incomplete or invalid decision')
        ordered = sorted(probabilities.items(), key=lambda kv: (-kv[1], 0 if kv[0] == choice else 1, kv[0]))
        ranked = tuple((by_id[k], probability) for k, probability in ordered if k in by_id)
        return Decision(done, absent, ranked, kind, choice == NONE_KEY, dict(metrics or {}))
    except (KeyError, TypeError, AttributeError):
        raise ValueError('incomplete or invalid decision') from None


def parse_response(raw):
    """Swift JSONDecoder-equivalent numeric boundary, before field decoding."""
    def constant(value): raise ValueError('non-JSON numeric constant')
    try:
        parsed = json.loads(raw, parse_constant=constant)
        def check(value):
            if isinstance(value, dict):
                for child in value.values(): check(child)
            elif isinstance(value, list):
                for child in value: check(child)
            elif type(value) in (int, float):
                if not math.isfinite(value): raise ValueError('nonfinite JSON number')
        check(parsed)
        if not isinstance(parsed, dict) or not isinstance(parsed.get('answers'), dict):
            raise ValueError('incomplete or invalid response')
        return parsed
    except (TypeError, OverflowError) as error:
        raise ValueError('incomplete or invalid response') from None


def response_metrics(response, connection, milliseconds):
    """Optional usage/provider fields decode leniently, as in the Mac client."""
    # Also refuse nonfinite optional metrics when given a decoded object directly.
    for value in ((response.get('usage') or {}).values() if isinstance(response.get('usage'), dict) else []):
        if type(value) in (int, float):
            try: finite = math.isfinite(value)
            except OverflowError: finite = False
            if not finite: raise ValueError('nonfinite JSON metric')
    usage = response.get('usage') if isinstance(response.get('usage'), dict) else {}
    tokens = usage.get('input_tokens')
    model = response.get('model')
    cost = usage.get('cost')
    provider = response.get('provider')
    return dict(milliseconds=milliseconds, inputTokens=tokens if type(tokens) is int else 0,
                model=model if isinstance(model, str) else CONNECTIONS[connection]['model'],
                cost=cost if type(cost) in (int,float) else None,
                provider=provider if isinstance(provider, str) else None)
