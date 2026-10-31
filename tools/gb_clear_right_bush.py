#!/usr/bin/env python3
"""GB-source version of clear_right_bush: remove right bush, add rear wheel.
usage: gb_clear_right_bush.py in.png out.png   (works on the 112x112 scene at 0,0)"""
import sys
from PIL import Image

src = Image.open(sys.argv[1]).convert("RGB")
shades = sorted(set(src.crop((0, 0, 112, 112)).getdata()), key=sum)
L1, L2, L3 = shades[1], shades[2], shades[3]
im = src.copy()

BX, BY = 100, 60       # bush top-left
SKY_Y, ROAD_Y = 72, 90
for y in range(BY, 112):
    for x in range(BX, 112):
        if y >= ROAD_Y:
            im.putpixel((x, y), src.getpixel((x - 40, y)))   # road texture
        elif y < SKY_Y:
            im.putpixel((x, y), L3)                          # sky
        else:
            im.putpixel((x, y), L1 if (x + y) % 2 else L2)   # hillside dither

FW = (38, 78, 57, 96)  # front wheel box
wheel = src.crop(FW)
RX = 84
im.paste(wheel, (RX, FW[1]))
im.save(sys.argv[2])
