"""
Combine two BSDIFF4 patches without access to the original data.

The first patch maps A to B and the second maps B to C.  Diff bytes are
additive modulo 256, so bytes in B can be represented symbolically as either
an A position plus a delta, or as a literal byte.  Applying the second patch
to that representation produces a patch from A directly to C.
The resulting patch is valid, but is not necessarily as compact as one
created directly from A and C.
"""
from io import BytesIO

from bsdiff4.format import (pack_control_block, read_patch,
                            unpack_control_block, write_patch)


INT64_MAX = (1 << 63) - 1
INT64_MIN = -(1 << 63)


def _update_position(position, increment):
    result = position + increment
    if not INT64_MIN <= result <= INT64_MAX:
        raise ValueError("corrupt patch (offset overflow)")
    return result


def _apply_symbolically(patch_bytes, source):
    """Apply a patch to symbolic source bytes.

    A reference is represented by ``(position, delta)`` and a literal by an
    integer.  When source is None, its bytes are the unknown original data.
    """
    control_block, diff_block, extra_block = read_patch(BytesIO(patch_bytes))
    dst_len = len(diff_block) + len(extra_block)
    result = []
    src_pos = dst_pos = diff_pos = extra_pos = 0

    for x, y, z in unpack_control_block(control_block):
        if x < 0 or x > dst_len - dst_pos or x > len(diff_block) - diff_pos:
            raise ValueError("corrupt patch (x out of range)")

        for j in range(x):
            delta = diff_block[diff_pos + j]
            position = src_pos + j
            if source is None:
                value = (position, delta)
            elif 0 <= position < len(source):
                value = source[position]
                if isinstance(value, tuple):
                    value = (value[0], (value[1] + delta) & 0xff)
                else:
                    value = (value + delta) & 0xff
            else:
                value = delta
            result.append(value)

        diff_pos += x
        dst_pos += x
        src_pos = _update_position(src_pos, x)

        if y < 0 or y > dst_len - dst_pos or y > len(extra_block) - extra_pos:
            raise ValueError("corrupt patch (y out of range)")

        result.extend(extra_block[extra_pos:extra_pos + y])
        extra_pos += y
        dst_pos += y
        src_pos = _update_position(src_pos, z)

    if dst_pos != dst_len:
        raise ValueError("corrupt patch (incomplete output)")

    assert diff_pos == len(diff_block) and extra_pos == len(extra_block)
    return result


def _seek(controls, position, target):
    """Move the source position to target."""
    merge = bool(controls)
    while position != target:
        increment = target - position
        increment = max(-INT64_MAX, min(INT64_MAX, increment))
        if merge:
            x, y, z = controls[-1]
            assert z == 0
            controls[-1] = x, y, increment
            merge = False
        else:
            controls.append((0, 0, increment))
        position = _update_position(position, increment)
    return position


def _make_patch(symbols):
    controls = []
    diff_block = bytearray()
    extra_block = bytearray()
    src_pos = 0
    i = 0

    while i < len(symbols):
        value = symbols[i]
        x = 0
        if isinstance(value, tuple):
            src_pos = _seek(controls, src_pos, value[0])

            while (i < len(symbols) and isinstance(symbols[i], tuple) and
                   symbols[i][0] == src_pos + x):
                diff_block.append(symbols[i][1])
                x += 1
                i += 1
            src_pos = _update_position(src_pos, x)

        y = 0
        while i < len(symbols) and isinstance(symbols[i], int):
            extra_block.append(symbols[i])
            y += 1
            i += 1

        controls.append((x, y, 0))

    f = BytesIO()
    write_patch(f, pack_control_block(*controls), diff_block, extra_block)
    return f.getvalue()


def canonicalize(patch_bytes: bytes) -> bytes:
    return _make_patch(_apply_symbolically(patch_bytes, None))


def combine(patch_ab: bytes, patch_bc: bytes) -> bytes:
    """combine(patch_ab, patch_bc) -> bytes

    Combine patches from A to B and B to C into a patch from A to C,
    without requiring A or B.  The result is not necessarily optimal.
    """
    b = _apply_symbolically(patch_ab, None)
    c = _apply_symbolically(patch_bc, b)
    return _make_patch(c)


# ------------------------------- tests -----------------------------------

import os
import sys
import unittest
from random import randrange

from bsdiff4.format import diff, patch
from bsdiff4.tests import ROUND_TRIP_CASES


class TestCanonicalize(unittest.TestCase):

    def check(self, a, b):
        patch_org = diff(a, b)
        patch_canon = canonicalize(patch_org)
        self.assertIs(type(patch_canon), bytes)
        self.assertEqual(patch(a, patch_canon), b)
        self.assertEqual(canonicalize(patch_canon), patch_canon)

    def test_cases(self):
        for a, b in ROUND_TRIP_CASES:
            self.check(a, b)
            self.check(b, a)


class TestCombine(unittest.TestCase):

    def check(self, a, b, c):
        patch_ab = diff(a, b)
        patch_bc = diff(b, c)
        patch_ac = combine(patch_ab, patch_bc)
        self.assertIs(type(patch_ac), bytes)
        self.assertEqual(patch(a, patch_ac), c)

    def test_examples(self):
        for values in [
                (b'', b'', b''),
                (b'', b'abc', b'xyz'),
                (b'abc', b'', b'xyz'),
                (b'abc', b'axc', b'axyz'),
                (100 * b'A' + 100 * b'B',
                 100 * b'B' + 100 * b'A',
                 100 * b'A' + 100 * b'C'),
        ]:
            self.check(*values)

    def test_without_source(self):
        # Exercise references, literals, forward seeks and backward seeks.
        patch_ab = self.make_patch([(3, 2, 2), (2, 0, 0)],
                                   bytes(range(1, 6)), b'XY')
        patch_bc = self.make_patch([(2, 1, 2), (3, 0, -7), (2, 0, 0)],
                                   bytes(range(10, 80, 10)), b'Q')
        patch_ac = combine(patch_ab, patch_bc)
        control_block = read_patch(BytesIO(patch_ac))[0]
        self.assertTrue(all(x or y for x, y, z in
                            unpack_control_block(control_block)))

        for a in b'', b'abc', b'abcdefg', 20 * b'a', bytes(range(20)):
            b = patch(a, patch_ab)
            c = patch(b, patch_bc)
            self.assertEqual(patch(a, patch_ac), c)

    def test_random(self):
        for _ in range(100):
            values = [os.urandom(randrange(100)) for _ in range(3)]
            self.check(*values)

    def test_random_mutations(self):
        n = 500
        a = os.urandom(n)
        b = bytearray(a)
        for _ in range(n // 10):
            b[randrange(n)] = randrange(256)
        b = bytes(b)
        c = bytearray(b)
        for _ in range(n // 10):
            c[randrange(n)] = randrange(256)
        c = bytes(c)
        self.check(a, b, c)

    def test_corrupt_patch(self):
        empty = diff(b'', b'')
        incomplete = self.make_patch([], b'x', b'')
        with self.assertRaisesRegex(ValueError,
                                    r"corrupt patch \(incomplete output\)"):
            combine(incomplete, empty)
        with self.assertRaisesRegex(ValueError,
                                    r"corrupt patch \(incomplete output\)"):
            combine(empty, incomplete)

    @staticmethod
    def make_patch(controls, diff_block, extra_block):
        f = BytesIO()
        write_patch(f, pack_control_block(*controls),
                    diff_block, extra_block)
        return f.getvalue()


if __name__ == '__main__':
    if len(sys.argv) == 2:
        from pprint import pprint
        from bsdiff4.format import read_data
        p = read_data(sys.argv[1])
        pprint(_apply_symbolically(p, None))
    else:
        unittest.main()
