"""Shared tkinter widgets for the NES tools GUIs."""
import queue
import threading
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

BG = "#1e1f22"
PANEL = "#2b2d30"
FG = "#e6e6e6"
MUTED = "#9aa0a6"
GOOD = "#2e9d57"
BAD = "#c0392b"
ACCENT = "#4c8dff"


def apply_theme(root):
    """Dark ttk theme that looks the same on Windows, macOS and Linux."""
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=BG)
    st.configure(".", background=BG, foreground=FG, fieldbackground=PANEL, bordercolor="#3c3f41",
                 lightcolor=PANEL, darkcolor=PANEL, troughcolor=PANEL, font=("Segoe UI", 10))
    st.configure("TFrame", background=BG)
    st.configure("Panel.TFrame", background=PANEL)
    st.configure("TLabel", background=BG, foreground=FG)
    st.configure("Muted.TLabel", foreground=MUTED)
    st.configure("Head.TLabel", font=("Segoe UI", 11, "bold"))
    st.configure("TLabelframe", background=BG, foreground=FG, bordercolor="#3c3f41")
    st.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=("Segoe UI", 10, "bold"))
    st.configure("TButton", background="#3a3d41", foreground=FG, padding=(10, 5), borderwidth=1)
    st.map("TButton", background=[("active", "#4a4e53"), ("disabled", "#2a2c2f")],
           foreground=[("disabled", "#666")])
    st.configure("Accent.TButton", background=ACCENT, foreground="white", font=("Segoe UI", 10, "bold"))
    st.map("Accent.TButton", background=[("active", "#6aa0ff"), ("disabled", "#2c3f66")])
    for w in ("TCheckbutton", "TRadiobutton"):
        st.configure(w, background=BG, foreground=FG)
        st.map(w, foreground=[("disabled", "#666")], background=[("active", BG)])
    st.configure("TEntry", fieldbackground=PANEL, foreground=FG, insertcolor=FG)
    st.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=FG, arrowcolor=FG)
    st.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("disabled", "#666")])
    st.configure("TSpinbox", fieldbackground=PANEL, foreground=FG, arrowcolor=FG)
    st.configure("TNotebook", background=BG, bordercolor="#3c3f41")
    st.configure("TNotebook.Tab", background="#2a2c2f", foreground=FG, padding=(12, 5))
    st.map("TNotebook.Tab", background=[("selected", "#3a3d41")])
    st.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=22, bordercolor="#3c3f41")
    st.configure("Treeview.Heading", background="#3a3d41", foreground=FG)
    st.map("Treeview", background=[("selected", "#365a99")])
    st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL)
    st.configure("TPanedwindow", background=BG)


class ImageView(ttk.Frame):
    """Scrollable, zoomable image canvas. Nearest-neighbour scaling (pixel art friendly).

    on_motion(ix, iy) is called with image-space coordinates (or None when the mouse leaves)."""

    ZOOMS = ["Fit", "1x", "2x", "3x", "4x", "6x", "8x"]

    def __init__(self, master, title="", on_motion=None, on_click=None, show_zoom=True):
        super().__init__(master)
        self.on_motion, self.on_click = on_motion, on_click
        self.image = None
        self._photo = None
        self.zoom_var = tk.StringVar(value="Fit")
        self._scale = 1.0
        self.overlay = []          # list of (x, y, w, h, color) rectangles in image space
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text=title, style="Head.TLabel").pack(side="left", padx=4)
        if show_zoom:
            cb = ttk.Combobox(top, textvariable=self.zoom_var, values=self.ZOOMS, width=5, state="readonly")
            cb.pack(side="right", padx=4)
            ttk.Label(top, text="Zoom", style="Muted.TLabel").pack(side="right")
            cb.bind("<<ComboboxSelected>>", lambda e: self.redraw())
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg="#101113", highlightthickness=0, cursor="crosshair")
        self.hbar = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        self.vbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)
        self.vbar.pack(side="right", fill="y")
        self.hbar.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", lambda e: self.on_motion and self.on_motion(None))
        self.canvas.bind("<Button-1>", self._click)

    def set_image(self, img, keep_view=False):
        self.image = img
        self.redraw()

    def scale(self):
        return self._scale

    def _compute_scale(self):
        z = self.zoom_var.get()
        if self.image is None:
            return 1.0
        if z == "Fit":
            cw, ch = max(self.canvas.winfo_width(), 50), max(self.canvas.winfo_height(), 50)
            s = min(cw / self.image.width, ch / self.image.height)
            return max(0.25, s if s < 1 else max(1, int(s)))
        return float(z.rstrip("x"))

    def redraw(self):
        self.canvas.delete("all")
        if self.image is None:
            return
        self._scale = self._compute_scale()
        w, h = int(self.image.width * self._scale), int(self.image.height * self._scale)
        shown = self.image.resize((max(1, w), max(1, h)), Image.NEAREST) if (w, h) != self.image.size else self.image
        self._photo = ImageTk.PhotoImage(shown)
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, w, h))
        for (x, y, rw, rh, col) in self.overlay:
            s = self._scale
            self.canvas.create_rectangle(x * s, y * s, (x + rw) * s, (y + rh) * s, outline=col, width=3)

    def to_image_xy(self, ev):
        s = self._scale or 1
        return int(self.canvas.canvasx(ev.x) / s), int(self.canvas.canvasy(ev.y) / s)

    def _motion(self, ev):
        if self.image is None or not self.on_motion:
            return
        x, y = self.to_image_xy(ev)
        self.on_motion((x, y) if 0 <= x < self.image.width and 0 <= y < self.image.height else None)

    def _click(self, ev):
        if self.image is None or not self.on_click:
            return
        x, y = self.to_image_xy(ev)
        if 0 <= x < self.image.width and 0 <= y < self.image.height:
            self.on_click((x, y), ev.state)

    def scroll_to(self, x, y):
        """Scroll so image-space (x, y) is near the centre."""
        if self.image is None:
            return
        s = self._scale
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        W, H = self.image.width * s, self.image.height * s
        if W > cw:
            self.canvas.xview_moveto(max(0, min(1, (x * s - cw / 2) / W)))
        if H > ch:
            self.canvas.yview_moveto(max(0, min(1, (y * s - ch / 2) / H)))


class Worker:
    """Run a function in a thread; results are delivered on the Tk thread via root.after polling."""

    def __init__(self, root):
        self.root, self.q = root, queue.Queue()
        self.busy = False
        self._after = self.root.after(80, self._poll)
        self.root.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, ev):
        if ev.widget is self.root and self._after:
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def start(self, fn, on_done, on_progress=None):
        if self.busy:
            return False
        self.busy = True

        def target():
            try:
                self.q.put(("done", on_done, fn(lambda *a: self.q.put(("prog", on_progress, a, None)) if on_progress else None), None))
            except Exception as e:  # noqa
                import traceback
                self.q.put(("done", on_done, None, (e, traceback.format_exc())))

        threading.Thread(target=target, daemon=True).start()
        return True

    def _poll(self):
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            while True:
                kind, cb, payload, err = self.q.get_nowait()
                if kind == "prog":
                    cb(*payload)
                else:
                    self.busy = False
                    cb(payload, err)
        except queue.Empty:
            pass
        try:
            self._after = self.root.after(80, self._poll)
        except tk.TclError:
            pass


def int_var(root, value):
    return tk.IntVar(root, value=value)


def safe_int(var, default=0):
    try:
        return int(var.get())
    except (tk.TclError, ValueError):
        return default
