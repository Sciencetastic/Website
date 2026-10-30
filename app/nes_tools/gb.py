"""Colorize 4-shade (Game Boy style) images under NES rules.

Three ways to get colour:
  theme      - a built-in 4-palette theme chosen per image (no reference needed)
  aligned    - a colour reference of the SAME artwork, pixel-aligned: the GB shades give the
               structure, the reference gives the colours (per 16x16 block palette choice)
  palette    - a reference of the same scene that need NOT line up: its colours, ordered by
               brightness, are mapped onto the GB shades by block brightness band
The darkest GB shade becomes the shared backdrop colour (black by default); each 16x16 block
uses one of at most 4 palettes, so output is compliant by construction.
"""
import itertools
import re

import numpy as np

from .audit import BLOCK, compose_canvas
from .convert import pick_groups
from .palette import color_distance, pack, snap_to_nes, to_hex, unpack

# --------------------------------------------------------------------------- shade levels
def gb_levels(rgba, tolerance=None):
    """Map an image with <=4 distinct shades to levels 0..3 (0 = darkest).

    Returns (levels HxW int8 (-1 where transparent), info dict). More than 4 shades are
    quantised by brightness into 4 bands (info['quantized'] = True)."""
    rgba = np.asarray(rgba, np.uint8)
    opaque = rgba[:, :, 3] > 0
    rgb = rgba[:, :, :3].astype(float)
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    codes = pack(rgba[:, :, :3])
    uniq = np.unique(codes[opaque]) if opaque.any() else np.array([], np.int64)
    info = dict(distinct=int(len(uniq)), quantized=False)
    lv = np.full(codes.shape, -1, np.int8)
    if len(uniq) == 0:
        return lv, info
    if len(uniq) <= 4:
        lums = {int(c): float(unpack(np.array([c]))[0] @ np.array([0.299, 0.587, 0.114])) for c in uniq}
        order = sorted(lums, key=lums.get)
        n = len(order)
        spread = [0] if n == 1 else [int(round(i * 3 / (n - 1))) for i in range(n)]
        m = {c: spread[i] for i, c in enumerate(order)}
        lv[opaque] = np.vectorize(m.__getitem__, otypes=[np.int8])(codes[opaque])
    else:
        info["quantized"] = True
        qs = np.percentile(lum[opaque], [25, 50, 75])
        lv[opaque] = np.digitize(lum[opaque], qs).astype(np.int8)
    return lv, info


# --------------------------------------------------------------------------- themes
def P(*names):
    return tuple(C[n] for n in names)

C = dict(
    dteal=(0, 64, 88), dgreen=(0, 88, 0), green=(0, 168, 0), lgreen=(184, 248, 184),
    teal=(0, 136, 136), sky=(164, 228, 252), blue=(0, 88, 248), lav=(184, 184, 248),
    gray=(120, 120, 120), lgray=(188, 188, 188), white=(252, 252, 252),
    brown=(80, 48, 0), olive=(136, 112, 0), orange=(252, 160, 68), yellow=(248, 216, 120),
    peach=(252, 224, 168), skin=(240, 208, 176), maroon=(136, 20, 0), red=(168, 16, 0),
    pink=(248, 120, 88), purple=(68, 40, 188), violet=(148, 0, 132), plum=(216, 184, 248),
    dblue=(0, 0, 124), rust=(200, 76, 12),
)

# four palettes (L1, L2, L3), darkest block-brightness band first
THEMES = {
    "snow": [P("dteal", "dgreen", "green"), P("dteal", "gray", "lgray"), P("dteal", "lgray", "sky"), P("gray", "sky", "white")],
    "forest": [P("dteal", "dgreen", "green"), P("dteal", "dgreen", "lgreen"), P("dgreen", "green", "sky"), P("green", "sky", "white")],
    "warm": [P("maroon", "brown", "rust"), P("brown", "rust", "orange"), P("brown", "orange", "yellow"), P("rust", "yellow", "peach")],
    "cave": [P("dblue", "dteal", "teal"), P("dteal", "teal", "lav"), P("dteal", "lav", "sky"), P("teal", "sky", "white")],
    "mine": [P("dteal", "dgreen", "olive"), P("dteal", "olive", "orange"), P("brown", "orange", "yellow"), P("olive", "yellow", "peach")],
    "horror": [P("maroon", "red", "rust"), P("maroon", "red", "pink"), P("red", "pink", "skin"), P("pink", "skin", "white")],
    "face": [P("maroon", "brown", "rust"), P("brown", "rust", "skin"), P("rust", "skin", "peach"), P("skin", "peach", "white")],
    "sepia": [P("brown", "rust", "orange"), P("brown", "orange", "yellow"), P("olive", "yellow", "peach"), P("orange", "peach", "white")],
    "throne": [P("dblue", "purple", "violet"), P("dblue", "purple", "plum"), P("purple", "plum", "lav"), P("plum", "lav", "white")],
    "night": [P("dblue", "dteal", "blue"), P("dblue", "blue", "lav"), P("dteal", "lav", "sky"), P("blue", "sky", "white")],
    "mono": [P("gray", "lgray", "white")] * 4,
}
THEME_RULES = [
    (r"cu\d|eaten|burnt_little", "face"),
    (r"death|bite|tentacle|angular|candle|flame", "horror"),
    (r"throne|puz", "throne"),
    (r"opening|title|logo|gameboy", "sepia"),
    (r"village_temple", "snow"),
    (r"mine|cave|temple|market_place|locked", "mine"),
    (r"tavern|bedroom|barn_int|office_int|black_smith|work_bench|alchemist_int|priesthouseint|interior|merch|alchemist_house", "warm"),
    (r"dark", "night"),
    (r"forest|briar|switchback|car2|field|outside|openmine|priest|valley|ruined|shacks|farm|carrol|cages|market|watchtower|barn|village", "snow"),
]


def theme_for(name):
    s = (name or "").lower()
    for pat, th in THEME_RULES:
        if re.search(pat, s):
            return th
    return "snow"


BAND_THRESH = (0.8, 1.5, 2.2)
BAND_MEAN = (0.5, 1.2, 1.9, 2.6)


def _bands(lvc, valid):
    """Per-block brightness band (0..3), smoothed. lvc: canvas-size levels, valid: bool mask."""
    H, W = lvc.shape
    bh, bw = H // BLOCK, W // BLOCK
    mean = {}
    for by in range(bh):
        for bx in range(bw):
            sl = (slice(by * BLOCK, (by + 1) * BLOCK), slice(bx * BLOCK, (bx + 1) * BLOCK))
            v = valid[sl]
            mean[bx, by] = float(lvc[sl][v].mean()) if v.any() else 0.0
    band = {k: sum(m >= t for t in BAND_THRESH) for k, m in mean.items()}
    for _ in range(2):
        nxt = {}
        for (bx, by), b in band.items():
            n = [band[bx + i, by + j] for i in (-1, 0, 1) for j in (-1, 0, 1) if (bx + i, by + j) in band]
            vals, cts = np.unique(n + [b, b], return_counts=True)
            nxt[bx, by] = int(vals[cts.argmax()])
        band = nxt
    return band


def _apply_bands(lvc, valid, band, backdrop, pals):
    H, W = lvc.shape
    out = np.empty((H, W, 3), np.uint8)
    out[:] = backdrop
    for (bx, by), b in band.items():
        sl = (slice(by * BLOCK, (by + 1) * BLOCK), slice(bx * BLOCK, (bx + 1) * BLOCK))
        sub, v = lvc[sl], valid[sl]
        blk = out[sl]
        for l in (1, 2, 3):
            blk[(sub == l) & v] = pals[b][l - 1]
    return out


def to_canvas_levels(lv, origin, backdrop=(0, 0, 0), screen=True):
    """Embed levels (HxW, -1 transparent) on the screen canvas. Returns (lvc, valid)."""
    h, w = lv.shape
    dummy = np.zeros((h, w, 4), np.uint8)
    dummy[:, :, 3] = (lv >= 0) * 255
    _, valid = compose_canvas(dummy, origin, backdrop, screen=screen)
    ch, cw = valid.shape
    lvc = np.zeros((ch, cw), np.int8)
    ox, oy = origin
    lvc[oy:oy + h, ox:ox + w] = np.where(lv >= 0, lv, 0)
    return lvc, valid


def colorize_theme(lv, theme, origin=(0, 0), backdrop=(0, 0, 0), screen=True):
    """Theme colouring. Returns canvas RGB (screen-sized), valid mask, info."""
    lvc, valid = to_canvas_levels(lv, origin, backdrop, screen)
    band = _bands(lvc, valid)
    out = _apply_bands(lvc, valid, band, backdrop, THEMES[theme])
    return out, valid, dict(method="theme:%s" % theme, palettes=[[to_hex(c) for c in p] for p in THEMES[theme]])


# --------------------------------------------------------------------------- reference: palette only
def ref_ramp(rgb, alpha=None, merge=14, keep=0.002):
    """Distinct colours of a reference, dark -> light, with pixel fractions."""
    rgb = np.asarray(rgb, np.uint8)
    flat = rgb.reshape(-1, 3)
    if alpha is not None:
        flat = flat[np.asarray(alpha).reshape(-1) > 0]
    cols, cnt = np.unique(flat, axis=0, return_counts=True)
    kept = []
    for i in np.argsort(-cnt):
        if cnt[i] < keep * cnt.sum():
            continue
        if all(np.linalg.norm(cols[i].astype(float) - cols[j]) > merge for j in kept):
            kept.append(i)
    cols, cnt = cols[kept].astype(float), cnt[kept]
    o = np.argsort(cols @ np.array([0.299, 0.587, 0.114]))
    return cols[o], cnt[o] / cnt.sum()


def _ramp_palettes(cols, frac, backdrop):
    """4 band palettes from a ramp. Backdrop colour itself is excluded from the ramp."""
    bd = np.array(backdrop, float)
    keep = np.linalg.norm(cols - bd, axis=1) > 20
    ramp, rf = (cols[keep], frac[keep]) if keep.sum() >= 3 else (cols, frac)
    pals = []
    for m in BAND_MEAN:
        row, prev = [], -1
        for l in (1, 2, 3):
            q = 0.6 * (l / 3) + 0.4 * (m / 3)
            i = int(round(q * (len(ramp) - 1)))
            lo, hi = max(prev + 1, i - 1), min(len(ramp), i + 2)
            if lo >= hi:
                lo = min(max(prev + 1, 0), len(ramp) - 1)
                hi = lo + 1
            prev = lo + int(rf[lo:hi].argmax())
            row.append(tuple(int(v) for v in ramp[prev]))
        pals.append(tuple(row))
    return pals


def colorize_ref_palette(lv, ref_rgb, ref_alpha=None, origin=(0, 0), backdrop=(0, 0, 0), snap=True, screen=True):
    ref = snap_to_nes(ref_rgb) if snap else np.asarray(ref_rgb, np.uint8)
    cols, frac = ref_ramp(ref, ref_alpha)
    pals = _ramp_palettes(cols, frac, backdrop)
    lvc, valid = to_canvas_levels(lv, origin, backdrop, screen)
    band = _bands(lvc, valid)
    out = _apply_bands(lvc, valid, band, backdrop, pals)
    return out, valid, dict(method="reference-palette", palettes=[[to_hex(c) for c in p] for p in pals])


# --------------------------------------------------------------------------- reference: aligned
def _box(a, k=4):
    c = np.cumsum(np.cumsum(np.pad(a, ((1, 0), (1, 0))), 0), 1)
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def align_reference(lv, ref_rgb):
    """Find the 1:1 crop of the reference that best matches the GB levels.

    The reference may be larger than the GB image (e.g. 122x122 art vs a 112x112 viewport).
    Returns (score, (ox, oy)); score is the structural correlation (1.0 = identical shape)."""
    gh, gw = lv.shape
    rh, rw = ref_rgb.shape[:2]
    if rh < gh or rw < gw:
        return -1.0, (0, 0)
    lum = ref_rgb.astype(float) @ np.array([0.299, 0.587, 0.114])
    g = lv.astype(float)
    mask = lv >= 0
    k = 4
    bg, bo = _box(np.where(mask, g, g[mask].mean() if mask.any() else 0), k), _box(lum, k)
    gh2, gw2 = bg.shape
    best = (-2.0, (0, 0))
    step = 1 if (rh - gh) * (rw - gw) <= 400 else 2
    for dy in range(0, rh - gh + 1, step):
        for dx in range(0, rw - gw + 1, step):
            win = bo[dy:dy + gh2, dx:dx + gw2]
            if win.shape != bg.shape:
                continue
            sc = np.corrcoef(bg.ravel(), win.ravel())[0, 1]
            if np.isfinite(sc) and sc > best[0]:
                best = (float(sc), (dx, dy))
    if step == 2:  # refine around the coarse optimum
        bx, by = best[1]
        for dy in range(max(0, by - 2), min(rh - gh, by + 2) + 1):
            for dx in range(max(0, bx - 2), min(rw - gw, bx + 2) + 1):
                win = bo[dy:dy + gh2, dx:dx + gw2]
                sc = np.corrcoef(bg.ravel(), win.ravel())[0, 1]
                if np.isfinite(sc) and sc > best[0]:
                    best = (float(sc), (dx, dy))
    return best


PERMS = np.array(list(itertools.permutations(range(4))))


def colorize_aligned(lv, ref_rgb, offset, origin=(0, 0), backdrop=(0, 0, 0), groups=4, max_colors=18,
                     snap=True, screen=True):
    """GB structure + colours of a pixel-aligned reference.

    For every 16x16 block choose one of `groups` palettes (backdrop + 3 colours) and the assignment
    of the block's 4 GB shades to those 4 colours that best reproduces the reference colours."""
    gh, gw = lv.shape
    ox_r, oy_r = offset
    crop = ref_rgb[oy_r:oy_r + gh, ox_r:ox_r + gw]
    if snap:
        crop = snap_to_nes(crop)
    lvc, valid = to_canvas_levels(lv, origin, backdrop, screen)
    H, W = lvc.shape
    refc = np.empty((H, W, 3), np.uint8)
    refc[:] = backdrop
    ox, oy = origin
    refc[oy:oy + gh, ox:ox + gw] = crop
    valid = valid & (lvc >= 0)

    codes = pack(refc)
    bcode = int(pack(np.array(backdrop)))
    u, c = np.unique(codes[valid], return_counts=True)
    kept = [bcode]
    for i in np.argsort(-c):
        if int(u[i]) not in kept:
            kept.append(int(u[i]))
        if len(kept) >= max_colors:
            break
    Cc = unpack(np.array(kept)).astype(np.int32)
    allu = np.unique(codes)
    nearest = color_distance(unpack(allu)[:, None, :], Cc[None]).argmin(1)
    lut = dict(zip(allu.tolist(), nearest.tolist()))
    idx = np.vectorize(lut.__getitem__, otypes=[np.int32])(codes)
    n = len(Cc)
    D = color_distance(Cc[:, None, :], Cc[None, :, :])
    bh, bw = H // BLOCK, W // BLOCK
    cost = np.zeros((bh * bw, 4, n))
    for by in range(bh):
        for bx in range(bw):
            sl = (slice(by * BLOCK, (by + 1) * BLOCK), slice(bx * BLOCK, (bx + 1) * BLOCK))
            v, L, I = valid[sl], lvc[sl], idx[sl]
            for l in range(4):
                m = v & (L == l)
                if m.any():
                    cost[by * bw + bx, l] = np.bincount(I[m], minlength=n) @ D
    rest = [i for i in range(n) if i != 0]
    while len(rest) < 3:
        rest.append(0)
    trips = np.array(list(itertools.combinations(rest, 3)))
    slots = np.concatenate([np.zeros((len(trips), 1), np.int64), trips], 1)       # T x 4
    A = cost[:, :, slots]                                                          # B x 4 x T x 4
    tot = np.zeros((bh * bw, len(trips), len(PERMS)))
    for pi, p in enumerate(PERMS):
        tot[:, :, pi] = sum(A[:, l, :, p[l]] for l in range(4))
    bc = tot.min(2)
    sel = pick_groups(bc, groups)
    out = np.empty((H, W, 3), np.uint8)
    out[:] = backdrop
    for by in range(bh):
        for bx in range(bw):
            b = by * bw + bx
            k = int(np.argmin([bc[b, s] for s in sel]))
            perm = PERMS[int(tot[b, sel[k]].argmin())]
            sl = (slice(by * BLOCK, (by + 1) * BLOCK), slice(bx * BLOCK, (bx + 1) * BLOCK))
            L, v = lvc[sl], valid[sl]
            blk = out[sl]
            for l in range(4):
                blk[(L == l) & v] = Cc[slots[sel[k]][perm[l]]]
    pals = [[to_hex(Cc[i]) for i in slots[s]] for s in sel]
    return out, valid, dict(method="reference-aligned", palettes=pals, offset=tuple(offset))
