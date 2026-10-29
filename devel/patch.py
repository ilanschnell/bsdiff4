"""
Reference implementation of bsdiff4.patch().

Here, the patch-application loop is implemented in Python; patch parsing
uses helpers from bsdiff4.format.
"""
from io import BytesIO

from bsdiff4.format import unpack_control_block, read_patch


def patch(src, patch_bytes) -> bytes:
    src_len = len(src)
    dst_len, control_block, diff_block, extra_block = \
        read_patch(BytesIO(patch_bytes))
    dst = bytearray(dst_len)
    src_pos = dst_pos = diff_pos = extra_pos = 0

    for x, y, z in unpack_control_block(control_block):
        if x < 0 or x > dst_len - dst_pos or x > len(diff_block) - diff_pos:
            raise ValueError("corrupt patch")

        dst[dst_pos:dst_pos + x] = diff_block[diff_pos:diff_pos + x]
        diff_pos += x

        # Add source bytes where the diff range overlaps the source.
        for j in range(max(0, -src_pos), min(x, src_len - src_pos)):
            dst[dst_pos + j] = (dst[dst_pos + j] + src[src_pos + j]) % 256

        dst_pos += x

        if y < 0 or y > dst_len - dst_pos or y > len(extra_block) - extra_pos:
            raise ValueError("corrupt patch")

        dst[dst_pos:dst_pos + y] = extra_block[extra_pos:extra_pos + y]
        extra_pos += y
        dst_pos += y
        src_pos += x + z

    if (dst_pos != dst_len or diff_pos != len(diff_block) or
        extra_pos != len(extra_block)):
        raise ValueError("corrupt patch")

    return bytes(dst)

# ------------------------------- tests -----------------------------------

import os
import random
import unittest

from bsdiff4.format import pack_control_block, diff, write_patch


class TestPatch(unittest.TestCase):

    def test_example(self):
        a = 1000 * b'a'
        b = bytearray(a)
        b[100:106] = b' diff '
        p = diff(a, bytes(b))
        self.assertEqual(patch(a, p), b)

    def round_trip(self, src, dst):
        p = diff(src, dst)
        self.assertEqual(patch(src, p), dst)

    def test_zero(self):
        self.round_trip(b'', b'')

    def test_edge_cases(self):
        for src, dst in [(b'', b'x'), (b'x', b''), (b'abc', b'abc')]:
            self.round_trip(src, dst)

    def test_extra(self):
        src = os.urandom(1000)
        dst = src + os.urandom(10)
        self.round_trip(src, dst)
        self.round_trip(dst, src)

    def test_small(self):
        src = b'123456789 987654321'
        dst = b'123456789000987654321'
        self.round_trip(src, dst)
        self.round_trip(dst, src)

    def test_random(self):
        for _ in range(100):
            n1 = random.randint(0, 1000)
            n2 = random.randint(0, 1000)
            self.round_trip(os.urandom(n1), os.urandom(n2))

    def assert_corrupt(self, dst_len, controls, bdiff=b'', bextra=b''):
        f = BytesIO()
        write_patch(f, dst_len, pack_control_block(*controls), bdiff, bextra)
        p = f.getvalue()
        with self.assertRaisesRegex(ValueError, "corrupt patch"):
            patch(b'', p)

    def test_malformed(self):
        # Negative diff and extra lengths.
        self.assert_corrupt(0, [(-1, 0, 0)])
        self.assert_corrupt(0, [(0, -1, 0)])

        # Truncated diff and extra blocks.
        self.assert_corrupt(1, [(1, 0, 0)])
        self.assert_corrupt(1, [(0, 1, 0)])

        # Diff and extra data extending beyond the destination.
        self.assert_corrupt(1, [(2, 0, 0)], bdiff=b'xx')
        self.assert_corrupt(1, [(0, 2, 0)], bextra=b'xx')


if __name__ == '__main__':
    unittest.main()
