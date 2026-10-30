#!/usr/bin/env python3
"""Overlay hand-made 4-colour chunks onto a full image, then conform the whole
thing to 4 sub-palettes (backdrop black). usage: overlay_chunks.py full.png out.png chunk.png:x:y ..."""
import sys
from PIL import Image

K, N, g, L, W = (0, 0, 0), (80, 48, 0), (120, 120, 120), (188, 188, 188), (252, 252, 252)
D, G, S = (0, 88, 0), (0, 168, 0), (164, 228, 252)
O, Y = (252, 160, 68), (248, 216, 120)
NES = [K, N, g, L, W, D, G, S, O, Y]
PALETTES = {"1": (G, S, W), "2": (N, S, W), "3": (N, W, O), "4": (N, O, Y)}
SUBS = {D: K, g: N}   # no room for these in the chosen palettes
BLOCKS = [
    "1112222",
    "1112222",
    "1123332",
    "1133333",
    "1133333",
    "1433333",
    "1444444",
]

def dist(a, b):
    rm = (a[0] + b[0]) / 2
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return (2 + rm / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rm) / 256) * db * db

def snap(im):
    im = im.convert("RGB")
    for y in range(im.height):
        for x in range(im.width):
            im.putpixel((x, y), min(NES, key=lambda n: dist(im.getpixel((x, y)), n)))
    return im

comp = snap(Image.open(sys.argv[1]))
for spec in sys.argv[3:]:
    path, x, y = spec.split(":")
    comp.paste(snap(Image.open(path)), (int(x), int(y)))

changed = 0
for y in range(comp.height):
    for x in range(comp.width):
        c = comp.getpixel((x, y))
        pal = (K,) + PALETTES[BLOCKS[y // 16][x // 16]]
        c = SUBS.get(c, c) if c not in pal else c
        n = min(pal, key=lambda p: dist(c, p))
        changed += n != comp.getpixel((x, y))
        comp.putpixel((x, y), n)
comp.save(sys.argv[2])
print("pixels changed after overlay:", changed)
