"""Pinned engine pure visual-policy cases. No pixels/network/actions."""
from tiptour_linux.visual_context import *
assert normalized_mode(' TARGET-IMAGE ')=='target_crop'
assert normalized_mode('noscreenshot')=='none'
assert normalized_mode('state')=='compact_state'
assert normalized_mode('unexpected')=='auto'
assert decision('none',screenshots_enabled=False)['mode']=='none'
assert decision('none',screenshots_enabled=False)['screenshotAllowed'] is False
assert decision('full_screenshot',screenshots_enabled=False)['mode']=='compact_state'
assert decision('compact_state',app_name='Blender')['mode']=='compact_state'
assert decision('target_crop',has_focus_target=False)['mode']=='full_screenshot'
assert decision('target_crop',has_focus_target=True)['mode']=='target_crop'
assert decision(target_count=2)['mode']=='compact_state'
assert decision(target_count=2)['reasons']==['local_state_sufficient']
assert decision(target_count=0)['mode']=='full_screenshot'
assert decision(target_count=2,app_name='Blender')['mode']=='full_screenshot'
assert decision(target_count=2,bundle_identifier='COM.FIGMA.DESKTOP')['mode']=='full_screenshot'
assert decision(target_count=2,has_focus_target=True)['mode']=='target_crop'
assert decision(target_count=2,has_focus_target=True,target_diagnosis='target_ambiguous')['mode']=='full_screenshot'
assert decision(target_count=2,target_diagnosis='target_not_found')['mode']=='full_screenshot'
assert decision(target_count=2,recent_action_uncertain=True)['mode']=='full_screenshot'
assert decision(target_count=2,policy_reason='post_action')['mode']=='compact_state'
assert decision(target_count=2,policy_reason='task_start')['mode']=='full_screenshot'
assert decision(target_count=2,policy_reason='task_start')['screenshotIncluded'] is False
print('visual-context pure policy: pass (ordering, opt-out, disabled screenshots, crop, ambiguity, canvas, recent failure, reason strings)')
