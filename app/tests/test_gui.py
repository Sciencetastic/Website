"""GUI interaction tests. Run under a display: xvfb-run -a python tests/test_gui.py"""
import os, sys, tempfile, time
from tkinter import filedialog, messagebox
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
messagebox.showinfo = messagebox.showerror = lambda *a, **k: None   # no modal popups in tests
passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("ok  ", name)

def wait(app, timeout=60):
    t = time.time()
    while app.worker.busy and time.time() - t < timeout:
        app.update(); time.sleep(0.02)
    for _ in range(5):
        app.update(); time.sleep(0.02)

rng = np.random.default_rng(3)
d = tempfile.mkdtemp()
src = os.path.join(d, "in"); os.makedirs(src)
for i in range(3):
    Image.fromarray(rng.integers(0, 256, (240, 256, 3)).astype(np.uint8)).save(os.path.join(src, "n%d.png" % i))
good = os.path.join(d, "good.png")
bad = os.path.join(d, "bad.png")
g = np.zeros((64, 64, 3), np.uint8); g[:, :32] = (248, 56, 0); g[:, 32:] = (0, 64, 88)
Image.fromarray(g).save(good)
b = g.copy(); b[16:32, 16:32] = rng.integers(0, 255, (16, 16, 3)); Image.fromarray(b).save(bad)

# ------------------------------------------------------------------ Auditor
from nes_auditor import AuditorApp
a = AuditorApp(); a.update()
a.path.set(bad); a.run_audit(); wait(a)
check("auditor: FAIL banner on bad image", "FAIL" in a.banner.cget("text"))
check("auditor: conflict listed in Blocks tab", "1,2" in a.tree.get_children() or len(a.tree.get_children()) > 0)
a.only_bad.set(True); a.fill_blocks()
check("auditor: 'only over-limit' filter", len(a.tree.get_children()) == a.res["conflict_blocks"] and a.res["conflict_blocks"] >= 1)
# hover + click on the bad square (block 1,1)
s = a._view_scale
a.on_hover((int(20 * s), int(20 * s)))
check("auditor: hover text names square", "square (16,16)" in a.hover.get() and "CONFLICT" in a.hover.get())
a.on_click((int(20 * s), int(20 * s)))
check("auditor: click selects + highlights square", len(a.view.overlay) == 1 and a.tree.selection())
a.path.set(good); a.run_audit(); wait(a)
check("auditor: PASS banner on good image", "PASS" in a.banner.cget("text") and a.res["groups_needed"] == 1)
# options: origin and backdrop reach the engine
a.origin_x.set(16); a.run_audit(); wait(a)
check("auditor: origin applied", a.res["origin"] == [16, 0])
a.origin_x.set(0); a.backdrop.set("F83800"); a.run_audit(); wait(a)
check("auditor: custom backdrop applied", a.res["backdrop"] == "#F83800")
# report save + batch
out = os.path.join(d, "rep")
filedialog.askdirectory = lambda **k: out
a.run_audit(); wait(a); a.save_report()
check("auditor: report files saved", sorted(os.listdir(out)) == ["good_audit.html", "good_audit.json", "good_audit.png", "good_blocks.csv"])
a.path.set(src); a.backdrop.set("000000")
out2 = os.path.join(d, "rep2"); filedialog.askdirectory = lambda **k: out2
a.run_batch(); wait(a)
check("auditor: batch lists every image", len(a.btree.get_children()) == 3)
check("auditor: batch summary.csv written", os.path.exists(os.path.join(out2, "summary.csv")) and "n0_audit.png" in os.listdir(out2))
a.destroy()

# ------------------------------------------------------------------ Colorizer
from nes_colorizer import ColorizerApp
c = ColorizerApp(); c.update()
check("colorizer: GB frame disabled in conform mode", c.ref_chk.instate(["disabled"]))
c.mode.set("gb"); c.update_states()
check("colorizer: GB frame enabled in GB mode", not c.ref_chk.instate(["disabled"]) and c.ref_entry.instate(["disabled"]))
c.use_ref.set(True); c.update_states()
check("colorizer: reference checkbox enables reference + disables theme",
      not c.ref_entry.instate(["disabled"]) and c.theme_cb.instate(["disabled"]))
c.use_ref.set(False); c.mode.set("conform"); c.update_states()
c.in_path.set(os.path.join(src, "n0.png")); c.reduce_tiles.set(True); c.tile_budget.set(192)
c.run_one(); wait(c)
check("colorizer: conform run PASS", c.result is not None and c.result.audit["palette_pass"] and "PASS" in c.banner.cget("text"))
check("colorizer: tile budget respected", c.result.audit["tiles"]["pattern_lower_bound"] <= 192)
sv = os.path.join(d, "saved.png")
filedialog.asksaveasfilename = lambda **k: sv
c.save_one()
check("colorizer: save result", os.path.exists(sv))
c.backdrop_mode.set("custom"); c.backdrop_hex.set("zzzzzz")
try:
    c.build_options(); ok = False
except ValueError:
    ok = True
check("colorizer: bad hex rejected", ok)
c.backdrop_hex.set("000000"); c.backdrop_mode.set("black")
outb = os.path.join(d, "outb"); filedialog.askdirectory = lambda **k: outb
c.in_path.set(src); c.run_batch(); wait(c)
check("colorizer: batch writes outputs + summary", len([f for f in os.listdir(outb) if f.endswith("_nes.png")]) == 3 and os.path.exists(os.path.join(outb, "batch_summary.csv")))
check("colorizer: batch outputs audit clean", all(__import__("nes_tools.audit", fromlist=["x"]).audit_image(os.path.join(outb, f))[0]["palette_pass"] for f in os.listdir(outb) if f.endswith(".png")))
c.destroy()
print("\nall %d GUI checks passed" % passed)
