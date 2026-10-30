#!/usr/bin/env python3
"""Batch-colorize 4-shade Game Boy screens under NES background rules.

Each image gets a theme (4 palettes, dark -> light).  Per 16x16 block the
palette is picked by the block's mean brightness (quartiles per image, then a
3x3 majority smooth), so a block never needs more than backdrop + 3 colours.
The darkest GB shade always maps to the shared backdrop (black).

usage: gb_batch_colorize.py in_dir out_dir [--sheet sheet.png]
"""
import os, re, sys, glob
from collections import Counter
from PIL import Image, ImageDraw

K = (0, 0, 0)
C = dict(
    dteal=(0, 64, 88), dgreen=(0, 88, 0), green=(0, 168, 0), lgreen=(184, 248, 184),
    teal=(0, 136, 136), sky=(164, 228, 252), blue=(0, 88, 248), lav=(184, 184, 248),
    gray=(120, 120, 120), lgray=(188, 188, 188), white=(252, 252, 252),
    brown=(80, 48, 0), olive=(136, 112, 0), orange=(252, 160, 68), yellow=(248, 216, 120),
    peach=(252, 224, 168), skin=(240, 208, 176), maroon=(136, 20, 0), red=(168, 16, 0),
    pink=(248, 120, 88), purple=(68, 40, 188), violet=(148, 0, 132), plum=(216, 184, 248),
    dblue=(0, 0, 124), rust=(200, 76, 12),
)
def P(*names): return tuple(C[n] for n in names)

# four palettes per theme, darkest band first; L1 and hue drift slowly between
# bands so palette borders read as light/shade, not as separate patches
THEMES = {
    "snow":   [P("dteal", "dgreen", "green"), P("dteal", "gray", "lgray"),
               P("dteal", "lgray", "sky"), P("gray", "sky", "white")],
    "forest": [P("dteal", "dgreen", "green"), P("dteal", "dgreen", "lgreen"),
               P("dgreen", "green", "sky"), P("green", "sky", "white")],
    "warm":   [P("maroon", "brown", "rust"), P("brown", "rust", "orange"),
               P("brown", "orange", "yellow"), P("rust", "yellow", "peach")],
    "cave":   [P("dblue", "dteal", "teal"), P("dteal", "teal", "lav"),
               P("dteal", "lav", "sky"), P("teal", "sky", "white")],
    "mine":   [P("dteal", "dgreen", "olive"), P("dteal", "olive", "orange"),
               P("brown", "orange", "yellow"), P("olive", "yellow", "peach")],
    "horror": [P("maroon", "red", "rust"), P("maroon", "red", "pink"),
               P("red", "pink", "skin"), P("pink", "skin", "white")],
    "face":   [P("maroon", "brown", "rust"), P("brown", "rust", "skin"),
               P("rust", "skin", "peach"), P("skin", "peach", "white")],
    "sepia":  [P("brown", "rust", "orange"), P("brown", "orange", "yellow"),
               P("olive", "yellow", "peach"), P("orange", "peach", "white")],
    "throne": [P("dblue", "purple", "violet"), P("dblue", "purple", "plum"),
               P("purple", "plum", "lav"), P("plum", "lav", "white")],
    "night":  [P("dblue", "dteal", "blue"), P("dblue", "blue", "lav"),
               P("dteal", "lav", "sky"), P("blue", "sky", "white")],
}
RULES = [  # first match on lower-cased file stem wins
    (r"cu\d|eaten|burnt_little", "face"),
    (r"death|bite|tentacle|angular|candle|flame", "horror"),
    (r"throne|puz", "throne"),
    (r"opening|title|logo|gameboy", "sepia"),
    (r"village_temple", "snow"),
    (r"mine|cave|inside_cave|temple|market_place|locked", "mine"),
    (r"tavern|bedroom|barn_int|office_int|black_smith|work_bench|alchemist_int|"
     r"priesthouseint|interior|market_interior|merch|alchemist_house|candle", "warm"),
    (r"watchtower_dark|dark", "night"),
    (r"forest|briar|switchback|car2|field|outside|openmine|priest|valley|ruined|shacks|"
     r"farm|carrol|cages|market|watchtower|barn|village", "snow"),
]
def theme_for(stem):
    s = stem.lower()
    for pat, th in RULES:
        if re.search(pat, s): return th
    return "snow"

GB = sorted([(7, 24, 33), (48, 104, 80), (134, 192, 108), (224, 248, 207)], key=sum)
def level(c):
    return min(range(4), key=lambda i: sum((a - b) ** 2 for a, b in zip(GB[i], c[:3])))

def colorize(im, theme):
    im = im.convert("RGBA")
    w, h = im.size
    lv = [[level(im.getpixel((x, y))) for x in range(w)] for y in range(h)]
    bw, bh = -(-w // 16), -(-h // 16)
    mean = {}
    for by in range(bh):
        for bx in range(bw):
            v = [lv[y][x] for y in range(by*16, min(h, by*16+16)) for x in range(bx*16, min(w, bx*16+16))]
            mean[bx, by] = sum(v) / len(v)
    q = (0.8, 1.5, 2.2)   # absolute mean-brightness thresholds between bands
    band = {k: sum(m >= t for t in q) for k, m in mean.items()}
    smooth = band
    for _ in range(2):
        nxt = {}
        for (bx, by), b in smooth.items():
            n = [smooth[bx+i, by+j] for i in (-1, 0, 1) for j in (-1, 0, 1) if (bx+i, by+j) in smooth]
            nxt[bx, by] = Counter(n + [b, b]).most_common(1)[0][0]
        smooth = nxt
    pals = THEMES[theme]
    out = Image.new("RGBA", im.size)
    for y in range(h):
        for x in range(w):
            a = im.getpixel((x, y))[3]
            l = lv[y][x]
            col = K if l == 0 else pals[smooth[x // 16, y // 16]][l - 1]
            out.putpixel((x, y), (*col, a))
    return out, smooth

# sprites/icons: one fixed palette per file (L1, L2, L3), picked by name
SPRITE_PALS = [
    (r"fire|brazer|explode|portal|savepoint|bullet", P("rust", "orange", "yellow")),
    (r"wolf|deer|bone|dead|blood|puppies|dumbo|angler|eye|tentacle", P("maroon", "gray", "lgray")),
    (r"hero|npc|player|sword|arrow|rope|stick|snow", P("brown", "skin", "white")),
    (r"chest|machine|backpack|inv|key|note|barel|barrel|ladd?ar|door|pod|stairs|trap", P("brown", "orange", "peach")),
    (r"forest|briar|watchtower|bush|window|tower", P("dteal", "dgreen", "lgreen")),
]
def sprite_pal(stem):
    for pat, pal in SPRITE_PALS:
        if re.search(pat, stem.lower()): return pal
    return P("gray", "lgray", "white")

def colorize_sprite(im, pal):
    im = im.convert("RGBA")
    out = Image.new("RGBA", im.size)
    for y in range(im.height):
        for x in range(im.width):
            c = im.getpixel((x, y))
            l = level(c)
            out.putpixel((x, y), (*(K if l == 0 else pal[l - 1]), c[3]))
    return out

def main_sprites(src, dst):
    os.makedirs(dst, exist_ok=True)
    n = 0
    for f in sorted(glob.glob(os.path.join(src, "*.[pP][nN][gG]")), key=str.lower):
        stem = os.path.splitext(os.path.basename(f))[0]
        im = Image.open(f)
        if len({c[:3] for c in im.convert("RGBA").getdata() if c[3]}) > 8:
            print("skip (already coloured):", stem); continue
        colorize_sprite(im, sprite_pal(stem)).save(os.path.join(dst, stem + ".png")); n += 1
    print(n, "sprites colorized")

def main():
    if "--sprites" in sys.argv:
        return main_sprites(sys.argv[1], sys.argv[2])
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    files = sorted(glob.glob(os.path.join(src, "*.[pP][nN][gG]")), key=str.lower)
    done = []
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        im = Image.open(f)
        if len({c[:3] for c in im.convert("RGBA").getdata() if c[3]}) > 8:
            print("skip (already coloured):", stem); continue
        th = theme_for(stem)
        out, _ = colorize(im, th)
        out.save(os.path.join(dst, stem + ".png"))
        done.append((stem, th, out))
    if "--sheet" in sys.argv:
        sp = sys.argv[sys.argv.index("--sheet") + 1]
        cols = 6
        rows = -(-len(done) // cols)
        sh = Image.new("RGB", (cols * 164, rows * 130), (255, 0, 255))
        d = ImageDraw.Draw(sh)
        for i, (stem, th, im) in enumerate(done):
            x, y = (i % cols) * 164, (i // cols) * 130
            sh.paste(im.convert("RGB").crop((0, 0, 112, 112)), (x + 2, y + 14))
            d.text((x + 2, y + 2), f"{stem[:18]}|{th}", fill=(255, 255, 255))
        sh.save(sp)
    print(len(done), "colorized")

if __name__ == "__main__":
    main()
