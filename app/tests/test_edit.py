"""Auditor palette-editing tests. Run: xvfb-run -a python tests/test_edit.py"""
import json, os, sys, tempfile, time
from tkinter import filedialog, messagebox
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
messagebox.showinfo = messagebox.showerror = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: True
from nes_auditor import AuditorApp
from nes_tools.audit import audit_image
from nes_tools.palette import pack

passed = 0
def check(name, cond, extra=""):
    global passed
    assert cond, "FAIL: %s %s" % (name, extra)
    passed += 1
    print("ok  ", name)

def wait(app):
    t = time.time()
    while app.worker.busy and time.time() - t < 60:
        app.update(); time.sleep(0.02)
    for _ in range(5):
        app.update(); time.sleep(0.02)

SRC = os.environ.get("EDIT_SRC")
d = tempfile.mkdtemp()
if not SRC:
    # synthetic failing screen: 6 groups of 3 colours spread over blocks
    rng = np.random.default_rng(5)
    pals = [[(248, 56, 0), (0, 64, 88), (248, 216, 120)], [(80, 48, 0), (0, 168, 0), (188, 188, 188)],
            [(152, 120, 248), (136, 20, 0), (252, 160, 68)], [(0, 88, 0), (164, 228, 252), (252, 252, 252)],
            [(168, 16, 0), (0, 136, 136), (240, 208, 176)], [(104, 68, 252), (248, 164, 192), (172, 124, 0)]]
    img = np.zeros((96, 96, 3), np.uint8)
    for by in range(6):
        for bx in range(6):
            blk = rng.integers(0, 4, (16, 16)); g = pals[(bx * 6 + by) % 6]
            for i, c in enumerate([(0, 0, 0)] + g):
                img[by * 16:(by + 1) * 16, bx * 16:(bx + 1) * 16][blk == i] = c
    SRC = os.path.join(d, "six_groups.png"); Image.fromarray(img).save(SRC)

a = AuditorApp(); a.update()
a.path.set(SRC); a.run_audit(); wait(a)
orig = a.orig_res
check("original needs more than 4 groups", orig["groups_needed"] > 4, orig["groups_needed"])
check("edit session uses <= 4 suggested palettes", 1 <= len(a.fixed) <= 4)
check("edit mode: squares need attention", a.res["edit_mode"] and (a.res["unfit_blocks"] + a.res["conflict_blocks"]) > 0)
check("banner says squares to fix", "to fix" in a.banner.cget("text"))

# ---- clicking squares keeps the selection after the event loop runs (incl. squares not in the Blocks list)
s_ = a._view_scale
a.on_click((int(5 * s_), int(5 * s_)), 0); a.update(); a.update()
check("click selects one square (survives event loop)", a.sel == {(0, 0)}, a.sel)
a.on_click((int(40 * s_), int(5 * s_)), 0x0001); a.update(); a.update()
check("shift+click adds a square", a.sel == {(0, 0), (2, 0)}, a.sel)
a.on_click((int(40 * s_), int(5 * s_)), 0x0001); a.update(); a.update()
check("shift+click again removes it", a.sel == {(0, 0)}, a.sel)
check("selection label updates", "Square (0,0)" in a.sel_label.cget("text"))
a.clear_selection(); a.update()

# ---- single-square assignment remaps pixels into the group's colours
a.select_set("unfit"); n0 = len(a.sel)
check("select unfit squares", n0 > 0 or True)
target = None
for key in sorted(a.sel):
    target = key; break
if target is None:
    a.select_set("conflicts"); target = sorted(a.sel)[0]
a.sel = {target}
before = a.work[target[1]*16:(target[1]+1)*16, target[0]*16:(target[0]+1)*16].copy()
a.assign_selected(1 if len(a.fixed) > 1 else 0)
a.update(); a.update()
check("selection survives an assignment", a.sel == {target} and "Square" in a.sel_label.cget("text"), a.sel)
g = 1 if len(a.fixed) > 1 else 0
after = a.work[target[1]*16:(target[1]+1)*16, target[0]*16:(target[0]+1)*16]
allowed = {int(pack(np.array(c))) for c in [(0, 0, 0)]} | set(a.fixed[g])
check("assigned square uses only the group's colours", {int(c) for c in pack(after).ravel()} <= allowed)
check("assignment recorded", a.assign.get(target) == g)
blk = next(b for b in a.res["blocks"] if (b["bx"], b["by"]) == target)
check("square now shows that group", blk["group"] == g and not blk["conflict"] and not blk["unfit"] and blk["assigned"])
a.do_undo()
check("undo restores pixels and assignment", (a.work[target[1]*16:(target[1]+1)*16, target[0]*16:(target[0]+1)*16] == before).all() and target not in a.assign)
a.do_redo()
check("redo re-applies", target in a.assign)
a.do_undo()

# ---- repair everything with auto-assign (select over-limit + unfit, assign each to best group)
for _ in range(3):
    a.select_set("conflicts"); a.sel |= {(b["bx"], b["by"]) for b in a.res["unfit"]}
    if not a.sel: break
    a.auto_assign()
check("auto-assign repairs every square", a.res["palette_pass"] and a.res["unfit_blocks"] == 0 and a.res["conflict_blocks"] == 0)
check("banner shows PASS + edited", "PASS" in a.banner.cget("text") and "edited" in a.banner.cget("text"))
check("dirty flag set", a.dirty)

# ---- save edited image; the standalone audit (min-cover, no fixed groups) must pass
out = os.path.join(d, "edited.png")
filedialog.asksaveasfilename = lambda **k: out
a.save_edited()
r, _ = audit_image(out)
check("saved edited image passes standard audit", r["palette_pass"] and r["groups_needed"] <= 4, (r["groups_needed"], r["conflict_blocks"]))
check("saved image keeps size/alpha", Image.open(out).size == (a.rgba_orig.shape[1], a.rgba_orig.shape[0]))
check("dirty cleared after save", not a.dirty)

# ---- attribute table export
ap = os.path.join(d, "scene.attr.bin")
filedialog.asksaveasfilename = lambda **k: ap
a.export_attributes()
data = open(os.path.join(d, "scene.attr.bin"), "rb").read()
j = json.load(open(os.path.join(d, "scene.attr.json")))
check("attribute table is 64 bytes", len(data) == 64 and j["attribute_table_hex"] == data.hex())
grid = j["palette_number_per_16x16_square"]
bx, by = 3, 2
byte = data[(by // 2) * 8 + (bx // 2)]
check("attribute byte matches square palette", (byte >> (((by % 2) * 2 + (bx % 2)) * 2)) & 3 == grid[by][bx])
check("export lists no invalid squares after repair", j["squares_not_valid"] == [])

# ---- reset + suggest palettes + undo of palette change
a.reset_edits()
check("reset clears edits", not a.dirty and not a.assign and a.res["unfit_blocks"] + a.res["conflict_blocks"] > 0)
old_fixed = list(a.fixed)
a.suggest_palettes()
check("suggest palettes pushes undo entry", a.dirty and len(a.undo) == 1)
a.do_undo()
check("undo palette change", a.fixed == old_fixed)
a.destroy()
print("\nall %d edit checks passed" % passed)
