"""NES background compliance audit.

Rules checked (same model as the supplied audit scripts):
  * the screen is a 256x240 canvas split into 16x16 attribute blocks anchored at (0,0)
  * every block may use the shared backdrop colour plus at most 3 other colours
  * at most 4 palette groups (backdrop + 3 colours each) exist for the whole screen
Extra diagnostics: which group each block uses, 8x8 tile pattern counts against a
CHR budget, tiles with more than four colours.
"""
import base64
import csv
import html
import io
import itertools
import json
import os
from collections import Counter, OrderedDict

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .palette import pack, to_hex

SCREEN = (256, 240)
BLOCK = 16
TILE = 8
GROUP_COLORS = [(70, 140, 255), (60, 200, 90), (255, 190, 40), (200, 90, 255)]
CONFLICT_COLOR = (255, 60, 60)


# --------------------------------------------------------------------------- fonts
def get_font(size, bold=False):
    names = (["DejaVuSansMono-Bold.ttf", "consolab.ttf", "arialbd.ttf"] if bold else []) + [
        "DejaVuSansMono.ttf", "consola.ttf", "Menlo.ttc", "LiberationMono-Regular.ttf", "arial.ttf",
    ]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


# --------------------------------------------------------------------------- canvas
def load_rgba(path_or_image):
    im = path_or_image if isinstance(path_or_image, Image.Image) else Image.open(path_or_image)
    return np.array(im.convert("RGBA"), dtype=np.uint8)


def compose_canvas(rgba, origin=(0, 0), backdrop=(0, 0, 0), screen=True):
    """Place an RGBA image on the NES screen canvas (transparent -> backdrop).

    Returns (canvas HxWx3 uint8, canvas_valid_mask HxW bool for image-covered pixels).
    If the image does not fit a 256x240 screen at `origin` (or screen=False), the canvas
    is the image area rounded up to whole 16x16 blocks, anchored at the screen origin.
    """
    h, w = rgba.shape[:2]
    ox, oy = origin
    if screen and ox + w <= SCREEN[0] and oy + h <= SCREEN[1]:
        cw, ch = SCREEN
    else:
        cw = -(-(ox + w) // BLOCK) * BLOCK
        ch = -(-(oy + h) // BLOCK) * BLOCK
    canvas = np.empty((ch, cw, 3), np.uint8)
    canvas[:] = backdrop
    rgb = rgba[:, :, :3].copy()
    opaque = rgba[:, :, 3] > 0
    rgb[~opaque] = backdrop
    canvas[oy:oy + h, ox:ox + w] = rgb
    valid = np.zeros((ch, cw), bool)
    valid[oy:oy + h, ox:ox + w] = opaque
    return canvas, valid


# --------------------------------------------------------------------------- core audit
def _min_cover(remaining, colors, budget_nodes=300000):
    """Smallest number of 3-colour groups covering all `remaining` colour sets.

    Exact search (bitmask set cover); returns (list_of_color_tuples, exact_flag).
    Falls back to a greedy cover (upper bound) if the search grows too large.
    """
    if not remaining:
        return [], True
    k = min(3, len(colors))
    masks = {}
    for combo in itertools.combinations(colors, k):
        cs = frozenset(combo)
        mask = 0
        for i, s in enumerate(remaining):
            if s <= cs:
                mask |= 1 << i
        if mask:
            masks.setdefault(mask, combo)
    # keep only maximal masks
    items = list(masks.items())
    maximal = [(m, c) for m, c in items if not any(m != n and (m & n) == m for n, _ in items)]
    masks = dict(maximal)
    full = (1 << len(remaining)) - 1
    memo = {}
    nodes = [0]

    class _Overflow(Exception):
        pass

    def cover(todo):
        if not todo:
            return ()
        if todo in memo:
            return memo[todo]
        nodes[0] += 1
        if nodes[0] > budget_nodes:
            raise _Overflow
        pivot = min((i for i in range(len(remaining)) if todo >> i & 1),
                    key=lambda i: sum(bool(m >> i & 1) for m in masks))
        options = [(m,) + cover(todo & ~m) for m in masks if m >> pivot & 1]
        best = min(options, key=len)
        memo[todo] = best
        return best

    try:
        chosen = cover(full)
        return [masks[m] for m in chosen], True
    except _Overflow:
        todo, out = full, []
        while todo:
            m = max(masks, key=lambda mm: bin(mm & todo).count("1"))
            out.append(masks[m])
            todo &= ~m
        return out, False


def audit_canvas(canvas, backdrop=(0, 0, 0), tile_budget=192, nearblack=0, valid=None,
                 fixed_groups=None, assignments=None):
    """Audit an HxWx3 canvas (H, W multiples of 16). Returns a result dict.

    fixed_groups: optional list (<=4) of colour-code tuples. When given, the screen is judged against
    exactly these palette groups (edit mode): blocks that fit none of them are reported as 'unfit'.
    assignments: optional {(bx, by): group_index} preferred group per block (used when it fits)."""
    canvas = np.asarray(canvas, np.uint8)
    backdrop = tuple(int(v) for v in backdrop)
    if nearblack:
        canvas = canvas.copy()
        near = (canvas.max(axis=2) <= nearblack)
        canvas[near] = backdrop
    H, W = canvas.shape[:2]
    codes = pack(canvas)
    bcode = int(pack(np.array(backdrop)))
    bh, bw = H // BLOCK, W // BLOCK

    blocks = []
    sets = OrderedDict()
    for by in range(bh):
        for bx in range(bw):
            sub = codes[by * BLOCK:(by + 1) * BLOCK, bx * BLOCK:(bx + 1) * BLOCK]
            u, c = np.unique(sub, return_counts=True)
            counts = {int(a): int(b) for a, b in zip(u, c)}
            nonb = frozenset(counts) - {bcode}
            sets.setdefault(nonb, []).append((bx, by))
            blocks.append(dict(bx=bx, by=by, x=bx * BLOCK, y=by * BLOCK, visible_colors=len(counts),
                               slots=len(nonb) + 1,
                               colors={to_hex(np.array([(k >> 16) & 255, (k >> 8) & 255, k & 255])): n
                                       for k, n in counts.items()},
                               _set=nonb))

    if fixed_groups is not None:
        groups = [tuple(sorted(int(c) for c in g)) for g in fixed_groups]
        exact_cover = True
    else:
        forced = [s for s in sets if len(s) == 3]
        remaining = [s for s in sets if len(s) < 3 and not any(s <= t for t in forced)]
        colors = sorted(set().union(*[s for s in sets if len(s) <= 3]) if sets else set())
        extra, exact_cover = _min_cover(remaining, colors)
        groups = [tuple(sorted(s)) for s in forced] + [tuple(sorted(c)) for c in extra]

    def hexs(code):
        return to_hex(np.array([(code >> 16) & 255, (code >> 8) & 255, code & 255]))

    group_sets = [frozenset(g) for g in groups]
    for b in blocks:
        s = b.pop("_set")
        b["conflict"] = b["slots"] > 4
        b["group"] = None
        b["unfit"] = False
        b["assigned"] = False
        if not b["conflict"]:
            pref = (assignments or {}).get((b["bx"], b["by"]))
            if pref is not None and pref < len(group_sets) and s <= group_sets[pref]:
                b["group"], b["assigned"] = pref, True
            else:
                for gi, gs in enumerate(group_sets):
                    if s <= gs:
                        b["group"] = gi
                        break
            if b["group"] is None and s:
                b["unfit"] = True
        b["nonbackdrop"] = [hexs(c) for c in sorted(s)]

    conflicts = [b for b in blocks if b["conflict"]]
    unfit = [b for b in blocks if b["unfit"]]

    # --- tile statistics (8x8)
    tiles = []
    for ty in range(H // TILE):
        for tx in range(W // TILE):
            tiles.append(codes[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE].tobytes())
    tile_arrays = [np.frombuffer(t, dtype=np.int64) for t in tiles]
    exact_patterns = len(set(tiles))

    def canonical(arr):
        labels = {}
        return bytes(labels.setdefault(int(v), len(labels)) for v in arr)

    canon_patterns = len({canonical(a) for a in tile_arrays})
    over4_tiles = sum(len(np.unique(a)) > 4 for a in tile_arrays)

    groups_needed = len(groups)
    result = dict(
        canvas=[W, H],
        backdrop=to_hex(backdrop),
        palette_pass=(not conflicts) and (not unfit) and groups_needed <= 4,
        unfit_blocks=len(unfit),
        edit_mode=fixed_groups is not None,
        conflict_blocks=len(conflicts),
        blocks_over_four_visible_colors=sum(b["visible_colors"] > 4 for b in blocks),
        max_slots_with_backdrop=max((b["slots"] for b in blocks), default=0),
        groups_needed=groups_needed,
        groups_exact=exact_cover,
        groups=[dict(index=i, colors=[to_hex(backdrop)] + [hexs(c) for c in g]) for i, g in enumerate(groups)],
        tiles=dict(exact_rgb_patterns=exact_patterns, pattern_lower_bound=canon_patterns,
                   over_four_color_tiles=int(over4_tiles), budget=tile_budget,
                   within_budget=(canon_patterns <= tile_budget) if tile_budget else None),
        blocks=blocks,
        conflicts=conflicts,
        unfit=unfit,
        nearblack_merge=int(nearblack),
    )
    result["_group_codes"] = [list(g) for g in groups]
    result["_backdrop_code"] = bcode
    return result


def audit_image(path_or_image, origin=(0, 0), backdrop=(0, 0, 0), tile_budget=192, nearblack=0, screen=True):
    """Convenience: load, place on the screen canvas, audit. Returns (result, canvas)."""
    rgba = load_rgba(path_or_image)
    canvas, valid = compose_canvas(rgba, origin, backdrop, screen=screen)
    res = audit_canvas(canvas, backdrop, tile_budget, nearblack, valid)
    res["image_size"] = [rgba.shape[1], rgba.shape[0]]
    res["origin"] = [int(origin[0]), int(origin[1])]
    return res, canvas


# --------------------------------------------------------------------------- rendering
def summary_lines(res):
    t = res["tiles"]
    lines = ["PASS" if res["palette_pass"] else "FAIL",
             "backdrop %s | canvas %dx%d" % (res["backdrop"], res["canvas"][0], res["canvas"][1]),
             "palette groups needed: %d (max 4)%s" % (res["groups_needed"], "" if res["groups_exact"] else " (approx.)"),
             "blocks over backdrop+3: %d" % res["conflict_blocks"],
             ] + (["blocks fitting none of the 4 palettes: %d" % res["unfit_blocks"]] if res.get("edit_mode") else []) + [
             "worst block: %d slots (max 4)" % res["max_slots_with_backdrop"],
             "blocks with >4 visible colors: %d" % res["blocks_over_four_visible_colors"],
             "8x8 pattern lower bound: %d" % t["pattern_lower_bound"],
             "exact RGB patterns: %d" % t["exact_rgb_patterns"],
             "tiles with >4 colors: %d" % t["over_four_color_tiles"]]
    if t["budget"]:
        lines.append("tile budget %d: %s" % (t["budget"], "within" if t["within_budget"] else "OVER by %d" % (t["pattern_lower_bound"] - t["budget"])))
    if res.get("nearblack_merge"):
        lines.append("near-black merge <= %d applied (diagnostic)" % res["nearblack_merge"])
    return lines


def render_annotated(canvas, res, scale=None, grid=True, tint=True, labels=True, legend=True, crop=None):
    """Annotated PIL image: grid, group outline + number per block, conflicts in red, legend panel."""
    H, W = canvas.shape[:2]
    if scale is None:
        scale = max(1, min(6, 1024 // W))
    im = Image.fromarray(canvas).resize((W * scale, H * scale), Image.NEAREST).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    font = get_font(max(9, min(14, 3 * scale)), bold=True)
    bs = BLOCK * scale
    for b in res["blocks"]:
        x, y = b["bx"] * bs, b["by"] * bs
        blank = (b["slots"] == 1)
        if b["conflict"]:
            d.rectangle((x, y, x + bs - 1, y + bs - 1), fill=CONFLICT_COLOR + (55,) if tint else None,
                        outline=CONFLICT_COLOR + (255,), width=max(2, scale // 2))
            if labels:
                d.rectangle((x + 2, y + 2, x + 6 + 8 * scale // 2, y + 4 + scale * 3), fill=(0, 0, 0, 220))
                d.text((x + 4, y + 2), str(b["slots"]), font=font, fill=(255, 90, 90, 255))
        elif b.get("unfit"):
            d.rectangle((x, y, x + bs - 1, y + bs - 1), fill=(255, 150, 0, 50) if tint else None,
                        outline=(255, 150, 0, 255), width=max(2, scale // 2))
            if labels:
                d.rectangle((x + 2, y + 2, x + 6 + 8 * scale // 2, y + 4 + scale * 3), fill=(0, 0, 0, 220))
                d.text((x + 4, y + 2), "?", font=font, fill=(255, 170, 40, 255))
        elif b["group"] is not None and not blank:
            gc = GROUP_COLORS[b["group"] % 4] if b["group"] < 4 else (160, 160, 160)
            if tint:
                d.rectangle((x, y, x + bs - 1, y + bs - 1), fill=gc + (28,), outline=gc + (220,), width=1)
            if labels:
                d.rectangle((x + 2, y + 2, x + 6 + 8 * scale // 2, y + 4 + scale * 3), fill=(0, 0, 0, 200))
                d.text((x + 4, y + 2), str(b["group"] + 1), font=font, fill=gc + (255,))
    if grid:
        for gx in range(0, W + 1, BLOCK):
            d.line((gx * scale, 0, gx * scale, H * scale), fill=(255, 255, 255, 45))
        for gy in range(0, H + 1, BLOCK):
            d.line((0, gy * scale, W * scale, gy * scale), fill=(255, 255, 255, 45))
    if not legend:
        return im
    panel_w = 340
    out = Image.new("RGB", (im.width + panel_w, max(im.height, 460)), (28, 28, 30))
    out.paste(im, (0, 0))
    p = ImageDraw.Draw(out)
    f, fb = get_font(13), get_font(15, bold=True)
    x0, y = im.width + 14, 12
    ok = res["palette_pass"]
    p.rectangle((x0 - 4, y - 4, x0 + panel_w - 24, y + 26), fill=(30, 120, 50) if ok else (160, 40, 40))
    p.text((x0, y), ("PASS  " if ok else "FAIL  ") + "NES palette rules", font=fb, fill=(255, 255, 255))
    y += 38
    for line in summary_lines(res)[1:]:
        p.text((x0, y), line, font=f, fill=(225, 225, 225))
        y += 19
    y += 8
    p.text((x0, y), "Key: coloured number = palette group used", font=f, fill=(170, 170, 170))
    y += 17
    p.text((x0, y), "     red box+number = colours in block (too many)", font=f, fill=(255, 130, 130))
    y += 26
    p.text((x0, y), "Palette groups (backdrop + 3):", font=fb, fill=(255, 255, 255))
    y += 24
    for g in res["groups"][:8]:
        gc = GROUP_COLORS[g["index"] % 4] if g["index"] < 4 else (160, 160, 160)
        p.text((x0, y + 2), str(g["index"] + 1) + ("" if g["index"] < 4 else "!"), font=fb, fill=gc)
        for j, hx in enumerate(g["colors"]):
            xx = x0 + 22 + j * 62
            p.rectangle((xx, y, xx + 54, y + 20), fill=hx, outline=(150, 150, 150))
        y += 28
    if len(res["groups"]) > 4:
        p.text((x0, y), "groups beyond 4 cannot exist on NES", font=f, fill=(255, 120, 120))
        y += 20
    if res["conflicts"]:
        y += 6
        p.text((x0, y), "Over-limit blocks (x,y: slots):", font=fb, fill=(255, 120, 120))
        y += 22
        for b in res["conflicts"][:12]:
            p.text((x0, y), "(%3d,%3d): %d slots" % (b["x"], b["y"], b["slots"]), font=f, fill=(255, 170, 170))
            y += 18
        if len(res["conflicts"]) > 12:
            p.text((x0, y), "... %d more (see report)" % (len(res["conflicts"]) - 12), font=f, fill=(255, 170, 170))
    return out


# --------------------------------------------------------------------------- reports
def save_report(folder, base, canvas, res, source=None):
    """Write PNG (annotated), JSON, CSV and HTML. Returns dict of written paths."""
    os.makedirs(folder, exist_ok=True)
    paths = {k: os.path.join(folder, "%s_%s" % (base, k)) for k in ("audit.png", "audit.json", "blocks.csv", "audit.html")}
    img = render_annotated(canvas, res)
    img.save(paths["audit.png"])
    slim = {k: v for k, v in res.items() if not k.startswith("_")}
    slim["source"] = source
    with open(paths["audit.json"], "w", encoding="utf-8") as fh:
        json.dump(slim, fh, indent=2)
    with open(paths["blocks.csv"], "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["x", "y", "visible_colors", "slots_with_backdrop", "group", "status", "colors"])
        for b in res["blocks"]:
            status = "CONFLICT" if b["conflict"] else ("UNFIT" if b.get("unfit") else ("ok" if b["slots"] > 1 else "empty"))
            w.writerow([b["x"], b["y"], b["visible_colors"], b["slots"],
                        "" if b["group"] is None else b["group"] + 1, status, " ".join(b["colors"])])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    rows = "".join(
        "<tr class='%s'><td>%d,%d</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            "bad" if (b["conflict"] or b.get("unfit")) else "", b["x"], b["y"], b["slots"],
            "" if b["group"] is None else b["group"] + 1,
            "CONFLICT" if b["conflict"] else ("UNFIT" if b.get("unfit") else ("ok" if b["slots"] > 1 else "empty")),
            html.escape(" ".join("%s:%d" % kv for kv in b["colors"].items())))
        for b in res["blocks"] if b["slots"] > 1)
    with open(paths["audit.html"], "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><meta charset='utf-8'><title>NES audit - %s</title>"
                 "<style>body{font:14px sans-serif;background:#1c1c1e;color:#eee;padding:16px}"
                 "table{border-collapse:collapse}td,th{border:1px solid #444;padding:3px 8px}"
                 ".bad{background:#5a1f1f}</style>" % html.escape(base))
        fh.write("<h2>%s - %s</h2><pre>%s</pre>" % (html.escape(base), "PASS" if res["palette_pass"] else "FAIL",
                                                     html.escape("\n".join(summary_lines(res)))))
        fh.write("<img style='max-width:100%%;image-rendering:pixelated' src='data:image/png;base64,%s'>" % b64)
        fh.write("<h3>Blocks (x,y = pixel origin)</h3><table><tr><th>block</th><th>slots</th><th>group</th>"
                 "<th>status</th><th>colors:pixels</th></tr>%s</table>" % rows)
    return paths
