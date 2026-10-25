#!/usr/bin/env python3
"""NES Auditor - check any image against the NES background palette rules.

Shows which 16x16 squares break the "backdrop + 3 colours" rule, which palette group every
square uses, how many groups the screen needs (max 4) and how many unique 8x8 tiles it has.
"""
import csv
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gui_common import (ACCENT, BAD, BG, FG, GOOD, MUTED, PANEL, ImageView, Worker, apply_theme, safe_int)  # noqa: E402
from nes_tools.audit import (BLOCK, GROUP_COLORS, CONFLICT_COLOR, audit_image, render_annotated, save_report,  # noqa: E402
                             summary_lines)
from nes_tools.palette import from_hex  # noqa: E402

IMG_TYPES = [("Images", "*.png *.gif *.bmp *.jpg *.jpeg"), ("All files", "*.*")]


class AuditorApp(tk.Tk):
    def __init__(self, initial=None):
        super().__init__()
        self.title("NES Auditor")
        self.geometry("1380x860")
        self.minsize(1100, 700)
        apply_theme(self)
        self.worker = Worker(self)
        self.path = tk.StringVar()
        self.origin_x, self.origin_y = tk.IntVar(value=0), tk.IntVar(value=0)
        self.backdrop = tk.StringVar(value="000000")
        self.screen = tk.BooleanVar(value=True)
        self.budget = tk.IntVar(value=192)
        self.nearblack = tk.IntVar(value=0)
        self.show_grid = tk.BooleanVar(value=True)
        self.show_tint = tk.BooleanVar(value=True)
        self.show_labels = tk.BooleanVar(value=True)
        self.only_bad = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Choose an image (or a folder) and press Run audit.")
        self.hover = tk.StringVar(value="")
        self.res = self.canvas = None
        self.batch_rows = []
        self._build()
        if initial:
            self.path.set(initial)
            self.after(200, self.run_audit)

    # ------------------------------------------------------------------ layout
    def _build(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Image or folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.path, width=60).grid(row=0, column=1, columnspan=5, sticky="we", padx=6)
        ttk.Button(top, text="Image…", command=self.pick_file).grid(row=0, column=6, padx=2)
        ttk.Button(top, text="Folder…", command=self.pick_folder).grid(row=0, column=7, padx=2)
        ttk.Label(top, text="Origin X,Y").grid(row=1, column=0, sticky="w", pady=(6, 0))
        sp = ttk.Frame(top)
        sp.grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Spinbox(sp, from_=0, to=255, increment=8, textvariable=self.origin_x, width=5).pack(side="left")
        ttk.Spinbox(sp, from_=0, to=239, increment=8, textvariable=self.origin_y, width=5).pack(side="left", padx=4)
        ttk.Label(top, text="Backdrop #").grid(row=1, column=2, sticky="e", pady=(6, 0))
        ttk.Entry(top, textvariable=self.backdrop, width=8).grid(row=1, column=3, sticky="w", padx=6, pady=(6, 0))
        ttk.Label(top, text="Tile budget").grid(row=1, column=4, sticky="e", pady=(6, 0))
        ttk.Spinbox(top, from_=0, to=1024, textvariable=self.budget, width=6).grid(row=1, column=5, sticky="w", padx=6, pady=(6, 0))
        ttk.Checkbutton(top, text="256×240 screen canvas", variable=self.screen).grid(row=2, column=1, sticky="w", padx=6)
        nb = ttk.Frame(top)
        nb.grid(row=2, column=2, columnspan=4, sticky="w")
        ttk.Label(nb, text="Merge near-black ≤").pack(side="left", padx=(0, 4))
        ttk.Spinbox(nb, from_=0, to=40, textvariable=self.nearblack, width=4).pack(side="left")
        ttk.Label(nb, text="(diagnostic, 0 = off)", style="Muted.TLabel").pack(side="left", padx=6)
        bt = ttk.Frame(top)
        bt.grid(row=0, column=8, rowspan=3, padx=(14, 0))
        ttk.Button(bt, text="Run audit", style="Accent.TButton", command=self.run_audit).pack(fill="x", pady=1)
        ttk.Button(bt, text="Save report…", command=self.save_report).pack(fill="x", pady=1)
        ttk.Button(bt, text="Batch folder → CSV", command=self.run_batch).pack(fill="x", pady=1)
        top.columnconfigure(1, weight=1)

        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        left = ttk.Frame(main)
        main.add(left, weight=3)
        opts = ttk.Frame(left)
        opts.pack(fill="x")
        for text, var in (("Grid", self.show_grid), ("Group tint", self.show_tint), ("Labels", self.show_labels)):
            ttk.Checkbutton(opts, text=text, variable=var, command=self.refresh_view).pack(side="left", padx=6)
        self.view = ImageView(left, "Annotated screen  (hover a square for details, click to select)",
                              on_motion=self.on_hover, on_click=self.on_click)
        self.view.pack(fill="both", expand=True)
        ttk.Label(left, textvariable=self.hover, style="Muted.TLabel", font=("Consolas", 10)).pack(fill="x", padx=4)

        right = ttk.Frame(main)
        main.add(right, weight=2)
        self.banner = tk.Label(right, text="—", bg=PANEL, fg=FG, font=("Segoe UI", 14, "bold"), pady=8)
        self.banner.pack(fill="x", pady=(0, 6))
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill="both", expand=True)
        t1 = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(t1, text="Summary")
        self.summary = tk.Text(t1, height=12, bg=PANEL, fg=FG, relief="flat", font=("Consolas", 10), wrap="word")
        self.summary.pack(fill="x")
        ttk.Label(t1, text="Palette groups (backdrop + 3 colours)", style="Head.TLabel").pack(anchor="w", pady=(10, 2))
        self.gcanvas = tk.Canvas(t1, bg=BG, highlightthickness=0, height=220)
        self.gcanvas.pack(fill="both", expand=True)
        t2 = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(t2, text="Blocks")
        ttk.Checkbutton(t2, text="Only over-limit blocks", variable=self.only_bad, command=self.fill_blocks).pack(anchor="w")
        cols = ("x", "y", "slots", "group", "colours")
        self.tree = ttk.Treeview(t2, columns=cols, show="headings", height=20)
        for c, wdt in zip(cols, (50, 50, 55, 55, 300)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=wdt, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_row)
        self.tree.tag_configure("bad", foreground="#ff8a80")
        t3 = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(t3, text="Batch")
        bc = ("file", "result", "groups", "conflicts", "tiles")
        self.btree = ttk.Treeview(t3, columns=bc, show="headings", height=20)
        for c, wdt in zip(bc, (230, 60, 60, 70, 60)):
            self.btree.heading(c, text=c)
            self.btree.column(c, width=wdt, anchor="w")
        self.btree.pack(fill="both", expand=True)
        self.btree.tag_configure("bad", foreground="#ff8a80")
        self.btree.tag_configure("ok", foreground="#7bd88f")
        self.btree.bind("<Double-1>", self.on_batch_open)

        bar = ttk.Frame(self, padding=(8, 2))
        bar.pack(fill="x")
        self.prog = ttk.Progressbar(bar, length=180)
        self.prog.pack(side="right")
        ttk.Label(bar, textvariable=self.status, style="Muted.TLabel").pack(side="left")

    # ------------------------------------------------------------------ inputs
    def pick_file(self):
        p = filedialog.askopenfilename(title="Image to audit", filetypes=IMG_TYPES)
        if p:
            self.path.set(p)
            self.run_audit()

    def pick_folder(self):
        p = filedialog.askdirectory(title="Folder of images")
        if p:
            self.path.set(p)
            self.run_batch()

    def _params(self):
        try:
            bd = from_hex(self.backdrop.get())
        except ValueError:
            raise ValueError("Backdrop must be 6 hex digits, e.g. 000000")
        return dict(origin=(safe_int(self.origin_x), safe_int(self.origin_y)), backdrop=bd,
                    tile_budget=safe_int(self.budget, 192), nearblack=safe_int(self.nearblack), screen=self.screen.get())

    # ------------------------------------------------------------------ single audit
    def run_audit(self):
        p = self.path.get().strip()
        if not p:
            return messagebox.showinfo("NES Auditor", "Choose an image first.")
        if os.path.isdir(p):
            return self.run_batch()
        try:
            prm = self._params()
        except ValueError as e:
            return messagebox.showerror("NES Auditor", str(e))
        self.status.set("Auditing…")
        self.prog.configure(mode="indeterminate")
        self.prog.start(12)

        def job(progress):
            return audit_image(p, **prm)

        def done(out, err):
            self.prog.stop()
            if err:
                self.status.set("Error: %s" % err[0])
                return messagebox.showerror("NES Auditor", "%s\n\n%s" % (err[0], err[1][-600:]))
            self.res, self.canvas = out
            self.status.set("Audited %s" % os.path.basename(p))
            self.show_result()

        self.worker.start(job, done)

    def refresh_view(self):
        if self.res is None:
            return
        scale = max(1, min(6, 1024 // self.canvas.shape[1]))
        img = render_annotated(self.canvas, self.res, scale=scale, grid=self.show_grid.get(),
                               tint=self.show_tint.get(), labels=self.show_labels.get(), legend=False)
        self._view_scale = scale
        self.view.set_image(img)

    def show_result(self):
        res = self.res
        ok = res["palette_pass"]
        self.banner.configure(text=("PASS" if ok else "FAIL") + "  —  NES palette rules", bg=GOOD if ok else BAD, fg="white")
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("end", "\n".join(summary_lines(res)[1:]))
        t = res["tiles"]
        self.summary.insert("end", "\n\nColours used: %d" % len({c for b in res["blocks"] for c in b["colors"]}))
        self.summary.configure(state="disabled")
        self.draw_groups()
        self.fill_blocks()
        self.refresh_view()
        self.view.overlay = []

    def draw_groups(self):
        g = self.gcanvas
        g.delete("all")
        y = 6
        for grp in self.res["groups"]:
            i = grp["index"]
            col = "#%02x%02x%02x" % (GROUP_COLORS[i % 4] if i < 4 else (160, 160, 160))
            g.create_text(10, y + 11, text=str(i + 1) + ("" if i < 4 else "!"), fill=col, font=("Consolas", 12, "bold"))
            for j, hx in enumerate(grp["colors"]):
                g.create_rectangle(28 + j * 78, y, 28 + j * 78 + 70, y + 22, fill=hx, outline="#777")
                g.create_text(28 + j * 78 + 35, y + 11, text=hx, font=("Consolas", 8),
                              fill="white" if sum(int(hx[k:k + 2], 16) for k in (1, 3, 5)) < 330 else "black")
            blocks = sum(1 for b in self.res["blocks"] if b["group"] == i)
            g.create_text(28 + 4 * 78 + 6, y + 11, text="%d blocks" % blocks, fill=MUTED, anchor="w", font=("Segoe UI", 9))
            y += 30
        if len(self.res["groups"]) > 4:
            g.create_text(8, y + 6, anchor="w", fill="#ff8a80", font=("Segoe UI", 9),
                          text="Groups marked ! exceed the NES limit of 4.")

    def fill_blocks(self):
        self.tree.delete(*self.tree.get_children())
        if self.res is None:
            return
        for b in self.res["blocks"]:
            if b["slots"] <= 1 or (self.only_bad.get() and not b["conflict"]):
                continue
            cols = " ".join("%s:%d" % kv for kv in b["colors"].items())
            self.tree.insert("", "end", iid="%d,%d" % (b["bx"], b["by"]), tags=("bad",) if b["conflict"] else (),
                             values=(b["x"], b["y"], b["slots"], "" if b["group"] is None else b["group"] + 1, cols))

    # ------------------------------------------------------------------ interaction
    def block_at(self, ix, iy):
        s = getattr(self, "_view_scale", 1)
        bx, by = int(ix / s) // BLOCK, int(iy / s) // BLOCK
        for b in self.res["blocks"]:
            if b["bx"] == bx and b["by"] == by:
                return b
        return None

    def on_hover(self, pos):
        if pos is None or self.res is None:
            self.hover.set("")
            return
        b = self.block_at(*pos)
        if b:
            grp = "CONFLICT" if b["conflict"] else ("empty" if b["slots"] == 1 else "group %d" % (b["group"] + 1))
            self.hover.set("square (%d,%d)  %s  slots %d  %s" % (b["x"], b["y"], grp, b["slots"], " ".join(b["colors"])))

    def on_click(self, pos):
        if self.res is None:
            return
        b = self.block_at(*pos)
        if b:
            self.select_block(b)
            iid = "%d,%d" % (b["bx"], b["by"])
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)

    def select_block(self, b):
        s = getattr(self, "_view_scale", 1)
        self.view.overlay = [(b["x"] * s, b["y"] * s, BLOCK * s, BLOCK * s, "#ffee58")]
        self.view.redraw()

    def on_row(self, _):
        sel = self.tree.selection()
        if not sel:
            return
        bx, by = map(int, sel[0].split(","))
        for b in self.res["blocks"]:
            if b["bx"] == bx and b["by"] == by:
                self.select_block(b)
                s = getattr(self, "_view_scale", 1)
                self.view.scroll_to(b["x"] * s, b["y"] * s)
                break

    # ------------------------------------------------------------------ reports + batch
    def save_report(self):
        if self.res is None:
            return messagebox.showinfo("NES Auditor", "Run an audit first.")
        folder = filedialog.askdirectory(title="Folder for the report files")
        if not folder:
            return
        base = os.path.splitext(os.path.basename(self.path.get() or "image"))[0]
        paths = save_report(folder, base, self.canvas, self.res, self.path.get())
        self.status.set("Report saved: %s" % folder)
        messagebox.showinfo("NES Auditor", "Wrote:\n" + "\n".join(os.path.basename(p) for p in paths.values()))

    def run_batch(self):
        p = self.path.get().strip()
        if not os.path.isdir(p):
            p = filedialog.askdirectory(title="Folder of images to audit")
            if not p:
                return
            self.path.set(p)
        try:
            prm = self._params()
        except ValueError as e:
            return messagebox.showerror("NES Auditor", str(e))
        self.batch_dir = p
        files = sorted(f for f in os.listdir(p) if f.lower().endswith((".png", ".gif", ".bmp", ".jpg", ".jpeg")))
        if not files:
            return messagebox.showinfo("NES Auditor", "No images in that folder.")
        out_dir = filedialog.askdirectory(title="Folder for per-image reports and summary.csv (Cancel = summary only)")
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        self.tabs.select(2)
        self.btree.delete(*self.btree.get_children())
        self.prog.configure(mode="determinate", maximum=len(files), value=0)
        self.status.set("Auditing %d images…" % len(files))

        def job(progress):
            rows = []
            for i, f in enumerate(files):
                fp = os.path.join(p, f)
                try:
                    res, canvas = audit_image(fp, **prm)
                    if out_dir:
                        save_report(out_dir, os.path.splitext(f)[0], canvas, res, fp)
                    rows.append((f, res))
                except Exception as e:  # noqa
                    rows.append((f, e))
                progress(i + 1, f)
            return rows

        def prog(i, f):
            self.prog.configure(value=i)

        def done(rows, err):
            if err:
                return messagebox.showerror("NES Auditor", str(err[0]))
            self.batch_rows = rows
            npass = 0
            for f, r in rows:
                if isinstance(r, Exception):
                    self.btree.insert("", "end", iid=f, values=(f, "ERROR", "", "", ""), tags=("bad",))
                    continue
                npass += r["palette_pass"]
                self.btree.insert("", "end", iid=f, tags=("ok" if r["palette_pass"] else "bad",),
                                  values=(f, "PASS" if r["palette_pass"] else "FAIL", r["groups_needed"], r["conflict_blocks"],
                                          r["tiles"]["pattern_lower_bound"]))
            if out_dir:
                with open(os.path.join(out_dir, "summary.csv"), "w", newline="", encoding="utf-8") as fh:
                    w = csv.writer(fh)
                    w.writerow(["file", "result", "palette_groups_needed", "conflict_blocks", "pattern_lower_bound",
                                "tile_budget", "within_budget"])
                    for f, r in rows:
                        if isinstance(r, Exception):
                            w.writerow([f, "ERROR", "", "", "", "", ""])
                        else:
                            w.writerow([f, "PASS" if r["palette_pass"] else "FAIL", r["groups_needed"], r["conflict_blocks"],
                                        r["tiles"]["pattern_lower_bound"], r["tiles"]["budget"], r["tiles"]["within_budget"]])
            self.status.set("Batch done: %d of %d pass the palette rules%s" % (npass, len(rows), " — summary.csv saved" if out_dir else ""))

        self.worker.start(job, done, prog)

    def on_batch_open(self, _):
        sel = self.btree.selection()
        if sel:
            folder = getattr(self, "batch_dir", "")
            self.path.set(os.path.join(folder, sel[0]))
            self.run_audit()


def _main():
    import traceback
    try:
        AuditorApp(sys.argv[1] if len(sys.argv) > 1 else None).mainloop()
    except Exception:  # noqa
        log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nes_tools_error.log")
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(traceback.format_exc())
        try:
            r = tk.Tk(); r.withdraw()
            messagebox.showerror("NES tools", "The program hit an error.\nDetails were saved to:\n" + log)
        except Exception:  # noqa
            pass
        raise


if __name__ == "__main__":
    _main()
