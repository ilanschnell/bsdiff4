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

from bsdiff4 import core
from bsdiff4.format import (pack_control_block, read_patch,
                            unpack_control_block, write_patch)


def apply_symbolically(patch_bytes, source):
    """Apply a patch to symbolic source bytes.

    A reference is represented by ``(position, delta)`` and a literal by an
    integer.  When source is None, its bytes are the unknown original data.
    """
    control_block, diff_block, extra_block = read_patch(BytesIO(patch_bytes))
    # validate patch by applying it to empty source
    core.patch(b'', control_block, diff_block, extra_block)
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
                value = ((position, delta) if position >= 0 else delta)
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
        src_pos += x

        if y < 0 or y > dst_len - dst_pos or y > len(extra_block) - extra_pos:
            raise ValueError("corrupt patch (y out of range)")

        result.extend(extra_block[extra_pos:extra_pos + y])
        extra_pos += y
        dst_pos += y
        src_pos += z

    if dst_pos != dst_len:
        raise ValueError("corrupt patch (incomplete output)")

    assert diff_pos == len(diff_block) and extra_pos == len(extra_block)
    return result


def move_src(controls, src_pos, target):
    "Move the source position to target."
    if src_pos == target:
        return
    increment = target - src_pos
    if controls:
        x, y, z = controls[-1]
        assert z == 0
        controls[-1] = x, y, increment
    else:
        controls.append((0, 0, increment))


def make_patch(symbols):
    controls = []
    diff_block = bytearray()
    extra_block = bytearray()
    src_pos = 0
    i = 0

    while i < len(symbols):
        value = symbols[i]
        x = 0
        if isinstance(value, tuple):
            move_src(controls, src_pos, value[0])
            src_pos = value[0]

            while (i < len(symbols) and isinstance(symbols[i], tuple) and
                   symbols[i][0] == src_pos + x):
                diff_block.append(symbols[i][1])
                x += 1
                i += 1
            src_pos += x

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
    """
    Normalizes:
    * negative source references into literal extra bytes
    * maximal consecutive source references into diff runs
    * maximal literal sequences into extra runs
    * diff followed by extra into one control tuple
    * source seeks into the preceding tuple where possible
    * empty/no-op and trailing control tuples
    * the final z to zero
    * noncanonical integer encodings such as negative zero
    * compressed blocks by decoding and recompressing them
    """
    return make_patch(apply_symbolically(patch_bytes, None))


def combine(patch_ab: bytes, patch_bc: bytes) -> bytes:
    """combine(patch_ab, patch_bc) -> bytes

    Combine patches from A to B and B to C into a patch from A to C,
    without requiring A or B.  The result is not necessarily optimal.
    """
    b = apply_symbolically(patch_ab, None)
    c = apply_symbolically(patch_bc, b)
    return make_patch(c)


# ------------------------------- tests -----------------------------------

import os
import unittest
from random import randrange

from bsdiff4.format import diff, patch, validate_canonical
from bsdiff4.tests import ROUND_TRIP_CASES


class PatchUtil:

    @staticmethod
    def make_patch(controls, diff_block, extra_block):
        f = BytesIO()
        write_patch(f, pack_control_block(*controls),
                    diff_block, extra_block)
        return f.getvalue()

    def assert_patches_equal(self, patch_a, patch_b):
        blocks_a = read_patch(BytesIO(patch_a))
        blocks_b = read_patch(BytesIO(patch_b))
        self.assertEqual(list(unpack_control_block(blocks_a[0])),
                         list(unpack_control_block(blocks_b[0])))
        self.assertEqual(blocks_a[1], blocks_b[1])
        self.assertEqual(blocks_a[2], blocks_b[2])


class TestCanonicalize(unittest.TestCase, PatchUtil):

    def check_case(self, a, b):
        org_patch = diff(a, b)
        canon_patch = canonicalize(org_patch)
        self.assertIs(type(canon_patch), bytes)
        self.assertEqual(patch(a, canon_patch), b)
        # idempotency
        self.assertEqual(canonicalize(canon_patch), canon_patch)
        control_block, _, _ = read_patch(BytesIO(canon_patch))
        validate_canonical(control_block, len(a))

    def test_cases(self):
        for a, b in ROUND_TRIP_CASES:
            self.check_case(a, b)
            self.check_case(b, a)

    def test_negative_source_position(self):
        f = BytesIO()
        bcontrol = pack_control_block((0, 0, -1), (1, 0, 0))
        write_patch(f, bcontrol, b'\x2a', b'')
        canon_patch = canonicalize(f.getvalue())
        blocks = read_patch(BytesIO(canon_patch))
        self.assertEqual(list(unpack_control_block(blocks[0])),
                         [(0, 1, 0)])
        self.assertEqual(blocks[1:], (b'', b'\x2a'))
        validate_canonical(blocks[0], 0)

    def test_merge_rules(self):
        controls = [(1, 0, 15), (0, 0, -15), (19, 27, 0)]
        bdiff = b'\xf6' + 19 * b'\x00'
        bextra = b'TWYVGPNBMEOXQDHIUSRFLJLKEOX'
        self.assert_patches_equal(
            canonicalize(self.make_patch(controls, bdiff, bextra)),
            self.make_patch([(20, 27, 0)], bdiff, bextra))

    def test_merge_rules_diff_only(self):
        controls = [(19, 0, 37), (0, 0, -37), (74, 0, 0)]
        mid = b"'\x15\x12!\x1c\x1a8?\x1b\xd0\xec\xe9\xc5\xfb\xc9\xbe\xfe\xeb"
        bdiff = 38 * b'\0' + mid + 37 * b'\0'
        self.assert_patches_equal(
            canonicalize(self.make_patch(controls, bdiff, b'')),
            self.make_patch([(93, 0, 0)], bdiff, b''))


class TestCombine(unittest.TestCase, PatchUtil):

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
        msg = r"corrupt patch \(incomplete output\)"
        with self.assertRaisesRegex(ValueError, msg):
            combine(incomplete, empty)
        with self.assertRaisesRegex(ValueError, msg):
            combine(empty, incomplete)


if __name__ == '__main__':
    unittest.main()
