#!/usr/bin/env python3
"""Colour a GB viewport from its original colour art under NES rules.

Pixel structure comes from the GB image (4 shades -> any 16x16 block needs at
most 4 colours).  For every block we pick one of 4 shared palettes
(backdrop + 3 colours) and the shade->colour assignment that best reproduces
the original art's colours, then write the 112x112 viewport.

usage: gb_from_original.py gb_dir art_dir match.json out_dir [min_score]
"""
import glob, itertools, json, os, sys
import numpy as np
from PIL import Image

GB = sorted([(7, 24, 33), (48, 104, 80), (134, 192, 108), (224, 248, 207)], key=sum)
PERMS = np.array(list(itertools.permutations(range(4))))

def levels(path):
    a = np.array(Image.open(path).convert("RGB")).astype(int)[:112, :112]
    return ((a[:, :, None, :] - np.array(GB)[None, None]) ** 2).sum(-1).argmin(-1)

def box(a, k=4):
    c = np.cumsum(np.cumsum(np.pad(a, ((1, 0), (1, 0))), 0), 1)
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)

def refine(lv, art):
    lum = np.array(art.convert("RGB")).astype(float) @ [0.299, 0.587, 0.114]
    bg, bo = box(lv.astype(float)), box(lum)
    best = (-2, (0, 0))
    for dy in range(11):
        for dx in range(11):
            o = bo[dy:dy+109, dx:dx+109]
            sc = np.corrcoef(bg.ravel(), o.ravel())[0, 1]
            if sc > best[0]: best = (sc, (dx, dy))
    return best

def dist(a, b):   # redmean colour distance, a: (..,3) b: (..,3)
    rm = (a[..., 0] + b[..., 0]) / 2
    d = a - b
    return (2 + rm / 256) * d[..., 0]**2 + 4 * d[..., 1]**2 + (2 + (255 - rm) / 256) * d[..., 2]**2

def palette_of(img, keep=0.0015, merge=14):
    cols, cnt = np.unique(img.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-cnt)
    kept = []
    for i in order:                       # near-duplicates fold into the commoner colour
        if cnt[i] < keep * cnt.sum():
            continue
        if all(np.linalg.norm(cols[i].astype(float) - cols[j]) > merge for j in kept):
            kept.append(i)
    kept = np.array(kept)
    c, n = cols[kept].astype(float), cnt[kept]
    while len(c) < 5:                     # pad tiny palettes so 3-colour sets exist
        c = np.vstack([c, c[-1] + 1]); n = np.append(n, 0)
    return c, c, n

def fit(lv, rgb):
    cols, _, cnt = palette_of(rgb)
    n = len(cols)
    flat = rgb.reshape(-1, 3).astype(float)
    # snap every pixel to the nearest kept colour
    idx = dist(flat[:, None, :], cols[None]).argmin(1).reshape(112, 112)
    D = dist(cols[:, None, :], cols[None, :, :])            # n x n
    blocks = [(bx, by) for by in range(7) for bx in range(7)]
    cost = np.zeros((49, 4, n))                              # block, shade, candidate colour
    for i, (bx, by) in enumerate(blocks):
        L = lv[by*16:by*16+16, bx*16:bx*16+16].ravel()
        I = idx[by*16:by*16+16, bx*16:bx*16+16].ravel()
        for l in range(4):
            h = np.bincount(I[L == l], minlength=n)
            cost[i, l] = h @ D                               # sum over pixels of dist(pixel, cand)
    best = None
    order = np.argsort(-cnt)
    for b in order[:4]:                                      # backdrop candidates
        rest = [c for c in range(n) if c != b]
        trip = np.array(list(itertools.combinations(rest, 3))) if len(rest) >= 3 else None
        if trip is None: continue
        slots = np.concatenate([np.full((len(trip), 1), b), trip], 1)   # T x 4
        A = cost[:, :, slots]                                # B x 4 x T x 4
        tot = np.zeros((49, len(trip), len(PERMS)))
        for pi, p in enumerate(PERMS):
            tot[:, :, pi] = sum(A[:, l, :, p[l]] for l in range(4))
        bc = tot.min(2)                                      # B x T  (best bijection)
        sel = []
        for _ in range(4):                                   # greedy init
            cur = bc[:, sel].min(1) if sel else np.full(49, 1e18)
            sel.append(int(np.minimum(cur[:, None], bc).sum(0).argmin()))
        for _ in range(4):                                   # coordinate descent
            for k in range(4):
                others = [sel[j] for j in range(4) if j != k]
                cur = bc[:, others].min(1)
                sel[k] = int(np.minimum(cur[:, None], bc).sum(0).argmin())
        total = bc[:, sel].min(1).sum()
        if best is None or total < best[0]:
            best = (total, b, sel, slots, tot)
    total, b, sel, slots, tot = best
    out = np.zeros((112, 112, 3), np.uint8)
    pal_of_block = {}
    for i, (bx, by) in enumerate(blocks):
        k = int(min(range(4), key=lambda j: tot[i, sel[j]].min()))
        p = PERMS[int(tot[i, sel[k]].argmin())]
        sl = slots[sel[k]]
        pal_of_block[bx, by] = k
        for l in range(4):
            m = lv[by*16:by*16+16, bx*16:bx*16+16] == l
            out[by*16:by*16+16, bx*16:bx*16+16][m] = cols[sl[p[l]]]
    pals = [tuple(tuple(int(v) for v in cols[c]) for c in slots[s]) for s in sel]
    return out, pals, pal_of_block

def main():
    gb_dir, art_dir, mj, out_dir = sys.argv[1:5]
    min_score = float(sys.argv[5]) if len(sys.argv) > 5 else 0.75
    os.makedirs(out_dir, exist_ok=True)
    match = json.load(open(mj))
    report = {}
    for name, m in sorted(match.items(), key=lambda kv: kv[0].lower()):
        if m["score"] < min_score:
            continue
        lv = levels(os.path.join(gb_dir, name))
        art = Image.open(m["art"])
        sc, (dx, dy) = refine(lv, art)
        crop = np.array(art.convert("RGB"))[dy:dy+112, dx:dx+112]
        out, pals, pob = fit(lv, crop)
        stem = os.path.splitext(name)[0]
        Image.fromarray(out).save(os.path.join(out_dir, stem + ".png"))
        report[stem] = dict(art=os.path.relpath(m["art"], art_dir), offset=[dx, dy],
                            score=round(float(sc), 3), palettes=pals,
                            block_palettes=[[pob[x, y] for x in range(7)] for y in range(7)])
        print(f"{stem:40s} {sc:.2f} off=({dx},{dy}) backdrop={pals[0][0]}")
    json.dump(report, open(os.path.join(out_dir, "report.json"), "w"))

if __name__ == "__main__":
    main()
