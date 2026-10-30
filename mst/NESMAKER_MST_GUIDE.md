# NES Maker `.MST` — headless editing guide (for AI agents)

**Goal:** let an AI build and modify NES Maker projects — levels (screens), art, palettes, variables —
by editing the `.MST` project file directly, *without opening the editor*, while the project still opens,
edits and compiles in the NES Maker editor.

**Scope:** NES Maker **4.5.9**, `.MST` **FileVersion 374** (the only version verified; the library refuses others).

| Trust label | Meaning |
|---|---|
| **VERIFIED** | Proven by an automated test against real projects, including edits made in the real editor |
| **INFERRED** | Consistent with all evidence but not independently proven |
| **UNKNOWN** | Parsed and preserved byte-for-byte, meaning not understood — do not edit |
| **NOT TESTED** | Needs the Windows editor, which was not available when this was written |

> **Read this first.** Every claim below was tested at *file level* on 8 real project files. **Nothing was opened
> in the NES Maker editor** (it is Windows-only; this work was done in a Linux cloud sandbox). The first thing to do
> with any file this toolkit writes is the human checklist in [§9](#9-human-verification-checklist). Until a person has
> done that for a given kind of edit, treat that edit type as *file-correct, editor-unconfirmed*.

---

## 1. Quick start

```bash
pip install pillow                       # only dependency (screen previews / art)
cd mst
python -m nesmaker_mst verify  Projects/Game.MST          # parse + byte-exact round trip
python -m nesmaker_mst info    Projects/Game.MST          # palettes, screens (+map position), assets, variables
python -m nesmaker_mst screen  Projects/Game.MST 2 --png s2.png   # tile grid, fields, embedded preview picture
python -m nesmaker_mst diff    A.MST B.MST                # field-level diff (same layout)
python -m nesmaker_mst set-tile Game.MST Game_edit.MST 2 7 8 4 --subpalette 1
python -m nesmaker_mst tree    Game.MST --depth 1         # raw object tree
```

```python
from nesmaker_mst import MSTProject
p = MSTProject.open("Projects/Game.MST")
assert p.verify_roundtrip()

s = p.screens[2]                       # Screen: 16 x 15 grid of 16x16 metatiles
s.set_tile(col=7, row=8, tile=4, subpalette=1)
p.palettes[3].set_color(sub=1, slot=2, nes_index=0x21)
p.ram_sections()["zeropage"].add("myCounter", value=1, notes="added by AI")
p.save("Projects/Game_edit.MST")       # NEW file; refuses to overwrite; re-parses what it wrote
```

Rules of the road (details in §8): **work on a copy · never overwrite the original · save to a new name ·
run `verify` before and after · re-fetch views after structural edits · ask a human to open the result.**

---

## 2. How the format was worked out (so you can trust or re-check it)

1. `.MST` is **not a custom format**: it is the output of a .NET `BinaryWriter`. Every class in
   `NESMaker.exe` implements `Persist(BinaryWriter)` / `Recall(BinaryReader)`.
2. The `Recall` routines were **statically decompiled** (IL → pseudo-code, no code executed) for all 56
   serialized classes. Those descriptions are in `nesmaker_mst/schema/*.Recall.txt`
   (order of reads, `FileVersion` gates, loops). They contain **format knowledge only** — no program binaries are shipped.
3. `nesmaker_mst/schema_reader.py` *executes those descriptions against real bytes* and records every primitive read
   as a **leaf** `(offset, kind, value, field name, owner)`. This is a lossless model: writing the leaves back in order
   reproduces the file byte-for-byte (`MSTProject.to_bytes()`).
4. Real-editor ground truth: `BEFORE`/`AFTER`/`C` projects differing by known edits made in the editor
   (see §7) pin down what an edit really changes on disk.

Primitive encodings (all little-endian, .NET `BinaryWriter`):

| kind | bytes |
|---|---|
| `int32` / `uint32` | 4 |
| `byte` / `bool` | 1 (`bool`: 0/1) |
| `string` | 7-bit-encoded length prefix, then UTF-8 bytes |
| GUID | `int32 16` then 16 bytes (`Guid.ToByteArray()` order = `uuid.UUID(bytes_le=…)`) |
| embedded bitmap | `int32 length` then a complete BMP file (length 0 = none) |

---

## 3. File layout (VERIFIED — all 8 sample files parse to the last modelled byte)

Top level (`MainGameModel`), in on-disk order. `n*` are counts read from the header.

| # | Section | Layout |
|--:|---|---|
| 1 | magic | `uint32 0xDEADBEEF` |
| 2 | version | `int32 374` (loader rejects `< 258`; later fields are gated on it) |
| 3 | counts | `int32 ×6`: nPalettes, nScreens, nOverworld, nUnderworld, nAssets, nPathInfos |
| 4 | **Palettes** | nPalettes × `[string name][PaletteInfo = 16×int32]` (128 in practice; names only for the first 64) |
| 5 | **Screens** | nScreens × `[GUID key][ScreenInfo]` |
| 6 | **Overworld map** | nOverworld × `[int32 x][int32 y][GUID]` — which screen sits at each map cell |
| 7 | **Underworld map** | nUnderworld × same |
| 8 | **Graphic assets** | nAssets × `[GUID key][GraphicAsset]` (tile sheets, embedded BMP) |
| 9 | Path infos | nPathInfos × `[GUID][PathinfoGroup]` |
| 10 | Initial settings | `InitialSettings` (start screen, start location, items…) |
| 11 | Monsters / groups / monster palettes | `int32 n ×[GUID][MonsterInfo]`, `int32 n ×[GUID][MonsterGroup]`, `int32 n ×MonsterSubPalette` |
| 12 | Asset groups | `int32 n ×[int32 key][int32 m][m GUIDs]`, then `int32 n ×[GUID][AssetGroup]` |
| 13 | Tables | `MapMeta` (screen-group names, map comments…), `TextInfo`, `ShopinfoGroup`, `TextGroupInfo`, `SpecialTileInfoGroup`, `AnimationTileGroupInfo` |
| 14 | Special screens / objects | `int32 n ×PaletteInfo`, `int32 n ×GraphicAsset`, `int32 n ×MonsterInfo` (GameObjects), `GameItemOffset` |
| 15 | Scripts & inputs | `int32 n × string` (script list), `int32 n ×ControlInput`, "label changes" block (enum-name tables **and the 78 `TileResouce` records**) |
| 16 | Emulator + music + HUD | 3 strings, `int32 n × byte`, `HudInfo`, 4 script-path strings |
| 17 | **Variables & defines** | `GlobalUserVars` (`int32 n × string`), `AllScriptDefines` (`int32 n ×ScriptDefine`) + `AllSoundAsm` string, `GlobalUserVarInitialValues` (`int32 n × int32`), 2 tileset strings, `SFXLinks`, **`UserDefinedVars`** (`int32 n ×UserDefinedVar`), sprite-zero settings, plugin blobs, **`ObjectVariables`**, **`UserRAMDefine` ×2 (zero page, overflow)**, **`UserDefinedConstants`** |
| 18 | Export metadata | 14 strings (title, studio, year, ROM file name …) |
| 19 | Music, actors, map detail | `Music`, `int32 n ×[GUID][ObjectManagerActor]`, `MapDetail` (high-res flags) |
| — | **tail** | ~450–670 opaque bytes written by the UI after the model (tree-view state: "Assets", "Path Info", "Graphics Bank 0"…). **UNKNOWN — preserved verbatim.** |

Complete per-class field lists (order, type, repeat counts): **[`FORMAT_FIELDS.md`](FORMAT_FIELDS.md)** (auto-generated from real projects).

---

## 4. The data model, by what you will want to edit

### 4.1 Screens = levels  (VERIFIED)

A screen (`ScreenInfo`, ~140 fields) is one 16×15 room of **16×16-pixel metatiles** (256×240 px).

| Field | Meaning | Status |
|---|---|---|
| `TileData[240]` (int32) | metatile id per cell, **row-major**, index = `row*16 + col` | VERIFIED (matches the editor's exported `Nametables/*.nam`; changes exactly where the editor edit was made) |
| `SubPaletteData[240]` (int32 0–3) | which of the screen palette's 4 sub-palettes each cell uses | VERIFIED (`AttributeTables/*.att` export equals the NES attribute bytes computed from it) |
| `AttributeData[240]` (uint32, 0/1 in samples) | per-cell flag | **UNKNOWN** (not the NES attribute table; untouched by tile/sub-palette edits) |
| `BankID`, `PaletteID` | graphics bank (1-3) and palette-list index used by the screen (`Palettes[PaletteID]`) | VERIFIED (appear in the export headers) |
| `TileSetMainID`, `TileSetScreenID`, `TileSetPathID` | which "Main"/"Screen"/"Path" sheet group of that bank to use | INFERRED |
| `ScreenGuid` | the screen's id; **identical to its dictionary key** | VERIFIED |
| embedded preview (`bool` + `int32 len` + BMP) | 256×240 **32-bpp** picture of the screen | VERIFIED that it re-renders on tile edits; see §4.1.1 |
| `ShowHUD`, `ScreenSpeed`, `SongIndex`, `IsBossRoom`, `IsDarkRoom`, `WarpOutScreenX/Y`, `WarpInScreenLocX/Y`, `ScreenType`, `UserScreenByte0-7`, `UserScreenFlag0-7`, `Monster{1-4}{Day,Night}{Normal,Triggered}{X,Y}`, `Monster{1-4}ID…`, `…MonsterGroup` (GUIDs), `DayMonsterBank`, … | per-screen settings; plain scalars | INFERRED from names (read/written exactly as listed in `FORMAT_FIELDS.md`) |

**Metatile id semantics (INFERRED, 1 exact pixel match + exports):** the id is the *CHR tile number of the cell's top-left
8×8 tile* in the bank's tile sheet (sheet = 16 tiles per row, 8 px tiles; the editor shows 16×16 metatiles = 2×2 tiles, so ids
are usually even). In the real edit that set cell id `4`, the preview cell is pixel-identical to the 16×16 block at sheet
position x=32,y=0 (tile 4) of `Main` sheet 0, recoloured by the sub-palette.

**Map position:** a screen is placed on the overworld/underworld grid by the map tables (§3 rows 6-7), keyed by
`(x, y)` → screen GUID. The editor's exports name screens `Screen_Over_<Y><X>` in hex (`(0,14)` → `E0`) — VERIFIED
(37 of 38 exported nametables equal the corresponding `TileData`; the 38th differs in one cell because that export predates a later edit).

#### 4.1.1 The preview bitmap
`ScreenInfo` stores a rendered picture. Tile edits in the editor rewrite the changed 16×16 cell in it.
`Screen.set_tile()` reproduces this by **copying that exact cell from any screen in the project that already uses the
same (bank, tilesets, palette, tile id, sub-palette) combination** (`MSTProject.cell_library()`); if the combination
never occurs, it returns `'preview-stale'` and leaves the old picture (the grid data is still correct).
Whether the editor regenerates stale previews on load is **NOT TESTED**. Reproduced byte-for-byte: both real editor edits (§7).

### 4.2 Palettes  (VERIFIED)

`Palettes[i]` = name + **16 × int32** = 4 sub-palettes × 4 slots. Values are **NES master-palette indices 0–63**
(`0x0F` = black). Slot 0 of every sub-palette is the shared backdrop; the sprite/background rules of the NES apply
(≤ 3 free colors per 16×16 block; all four backdrops should match). A screen uses `Palettes[screen.PaletteID]`.
The API: `p.palettes[i].set_color(sub, slot, nes_index)`, `.set_colors([16 ints])`, `.name = "…"`.

### 4.3 Art (graphic assets)  (VERIFIED for read + swap; NOT TESTED in the editor)

* 78 `GraphicAsset` records per project, each with an **embedded BMP**, paired **by order** with 78 `TileResouce`
  records (`BankID`, `GroupID`, `TileType` = `Main`/`Screen`/`Path`/`specialTiles`/`objectTiles`/`HudTiles`/`Monster`,
  `Name` = relative path such as `Moooooo\BckCHR_00.bmp`, `Display` = e.g. `B1 Main-0`).
* The embedded BMP is **pixel-identical to the external file** `GraphicAssets/<Name>` (checked for all 78).
  **Therefore change art in both places**: `Asset.replace_image(img)` updates the `.MST` copy and keeps the length prefix right;
  you must also write the same image to `GraphicAssets/<Asset.file>` (the editor keeps these in sync; whether it prefers the file or
  the embedded copy on load is **NOT TESTED**, so keep them equal).
* `TileSize` is in **16 px units** (`8×3` ⇒ a 128×48 px sheet). `replace_image` requires an identical pixel size.
* Tile sheets are *index art*: pixels use a few fixed colors that the screen's sub-palette recolors. Use the colors already in
  the sheet; NES limits (4 colors/tile) are your job — the toolkit does not recolor.
* `TileIDs / SubPaletteIDs / Attributes / FlipH / FlipV` (per metatile, per asset) exist and are all zero in the samples. **UNKNOWN meaning.**

### 4.4 Variables, constants, scripts  (VERIFIED read/write; NOT TESTED in editor/compile)

| API | Model field | Record |
|---|---|---|
| `p.user_vars()` | `UserDefinedVars` | `Var(name, value=InitialValue, enabled, notes)` |
| `p.ram_sections()['zeropage']` | `UserRAMDefine_ZeroPage` | `Var(name, value = size in bytes, enabled, notes)` |
| `…['overflow']` | `UserRAMDefine_Overflow` | same |
| `…['constants']` | `UserDefinedConstants` | `Var(name, value = constant)` |
| `…['object']` | `ObjectVariables` | per-object RAM variables |
| `p.global_vars()` | `GlobalUserVars` + `GlobalUserVarInitialValues` | parallel lists (name, initial) |
| `p.script_defines()` | `AllScriptDefines` | `ScriptDefine(Name, Define, Script, Group)` — 170+ entries mapping `SCR_*` defines to `Routines\…\*.asm` files |

`VarSection.add(name, value, notes)` / `p.add_user_var(name, value, notes)` append a record, increment the section's count and re-parse (work on empty lists too).
`ObjectVariables.VarCount` (a separate field that differs from the item count in the samples: 13 vs 19) is left untouched — meaning UNKNOWN.
`Var.value/name/enabled/notes` are plain setters (no layout change).
The assembly *routines* themselves live outside the `.MST` (`Routines/…asm`); the project only stores paths and defines.

### 4.5 Other tables (readable generically, edit scalars only)

`p.initial_settings()` (start screen/location), `p.monsters()` (objects/monsters: size, speeds, health, hitbox, palettes, flags),
`MapMeta`, `TextInfo`, HUD, music. Use `NodeView`: `view["Health"] = 5` or walk `p.root` (`kids()`, `field()`, `array()`).
Setting a scalar is safe (fixed size). Changing the *number* of items in these lists is supported only for the cases below.

---

## 5. Operations catalogue

| Operation | API | Layout change | Status |
|---|---|---|---|
| Round-trip / diff | `verify_roundtrip()`, CLI `diff` | none | VERIFIED (8/8 files byte-exact) |
| Paint a cell | `Screen.set_tile(col,row,tile,subpalette)` | none | VERIFIED — reproduces the editor's own edits **byte-for-byte** |
| Fill / generate a screen | loop of `set_tile` (build the library once: `lib=p.cell_library()`; pass `library=lib`) | none | VERIFIED (same primitive) |
| Edit any scalar field | `Screen[...]=`, `NodeView[...]=`, `set_leaf` | none | VERIFIED |
| Palette color / rename | `Palette.set_color/name` | none | VERIFIED (file) |
| Swap art | `Asset.replace_image` (+ write the external BMP) | blob length only | VERIFIED (file) |
| Rename/retarget a variable, change value | `Var.name/value` | string length | VERIFIED (file) |
| Add a variable | `VarSection.add`, `add_user_var` | +1 record, count fixed | VERIFIED (file); editor NOT TESTED |
| New screen | `clone_screen(src)` → set tiles → `place_screen(world,x,y,guid)` | +1 record (+ map row) | VERIFIED (file: parses, counts, GUID in both places; add→delete is a byte-exact no-op); editor NOT TESTED |
| Delete screen | `delete_screen(guid)` (also removes its map cells) | −records | file-verified; **other references (start screen, warps, MapMeta comments/types keyed by map cell, path groups) are NOT cleaned** |
| Move a screen on the map | `unplace_screen` + `place_screen` | map row | file-verified |

Not implemented: creating a project from nothing, adding assets/palettes/monsters/objects, editing the opaque tail, regenerating the
export (`GameEngineData/…`) — **let the editor export/compile**; its output matches the `.MST` (VERIFIED: nametable and attribute exports equal
`TileData`/`SubPaletteData`).

---

## 6. Recipes

**Make a new room from an existing one**
```python
p = MSTProject.open("Projects/Game.MST")
new = p.clone_screen(2)                      # returns the new GUID; copy of screen #2 (index in p.screens)
p.place_screen("overworld", 3, 4, new)       # raises if the map cell is taken
s = p.screen_by_guid(new)                    # re-fetch: structural edits re-parse the file
lib = p.cell_library()
for r in range(15):
    for c in range(16):
        s.set_tile(c, r, 168, 0, library=lib)   # 168 = a ground tile in the sample project; look up ids with `screen` CLI
p.save("Projects/Game_new_room.MST")
```
Pick tile ids from what existing screens use (`python -m nesmaker_mst screen file.MST N`) — an id only makes sense for the
bank/tilesets that screen references. Copy the `BankID`, `PaletteID`, `TileSet*ID` of a screen you like with `s["BankID"]=…`.

**Recolor a world:** edit `p.palettes[k].set_color(...)` for the palette index the screens reference (`screen["PaletteID"]`). Keep slot 0 equal across sub-palettes.

**Replace tileset art:** build a new BMP of the *same pixel size* using the sheet's existing index colors, then
`asset.replace_image(img)` **and** save the same image to `GraphicAssets/<asset.file>`.

**Add a gameplay variable:** `p.ram_sections()['zeropage'].add("myFlag", 1, "doc")` (RAM reservation, size in bytes) or
`p.add_user_var("myScore", 0, "doc")` (project user variable with an initial value). Both re-parse the file, so re-fetch views afterwards.

---

## 7. Evidence (what was actually tested)

Samples: 13BytesOfOctober (0 screens), From_Beyond (0 screens), Moooooo (38 screens, 78 assets) and 5 copies/variants of it.

| Test | Result |
|---|---|
| Parse all 8 projects; every modelled byte consumed | **8/8** (`FileVersion 374`) |
| Re-serialize from the leaf list | **byte-identical, 8/8** |
| `BEFORE → AFTER` (one tile painted in the editor) vs. headless `set_tile(7,8,4)` on screen 2 | **byte-identical file** |
| `BEFORE → C` (two cells, one with a sub-palette change) vs. headless edits | **byte-identical file** |
| Editor diff granularity | AFTER = exactly `TileData[135]` 2→4 + 432 bytes of preview; C = that + `TileData[118]` 0→2 + `SubPaletteData[118]` 3→1 (so tile id and sub-palette are independent arrays) |
| Screens vs editor-exported `ScreenData/Nametables/*.nam` | **37/38 identical** (the other: 1 cell, export is older than the edit) |
| `SubPaletteData` → NES attribute bytes vs exported `*.att` | **identical** (64/64 bytes) |
| 78 embedded asset BMPs vs `GraphicAssets/Moooooo/*.bmp` | **78/78 pixel-identical**, paired to `TileResouce` by order |
| Add variable / add + place + delete screen / palette edit / art swap, then save + reopen | parses, counts correct; **add→delete screen is a byte-exact no-op** |
| Opening or compiling any written file in NES Maker | **NOT TESTED** |

Run the suite yourself: `MST_SAMPLES=/path/to/Projects python -m unittest discover -s tests -v`.

---

## 8. Safety rules (follow all of them)

1. **Never edit the only copy.** `save()` refuses to overwrite; keep it that way. Keep a pristine backup of the project *and* its `GraphicAssets/` folder.
2. **`verify` first.** If `verify_roundtrip()` is false or the loader raises, stop: the file is newer/different. Do not "fix" the schema blind.
3. **Prefer scalar edits.** They cannot corrupt layout. Structural edits (`add`, `clone_screen`, `delete_screen`, map place/remove) splice records and re-parse; they
   reject the result if parsing fails, but cannot know what the *editor* expects (see §10).
4. **Re-fetch views after any structural edit** (`p.screens`, `p.palettes`, … are re-built; old `Screen`/`Var` objects point at stale leaves).
5. **Keep related data consistent**: asset BMP ⇄ external file; screen GUID ⇄ its key (done by `clone_screen`); map cell ⇄ existing screen; counts (done for you).
6. **Respect NES limits yourself**: ≤ 3 colors + shared backdrop per sub-palette, 4 sub-palettes, tile-sheet capacity, ids 0–255, a screen's tile ids must exist in its bank/tileset.
   The `.MST` can store illegal values; the editor/assembler will then misbehave.
7. **Unknown fields**: do not modify anything labelled UNKNOWN. Unknown regions are carried verbatim.
8. **Don't trust names blindly**: field names come from the program's own identifiers, but a name is not a promise about engine behavior. Verify by diffing an editor-made change.

---

## 9. Human verification checklist

For each *new kind* of edit, one person with the Windows editor should do this once (≈5 minutes) and report back:

1. Copy the whole project folder. In the copy, place the AI-written `.MST` in `Projects/`.
2. Open it in NES Maker 4.5.9. **Pass:** opens without an error dialog.
3. Look at what was edited (screen map, the changed screen, palette editor, variable lists, tile sheet). **Pass:** matches the intent.
4. Press *Save*, close, reopen. **Pass:** still fine. (Then `python -m nesmaker_mst diff` the editor-saved file against the AI file: should be tiny.)
5. Export & Test. **Pass:** ROM builds and the change is visible in the emulator.
6. Record failures with the exact edit; fix the schema/doc, add a test.

The most valuable single test: make a *known* edit in the editor (e.g. add one variable, or one new screen), save as a new name, and `diff` it against the
original — this teaches the toolkit exactly what the editor does for that operation (this is how tile painting was proven).

---

## 10. Known gaps / open questions

* **Editor acceptance** of structural edits (new screens, variables) is unconfirmed. Possible hidden coupling: screen **MapMeta** entries
  (screen type / comment per map cell), **path groups**, per-map "screen group" naming, `InitialSettings.StartingScreen`.
* **Preview regeneration** when a tile/sub-palette combination has no existing cell to copy (returns `preview-stale`).
* `ScreenInfo.AttributeData` semantics; per-asset `TileIDs/Attributes` semantics; `TileSet*ID` selection rule; metatile id ↔ sheet position beyond the one checked case.
* The UI **tail** (≈ 0.5 KB of tree-view state) is not decoded.
* Only `FileVersion 374`. Older projects (258–373) use the same schema with gates implemented in the `.Recall.txt` files, but are **not tested**.
* Plugin blobs and the `NesMakerModFile` import format are not exercised.
* The loader skips the editor's own "poison asset" cleanup (names it drops on load); this toolkit keeps every record.

---

## 11. Layout of this folder

```
mst/
  NESMAKER_MST_GUIDE.md      ← this file
  FORMAT_FIELDS.md           ← per-class ordered field tables (generated)
  nesmaker_mst/
    project.py               ← MSTProject + views (Screen, Palette, Asset, Var…), edit/splice/save
    schema_reader.py         ← schema-driven parser (records every primitive read)
    __main__.py              ← CLI
    schema/                  ← *.Recall.txt (field order + version gates) + field_types.json
  scripts/gen_field_reference.py
  tests/test_mst.py          ← run with MST_SAMPLES=<folder of .MST>
```

Notes on provenance: the schema files were derived by static analysis of the editor's own serialization routines for the purpose of
interoperating with project files. The repository does **not** contain NES Maker, its engine files, or user projects; point `MST_SAMPLES` at your own.
