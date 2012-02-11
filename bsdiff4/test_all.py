import os
import sys
import random
import unittest

import bsdiff4.core as core
import bsdiff4.format as format


def to_bytes(s):
    if sys.version_info[0] >= 3:
        return bytes(s.encode('latin1'))
    elif sys.version_info[:2] >= (2, 6):
        return bytes(s)
    else:
        return s

N = 2 ** 63 - 1


def random_bytes(n):
    return os.urandom(n)


class TestEncode(unittest.TestCase):

    def test_special_values(self):
        for n, s in [
            (-N, '\xff\xff\xff\xff\xff\xff\xff\xff'),
            (-256, '\x00\x01\x00\x00\x00\x00\x00\x80'),
            (-128, '\x80\x00\x00\x00\x00\x00\x00\x80'),
            (-1, '\x01\x00\x00\x00\x00\x00\x00\x80'),
            (0, '\x00\x00\x00\x00\x00\x00\x00\x00'),
            (1, '\x01\x00\x00\x00\x00\x00\x00\x00'),
            (127, '\x7f\x00\x00\x00\x00\x00\x00\x00'),
            (128, '\x80\x00\x00\x00\x00\x00\x00\x00'),
            (129, '\x81\x00\x00\x00\x00\x00\x00\x00'),
            (255, '\xff\x00\x00\x00\x00\x00\x00\x00'),
            (256, '\x00\x01\x00\x00\x00\x00\x00\x00'),
            (257, '\x01\x01\x00\x00\x00\x00\x00\x00'),
            (N, '\xff\xff\xff\xff\xff\xff\xff\x7f'),
            ]:
            b = to_bytes(s)
            self.assertEqual(core.encode_int64(n), b)
            self.assertEqual(core.decode_int64(b), n)

    def test_errors(self):
        self.assertRaises(TypeError, core.encode_int64, 'x')
        self.assertRaises(TypeError, core.decode_int64, 12345)
        self.assertRaises(ValueError, core.decode_int64, to_bytes(7 * 'a'))
        self.assertRaises(ValueError, core.decode_int64, to_bytes(9 * 'b'))

    def test_random(self):
        for dum in range(1000):
            n = random.randint(-N, N)
            b = core.encode_int64(n)
            self.assertEqual(len(b), 8)
            self.assertEqual(core.decode_int64(b), n)


class TestFormat(unittest.TestCase):

    def round_trip(self, src, dst):
        patch = format.diff(src, dst)
        #print(len(src), len(patch))
        dst2 = format.patch(src, patch)
        self.assertEqual(dst, dst2)

    def test_zero(self):
        self.round_trip(to_bytes(''), to_bytes(''))

    def test_extra(self):
        src = random_bytes(1000)
        dst = src + random_bytes(10)
        self.round_trip(src, dst)
        self.round_trip(dst, src)

    def test_random(self):
        self.round_trip(random_bytes(2000), random_bytes(2000))

    def test_large(self):
        a = random_bytes(50000)
        b = random_bytes(40000)
        src = a + random_bytes(100) + b
        dst = a + random_bytes(100) + b
        self.round_trip(src, dst)


def run(verbosity=1):
    from . import __version__
    print('bsdiff4 is installed in: ' + os.path.dirname(__file__))
    print('bsdiff4 version: ' + __version__)

    suite = unittest.TestSuite()
    for cls in [TestEncode, TestFormat]:
        suite.addTest(unittest.makeSuite(cls))
    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


if __name__ == '__main__':
    unittest.main()
