import json
from ..config import APP_ROOT, REFERENCE_W, REFERENCE_H

# work in progress resolution scaling to handle black bars on phones and different shapes

SAME_SHAPE = 0.03        # screens within 3% of the reference shape are scaled straight across
TOP_ZONE = 0.15          # reference y above this fraction of the height: pinned to the top (HUD)

# words the game always draws at a known spot in the top bar, and where (reference coordinates)
ANCHOR_WORDS = {"auto": (792, 69), "menu": (997, 71)}
# a measured inset larger than this fraction of the height is a misread
MAX_INSET = 0.12        
INSET_FILE = APP_ROOT.parent / ".layout.json"  

ANCHORS = {}

def anchor_for(y, ref_h=REFERENCE_H):
    fraction = y / ref_h
    if fraction < TOP_ZONE:
        return "top"
    return "center"

def _load():
    try:
        return {tuple(map(int, key.split("x"))): float(value)
                for key, value in json.loads(INSET_FILE.read_text(encoding="utf-8")).items()}
    except Exception:
        return {}

INSETS = _load()    

def _save():
    try:
        INSET_FILE.write_text(json.dumps({f"{w}x{h}": round(float(v), 1) for (w, h), v in INSETS.items()}), encoding="utf-8")
    except Exception:
        pass   

def calibrate(items, width, height, ref=(REFERENCE_W, REFERENCE_H)):
    fit = _fit(width, height, ref)
    if fit is None:
        return None
    s = float(fit[0])
    seen = []
    for text, _, cy in items:
        point = ANCHOR_WORDS.get(text.strip().lower())
        if point and cy < height * 0.25:
            seen.append(cy - point[1] * s)
    if not seen:
        return None
    measured = float(sorted(seen)[len(seen) // 2])
    if not 0 <= measured <= height * MAX_INSET:
        return None
    key = (width, height)
    old = INSETS.get(key)
    new = measured if old is None else old * 0.7 + measured * 0.3
    if old is not None and abs(new - old) < 2:
        return None
    INSETS[key] = new
    _save()
    return new

def _fit(width, height, ref):
    rw, rh = ref
    sx, sy = width / rw, height / rh
    if abs(sx / sy - 1) <= SAME_SHAPE:
        return None
    s = min(sx, sy)
    return s, width - rw * s, height - rh * s, INSETS.get((width, height), 0.0)

def scale(width, height, ref=(REFERENCE_W, REFERENCE_H)):
    fit = _fit(width, height, ref)
    if fit is None:
        return width / ref[0], height / ref[1]
    return fit[0], fit[0]

def to_pixels(point, width, height, anchor=None, ref=(REFERENCE_W, REFERENCE_H)):
    x, y = point
    fit = _fit(width, height, ref)
    if fit is None:
        return x * width / ref[0], y * height / ref[1]
    s, extra_x, extra_y, inset = fit
    anchor = anchor or anchor_for(y, ref[1])
    if anchor == "top":
        py = inset + y * s
    elif anchor == "bottom":
        py = height - inset - (ref[1] - y) * s
    else:
        py = extra_y * 0.5 + y * s
    return x * s + extra_x * 0.5, py

def to_reference(x, y, width, height, ref=(REFERENCE_W, REFERENCE_H)):
    fit = _fit(width, height, ref)
    if fit is None:
        return x * ref[0] / width, y * ref[1] / height
    s, extra_x, extra_y, inset = fit
    rx = (x - extra_x * 0.5) / s
    for anchor, ry in (("top", (y - inset) / s), ("center", (y - extra_y * 0.5) / s)):
        if anchor_for(ry, ref[1]) == anchor:
            return rx, ry
    return rx, (y - extra_y * 0.5) / s

def box_pixels(left, top, right, bottom, width, height, ref=(REFERENCE_W, REFERENCE_H)):
    x1, y1 = to_pixels((left, top), width, height, ref=ref)
    x2, y2 = to_pixels((right, bottom), width, height, ref=ref)
    return round(x1), round(y1), round(x2), round(y2)
