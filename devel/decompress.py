import bz2


def decompress(data, limit=None):
    "Decompress one or more bzip2 streams, optionally limiting output."
    if limit is None:
        return bz2.decompress(data)
    if limit < 0:
        raise ValueError("negative decompression limit")

    chunks = []
    size = 0
    while data:
        decompressor = bz2.BZ2Decompressor()
        try:
            chunk = decompressor.decompress(data, limit - size + 1)
        except OSError:
            # Like bz2.decompress(), ignore trailing non-bzip2 data after
            # at least one complete stream.
            if chunks:
                break
            raise OSError("invalid bzip2 data") from None
        chunks.append(chunk)
        size += len(chunk)
        if size > limit:
            raise ValueError("decompressed data exceeds limit")
        if not decompressor.eof:
            raise ValueError("Compressed data ended before end-of-stream "
                             "marker was reached")
        data = decompressor.unused_data

    return b''.join(chunks)

# ------------------------------- tests -----------------------------------

import unittest


EMPTY = bz2.compress(b'')  # compressed empty block

class TestDecompress(unittest.TestCase):

    def test_streams(self):
        streams = bz2.compress(b'abc') + bz2.compress(b'defg')
        self.assertEqual(decompress(streams), b'abcdefg')
        self.assertEqual(decompress(streams, 7), b'abcdefg')
        self.assertEqual(decompress(streams, 8), b'abcdefg')
        self.assertRaisesRegex(ValueError, "exceeds limit",
                               decompress, streams, 6)

    def test_empty(self):
        self.assertEqual(decompress(b'', 0), b'')
        self.assertEqual(decompress(EMPTY, 0), b'')

    def test_errors(self):
        self.assertRaisesRegex(ValueError, "negative decompression limit",
                               decompress, EMPTY, -1)
        self.assertRaisesRegex(OSError, "invalid bzip2 data",
                               decompress, b'invalid', 10)
        self.assertRaises(ValueError, decompress, bz2.compress(b'abc')[:-1],
                          10)

    def test_trailing_data(self):
        data = bz2.compress(b'abc') + b'trailing data'
        self.assertEqual(decompress(data, 3), b'abc')


if __name__ == '__main__':
    unittest.main()
