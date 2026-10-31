#!/usr/bin/env python3
"""Match each 4-shade GB viewport (top-left 112x112 of a 160x144 screen) to the
original 122x122 colour art and find the crop offset.
usage: match_originals.py gb_dir art_dir out.json"""
import glob, json, os, sys
import numpy as np
from PIL import Image

GB = sorted([(7, 24, 33), (48, 104, 80), (134, 192, 108), (224, 248, 207)], key=sum)

def gb_levels(path):
    a = np.array(Image.open(path).convert("RGB")).astype(int)
    d = ((a[:, :, None, :] - np.array(GB)[None, None]) ** 2).sum(-1)
    return d.argmin(-1)

def box(a, k=4):
    c = np.cumsum(np.cumsum(np.pad(a, ((1, 0), (1, 0))), 0), 1)
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)

def lum(path):
    a = np.array(Image.open(path).convert("RGB")).astype(float)
    return a @ [0.299, 0.587, 0.114]

def main():
    gb_dir, art_dir, out = sys.argv[1:4]
    arts = [f for f in glob.glob(os.path.join(art_dir, "**", "*.png"), recursive=True)
            if Image.open(f).size == (122, 122)]
    B = np.stack([box(lum(f)) for f in arts])            # N x 119 x 119
    # sample grid of 14x14 points, stride 8, on the 109x109 blurred GB window
    ys = xs = np.arange(0, 109, 8)
    res = {}
    for g in sorted(glob.glob(os.path.join(gb_dir, "*.[pP][nN][gG]")), key=str.lower):
        lv = gb_levels(g)[:112, :112].astype(float)
        bg = box(lv)                                      # 109 x 109
        s = bg[np.ix_(ys, xs)].ravel()
        if s.std() < 1e-6:
            continue
        s = (s - s.mean()) / s.std()
        best = (-2, None, None)
        for dy in range(11):
            for dx in range(11):
                o = B[:, dy:dy+109, dx:dx+109][:, ys][:, :, xs].reshape(len(arts), -1)
                o = (o - o.mean(1, keepdims=True)) / (o.std(1, keepdims=True) + 1e-9)
                sc = (o * s).mean(1)
                i = int(sc.argmax())
                if sc[i] > best[0]:
                    best = (float(sc[i]), arts[i], (dx, dy))
        res[os.path.basename(g)] = dict(score=round(best[0], 3), art=best[1], offset=best[2])
        print(f"{os.path.basename(g):45s} {best[0]:.2f} {best[2]} {os.path.relpath(best[1], art_dir)}")
    json.dump(res, open(out, "w"), indent=1)

if __name__ == "__main__":
    main()
