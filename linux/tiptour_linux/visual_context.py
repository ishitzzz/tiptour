"""Pure visual-context policy from pinned Core/TipTourEngine.swift.

No capture, provider request or action is performed here. The actual shared
engine facade and HTTP transport must supply live context and honor its result.
"""
from .app_skills import normalized_command


def normalized_mode(mode=None):
    mode = normalized_command(mode or 'auto')
    groups = {
        'none': ('none','off','noscreenshot','disabled'),
        'compact_state': ('compact','compactstate','state','text'),
        'target_crop': ('crop','targetcrop','target','targetimage','targetregion'),
        'full_screenshot': ('full','screenshot','fullscreenshot','image'),
    }
    return next((k for k,v in groups.items() if mode in v), 'auto')


def policy_reason_needs_screenshot(reason):
    return bool(reason and any(token in reason.lower() for token in (
        'start','screenshot','visual','canvas','target_not_found','ambiguous',
        'failed','uncertain','state_did_not_change')))


def is_canvas_app(app_name=None, bundle_identifier=None):
    return ((bundle_identifier or '').lower() in ('org.blenderfoundation.blender','com.figma.desktop','com.adobe.photoshop','com.adobe.illustrator')
            or any(token in normalized_command(app_name or '') for token in
                   ('blender','figma','sketch','photoshop','illustrator','unity','unreal')))


def decision(requested_mode='auto', policy_reason=None, app_name=None,
             bundle_identifier=None, target_count=0, target_diagnosis=None,
             has_focus_target=False, screenshots_enabled=True, recent_action_uncertain=False):
    """Same ordering, reasons, mode and output keys as Mac policy."""
    reasons = [policy_reason] if policy_reason is not None else []
    def result(mode):
        return dict(mode=mode, requestedMode=requested_mode, reasons=reasons,
                    screenshotAllowed=screenshots_enabled, screenshotIncluded=False,
                    screenChangedSinceLastSnapshot=None)
    if requested_mode == 'none':
        reasons.append('agent_requested_no_screenshot'); return result('none')
    if not screenshots_enabled:
        reasons.append('screenshots_disabled'); return result('compact_state')
    if requested_mode == 'compact_state':
        reasons.append('agent_requested_compact_state'); return result('compact_state')
    if requested_mode == 'target_crop':
        reasons.append('agent_requested_target_crop' if has_focus_target else 'target_crop_requested_without_target')
        return result('target_crop' if has_focus_target else 'full_screenshot')
    if requested_mode == 'full_screenshot':
        reasons.append('agent_requested_screenshot'); return result('full_screenshot')
    canvas = is_canvas_app(app_name,bundle_identifier)
    if canvas: reasons.append('canvas_app')
    if target_count == 0: reasons.append('no_local_targets')
    if target_diagnosis is not None: reasons.append(target_diagnosis)
    if has_focus_target: reasons.append('focus_target_available')
    if recent_action_uncertain: reasons.append('recent_action_uncertain')
    needs = policy_reason_needs_screenshot(policy_reason)
    if needs: reasons.append('reason_requests_visual_context')
    include = (canvas or target_count == 0 or has_focus_target or
               target_diagnosis in ('target_not_found','target_ambiguous','explicit_target_not_found')
               or recent_action_uncertain or needs)
    crop = has_focus_target and target_diagnosis != 'target_ambiguous'
    if not reasons: reasons.append('local_state_sufficient')
    return result(('target_crop' if crop else 'full_screenshot') if include else 'compact_state')
