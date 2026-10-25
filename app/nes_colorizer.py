#!/usr/bin/env python3
"""NES Colorizer - make art that is 100% compliant with NES background palette rules.

Two jobs:
  * Colour image  -> conform: reduce any image to NES colours, <= backdrop + 3 colours per 16x16
                     square and <= 4 palette groups for the whole screen.
  * Game Boy image -> colorize: 4-shade art gets colour, either from built-in themes or from a
                     reference image (colour artwork of the same scene).
The result is audited with the same rules the NES Auditor uses and can be saved or batch-processed.
"""
import csv
import os
import subprocess
import sys
import tempfile
import tkinter as tk
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gui_common import (BAD, GOOD, MUTED, PANEL, ImageView, Worker, apply_theme, safe_int)  # noqa: E402
from nes_tools import pipeline  # noqa: E402
from nes_tools.audit import render_annotated, summary_lines  # noqa: E402
from nes_tools.gb import THEMES  # noqa: E402

IMG_TYPES = [("Images", "*.png *.gif *.bmp *.jpg *.jpeg"), ("All files", "*.*")]
IMG_EXT = (".png", ".gif", ".bmp", ".jpg", ".jpeg")
REF_METHODS = {"Auto (align if it lines up, else palette)": "auto",
               "Aligned (same artwork, pixel match)": "aligned",
               "Palette only (any reference image)": "palette"}


class ColorizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NES Colorizer")
        self.geometry("1420x900")
        self.minsize(1180, 760)
        apply_theme(self)
        self.worker = Worker(self)
        v = tk
        self.in_path = v.StringVar()
        self.mode = v.StringVar(value="conform")
        self.use_ref = v.BooleanVar(value=False)
        self.ref_path = v.StringVar()
        self.ref_method = v.StringVar(value=list(REF_METHODS)[0])
        self.theme = v.StringVar(value="Auto (from file name)")
        self.crop_on = v.BooleanVar(value=False)
        self.crop = [v.IntVar(value=a) for a in (0, 0, 112, 112)]
        self.backdrop_mode = v.StringVar(value="black")
        self.backdrop_hex = v.StringVar(value="000000")
        self.ox, self.oy = v.IntVar(value=0), v.IntVar(value=0)
        self.reduce_tiles = v.BooleanVar(value=False)
        self.tile_budget = v.IntVar(value=192)
        self.max_colors = v.IntVar(value=24)
        self.snap = v.BooleanVar(value=True)
        self.status = v.StringVar(value="Pick an image, choose what it is, then press Run.")
        self.result = None
        self._build()
        self.update_states()

    # ------------------------------------------------------------------ layout
    def _build(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)
        left = ttk.Frame(paned, width=410)
        paned.add(left, weight=0)
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        # 1. input -----------------------------------------------------------------
        f = ttk.LabelFrame(left, text="1  Input", padding=8)
        f.pack(fill="x", pady=(0, 6))
        r = ttk.Frame(f)
        r.pack(fill="x")
        ttk.Entry(r, textvariable=self.in_path).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="Image…", command=self.pick_input).pack(side="left", padx=(6, 0))
        ttk.Button(r, text="Folder…", command=self.pick_folder).pack(side="left", padx=(4, 0))
        ttk.Label(f, text="A folder runs as a batch with the same settings.", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

        # 2. what is it ------------------------------------------------------------
        f = ttk.LabelFrame(left, text="2  What are you converting?", padding=8)
        f.pack(fill="x", pady=6)
        ttk.Radiobutton(f, text="Colour image — conform / reduce to NES", variable=self.mode, value="conform",
                        command=self.update_states).pack(anchor="w")
        ttk.Radiobutton(f, text="Game Boy (4-shade) image — colorize", variable=self.mode, value="gb",
                        command=self.update_states).pack(anchor="w", pady=(4, 0))

        # 3. GB options ------------------------------------------------------------
        self.gbf = ttk.LabelFrame(left, text="3  Game Boy colorizing", padding=8)
        self.gbf.pack(fill="x", pady=6)
        self.ref_chk = ttk.Checkbutton(self.gbf, text="Use a reference image for colors", variable=self.use_ref,
                                       command=self.update_states)
        self.ref_chk.pack(anchor="w")
        rr = ttk.Frame(self.gbf)
        rr.pack(fill="x", pady=(4, 0))
        self.ref_entry = ttk.Entry(rr, textvariable=self.ref_path)
        self.ref_entry.pack(side="left", fill="x", expand=True)
        self.ref_btn = ttk.Button(rr, text="Image…", command=self.pick_ref)
        self.ref_btn.pack(side="left", padx=(6, 0))
        self.ref_dir_btn = ttk.Button(rr, text="Folder…", command=self.pick_ref_dir)
        self.ref_dir_btn.pack(side="left", padx=(4, 0))
        self.ref_method_cb = ttk.Combobox(self.gbf, textvariable=self.ref_method, values=list(REF_METHODS), state="readonly")
        self.ref_method_cb.pack(fill="x", pady=(4, 0))
        ttk.Label(self.gbf, text="Reference = colour artwork of the same scene. For batches, give a folder\n"
                                 "(matched to each image by file name).", style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        tr = ttk.Frame(self.gbf)
        tr.pack(fill="x", pady=(8, 0))
        ttk.Label(tr, text="Theme (no reference)").pack(side="left")
        self.theme_cb = ttk.Combobox(tr, textvariable=self.theme, state="readonly", width=24,
                                     values=["Auto (from file name)"] + sorted(THEMES))
        self.theme_cb.pack(side="right")
        cr = ttk.Frame(self.gbf)
        cr.pack(fill="x", pady=(8, 0))
        self.crop_chk = ttk.Checkbutton(cr, text="Crop first  x,y,w,h", variable=self.crop_on, command=self.update_states)
        self.crop_chk.pack(side="left")
        self.crop_sp = []
        for var in self.crop:
            sp = ttk.Spinbox(cr, from_=0, to=1024, textvariable=var, width=4)
            sp.pack(side="left", padx=2)
            self.crop_sp.append(sp)

        # 4. output rules ----------------------------------------------------------
        f = ttk.LabelFrame(left, text="4  NES output rules", padding=8)
        f.pack(fill="x", pady=6)
        br = ttk.Frame(f)
        br.pack(fill="x")
        ttk.Label(br, text="Backdrop").pack(side="left")
        ttk.Radiobutton(br, text="Black", variable=self.backdrop_mode, value="black", command=self.update_states).pack(side="left", padx=6)
        self.auto_rb = ttk.Radiobutton(br, text="Auto-best", variable=self.backdrop_mode, value="auto", command=self.update_states)
        self.auto_rb.pack(side="left")
        ttk.Radiobutton(br, text="Hex", variable=self.backdrop_mode, value="custom", command=self.update_states).pack(side="left", padx=6)
        self.bd_entry = ttk.Entry(br, textvariable=self.backdrop_hex, width=8)
        self.bd_entry.pack(side="left")
        orow = ttk.Frame(f)
        orow.pack(fill="x", pady=(6, 0))
        ttk.Label(orow, text="Screen origin X,Y").pack(side="left")
        ttk.Spinbox(orow, from_=0, to=255, increment=8, textvariable=self.ox, width=5).pack(side="left", padx=(8, 2))
        ttk.Spinbox(orow, from_=0, to=239, increment=8, textvariable=self.oy, width=5).pack(side="left")
        ttk.Label(f, text="Compliant = ≤ backdrop + 3 colours per 16×16 square, ≤ 4 palette groups.",
                  style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        tb = ttk.Frame(f)
        tb.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(tb, text="Reduce unique 8×8 tiles to", variable=self.reduce_tiles).pack(side="left")
        ttk.Spinbox(tb, from_=16, to=1024, textvariable=self.tile_budget, width=6).pack(side="left", padx=6)
        ttk.Label(tb, text="(changes some pixels)", style="Muted.TLabel").pack(side="left")
        ab = ttk.Frame(f)
        ab.pack(fill="x", pady=(6, 0))
        self.snap_chk = ttk.Checkbutton(ab, text="Snap to NES master palette", variable=self.snap)
        self.snap_chk.pack(side="left")
        ttk.Label(ab, text="Max colours kept").pack(side="left", padx=(12, 4))
        ttk.Spinbox(ab, from_=6, to=40, textvariable=self.max_colors, width=4).pack(side="left")

        # 5. actions ---------------------------------------------------------------
        bt = ttk.Frame(left)
        bt.pack(fill="x", pady=(8, 0))
        self.run_btn = ttk.Button(bt, text="▶  Run", style="Accent.TButton", command=self.run_one)
        self.run_btn.pack(fill="x", pady=2)
        row = ttk.Frame(bt)
        row.pack(fill="x")
        ttk.Button(row, text="Save result…", command=self.save_one).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(row, text="Open in Auditor", command=self.open_auditor).pack(side="left", fill="x", expand=True, padx=(2, 0))
        ttk.Button(bt, text="Batch run (folder → folder)…", command=self.run_batch).pack(fill="x", pady=2)

        # right: previews ------------------------------------------------------------
        views = ttk.PanedWindow(right, orient="horizontal")
        views.pack(fill="both", expand=True)
        self.src_view = ImageView(views, "Source")
        views.add(self.src_view, weight=1)
        nb = ttk.Notebook(views)
        views.add(nb, weight=1)
        self.res_view = ImageView(nb, "")
        self.map_view = ImageView(nb, "")
        nb.add(self.res_view, text="Result")
        nb.add(self.map_view, text="Compliance map")
        self.banner = tk.Label(right, text="No result yet", bg=PANEL, fg="#cccccc", font=("Segoe UI", 13, "bold"), pady=6)
        self.banner.pack(fill="x", pady=(6, 4))
        self.text = tk.Text(right, height=13, bg=PANEL, fg="#e6e6e6", relief="flat", font=("Consolas", 10), wrap="word")
        self.text.pack(fill="x")
        bar = ttk.Frame(right)
        bar.pack(fill="x", pady=(4, 0))
        self.prog = ttk.Progressbar(bar, length=200)
        self.prog.pack(side="right")
        ttk.Label(bar, textvariable=self.status, style="Muted.TLabel").pack(side="left")

    # ------------------------------------------------------------------ enable/disable
    @staticmethod
    def _enable(widgets, on):
        for w in widgets:
            try:
                w.state(["!disabled"] if on else ["disabled"])
            except Exception:
                pass

    def update_states(self):
        gb = self.mode.get() == "gb"
        self._enable([self.ref_chk, self.theme_cb, self.crop_chk], gb)
        ref_on = gb and self.use_ref.get()
        self._enable([self.ref_entry, self.ref_btn, self.ref_dir_btn, self.ref_method_cb], ref_on)
        self._enable([self.theme_cb], gb and not self.use_ref.get())
        self._enable(self.crop_sp, gb and self.crop_on.get())
        self._enable([self.bd_entry], self.backdrop_mode.get() == "custom")
        self._enable([self.auto_rb], True)
        self._enable([self.snap_chk], True)

    # ------------------------------------------------------------------ pickers
    def pick_input(self):
        p = filedialog.askopenfilename(title="Image to convert", filetypes=IMG_TYPES)
        if p:
            self.set_input(p)

    def pick_folder(self):
        p = filedialog.askdirectory(title="Folder of images (batch)")
        if p:
            self.in_path.set(p)

    def pick_ref(self):
        p = filedialog.askopenfilename(title="Reference (colour) image", filetypes=IMG_TYPES)
        if p:
            self.ref_path.set(p)

    def pick_ref_dir(self):
        p = filedialog.askdirectory(title="Folder of reference images")
        if p:
            self.ref_path.set(p)

    def set_input(self, p):
        self.in_path.set(p)
        try:
            im = Image.open(p)
            self.src_view.set_image(im.convert("RGBA"))
            if self.mode.get() == "gb" and im.size == (160, 144) and not self.crop_on.get():
                self.crop_on.set(True)
                for var, val in zip(self.crop, (0, 0, 112, 112)):
                    var.set(val)
                self.status.set("160×144 game screen: cropped to the 112×112 viewport (untick to keep the UI).")
                self.update_states()
        except Exception as e:  # noqa
            self.status.set("Could not open image: %s" % e)

    # ------------------------------------------------------------------ options
    def build_options(self):
        bm = self.backdrop_mode.get()
        if bm == "custom":
            hx = self.backdrop_hex.get().strip().lstrip("#")
            if len(hx) != 6:
                raise ValueError("Backdrop hex must be 6 digits, e.g. 000000")
            int(hx, 16)
            backdrop = "#" + hx
        else:
            backdrop = bm
        crop = tuple(safe_int(c) for c in self.crop) if (self.mode.get() == "gb" and self.crop_on.get()) else None
        return pipeline.Options(
            mode=self.mode.get(), backdrop=backdrop, origin=(safe_int(self.ox), safe_int(self.oy)),
            tile_budget=safe_int(self.tile_budget, 192) if self.reduce_tiles.get() else 0,
            max_colors=safe_int(self.max_colors, 24), snap=self.snap.get(),
            use_reference=self.mode.get() == "gb" and self.use_ref.get() and bool(self.ref_path.get()),
            reference=self.ref_path.get() or None, ref_method=REF_METHODS.get(self.ref_method.get(), "auto"),
            theme="auto" if self.theme.get().startswith("Auto") else self.theme.get(), crop=crop)

    # ------------------------------------------------------------------ single run
    def run_one(self):
        p = self.in_path.get().strip()
        if os.path.isdir(p):
            return self.run_batch()
        if not os.path.isfile(p):
            return messagebox.showinfo("NES Colorizer", "Choose an image to convert first.")
        try:
            opt = self.build_options()
        except ValueError as e:
            return messagebox.showerror("NES Colorizer", str(e))
        if opt.use_reference and os.path.isdir(opt.reference):
            opt = replace(opt, reference=self._match_reference(os.path.basename(p), opt.reference))
            opt = replace(opt, use_reference=opt.reference is not None)
        self.src_view.set_image(Image.open(p).convert("RGBA"))
        self.status.set("Working…")
        self.prog.configure(mode="indeterminate")
        self.prog.start(12)
        self.run_btn.state(["disabled"])

        def job(progress):
            return pipeline.run(p, opt)

        def done(res, err):
            self.prog.stop()
            self.run_btn.state(["!disabled"])
            if err:
                self.status.set("Error: %s" % err[0])
                return messagebox.showerror("NES Colorizer", "%s\n\n%s" % (err[0], err[1][-700:]))
            self.show_result(res)

        self.worker.start(job, done)

    def show_result(self, res):
        self.result = res
        self.res_view.set_image(res.image)
        self.map_view.set_image(render_annotated(res.canvas, res.audit, scale=max(1, min(4, 1024 // res.canvas.shape[1])),
                                                 legend=False))
        a = res.audit
        ok = a["palette_pass"]
        self.banner.configure(text=("PASS" if ok else "FAIL") + " — NES palette rules  (%d group%s, %d over-limit squares)" % (
            a["groups_needed"], "" if a["groups_needed"] == 1 else "s", a["conflict_blocks"]),
            bg=GOOD if ok else BAD, fg="white")
        d = res.details
        lines = ["• " + n for n in res.notes]
        if d.get("changed_pixels") is not None:
            lines.append("• %d of %d pixels changed from the source" % (d["changed_pixels"], d.get("total_opaque", 0)))
        if "alignment_score" in d:
            lines.append("• reference alignment score %.2f" % d["alignment_score"])
        lines += [""] + summary_lines(a)[1:]
        self.text.delete("1.0", "end")
        self.text.insert("end", "\n".join(lines))
        self.status.set("Done — %s" % d.get("method", ""))

    def save_one(self):
        if self.result is None:
            return messagebox.showinfo("NES Colorizer", "Run a conversion first.")
        stem = os.path.splitext(os.path.basename(self.in_path.get() or "image"))[0]
        p = filedialog.asksaveasfilename(title="Save NES-compliant PNG", defaultextension=".png",
                                         initialfile=stem + "_nes.png", filetypes=[("PNG", "*.png")])
        if p:
            self.result.image.save(p)
            self.status.set("Saved %s" % p)

    def open_auditor(self):
        if self.result is None:
            return messagebox.showinfo("NES Colorizer", "Run a conversion first.")
        tmp = os.path.join(tempfile.gettempdir(), "nes_colorizer_result.png")
        self.result.image.save(tmp)
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nes_auditor.py")
        subprocess.Popen([sys.executable, script, tmp])

    # ------------------------------------------------------------------ batch
    @staticmethod
    def _match_reference(name, ref_dir):
        stem = os.path.splitext(name)[0].lower()
        files = [f for f in os.listdir(ref_dir) if f.lower().endswith(IMG_EXT)]
        by = {os.path.splitext(f)[0].lower(): f for f in files}
        hit = by.get(stem) or next((by[k] for k in by if k in stem or stem in k), None)
        return os.path.join(ref_dir, hit) if hit else None

    def run_batch(self):
        src = self.in_path.get().strip()
        if not os.path.isdir(src):
            src = filedialog.askdirectory(title="Folder of images to convert")
            if not src:
                return
            self.in_path.set(src)
        out_dir = filedialog.askdirectory(title="Output folder for the converted PNGs")
        if not out_dir:
            return
        try:
            opt = self.build_options()
        except ValueError as e:
            return messagebox.showerror("NES Colorizer", str(e))
        os.makedirs(out_dir, exist_ok=True)
        files = sorted(os.path.join(src, f) for f in os.listdir(src) if f.lower().endswith(IMG_EXT))
        if not files:
            return messagebox.showinfo("NES Colorizer", "No images in that folder.")
        self.prog.configure(mode="determinate", maximum=len(files), value=0)
        self.status.set("Batch: %d images…" % len(files))
        self.run_btn.state(["disabled"])

        def job(progress):
            rows = []
            for i, p in enumerate(files):
                o = opt
                if o.use_reference and os.path.isdir(o.reference or ""):
                    m = self._match_reference(os.path.basename(p), o.reference)
                    o = replace(o, reference=m, use_reference=m is not None)
                try:
                    r = pipeline.run(p, o)
                    op = os.path.join(out_dir, os.path.splitext(os.path.basename(p))[0] + "_nes.png")
                    r.image.save(op)
                    rows.append((p, op, r))
                except Exception as e:  # noqa
                    rows.append((p, None, e))
                progress(i + 1, p)
            return rows

        def prog(i, p):
            self.prog.configure(value=i)

        def done(rows, err):
            self.run_btn.state(["!disabled"])
            if err:
                return messagebox.showerror("NES Colorizer", str(err[0]))
            npass = 0
            with open(os.path.join(out_dir, "batch_summary.csv"), "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["file", "output", "result", "palette_groups", "conflict_blocks", "pattern_lower_bound", "notes"])
                for p, op, r in rows:
                    if isinstance(r, Exception):
                        w.writerow([os.path.basename(p), "", "ERROR", "", "", "", str(r)])
                        continue
                    npass += r.audit["palette_pass"]
                    w.writerow([os.path.basename(p), os.path.basename(op), "PASS" if r.audit["palette_pass"] else "FAIL",
                                r.audit["groups_needed"], r.audit["conflict_blocks"],
                                r.audit["tiles"]["pattern_lower_bound"], "; ".join(r.notes)])
            self.status.set("Batch done: %d of %d pass — outputs + batch_summary.csv in %s" % (npass, len(rows), out_dir))
            self.banner.configure(text="Batch: %d of %d pass" % (npass, len(rows)), bg=GOOD if npass == len(rows) else BAD, fg="white")
            self.text.delete("1.0", "end")
            for p, op, r in rows:
                self.text.insert("end", "%-42s %s\n" % (os.path.basename(p), "ERROR %s" % r if isinstance(r, Exception) else (
                    "PASS" if r.audit["palette_pass"] else "FAIL")))

        self.worker.start(job, done, prog)

    # ------------------------------------------------------------------ test hook
    def script(self, steps):
        """Used by tests: ['mode=gb', 'in=/path', 'use_ref=1', 'ref=/path', 'run'] ..."""
        def go():
            for s in steps:
                if s == "run":
                    self.run_one()
                    continue
                k, _, val = s.partition("=")
                if k == "in":
                    self.set_input(val)
                elif k == "mode":
                    self.mode.set(val)
                elif k == "use_ref":
                    self.use_ref.set(val == "1")
                elif k == "ref":
                    self.ref_path.set(val)
                elif k == "method":
                    self.ref_method.set(next(m for m in REF_METHODS if REF_METHODS[m] == val))
                elif k == "tiles":
                    self.reduce_tiles.set(True)
                    self.tile_budget.set(int(val))
                elif k == "crop":
                    self.crop_on.set(True)
                    for var, n in zip(self.crop, val.split(",")):
                        var.set(int(n))
                self.update_states()
        self.after(300, go)


if __name__ == "__main__":
    ColorizerApp().mainloop()
