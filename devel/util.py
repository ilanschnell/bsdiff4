"""
Utility functions used by development scripts.
"""
from string import ascii_lowercase, ascii_uppercase, digits


def alphabetize(*blocks):
    "Map byte values to printable ASCII while preserving their order."
    values = bytes(sorted(set(b''.join(blocks))))
    m = len(values)
    alphabet = ascii_lowercase
    if m > 26:
        alphabet += ascii_uppercase
    if m > 52:
        alphabet += digits
    if m > 62:
        alphabet += '!#$%&()*+,-./:;<=>?@[]^_{|}~'
    if m > len(alphabet):
        raise ValueError("Cannot turn %d values into printable ASCII" % m)
    alphabet = bytes(sorted(alphabet.encode('utf-8')))
    table = bytes.maketrans(values, alphabet[:m])
    blocks = [data.translate(table) for data in blocks]
    return blocks[0] if len(blocks) == 1 else tuple(blocks)


# ------------------------------- tests -----------------------------------

import random
import unittest


class TestAlphabetize(unittest.TestCase):

    def test_examples(self):
        for data, alphabetized in [
                (b'', b''),
                (bytes(range(5)), b'abcde'),
                (b"DK1KO",        b"bcacd"),
                (b"mississippi",  b"baddaddacca"),
                (b"MISSISSIPPI",  b"baddaddacca"),
        ]:
            self.assertEqual(alphabetize(data), alphabetized)

        self.assertEqual(alphabetize(b"Hong", b"Kong"), (b"aedc", b"bedc"))

    def test_range(self):
        n = 100  # data size
        for m in range(1, 91):  # alphabet size
            chars = random.sample(range(256), m)
            self.assertEqual(len(chars), m)
            values = chars + random.choices(chars, k=n - m)
            random.shuffle(values)
            data = bytes(values)
            self.assertEqual(len(set(data)), m)
            self.assertEqual(len(data), n)

            alpha_data = alphabetize(data)
            # check ordering of alphabetized data
            self.assertEqual(sorted(range(n), key=lambda i: alpha_data[i]),
                             sorted(range(n), key=lambda i: data[i]))

            self.assertEqual(alphabetize(alpha_data), alpha_data)

    def test_blocks(self):
        self.assertEqual(alphabetize(), ())
        A = b'\x00\x07'
        B = b'\x02\x07\x05'
        self.assertEqual(alphabetize(A, B), (b'ad', b'bdc'))
        C = b'\x06'
        self.assertEqual(alphabetize(A, B, C), (b'ae', b'bec', b'd'))
        self.assertEqual(alphabetize(A, B, b''), (b'ad', b'bdc', b''))

    def test_errors(self):
        self.assertRaises(ValueError, alphabetize, bytes(range(91)))


if __name__ == '__main__':
    unittest.main()
