import bz2
import os
import sys
import random
import shutil
import unittest
import tempfile
from io import BytesIO

import bsdiff4.core as core
import bsdiff4.format as format
from bsdiff4 import diff, patch, file_diff, file_patch, file_patch_inplace


UNDER_QEMU = os.environ.get('UNDER_QEMU') == '1'


class TestEncode(unittest.TestCase):

    def test_special_values(self):
        N = (1 << 63) - 1
        for n, hexstr in [
            (  -N, 'ff ff ff ff ff ff ff ff'),
            (-256, '00 01 00 00 00 00 00 80'),
            (-128, '80 00 00 00 00 00 00 80'),
            (  -1, '01 00 00 00 00 00 00 80'),
            (   0, '00 00 00 00 00 00 00 00'),
            (   1, '01 00 00 00 00 00 00 00'),
            ( 127, '7f 00 00 00 00 00 00 00'),
            ( 128, '80 00 00 00 00 00 00 00'),
            ( 129, '81 00 00 00 00 00 00 00'),
            ( 255, 'ff 00 00 00 00 00 00 00'),
            ( 256, '00 01 00 00 00 00 00 00'),
            ( 257, '01 01 00 00 00 00 00 00'),
            (   N, 'ff ff ff ff ff ff ff 7f'),
        ]:
            b = bytes.fromhex(hexstr)
            self.assertEqual(core.encode_int64(n), b)
            self.assertEqual(core.decode_int64(b), n)

        self.assertEqual(  # noncanonical "negative zero"
            core.decode_int64(bytes.fromhex('00 00 00 00 00 00 00 80')), 0)

    def test_errors(self):
        self.assertRaises(TypeError, core.encode_int64, 'x')
        M = 1 << 63
        for n in -M -1, -M, M, M + 1:
            self.assertRaises(OverflowError, core.encode_int64, n)

        self.assertRaises(TypeError, core.decode_int64, 12345)
        self.assertRaises(ValueError, core.decode_int64, 7 * b'a')
        self.assertRaises(ValueError, core.decode_int64, 9 * b'b')

    def test_random(self):
        N = (1 << 63) - 1
        for _ in range(1000):
            n = random.randint(-N, N)
            b = core.encode_int64(n)
            self.assertEqual(len(b), 8)
            self.assertEqual(core.decode_int64(b), n)


def control_block(*controls):
    return b''.join(core.encode_int64(x) for control in controls
                    for x in control)


def header(len_control, len_diff, len_dst):
    return (format.MAGIC +
            core.encode_int64(len_control) +
            core.encode_int64(len_diff) +
            core.encode_int64(len_dst))


class TestHelpers(unittest.TestCase):

    def test_control_block(self):
        self.assertEqual(control_block((0, 0, -1), (2, 0, 0)),
                         bytes.fromhex("""
                         0000000000000000 0000000000000000 0100000000000080
                         0200000000000000 0000000000000000 0000000000000000
                         """))

    def test_header(self):
        self.assertEqual(header(0x2c9, 0x7a2, 0x20fc0),
                         b'BSDIFF40' + bytes.fromhex("""
                         c9 02 00 00 00 00 00 00
                         a2 07 00 00 00 00 00 00
                         c0 0f 02 00 00 00 00 00 """))


class TestFormat(unittest.TestCase):

    @unittest.skipIf(UNDER_QEMU, "slow under QEMU")
    def test_example(self):
        a = 100_000 * b'a'
        b = bytearray(a)
        b[100:106] = b' diff '
        p = diff(a, bytes(b))
        self.assertEqual(patch(a, p), b)

    def round_trip(self, src, dst):
        p = diff(src, dst)
        dst2 = patch(src, p)
        self.assertEqual(dst, dst2)

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

    def test_small(self):  # issue #14
        src = b'123456789 987654321'
        dst = b'123456789000987654321'
        self.round_trip(src, dst)
        self.round_trip(dst, src)

    def test_diff_blocks(self):
        # Exercise both split_small() and partition_group().
        self.assertEqual(
            core.diff(b'banana', b'bandana'),
            (control_block((3, 4, 2)), 3 * b'\x00', b'dana'))

        src = 32 * b'a'
        dst = 16 * b'a' + b'b' + 16 * b'a'
        self.assertEqual(
            core.diff(src, dst),
            (control_block((32, 1, -1)),
             16 * b'\x00' + b'\x01' + 15 * b'\x00', b'a'))

        src = 100 * b'a' + 100 * b'b'
        dst = 100 * b'b' + 100 * b'a'
        self.assertEqual(
            core.diff(src, dst),
            (control_block((0, 100, 0), (100, 0, -100)),
             100 * b'\x00', 100 * b'b'))

    def test_random(self):
        for _ in range(100):
            n1 = random.randint(0, 1000)
            n2 = random.randint(0, 1000)
            self.round_trip(os.urandom(n1), os.urandom(n2))

    def test_large(self):
        a = os.urandom(50000)
        b = os.urandom(40000)
        src = a + os.urandom(100) + b
        dst = a + os.urandom(100) + b
        self.round_trip(src, dst)

    def test_corrupt(self):
        for bcontrol in [control_block((-1, 0, 0)),
                         control_block((0, -1, 0)),
                         control_block((5, 0, 0)),
                         control_block((0, 5, 0))]:
            self.assertRaises(ValueError, core.patch,
                              b'abcd', 4, bcontrol, 4 * b'\x00', b'')

        self.assertRaises(ValueError, core.patch, b'', -1, b'', b'', b'')
        self.assertRaises(TypeError, core.patch, b'', 0, [], b'', b'')
        self.assertRaises(ValueError, core.patch, b'', 0, b'A', b'', b'')

    def test_underflow(self):
        for args in [
            (b'', 1, b'', b'', b''),
            (b'', 0, b'', b'x', b''),
            (b'', 0, b'', b'', b'x'),
        ]:
            self.assertRaises(ValueError, core.patch, *args)

    def test_oldpos_out_of_range(self):
        bcontrol = control_block((0, 0, -1), (2, 0, 0))
        self.assertEqual(
            core.patch(b'ab', 2, bcontrol, b'\x01\x01', b''), b'\x01b')

        bcontrol = control_block((0, 0, 2), (2, 0, 0))
        self.assertEqual(
            core.patch(b'ab', 2, bcontrol, b'\x01\x02', b''), b'\x01\x02')

    def test_oldpos_overflow(self):
        M = 1 << 63
        for z in -M + 1, M - 1:
            self.assertEqual(
                core.patch(b'', 0, control_block((0, 0, z)), b'', b''), b'')

        for controls in [[(0, 0, M - 1), (0, 0, 1)],
                         [(0, 0, -M + 1), (0, 0, -1), (0, 0, -1)]]:
            bcontrol = control_block(*controls)
            self.assertRaises(ValueError, core.patch,
                              b'', 0, bcontrol, b'', b'')
        bcontrol = control_block((0, 0, M - 1), (2, 0, 0))
        self.assertRaises(
            ValueError, core.patch, b'', 2, bcontrol, 2 * b'\x00', b'')

    def test_malformed_patch(self):
        empty = bz2.compress(b'')
        self.assertRaises(ValueError, format.read_patch,
                          BytesIO(format.MAGIC))

        for lengths in [(-1, 0, 0), (0, -1, 0), (0, 0, -1)]:
            data = header(*lengths) + 3 * empty
            self.assertRaises(ValueError, format.read_patch, BytesIO(data))

        invalid_blocks = [
            header(1, len(empty), 0) + b'x' + empty + empty,
            header(len(empty), 1, 0) + empty + b'x' + empty,
            header(len(empty), len(empty), 0) + empty + empty + b'x',
        ]
        for data in invalid_blocks:
            self.assertRaises(OSError, format.read_patch, BytesIO(data))

        control = bz2.compress(b'\x00')
        data = header(len(control), len(empty), 0) + control + 2 * empty
        self.assertRaises(ValueError, format.read_patch, BytesIO(data))

        for data in [
            header(len(empty) + 1, 0, 0) + empty,
            header(len(empty), len(empty) + 1, 0) + 2 * empty,
        ]:
            self.assertRaises(ValueError, format.read_patch, BytesIO(data))

    def test_header_only(self):
        fi = BytesIO()
        format.write_patch(fi, 4, control_block((3, 1, 0)),
                           3 * b'\x00', b'!')
        fi.seek(0)
        len_control, len_diff, len_dst, bcontrol = format.read_patch(
            fi, header_only=True)
        self.assertEqual((len_dst, bcontrol),
                         (4, control_block((3, 1, 0))))
        self.assertEqual(fi.tell(), 32 + len_control)
        self.assertGreater(len_diff, 0)

    # BSDIFF40 patch from b'abc' to b'abd!', verified with bspatch.
    # 42 5a 68 39 = BZh9
    data = bytes.fromhex("""
    42534449 46463430 2a000000 00000000 25000000 00000000 04000000 00000000
    425a6839 31415926 5359d014 9a290000 04c00068 08200030 cd34193f 5209593c
    5dc914e1 42434052 68a4425a 68393141 59265359 4c5a9f48 00000040 00600020
    00210082 8c5dc914 e1424131 6a7d2042 5a683931 41592653 592d15eb 1c000000
    10002000 20002118 4682ee48 a70a1205 a2bd6380
    """)

    def test_compatibility(self):
        self.assertEqual(patch(b'abc', self.data), b'abd!')

    def test_truncated_patch(self):
        for i in range(len(self.data)):
            # truncating patch
            self.assertRaises(ValueError, patch, b'abc', self.data[:i])

    @unittest.skipIf(UNDER_QEMU, "slow under QEMU")
    def test_mutated_patch(self):
        data = self.data
        for i in range(len(data)):
            mut = bytearray(data)
            for j in range(8):
                # mutate j-th bit in i-th byte
                mut[i] = data[i] ^ (1 << j)
                try:
                    dst = patch(b'abc', bytes(mut))
                except (ValueError, MemoryError, OSError):
                    continue
                # mutation could theoretically produce another valid patch
                self.assertEqual(dst, b'abd!')

    def test_adjust_overlap(self):
        # Ensure that an overlapping byte is assigned to the better
        # matching block.
        src = b'ccccdabcadcb'
        dst = b'ccccdcdabcadcb'
        self.assertEqual(
            core.diff(src, dst),
            (control_block((5, 0, -2), (9, 0, -9)), 14 * b'\0', b''))


class TestSuffixArray(unittest.TestCase):

    def test_basic(self):
        SA = core.suffix_array
        self.assertEqual(SA(b''), [0])
        self.assertEqual(SA(b'banana'), [6, 5, 3, 1, 0, 4, 2])

    def check_data(self, data):
        self.assertEqual(
            core.suffix_array(data),
            sorted(range(len(data) + 1), key=lambda i: data[i:]))

    def test_two_element_group(self):
        # A two-element group must not be mistaken for a singleton.
        self.check_data(b'CCBBCCCACCCCBCACBCCCCC')

    def test_random(self):
        # randomized comparison
        self.check_data(os.urandom(1000))


class TestFile(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def path(self, fn):
        return os.path.join(self.tmpdir, fn)

    def assert_same_file_content(self, fn1, fn2):
        data1 = format.read_data(self.path(fn1))
        data2 = format.read_data(self.path(fn2))
        self.assertEqual(data1, data2)

    def round_trip(self):
        # write file 'patch'
        file_diff(self.path('src'), self.path('dst'), self.path('patch'))
        # write file 'dst2'
        file_patch(self.path('src'), self.path('dst2'), self.path('patch'))
        # compare files 'dst' and 'dst2'
        self.assert_same_file_content('dst', 'dst2')
        # patch 'src' in place
        file_patch(self.path('src'), self.path('src'), self.path('patch'))
        self.assert_same_file_content('src', 'dst')

    def write_data(self, fn, data):
        with open(self.path(fn), 'wb') as fo:
            fo.write(data)

    def test_wrong_header(self):
        path = self.path('foo')
        self.write_data(path, b"WRONG_HEADER")
        with open(path, "rb") as fi:
            self.assertRaises(ValueError, format.read_patch, fi)

    def test_1(self):
        a = 1000 * b'ABCDE'
        b = 1000 * b'XYZ'
        self.write_data('src', a + os.urandom(100) + b)
        self.write_data('dst', a + os.urandom(100) + b)
        self.round_trip()

    def test_2(self):
        a = 10000 * b'ABCDEFG'
        self.write_data('src', a)
        self.write_data('dst', a + b'extra bytes at the end')
        self.round_trip()

    def test_inplace(self):
        a = 1000 * b'ABCDE'
        b = 1000 * b'XYZ'
        self.write_data('src', a + os.urandom(100) + b)
        self.write_data('dst', a + os.urandom(100) + b)
        file_diff(self.path('src'), self.path('dst'), self.path('patch'))
        file_patch_inplace(self.path('src'), self.path('patch'))
        self.assert_same_file_content('src', 'dst')


def run(verbosity=1):
    from . import __version__
    print('Python version: %s' % sys.version)
    print('bsdiff4 is installed in: %s' % os.path.dirname(__file__))
    print('bsdiff4 version: %s' % __version__)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(sys.modules[__name__]))
    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


if __name__ == '__main__':
    unittest.main()
