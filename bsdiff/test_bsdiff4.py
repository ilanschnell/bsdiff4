import random
import unittest

import bsdiff4


def gen_random_bytes(size):
    return ''.join(chr(random.randint(0, 255)) for i in xrange(size))


class TestBSDiff4(unittest.TestCase):

    def round_trip(self, src, dst):
        patch = bsdiff4.diff(src, dst)
        #if self.verbose:
        print len(src), len(patch)
        dst2 = bsdiff4.patch(src, patch)
        self.assertEqual(dst, dst2)

    def test_extra(self):
        src = gen_random_bytes(1000)
        dst = src + 'extra'
        self.round_trip(src, dst)

    def test_random(self):
        self.round_trip(gen_random_bytes(2000), gen_random_bytes(2000))

    def test_large(self):
        a = gen_random_bytes(50000)
        b = gen_random_bytes(40000)
        src = a + gen_random_bytes(100) + b
        dst = a = gen_random_bytes(100) + b
        self.round_trip(src, dst)


if __name__ == '__main__':
    unittest.main()
