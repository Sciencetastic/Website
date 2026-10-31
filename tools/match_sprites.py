#!/usr/bin/env python3
"""Match 4-shade GB sprites to original colour layers.  Originals are often
122x122 layers with transparency, so each is cropped to its visible bounding
box and the GB sprite is slid over it (GB sprites are padded to tile sizes).
usage: match_sprites.py gb_sprite_dir art_dir out.json"""
import glob, json, os, sys
import numpy as np
from PIL import Image

GB = sorted([(7, 24, 33), (48, 104, 80), (134, 192, 108), (224, 248, 207)], key=sum)

def load_arts(adir):
    arts = []
    for f in glob.glob(os.path.join(adir, "**", "*.[pP][nN][gG]"), recursive=True):
        try: a = np.array(Image.open(f).convert("RGBA"))
        except Exception: continue
        m = a[:, :, 3] > 0
        if m.sum() < 8: continue
        ys, xs = np.where(m)
        crop = a[ys.min():ys.max()+1, xs.min():xs.max()+1].astype(float)
        if crop.shape[0] > 130 or crop.shape[1] > 300: continue
        arts.append((f, crop, (int(xs.min()), int(ys.min()))))
    return arts

def main():
    gdir, adir, out = sys.argv[1:4]
    arts = load_arts(adir)
    res = {}
    for g in sorted(glob.glob(os.path.join(gdir, "*.[pP][nN][gG]")), key=str.lower):
        ga = np.array(Image.open(g).convert("RGBA")).astype(int)
        if len({tuple(c[:3]) for c in ga.reshape(-1, 4) if c[3]}) > 8: continue
        gh, gw = ga.shape[:2]
        lv = ((ga[:, :, None, :3] - np.array(GB)[None, None]) ** 2).sum(-1).argmin(-1).astype(float)
        best = (-2, None, None)
        for f, c, org in arts:
            ch, cw = c.shape[:2]
            if ch > gh or cw > gw or gh - ch > 16 or gw - cw > 16: continue
            lum = c[:, :, :3] @ [0.299, 0.587, 0.114]; m = c[:, :, 3] > 0
            for oy in range(gh - ch + 1):
                for ox in range(gw - cw + 1):
                    x, y = lv[oy:oy+ch, ox:ox+cw][m], lum[m]
                    if x.size < 8 or x.std() < 1e-6 or y.std() < 1e-6: continue
                    sc = float(np.corrcoef(x, y)[0, 1])
                    if sc > best[0]: best = (sc, f, (ox, oy))
        res[os.path.basename(g)] = dict(score=round(best[0], 3), art=best[1], offset=best[2])
        print(f"{os.path.basename(g):32s} {(gw, gh)}  {best[0]:.2f}  {os.path.relpath(best[1], adir) if best[1] else '-'}  {best[2]}")
    json.dump(res, open(out, "w"), indent=1)

if __name__ == "__main__":
    main()
