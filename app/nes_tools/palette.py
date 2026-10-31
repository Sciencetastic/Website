"""NES master palette and colour helpers (numpy based)."""
import numpy as np

# Commonly used NES master palette entries (RGB hex). Colours outside this
# list are snapped to the nearest entry (redmean distance).
_NES_HEX = [
    0x7c7c7c, 0x0000fc, 0x0000bc, 0x4428bc, 0x940084, 0xa80020, 0xa81000, 0x881400,
    0x503000, 0x007800, 0x006800, 0x005800, 0x004058, 0x000000,
    0xbcbcbc, 0x0078f8, 0x0058f8, 0x6844fc, 0xd800cc, 0xe40058, 0xf83800, 0xe45c10,
    0xac7c00, 0x00b800, 0x00a800, 0x00a844, 0x008888,
    0xf8f8f8, 0x3cbcfc, 0x6888fc, 0x9878f8, 0xf878f8, 0xf85898, 0xf87858, 0xfca044,
    0xf8b800, 0xb8f818, 0x58d854, 0x58f898, 0x00e8d8, 0x787878,
    0xfcfcfc, 0xa4e4fc, 0xb8b8f8, 0xd8b8f8, 0xf8b8f8, 0xf8a4c0, 0xf0d0b0, 0xfce0a8,
    0xf8d878, 0xd8f878, 0xb8f8b8, 0xb8f8d8, 0x00fcfc, 0xf8d8f8,
]
NES_PALETTE = np.array([[(c >> 16) & 255, (c >> 8) & 255, c & 255] for c in _NES_HEX], dtype=np.int32)


def color_distance(a, b):
    """Redmean colour distance; a and b broadcast, last axis is RGB."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    rm = (a[..., 0] + b[..., 0]) / 2
    d = a - b
    return (2 + rm / 256) * d[..., 0] ** 2 + 4 * d[..., 1] ** 2 + (2 + (255 - rm) / 256) * d[..., 2] ** 2


def snap_to_nes(rgb):
    """Snap every pixel of an HxWx3 uint8 array to the nearest NES palette colour."""
    rgb = np.asarray(rgb, dtype=np.uint8)
    flat = rgb.reshape(-1, 3)
    cols, inv = np.unique(flat, axis=0, return_inverse=True)
    inv = np.asarray(inv).reshape(-1)
    d = color_distance(cols[:, None, :], NES_PALETTE[None, :, :])
    return NES_PALETTE[d.argmin(1)][inv].reshape(rgb.shape).astype(np.uint8)


def pack(rgb):
    """Pack an (...,3) uint array into int codes 0xRRGGBB."""
    rgb = np.asarray(rgb).astype(np.int64)
    return (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]


def unpack(code):
    code = np.asarray(code).astype(np.int64)
    return np.stack([(code >> 16) & 255, (code >> 8) & 255, code & 255], axis=-1).astype(np.uint8)


def to_hex(c):
    return "#%02X%02X%02X" % tuple(int(v) for v in c[:3])


def from_hex(s):
    s = s.strip().lstrip("#")
    if len(s) != 6:
        raise ValueError("expected 6 hex digits, got %r" % s)
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
