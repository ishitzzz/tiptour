"""Offline contract checks, no provider or OS input."""
import json
from pathlib import Path
import tempfile
from tiptour_linux.app_skills import AppSkillRegistry, load_skill, normalized_command

BUNDLED = Path(__file__).resolve().parents[1] / 'skills'
r = AppSkillRegistry(roots=[(BUNDLED, 'bundled')])
assert len(r.skills) == 1
s = r.skill(' Blender 4.3 ')
assert s and s.name == 'blender' and r.skill(bundle_identifier='ORG.BLENDERFOUNDATION.BLENDER') == s
assert r.skill('Text Editor') is None
assert s.command_alias('Please select all objects')['label'] == 'A'
assert s.command_alias('scale')['type'] == 'pressKey'
assert s.command_alias('Unrelated task') is None
assert s.should_type_physical_keys(' -2.5 ')
assert not s.should_type_physical_keys('a2')
assert not s.should_type_physical_keys('1' * 17)
assert not s.should_type_physical_keys('++')
assert s.menu_selection_preferred_left_region_max_x == .72
assert r.planner_instructions('Blender').startswith('Active app skill: blender\n- ')
assert r.planner_instructions('Other') is None
assert r.skill_infos('Blender')[0]['isActive']
assert not r.skill_infos('Other')[0]['isActive']
assert normalized_command(' Select-All! ') == 'selectall'
with tempfile.TemporaryDirectory() as d:
 p = Path(d)
 user = p / 'user'; user.mkdir()
 text = s.markdown.replace('name: blender', 'name: BLENDER').replace('description: Use when', 'description: User override when')
 (user / 'custom.md').write_text(text)
 (user / 'README.md').write_text(text.replace('name: BLENDER', 'name: excluded'))
 (user / '.hidden').mkdir(); (user / '.hidden/hidden.md').write_text(text.replace('name: BLENDER', 'name: hidden'))
 (user / 'bad.md').write_text('```tiptour-runtime-hints\n{}\n```')
 (user / 'unclosed.md').write_text('```tiptour-runtime-hints\n{}')
 (user / 'nofence.md').write_text('Markdown is data, not runtime code.')
 reg = AppSkillRegistry(roots=[(user,'user'),(BUNDLED,'bundled'),(user,'duplicate-root')])
 assert len(reg.skills) == 1 and reg.skills[0].name == 'BLENDER' and reg.skills[0].source == 'user'
 assert reg.skills[0].description.startswith('User override')
 assert load_skill(user/'bad.md','user') is None
 assert load_skill(user/'unclosed.md','user') is None
 base = s.runtime_hints
 for field, value in [('plannerInstructions', 2), ('commandAliases', [{}]), ('inputPolicies', [{'kind':'numericModalText','delivery':'physicalKeys','maxLength':'2'}]),('appMatchers',{'names':['Blender']})]:
  hints = dict(base);hints[field] = value
  (user/'invalid.md').write_text('```tiptour-runtime-hints\n'+json.dumps(hints)+'\n```')
  assert load_skill(user/'invalid.md','user') is None, field
print('app skill offline contract: pass (bundled, precedence, matching, aliases, numeric policy, info, malformed files)')
from tiptour_linux.app_skills import normalize_semantic_keyboard_steps
original = [dict(type='pressKey',label='select all',targetID='stale',targetMark=3,value='unchanged',hintX=.2),dict(type='click',label='scale')]
out = normalize_semantic_keyboard_steps(original,'Blender',r)
assert out[0]['type'] == 'pressKey' and out[0]['label'] == 'A' and 'targetID' not in out[0]
assert out[0]['value'] == 'unchanged' and out[0]['hintX'] == .2
assert out[1] == original[1] and original[0]['label'] == 'select all'
out = normalize_semantic_keyboard_steps(original,'Text Editor',r)
assert out[0]['type'] == 'keyboardShortcut' and out[0]['label'] == 'Cmd+A'
assert normalize_semantic_keyboard_steps([dict(type='type',value='first'),dict(type='type',value='next')],'Blender',r) == [dict(type='type',value='first'),dict(type='type',value='next')]
print('semantic key normalization: pass (app alias, common fallback, immutable input, no text coalescing)')

with tempfile.TemporaryDirectory() as d:
 p = Path(d)/'invalid.md'
 for constant in ('NaN', 'Infinity', '-Infinity', '1e999'):
  raw = s.markdown.replace('0.72',constant)
  p.write_text(raw)
  assert load_skill(p,'user') is None, constant
print('strict JSON nonfinite skill negatives: pass')

with tempfile.TemporaryDirectory() as d:
 p = Path(d)/'huge.md'
 p.write_text(s.markdown.replace('0.72', str(10**400)))
 assert load_skill(p,'user') is None
 reg = AppSkillRegistry(roots=[(p.parent,'user'),(BUNDLED,'bundled')])
 assert len(reg.skills) == 1 and reg.skill('Blender') is not None
 assert normalize_semantic_keyboard_steps([dict(type='pressKey',label='select all')], 'Blender', reg)[0]['label']=='A'
print('huge JSON integer ignored without registry/proposal crash: pass')
