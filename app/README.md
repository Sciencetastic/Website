# NES Art Tools

Two small desktop programs (and a shared Python engine) for keeping artwork inside the NES
background palette rules:

* every 16×16 attribute square uses the shared **backdrop colour + at most 3 other colours**
* the whole screen needs **at most 4 palette groups**
* (diagnostic) unique 8×8 tile patterns vs your CHR budget (default 192 for art)

| Program | Purpose |
|---|---|
| **NES Colorizer** (`nes_colorizer.py`) | Makes an image 100 % compliant. Colour image → conform to NES, **or** Game Boy 4-shade image → colorize, optionally **using a reference image** for the colours. Optional tile-budget reduction. Batch folder mode. |
| **NES Auditor** (`nes_auditor.py`) | Checks any finished image. Highlights over-limit squares, shows which palette group each square uses, counts groups and tiles, saves PNG / JSON / CSV / HTML reports. Batch folder → `summary.csv`. |

## Run it (Windows)

1. Install Python 3.9 or newer from python.org (tick *Add Python to PATH*; tkinter is included).
2. Double-click `run_colorizer.bat` or `run_auditor.bat` (or `NES_Tools_Launcher.bat` for a menu). The first run installs Pillow and numpy; the app opens without a console window.
3. Optional: double-click `build_exe.bat` to create standalone `NES_Colorizer.exe` / `NES_Auditor.exe` in `dist\`.

macOS / Linux: `pip install -r requirements.txt`, then `./run_colorizer.sh` or `./run_auditor.sh`
(Linux may need `sudo apt install python3-tk`).

## NES Colorizer

1. **Input** – an image, or a folder (batch).
2. **What are you converting?**
   * *Colour image* – colours are snapped to the NES master palette, then 4 palette groups are chosen to
     lose as little colour as possible. Already-compliant art is left unchanged.
   * *Game Boy image* – the 4 shades become colours:
     * **No reference** – pick a *theme* (or Auto from the file name). Each 16×16 square picks one of the
       theme's 4 palettes by brightness.
     * **Use a reference image** – colour artwork of the same scene.
       *Aligned* = same drawing, pixel-matched (the reference may be larger, e.g. 122×122 art for a 112×112
       viewport; the crop is found automatically). *Palette only* = the reference need not line up; its
       colours are mapped onto the shades by brightness. *Auto* tries aligned first.
       For a batch, point at a folder of references; they are matched to each image by file name.
     * *Crop first* – e.g. cut a 160×144 game screen down to its 112×112 viewport.
3. **Output rules** – backdrop (black / auto-best / hex), screen origin (squares are measured from the
   256×240 screen grid), optional **tile-budget reduction**, colours kept.
4. **Run** – the result is audited immediately (PASS/FAIL banner, plus a *Compliance map* tab).
   **Save result…**, **Open in Auditor**, or **Batch run** (writes `*_nes.png` and `batch_summary.csv`).

### Notes
* Compliance is guaranteed by construction (≤ backdrop + 3 per square, ≤ 4 groups) and re-verified.
* Photographs convert to flat NES-colour regions (no dithering). Pixel art works best.
* *Tile-budget reduction* merges rare 8×8 patterns into their nearest pattern until the budget is met. It
  changes pixels (the count is shown) but never breaks the palette rules. Tiles that contain transparent
  pixels are left alone.
* Transparent pixels stay transparent and count as the backdrop.

## NES Auditor

Pick an image (or folder). Options: placement on the 256×240 screen, backdrop colour, tile budget, an optional
near-black merge diagnostic.

* **Annotated screen** – every 16×16 square is outlined and numbered with the **palette group** it uses
  (coloured), over-limit squares are **red** with their slot count (backdrop + colours).
  Hover for details, click to select.
* **Summary** – PASS/FAIL, groups needed (max 4), worst square, tile counts, and the palette-group swatches.
* **Blocks** tab – every square with its group and colours; filter to over-limit squares.
* **Batch** tab / *Batch folder → CSV* – one line per image; per-image reports optional.
* **Edit tab – change a square's palette group.** Click a square (Shift+click to add more, or *Select over-limit* /
  *Select unfit*), then press **Assign to group N** (or the keys **1–4**). The square's pixels are remapped into that
  group's colours: the backdrop stays the backdrop and the other colours map one-to-one onto the group's colours by
  least colour error (extra colours fold into the nearest). *Auto-assign best group* picks the best-fitting group for
  each selected square. **Undo / Redo** (Ctrl+Z / Ctrl+Y) and **Reset all edits** are available.
  While editing, the screen is judged against a fixed set of up to 4 palettes: the detected groups if the image needs 4
  or fewer, otherwise **Suggest 4 palettes** picks the best 4 for the current pixels (orange `?` squares fit none of them
  and red squares have too many colours - assign them to a group to fix them).
  **Save edited image…** writes the PNG (original size and transparency kept); **Export attribute table…** writes
  `*.attr.bin` (64-byte NES attribute table: palette number 0-3 = group 1-4 for each 16×16 square) and `*.attr.json`
  (the 4 palettes + the per-square palette numbers).
* **Save report…** writes `_audit.png`, `_audit.json`, `_blocks.csv`, `_audit.html`.

The rules and the "minimum palette groups" search mirror the supplied audit scripts.
*Group count* is the exact minimum number of groups needed by the blocks that are individually valid.

## Command line

```
python -m nes_tools audit image.png --report-dir reports
python -m nes_tools audit folder/ --report-dir reports          # also writes summary.csv
python -m nes_tools convert in.png out.png --tile-budget 192
python -m nes_tools convert gb.png out.png --mode gb --crop 0 0 112 112 --reference color.png
```

## Tests

```
python tests/test_core.py
xvfb-run -a python tests/test_gui.py        # Linux; on Windows/macOS just: python tests/test_gui.py
xvfb-run -a python tests/test_edit.py       # palette-editing tests
```
