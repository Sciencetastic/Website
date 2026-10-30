#!/usr/bin/env python3
"""Colour GB sprites/icons from original art, one 4-colour palette per file
(darkest shade -> backdrop colour), transparency preserved.

 1. aligned  : original layer matched pixel-for-pixel (match_sprites.py); each GB
               shade gets the modal original colour under it.
 2. reference: palette ramp from a named original (no alignment needed).
 3. fallback : the theme palette from gb_batch_colorize.py.

usage: gb_sprites_color.py gb_sprite_dir art_dir spmatch.json out_dir
"""
import json, os, sys, glob
from collections import Counter
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gb_batch_colorize as T          # theme fallback palettes (SPRITE_PALS)
import gb_palette_from_ref as R        # ramp_from_ref helpers

GB = R.GB
REFS = {
    "arrow": "UI/UI_0009s_0000_Left_arrow_on.png",
    "Backpack": "Forest_Car/Backpack.png", "Backpack-export": "Inventory/INV_BackPack.png",
    "bone": "Forest_Ext_Cave/Outside_Cave_bone.png",
    "brazer_fire": "Forest_Watch_Tower_top/watchtower top_background_melt_fire_OPEN.png",
    "brazer_sticks": "Village_BlackSmith/Village_Black_SticksinForge.png",
    "chest": "Village_Market_Interior_Burnt/Market_Interior_Burnt_Chest_Closed.png",
    "cursor": "Cursors/Talk.png",
    "DeadDeer": "Forest_Deer_Cliff/Background6Deer.png", "DeerBlood": "Forest_Deer_Cliff/Background6Bloodtrail.png",
    "ending_hero_forward": "Ending/Ending_Back_Walk1.png", "ending_hero_side": "Ending/Ending_BackSide_Walk3.png",
    "Forest_briar": "Forest_Briar/Forest_Briar_Sticks.png", "Forest_Briar_Sticks": "Forest_Briar/Forest_Briar_Sticks.png",
    "Forest_Briar_bush": "Forest_Briar/Forest_Briar_Background.png",
    "hidden_stairs": "Village_Marketplace_Locked_Bedroom/locked_marketplace_stairs_room_background.png",
    "Inv_Act1_Large": "Village_Market_Interior_Burnt/board_for_inventory.png",
    "Inv_Act1_Small": "Village_Market_Interior_Burnt/board_for_inventory.png",
    "Inv_Act1_Tools": "Village_Market_Interior_Burnt/board_for_inventory.png",
    "Inv_Keys": "Village_Barn_Office_Int/Village_Barn_Office_Int_Keys.png",
    "note_icon": "Village_Market_Interior_Burnt/Market_Interior_Burnt_Note.png",
    "Rope_Top": "Forest_Watchtower_ext/watchtower_Toprope.png",
    "tower_wolf": "Forest_Watchtower_ext/wolf_alive.png",
    "wolf": "Forest_Watchtower_ext/wolf_alive.png", "wolf_insidecavef": "Forest_Watchtower_ext/wolf_alive.png",
    "watchtower_barel": "Forest_Watchtower_ext/watchtower_barrel.png",
    "watchtower-top_TRAPDOOR": "Forest_Watchtower_ext/watchtower_Tower_closed.png",
    "watchtower_window": "Forest_Watchtower_ext/watchtower_Tower_closed.png",
    "ui_weapon": "Inventory/INV_BackPack.png",
}

def lvl(a):
    return ((a[:, :, None, :3] - np.array(GB)[None, None]) ** 2).sum(-1).argmin(-1)

def snap_cols(rgb, merge=14):
    cols, cnt = np.unique(rgb.reshape(-1, 3), axis=0, return_counts=True)
    kept = []
    for i in np.argsort(-cnt):
        if all(np.linalg.norm(cols[i].astype(float) - cols[j]) > merge for j in kept): kept.append(i)
    return cols[kept], cnt[kept]

def aligned_palette(gb, art_path, off):
    g = np.array(gb.convert("RGBA")).astype(int)
    a = np.array(Image.open(art_path).convert("RGBA"))
    ys, xs = np.where(a[:, :, 3] > 0)
    crop = a[ys.min():ys.max()+1, xs.min():xs.max()+1]
    ox, oy = off; ch, cw = crop.shape[:2]
    lv = lvl(g)
    pal = {}
    for l in range(4):
        sub = np.zeros(lv.shape, bool); sub[oy:oy+ch, ox:ox+cw] = (crop[:, :, 3] > 0)
        m = (lv == l) & sub & (g[:, :, 3] > 0)
        if not m.any(): continue
        src = np.zeros(lv.shape + (3,), np.uint8); src[oy:oy+ch, ox:ox+cw] = crop[:, :, :3]
        cols, cnt = snap_cols(src[m])
        pal[l] = tuple(int(v) for v in cols[int(np.argmax(cnt))])
    return pal

def ref_palette(art_path):
    cols, frac = R.ref_ramp(art_path)
    backdrop = cols[0]
    ramp, rf = (cols[1:], frac[1:]) if len(cols) > 3 else (cols, frac)
    pal = {0: tuple(int(v) for v in backdrop)}; prev = -1
    for l in (1, 2, 3):
        q = 0.6 * (l / 3) + 0.4 * (1.5 / 3)
        i = int(round(q * (len(ramp) - 1)))
        lo, hi = max(prev + 1, i - 1), min(len(ramp), i + 2)
        if lo >= hi: lo = min(max(prev + 1, 0), len(ramp) - 1); hi = lo + 1
        prev = lo + int(rf[lo:hi].argmax()); pal[l] = tuple(int(v) for v in ramp[prev])
    return pal

def apply(gb, pal):
    g = np.array(gb.convert("RGBA")).astype(int); lv = lvl(g)
    out = np.zeros(g.shape, np.uint8); out[:, :, 3] = g[:, :, 3]
    for l in range(4):
        out[lv == l, :3] = pal.get(l, pal.get(max(k for k in pal if k <= l), (0, 0, 0)) if any(k <= l for k in pal) else (0, 0, 0))
    return Image.fromarray(out)

def main():
    gdir, adir, mj, out = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    match = json.load(open(mj)); info = {}
    for f in sorted(glob.glob(os.path.join(gdir, "*.[pP][nN][gG]")), key=str.lower):
        stem = os.path.splitext(os.path.basename(f))[0]
        gb = Image.open(f)
        if len({c[:3] for c in gb.convert("RGBA").getdata() if c[3]}) > 8:
            continue                                    # already coloured (npc004-006)
        m = match.get(os.path.basename(f), {}); how = ""
        if m.get("score", 0) >= 0.88:
            pal = aligned_palette(gb, m["art"], m["offset"]); how = "aligned:" + os.path.relpath(m["art"], adir)
        elif stem in REFS and os.path.exists(os.path.join(adir, REFS[stem])):
            pal = ref_palette(os.path.join(adir, REFS[stem])); how = "reference:" + REFS[stem]
        else:
            pal = None
        if pal is not None and how.startswith('reference') and len(set(pal.values())) < 3:
            pal = None                                  # degenerate reference (all dark) -> theme
        if pal is None:
            tp = T.sprite_pal(stem); pal = {0: (0, 0, 0), 1: tp[0], 2: tp[1], 3: tp[2]}; how = "theme"
        apply(gb, pal).save(os.path.join(out, stem + ".png"))
        info[stem] = dict(method=how, palette={str(k): list(v) for k, v in sorted(pal.items())})
    json.dump(info, open(os.path.join(out, "report.json"), "w"), indent=1)
    print(Counter(v["method"].split(":")[0] for v in info.values()))

if __name__ == "__main__":
    main()
