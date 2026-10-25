"""Read-only owner PNG audit; diagnostic annotations are not import assets."""
from pathlib import Path
from collections import Counter, defaultdict
from itertools import combinations
from functools import lru_cache
import argparse, hashlib, json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path, nargs='?', default=Path(r'C:\Users\cool_\Desktop\UI_new_draft2.png'))
parser.add_argument('--origin', nargs=2, type=int, default=(0,0), metavar=('X','Y'))
parser.add_argument('--backdrop', default='000000', help='Shared backdrop RGB hex, without #')
args = parser.parse_args()
BACKDROP = tuple(bytes.fromhex(args.backdrop.lstrip('#')))
assert len(BACKDROP)==3
SOURCE = args.source.resolve()
raw = SOURCE.read_bytes()
sha = hashlib.sha256(raw).hexdigest()
out = ROOT / 'outputs/Art_Reviews' / f'Filter_Test_{sha[:8]}'
out.mkdir(parents=True, exist_ok=True)
snapshot = out / SOURCE.name
assert not snapshot.exists() or snapshot.read_bytes() == raw
snapshot.write_bytes(raw)
im = Image.open(snapshot).convert('RGBA')
source_size = im.size
ox, oy = args.origin
assert 0 <= ox and 0 <= oy and ox+im.width <= 256 and oy+im.height <= 240
rgba = list(im.get_flattened_data())
assert all(p[3] in (0, 255) for p in rgba)
pixels = [p[:3] if p[3] else BACKDROP for p in rgba]
source_rgb = Image.new('RGB', im.size)
source_rgb.putdata(pixels)
rgb = Image.new('RGB', (256,240), BACKDROP)
rgb.paste(source_rgb, (ox,oy))
pixels = list(rgb.get_flattened_data())

def color(c): return '#'+''.join(f'{v:02X}' for v in c)

def audit(image):
    blocks=[]
    sets=defaultdict(list)
    for y in range(0,240,16):
        for x in range(0,256,16):
            counts=Counter(image.crop((x,y,x+16,y+16)).get_flattened_data())
            nonblack=frozenset(counts)-{BACKDROP}
            sets[nonblack].append([x,y])
            blocks.append(dict(x=x,y=y,visible_colors=len(counts),slots_with_black=len(nonblack)+1,
                               colors={color(c):n for c,n in counts.items()}))
    forced=[s for s in sets if len(s)==3]
    remaining=[s for s in sets if len(s)<3 and not any(s<=t for t in forced)]
    colors=sorted(set().union(*(s for s in sets if len(s)<=3)))
    masks={}
    for c in combinations(colors,min(3,len(colors))):
        mask=sum(1<<i for i,s in enumerate(remaining) if s<=frozenset(c))
        if mask: masks.setdefault(mask,c)
    masks={m:c for m,c in masks.items() if not any(m!=n and m&n==m for n in masks)}
    @lru_cache(None)
    def cover(todo):
        if not todo:return ()
        pivot=min((i for i in range(len(remaining)) if todo>>i&1),key=lambda i:sum(bool(m>>i&1) for m in masks))
        options=[(m,)+cover(todo&~m) for m in masks if m>>pivot&1]
        return min(options,key=len)
    extra=cover((1<<len(remaining))-1)
    tiles=[tuple(image.crop((x,y,x+8,y+8)).get_flattened_data()) for y in range(0,240,8) for x in range(0,256,8)]
    # Arbitrary per-tile color relabeling is more permissive than legal attribute palettes.
    # Therefore this gives a rigorous lower bound, not an achievable CHR count.
    def canonical(tile):
        labels={}
        return bytes(labels.setdefault(c,len(labels)) for c in tile)
    return dict(local_conflicts=[b for b in blocks if b['slots_with_black']>4],
                blocks_over_four_visible_colors=sum(b['visible_colors']>4 for b in blocks),
                maximum_slots_with_shared_black=max(b['slots_with_black'] for b in blocks),
                forced_distinct_full_triples=len(forced),
                minimum_groups_for_locally_valid_blocks=len(forced)+len(extra),
                group_witness=[list(map(color,sorted(g))) for g in forced]+[list(map(color,masks[m])) for m in extra],
                exact_RGB_patterns=len(set(tiles)),
                pattern_lower_bound_with_arbitrary_color_relabeling=len({canonical(t) for t in tiles}),
                over_four_color_8x8_tiles=sum(len(set(t))>4 for t in tiles),blocks=blocks)

exact=audit(rgb)
palette_pass=not exact['local_conflicts'] and exact['minimum_groups_for_locally_valid_blocks']<=4
merged=rgb.copy()
merged.putdata([BACKDROP if c==(5,5,5) else c for c in pixels])
normalized=audit(merged)
report=dict(source=str(SOURCE),source_sha256=sha,snapshot=str(snapshot),canvas=[256,240],source_canvas=list(source_size),analysis_origin=[ox,oy],
            shared_backdrop_RGB=list(BACKDROP),
            whole_screen_palette_pass=palette_pass,
            opaque_colors={color(c[:3]):n for c,n in Counter(rgba).items() if c[3]},
            transparent_pixels=sum(p[3]==0 for p in rgba),exact=exact,
            hypothetical_merge_050505_into_shared_black=normalized,
            scope='PNG audit only. No artwork conversion, ROM build, emulator or native-editor test; source untouched.')
(out/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

canvas=Image.new('RGB',(1140,760),(25,25,25))
canvas.paste(rgb.resize((768,720),Image.Resampling.NEAREST),(0,40))
d=ImageDraw.Draw(canvas)
font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',16)
small=ImageFont.truetype('C:/Windows/Fonts/consolab.ttf',14)
bad={(b['x'],b['y']) for b in normalized['local_conflicts']}
for i,b in enumerate(exact['local_conflicts'],1):
    x,y=b['x']*3,40+b['y']*3
    fill=(255,70,70) if (b['x'],b['y']) in bad else (255,185,30)
    d.rectangle((x,y,x+47,y+47),outline=fill,width=2)
    d.rectangle((x+2,y+2,x+29,y+17),fill=(20,20,20))
    d.text((x+3,y+2),str(i),font=small,fill=fill)
d.text((12,10),'FULL SOURCE + 16x16 ATTRIBUTE CONFLICTS (diagnostic)',font=font,fill='white')
lines=['PALETTES: '+('PASS' if palette_pass else 'FAIL'),'',f"{len(report['opaque_colors'])} opaque RGB colors",f"{report['transparent_pixels']} transparent pixels",f"{exact['exact_RGB_patterns']} raw RGB tile patterns",f"{exact['pattern_lower_bound_with_arbitrary_color_relabeling']} minimum pattern shapes",'',f"{len(exact['local_conflicts'])} blocks over black + 3",f"Worst block: {exact['maximum_slots_with_shared_black']} slots",'', 'RED: still over capacity after', '#050505 merges into black.', 'ORANGE: near-black merge fixes', 'this local block only.', '',f"After merge: {len(normalized['local_conflicts'])} blocks still fail",f"Valid blocks need >= {normalized['minimum_groups_for_locally_valid_blocks']} groups",'(Only 4 background groups.)','', 'No artwork or engine edits.', 'See validation.json for coords.', '', 'Tile budget: 192 art + 64 font.', 'Shape count is a lower bound,', 'not a completed CHR conversion.']
for i,line in enumerate(lines):d.text((784,16+i*26),line,font=font,fill='white')
canvas.save(out/'Palette_Conflicts.png')
(out/'REVIEW.md').write_text(f'''# Filter test

Source: `{SOURCE}`. SHA-256: `{sha}`. Original untouched; snapshot byte-identical.

**Unchanged background-only PNG {'passes' if palette_pass else 'fails'} the checked NES palette-group constraints.** All 16x16 regions are measured from screen origin (0,0), with shared black backdrop; source placement is {ox},{oy}.

- {len(report['opaque_colors'])} opaque RGB colors plus transparency; transparent pixels composite onto shared black for this test.
- {len(exact['local_conflicts'])} blocks exceed shared black plus three colors; {exact['blocks_over_four_visible_colors']} contain more than four visible colors. Worst requires {exact['maximum_slots_with_shared_black']} slots.
- Hypothetically merging opaque #050505 into the black backdrop still leaves {len(normalized['local_conflicts'])} failing blocks. This is only an in-memory diagnostic; no revised art was saved.
- The locally valid blocks alone require at least {normalized['minimum_groups_for_locally_valid_blocks']} global groups after that merge; only four background groups are available. Overfull blocks are excluded from this group minimum, not silently counted as valid.
- {exact['exact_RGB_patterns']} exact RGB 8x8 patterns; arbitrary color relabeling gives a rigorous lower bound of {exact['pattern_lower_bound_with_arbitrary_color_relabeling']} pattern shapes. It is not a final achievable 2-bit CHR count. Current port reserves 64 of 256 background patterns for font, leaving 192 for art/state patterns.

`Palette_Conflicts.png` shows the whole source at 3x. Red blocks still fail after near-black merging; orange blocks pass locally after that merge. `validation.json` records every coordinate, color count, and minimum-group witness.

This tests local color limits and globally shared groups, not NES RGB-display calibration, engine import, overlay feasibility or complete CHR assignment. No sprite overlay plan was attempted. No build/test or project promotion. Existing Car Scene v1 ROMs remain unchanged.
''',encoding='utf-8')
assert SOURCE.read_bytes()==snapshot.read_bytes()==raw
print(json.dumps(dict(output=str(out),source_sha256=sha,opaque_colors=len(report['opaque_colors']),transparent_pixels=report['transparent_pixels'],exact={k:v for k,v in exact.items() if k not in ('blocks','local_conflicts','group_witness')},merged={k:v for k,v in normalized.items() if k not in ('blocks','local_conflicts','group_witness')},bad_blocks=len(exact['local_conflicts']),bad_after_merge=len(normalized['local_conflicts'])),indent=2))
