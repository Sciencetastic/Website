"""High-level entry points used by the GUIs and the CLI."""
import os
from dataclasses import dataclass, field, replace
from typing import Optional, Tuple

import numpy as np
from PIL import Image

from . import gb as gbmod
from .audit import audit_canvas, audit_image, compose_canvas, load_rgba
from .convert import conform_rgba, reduce_tiles
from .palette import from_hex, to_hex


@dataclass
class Options:
    mode: str = "conform"                 # 'conform' (colour image) | 'gb' (4-shade image)
    backdrop: str = "black"               # 'black' | 'auto' | '#RRGGBB'
    origin: Tuple[int, int] = (0, 0)      # placement on the 256x240 screen
    screen: bool = True                   # analyse on the 256x240 screen canvas
    tile_budget: int = 0                  # 0 = off; else merge tiles down to this many patterns
    max_colors: int = 24
    snap: bool = True                     # snap colours to the NES master palette first
    # --- Game Boy options
    use_reference: bool = False
    reference: Optional[object] = None    # path or PIL image
    ref_method: str = "auto"              # 'auto' | 'aligned' | 'palette'
    theme: str = "auto"                   # 'auto' (from file name) or a theme name
    crop: Optional[Tuple[int, int, int, int]] = None   # (x, y, w, h) crop before colouring
    name: str = ""                        # file name, used for the 'auto' theme


@dataclass
class Result:
    source: Image.Image
    image: Image.Image
    audit: dict
    canvas: np.ndarray
    details: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


def _backdrop_rgb(opt):
    if opt.backdrop in ("black", None, ""):
        return (0, 0, 0)
    if opt.backdrop == "auto":
        return None
    return from_hex(opt.backdrop)


def run(src, opt: Options) -> Result:
    """Convert one image. src: path or PIL image."""
    im = src if isinstance(src, Image.Image) else Image.open(src)
    if not opt.name and isinstance(src, str):
        opt = replace(opt, name=os.path.splitext(os.path.basename(src))[0])
    rgba = np.array(im.convert("RGBA"), np.uint8)
    notes, details = [], {}
    if opt.crop:
        x, y, w, h = opt.crop
        rgba = rgba[y:y + h, x:x + w].copy()
        notes.append("cropped to %dx%d at (%d,%d)" % (w, h, x, y))
    ox, oy = opt.origin
    h, w = rgba.shape[:2]
    if opt.screen and (ox + w > 256 or oy + h > 240):
        notes.append("image is larger than a 256x240 screen at this origin; analysed on its own block grid")

    if opt.mode == "conform":
        out, info = conform_rgba(rgba, origin=opt.origin, backdrop=_backdrop_rgb(opt) or "auto",
                                 snap=opt.snap, max_colors=opt.max_colors, screen=opt.screen)
        backdrop = info["backdrop"]
        details.update(method="conform", **{k: info[k] for k in ("groups", "changed_pixels", "total_opaque", "kept_colors")})
        if _backdrop_rgb(opt) is None:
            notes.append("auto backdrop chosen: %s" % to_hex(backdrop))
    else:
        backdrop = _backdrop_rgb(opt) or (0, 0, 0)
        if opt.backdrop == "auto":
            notes.append("auto backdrop is not used for Game Boy art (darkest shade -> black)")
        lv, ginfo = gbmod.gb_levels(rgba)
        if ginfo["quantized"]:
            notes.append("image had %d shades; quantised to 4 by brightness" % ginfo["distinct"])
        elif ginfo["distinct"] < 4:
            notes.append("image has only %d shades" % ginfo["distinct"])
        method = None
        if opt.use_reference and opt.reference is not None:
            ref_im = opt.reference if isinstance(opt.reference, Image.Image) else Image.open(opt.reference)
            ref = np.array(ref_im.convert("RGBA"), np.uint8)
            ref_rgb, ref_alpha = ref[:, :, :3], ref[:, :, 3]
            want = opt.ref_method
            score, off = gbmod.align_reference(lv, ref_rgb)
            details["alignment_score"] = round(float(score), 3)
            if want in ("auto", "aligned") and (score >= 0.75 or (want == "aligned" and score > 0.3)):
                canvas_rgb, valid, info = gbmod.colorize_aligned(lv, ref_rgb, off, opt.origin, backdrop,
                                                                  snap=opt.snap, screen=opt.screen)
                notes.append("reference aligned (match %.2f at offset %s)" % (score, off))
                method = "aligned"
            else:
                if want == "aligned":
                    notes.append("reference did not align well (match %.2f); used palette-only" % score)
                elif want == "auto":
                    notes.append("no pixel alignment found (best match %.2f); used reference palette only" % score)
                canvas_rgb, valid, info = gbmod.colorize_ref_palette(lv, ref_rgb, ref_alpha, opt.origin, backdrop,
                                                                     snap=opt.snap, screen=opt.screen)
                method = "palette"
        else:
            th = opt.theme if opt.theme != "auto" else gbmod.theme_for(opt.name)
            canvas_rgb, valid, info = gbmod.colorize_theme(lv, th, opt.origin, backdrop, screen=opt.screen)
            notes.append("theme: %s" % th)
        details.update(method="gb-" + info["method"], palettes=info["palettes"])
        out = rgba.copy()
        out[:, :, :3] = canvas_rgb[oy:oy + h, ox:ox + w]
        out[:, :, 3] = np.where(lv >= 0, 255, 0)
        details["changed_pixels"] = None

    result_img = Image.fromarray(out, "RGBA")
    res, canvas = audit_image(result_img, opt.origin, backdrop, opt.tile_budget or 192, screen=opt.screen)
    if opt.tile_budget and res["palette_pass"]:
        out2, tinfo = reduce_tiles(out, res, opt.origin, opt.tile_budget, screen=opt.screen)
        if tinfo.get("merged"):
            result_img = Image.fromarray(out2, "RGBA")
            res, canvas = audit_image(result_img, opt.origin, backdrop, opt.tile_budget, screen=opt.screen)
            notes.append("tile reduction: %d -> %d patterns (%d pixels changed)" % (
                tinfo["before"], tinfo["after"], tinfo["changed_pixels"]))
        details["tile_reduction"] = tinfo
    details["backdrop"] = to_hex(backdrop)
    return Result(source=im, image=result_img, audit=res, canvas=canvas, details=details, notes=notes)


def run_batch(paths, out_dir, opt: Options, progress=None, suffix="_nes"):
    """Run many files. Returns list of (path, out_path, Result|Exception)."""
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for i, p in enumerate(paths):
        try:
            r = run(p, opt)
            op = os.path.join(out_dir, os.path.splitext(os.path.basename(p))[0] + suffix + ".png")
            r.image.save(op)
            rows.append((p, op, r))
        except Exception as e:  # keep going, report per file
            rows.append((p, None, e))
        if progress:
            progress(i + 1, len(paths), p)
    return rows
