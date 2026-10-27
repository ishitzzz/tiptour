"""Portable port of pinned Mac Skills/MarkdownAppSkill.swift.

Only structured tiptour-runtime-hints are interpreted. Markdown remains data.
Linux OS substitution: an app's desktop id may be used as the bundle identifier.
No planner or action path is changed by importing this module.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import math


def normalized_command(text):
    return ''.join(c for c in text.lower() if c.isalnum())


@dataclass(frozen=True)
class AppSkill:
    name: str
    description: str
    source: str
    path: str
    markdown: str
    runtime_hints: dict

    def matches(self, application_name=None, bundle_identifier=None):
        matchers = self.runtime_hints.get('appMatchers') or {}
        app = (application_name or '').strip().lower()
        bundle = (bundle_identifier or '').lower()
        return (any(bundle == x.lower() for x in matchers.get('bundleIdentifiers', []))
                or any(x.strip().lower() in app for x in matchers.get('names', [])))

    def command_alias(self, text):
        command = normalized_command(text)
        for alias in self.runtime_hints['commandAliases']:
            if any(normalized_command(phrase) in command for phrase in alias['phrases']):
                return dict(alias)
        return None

    def should_type_physical_keys(self, text):
        text = text.strip()
        if not text:
            return False
        for policy in self.runtime_hints['inputPolicies']:
            if policy['kind'] != 'numericModalText' or policy['delivery'] != 'physicalKeys':
                continue
            if policy.get('maxLength') is not None and len(text) > policy['maxLength']:
                continue
            allowed = policy.get('characters')
            if allowed is not None and any(c not in allowed for c in text):
                continue
            if any(c.isdecimal() for c in text):
                return True
        return False

    @property
    def menu_selection_preferred_left_region_max_x(self):
        return ((self.runtime_hints.get('targetPolicies') or {}).get('menuSelection') or {}).get('preferLeftMenuRegionMaxX')

    def info(self, active=False):
        matchers = self.runtime_hints.get('appMatchers') or {}
        return dict(name=self.name, description=self.description, source=self.source,
                    path=self.path, appNames=matchers.get('names', []),
                    bundleIdentifiers=matchers.get('bundleIdentifiers', []),
                    plannerInstructionCount=len(self.runtime_hints['plannerInstructions']),
                    plannerInstructions=list(self.runtime_hints['plannerInstructions']), isActive=active)


def _strings(value):
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def _valid_hints(hints):
    # Match JSONDecoder's required fields and types; reject malformed skill files.
    if not isinstance(hints, dict): return False
    if not all(isinstance(hints.get(k), list) for k in ('commandAliases', 'inputPolicies')): return False
    if not _strings(hints.get('plannerInstructions')): return False
    matchers = hints.get('appMatchers')
    if matchers is not None and (not isinstance(matchers, dict) or not all(_strings(matchers.get(k)) for k in ('bundleIdentifiers', 'names'))): return False
    for alias in hints['commandAliases']:
        if not isinstance(alias, dict) or not _strings(alias.get('phrases')) or not isinstance(alias.get('label'), str): return False
        if alias.get('type') not in ('click','doubleClick','rightClick','type','setValue','pressKey','keyboardShortcut','openApp','openURL','scroll','waitForState','observe'): return False
    for policy in hints['inputPolicies']:
        if not isinstance(policy, dict) or not all(isinstance(policy.get(k), str) for k in ('kind','delivery')): return False
        if policy.get('maxLength') is not None and type(policy['maxLength']) is not int: return False
        if policy.get('characters') is not None and not isinstance(policy['characters'], str): return False
    target = hints.get('targetPolicies')
    if target is not None:
        if not isinstance(target, dict): return False
        menu = target.get('menuSelection')
        if menu is not None:
            if not isinstance(menu, dict): return False
            number = menu.get('preferLeftMenuRegionMaxX')
            if number is not None and (type(number) not in (int, float) or not math.isfinite(number)): return False
    return True


def load_skill(path, source):
    try:
        path = Path(path)
        markdown = path.read_text(encoding='utf-8')
        start = markdown.index('```tiptour-runtime-hints')
        start = markdown.index('\n', start) + 1
        end = markdown.index('\n```', start)
        def invalid_constant(value): raise ValueError('non-JSON numeric constant')
        hints = json.loads(markdown[start:end], parse_constant=invalid_constant)
        if not _valid_hints(hints): return None
        metadata = {}
        if markdown.startswith('---\n'):
            closing = markdown.find('\n---', 4)
            if closing != -1:
                for line in markdown[4:closing].splitlines():
                    if ':' in line:
                        k, v = line.split(':', 1)
                        metadata[k.strip()] = v.strip().strip('\"\'')
        return AppSkill(metadata.get('name', path.parent.name), metadata.get('description', ''), source, str(path), markdown, hints)
    except (OSError, ValueError, TypeError, OverflowError):
        return None


class AppSkillRegistry:
    def __init__(self, roots=None, home=None, cwd=None, repository=None):
        if roots is None:
            home = Path(home or Path.home())
            cwd = Path(cwd or Path.cwd())
            repository = Path(repository or Path(__file__).resolve().parents[2])
            roots = [(home / '.tiptour/skills', 'user')]
            for root in (cwd, repository):
                roots.extend((root / relative, 'project') for relative in
                             ('.claude/skills', '.agents/skills', '.openhands/skills', '.openhands/microagents'))
            roots.extend(((repository / 'linux/skills', 'bundled'), (repository / 'TipTour/Skills', 'bundled-source')))
        self.skills = []
        seen_paths, seen_names = set(), set()
        for root, source in roots:
            root = Path(root)
            if not root.exists() or root.resolve() in seen_paths: continue
            seen_paths.add(root.resolve())
            # Mac filesystem enumeration is unspecified; lexical order makes Linux deterministic.
            for path in sorted(root.rglob('*')):
                if not path.is_file() or any(p.startswith('.') for p in path.relative_to(root).parts): continue
                if path.suffix.lower() != '.md' or path.name.lower() == 'readme.md': continue
                skill = load_skill(path, source)
                if skill and skill.name.lower() not in seen_names:
                    self.skills.append(skill)
                    seen_names.add(skill.name.lower())

    def skill(self, application_name=None, bundle_identifier=None):
        return next((s for s in self.skills if s.matches(application_name, bundle_identifier)), None)

    def planner_instructions(self, application_name=None, bundle_identifier=None):
        skill = self.skill(application_name, bundle_identifier)
        if not skill or not skill.runtime_hints['plannerInstructions']: return None
        return 'Active app skill: ' + skill.name + '\n' + '\n'.join('- ' + s for s in skill.runtime_hints['plannerInstructions'])

    def skill_infos(self, application_name=None, bundle_identifier=None):
        active = self.skill(application_name, bundle_identifier)
        return [s.info(active is not None and s.name == active.name) for s in self.skills]


# Mac MarkdownAppSkillRegistry.shared is a lazy, process-owned snapshot.
# Explicit AppSkillRegistry(...) construction remains independent for tests/tools.
_shared_registry = None
import threading as _threading
_shared_registry_lock = _threading.Lock()

def shared_registry():
    global _shared_registry
    with _shared_registry_lock:
        if _shared_registry is None:
            _shared_registry = AppSkillRegistry()
        return _shared_registry


def normalize_semantic_keyboard_steps(steps, app_name, registry=None):
    """Mac CompanionManager.normalizingSemanticKeyboardSteps, BEFORE proposal hashing.

    The eventual proposal displays the exact normalized keys. This never grants
    action permission, dispatches input, coalesces text, or changes non-key steps.
    """
    import copy
    registry = registry if registry is not None else shared_registry()
    skill = registry.skill(app_name)
    common = dict(selectall='Cmd+A', copy='Cmd+C', paste='Cmd+V', cut='Cmd+X',
                  undo='Cmd+Z', redo='Cmd+Shift+Z', save='Cmd+S')
    output = copy.deepcopy(steps)
    for step in output:
        if step.get('type') not in ('keyboardShortcut', 'pressKey'): continue
        label = (step.get('label') or '').strip()
        if not label: continue
        alias = skill.command_alias(label) if skill else None
        if alias:
            step['type'], step['label'] = alias['type'], alias['label']
        elif normalized_command(label) in common:
            step['type'], step['label'] = 'keyboardShortcut', common[normalized_command(label)]
        else:
            continue
        # Equivalent to constructing WorkflowStep with targetID/targetMark nil.
        step.pop('targetID', None); step.pop('targetMark', None)
        step.pop('target_id', None); step.pop('target_mark', None)
    return output
