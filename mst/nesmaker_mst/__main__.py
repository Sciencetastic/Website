"""python -m nesmaker_mst <command> ...   (see `--help`)"""
import argparse
import json
import sys

from . import MSTProject
from .project import kids, leaves_of
from .schema_reader import Leaf, Node


def _dump(node, depth, maxdepth, out, maxarr=8):
    pad = '  ' * depth
    ls = leaves_of(node)
    scal = {}
    for l in ls:
        if l.name and not l.name.startswith('$') and l.idx is None:
            v = l.val
            scal[l.name] = (v.hex()[:16] + '..') if isinstance(v, bytes) and len(v) > 8 else v
    arrs = {}
    for l in ls:
        if l.idx is not None:
            arrs.setdefault(l.name, []).append(l.val)
    out.append(f'{pad}{node._cls} {json.dumps(scal, default=str)[:300]}')
    for k, v in arrs.items():
        out.append(f'{pad}  {k}[{len(v)}] {v[:maxarr]}{"..." if len(v) > maxarr else ""}')
    if depth < maxdepth:
        for c in kids(node):
            _dump(c, depth + 1, maxdepth, out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='nesmaker_mst', description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('info', help='counts, palettes, screens, assets, variables')
    a.add_argument('mst')
    a = sub.add_parser('verify', help='parse + byte-exact round-trip check')
    a.add_argument('mst')
    a = sub.add_parser('tree', help='dump the object tree')
    a.add_argument('mst')
    a.add_argument('--depth', type=int, default=1)
    a = sub.add_parser('screen', help='print one screen grid / fields / save preview PNG')
    a.add_argument('mst')
    a.add_argument('index', type=int)
    a.add_argument('--png')
    a = sub.add_parser('diff', help='field-level diff of two projects with identical layout')
    a.add_argument('a')
    a.add_argument('b')
    a = sub.add_parser('set-tile', help='set a screen cell and write a NEW project file')
    a.add_argument('mst')
    a.add_argument('out')
    a.add_argument('screen', type=int)
    a.add_argument('col', type=int)
    a.add_argument('row', type=int)
    a.add_argument('tile', type=int)
    a.add_argument('--subpalette', type=int)
    args = ap.parse_args(argv)

    if args.cmd == 'diff':
        pa, pb = MSTProject.open(args.a), MSTProject.open(args.b)
        if len(pa.leaves) != len(pb.leaves):
            print('layouts differ (leaf counts %d vs %d): structural change' % (len(pa.leaves), len(pb.leaves)))
            return 1
        n = 0
        for x, y in zip(pa.leaves, pb.leaves):
            if x.val != y.val:
                n += 1
                if n <= 200:
                    print(f'{x.off:#x} {x.kind} {x.name}{"" if x.idx is None else "[%s]" % (x.idx,)}: {str(x.val)[:40]} -> {str(y.val)[:40]}')
        print(n, 'leaf(s) differ')
        return 0

    p = MSTProject.open(args.mst)
    if args.cmd == 'verify':
        ok = p.verify_roundtrip()
        print('FileVersion', p.version, '| modelled bytes', len(p.to_bytes()) - len(p.tail), '| opaque UI tail', len(p.tail),
              '| round-trip', 'EXACT' if ok else 'MISMATCH')
        return 0 if ok else 1
    if args.cmd == 'info':
        print('objects:', p.summary())
        print('\nPalettes with names:')
        for pal in p.palettes:
            if pal.name:
                print(f'  [{pal.index}] {pal.name!r}: {pal.colors}')
        print('\nScreens:')
        wm = {e.guid: (e.x, e.y) for e in p.world_map()}
        for s in p.screens:
            print(f'  #{s.index} {s.guid} map={wm.get(s.guid)} bank={s["BankID"]} palette={s["PaletteID"]} mainTS={s["TileSetMainID"]} screenTS={s["TileSetScreenID"]}')
        print('\nAssets:')
        for x in p.assets:
            print(' ', x, x.image().size if x.image() else None)
        print('\nUser vars:', [(v.name, v.value) for v in p.user_vars()])
        for k, sec in p.ram_sections().items():
            print(f'{k}:', [(v.name, v.value) for v in sec.vars()][:12], '...' if len(sec.vars()) > 12 else '')
        return 0
    if args.cmd == 'tree':
        out = []
        _dump(p.root, 0, args.depth, out)
        print('\n'.join(out))
        return 0
    if args.cmd == 'screen':
        s = p.screens[args.index]
        print(s, '\n' + s.ascii())
        print('subpalettes:\n' + '\n'.join(' '.join(str(s.subpalettes()[r * 16 + c]) for c in range(16)) for r in range(15)))
        print(s.fields())
        if args.png:
            s.preview_image().save(args.png)
            print('preview ->', args.png)
        return 0
    if args.cmd == 'set-tile':
        s = p.screens[args.screen]
        r = s.set_tile(args.col, args.row, args.tile, args.subpalette)
        n = p.save(args.out)
        print(f'{r}; wrote {n} bytes to {args.out}')
        return 0


if __name__ == '__main__':
    sys.exit(main())
