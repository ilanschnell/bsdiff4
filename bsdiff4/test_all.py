from __future__ import absolute_import

import os
import sys
import random
import shutil
import unittest
import tempfile

import bsdiff4.core as core
import bsdiff4.format as format
from bsdiff4 import diff, patch, file_diff, file_patch, file_patch_inplace


N = 2 ** 63 - 1


class TestEncode(unittest.TestCase):

    def test_special_values(self):
        for n, b in [
            (-N, b'\xff\xff\xff\xff\xff\xff\xff\xff'),
            (-256, b'\x00\x01\x00\x00\x00\x00\x00\x80'),
            (-128, b'\x80\x00\x00\x00\x00\x00\x00\x80'),
            (-1, b'\x01\x00\x00\x00\x00\x00\x00\x80'),
            (0, b'\x00\x00\x00\x00\x00\x00\x00\x00'),
            (1, b'\x01\x00\x00\x00\x00\x00\x00\x00'),
            (127, b'\x7f\x00\x00\x00\x00\x00\x00\x00'),
            (128, b'\x80\x00\x00\x00\x00\x00\x00\x00'),
            (129, b'\x81\x00\x00\x00\x00\x00\x00\x00'),
            (255, b'\xff\x00\x00\x00\x00\x00\x00\x00'),
            (256, b'\x00\x01\x00\x00\x00\x00\x00\x00'),
            (257, b'\x01\x01\x00\x00\x00\x00\x00\x00'),
            (N, b'\xff\xff\xff\xff\xff\xff\xff\x7f'),
            ]:
            self.assertEqual(core.encode_int64(n), b)
            self.assertEqual(core.decode_int64(b), n)

    def test_errors(self):
        self.assertRaises(TypeError, core.encode_int64, 'x')
        self.assertRaises(TypeError, core.decode_int64, 12345)
        self.assertRaises(ValueError, core.decode_int64, 7 * b'a')
        self.assertRaises(ValueError, core.decode_int64, 9 * b'b')

    def test_random(self):
        for dum in range(1000):
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

    suite = unittest.TestSuite()
    for cls in [TestEncode, TestFormat, TestFile]:
        suite.addTest(unittest.makeSuite(cls))
    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


if __name__ == '__main__':
    unittest.main()
