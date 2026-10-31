"""Schema-driven .MST reader.

`schema/*.Recall.txt` describe, class by class, the exact order in which NES Maker (4.5.9, file
version 374) reads primitives from the project stream (including FileVersion gates and loops).
This module executes those descriptions against real bytes and records every primitive read
(offset, kind, value, field name, owning object). The result is a lossless leaf list: writing the
leaves back in order reproduces the file byte for byte (see MSTProject.to_bytes).
"""
import re, os, json, struct, sys

DEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema')
with open(os.path.join(DEC, 'field_types.json'), encoding='utf-8') as _fh:
    FT = json.load(_fh)


def clean(n):
    m = re.match(r'<(.+)>k__BackingField', n)
    return m.group(1) if m else n


FTYPES = {c: {clean(k): v for k, v in d.items()} for c, d in FT.items()}


def elem_type(t):
    m = re.match(r'.*`\d<(.+)>$', t)
    if m:
        a = m.group(1).split(',')
        return a[-1]
    if t.endswith('[]'):
        return t[:-2]
    return t


class Stub:
    """Auto-vivifying inert object used for state that does not affect parsing."""
    def __init__(self, **kw):
        self.__dict__['_d'] = dict(kw)

    def __getattr__(self, k):
        if k.startswith('__'):
            raise AttributeError(k)
        d = self.__dict__['_d']
        if k not in d:
            d[k] = Stub() if k != 'Count' else 0
        return d[k]

    def __setattr__(self, k, v):
        self.__dict__['_d'][k] = v

    def __call__(self, *a, **k):
        return Stub()

    def __getitem__(self, i):
        return Stub()

    def __setitem__(self, i, v):
        pass

    def __lt__(self, o): return False
    def __gt__(self, o): return False
    def __le__(self, o): return False
    def __ge__(self, o): return False
    def __bool__(self): return False
    def __add__(self, o): return 0
    __radd__ = __add__
    __sub__ = __add__
    __rsub__ = __add__

    def __iter__(self):
        return iter(())


class ListStub(list):
    @property
    def Count(self):
        return len(self)

    def Add(self, x):
        self.append(x)

    def Clear(self):
        self.clear()

    def __setattr__(self, k, v):
        if k == 'Item':
            return
        object.__setattr__(self, k, v)

    def __getattr__(self, k):
        if k.startswith('__'):
            raise AttributeError(k)
        return Stub()


class EnumStub:
    def __init__(self, items):
        self.items = list(items)
        self.i = -1

    def MoveNext(self):
        self.i += 1
        return self.i < len(self.items)

    @property
    def Current(self):
        return self.items[self.i]

    def Dispose(self):
        pass


class Leaf:
    __slots__ = ('off', 'kind', 'val', 'name', 'node', 'idx', 'size', 'raw')

    def __init__(self, off, kind, val, name, node, idx, size, raw):
        self.off, self.kind, self.val, self.name, self.node, self.idx, self.size, self.raw = off, kind, val, name, node, idx, size, raw

    def __repr__(self):
        return f'<{self.off:#x} {self.kind} {self.name}{"" if self.idx is None else "[%s]" % self.idx}={self.val!r}>'


class Node(Stub):
    def __init__(self, cls, parent=None, via=None):
        super().__init__()
        d = self.__dict__
        d['_cls'] = cls
        d['_parent'] = parent
        d['_via'] = via
        d['_items'] = []
        d['_fields'] = {}
        if cls == 'PaletteInfo':
            d['_d']['AllPalettes'] = ListStub([ListStub([0] * 4) for _ in range(4)])

    # attribute sets on a Node are model state (and recorded as scalar fields)
    def __repr__(self):
        return f'<Node {self._cls}>'


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.leaves = []
        self.cur_name = None
        self.cur_node = None
        self.cur_idx = None

    def _need(self, n):
        if self.pos + n > len(self.data):
            raise EOFError(f'read past end at {self.pos:#x}+{n}')

    def read(self, kind, n=None):
        d = self.data
        off = self.pos
        if kind == 'i32':
            self._need(4); v = struct.unpack_from('<i', d, off)[0]; self.pos += 4
        elif kind == 'u32':
            self._need(4); v = struct.unpack_from('<I', d, off)[0]; self.pos += 4
        elif kind == 'u8':
            self._need(1); v = d[off]; self.pos += 1
        elif kind == 'bool':
            self._need(1); v = d[off] != 0; self.pos += 1
        elif kind == 'char':
            self._need(1); v = chr(d[off]); self.pos += 1
        elif kind == 'str':
            ln = 0; sh = 0; p = off
            while True:
                self._need(1); b = d[p]; p += 1
                ln |= (b & 0x7f) << sh; sh += 7
                if not b & 0x80:
                    break
            self._need(ln + (p - off)); v = d[p:p + ln].decode('utf-8', 'surrogateescape'); self.pos = p + ln
        elif kind == 'bytes':
            self._need(n); v = bytes(d[off:off + n]); self.pos += n
        else:
            raise ValueError(kind)
        lf = Leaf(off, kind, v, self.cur_name, self.cur_node, self.cur_idx, self.pos - off, None)
        self.leaves.append(lf)
        if self.cur_node is not None:
            self.cur_node._items.append(lf)
        return v


KIND = {'Int32': 'i32', 'UInt32': 'u32', 'Byte': 'u8', 'Boolean': 'bool', 'String': 'str', 'Char': 'char'}


class Guid:
    def __init__(self, b=b'\0' * 16):
        self.b = b

    def __repr__(self):
        import uuid
        try:
            return 'Guid(%s)' % uuid.UUID(bytes_le=bytes(self.b))
        except Exception:
            return 'Guid(?)'


class Size:
    def __init__(self, w=0, h=0):
        self.Width, self.Height = w, h


class Point:
    def __init__(self, x=0, y=0):
        self.X, self.Y = x, y


class Unresolved(Exception):
    pass


class Interp:
    def __init__(self, data, strict=False):
        self.R = Reader(data)
        self.version = 0
        self.warn = {}
        self.cache = {}
        self.depth = 0

    # ---- program loading
    def prog(self, cls, meth):
        k = (cls, meth)
        if k in self.cache:
            return self.cache[k]
        p = os.path.join(DEC, f'{cls}.{meth}.txt')
        if not os.path.exists(p):
            self.cache[k] = None
            return None
        with open(p, encoding='utf-8') as fh:
            lines = [l.rstrip('\n') for l in fh if l.strip()]
        labels = {}
        for i, l in enumerate(lines):
            m = re.match(r'^(L[0-9a-f]+):$', l)
            if m:
                labels[m.group(1)] = i
        self.cache[k] = (lines, labels)
        return self.cache[k]

    # ---- expression translation
    def _w(self, key, txt):
        self.warn.setdefault(key, set()).add(txt)

    def translate(self, e):
        e = e.strip()
        e = re.sub(r'R:Bytes\(', '_rb(', e)
        e = re.sub(r'R:(Int32|UInt32|Byte|Boolean|String|Char)\(\)', lambda m: "_r('%s')" % KIND[m.group(1)], e)
        e = re.sub(r'new tok[0-9a-f]+\[', '_arr(', e)
        e = e.replace('new R:TypeSpec(', '_new(None,')
        e = re.sub(r'new (\w+)\(\)', r"_new('\1')", e)
        e = re.sub(r'new (\w+)\(', r"_new('\1',", e)
        e = e.replace(',)', ')')
        e = re.sub(r'(.+)\.GetEnumerator\(\)$', r'_enum(\1)', e)
        e = re.sub(r'\bnull\b', 'None', e)
        e = re.sub(r'(?<![=!<>])!(?!=)', ' not ', e)
        return e

    def make_ns(self, fr):
        R = self.R
        ns = {}

        def _r(kind):
            return R.read(kind)

        def _rb(n):
            return R.read('bytes', int(n))

        def _new(cls, *a):
            if cls is None or cls == 'TypeSpec':
                return ListStub()
            if cls == 'Guid':
                return Guid(a[0] if a else b'\0' * 16)
            if cls == 'Size':
                return Size(*a)
            if cls == 'Point':
                return Point(*a)
            if cls == 'MemoryStream':
                return Stub()
            if cls.startswith('M:') or cls.startswith('<'):
                return Stub()
            return Node(cls)

        def _arr(*a):
            return ListStub()
        ns['_enum'] = lambda c: EnumStub(c if isinstance(c, (list, tuple)) else [])
        ns.update(_r=_r, _rb=_rb, _new=_new, _arr=_arr, FileVersion=self.version)
        ns.update(fr['vars'])
        return ns

    def ev(self, expr, fr):
        py = self.translate(expr)
        ns = self.make_ns(fr)
        ns['this'] = fr['this']
        ns['a1'] = fr['vars'].get('a1', Stub())
        try:
            return eval(py, {'__builtins__': {'len': len, 'max': max, 'min': min, 'int': int}}, ns)
        except (NameError, AttributeError, TypeError, KeyError, ZeroDivisionError, IndexError, SyntaxError, ValueError) as ex:
            if '_r(' in py or '_rb(' in py:
                raise RuntimeError(f'cannot evaluate read expr {expr!r}: {ex}')
            self._w('eval', f'{expr} -> {ex}')
            return Stub()

    # ---- statement exec
    def run(self, cls, meth, this, args=None, name=None):
        pg = self.prog(cls, meth)
        if pg is None:
            raise RuntimeError(f'missing program {cls}.{meth}')
        lines, labels = pg
        fr = dict(this=this, vars={'a1': Stub()})
        if args:
            fr['vars'].update(args)
        pc = 0
        steps = 0
        n = len(lines)
        while pc < n:
            steps += 1
            if steps > 5_000_000:
                raise RuntimeError('step limit in %s.%s' % (cls, meth))
            l = lines[pc]
            pc += 1
            if re.match(r'^L[0-9a-f]+:$', l):
                continue
            if l == 'return' or l.startswith('return'):
                return
            m = re.match(r'^goto (L[0-9a-f]+)$', l)
            if m:
                pc = labels[m.group(1)]
                continue
            m = re.match(r'^switch (\S+) -> (\[.*\])$', l)
            if m:
                v = self.ev(m.group(1), fr)
                tg = eval(m.group(2))
                if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(tg):
                    pc = labels[tg[v]]
                continue
            m = re.match(r'^if (.+) goto (L[0-9a-f]+)$', l)
            if m:
                c = m.group(1)
                neg = False
                if c.startswith('!') and not c.startswith('!='):
                    neg = True
                    c = c[1:]
                v = self.ev(c, fr)
                if bool(v) != neg:
                    pc = labels[m.group(2)]
                continue
            if l.startswith('new tok') or l.startswith('??') or 'ReportLoadStatus' in l:
                continue
            # recall calls
            m = re.match(r'^(.+)\.Recall\(a1\)$', l)
            if m:
                self.do_recall(m.group(1), fr, cls)
                continue
            m = re.match(r'^(\S+) = TypeSpec::RecallNew\(a1\)$', l)
            if m:
                nxt = lines[pc]
                mm = re.search(r'this\.(\w+)\.Add\(', nxt)
                t = elem_type(FTYPES[cls][mm.group(1)])
                node = Node(t, via=m.group(1))
                self.do_recall_node(node, t)
                fr['vars'][m.group(1)] = node
                continue
            m = re.match(r'^this\.(Recall\w+)\((.*)\)$', l)
            if m and self.prog(cls, m.group(1)):
                self.R.cur_node = fr['this'] if isinstance(fr['this'], Node) else self.R.cur_node
                self.run(cls, m.group(1), fr['this'], args={'a1': Stub()})
                continue
            m = re.match(r'^(\S+?)\.\.ctor\((.*)\)$', l)
            if m:
                self.R.cur_name = None
                val = self.ev('new Guid(' + m.group(2) + ')', fr) if 'R:' in m.group(2) else self.ev('new Point(' + m.group(2) + ')', fr)
                fr['vars'][m.group(1)] = val
                continue
            # assignment
            m = re.match(r'^(.+?) = (.+)$', l)
            if m and not re.match(r'^.*[=!<>]$', m.group(1)):
                self.assign(m.group(1), m.group(2), fr)
                continue
            # bare call / other statement: evaluate for side effects (reads) only
            if 'R:' in l:
                self.R.cur_name = None
                self.ev(l, fr)
            else:
                try:
                    self.ev(l, fr)
                except RuntimeError:
                    raise

    def setname(self, lhs, fr):
        lhs = lhs.strip()
        m = re.match(r'^this\.(\w+)\.Item\[(.+)\]$', lhs)
        if m:
            self.R.cur_name = m.group(1)
            try:
                k = self.ev(m.group(2), fr)
                self.R.cur_idx = (k.X, k.Y) if isinstance(k, Point) else (k if isinstance(k, (int, str)) else None)
            except Exception:
                self.R.cur_idx = None
            return
        m = re.match(r'^this\.(\w+)(\[(.+)\])?$', lhs)
        if m:
            self.R.cur_name = m.group(1)
            self.R.cur_idx = None
            if m.group(3) is not None:
                try:
                    idx = self.ev(m.group(3), fr)
                    self.R.cur_idx = idx if isinstance(idx, int) else None
                except Exception:
                    pass
            return
        m = re.match(r'^(\w+)\[(.+)\]$', lhs)
        if m:
            self.R.cur_name = '$' + m.group(1)
            try:
                idx = self.ev(m.group(2), fr)
                self.R.cur_idx = idx if isinstance(idx, int) else None
            except Exception:
                self.R.cur_idx = None
            return
        self.R.cur_name = '$' + lhs if re.match(r'^\w+$', lhs) else None
        self.R.cur_idx = None

    def assign(self, lhs, rhs, fr):
        R = self.R
        node = fr['this'] if isinstance(fr['this'], Node) else None
        R.cur_node = node
        if 'R:' in rhs or '..ctor' in rhs:
            self.setname(lhs, fr)
        else:
            R.cur_name = None
        val = self.ev(rhs, fr)
        R.cur_name = None
        R.cur_idx = None
        lhs = lhs.strip()
        m = re.match(r'^this\.(\w+)$', lhs)
        if m:
            if node is not None:
                node.__dict__['_fields'][m.group(1)] = val
                if isinstance(val, Node):
                    val.__dict__['_via'] = m.group(1)
                    val.__dict__['_parent'] = node
                node.__dict__['_d'][m.group(1)] = val
            return
        if lhs == 'FileVersion':
            self.version = val
            return
        if re.match(r'^v\d+$', lhs):
            fr['vars'][lhs] = val
            return
        m = re.match(r'^(v\d+)\.(\w+)$', lhs)
        if m:
            tgt = fr['vars'].get(m.group(1))
            if isinstance(tgt, Stub):
                setattr(tgt, m.group(2), val)
            return
        m = re.match(r'^(v\d+)\[(.+)\]$', lhs)
        if m:
            tgt = fr['vars'].get(m.group(1))
            if isinstance(tgt, list):
                idx = self.ev(m.group(2), fr)
                if isinstance(idx, int) and 0 <= idx < len(tgt):
                    tgt[idx] = val
            return
        # array / item stores etc: ignore
        return

    def do_recall(self, recv, fr, cls):
        recv = recv.strip()
        this = fr['this']
        node = None
        t = None
        m = re.match(r'^this\.(\w+)(\[.+\])?$', recv)
        if m:
            fname = m.group(1)
            cur = this._d.get(fname) if isinstance(this, Node) else None
            if isinstance(cur, Node):
                node = cur
                t = cur._cls
            else:
                t = elem_type(FTYPES[this._cls][fname]) if m.group(2) else FTYPES[this._cls][fname]
                node = Node(t, parent=this, via=fname)
                if not m.group(2):
                    this._d[fname] = node
        else:
            node = self.ev(recv, fr)
            if not isinstance(node, Node):
                raise RuntimeError(f'recall receiver {recv!r} is not a Node ({node!r})')
            t = node._cls
        self.do_recall_node(node, t)

    def do_recall_node(self, node, t):
        parent = self.R.cur_node
        node.__dict__['_parent'] = parent
        if parent is not None:
            parent._items.append(node)
        node.__dict__['_start'] = len(self.R.leaves)
        saved = self.R.cur_node
        self.R.cur_node = node
        self.run(t, 'Recall', node)
        self.R.cur_node = saved
        node.__dict__['_end'] = len(self.R.leaves)


def parse_mst(data, root_cls='MainGameModel'):
    it = Interp(data)
    root = Node(root_cls)
    root.__dict__['_start'] = 0
    it.R.cur_node = root
    it.run(root_cls, 'Recall', root)
    root.__dict__['_end'] = len(it.R.leaves)
    return it, root


if __name__ == '__main__':
    p = sys.argv[1]
    data = open(p, 'rb').read()
    it, root = parse_mst(data)
    print(p, 'size', len(data), 'consumed', it.R.pos, 'leaves', len(it.R.leaves), 'ver', it.version)
    for k, v in it.warn.items():
        print('WARN', k, len(v), sorted(v)[:8])
