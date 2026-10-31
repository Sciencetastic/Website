"""Conform an image to NES background rules and (optionally) reduce unique tiles.

Pipeline for an ordinary colour image:
  1. snap colours to the NES master palette (optional) and keep the N most used
  2. choose the shared backdrop (black / auto-best / explicit)
  3. pick up to 4 palette groups (backdrop + 3 colours) minimising colour error,
     assign every 16x16 block to its best group, map pixels to that group's colours
The result is compliant by construction (<= backdrop + 3 colours per block, <= 4 groups).
"""
import itertools

import numpy as np

from .audit import BLOCK, TILE, audit_canvas, compose_canvas
from .palette import color_distance, pack, snap_to_nes, to_hex, unpack


# --------------------------------------------------------------------------- helpers
def pick_groups(cost, k):
    """Choose k columns of cost (B x T) minimising sum_b min_k cost[b, sel_k]
    (greedy start, then coordinate descent)."""
    B, T = cost.shape
    sel = []
    for _ in range(min(k, T)):
        cur = cost[:, sel].min(1) if sel else np.full(B, np.inf)
        sel.append(int(np.minimum(cur[:, None], cost).sum(0).argmin()))
    for _ in range(8):
        changed = False
        for i in range(len(sel)):
            others = [sel[j] for j in range(len(sel)) if j != i]
            cur = cost[:, others].min(1) if others else np.full(B, np.inf)
            new = int(np.minimum(cur[:, None], cost).sum(0).argmin())
            if new != sel[i]:
                sel[i], changed = new, True
        if not changed:
            break
    return sel


def kept_palette(canvas, valid, backdrop, max_colors, extra=()):
    """Return (colors (n,3) int, index image (H,W), index of backdrop).

    The n kept colours = backdrop + (max_colors-1) most used colours; every other pixel colour
    is mapped to its nearest kept colour."""
    codes = pack(canvas)
    cvalid = codes[valid]
    uniq, counts = np.unique(cvalid, return_counts=True) if cvalid.size else (np.array([], np.int64), np.array([], np.int64))
    bcode = int(pack(np.array(backdrop)))
    order = np.argsort(-counts)
    kept = [bcode]
    for i in order:
        c = int(uniq[i])
        if c not in kept:
            kept.append(c)
        if len(kept) >= max_colors:
            break
    for c in extra:
        if int(c) not in kept:
            kept.append(int(c))
    C = unpack(np.array(kept)).astype(np.int32)
    allu = np.unique(codes)
    d = color_distance(unpack(allu)[:, None, :], C[None, :, :])
    nearest = d.argmin(1)
    lut = dict(zip(allu.tolist(), nearest.tolist()))
    idx = np.vectorize(lut.__getitem__, otypes=[np.int32])(codes)
    return C, idx, 0


def fit_groups(C, idx, valid, bi, groups):
    """Core solver. Returns dict with chosen triples, per-block group, total cost."""
    H, W = idx.shape
    bh, bw = H // BLOCK, W // BLOCK
    n = len(C)
    hist = np.zeros((bh * bw, n))
    for by in range(bh):
        for bx in range(bw):
            sl = (slice(by * BLOCK, (by + 1) * BLOCK), slice(bx * BLOCK, (bx + 1) * BLOCK))
            v = valid[sl]
            if v.any():
                hist[by * bw + bx] = np.bincount(idx[sl][v], minlength=n)
    D = color_distance(C[:, None, :], C[None, :, :])
    rest = [i for i in range(n) if i != bi]
    while len(rest) < 3:
        rest.append(bi)
    trips = np.array(list(itertools.combinations(rest, 3)), dtype=np.int64)
    m = np.minimum.reduce([np.repeat(D[:, [bi]], len(trips), axis=1), D[:, trips[:, 0]],
                           D[:, trips[:, 1]], D[:, trips[:, 2]]])
    cost = hist @ m
    sel = pick_groups(cost, groups)
    total = float(cost[:, sel].min(1).sum())
    return dict(trips=trips, sel=sel, cost=cost, D=D, hist=hist, total=total, bh=bh, bw=bw)


# --------------------------------------------------------------------------- public API
def conform_rgba(rgba, origin=(0, 0), backdrop="black", snap=True, max_colors=24, groups=4, screen=True):
    """Conform an HxWx4 uint8 image. Returns (out_rgba, info dict).

    backdrop: 'black' | 'auto' | (r,g,b)
    """
    rgba = np.asarray(rgba, np.uint8)
    h, w = rgba.shape[:2]
    ox, oy = origin
    if backdrop in ("black", None):
        cands = [(0, 0, 0)]
    elif backdrop == "auto":
        cands = None
    else:
        cands = [tuple(int(v) for v in backdrop)]

    base = rgba.copy()
    if snap:
        base[:, :, :3] = snap_to_nes(base[:, :, :3])

    # canvas aligned to the screen's 16x16 grid
    probe, valid = compose_canvas(base, origin, (0, 0, 0), screen=screen)
    if cands is None:
        cv = pack(probe)[valid]
        u, c = np.unique(cv, return_counts=True)
        cands = [tuple(int(v) for v in unpack(np.array([u[i]]))[0]) for i in np.argsort(-c)[:5]]

    best = None
    for bd in cands:
        canvas, valid = compose_canvas(base, origin, bd, screen=screen)
        C, idx, bi = kept_palette(canvas, valid, bd, max_colors)
        fit = fit_groups(C, idx, valid, bi, groups)
        if best is None or fit["total"] < best[0]["total"]:
            best = (fit, C, idx, bi, bd, valid, canvas)
    fit, C, idx, bi, bd, valid, canvas = best

    # assign blocks and map pixels
    D, trips, sel, cost = fit["D"], fit["trips"], fit["sel"], fit["cost"]
    bw, bh = fit["bw"], fit["bh"]
    out_idx = idx.copy()
    block_group = {}
    for by in range(bh):
        for bx in range(bw):
            b = by * bw + bx
            k = int(np.argmin([cost[b, s] for s in sel]))
            slots = [bi] + list(trips[sel[k]])
            lut = np.array([slots[int(np.argmin(D[c, slots]))] for c in range(len(C))])
            sl = (slice(by * BLOCK, (by + 1) * BLOCK), slice(bx * BLOCK, (bx + 1) * BLOCK))
            out_idx[sl] = lut[idx[sl]]
            block_group[(bx, by)] = k
    out_canvas = C[out_idx].astype(np.uint8)
    out_canvas[~valid] = bd
    out = base.copy()
    out[:, :, :3] = out_canvas[oy:oy + h, ox:ox + w]
    changed = int(np.any(out[:, :, :3] != rgba[:, :, :3], axis=2)[rgba[:, :, 3] > 0].sum())
    info = dict(backdrop=tuple(int(v) for v in bd), groups=[[to_hex(C[bi])] + [to_hex(C[i]) for i in trips[s]] for s in sel],
                changed_pixels=changed, total_opaque=int((rgba[:, :, 3] > 0).sum()),
                kept_colors=len(C), snapped=bool(snap))
    return out, info


# --------------------------------------------------------------------------- tile reduction
def reduce_tiles(rgba, res, origin=(0, 0), budget=192, screen=True):
    """Merge rarely used 8x8 tile patterns into their nearest pattern until at most `budget`
    unique patterns remain. `res` must be a passing audit_canvas() result for the same image.

    A pattern is the per-pixel slot index (0=backdrop, 1..3) inside the block's palette group, so
    a replacement pattern always stays within the block's own palette -> compliance is preserved.
    Returns (new_rgba, info)."""
    h, w = rgba.shape[:2]
    bd = tuple(int(res["backdrop"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    canvas, valid = compose_canvas(rgba, origin, bd, screen=screen)
    H, W = canvas.shape[:2]
    codes = pack(canvas)
    groups = res["_group_codes"]
    bcode = res["_backdrop_code"]
    group_slots = [[bcode] + sorted(g) for g in groups]
    bw = W // BLOCK
    block_group = {(b["bx"], b["by"]): b["group"] for b in res["blocks"]}
    ntx, nty = W // TILE, H // TILE
    pats = np.zeros((nty * ntx, TILE * TILE), np.int8)
    for ty in range(nty):
        for tx in range(ntx):
            g = block_group[(tx * TILE // BLOCK, ty * TILE // BLOCK)]
            tile = codes[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE].ravel()
            slots = group_slots[g if g is not None else 0]
            lookup = {c: i for i, c in enumerate(slots)}
            pats[ty * ntx + tx] = [lookup.get(int(c), 0) for c in tile]
    before = len({p.tobytes() for p in pats})
    # tiles containing transparent pixels are locked: their pattern may be a merge *target* but is
    # never rewritten (transparent pixels cannot hold colour)
    tvalid = valid.reshape(nty, TILE, ntx, TILE).transpose(0, 2, 1, 3).reshape(nty * ntx, -1)
    inside = np.zeros((H, W), bool)
    inside[origin[1]:origin[1] + h, origin[0]:origin[0] + w] = True
    tinside = inside.reshape(nty, TILE, ntx, TILE).transpose(0, 2, 1, 3).reshape(nty * ntx, -1)
    locked_tiles = (tinside & ~tvalid).any(1)
    uniq, inv, counts = np.unique(pats, axis=0, return_inverse=True, return_counts=True)
    inv = np.asarray(inv).reshape(-1)
    U = len(uniq)
    if U <= budget:
        return rgba.copy(), dict(before=before, after=before, merged=0, note="already within budget")
    counts = counts.astype(np.float64)
    locked = np.zeros(U, bool)
    locked[np.unique(inv[locked_tiles])] = True
    blank = int(np.where((uniq == 0).all(1))[0][0]) if (uniq == 0).all(1).any() else -1
    # pairwise Hamming distance
    dist = np.zeros((U, U), np.int32)
    for i in range(U):
        dist[i] = (uniq != uniq[i]).sum(1)
    np.fill_diagonal(dist, 10 ** 6)
    alive = np.ones(U, bool)
    remap = np.arange(U)
    nearest = dist.argmin(1)
    ndist = dist[np.arange(U), nearest].astype(np.float64)
    remaining = U
    while remaining > budget:
        score = np.where(alive, counts * ndist, np.inf)
        score[locked] = np.inf
        if blank >= 0:
            score[blank] = np.inf
        p = int(score.argmin())
        if not np.isfinite(score[p]):
            break
        q = int(nearest[p])
        alive[p] = False
        remap[remap == p] = q
        counts[q] += counts[p]
        dist[:, p] = 10 ** 6
        remaining -= 1
        for u in np.where(alive & (nearest == p))[0]:
            row = np.where(alive, dist[u], 10 ** 6)
            nearest[u] = int(row.argmin())
            ndist[u] = row[nearest[u]]
    new_codes = codes.copy()
    for t in range(nty * ntx):
        tile_new = uniq[remap[inv[t]]]
        if (tile_new == pats[t]).all():
            continue
        ty, tx = divmod(t, ntx)
        g = block_group[(tx * TILE // BLOCK, ty * TILE // BLOCK)]
        slots = group_slots[g if g is not None else 0]
        new_codes[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE] = \
            np.array([slots[int(i)] for i in tile_new]).reshape(TILE, TILE)
    out_canvas = unpack(new_codes)
    ox, oy = origin
    out = rgba.copy()
    opaque = rgba[:, :, 3] > 0
    region = out_canvas[oy:oy + h, ox:ox + w]
    out[:, :, :3][opaque] = region[opaque]
    changed = int(np.any(out[:, :, :3] != rgba[:, :, :3], axis=2)[opaque].sum())
    return out, dict(before=before, after=int(remaining), merged=before - int(remaining), changed_pixels=changed)
