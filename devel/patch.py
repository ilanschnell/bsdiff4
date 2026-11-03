"""
Reference implementation of bsdiff4.patch().

Here, the patch-application loop is implemented in Python; patch parsing
uses helpers from bsdiff4.format.
"""
from io import BytesIO

from bsdiff4.format import unpack_control_block, read_patch


def patch(src, patch_bytes) -> bytes:
    src_len = len(src)
    dst_len, control_block, diff_block, extra_block = read_patch(
        BytesIO(patch_bytes))
    dst = bytearray(dst_len)
    src_pos = dst_pos = diff_pos = extra_pos = 0

    for x, y, z in unpack_control_block(control_block):
        if x < 0 or x > dst_len - dst_pos or x > len(diff_block) - diff_pos:
            raise ValueError("corrupt patch (x out of range)")

        dst[dst_pos:dst_pos + x] = diff_block[diff_pos:diff_pos + x]
        diff_pos += x

        # Add source bytes where the diff range overlaps the source.
        for j in range(max(0, -src_pos), min(x, src_len - src_pos)):
            dst[dst_pos + j] = (dst[dst_pos + j] + src[src_pos + j]) % 256

        dst_pos += x

        if y < 0 or y > dst_len - dst_pos or y > len(extra_block) - extra_pos:
            raise ValueError("corrupt patch (y out of range)")

        dst[dst_pos:dst_pos + y] = extra_block[extra_pos:extra_pos + y]
        extra_pos += y
        dst_pos += y
        src_pos += x + z

    if dst_pos != dst_len:
        raise ValueError("corrupt patch (incomplete output)")

    if diff_pos != len(diff_block) or extra_pos != len(extra_block):
        raise ValueError("corrupt patch (unused block data)")

    return bytes(dst)

# ------------------------------- tests -----------------------------------

import unittest

from bsdiff4.format import pack_control_block, diff, write_patch
from bsdiff4.tests import ROUND_TRIP_CASES


class TestPatch(unittest.TestCase):

    def test_example(self):
        a = 1000 * b'a'
        b = bytearray(a)
        b[100:106] = b' diff '
        p = diff(a, bytes(b))
        self.assertEqual(patch(a, p), b)

    def round_trip(self, src, dst):
        p = diff(src, dst)
        dst2 = patch(src, p)
        self.assertIs(type(dst2), bytes)
        self.assertEqual(dst, dst2)

    def test_cases(self):
        for a, b in ROUND_TRIP_CASES:
            self.round_trip(a, b)
            self.round_trip(b, a)

    def assert_corrupt(self, reason, dst_len, controls,
                       bdiff=b'', bextra=b''):
        f = BytesIO()
        write_patch(f, dst_len, pack_control_block(*controls), bdiff, bextra)
        with self.assertRaisesRegex(ValueError,
                                    r"corrupt patch \(%s\)" % reason):
            patch(b'', f.getvalue())

    def test_malformed(self):
        # Negative diff and extra lengths.
        self.assert_corrupt("x out of range", 0, [(-1, 0, 0)])
        self.assert_corrupt("y out of range", 0, [(0, -1, 0)])

        # Truncated diff and extra blocks.
        self.assert_corrupt("x out of range", 1, [(1, 0, 0)])
        self.assert_corrupt("y out of range", 1, [(0, 1, 0)])

        # Diff and extra data extending beyond the destination.
        self.assert_corrupt("x out of range", 1, [(2, 0, 0)], bdiff=b'xx')
        self.assert_corrupt("y out of range", 1, [(0, 2, 0)], bextra=b'xx')

        # Destination length is 1, but no destination bytes are generated.
        self.assert_corrupt("incomplete output", 1, [])

        # Additional unused diff and extra block data.
        self.assert_corrupt("unused block data", 0, [], bdiff=b'x')
        self.assert_corrupt("unused block data", 0, [], bextra=b'x')


if __name__ == '__main__':
    unittest.main()
