#!/usr/bin/env python3
"""Replace the right-hand bush with road/hillside and add a rear wheel
(copy of the front wheel) so both wheels read. usage: in.png out.png"""
import sys
from PIL import Image

src = Image.open(sys.argv[1]).convert("RGBA")
src = src.crop(src.getchannel("A").getbbox())
im = src.copy()
W, H = im.size
GRAY, BROWN = (120, 120, 120), (80, 48, 0)

BX, BY = 101, 55            # bush bounding region (top-left)
ROAD_Y = 96                 # rows from here down are road
for y in range(BY, H):
    for x in range(BX, W):
        if y >= ROAD_Y:
            im.putpixel((x, y), src.getpixel((x - 40, y)))
        elif y < 74:
            im.putpixel((x, y), (164, 228, 252, 255))
        else:
            im.putpixel((x, y), (*(BROWN if (x + y) % 2 == 0 else GRAY), 255))

# front wheel box -> rear wheel
FW = (35, 84, 57, 108)
wheel = src.crop(FW)
RX = 90
for j in range(wheel.height):
    for i in range(wheel.width):
        p = wheel.getpixel((i, j))
        if p[:3] != (0, 0, 0) or True:
            im.putpixel((RX + i, FW[1] + j), p)
# flatten the sky gradient dither: lavender speckle surrounded by sky -> sky
SKY, LAV = (164, 228, 252), (184, 184, 248)
flat = im.copy()
for y in range(H):
    for x in range(W):
        if im.getpixel((x, y))[:3] == LAV:
            n = [im.getpixel((x + i, y + j))[:3] for i in (-1, 0, 1) for j in (-1, 0, 1)
                 if (i or j) and 0 <= x + i < W and 0 <= y + j < H]
            if n.count(SKY) >= 3:
                flat.putpixel((x, y), (*SKY, 255))
im = flat
im.save(sys.argv[2])
