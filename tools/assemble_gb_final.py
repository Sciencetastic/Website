#!/usr/bin/env python3
"""Pick per-scene best of (A) GB-structure fit and (B) direct fit of the original,
snap to the NES master palette, and write the final set.
usage: assemble_gb_final.py fitA_dir fitB_dir crops_dir theme_dir gb_dir out_dir report.json"""
import glob, json, os, sys
import numpy as np
from PIL import Image

NES = [0x7c7c7c,0x0000fc,0x0000bc,0x4428bc,0x940084,0xa80020,0xa81000,0x881400,0x503000,0x007800,
       0x006800,0x005800,0x004058,0x000000,0xbcbcbc,0x0078f8,0x0058f8,0x6844fc,0xd800cc,0xe40058,
       0xf83800,0xe45c10,0xac7c00,0x00b800,0x00a800,0x00a844,0x008888,0xf8f8f8,0x3cbcfc,0x6888fc,
       0x9878f8,0xf878f8,0xf85898,0xf87858,0xfca044,0xf8b800,0xb8f818,0x58d854,0x58f898,0x00e8d8,
       0x787878,0xfcfcfc,0xa4e4fc,0xb8b8f8,0xd8b8f8,0xf8b8f8,0xf8a4c0,0xf0d0b0,0xfce0a8,0xf8d878,
       0xd8f878,0xb8f8b8,0xb8f8d8,0x00fcfc,0xf8d8f8]
NES = np.array([[(c >> 16) & 255, (c >> 8) & 255, c & 255] for c in NES], float)

def dist(a, b):
    rm = (a[..., 0] + b[..., 0]) / 2
    d = a - b
    return (2 + rm / 256) * d[..., 0]**2 + 4 * d[..., 1]**2 + (2 + (255 - rm) / 256) * d[..., 2]**2

def snap(img):
    a = np.array(img.convert("RGB")).astype(float)
    cols = np.unique(a.reshape(-1, 3), axis=0)
    m = {tuple(c): NES[dist(c[None], NES).argmin()] for c in cols}
    return Image.fromarray(np.array([[m[tuple(p)] for p in row] for row in a]).astype(np.uint8))

def main():
    fa, fb, cr, th, gbd, out, rep = sys.argv[1:8]
    os.makedirs(out, exist_ok=True)
    report = {}
    matched = json.load(open(os.path.join(fa, "report.json")))
    for n in matched:
        o = np.array(Image.open(os.path.join(cr, n + ".png")).convert("RGB")).astype(float)
        A = Image.open(os.path.join(fa, n + ".png")).convert("RGB")
        eA = float(dist(o, np.array(A).astype(float)).mean())
        bs = [(float(dist(o, np.array(Image.open(f).convert("RGB")).astype(float)).mean()), f)
              for f in glob.glob(os.path.join(fb, n + "__*.png"))]
        eB, fB = min(bs)
        pick, img = ("B_direct", Image.open(fB)) if eB < eA * 0.9 else ("A_gb_structure", A)
        snap(img).save(os.path.join(out, n + ".png"))
        report[n] = dict(method=pick, source=matched[n]["art"], offset=matched[n]["offset"],
                         err_A=round(eA), err_B=round(eB))
    for f in sorted(glob.glob(os.path.join(th, "*.png"))):
        n = os.path.splitext(os.path.basename(f))[0]
        if n in report: continue
        im = Image.open(f).convert("RGB")
        gb = np.array(Image.open(os.path.join(gbd, os.path.basename(f))).convert("RGB")).astype(int)
        # screens with the Move/verb UI: keep only the 112x112 viewport
        has_ui = (gb[:, 112:, :].mean() > 0) and "Inventory" not in n and n not in ("titlescreen", "logo", "Gameboy Graphic")
        has_ui = has_ui and (n.lower() not in ("black", "black_bg")) and im.size == (160, 144) and _ui(gb)
        (im.crop((0, 0, 112, 112)) if has_ui else im).save(os.path.join(out, n + ".png"))
        report[n] = dict(method="theme_fallback", cropped_to_viewport=bool(has_ui))
    json.dump(report, open(rep, "w"), indent=1)
    from collections import Counter
    print(Counter(r["method"] for r in report.values()))

REF = None
def _ui(gb):
    global REF
    # UI template: right column is mostly the light panel colour in rows 24..110
    panel = (224, 248, 207)
    right = gb[24:100, 120:158]
    return (right == panel).all(-1).mean() > 0.6

if __name__ == "__main__":
    main()
