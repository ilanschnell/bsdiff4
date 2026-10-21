import base64
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


class TestEncode(unittest.TestCase):

    def test_special_values(self):
        N = (1 << 63) - 1
        for n, b in [
            (  -N, b'\xff\xff\xff\xff\xff\xff\xff\xff'),
            (-256, b'\x00\x01\x00\x00\x00\x00\x00\x80'),
            (-128, b'\x80\x00\x00\x00\x00\x00\x00\x80'),
            (  -1, b'\x01\x00\x00\x00\x00\x00\x00\x80'),
            (   0, b'\x00\x00\x00\x00\x00\x00\x00\x00'),
            (   1, b'\x01\x00\x00\x00\x00\x00\x00\x00'),
            ( 127, b'\x7f\x00\x00\x00\x00\x00\x00\x00'),
            ( 128, b'\x80\x00\x00\x00\x00\x00\x00\x00'),
            ( 129, b'\x81\x00\x00\x00\x00\x00\x00\x00'),
            ( 255, b'\xff\x00\x00\x00\x00\x00\x00\x00'),
            ( 256, b'\x00\x01\x00\x00\x00\x00\x00\x00'),
            ( 257, b'\x01\x01\x00\x00\x00\x00\x00\x00'),
            (   N, b'\xff\xff\xff\xff\xff\xff\xff\x7f'),
        ]:
            self.assertEqual(core.encode_int64(n), b)
            self.assertEqual(core.decode_int64(b), n)

        self.assertEqual(  # noncanonical "negative zero"
            core.decode_int64(b'\x00\x00\x00\x00\x00\x00\x00\x80'), 0)

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


class TestFormat(unittest.TestCase):

    def round_trip(self, src, dst):
        p = diff(src, dst)
        #print(len(src), len(p))
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

    def test_small(self): # issue #14
        src = b'123456789 987654321'
        dst = b'123456789000987654321'
        self.round_trip(src, dst)
        self.round_trip(dst, src)

    def test_diff_blocks(self):
        # Exercise both split_small() and partition_group().
        self.assertEqual(
            core.diff(b'banana', b'bandana'),
            ([(3, 4, 2)], 3 * b'\x00', b'dana'))

        src = 32 * b'a'
        dst = 16 * b'a' + b'b' + 16 * b'a'
        self.assertEqual(
            core.diff(src, dst),
            ([(32, 1, -1)], 16 * b'\x00' + b'\x01' + 15 * b'\x00', b'a'))

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
        for tcontrol in [(-1, 0, 0)], [(0, -1, 0)], [(5, 0, 0)], [(0, 5, 0)]:
            self.assertRaises(ValueError, core.patch,
                              b'abcd', 4, tcontrol, 4 * b'\x00', b'')

        self.assertRaises(ValueError, core.patch, b'', -1, [], b'', b'')
        for control in [('x', 0, 0), (0, 'x', 0), (0, 0, 'x')]:
            self.assertRaises(TypeError, core.patch,
                              b'', 0, [control], b'', b'')
        for control in [None, (), (0, 0), (0, 0, 0, 0)]:
            self.assertRaises(TypeError, core.patch,
                              b'', 0, [control], b'', b'')

    def test_underflow(self):
        for args in [
            (b'', 1, [], b'', b''),
            (b'', 0, [], b'x', b''),
            (b'', 0, [], b'', b'x'),
        ]:
            self.assertRaises(ValueError, core.patch, *args)

    def test_oldpos_out_of_range(self):
        self.assertEqual(
            core.patch(b'ab', 2, [(0, 0, -1), (2, 0, 0)],
                       b'\x01\x01', b''),
            b'\x01b')
        self.assertEqual(
            core.patch(b'ab', 2, [(0, 0, 2), (2, 0, 0)],
                       b'\x01\x02', b''),
            b'\x01\x02')

    def test_oldpos_overflow(self):
        M = 1 << 63
        for z in -M, M - 1:
            self.assertEqual(
                core.patch(b'', 0, [(0, 0, z)], b'', b''), b'')

        for controls in [[(0, 0, M - 1), (0, 0, 1)],
                         [(0, 0, -M), (0, 0, -1)]]:
            self.assertRaises(ValueError, core.patch,
                              b'', 0, controls, b'', b'')
        self.assertRaises(
            ValueError, core.patch, b'', 2,
            [(0, 0, M - 1), (2, 0, 0)], 2 * b'\x00', b'')

    def test_malformed_patch(self):
        def header(len_control, len_diff, len_dst):
            return (format.MAGIC + core.encode_int64(len_control) +
                    core.encode_int64(len_diff) + core.encode_int64(len_dst))

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
        format.write_patch(fi, 4, [(3, 1, 0)], 3 * b'\x00', b'!')
        fi.seek(0)
        len_control, len_diff, len_dst, controls = format.read_patch(
            fi, header_only=True)
        self.assertEqual((len_dst, controls), (4, [(3, 1, 0)]))
        self.assertEqual(fi.tell(), 32 + len_control)
        self.assertGreater(len_diff, 0)

    def test_compatibility(self):
        # BSDIFF40 patch from b'abc' to b'abd!', verified with bspatch.
        data = base64.b64decode(
            b'QlNESUZGNDAqAAAAAAAAACUAAAAAAAAABAAAAAAAAABCWmg5MUFZJlNZ0BSaKQAA'
            b'BMAAaAggADDNNBk/UglZPF3JFOFCQ0BSaKRCWmg5MUFZJlNZTFqfSAAAAEAAYAA'
            b'gACEAgoxdyRThQkExan0gQlpoOTFBWSZTWS0V6xwAAAAQACAAIAAhGEaC7kinCh'
            b'IFor1jgA==')
        self.assertEqual(patch(b'abc', data), b'abd!')


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
