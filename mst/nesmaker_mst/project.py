"""High-level, headless access to a NES Maker 4.5.9 `.MST` project file.

Everything is built on a lossless *leaf list*: the file is a flat sequence of primitive values
(int32 / uint32 / byte / bool / string / raw bytes). `MSTProject.to_bytes()` writes those leaves back
in order, so an untouched project round-trips byte-for-byte and an edit changes exactly the leaves
that were set.

Safety model
  * Scalar edits (tile ids, palette colours, names, flags ...) never change the file layout.
  * Structural edits (add/remove list items) splice whole leaf blocks, fix the owning count leaf and
    re-parse the result; the whole file must still be consumed or the edit is rejected.
  * `save()` never overwrites an existing file unless asked and re-parses what it wrote.
"""
import copy
import io
import os
import struct
import uuid

from . import schema_reader as sr
from .schema_reader import Leaf, Node

NES_COLOR_COUNT = 64


# --------------------------------------------------------------------------- primitive emit
def _emit(l):
    k, v = l.kind, l.val
    if k == 'i32':
        return struct.pack('<i', v)
    if k == 'u32':
        return struct.pack('<I', v)
    if k == 'u8':
        return bytes((v,))
    if k == 'bool':
        return b'\x01' if v else b'\x00'
    if k == 'char':
        return v.encode('utf-8')
    if k == 'str':
        raw = v.encode('utf-8', 'surrogateescape')
        n, out = len(raw), bytearray()
        while True:
            b = n & 0x7f
            n >>= 7
            if n:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
        return bytes(out) + raw
    if k == 'bytes':
        return bytes(v)
    raise ValueError(k)


def guid_str(b):
    return str(uuid.UUID(bytes_le=bytes(b)))


def guid_bytes(s):
    return uuid.UUID(s).bytes_le


# --------------------------------------------------------------------------- node helpers
def new_var_leaves(name, value=0, notes='', enabled=True):
    """Leaves of one UserDefinedVar record (FileVersion >= 344: Name, InitialValue, Enabled, Notes)."""
    mk = lambda k, v, n: Leaf(0, k, v, n, None, None, 0, None)  # noqa: E731
    return [mk('str', name, 'Name'), mk('i32', int(value), 'InitialValue'), mk('bool', bool(enabled), 'Enabled'),
            mk('str', notes, 'Notes')]


def kids(node, cls=None):
    return [x for x in node._items if isinstance(x, Node) and (cls is None or x._cls == cls)]


def leaves_of(node):
    return [x for x in node._items if isinstance(x, Leaf)]


def field(node, name):
    for x in node._items:
        if isinstance(x, Leaf) and x.name == name:
            return x
    raise KeyError(f'{node._cls} has no field {name!r}')


def array(node, name):
    return [x for x in node._items if isinstance(x, Leaf) and x.name == name]


def all_leaves(node):
    """Every leaf under node, in file order."""
    out = []
    for x in node._items:
        if isinstance(x, Leaf):
            out.append(x)
        else:
            out.extend(all_leaves(x))
    return out


class NodeView:
    """Dict-like access to the scalar fields of one serialized object."""

    def __init__(self, proj, node):
        self.proj, self.node = proj, node

    def fields(self):
        d = {}
        for l in leaves_of(self.node):
            if l.name and not l.name.startswith('$') and l.idx is None:
                d.setdefault(l.name, l.val)
        return d

    def __getitem__(self, name):
        return field(self.node, name).val

    def __setitem__(self, name, value):
        self.proj.set_leaf(field(self.node, name), value)

    def __repr__(self):
        return f'<{self.node._cls} {self.fields()}>'


# --------------------------------------------------------------------------- BMP helpers
def bmp_pixels(b):
    """Return (offset, width, height, bpp, stride, bottom_up) for an uncompressed BMP byte string."""
    off = struct.unpack_from('<I', b, 10)[0]
    w, h = struct.unpack_from('<ii', b, 18)
    bpp = struct.unpack_from('<H', b, 28)[0]
    stride = ((w * bpp + 31) // 32) * 4
    return off, w, abs(h), bpp, stride, h > 0


def bmp_cell(b, col, row, size=16):
    off, w, h, bpp, stride, up = bmp_pixels(b)
    if bpp != 32:
        raise ValueError('only 32bpp preview BMPs are supported')
    rows = []
    for r in range(size):
        y = row * size + r
        fy = (h - 1 - y) if up else y
        s = off + fy * stride + col * size * 4
        rows.append(bytes(b[s:s + size * 4]))
    return b''.join(rows)


def bmp_put_cell(b, col, row, cell, size=16):
    off, w, h, bpp, stride, up = bmp_pixels(b)
    ba = bytearray(b)
    for r in range(size):
        y = row * size + r
        fy = (h - 1 - y) if up else y
        s = off + fy * stride + col * size * 4
        ba[s:s + size * 4] = cell[r * size * 4:(r + 1) * size * 4]
    return bytes(ba)


# --------------------------------------------------------------------------- the project
class MSTProject:
    SUPPORTED_VERSION = 374

    def __init__(self, data):
        self._load(bytes(data))
        self._original = bytes(data)

    @classmethod
    def open(cls, path):
        with open(path, 'rb') as f:
            return cls(f.read())

    def _load(self, data):
        it, root = sr.parse_mst(data)
        if it.version != self.SUPPORTED_VERSION:
            raise ValueError(f'unsupported FileVersion {it.version}; only {self.SUPPORTED_VERSION} is verified')
        self.leaves = it.R.leaves
        self.root = root
        self.tail = data[it.R.pos:]
        self.version = it.version

    # ---- (de)serialisation
    def to_bytes(self):
        return b''.join(_emit(l) for l in self.leaves) + self.tail

    def verify_roundtrip(self):
        """True when the untouched leaf list reproduces the loaded bytes exactly."""
        return self.to_bytes() == self._original

    def save(self, path, overwrite=False):
        """Atomically write the project to a *new* file and re-parse it to prove it is well formed."""
        if os.path.exists(path) and not overwrite:
            raise FileExistsError(f'{path} exists; pass overwrite=True (keep a backup!)')
        data = self.to_bytes()
        MSTProject(data)                     # must parse and consume every modelled byte
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)
        return len(data)

    # ---- generic leaf edits
    def set_leaf(self, leaf, value):
        k = leaf.kind
        if k in ('i32', 'u32', 'u8') and not isinstance(value, int):
            raise TypeError(f'{leaf.name} needs an int')
        if k == 'u8' and not 0 <= value <= 255:
            raise ValueError('byte out of range')
        if k == 'i32' and not -2**31 <= value < 2**31:
            raise ValueError('int32 out of range')
        if k == 'u32' and not 0 <= value < 2**32:
            raise ValueError('uint32 out of range')
        if k == 'bool':
            value = bool(value)
        if k == 'str' and not isinstance(value, str):
            raise TypeError('string needed')
        if k == 'bytes':
            raise TypeError('use set_blob for byte blobs (it must fix the length prefix)')
        leaf.val = value

    def set_blob(self, leaf, blob):
        """Replace a length-prefixed byte blob (i32 length leaf immediately precedes it)."""
        i = self._index(leaf)
        ln = self.leaves[i - 1]
        if ln.kind != 'i32' or ln.val != len(leaf.val):
            raise ValueError('blob is not preceded by its length prefix; refusing')
        leaf.val = bytes(blob)
        ln.val = len(blob)

    def _index(self, leaf):
        for i, l in enumerate(self.leaves):
            if l is leaf:
                return i
        raise KeyError('leaf not in project')

    # ---- structural edits: splice, fix counts, re-parse
    def _reparse(self):
        data = self.to_bytes()
        self._load(data)

    def splice(self, start_leaf_index, remove, insert):
        self.leaves[start_leaf_index:start_leaf_index + remove] = insert
        self._reparse()

    # =================================================================== palettes
    @property
    def palettes(self):
        out, prev = [], None
        for x in self.root._items:
            if isinstance(x, Node) and x._cls == 'PaletteInfo' and isinstance(prev, Leaf) and prev.kind == 'str':
                out.append(Palette(self, len(out), prev, x))
            prev = x
        return out

    # =================================================================== screens
    @property
    def screens(self):
        out, prev2, prev = [], None, None
        for x in self.root._items:
            if isinstance(x, Node) and x._cls == 'ScreenInfo' and isinstance(prev, Leaf) and prev.kind == 'bytes' and len(prev.val) == 16:
                out.append(Screen(self, len(out), prev, x))
            prev2, prev = prev, x
        return out

    def screen_by_guid(self, g):
        for s in self.screens:
            if s.guid == g:
                return s
        raise KeyError(g)

    def _clone_leaves(self, leaves):
        return [Leaf(0, l.kind, copy.copy(l.val), l.name, None, l.idx, 0, None) for l in leaves]

    def clone_screen(self, src, new_guid=None):
        """Duplicate a screen (key + record) at the end of the screen table; returns the new GUID.
        The copy is not placed on any map; use place_screen()."""
        src_s = self.screens[src] if isinstance(src, int) else self.screen_by_guid(src)
        new_guid = new_guid or str(uuid.uuid4())
        if new_guid in {s.guid for s in self.screens}:
            raise ValueError('GUID already used')
        ls = self.leaves
        key_i = self._index(src_s._key)
        block = ls[key_i - 1:key_i + 1] + all_leaves(src_s.node)       # i32 16, guid bytes, record leaves
        last = self.screens[-1]
        pos = self._index(all_leaves(last.node)[-1]) + 1
        new = self._clone_leaves(block)
        gb = guid_bytes(new_guid)
        new[1].val = gb
        # the record repeats its own ScreenGuid (i32 len + 16 bytes)
        for i, l in enumerate(new):
            if l.kind == 'bytes' and l.val == src_s._key.val and i > 1:
                l.val = gb
        ls[3].val += 1                                                      # header: screen count
        self.splice(pos, 0, new)
        return new_guid

    def delete_screen(self, guid):
        """Remove a screen and any map cells that point at it."""
        for world in ('overworld', 'underworld'):
            for e in self.world_map(world):
                if e.guid == guid:
                    self.unplace_screen(world, e.x, e.y)
        s = self.screen_by_guid(guid)
        ls = self.leaves
        a = self._index(s._key) - 1
        b = self._index(all_leaves(s.node)[-1]) + 1
        ls[3].val -= 1
        self.splice(a, b - a, [])

    def cell_library(self):
        """(bank, mainTileset, screenTileset, paletteId, tile, subpalette) -> 16x16 BGRA cell, learned
        from every screen preview in the project. Used to refresh previews after tile edits."""
        lib = {}
        for s in self.screens:
            b = s.preview_bytes()
            if not b:
                continue
            key0 = (s['BankID'], s['TileSetMainID'], s['TileSetScreenID'], s['PaletteID'])
            for i, (t, sp) in enumerate(zip(s.tiles(), s.subpalettes())):
                lib.setdefault(key0 + (t, sp), bmp_cell(b, i % 16, i // 16))
        return lib

    # =================================================================== maps
    def world_map(self, world='overworld'):
        """List of MapEntry(x, y, guid) for 'overworld' or 'underworld' (screen placement)."""
        return _WorldMap(self, world).entries()

    def place_screen(self, world, x, y, guid):
        _WorldMap(self, world).place(x, y, guid)

    def unplace_screen(self, world, x, y):
        _WorldMap(self, world).remove(x, y)

    # =================================================================== graphics assets
    @property
    def assets(self):
        gas = kids(self.root, 'GraphicAsset')
        trs = kids(self.root, 'TileResouce')
        out = []
        prev = None
        i = 0
        for x in self.root._items:
            if isinstance(x, Node) and x._cls == 'GraphicAsset' and i < len(gas) and prev is not None and prev.kind == 'bytes':
                tr = trs[len(out)] if len(out) < len(trs) else None
                out.append(Asset(self, len(out), prev, x, tr))
            prev = x if isinstance(x, Leaf) else None
        return out

    # =================================================================== variables & scripts
    def user_vars(self):
        """Project-level user variables (the 'UserDefinedVars' list)."""
        return [Var(self, n) for n in kids(self.root, 'UserDefinedVar')]

    def add_user_var(self, name, value=0, notes='', enabled=True):
        """Append to the project-level UserDefinedVars list (clone a record, fix count, re-parse)."""
        zi = self._index(field(self.root, 'SpriteZeroCheck'))       # the field right after the list
        existing = kids(self.root, 'UserDefinedVar')
        if any(v.name == name for v in self.user_vars()):
            raise ValueError(f'user variable {name!r} already exists')
        if existing:
            first = self._index(all_leaves(existing[0])[0])
            count = self.leaves[first - 1]
        else:
            count = self.leaves[zi - 1]
        if count.kind != 'i32' or count.val != len(existing):
            raise RuntimeError('UserDefinedVars count leaf not where expected; refusing')
        new = new_var_leaves(name, value, notes, enabled)
        count.val += 1
        self.splice(zi, 0, new)

    def ram_sections(self):
        """name -> VarSection for the three UserRAMDefine blocks and the object-variable block."""
        rams = kids(self.root, 'UserRAMDefine')
        names = ['zeropage', 'overflow', 'constants']
        d = {n: VarSection(self, r) for n, r in zip(names, rams)}
        ov = kids(self.root, 'ObjectVariables')
        if ov:
            d['object'] = VarSection(self, ov[0])
        return d

    def global_vars(self):
        """[(name, initial_value)] from GlobalUserVars + GlobalUserVarInitialValues (parallel lists)."""
        return _GlobalVars(self)

    def script_defines(self):
        return [NodeView(self, n) for n in kids(self.root, 'ScriptDefine')]

    # =================================================================== misc views
    def initial_settings(self):
        return NodeView(self, kids(self.root, 'InitialSettings')[0])

    def monsters(self):
        return [NodeView(self, n) for n in kids(self.root, 'MonsterInfo')]

    def summary(self):
        c = {}
        for x in self.root._items:
            if isinstance(x, Node):
                c[x._cls] = c.get(x._cls, 0) + 1
        return c


# --------------------------------------------------------------------------- views
class Palette:
    def __init__(self, proj, idx, name_leaf, node):
        self.proj, self.index, self._name, self.node = proj, idx, name_leaf, node

    @property
    def name(self):
        return self._name.val

    @name.setter
    def name(self, v):
        self.proj.set_leaf(self._name, v)

    def _leaves(self):
        return [l for l in leaves_of(self.node)]

    @property
    def colors(self):
        """16 NES colour indices (0..63): 4 sub-palettes x 4 slots; slot 0 of each is the backdrop."""
        return [l.val for l in self._leaves()]

    def set_color(self, sub, slot, nes_index):
        if not (0 <= sub < 4 and 0 <= slot < 4):
            raise IndexError('sub-palette 0..3, slot 0..3')
        if not 0 <= nes_index < NES_COLOR_COUNT:
            raise ValueError('NES colour index must be 0..63')
        self.proj.set_leaf(self._leaves()[sub * 4 + slot], int(nes_index))

    def set_colors(self, colors):
        if len(colors) != 16:
            raise ValueError('need 16 colours')
        for i, c in enumerate(colors):
            self.set_color(i // 4, i % 4, c)

    def __repr__(self):
        return f'<Palette {self.index} {self.name!r} {self.colors}>'


class Screen:
    W, H = 16, 15

    def __init__(self, proj, idx, key_leaf, node):
        self.proj, self.index, self._key, self.node = proj, idx, key_leaf, node

    # identity
    @property
    def guid(self):
        return guid_str(self._key.val)

    # scalar fields (BankID, PaletteID, TileSetMainID, ScreenSpeed, SongIndex, ...)
    def __getitem__(self, name):
        return field(self.node, name).val

    def __setitem__(self, name, v):
        if name in ('TileData', 'SubPaletteData', 'AttributeData'):
            raise KeyError('use tiles()/set_tile() for grids')
        self.proj.set_leaf(field(self.node, name), v)

    def fields(self):
        return NodeView(self.proj, self.node).fields()

    # grids (240 cells, row-major, 16 columns x 15 rows)
    def tiles(self):
        return [l.val for l in array(self.node, 'TileData')]

    def subpalettes(self):
        return [l.val for l in array(self.node, 'SubPaletteData')]

    def attributes(self):
        return [l.val for l in array(self.node, 'AttributeData')]

    def get_tile(self, col, row):
        i = row * self.W + col
        return self.tiles()[i], self.subpalettes()[i]

    def set_tile(self, col, row, tile, subpalette=None, refresh_preview=True, library=None):
        """Set one 16x16 metatile cell. Returns 'preview-updated' or 'preview-stale'.

        tile      : tile id = index of the cell's top-left 8x8 in the CHR sheet (sheet is 16 tiles wide)
        subpalette: 0..3 (None keeps the current value)
        """
        if not (0 <= col < self.W and 0 <= row < self.H):
            raise IndexError('col 0..15, row 0..14')
        if not 0 <= tile < 256:
            raise ValueError('tile id 0..255')
        i = row * self.W + col
        if refresh_preview and library is None:
            library = self.proj.cell_library()      # learn cell art BEFORE touching the grid
        self.proj.set_leaf(array(self.node, 'TileData')[i], int(tile))
        if subpalette is not None:
            if not 0 <= subpalette < 4:
                raise ValueError('sub-palette 0..3')
            self.proj.set_leaf(array(self.node, 'SubPaletteData')[i], int(subpalette))
        if not refresh_preview:
            return 'preview-stale'
        return self._refresh_cell(col, row, library)

    def _refresh_cell(self, col, row, library=None):
        b = self.preview_bytes()
        if not b:
            return 'preview-stale'
        lib = library if library is not None else self.proj.cell_library()
        t, sp = self.get_tile(col, row)
        key = (self['BankID'], self['TileSetMainID'], self['TileSetScreenID'], self['PaletteID'], t, sp)
        cell = lib.get(key)
        if cell is None:
            return 'preview-stale'
        self.set_preview_bytes(bmp_put_cell(b, col, row, cell))
        return 'preview-updated'

    def fill(self, tile, subpalette=None):
        lib = self.proj.cell_library()
        res = set()
        for r in range(self.H):
            for c in range(self.W):
                res.add(self.set_tile(c, r, tile, subpalette, library=lib))
        return res

    # preview bitmap (256x240, 32bpp, re-rendered by the editor itself)
    def _preview_leaf(self):
        for l in leaves_of(self.node):
            if l.kind == 'bytes' and len(l.val) > 1000:
                return l
        return None

    def preview_bytes(self):
        l = self._preview_leaf()
        return l.val if l else None

    def set_preview_bytes(self, b):
        l = self._preview_leaf()
        self.proj.set_blob(l, b)

    def preview_image(self):
        from PIL import Image
        return Image.open(io.BytesIO(self.preview_bytes())).convert('RGB')

    def ascii(self):
        t = self.tiles()
        return '\n'.join(' '.join('%3d' % t[r * 16 + c] for c in range(16)) for r in range(15))

    def __repr__(self):
        return f'<Screen #{self.index} {self.guid} bank={self["BankID"]} pal={self["PaletteID"]}>'


class Asset:
    """One GraphicAsset: a CHR/tile sheet bitmap + its resource record (file name, bank, group, type)."""

    def __init__(self, proj, idx, key_leaf, node, tres):
        self.proj, self.index, self._key, self.node, self.tres = proj, idx, key_leaf, node, tres

    @property
    def guid(self):
        return guid_str(self._key.val)

    @property
    def resource(self):
        return NodeView(self.proj, self.tres).fields() if self.tres is not None else {}

    @property
    def file(self):
        """Relative path of the external BMP (under GraphicAssets/) that NES Maker keeps in sync."""
        return self.resource.get('Name', '').replace('\\', '/')

    def _bmp_leaf(self):
        for l in leaves_of(self.node):
            if l.kind == 'bytes' and len(l.val) > 54:
                return l
        return None

    def image(self):
        from PIL import Image
        l = self._bmp_leaf()
        return Image.open(io.BytesIO(l.val)).convert('RGB') if l else None

    def replace_image(self, img):
        """Swap the bitmap. Same pixel size is required (tile tables are sized by it)."""
        cur = self.image()
        if cur is None:
            raise ValueError('asset has no bitmap')
        if img.size != cur.size:
            raise ValueError(f'size must stay {cur.size}, got {img.size}')
        buf = io.BytesIO()
        img.convert('RGB').save(buf, 'BMP')
        self.proj.set_blob(self._bmp_leaf(), buf.getvalue())

    def __repr__(self):
        return f'<Asset #{self.index} {self.resource.get("TileType")}/{self.resource.get("GroupID")} {self.file}>'


class Var:
    def __init__(self, proj, node):
        self.proj, self.node = proj, node

    @property
    def name(self):
        return field(self.node, 'Name').val

    @name.setter
    def name(self, v):
        self.proj.set_leaf(field(self.node, 'Name'), v)

    @property
    def value(self):
        """InitialValue for user vars; size in bytes for RAM reservations; value for constants."""
        return field(self.node, 'InitialValue').val

    @value.setter
    def value(self, v):
        self.proj.set_leaf(field(self.node, 'InitialValue'), v)

    @property
    def enabled(self):
        return field(self.node, 'Enabled').val

    @enabled.setter
    def enabled(self, v):
        self.proj.set_leaf(field(self.node, 'Enabled'), v)

    @property
    def notes(self):
        return field(self.node, 'Notes').val

    @notes.setter
    def notes(self, v):
        self.proj.set_leaf(field(self.node, 'Notes'), v)

    def __repr__(self):
        return f'<Var {self.name}={self.value} enabled={self.enabled}>'


class VarSection:
    """A counted list of UserDefinedVar-shaped records (zero page, overflow RAM, constants, object vars)."""

    def __init__(self, proj, node):
        self.proj, self.node = proj, node

    def vars(self):
        return [Var(self.proj, n) for n in kids(self.node, 'UserDefinedVar')]

    def get(self, name):
        for v in self.vars():
            if v.name == name:
                return v
        raise KeyError(name)

    def _count_leaf(self):
        cl = [l for l in leaves_of(self.node) if l.kind == 'i32' and l.name in ('$v0', '$v7')]
        if not cl:
            raise KeyError('count leaf not found')
        return cl[-1] if self.node._cls == 'ObjectVariables' else cl[0]

    def add(self, name, value=1, notes='', enabled=True):
        """Append a variable record, fix the section's item count and re-parse."""
        proj = self.proj
        items = kids(self.node, 'UserDefinedVar')
        if any(v.name == name for v in self.vars()):
            raise ValueError(f'variable {name!r} already exists in this section')
        cl = self._count_leaf()
        pos = proj._index(all_leaves(items[-1])[-1]) + 1 if items else proj._index(cl) + 1
        new = new_var_leaves(name, value, notes, enabled)
        self._count_leaf().val += 1
        proj.splice(pos, 0, new)
        return name


class _GlobalVars:
    def __init__(self, proj):
        self.proj = proj
        rl = [x for x in proj.root._items if isinstance(x, Leaf)]
        self._idx = [i for i, l in enumerate(rl) if l.kind == 'str' and l.name == '$v132']
        self._vals = [l for l in rl if l.name == '$v142']
        self._names = [rl[i] for i in self._idx]

    def items(self):
        return [(n.val, v.val) for n, v in zip(self._names, self._vals)]


class MapEntry:
    def __init__(self, x, y, guid):
        self.x, self.y, self.guid = x, y, guid

    def __repr__(self):
        return f'({self.x},{self.y})->{self.guid}'


class _WorldMap:
    """Overworld/underworld placement: repeated (i32 x, i32 y, i32 16, 16-byte guid) records."""
    # the two blocks follow the screen records; their record counts are root header leaves #3 and #4
    def __init__(self, proj, world):
        if world not in ('overworld', 'underworld'):
            raise ValueError("world is 'overworld' or 'underworld'")
        self.proj, self.world = proj, world
        rl = [x for x in proj.root._items if isinstance(x, Leaf)]
        hdr = {l.name: l for l in rl[:8]}
        self.count_leaf = hdr['$v3'] if world == 'overworld' else hdr['$v4']
        self.xname, self.yname, self.lenname = ('$v28', '$v29', '$v30') if world == 'overworld' else ('$v34', '$v35', '$v36')
        self.rl = rl

    def _records(self):
        recs, L = [], self.rl
        for i, l in enumerate(L):
            if l.name == self.xname and i + 3 < len(L) and L[i + 1].name == self.yname:
                recs.append((l, L[i + 1], L[i + 2], L[i + 3]))
        return recs

    def entries(self):
        return [MapEntry(x.val, y.val, guid_str(g.val)) for x, y, _, g in self._records()]

    def place(self, x, y, guid):
        proj = self.proj
        recs = self._records()
        if any(r[0].val == x and r[1].val == y for r in recs):
            raise ValueError(f'{self.world} cell ({x},{y}) already holds a screen')
        if guid not in {s.guid for s in proj.screens}:
            raise KeyError(f'no screen {guid}')
        if recs:
            pos = proj._index(recs[-1][3]) + 1
        else:
            raise NotImplementedError('placing into an empty map is not supported yet')
        new = [Leaf(0, 'i32', int(x), self.xname, None, None, 0, None), Leaf(0, 'i32', int(y), self.yname, None, None, 0, None),
               Leaf(0, 'i32', 16, self.lenname, None, None, 0, None), Leaf(0, 'bytes', guid_bytes(guid), None, None, None, 0, None)]
        self.count_leaf.val += 1
        proj.splice(pos, 0, new)

    def remove(self, x, y):
        proj = self.proj
        for xl, yl, ln, g in self._records():
            if xl.val == x and yl.val == y:
                pos = proj._index(xl)
                self.count_leaf.val -= 1
                proj.splice(pos, 4, [])
                return
        raise KeyError((x, y))
