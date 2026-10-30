#!/usr/bin/env python3
"""Scale+offset match of a GB viewport to an original using edge maps, which
survive the GB shade assignment not tracking original brightness.
usage: match_edges.py gb.png art.png"""
import sys
import numpy as np
from PIL import Image

GB = sorted([(7, 24, 33), (48, 104, 80), (134, 192, 108), (224, 248, 207)], key=sum)

def gb_levels(path):
    a = np.array(Image.open(path).convert("RGB")).astype(int)[:112, :112]
    return ((a[:, :, None, :] - np.array(GB)[None, None]) ** 2).sum(-1).argmin(-1).astype(float)

def edges(a):
    gy, gx = np.gradient(a)
    return np.hypot(gx, gy)

def small(a, f=4):
    h, w = a.shape[0] // f * f, a.shape[1] // f * f
    return a[:h, :w].reshape(h // f, f, w // f, f).mean((1, 3))

def search(gb_path, art_path, scales=np.arange(0.9, 1.61, 0.05), step=2):
    g = small(edges(small(gb_levels(gb_path), 2)), 2)             # 28x28 edge energy
    art = Image.open(art_path).convert("RGB")
    best = (-2, None)
    for s in scales:
        w, h = int(round(art.width * s)), int(round(art.height * s))
        if w < 112 or h < 112: continue
        lum = np.array(art.resize((w, h), Image.BILINEAR)).astype(float) @ [0.299, 0.587, 0.114]
        lum = np.digitize(lum, np.percentile(lum, [25, 50, 75])).astype(float)   # 4 levels like GB
        E = small(edges(small(lum, 2)), 2)                         # edge energy at 1/4 res
        for oy in range(0, h - 112 + 1, step):
            for ox in range(0, w - 112 + 1, step):
                win = E[oy // 4:oy // 4 + 28, ox // 4:ox // 4 + 28]
                if win.shape != g.shape: continue
                sc = np.corrcoef(g.ravel(), win.ravel())[0, 1]
                if sc > best[0]: best = (sc, (round(float(s), 2), ox, oy))
    return best

if __name__ == "__main__":
    print(search(sys.argv[1], sys.argv[2]))
