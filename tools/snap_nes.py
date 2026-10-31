#!/usr/bin/env python3
"""Snap every pixel to the nearest colour of a fixed NES colour list.
usage: snap_nes.py in.png out.png"""
import sys
from PIL import Image

NES = [(0, 0, 0), (80, 48, 0), (120, 120, 120), (188, 188, 188), (252, 252, 252),
       (0, 88, 0), (0, 168, 0), (164, 228, 252), (252, 160, 68), (248, 216, 120)]

def near(c):
    return min(NES, key=lambda n: sum((a - b) ** 2 for a, b in zip(c, n)))

im = Image.open(sys.argv[1]).convert("RGB")
for y in range(im.height):
    for x in range(im.width):
        im.putpixel((x, y), near(im.getpixel((x, y))))
im.save(sys.argv[2])
