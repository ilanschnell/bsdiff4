"""
Utility functions used by development scripts.
"""
import ast
from datetime import datetime
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
        alphabet += '!#$%&()*+,-./:;<=>?@[]^_{|}~'[:m - 62]
    if m > len(alphabet):
        raise ValueError("Cannot turn %d values into printable ASCII" % m)
    alphabet = bytes(sorted(alphabet.encode('utf-8')))
    table = bytes.maketrans(values, alphabet[:m])
    blocks = [data.translate(table) for data in blocks]
    return blocks[0] if len(blocks) == 1 else tuple(blocks)


def read_cases(path='output.txt'):
    "Return the (src, dst) pairs stored in a branch2 output file."
    with open(path) as f:
        tree = ast.parse(f.read(), path)

    pending_src = None

    for node in tree.body:
        if (not isinstance(node, ast.Assign) or
                len(node.targets) != 1 or
                not isinstance(node.targets[0], ast.Name)):
            raise ValueError("invalid branch2 output")

        name = node.targets[0].id
        value = ast.literal_eval(node.value)
        if not isinstance(value, bytes):
            raise ValueError("%s must be bytes" % name)

        if name == 'src' and pending_src is None:
            pending_src = value
        elif name == 'dst' and pending_src is not None:
            yield pending_src, value
            pending_src = None
        else:
            raise ValueError("expected alternating src and dst assignments")

    if pending_src is not None:
        raise ValueError("missing dst assignment")


def append_case(src, dst, path='output.txt'):
    record = (
        "# %s\n" % datetime.now().strftime('%Y-%m-%d %H:%M:%S') +
        "# %d %d (%d)\n" % (len(src), len(dst), len(set(src + dst))) +
        "src = %r\n" % src +
        "dst = %r\n\n" % dst
    )
    with open(path, 'a') as fo:
        fo.write(record)


def write_cases(cases, path='output.txt'):
    cases = list(cases)
    with open(path, 'w') as fo:
        for src, dst in cases:
            fo.write("# %d %d (%d)\n" % (len(src), len(dst),
                                         len(set(src + dst))))
            fo.write("src = %r\n" % src)
            fo.write("dst = %r\n\n" % dst)

# ------------------------------- tests -----------------------------------

import random
import shutil
import unittest
import tempfile
from os.path import join


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
            values = random.sample(range(256), m)
            self.assertEqual(len(values), m)
            values.extend(random.choices(values, k=n - m))
            random.shuffle(values)
            data = bytes(values)
            self.assertEqual(len(set(data)), m)
            self.assertEqual(len(data), n)

            alpha_data = alphabetize(data)
            # check ordering of alphabetized data
            self.assertEqual(sorted(range(n), key=lambda i: alpha_data[i]),
                             sorted(range(n), key=lambda i: data[i]))
            # idempotency
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


class TestFileCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def path(self):
        return join(self.tmpdir, 'cases.txt')

    def test_round_trip(self):
        path = self.path()
        cases = [(b"abcde", b"bdc"), (b"cccc", b"ddabcc")]
        write_cases(cases, self.path())
        # actual round trip
        write_cases(read_cases(path), path)
        self.assertEqual(list(read_cases(path)), cases)

    def test_append(self):
        cases = [(b"A", b"B"), (b"C", b"D")]
        write_cases(cases, self.path())
        self.assertEqual(list(read_cases(self.path())), cases)
        append_case(b"E", b"F", self.path())
        self.assertEqual(list(read_cases(self.path())),
                         cases + [(b"E", b"F")])

    def test_read(self):
        with open(self.path(), 'w') as fo:
            fo.write('src = b"A"\ndst = b"B"\n')
            fo.write("src = b'\\x58'\ndst = b'\\x59'\n")
            fo.write("src=b'v'\ndst=b'w'")
        self.assertEqual(list(read_cases(self.path())),
                         [(b'A', b'B'), (b'X', b'Y'), (b'v', b'w')])

    def test_read_errors(self):
        for line, msg in [
            ("src = 'aa'", "src must be bytes"),
            ("src = b'a'", "missing dst assignment"),
            ("dst = b'a'", "expected alternating src and dst assignments"),
            ("src, dst = b'A', b'B'", "invalid branch2 output"),
            ("b'abcdefg'", "invalid branch2 output"),
            ("src = dst = b'A'", "invalid branch2 output"),
        ]:
            with open(self.path(), 'w') as fo:
                fo.write(line + "\n")
            self.assertRaisesRegex(ValueError, msg,
                                   list, read_cases(self.path()))

        for data, error in [
            ("src = 2a\n", SyntaxError),
            ("  src = b'c'\n", IndentationError),
            ("src = bytes(b'a')\n", ValueError),
            ("xxx = b'a'\n", ValueError),
        ]:
            with open(self.path(), 'w') as fo:
                fo.write(data)
            self.assertRaises(error, list, read_cases(self.path()))


if __name__ == '__main__':
    unittest.main()
