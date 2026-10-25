"""Core engine tests (no GUI). Run: python tests/test_core.py"""
import os, sys, tempfile
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nes_tools import pipeline
from nes_tools.audit import audit_canvas, audit_image, compose_canvas, save_report
from nes_tools.convert import conform_rgba, reduce_tiles
from nes_tools.gb import gb_levels, colorize_theme, THEMES, theme_for
from nes_tools.palette import NES_PALETTE, snap_to_nes

passed = 0
def check(name, cond, extra=""):
    global passed
    assert cond, "FAIL: %s %s" % (name, extra)
    passed += 1
    print("ok  ", name)

rng = np.random.default_rng(7)

# 1. a compliant synthetic image passes: 4 groups x (black + 3 colours)
pal = [[(252, 160, 68), (0, 88, 0), (164, 228, 252)], [(136, 20, 0), (248, 56, 0), (252, 252, 252)],
       [(0, 64, 88), (152, 120, 248), (248, 216, 120)], [(80, 48, 0), (0, 168, 0), (188, 188, 188)]]
img = np.zeros((240, 256, 3), np.uint8)
for by in range(15):
    for bx in range(16):
        g = pal[(bx + by) % 4]
        blk = rng.integers(0, 4, (16, 16))
        for i, c in enumerate([(0, 0, 0)] + g):
            img[by * 16:(by + 1) * 16, bx * 16:(bx + 1) * 16][blk == i] = c
res = audit_canvas(img)
check("compliant image passes", res["palette_pass"] and res["groups_needed"] == 4 and res["conflict_blocks"] == 0, res["groups_needed"])

# 2. one 4-colour block fails and is reported at the right square
bad = img.copy()
bad[32:48, 48:64] = rng.integers(0, 255, (16, 16, 3))
r2 = audit_canvas(bad)
check("over-limit block detected", not r2["palette_pass"] and any(b["x"] == 48 and b["y"] == 32 for b in r2["conflicts"]))
check("conflict slot count reported", all(b["slots"] > 4 for b in r2["conflicts"]))

# 3. a 5th group is flagged
five = img.copy()
five[0:16, 0:16] = (0, 0, 0)
five[0:8, 0:16] = (0, 0, 252); five[8:16, 0:8] = (252, 0, 252); five[8:16, 8:16] = (0, 252, 252)
r3 = audit_canvas(five)
check("5th palette group flagged", r3["groups_needed"] >= 5 and not r3["palette_pass"], r3["groups_needed"])

# 4. each block gets the group whose colours it uses
g_of = {(b["bx"], b["by"]): b["group"] for b in res["blocks"]}
check("blocks assigned to groups", all(v is not None for v in g_of.values()))
check("same palette -> same group", g_of[(0, 0)] == g_of[(4, 0)] and g_of[(0, 0)] != g_of[(1, 0)])

# 5. conform: random noise image becomes compliant
noise = np.dstack([rng.integers(0, 256, (240, 256, 3)).astype(np.uint8), np.full((240, 256), 255, np.uint8)])
out, info = conform_rgba(noise)
r5, _ = audit_image(Image.fromarray(out))
check("conform noise -> compliant", r5["palette_pass"] and r5["conflict_blocks"] == 0)
check("conform output on NES palette", {tuple(c) for c in out[:, :, :3].reshape(-1, 3)} <= {tuple(c) for c in NES_PALETTE.tolist()})

# 6. conform keeps already-compliant art unchanged
rgba = np.dstack([img, np.full((240, 256), 255, np.uint8)])
out2, info2 = conform_rgba(rgba, snap=False)
check("compliant image unchanged by conform", info2["changed_pixels"] == 0, info2["changed_pixels"])

# 7. non-zero origin / odd sizes work and keep alpha
small = np.dstack([rng.integers(0, 256, (50, 70, 3)).astype(np.uint8), np.full((50, 70), 255, np.uint8)])
small[:5, :5, 3] = 0
o3, i3 = conform_rgba(small, origin=(8, 8))
check("origin 8,8 compliant", audit_image(Image.fromarray(o3), (8, 8))[0]["palette_pass"])
check("alpha preserved", (o3[:5, :5, 3] == 0).all())

# 8. tile reduction keeps compliance and meets the budget
big = np.dstack([rng.integers(0, 256, (240, 256, 3)).astype(np.uint8), np.full((240, 256), 255, np.uint8)])
cb, _ = conform_rgba(big)
rb, _ = audit_image(Image.fromarray(cb))
rd, tinfo = reduce_tiles(cb, rb, budget=192)
rr, _ = audit_image(Image.fromarray(rd))
check("tile reduction compliant", rr["palette_pass"])
check("tile reduction meets budget", rr["tiles"]["pattern_lower_bound"] <= 192, rr["tiles"]["pattern_lower_bound"])

# 9. GB colorize: theme output compliant for every theme; levels map 4 shades
shades = [(7, 24, 33), (48, 104, 80), (134, 192, 108), (224, 248, 207)]
gb = np.zeros((112, 112, 4), np.uint8); gb[:, :, 3] = 255
idx = rng.integers(0, 4, (112, 112))
for i, c in enumerate(shades):
    gb[idx == i, :3] = c
lv, ginfo = gb_levels(gb)
check("gb levels", sorted(set(lv.ravel().tolist())) == [0, 1, 2, 3] and not ginfo["quantized"])
for th in THEMES:
    cv, valid, _ = colorize_theme(lv, th)
    out = np.dstack([cv[:112, :112], np.full((112, 112), 255, np.uint8)])
    rr, _ = audit_image(Image.fromarray(out))
    assert rr["palette_pass"], th
check("all themes compliant", True)
check("theme from name", theme_for("Village_Tavern") == "warm" and theme_for("Mine_Pool") == "mine")

# 10. pipeline end-to-end (gb theme, conform, reference palette + aligned)
d = tempfile.mkdtemp()
Image.fromarray(gb).save(os.path.join(d, "gb.png"))
r = pipeline.run(os.path.join(d, "gb.png"), pipeline.Options(mode="gb"))
check("pipeline gb theme", r.audit["palette_pass"])
col = np.zeros((112, 112, 3), np.uint8)
for i, c in enumerate([(0, 0, 0), (80, 48, 0), (252, 160, 68), (248, 216, 120)]):
    col[idx == i] = c
Image.fromarray(col).save(os.path.join(d, "ref.png"))
ra = pipeline.run(os.path.join(d, "gb.png"), pipeline.Options(mode="gb", use_reference=True, reference=os.path.join(d, "ref.png")))
check("pipeline aligned reference", ra.audit["palette_pass"] and ra.details["method"] == "gb-reference-aligned", ra.details["method"])
check("aligned reference reproduces colours", (np.array(ra.image.convert("RGB")) == col).all())
rp = pipeline.run(os.path.join(d, "gb.png"), pipeline.Options(mode="gb", use_reference=True, reference=os.path.join(d, "ref.png"), ref_method="palette"))
check("pipeline palette reference", rp.audit["palette_pass"] and rp.details["method"] == "gb-reference-palette")

# 11. report files
paths = save_report(os.path.join(d, "rep"), "x", rb and audit_image(Image.fromarray(cb))[1], rb, "src")
check("report files written", all(os.path.getsize(p) > 0 for p in paths.values()))
print("\nall %d checks passed" % passed)
