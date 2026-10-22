#!/usr/bin/env python3
"""Apply a hand-chosen block->palette map: each pixel snaps to the nearest
colour of its block's palette (backdrop is always available).
usage: nes_fixed_palettes.py in.png out.png"""
import sys
from PIL import Image

K, N, L, W = (0, 0, 0), (80, 48, 0), (188, 188, 188), (252, 252, 252)
D, G, S = (0, 88, 0), (0, 168, 0), (164, 228, 252)
O, Y = (252, 160, 68), (248, 216, 120)
BACKDROP = K
PALETTES = {
    "A": (S, D, G),   # foliage / sky holes
    "B": (S, N, L),   # sky and mountain
    "C": (N, Y, O),   # road, wheels
    "E": (W, D, G),   # low bush with white flowers
}
# explicit substitutions where nearest-colour picks the wrong stand-in
SUBS = {"B": {W: L}, "C": {W: Y}}
BLOCKS = [
    "AAABBBB",
    "AAABBBB",
    "AABBBBB",
    "AABBBBB",
    "EEBBBBB",
    "ECCCCCC",
    "CCCCCCC",
]

def dist(a, b):
    rm = (a[0] + b[0]) / 2
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return (2 + rm / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rm) / 256) * db * db

im = Image.open(sys.argv[1]).convert("RGB")
out = im.copy()
changed = 0
for y in range(im.height):
    for x in range(im.width):
        c = im.getpixel((x, y))
        c = SUBS.get(BLOCKS[y // 16][x // 16], {}).get(c, c)
        pal = (BACKDROP,) + PALETTES[BLOCKS[y // 16][x // 16]]
        n = min(pal, key=lambda p: dist(c, p))
        changed += n != im.getpixel((x, y))
        out.putpixel((x, y), n)
out.save(sys.argv[2])
print("changed pixels:", changed)
