"""Screen capture on X11 (incl. XWayland). Returns PIL image + JPEG bytes."""
import io
from PIL import ImageGrab

def grab(max_w=1280, exclude_xid=None):
    if exclude_xid is None:full = ImageGrab.grab(xdisplay=None)
    else:
        from .x11_capture import excluding
        full=excluding(exclude_xid)
    W, H = full.size
    img = full if W <= max_w else full.resize((max_w, round(H * max_w / W)))
    buf = io.BytesIO(); img.convert("RGB").save(buf, "JPEG", quality=80)
    return full, buf.getvalue(), (W, H)

def norm_to_px(point_yx, size):
    y, x = point_yx; W, H = size
    return round(x / 1000 * W), round(y / 1000 * H)


def changed_fraction(a, b, side=192, delta=24):
    """Fraction of pixels (on a downscaled grayscale copy) whose brightness differs by more than delta. Size mismatch counts as fully changed."""
    if a.size != b.size: return 1.0
    from PIL import ImageChops
    h = max(1, round(a.height * side / a.width))
    d = ImageChops.difference(a.convert("L").resize((side, h)), b.convert("L").resize((side, h)))
    px = list(d.getdata()); return sum(1 for v in px if v > delta) / len(px)


def target_changed_fraction(a, b, center, half=90, delta=24):
    """Same measure on a (2*half)^2 crop around the pointed target, so a small control that moved or changed state is not diluted by the whole frame."""
    if a.size != b.size: return 1.0
    x, y = int(center[0]), int(center[1]); box = (max(0, x - half), max(0, y - half), min(a.width, x + half), min(a.height, y + half))
    from PIL import ImageChops
    d = ImageChops.difference(a.crop(box).convert("L"), b.crop(box).convert("L")); px = list(d.getdata())
    return sum(1 for v in px if v > delta) / max(1, len(px))
