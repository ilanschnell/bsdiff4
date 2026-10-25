"""
Additional tests and verifications for suffix_array() which are neither
part of the regular test suite nor part of any bsdiff4 distributions.
"""
import os
import random
import unittest
from itertools import pairwise

from bsdiff4.core import suffix_array


N_SMALL = 500
N_LARGE = 1_000_000


class TestSuffixArray(unittest.TestCase):

    def check_data(self, data):
        n = len(data)
        sa = suffix_array(data)
        self.assertEqual(len(sa), n + 1)
        self.assertEqual(sorted(sa), list(range(n + 1)))
        # test against naive Python implementation
        self.assertEqual(sa,
                         sorted(range(n + 1), key=lambda i: data[i:]))
        # empty suffix is always first
        self.assertEqual(sa[0], n)
        # verify that every suffix is lexicographically smaller than
        # the suffix following it
        self.assertTrue(all(data[i:] < data[j:] for i, j in pairwise(sa)))

    def test_uniform(self):
        for n in range(N_SMALL):
            self.check_data(n * b'\x00')

    def test_small_alphabets(self):
        for alphabet_size in range(1, 257):
            data = bytes(random.randrange(alphabet_size)
                         for _ in range(N_SMALL))
            self.check_data(data)

    def test_random(self):
        for n in range(N_SMALL):
            self.check_data(os.urandom(n))

    def test_large_uniform(self):
        n = N_LARGE
        data = n * b'A'
        self.assertEqual(suffix_array(data), list(range(n, -1, -1)))

    def test_large_random(self):
        n = N_LARGE
        data = os.urandom(n)
        sa = suffix_array(data)

        self.assertEqual(len(sa), n + 1)
        # Map each suffix position to its rank in the suffix array.
        rank = [-1] * (n + 1)
        for r, pos in enumerate(sa):
            self.assertTrue(0 <= pos <= n)
            self.assertEqual(rank[pos], -1)
            rank[pos] = r

        self.assertEqual(sa[0], n)
        for i, j in pairwise(sa[1:]):
            self.assertLess((data[i], rank[i + 1]),
                            (data[j], rank[j + 1]))


if __name__ == '__main__':
    unittest.main()
