"""
Additional tests and verifications for suffix_array() which are neither
part of the regular test suite nor part of any bsdiff4 distributions.
"""
import os
import random
import unittest

from bsdiff4.core import suffix_array


N = 500


class TestSuffixArray(unittest.TestCase):

    def check_data(self, data):
        n = len(data)
        SA = suffix_array(data)
        self.assertEqual(len(SA), n + 1)
        self.assertEqual(sorted(SA), list(range(n + 1)))
        # test against naive Python implementation
        self.assertEqual(SA,
                         sorted(range(n + 1), key=lambda i: data[i:]))
        # empty suffix is always first
        self.assertEqual(SA[0], n)
        # verify that every suffix is lexicographically smaller than
        # the suffix following it
        self.assertTrue(all(data[i:] < data[j:] for i, j in zip(SA, SA[1:])))

    def test_uniform(self):
        for n in range(N):
            self.check_data(n * b'\x00')

    def test_small_alphabet(self):
        for alphabet_size in range(1, 257):
            data = bytes(random.randrange(alphabet_size) for _ in range(N))
            self.check_data(data)

    def test_random(self):
        for n in range(N):
            self.check_data(os.urandom(n))


if __name__ == '__main__':
    unittest.main()
