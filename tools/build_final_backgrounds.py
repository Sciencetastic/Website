#!/usr/bin/env python3
"""Assemble the final NES-compliant background set.

 - user-approved files (out/final_approved) are copied verbatim
 - every other background comes from out/gb_color_final; if its unique 8x8 pattern count is over the
   budget (192, as measured by the auditor) the tile reducer trims it (palette rules are preserved)
 - every file is audited with the app's auditor (black backdrop) and gets a 64-byte attribute table

usage: build_final_backgrounds.py out_dir
"""
import csv, glob, json, os, shutil, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))
from nes_tools.audit import audit_image, load_rgba, render_annotated
from nes_tools.convert import reduce_tiles
from nes_tools.edit import attribute_table

BUDGET = 192
out_dir = sys.argv[1]
bg_dir, at_dir = os.path.join(out_dir, "backgrounds"), os.path.join(out_dir, "attribute_tables")
for d in (bg_dir, at_dir):
    os.makedirs(d, exist_ok=True)
approved = {os.path.splitext(f)[0]: os.path.join(ROOT, "out/final_approved", f)
            for f in os.listdir(os.path.join(ROOT, "out/final_approved")) if f.endswith(".png")}
report = json.load(open(os.path.join(ROOT, "out/gb_color_final_report.json")))
rows = []
for f in sorted(glob.glob(os.path.join(ROOT, "out/gb_color_final/*.png")), key=str.lower):
    name = os.path.splitext(os.path.basename(f))[0]
    src = approved.get(name, f)
    status = "approved (untouched)" if name in approved else "auto"
    rgba = load_rgba(src)
    res, canvas = audit_image(src, tile_budget=BUDGET)
    note = ""
    if name not in approved and res["palette_pass"] and res["tiles"]["pattern_lower_bound"] > BUDGET:
        before = res["tiles"]["pattern_lower_bound"]
        new, info = reduce_tiles(rgba, res, budget=BUDGET)
        rgba = new
        Image.fromarray(rgba, "RGBA").save(os.path.join(bg_dir, name + ".png"))
        res, canvas = audit_image(os.path.join(bg_dir, name + ".png"), tile_budget=BUDGET)
        note = "tile-reduced %d->%d (%d px changed)" % (before, res["tiles"]["pattern_lower_bound"], info.get("changed_pixels", 0))
        status = "auto, tiles trimmed"
    else:
        shutil.copyfile(src, os.path.join(bg_dir, name + ".png"))
    grid = {(b["bx"], b["by"]): (b["group"] or 0) for b in res["blocks"]}
    open(os.path.join(at_dir, name + ".attr.bin"), "wb").write(attribute_table(grid))
    with open(os.path.join(at_dir, name + ".palettes.json"), "w") as fh:
        json.dump({"backdrop": res["backdrop"], "palettes": [{"palette_number": g["index"], "colors": g["colors"]} for g in res["groups"]],
                   "attribute_table_hex": attribute_table(grid).hex()}, fh, indent=1)
    method = report.get(name, {}).get("method", "")
    rows.append([name + ".png", "%dx%d" % Image.open(os.path.join(bg_dir, name + ".png")).size, "PASS" if res["palette_pass"] else "FAIL",
                 res["groups_needed"], res["conflict_blocks"], res["tiles"]["pattern_lower_bound"],
                 "yes" if res["tiles"]["pattern_lower_bound"] <= BUDGET else "no", status, method, note])
with open(os.path.join(out_dir, "audit_summary.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["file", "size", "palette_rules", "groups", "over_limit_squares", "tile_patterns", "within_192", "status", "colour_source", "note"])
    w.writerows(rows)
print(len(rows), "files |", sum(r[2] == "PASS" for r in rows), "pass palette rules |", sum(r[6] == "yes" for r in rows), "within tile budget")
print("still over budget:", [(r[0], r[5]) for r in rows if r[6] == "no"])
print("trimmed:", sum("trimmed" in r[7] for r in rows))
