import random
import unittest

import core
import format


N = 2 ** 63 - 1


def gen_random_bytes(size):
    return ''.join(chr(random.randint(0, 255)) for i in xrange(size))


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
            self.assertEqual(core.encode_int64(n), s)
            self.assertEqual(core.decode_int64(s), n)

    def test_random(self):
        for dum in xrange(10000):
            x = random.randint(-N, N)
            s = core.encode_int64(x)
            self.assertEqual(len(s), 8)
            self.assertEqual(core.decode_int64(s), x)


class TestFormat(unittest.TestCase):

    def round_trip(self, src, dst):
        patch = format.diff(src, dst)
        #print len(src), len(patch)
        dst2 = format.patch(src, patch)
        self.assertEqual(dst, dst2)

    def test_zero(self):
        self.round_trip('', '')

    def test_extra(self):
        src = gen_random_bytes(1000)
        dst = src + gen_random_bytes(10)
        self.round_trip(src, dst)
        self.round_trip(dst, src)

    def test_random(self):
        self.round_trip(gen_random_bytes(2000), gen_random_bytes(2000))

    def test_large(self):
        a = gen_random_bytes(50000)
        b = gen_random_bytes(40000)
        src = a + gen_random_bytes(100) + b
        dst = a = gen_random_bytes(100) + b
        self.round_trip(src, dst)


def run(verbosity):
    suite = unittest.TestSuite()
    for cls in [TestEncode, TestFormat]:
        suite.addTest(unittest.makeSuite(cls))
    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


if __name__ == '__main__':
    unittest.main()
