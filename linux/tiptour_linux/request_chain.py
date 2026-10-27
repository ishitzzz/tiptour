"""Conservative local request provenance, independent of model goal labels."""
import copy
import re

_META = re.compile(r'\b(?:submit_workflow_plan|(?:submit|show|display|propose|prepare|confirm|approve|execute|run)\s+(?:(?:the|that|this|a|proposed|exact|same|stored|agreed|displayed)\s+)*(?:plan|steps|proposal))\b', re.I)
_RESPONSE = re.compile(r'^(?:yes|yeah|yep|sure|ok|okay|confirm|confirmed|go ahead|do it|proceed|yes please|yes do it|yes go ahead|go for it)[.!? ]*$', re.I)
# This grammar only recognizes local protocol continuation. It never grants an
# action or infers same-task status from a model-supplied goal paraphrase.
_META_WORDS = set('yes yeah yep sure ok okay please now to that this the a an of for with those these exact same stored agreed displayed proposed reversible test plan steps proposal app can display show submit prepare review separate local my confirmation confirm first before after until do not execute execution only user says say you it so and in order workflow submit_workflow_plan press button proceed ready me'.split())


def continuation(text):
    t = (text or '').strip()
    if _RESPONSE.fullmatch(t):
        return 'continue'
    if not _META.search(t):
        return 'new'
    words = re.findall(r"[a-z_]+", t.lower())
    return 'continue' if words and all(w in _META_WORDS for w in words) else 'ambiguous'


class Requests:
    def __init__(self):
        self.revision = 0
        self.record = None
        self.blocked = False
        self.pending_text = None

    def accept(self, text, context=None, epoch=None):
        if self.record is not None and text.strip() == self.record['text'].strip():
            self.blocked = False
            return 'continued'
        explicit_new = re.match(r'^(?:new task|different task|instead|start over)\s*[:,-]\s*(.+)$', text.strip(), re.I)
        kind = 'new' if explicit_new else continuation(text)
        if self.record is not None and kind == 'new' and not explicit_new:
            self.blocked = True
            self.pending_text = text
            return 'blocked'
        if explicit_new:
            text = explicit_new.group(1)
        if kind != 'new':
            self.blocked = kind == 'ambiguous' or self.record is None
            self.pending_text = text if self.blocked and self.record is not None else None
            return 'blocked' if self.blocked else 'continued'
        self.revision += 1
        from .highlight import refers_to_highlight
        if not refers_to_highlight(text):
            context, epoch = None, None
        self.pending_text = None
        self.record = {'id': self.revision, 'text': text,
                       'context': copy.deepcopy(context), 'context_epoch': epoch,
                       'context_identity': id(context) if context is not None else None}
        self.blocked = False
        return 'new'

    def boundary(self):
        if not self.blocked or not self.record or not self.pending_text:
            return None
        return {'request_id': self.record['id'], 'original': copy.deepcopy(self.record),
                'incoming': self.pending_text}

    def choose_boundary(self, request_id, incoming, separate=False, context=None, epoch=None):
        # Apply a boundary to this record or a private preview. This method grants no execution approval.
        b = self.boundary()
        if b is None or b['request_id'] != request_id or b['incoming'] != incoming:
            return False
        previous = copy.deepcopy(self.record)
        if separate:
            candidate = Requests()
            candidate.revision = self.revision
            result = candidate.accept(incoming, context, epoch)
            if result != 'new': return False
            self.record, self.revision = candidate.record, candidate.revision
            self.blocked, self.pending_text = False, None
            self.record['previous_task'] = previous
            self.record['boundary_choice'] = 'separate'
        else:
            self.record = copy.deepcopy(previous)
            self.record['text'] += '\nFollow-up: ' + incoming
            self.record['boundary_choice'] = 'continue'
            self.blocked = False
            self.pending_text = None
        return True

    def snapshot(self):
        return None if self.blocked else copy.deepcopy(self.record)

    def clear(self):
        self.record = None
        self.blocked = False
        self.pending_text = None
