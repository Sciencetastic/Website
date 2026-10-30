"""Manual palette-group editing helpers for the Auditor.

An edit session works on a screen canvas against a FIXED set of up to 4 palette groups
(each = shared backdrop + up to 3 colours). Assigning a 16x16 square to a group remaps the
square's pixels into that group's colours while keeping its structure:
  * the backdrop colour always stays the backdrop
  * the remaining colours map one-to-one onto the group's colours by minimum colour error
    (shading order is preserved by the error cost); if the square uses more colours than the group
    can hold, the least-used ones fold into their nearest group colour.
"""
import itertools

import numpy as np

from .audit import BLOCK, TILE
from .convert import fit_groups, kept_palette
from .palette import color_distance, pack, unpack


def group_slots(group_codes, backdrop_code):
    """(4,3) array: slot 0 = backdrop, then the group's colours (padded with the backdrop)."""
    cols = [backdrop_code] + [int(c) for c in group_codes]
    while len(cols) < 4:
        cols.append(backdrop_code)
    return unpack(np.array(cols[:4])).astype(np.int32)


def remap_block(block, slots, backdrop):
    """Remap one (16,16,3) block into the 4 `slots` colours. Returns (new_block, cost)."""
    flat = block.reshape(-1, 3)
    codes = pack(flat)
    uniq, inv, cnt = np.unique(codes, return_inverse=True, return_counts=True)
    inv = np.asarray(inv).reshape(-1)
    cols = unpack(uniq).astype(np.int32)
    n = len(uniq)
    bcode = int(pack(np.array(backdrop)))
    D = color_distance(cols[:, None, :], slots[None, :, :]) * cnt[:, None]     # n x 4
    target = np.zeros(n, dtype=np.int64)
    is_bd = uniq == bcode
    free = [i for i in range(n) if not is_bd[i]]
    if is_bd.any():
        target[is_bd] = 0
    # usable slots = the group's own colours (padded slots equal to the backdrop are not targets)
    slot_pool = [i for i in (1, 2, 3) if int(pack(slots[i])) != bcode]
    free_sorted = sorted(free, key=lambda i: -cnt[i])
    main, rest = free_sorted[:len(slot_pool)], free_sorted[len(slot_pool):]
    if slot_pool:
        best = None
        for perm in itertools.permutations(slot_pool, len(main)):
            cost = sum(D[i, s_] for i, s_ in zip(main, perm))
            if best is None or cost < best[0]:
                best = (cost, perm)
        if best:
            for i, s_ in zip(main, best[1]):
                target[i] = s_
        for i in rest:                       # overflow colours fold into the nearest group colour
            target[i] = slot_pool[int(np.argmin(D[i, slot_pool]))]
    else:
        target[free] = 0
    out_flat = slots[target[inv]].astype(np.uint8)
    cost = float(sum(D[i, target[i]] for i in range(n)))
    return out_flat.reshape(block.shape), cost


def assign_block(canvas, bx, by, group_codes, backdrop):
    """Remap block (bx,by) of `canvas` in place into the group. Returns (old_pixels, cost)."""
    sl = (slice(by * BLOCK, (by + 1) * BLOCK), slice(bx * BLOCK, (bx + 1) * BLOCK))
    old = canvas[sl].copy()
    bcode = int(pack(np.array(backdrop)))
    new, cost = remap_block(old, group_slots(group_codes, bcode), backdrop)
    canvas[sl] = new
    return old, cost


def best_group_for_block(canvas, bx, by, groups, backdrop):
    """Index of the group that reproduces the block's colours with least error."""
    sl = (slice(by * BLOCK, (by + 1) * BLOCK), slice(bx * BLOCK, (bx + 1) * BLOCK))
    blk = canvas[sl]
    bcode = int(pack(np.array(backdrop)))
    costs = [remap_block(blk, group_slots(g, bcode), backdrop)[1] for g in groups]
    return int(np.argmin(costs))


def suggest_groups(canvas, valid, backdrop, k=4, max_colors=24):
    """Best k palette groups (tuples of colour codes) for the current pixels."""
    C, idx, bi = kept_palette(canvas, valid, backdrop, max_colors)
    fit = fit_groups(C, idx, valid, bi, k)
    groups = []
    for s in fit["sel"]:
        codes = tuple(sorted({int(pack(C[i])) for i in fit["trips"][s] if i != bi}))
        if codes not in groups:
            groups.append(codes)
    return groups


def attribute_table(blocks, canvas_w=256, canvas_h=240):
    """NES attribute-table bytes for one nametable (64 bytes) from block palette numbers.

    blocks: {(bx, by): group_index (0..3)}. Each byte covers a 32x32 px area:
    bits 0-1 top-left, 2-3 top-right, 4-5 bottom-left, 6-7 bottom-right 16x16 square."""
    out = bytearray(64)
    for (bx, by), g in blocks.items():
        if bx >= 16 or by >= 15:
            continue
        byte_index = (by // 2) * 8 + (bx // 2)
        shift = ((by % 2) * 2 + (bx % 2)) * 2
        out[byte_index] |= (int(g) & 3) << shift
    return bytes(out)
