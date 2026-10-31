#!/usr/bin/env python3
"""Scale+offset search for GB viewports whose original was re-framed.
usage: match_scaled.py gb_dir art_file gb_name -> prints best (scale, ox, oy, score)"""
import sys
import numpy as np
from PIL import Image

GB = sorted([(7, 24, 33), (48, 104, 80), (134, 192, 108), (224, 248, 207)], key=sum)

def gb_levels(path):
    a = np.array(Image.open(path).convert("RGB")).astype(int)[:112, :112]
    return ((a[:, :, None, :] - np.array(GB)[None, None]) ** 2).sum(-1).argmin(-1).astype(float)

def small(a, f=4):
    h, w = a.shape[0] // f * f, a.shape[1] // f * f
    return a[:h, :w].reshape(h // f, f, w // f, f).mean((1, 3))

def search(gb_path, art_path):
    g = small(gb_levels(gb_path))                      # 28x28
    art = Image.open(art_path).convert("RGB")
    best = (-2, None)
    for s in np.arange(0.80, 1.61, 0.05):              # GB = orig * s
        w = int(round(art.width * s)); h = int(round(art.height * s))
        if w < 112 or h < 112: continue
        lum = np.array(art.resize((w, h), Image.BILINEAR)).astype(float) @ [0.299, 0.587, 0.114]
        for oy in range(0, h - 112 + 1, 2):
            for ox in range(0, w - 112 + 1, 2):
                win = small(lum[oy:oy+112, ox:ox+112])
                sc = np.corrcoef(g.ravel(), win.ravel())[0, 1]
                if sc > best[0]: best = (sc, (round(float(s), 2), ox, oy))
    return best

if __name__ == "__main__":
    print(search(sys.argv[1], sys.argv[2]))
