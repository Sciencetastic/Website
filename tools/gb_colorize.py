#!/usr/bin/env python3
"""Colorize a 4-shade Game Boy image under NES background rules.

Darkest GB shade -> shared backdrop colour; the other 3 shades map to the 3
colours of the sub-palette chosen for each 16x16 block.
usage: gb_colorize.py in.png out.png [x y w h]   (crop defaults to 0 0 112 112)
"""
import sys
from PIL import Image

BACKDROP = (0, 0, 0)
# colours ordered darkest-to-lightest GB shade (L1, L2, L3)
PALETTES = [
    ((0, 88, 0), (0, 168, 0), (164, 228, 252)),       # 0 foliage, sky holes
    ((80, 48, 0), (188, 188, 188), (164, 228, 252)),   # 1 sky / mountain
    ((0, 88, 0), (0, 168, 0), (252, 252, 252)),        # 2 low bush, white flowers
    ((80, 48, 0), (252, 160, 68), (248, 216, 120)),    # 3 road
]
BLOCKS = [
    [0, 0, 0, 1, 1, 1, 1],
    [0, 0, 0, 1, 1, 1, 1],
    [0, 0, 1, 1, 1, 1, 1],
    [0, 0, 1, 1, 1, 1, 1],
    [2, 2, 1, 1, 1, 1, 1],
    [2, 3, 3, 3, 3, 3, 3],
    [3, 3, 3, 3, 3, 3, 3],
]

def main():
    src = Image.open(sys.argv[1]).convert("RGB")
    x, y, w, h = (int(v) for v in sys.argv[3:7]) if len(sys.argv) >= 7 else (0, 0, 112, 112)
    src = src.crop((x, y, x + w, y + h))
    shades = sorted({p for p in src.getdata()}, key=sum)
    assert len(shades) <= 4, shades
    level = {c: i for i, c in enumerate(shades)}
    out = Image.new("RGB", src.size)
    for py in range(h):
        for px in range(w):
            lv = level[src.getpixel((px, py))]
            pal = PALETTES[BLOCKS[py // 16][px // 16]]
            out.putpixel((px, py), BACKDROP if lv == 0 else pal[lv - 1])
    out.save(sys.argv[2])

if __name__ == "__main__":
    main()
