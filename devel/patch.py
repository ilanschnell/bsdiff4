"""
Pure Python implementation of BSDIFF4's patch function.
"""
import os
import random
import unittest
from io import BytesIO

from bsdiff4.format import (pack_control_block, unpack_control_block,
                            diff, read_patch, write_patch)


def patch(bsrc, bpatch) -> bytes:
    len_src = len(bsrc)
    len_dst, bcontrol, bdiff, bextra = read_patch(BytesIO(bpatch))
    bdst = bytearray(len_dst)
    newpos = oldpos = diffpos = extrapos = 0

    for x, y, z in unpack_control_block(bcontrol):
        if x < 0 or x > len_dst - newpos or x > len(bdiff) - diffpos:
            raise ValueError("corrupt patch")

        bdst[newpos:newpos + x] = bdiff[diffpos:diffpos + x]
        diffpos += x

        # Add source bytes where the diff range overlaps the source.
        for j in range(max(0, -oldpos), min(x, len_src - oldpos)):
            bdst[newpos + j] = (bdst[newpos + j] + bsrc[oldpos + j]) % 256

        newpos += x

        if y < 0 or y > len_dst - newpos or y > len(bextra) - extrapos:
            raise ValueError("corrupt patch")

        bdst[newpos:newpos + y] = bextra[extrapos:extrapos + y]
        extrapos += y
        newpos += y
        oldpos += x + z

    if newpos != len_dst or diffpos != len(bdiff) or extrapos != len(bextra):
        raise ValueError("corrupt patch")

    return bytes(bdst)


class TestPatch(unittest.TestCase):

    def make_patch(self, len_dst, controls, bdiff=b'', bextra=b''):
        bcontrol = pack_control_block(*controls)
        f = BytesIO()
        write_patch(f, len_dst, bcontrol, bdiff, bextra)
        return f.getvalue()

    def assert_corrupt(self, len_dst, controls, bdiff=b'', bextra=b''):
        p = self.make_patch(len_dst, controls, bdiff, bextra)
        with self.assertRaisesRegex(ValueError, "corrupt patch"):
            patch(b'', p)

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
