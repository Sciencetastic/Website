#!/usr/bin/env python3
"""Fit an image to NES background rules: one shared backdrop colour plus
4 sub-palettes of 3 colours, one sub-palette per 16x16 attribute block.

usage: nes_quantize.py in.png out.png [--backdrop R,G,B] [--seed N]
"""
import argparse, itertools, random, sys
from PIL import Image

B = 16

def dist(a, b):
    # redmean-weighted RGB distance: cheap and close enough to perceptual
    rm = (a[0] + b[0]) / 2
    dr, dg, db = a[0]-b[0], a[1]-b[1], a[2]-b[2]
    return (2+rm/256)*dr*dr + 4*dg*dg + (2+(255-rm)/256)*db*db

def load(path, backdrop):
    im = Image.open(path).convert("RGBA")
    im = im.crop(im.getchannel("A").getbbox())
    w, h = im.size
    W, H = -(-w//B)*B, -(-h//B)*B
    px = {}
    for y in range(H):
        for x in range(W):
            if x < w and y < h:
                r, g, b, a = im.getpixel((x, y))
                px[x, y] = (r, g, b) if a else backdrop
            else:
                px[x, y] = backdrop
    return px, W, H

def block_pixels(px, bx, by):
    return [px[bx*B+i, by*B+j] for j in range(B) for i in range(B)]

def cost(hist, pal):
    return sum(n * min(dist(c, p) for p in pal) for c, n in hist.items())

def solve(blocks, backdrop, colors, rng, iters=30, k=4):
    cands = list(itertools.combinations(colors, 3))
    pals = [(backdrop,) + rng.choice(cands) for _ in range(k)]
    assign = [0]*len(blocks)
    for _ in range(iters):
        new = [min(range(k), key=lambda p: cost(h, pals[p])) for h in blocks]
        changed = new != assign
        assign = new
        for p in range(k):
            mine = [blocks[i] for i, a in enumerate(assign) if a == p]
            if not mine:
                continue
            best = min(cands, key=lambda t: sum(cost(h, (backdrop,)+t) for h in mine))
            pals[p] = (backdrop,) + best
        if not changed:
            break
    total = sum(cost(blocks[i], pals[a]) for i, a in enumerate(assign))
    return total, pals, assign

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--backdrop", default="0,0,0")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tries", type=int, default=40)
    a = ap.parse_args()
    backdrop = tuple(int(v) for v in a.backdrop.split(","))
    px, W, H = load(a.src, backdrop)
    # fold near-blacks (e.g. #080808) into true black
    px = {k: ((0, 0, 0) if sum(v) < 40 else v) for k, v in px.items()}
    colors = sorted({v for v in px.values()} - {backdrop})
    bw, bh = W//B, H//B
    hists = []
    for by in range(bh):
        for bx in range(bw):
            h = {}
            for c in block_pixels(px, bx, by):
                h[c] = h.get(c, 0) + 1
            hists.append(h)
    rng = random.Random(a.seed)
    best = min((solve(hists, backdrop, colors, rng) for _ in range(a.tries)), key=lambda r: r[0])
    total, pals, assign = best
    out = Image.new("RGB", (W, H))
    for i, p in enumerate(assign):
        bx, by = i % bw, i // bw
        for j in range(B):
            for k in range(B):
                c = px[bx*B+k, by*B+j]
                out.putpixel((bx*B+k, by*B+j), min(pals[p], key=lambda q: dist(c, q)))
    out.save(a.dst)
    print(f"error {total:.0f}; backdrop {backdrop}")
    for n, p in enumerate(pals):
        print(f" pal{n}:", *[f"#{r:02x}{g:02x}{b:02x}" for r, g, b in p[1:]])
    for by in range(bh):
        print(" ".join(str(assign[by*bw+bx]) for bx in range(bw)))

if __name__ == "__main__":
    main()
