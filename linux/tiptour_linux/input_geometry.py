"""Pure geometry from pinned TextCommandPanelManager + CompanionManager.

Inputs/outputs use Linux top-left global pixel coordinates. Source macOS points
use bottom-left; Y signs and candidate order are converted explicitly here.
No windows, shortcuts, model calls, input dispatch or provider routing.
"""
import math

EDGE_INSET = 12
CURSOR_CLEARANCE = 44
HORIZONTAL_OFFSET = 56
VERTICAL_OFFSET = 32
SMOOTHING = .24


def _point(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2: raise ValueError('expected point')
    try:
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value): raise ValueError('invalid coordinate')
        return tuple(float(v) for v in value)
    except OverflowError: raise ValueError('coordinate overflow')


def panel_origin(mouse, size, screen):
    """Screen = (x,y,width,height). Reject panel larger than usable screen."""
    x, y = _point(mouse); width, height = _point(size)
    if not isinstance(screen, (tuple, list)) or len(screen) != 4: raise ValueError('expected screen')
    sx, sy = _point(screen[:2]); sw, sh = _point(screen[2:])
    if width <= 0 or height <= 0 or width + 2 * EDGE_INSET > sw or height + 2 * EDGE_INSET > sh: raise ValueError('panel does not fit usable screen')
    candidates = [(x + HORIZONTAL_OFFSET, y + VERTICAL_OFFSET),
                  (x + HORIZONTAL_OFFSET, y - height - VERTICAL_OFFSET),
                  (x - width - HORIZONTAL_OFFSET, y + VERTICAL_OFFSET),
                  (x - width - HORIZONTAL_OFFSET, y - height - VERTICAL_OFFSET)]
    def good(p):
        px, py = p
        contains = px >= sx and py >= sy and px + width <= sx + sw and py + height <= sy + sh
        intersects = px < x + CURSOR_CLEARANCE and px + width > x - CURSOR_CLEARANCE and py < y + CURSOR_CLEARANCE and py + height > y - CURSOR_CLEARANCE
        return contains and not intersects
    px, py = next((p for p in candidates if good(p)), candidates[0])
    return (min(max(px, sx + EDGE_INSET), sx + sw - width - EDGE_INSET),
            min(max(py, sy + EDGE_INSET), sy + sh - height - EDGE_INSET))


def smoothed_origin(current, target, animated=True):
    tx, ty = _point(target)
    if current is None or not animated: return tx, ty
    x, y = _point(current); dx, dy = tx-x, ty-y
    if abs(dx) < .5 and abs(dy) < .5: return tx, ty
    return x + dx * SMOOTHING, y + dy * SMOOTHING


def radial_option(point, center):
    x,y = _point(point); cx,cy = _point(center)
    dx,dy = x-cx, cy-y  # Linux down-positive -> Mac up-positive
    if math.hypot(dx,dy) < 24: return None
    angle = math.degrees(math.atan2(dy,dx))
    if 30 <= angle <= 150: return 'speak'
    if -90 <= angle < 30: return 'type'
    return 'highlight'
