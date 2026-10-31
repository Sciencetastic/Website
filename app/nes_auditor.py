"""NES Auditor - check any image against the NES background palette rules.

Shows which 16x16 squares break the "backdrop + 3 colours" rule, which palette group every
square uses, how many groups the screen needs (max 4) and how many unique 8x8 tiles it has.
"""
import csv
import json
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gui_common import (ACCENT, BAD, BG, FG, GOOD, MUTED, PANEL, ImageView, Worker, apply_theme, safe_int)  # noqa: E402
from nes_tools.audit import (BLOCK, GROUP_COLORS, CONFLICT_COLOR, audit_canvas, audit_image, compose_canvas,  # noqa: E402
                             load_rgba, render_annotated, save_report, summary_lines)
from nes_tools.edit import (assign_block, attribute_table, best_group_for_block, suggest_groups)  # noqa: E402
from nes_tools.palette import from_hex, pack, to_hex  # noqa: E402

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
        # edit session
        self.rgba_orig = self.work = self.valid = self.orig_res = None
        self.fixed, self.assign, self.sel = [], {}, set()
        self.undo, self.redo = [], []
        self.dirty = False
        self.edit_prm = None
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
        self.view = ImageView(left, "Annotated screen  (click a square to select, Shift+click adds)",
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
        te = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(te, text="Edit")
        self._build_edit_tab(te)
        t2 = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(t2, text="Blocks")
        ttk.Checkbutton(t2, text="Only over-limit blocks", variable=self.only_bad, command=self.fill_blocks).pack(anchor="w")
        cols = ("x", "y", "slots", "group", "colours")
        self.tree = ttk.Treeview(t2, columns=cols, show="headings", height=20, selectmode="extended")
        for c, wdt in zip(cols, (50, 50, 55, 55, 300)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=wdt, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_row)
        self.tree.tag_configure("bad", foreground="#ff8a80")
        self.tree.tag_configure("warn", foreground="#ffb74d")
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
        for k in "1234":
            self.bind(k, lambda e, g=int(k) - 1: self._key_assign(g))
        self.bind("<Control-z>", lambda e: self.do_undo())
        self.bind("<Control-y>", lambda e: self.do_redo())

    def _build_edit_tab(self, f):
        ttk.Label(f, text="Change the palette group of selected squares", style="Head.TLabel").pack(anchor="w")
        ttk.Label(f, text="Click a square (Shift+click to add more), then press a group button or the keys 1–4.\n"
                          "The square's pixels are remapped into that group's colours; undo with Ctrl+Z.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(2, 6))
        self.sel_label = ttk.Label(f, text="No squares selected.", font=("Consolas", 10), justify="left")
        self.sel_label.pack(anchor="w", pady=(0, 6))
        self.edit_rows = []
        for k in range(4):
            row = ttk.Frame(f)
            row.pack(fill="x", pady=2)
            cv = tk.Canvas(row, width=300, height=26, bg=BG, highlightthickness=0)
            cv.pack(side="left")
            btn = ttk.Button(row, text="Assign to group %d" % (k + 1), command=lambda g=k: self.assign_selected(g))
            btn.pack(side="left", padx=8)
            self.edit_rows.append((cv, btn))
        r1 = ttk.Frame(f)
        r1.pack(fill="x", pady=(8, 2))
        ttk.Button(r1, text="Auto-assign best group", command=self.auto_assign).pack(side="left", padx=(0, 4))
        ttk.Button(r1, text="Select over-limit", command=lambda: self.select_set("conflicts")).pack(side="left", padx=4)
        ttk.Button(r1, text="Select unfit", command=lambda: self.select_set("unfit")).pack(side="left", padx=4)
        ttk.Button(r1, text="Clear", command=self.clear_selection).pack(side="left", padx=4)
        r2 = ttk.Frame(f)
        r2.pack(fill="x", pady=2)
        self.undo_btn = ttk.Button(r2, text="Undo", command=self.do_undo)
        self.undo_btn.pack(side="left", padx=(0, 4))
        self.redo_btn = ttk.Button(r2, text="Redo", command=self.do_redo)
        self.redo_btn.pack(side="left", padx=4)
        ttk.Button(r2, text="Reset all edits", command=self.reset_edits).pack(side="left", padx=4)
        r3 = ttk.Frame(f)
        r3.pack(fill="x", pady=(10, 2))
        ttk.Button(r3, text="Suggest 4 palettes", command=self.suggest_palettes).pack(side="left", padx=(0, 4))
        ttk.Button(r3, text="Use detected palettes", command=self.use_detected).pack(side="left", padx=4)
        ttk.Label(f, text="Suggest = best 4 groups for the current pixels (needed when the image uses more than 4).",
                  style="Muted.TLabel").pack(anchor="w")
        r4 = ttk.Frame(f)
        r4.pack(fill="x", pady=(12, 2))
        ttk.Button(r4, text="Save edited image…", style="Accent.TButton", command=self.save_edited).pack(side="left", padx=(0, 4))
        ttk.Button(r4, text="Export attribute table…", command=self.export_attributes).pack(side="left", padx=4)

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
        if self.dirty and not messagebox.askyesno("NES Auditor", "You have unsaved palette edits. Discard them and audit again?"):
            return
        self.status.set("Auditing…")
        self.prog.configure(mode="indeterminate")
        self.prog.start(12)

        def job(progress):
            out = audit_image(p, **prm)
            return out + (load_rgba(p),)

        def done(out, err):
            self.prog.stop()
            if err:
                self.status.set("Error: %s" % err[0])
                return messagebox.showerror("NES Auditor", "%s\n\n%s" % (err[0], err[1][-600:]))
            self.res, self.canvas, rgba = out
            self.status.set("Audited %s" % os.path.basename(p))
            self.begin_edit_session(rgba, prm)
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
        if res.get("edit_mode") and not ok:
            n = res["conflict_blocks"] + res["unfit_blocks"]
            txt = "FAIL  —  %d square%s to fix" % (n, "" if n == 1 else "s")
        else:
            txt = ("PASS" if ok else "FAIL") + "  —  NES palette rules"
        self.banner.configure(text=txt + ("   (edited)" if self.dirty else ""), bg=GOOD if ok else BAD, fg="white")
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("end", "\n".join(summary_lines(res)[1:]))
        self.summary.insert("end", "\n\nColours used: %d" % len({c for b in res["blocks"] for c in b["colors"]}))
        if res.get("edit_mode") and self.orig_res is not None:
            o = self.orig_res
            self.summary.insert("end", "\nOriginal image: %d group(s) needed, %d over-limit squares" % (o["groups_needed"], o["conflict_blocks"]))
        self.summary.configure(state="disabled")
        self.draw_groups()
        self.draw_edit_groups()
        self.fill_blocks()
        self.refresh_view()
        self.draw_selection()

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
        self._syncing = True                      # deleting/adding rows fires selection events
        self.tree.delete(*self.tree.get_children())
        if self.res is None:
            self.after_idle(lambda: setattr(self, "_syncing", False))
            return
        for b in self.res["blocks"]:
            if b["slots"] <= 1 or (self.only_bad.get() and not (b["conflict"] or b.get("unfit"))):
                continue
            cols = " ".join("%s:%d" % kv for kv in b["colors"].items())
            self.tree.insert("", "end", iid="%d,%d" % (b["bx"], b["by"]),
                             tags=("bad",) if b["conflict"] else (("warn",) if b.get("unfit") else ()),
                             values=(b["x"], b["y"], b["slots"], "" if b["group"] is None else b["group"] + 1, cols))
        self.sync_tree_selection()

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
            grp = ("CONFLICT" if b["conflict"] else "empty" if b["slots"] == 1 else
                   "fits no palette" if b.get("unfit") else "group %d%s" % (b["group"] + 1, "*" if b.get("assigned") else ""))
            self.hover.set("square (%d,%d)  %s  slots %d  %s" % (b["x"], b["y"], grp, b["slots"], " ".join(b["colors"])))

    def on_click(self, pos, state=0):
        if self.res is None:
            return
        b = self.block_at(*pos)
        if not b:
            return
        key = (b["bx"], b["by"])
        if state & 0x0001:                       # Shift: toggle in selection
            self.sel ^= {key}
        else:
            self.sel = {key}
        self.sync_tree_selection()
        self.draw_selection()

    def sync_tree_selection(self):
        # <<TreeviewSelect>> is delivered later by the event loop, so keep the guard up until idle
        self._syncing = True
        ids = [("%d,%d" % k) for k in sorted(self.sel) if self.tree.exists("%d,%d" % k)]
        self.tree.selection_set(ids)
        if ids:
            self.tree.see(ids[-1])
        self.after_idle(lambda: setattr(self, "_syncing", False))

    def on_row(self, _):
        if getattr(self, "_syncing", False) or self.res is None:
            return
        self.sel = {tuple(map(int, i.split(","))) for i in self.tree.selection()}
        self.draw_selection()
        if self.sel:
            bx, by = sorted(self.sel)[0]
            s = getattr(self, "_view_scale", 1)
            self.view.scroll_to(bx * BLOCK * s, by * BLOCK * s)

    def select_set(self, which):
        if self.res is None:
            return
        self.sel = {(b["bx"], b["by"]) for b in self.res[which]}
        self.sync_tree_selection()
        self.draw_selection()

    def clear_selection(self):
        self.sel = set()
        self.sync_tree_selection()
        self.draw_selection()

    def draw_selection(self):
        s = getattr(self, "_view_scale", 1)
        self.view.overlay = [(bx * BLOCK * s, by * BLOCK * s, BLOCK * s, BLOCK * s, "#ffee58") for bx, by in sorted(self.sel)]
        self.view.redraw()
        if not self.sel or self.res is None:
            self.sel_label.configure(text="No squares selected.")
            return
        if len(self.sel) == 1:
            bx, by = next(iter(self.sel))
            b = next(x for x in self.res["blocks"] if x["bx"] == bx and x["by"] == by)
            g = ("OVER LIMIT (%d slots)" % b["slots"] if b["conflict"] else "fits no palette" if b.get("unfit")
                 else "empty" if b["slots"] == 1 else "group %d" % (b["group"] + 1))
            self.sel_label.configure(text="Square (%d,%d): %s\n%s" % (b["x"], b["y"], g, "  ".join(b["nonbackdrop"]) or "backdrop only"))
        else:
            self.sel_label.configure(text="%d squares selected." % len(self.sel))

    # ------------------------------------------------------------------ edit session
    def begin_edit_session(self, rgba, prm):
        """Start editing the just-audited image against a fixed set of <= 4 palette groups."""
        self.rgba_orig, self.edit_prm = rgba, prm
        canvas, valid = compose_canvas(rgba, prm["origin"], prm["backdrop"], screen=prm["screen"])
        self.base_canvas, self.work, self.valid = canvas.copy(), canvas.copy(), valid
        self.orig_res = self.res
        if self.res["groups_needed"] <= 4:
            self.fixed = [tuple(g) for g in self.res["_group_codes"]]
        else:
            self.fixed = suggest_groups(self.work, valid, prm["backdrop"])
        self.assign, self.sel, self.undo, self.redo, self.dirty = {}, set(), [], [], False
        self.refresh_audit(show=False)

    def refresh_audit(self, show=True):
        prm = self.edit_prm
        self.res = audit_canvas(self.work, prm["backdrop"], prm["tile_budget"], 0, self.valid,
                                fixed_groups=self.fixed, assignments=self.assign)
        self.res["origin"] = [int(prm["origin"][0]), int(prm["origin"][1])]
        self.res["image_size"] = [int(self.rgba_orig.shape[1]), int(self.rgba_orig.shape[0])]
        self.canvas = self.work
        self._update_undo_buttons()
        if show:
            self.show_result()

    def _update_undo_buttons(self):
        self.undo_btn.state(["!disabled"] if self.undo else ["disabled"])
        self.redo_btn.state(["!disabled"] if self.redo else ["disabled"])

    def draw_edit_groups(self):
        for k, (cv, btn) in enumerate(self.edit_rows):
            cv.delete("all")
            exists = self.res is not None and k < len(self.res["groups"])
            btn.state(["!disabled"] if exists else ["disabled"])
            col = "#%02x%02x%02x" % GROUP_COLORS[k]
            cv.create_text(10, 13, text=str(k + 1), fill=col, font=("Consolas", 12, "bold"))
            if not exists:
                cv.create_text(40, 13, text="(no palette)", fill=MUTED, anchor="w", font=("Segoe UI", 9))
                continue
            for j, hx in enumerate(self.res["groups"][k]["colors"]):
                cv.create_rectangle(26 + j * 66, 2, 26 + j * 66 + 60, 24, fill=hx, outline="#777")
                cv.create_text(26 + j * 66 + 30, 13, text=hx, font=("Consolas", 8),
                               fill="white" if sum(int(hx[i:i + 2], 16) for i in (1, 3, 5)) < 330 else "black")

    def _key_assign(self, g):
        if isinstance(self.focus_get(), (ttk.Entry, ttk.Spinbox, tk.Text)):
            return
        if self.sel and self.res is not None and g < len(self.fixed):
            self.assign_selected(g)

    def _apply_assignments(self, items):
        """items: list of ((bx,by), group_index). Applies, records an undo entry."""
        backdrop = self.edit_prm["backdrop"]
        entry = {"kind": "blocks", "changes": []}
        for (bx, by), g in items:
            sl = (slice(by * BLOCK, (by + 1) * BLOCK), slice(bx * BLOCK, (bx + 1) * BLOCK))
            old_px, old_as = self.work[sl].copy(), self.assign.get((bx, by))
            assign_block(self.work, bx, by, self.fixed[g], backdrop)
            self.assign[(bx, by)] = g
            entry["changes"].append(((bx, by), old_px, old_as, self.work[sl].copy(), g))
        self.undo.append(entry)
        self.redo.clear()
        self.dirty = True
        self.refresh_audit()

    def assign_selected(self, g):
        if self.res is None or not self.sel:
            return messagebox.showinfo("NES Auditor", "Click a square in the image first.")
        if g >= len(self.fixed):
            return
        self._apply_assignments([(k, g) for k in sorted(self.sel)])
        self.status.set("Assigned %d square(s) to group %d" % (len(self.sel), g + 1))

    def auto_assign(self):
        if self.res is None or not self.sel:
            return messagebox.showinfo("NES Auditor", "Click a square in the image first.")
        items = [(k, best_group_for_block(self.work, k[0], k[1], self.fixed, self.edit_prm["backdrop"])) for k in sorted(self.sel)]
        self._apply_assignments(items)
        self.status.set("Auto-assigned %d square(s) to their best-fitting group" % len(items))

    def _restore(self, entry, forward):
        if entry["kind"] == "blocks":
            for (bx, by), old_px, old_as, new_px, g in entry["changes"]:
                sl = (slice(by * BLOCK, (by + 1) * BLOCK), slice(bx * BLOCK, (bx + 1) * BLOCK))
                self.work[sl] = new_px if forward else old_px
                tgt = g if forward else old_as
                if tgt is None:
                    self.assign.pop((bx, by), None)
                else:
                    self.assign[(bx, by)] = tgt
        else:
            self.fixed, self.assign = (entry["new"] if forward else entry["old"])
            self.fixed, self.assign = list(self.fixed), dict(self.assign)

    def do_undo(self):
        if not self.undo:
            return
        e = self.undo.pop()
        self._restore(e, False)
        self.redo.append(e)
        self.dirty = bool(self.undo)
        self.refresh_audit()

    def do_redo(self):
        if not self.redo:
            return
        e = self.redo.pop()
        self._restore(e, True)
        self.undo.append(e)
        self.dirty = True
        self.refresh_audit()

    def reset_edits(self):
        if self.rgba_orig is None:
            return
        if self.dirty and not messagebox.askyesno("NES Auditor", "Throw away all edits and palette changes?"):
            return
        self.begin_edit_session(self.rgba_orig, self.edit_prm)
        self.show_result()

    def _set_palettes(self, groups, label):
        entry = {"kind": "palettes", "old": (list(self.fixed), dict(self.assign)), "new": (list(groups), {})}
        self.fixed, self.assign = list(groups), {}
        self.undo.append(entry)
        self.redo.clear()
        self.dirty = True
        self.refresh_audit()
        self.status.set(label)

    def suggest_palettes(self):
        if self.res is None:
            return
        g = suggest_groups(self.work, self.valid, self.edit_prm["backdrop"])
        self._set_palettes(g, "Suggested %d palette group(s) for the current pixels (assignments cleared)" % len(g))

    def use_detected(self):
        if self.orig_res is None:
            return
        if self.orig_res["groups_needed"] > 4:
            return messagebox.showinfo("NES Auditor", "The original image needs %d groups (> 4), so there is no valid detected set. "
                                       "Use 'Suggest 4 palettes'." % self.orig_res["groups_needed"])
        self._set_palettes([tuple(g) for g in self.orig_res["_group_codes"]], "Restored the detected palette groups")

    # ------------------------------------------------------------------ saving edits
    def _edited_rgba(self):
        h, w = self.rgba_orig.shape[:2]
        ox, oy = self.edit_prm["origin"]
        out = self.rgba_orig.copy()
        opaque = out[:, :, 3] > 0
        region = self.work[oy:oy + h, ox:ox + w]
        out[:, :, :3][opaque] = region[opaque]
        return out

    def save_edited(self):
        if self.rgba_orig is None:
            return messagebox.showinfo("NES Auditor", "Run an audit first.")
        stem = os.path.splitext(os.path.basename(self.path.get() or "image"))[0]
        p = filedialog.asksaveasfilename(title="Save edited image", defaultextension=".png",
                                         initialfile=stem + "_edited.png", filetypes=[("PNG", "*.png")])
        if not p:
            return
        Image.fromarray(self._edited_rgba(), "RGBA").save(p)
        self.dirty = False
        self.status.set("Saved %s%s" % (p, "" if self.res["palette_pass"] else "  (still has squares outside the 4 palettes)"))
        self.show_result()

    def export_attributes(self):
        if self.res is None:
            return messagebox.showinfo("NES Auditor", "Run an audit first.")
        stem = os.path.splitext(os.path.basename(self.path.get() or "image"))[0]
        p = filedialog.asksaveasfilename(title="Export attribute table (writes .attr.bin and .attr.json)",
                                         defaultextension=".bin", initialfile=stem + ".attr.bin",
                                         filetypes=[("Attribute table", "*.bin")])
        if not p:
            return
        base = p[:-4] if p.lower().endswith(".bin") else p
        if base.lower().endswith(".attr"):
            base = base[:-5]
        grid = {(b["bx"], b["by"]): (b["group"] if b["group"] is not None else 0) for b in self.res["blocks"]}
        data = attribute_table(grid)
        with open(base + ".attr.bin", "wb") as fh:
            fh.write(data)
        rows = [[grid.get((bx, by), 0) for bx in range(self.res["canvas"][0] // BLOCK)] for by in range(self.res["canvas"][1] // BLOCK)]
        bad = [[b["x"], b["y"]] for b in self.res["blocks"] if b["conflict"] or b.get("unfit")]
        with open(base + ".attr.json", "w", encoding="utf-8") as fh:
            json.dump({"backdrop": self.res["backdrop"],
                       "palettes": [{"palette_number": g["index"], "colors": g["colors"]} for g in self.res["groups"]],
                       "palette_number_per_16x16_square": rows,
                       "attribute_table_hex": data.hex(),
                       "squares_not_valid": bad,
                       "note": "palette_number 0-3 = group 1-4. Attribute byte layout: bits0-1 top-left, 2-3 top-right, "
                               "4-5 bottom-left, 6-7 bottom-right 16x16 square of each 32x32 area."}, fh, indent=2)
        self.status.set("Attribute table written: %s.attr.bin / .attr.json" % base)

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
