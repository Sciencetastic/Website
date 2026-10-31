#!/usr/bin/env python3
"""Colour a redrawn GB screen using the colour distribution of its original art.

No pixel alignment is needed: the original's colours are ordered by brightness
and sampled at the percentile each GB shade/block-brightness band implies, so a
screen gets the original's hues.  The darkest shade is the shared backdrop.
Per 16x16 block one of 4 palettes (backdrop + 3 colours) is chosen by mean
brightness, so the NES block rule holds by construction.

usage: gb_palette_from_ref.py gb_dir art_dir out_dir
"""
import json, os, sys
import numpy as np
from PIL import Image

REFS = {
    "Angular_Death_1": "Deaths/Alch_ANGULAR.png",
    "alchemist_house": "Village_Alchemist_House/Village_Alchemist_Ext.png",
    "alchemist_house_door_open": "Village_Alchemist_House/Village_Alchemist_Door_Open.png",
    "Cellar_Candle_Death": "Village_Cellar/Cellar_Candle_Death.png",
    "CU1": "CU/CU1.png", "CU4": "CU/CU4.png", "CU5": "CU/CU5.png",
    "Face_Eaten": "Deaths/Alch_Face_Eaten.png",
    "Fall_Backswitch": "Forest_SwitchBack/Player_Fall.png",
    "Forest_Cave_Death_F1": "Deaths/Cave_In/Forest_Cave_Death_Frame1.png",
    "Forest_Cave_Death_f2": "Deaths/Cave_In/Forest_Cave_Death_Frame2.png",
    "Forest_Cave_Death_F3": "Deaths/Cave_In/Forest_Cave_Death_Frame3.png",
    "Market_Place_Death": "Deaths/Market_Place_Death.png",
    "Mine_Death": "Deaths/Mine_Death.png",
    "Mine_Temple_Flame_death": "Deaths/Mine_Temple_ flame_Death.png",
    "wolf_bite": "Deaths/wolf_bite.png",
    "Opening_1": "Opening/Opening_1.png", "Opening_2": "Opening/Opening_2.png",
    "Opening_3": "Opening/Opening_3.png", "Opening_4": "Opening/Opening_4.png",
    "Opening_5": "Opening/Opening_5.png",
    "tentacle_Death": "Tentacle_Grab_2/1_0022_Layer-2.png",
    "titlescreen": "Title/Title_BG_1.png",
    "logo": "Title/Title_title.png",
    "Village_Black_Smith": "Village_BlackSmith/Village_Black_Smith_Background.png",
    "Village_Work_Bench": "Village_Alchemist_Int_WorkBench/Village_Work_Bench_Background.png",
    "VillageValley": "Forest_Deer_Cliff/Background6VillageValley.png",
}
for n in ["Blank", "Diary_Page", "FOLIO_Journal_Select", "FOLIO_select_blank", "KEYS_select_blank",
          "LARGE_select", "LARGE_select2", "Notes_Select", "SMALL_select_blank", "TOOLS_select_blank"]:
    REFS["Inventory UI_" + n] = "UI/UI_0002_Layer-1.png"

GB = sorted([(7, 24, 33), (48, 104, 80), (134, 192, 108), (224, 248, 207)], key=sum)
BAND_MEAN = (0.5, 1.2, 1.9, 2.6)
THRESH = (0.8, 1.5, 2.2)

def dist(a, b):
    rm = (a[..., 0] + b[..., 0]) / 2
    d = a - b
    return (2 + rm / 256) * d[..., 0]**2 + 4 * d[..., 1]**2 + (2 + (255 - rm) / 256) * d[..., 2]**2

def ref_ramp(path, merge=14, keep=0.002):
    im = Image.open(path).convert("RGBA")
    a = np.array(im).reshape(-1, 4)
    a = a[a[:, 3] > 0][:, :3]
    cols, cnt = np.unique(a, axis=0, return_counts=True)
    kept = []
    for i in np.argsort(-cnt):
        if cnt[i] < keep * cnt.sum(): continue
        if all(np.linalg.norm(cols[i].astype(float) - cols[j]) > merge for j in kept): kept.append(i)
    cols, cnt = cols[kept].astype(float), cnt[kept]
    lum = cols @ [0.299, 0.587, 0.114]
    o = np.argsort(lum)
    return cols[o], cnt[o] / cnt.sum()

def build(cols, frac):
    """cols sorted dark -> light.  Backdrop = darkest colour; the remaining
    distinct colours form the ramp, sampled by position (not pixel count) so a
    big black area cannot swallow the palette."""
    backdrop = cols[0]
    ramp, rf = (cols[1:], frac[1:]) if len(cols) > 3 else (cols, frac)
    pals = []
    for m in BAND_MEAN:
        row, prev = [], -1
        for l in (1, 2, 3):
            q = 0.6 * (l / 3) + 0.4 * (m / 3)
            i = int(round(q * (len(ramp) - 1)))
            lo, hi = max(prev + 1, i - 1), min(len(ramp), i + 2)   # nearby dominant colour, strictly brighter
            if lo >= hi:
                lo, hi = min(max(prev + 1, 0), len(ramp) - 1), min(max(prev + 1, 0), len(ramp) - 1) + 1
            prev = lo + int(rf[lo:hi].argmax())
            row.append(ramp[prev])
        pals.append(row)
    return backdrop, pals

def colorize(gb_img, backdrop, pals):
    a = np.array(gb_img.convert("RGB")).astype(int)
    lv = ((a[:, :, None, :] - np.array(GB)[None, None]) ** 2).sum(-1).argmin(-1)
    h, w = lv.shape
    bw, bh = -(-w // 16), -(-h // 16)
    mean = {(bx, by): lv[by*16:by*16+16, bx*16:bx*16+16].mean() for by in range(bh) for bx in range(bw)}
    band = {k: sum(m >= t for t in THRESH) for k, m in mean.items()}
    for _ in range(2):
        nxt = {}
        for (bx, by), b in band.items():
            n = [band[bx+i, by+j] for i in (-1, 0, 1) for j in (-1, 0, 1) if (bx+i, by+j) in band]
            vals, cts = np.unique(n + [b, b], return_counts=True)
            nxt[bx, by] = int(vals[cts.argmax()])
        band = nxt
    out = np.zeros((h, w, 3), np.uint8)
    for y in range(h):
        for x in range(w):
            l = lv[y, x]
            out[y, x] = backdrop if l == 0 else pals[band[x // 16, y // 16]][l - 1]
    return Image.fromarray(out)

def main():
    gb_dir, art_dir, out_dir = sys.argv[1:4]
    os.makedirs(out_dir, exist_ok=True)
    info = {}
    for stem, rel in REFS.items():
        gp = os.path.join(gb_dir, stem + ".png")
        ap = os.path.join(art_dir, rel)
        if not (os.path.exists(gp) and os.path.exists(ap)):
            print("missing", stem, rel); continue
        cols, frac = ref_ramp(ap)
        backdrop, pals = build(cols, frac)
        colorize(Image.open(gp), backdrop, pals).save(os.path.join(out_dir, stem + ".png"))
        info[stem] = dict(reference=rel, backdrop=[int(v) for v in backdrop],
                          palettes=[[[int(v) for v in c] for c in p] for p in pals])
    json.dump(info, open(os.path.join(out_dir, "palettes.json"), "w"), indent=1)
    print(len(info), "screens colorized from reference palettes")

if __name__ == "__main__":
    main()
