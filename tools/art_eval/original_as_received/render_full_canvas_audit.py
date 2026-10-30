"""Render an existing audit at its original source grid, without cropping."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('folder', type=Path)
parser.add_argument('--groups', action='store_true', help='Show the minimum palette-group witness and block IDs')
args = parser.parse_args()
out = args.folder
r = json.loads((out/'validation.json').read_text(encoding='utf-8'))
assert r['analysis_origin'] == [0, 0]
im = Image.open(r['snapshot']).convert('RGB')
assert hashlib.sha256(Path(r['source']).read_bytes()).hexdigest() == r['source_sha256']
scale = 4
left, top = 16, 54
legend = left + im.width*scale + 24
height = max(530, top + im.height*scale + 30)
canvas = Image.new('RGB', (legend+420, height), (30,30,30))
canvas.paste(im.resize((im.width*scale,im.height*scale),Image.Resampling.NEAREST),(left,top))
d = ImageDraw.Draw(canvas)
font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf',16)
d.text((16,12),f'FULL {im.width}x{im.height} IMAGE | GRID ORIGIN (0,0) | NO CROPPING',font=font,fill='white')
for x in range(0,im.width+1,16):
    d.line((left+x*scale,top,left+x*scale,top+im.height*scale),fill=(75,80,255))
for y in range(0,im.height+1,16):
    d.line((left,top+y*scale,left+im.width*scale,top+y*scale),fill=(75,80,255))
a = r['exact']
for b in a['local_conflicts']:
    x,y = left+b['x']*scale,top+b['y']*scale
    d.rectangle((x,y,x+63,y+63),outline=(255,60,60),width=2)
    d.rectangle((x+2,y+2,x+22,y+21),fill='black')
    d.text((x+4,y+2),str(b['slots_with_black']),font=font,fill='white')
tiles = len({im.crop((x,y,x+8,y+8)).tobytes() for y in range(0,im.height,8) for x in range(0,im.width,8)})
bg = '#'+''.join(f'{v:02X}' for v in r['shared_backdrop_RGB'])
lines = [f"{len(a['local_conflicts'])} blocks exceed backdrop + 3.",
         f'Shared backdrop: {bg}', 'Labels = slots including backdrop.', '',
         f"{a['blocks_over_four_visible_colors']} blocks have >4 visible colors.", '',
         f"Valid blocks need {a['minimum_groups_for_locally_valid_blocks']} palette groups.",
         'Only 4 available.', '', f'{tiles} raw picture tile patterns.',
         f"{a['exact_RGB_patterns']} with padded screen blank.",
         'Final legal encoding untested.', '', 'Original unchanged; no ROM build.']
for i,line in enumerate(lines):
    d.text((legend,58+29*i),line,font=font,fill='white')
filename = 'Full_Canvas_Grid.png'
if args.groups:
    filename = 'Palette_Group_Map.png'
    d.rectangle((legend,54,canvas.width,height),fill=(30,30,30))
    witness = r['exact']['group_witness']
    groups = [set(g) for g in witness]
    bg_tuple = tuple(r['shared_backdrop_RGB'])
    for y in range(0,im.height,16):
        for x in range(0,im.width,16):
            colors = set(im.crop((x,y,x+16,y+16)).get_flattened_data())-{bg_tuple}
            colors = {'#'+''.join(f'{v:02X}' for v in c) for c in colors}
            label = next((str(i+1) for i,g in enumerate(groups) if colors<=g),'X')
            xx,yy = left+x*scale,top+y*scale
            d.rectangle((xx+1,yy+1,xx+25,yy+20),fill='black')
            d.text((xx+3,yy+2),label,font=font,fill=(255,230,130))
    d.text((legend,58),f'{len(groups)} required groups; only 4 allowed.',font=font,fill='white')
    for i,g in enumerate(witness):
        y = 96+34*i
        d.text((legend,y),str(i+1),font=font,fill='white')
        for j,c in enumerate([bg]+g):
            x = legend+38+65*j
            d.rectangle((x,y,x+55,y+22),fill=c,outline=(130,130,130))
    d.text((legend,height-42),'All picture blocks pass locally.' if not a['local_conflicts'] else 'X = a local conflict.',font=font,fill='white')
d.text((16,height-21),'Diagnostic grid only; original pixels preserved.',font=font,fill='white')
canvas.save(out/filename)
print(json.dumps({'source_tiles':tiles,'diagnostic':str(out/filename)}))
