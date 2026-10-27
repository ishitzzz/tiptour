"""Shared read-only engine facade, ported from pinned TipTourEngine.swift.

All live state and capture are supplied by the existing runtime. This facade
never activates a window, dispatches input, reads a key or creates a provider.
Action submission is intentionally absent until shared local approval is wired.
"""
import base64
from datetime import datetime, timezone
from .app_skills import shared_registry


class ReadOnlyEngine:
    def __init__(self, active_app, flags, active_goal, target_cache, refresh_targets,
                 capture, registry=None, detection_count=None):
        self._active_app = active_app
        self._flags = flags
        self._active_goal = active_goal
        self._cache = target_cache
        self._refresh = refresh_targets
        self._detection_count = detection_count or target_cache.fresh_target_count
        self._capture = capture
        self._registry = registry if registry is not None else shared_registry()

    def _app(self):
        app = self._active_app() or {}
        return dict(activeAppName=app.get('name'), activeBundleIdentifier=app.get('desktop_id'))

    def observe(self):
        flags = self._flags()
        return dict(ok=True, **self._app(), activePlanGoal=self._active_goal(),
                    isAutopilotEnabled=bool(flags.get('autopilot')),
                    isScreenshotStreamingEnabled=bool(flags.get('screenshots')),
                    isAccurateGroundingEnabled=bool(flags.get('accurate_grounding')),
                    isCuaActionDriverEnabled=bool(flags.get('action_driver')),
                    detectionElementCount=self._detection_count(),
                    externalHarnessVisualContext='Read-only Linux facade. Action submission requires the local revision-bound proposal and confirmation path; external execute=true is not consent.')

    def skills(self):
        app = self._app()
        skills = self._registry.skill_infos(app['activeAppName'],app['activeBundleIdentifier'])
        return dict(ok=True, **app, skillCount=len(skills), skills=skills)

    def active_skill(self):
        app = self._app()
        skill = self._registry.skill(app['activeAppName'],app['activeBundleIdentifier'])
        return dict(ok=True, **app, skill=skill.info(True) if skill else None)

    @staticmethod
    def _target(target):
        return dict(id=target['id'], mark=target['mark'], label=target['label'],
                    source=target['source'], confidence=target['confidence'],
                    screenshotBox=target['screenshot_box'], normalizedBox2D=target['normalized_box_2d'],
                    globalCenter=target['global_center'], globalBox=target['global_box'],
                    displayFrame=target['display_frame'], cacheAgeMs=target['cache_age_ms'])

    def targets(self, refresh=False, reason='harness requested targets'):
        if refresh: self._refresh(reason)
        targets = [self._target(t) for t in self._cache.current_targets()]
        return dict(ok=True, **self._app(), refreshed=refresh, targetCount=len(targets), targets=targets)

    def screenshots(self):
        app = self._app()
        if not self._flags().get('screenshots'):
            return dict(ok=False, **app, reason='screenshots_disabled',
                        message='TipTour Screenshots is off, so the harness will not expose raw screen images.',
                        screenshotCount=0, screenshots=[])
        try:
            full, jpeg, size = self._capture()
            import io
            from PIL import Image
            pixels = Image.open(io.BytesIO(jpeg)).size
            captured = datetime.now(timezone.utc).isoformat()
            image = dict(label='X11 desktop', isCursorScreen=True,
                         displayWidthInPoints=size[0], displayHeightInPoints=size[1],
                         screenshotWidthInPixels=pixels[0], screenshotHeightInPixels=pixels[1],
                         capturedAt=captured, mediaType='image/jpeg',
                         dataURL='data:image/jpeg;base64,'+base64.b64encode(jpeg).decode('ascii'))
            return dict(ok=True, **app, reason=None, message='Captured fresh TipTour screenshot.', screenshotCount=1, screenshots=[image])
        except Exception:
            # Never expose exception contents (may include private labels or paths).
            return dict(ok=False, **app, reason='screenshot_capture_failed', message='Screenshot capture failed.', screenshotCount=0, screenshots=[])
