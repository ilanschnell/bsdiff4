import bz2
import os
import sys
import random
import shutil
import unittest
import tempfile
from io import BytesIO
from os.path import exists, samefile
from sysconfig import get_config_var
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import bsdiff4.core as core  # type: ignore
from bsdiff4.format import (pack_header, unpack_header,
                            pack_control_block, unpack_control_block,
                            write_patch, read_patch)
from bsdiff4 import diff, patch, file_diff, file_patch, file_patch_inplace


UNDER_QEMU = os.environ.get('UNDER_QEMU') == '1'
GIL_DISABLED = get_config_var("Py_GIL_DISABLED") in (1, "1")

# ---------------------------- core layer --------------------------------

class TestCoreInt64(unittest.TestCase):

    def test_special_values(self):
        N = (1 << 63) - 1
        for n, hexstr in [
            (  -N, 'ff ff ff ff ff ff ff ff'),
            (-256, '00 01 00 00 00 00 00 80'),
            (-128, '80 00 00 00 00 00 00 80'),
            (  -1, '01 00 00 00 00 00 00 80'),
            (   0, '00 00 00 00 00 00 00 00'),
            (   1, '01 00 00 00 00 00 00 00'),
            ( 127, '7f 00 00 00 00 00 00 00'),
            ( 128, '80 00 00 00 00 00 00 00'),
            ( 129, '81 00 00 00 00 00 00 00'),
            ( 255, 'ff 00 00 00 00 00 00 00'),
            ( 256, '00 01 00 00 00 00 00 00'),
            ( 257, '01 01 00 00 00 00 00 00'),
            (   N, 'ff ff ff ff ff ff ff 7f'),
        ]:
            b = bytes.fromhex(hexstr)
            self.assertEqual(core.encode_int64(n), b)
            self.assertEqual(core.decode_int64(b), n)

        self.assertEqual(  # noncanonical "negative zero"
            core.decode_int64(bytes.fromhex('00 00 00 00 00 00 00 80')), 0)

    def test_errors(self):
        self.assertRaises(TypeError, core.encode_int64, 8 * b'\x00')
        M = 1 << 63
        for n in -M -1, -M, M, M + 1:
            self.assertRaises(OverflowError, core.encode_int64, n)

        self.assertRaises(TypeError, core.decode_int64, 0)
        for n in 0, 1, 7, 9, 16:
            self.assertRaisesRegex(ValueError, "8 bytes expected",
                                   core.decode_int64, n * b'\x00')

    def test_random(self):
        N = (1 << 63) - 1
        for _ in range(1000):
            n = random.randint(-N, N)
            b = core.encode_int64(n)
            self.assertEqual(len(b), 8)
            self.assertEqual(core.decode_int64(b), n)


class TestSuffixArray(unittest.TestCase):

    def test_basic(self):
        SA = core.suffix_array
        self.assertEqual(SA(b''), [0])
        self.assertEqual(SA(b'banana'), [6, 5, 3, 1, 0, 4, 2])

    def test_equal_bytes(self):
        n = 10_000
        self.assertEqual(core.suffix_array(n * b'a'),
                         list(range(n, -1, -1)))

    def check_data(self, data):
        self.assertEqual(
            core.suffix_array(data),
            sorted(range(len(data) + 1), key=lambda i: data[i:]))

    def test_repeated_groups(self):
        self.check_data(32 * b'a')
        self.check_data(100 * b'a' + 100 * b'b')

    def test_two_element_group(self):
        # A two-element group must not be mistaken for a singleton.
        self.check_data(b'CCBBCCCACCCCBCACBCCCCC')

    def test_random(self):
        # randomized comparison
        self.check_data(os.urandom(1000))


RND_200 = os.urandom(200)

ROUND_TRIP_CASES = [
    (b'', b''),
    (b'', b'x'),
    (b'abc', b'abc'),
    (b'abc', b'abx'),
    (b'abc', b'axc'),
    (b'abc', b'abxy'),
    (b'abc', b'xbc'),
    (b'abc', b'xybc'),
    (b'ccccdabcadcb', b'ccccdcdabcadcb'),
    (b'123456789 987654321', b'123456789000987654321'),  # issue #14
    # These inputs cause control tuples to be merged during diff generation.
    (b'ababababcdababababc', b'&ababababcdabababab'),
    (b'aaaaaaaaaaaaaaaaaaaabxtrabytes',
     b'ccaaaaaaaaaaaaaaaaaabexbytesbextrabytes'),
    # swap repeated blocks
    (50 * b'a' + 50 * b'b', 50 * b'b' + 50 * b'a'),
    # swap random blocks
    (RND_200, RND_200[100:] + RND_200[:100]),
    (b'', RND_200),
    (RND_200, RND_200),
    (RND_200, os.urandom(20) + RND_200),
    (RND_200, RND_200 + os.urandom(20)),
    # Three bytes in the middle replaced.
    (RND_200, RND_200[:98] + os.urandom(3) + RND_200[101:]),
    # 10 bytes replaced by 15 new bytes
    (RND_200, RND_200[:95] + os.urandom(15) + RND_200[105:]),
]

BYTES_CASES = [b'', b'a', b'abc', 100 * b'a', RND_200]


class TestCoreDiffPatch(unittest.TestCase):

    def assert_canonical(self, control_block, src_len):
        controls = list(unpack_control_block(control_block))
        src_pos = 0
        for i, (x, y, z) in enumerate(controls):
            # Source position is always in the source range.
            self.assertTrue(0 <= src_pos <= src_len)
            # Generated patches never reference negative or overlong
            # source ranges.
            self.assertTrue(0 <= x <= src_len - src_pos)
            self.assertGreaterEqual(y, 0)
            # No-op tuples are not present.
            self.assertTrue(x or y or z)
            if i:
                # Canonical tuple must contain a nonempty diff range.
                self.assertGreater(x, 0)
            if i == len(controls) - 1:
                # The final source offset is irrelevant and set to zero
                self.assertEqual(z, 0)
            else:
                # Adjacent diff ranges must have been merged.
                self.assertTrue(y or z)
            src_pos += x + z

    def round_trip(self, src, dst):
        blocks = core.diff(src, dst)
        for block in blocks:
            self.assertIs(type(block), bytes)
        self.assert_canonical(blocks[0], len(src))
        dst2 = core.patch(src, *blocks)
        self.assertIs(type(dst2), bytes)
        self.assertEqual(dst2, dst)

    def test_cases(self):
        for a, b in ROUND_TRIP_CASES:
            self.round_trip(a, b)
            self.round_trip(b, a)

    def check_diff_blocks(self, src, dst, controls, diff, extra):
        # Check construction of control, diff and extra blocks.
        blocks = core.diff(src, dst)
        self.assertEqual(list(unpack_control_block(blocks[0])), controls)
        self.assertEqual(blocks[1], diff)
        self.assertEqual(blocks[2], extra)
        self.assertEqual(core.patch(src, *blocks), dst)

    def test_diff_simple_example(self):
        self.check_diff_blocks(b'banana', b'bandana',
                               [(3, 4, 0)], 3 * b'\x00', b'dana')

    def test_nonzero_diff(self):
        src = b"The quick brown fox jumps over the lazy dog."
        dst = b"the quick brown fox jumps over the hazy dog."
        n = len(dst)
        diff = bytearray(n)
        diff[0] = 32
        diff[35] = (ord(b'h') - ord(b'l')) & 0xff
        self.check_diff_blocks(src, dst, [(n, 0, 0)], bytes(diff), b'')

    def test_merge_rule(self):
        # A diff range followed by an extra-only control is merged into
        # one control tuple.
        src = 20 * b' ' + b'&xtraBlock'
        dst = b'..' + 18 * b' ' + b'&exBlock&extraBlock'
        # Without merging, controls would be [(21, 0, -9), (0, 18, 9)]
        self.check_diff_blocks(src, dst,
                               controls=[(21, 18, 0)],
                               diff=b'\x0e\x0e' + 19 * b'\x00',
                               extra=b'exBlock&extraBlock')

    def test_diff_insert_byte(self):
        src = 32 * b'a'
        dst = src[:16] + b'b' + src[16:]
        self.check_diff_blocks(src, dst, [(32, 1, 0)],
                               diff=16 * b'\x00' + b'\x01' + 15 * b'\x00',
                               extra=b'a')

    def test_diff_swap_repeated_blocks(self):
        A, B = 100 * b'A', 100 * b'B'
        self.check_diff_blocks(A + B, B + A,
                               [(0, 100, 0), (100, 0, 0)],
                               diff=100 * b'\x00', extra=B)

    def test_diff_swap_blocks(self):
        src = bytes(range(200))
        dst = src[100:] + src[:100]
        self.check_diff_blocks(src, dst,
                               [(0, 0, 100), (100, 0, -200), (100, 0, 0)],
                               diff=200 * b'\x00', extra=b'')

    def test_diff_adjust_overlap(self):
        # Ensure that an overlapping byte is assigned to the better
        # matching block.
        self.check_diff_blocks(b'ccccdabcadcb',
                               b'ccccdcdabcadcb',
                               [(5, 0, -2), (9, 0, 0)],
                               14 * b'\x00', b'')

    def test_empty_dst(self):
        for src in BYTES_CASES:
            self.check_diff_blocks(src, b'', [], b'', b'')

    def test_empty_src(self):
        for dst in BYTES_CASES:
            self.check_diff_blocks(b'', dst,
                                   [(0, len(dst), 0)] if dst else [],
                                   diff=b'', extra=dst)

    def test_identical_src_dst(self):
        for src in BYTES_CASES:
            control, diff, extra = core.diff(src, src)
            controls = list(unpack_control_block(control))

            if src:
                self.assertEqual(len(controls), 1)
                x, y, z = controls[0]
                self.assertEqual(x, len(src))
                self.assertEqual(y, 0)
                # final source-position adjustment z does not affect output
            else:
                self.assertEqual(controls, [])

            self.assertEqual(diff, len(src) * b'\x00')
            self.assertEqual(extra, b'')
            self.assertEqual(core.patch(src, control, diff, extra), src)

    def test_patch_addition(self):
        src = bytes(range(256))
        dst = bytes((value + 1) % 256 for value in src)
        bcontrol = pack_control_block((len(src), 0, 0))
        blocks = bcontrol, len(src) * b'\x01', b''
        self.assertEqual(core.patch(src, *blocks), dst)

    def test_patch(self):
        noop = pack_control_block((0, 0, 0))  # no-op control tuple
        noop2 = 3 * (7 * b'\x00' + b'\x80')   # negative zero no-op
        operation = pack_control_block((3, 4, 2))
        for bcontrol in [
            operation,
            noop + operation + noop,
            noop2 + operation + noop + noop2,
        ]:
            dst = core.patch(b'banana', bcontrol, 3 * b'\x00', b'dana')
            self.assertEqual(dst, b'bandana')

        # The control block must be binary data, not a list of tuples.
        self.assertRaises(TypeError, core.patch, b'', [], b'', b'')

    # ----- Patch edge cases and error handling -----

    def assert_corrupt(self, reason, control=b'', diff=b'', extra=b''):
        msg = r"corrupt patch \(%s\)" % reason
        with self.assertRaisesRegex(ValueError, msg):
            core.patch(b'', control, diff, extra)

    def test_x_y_out_of_range(self):
        # regression test for PR #29
        for control, var_name in [((-1, 0, 0), 'x'),
                                  ((0, -1, 0), 'y'),
                                  ((5, 0, 0), 'x'),
                                  ((0, 5, 0), 'y')]:
            bcontrol = pack_control_block(control)
            self.assert_corrupt("%s out of range" % var_name,
                                bcontrol, diff=4 * b'\x00', extra=b'abcd')

    def test_invalid_control_block(self):
        for n in 1, 23, 25, 47, 49:
            self.assert_corrupt("invalid control block", control=n * b'\x00')

    def test_final_state(self):
        self.assert_corrupt("incomplete output", diff=b'x')
        self.assert_corrupt("incomplete output", extra=b'y')
        self.assert_corrupt("incomplete output", diff=b'x', extra=b'y')

    def test_src_pos_outside_source(self):
        src = b'ab'
        for controls, bdiff, dst in [
            ([(0, 0, -1), (2, 0, 0)], b'\x01\x01', b'\x01b'),
            ([(0, 0,  2), (2, 0, 0)], b'\x01\x02', b'\x01\x02'),
        ]:
            bcontrol = pack_control_block(*controls)
            self.assertEqual(core.patch(src, bcontrol, bdiff, b''), dst)

    def test_src_pos_overflow(self):
        M = 1 << 63
        for z in -M + 1, M - 1:
            bcontrol = pack_control_block((0, 0, z))
            self.assertEqual(core.patch(b'', bcontrol, b'', b''), b'')

        for controls, diff_len in [
            ([(0, 0, M - 1), (0, 0, 1)], 0),
            ([(0, 0, -M + 1), (0, 0, -1), (0, 0, -1)], 0),
            ([(0, 0, M - 1), (2, 0, 0)], 2),
        ]:
            bcontrol = pack_control_block(*controls)
            self.assert_corrupt("offset overflow",
                                bcontrol, diff=diff_len * b'\x00')

# ----------------------- BSDIFF4 format layer ---------------------------

class TestHelpers(unittest.TestCase):

    def test_header(self):
        bheader = bytes.fromhex("""
        42 53 44 49 46 46 34 30   c9 02 00 00 00 00 00 00
        a2 07 00 00 00 00 00 00   c0 0f 02 00 00 00 00 00 """)
        sizes = (0x2c9, 0x7a2, 0x20fc0)

        self.assertEqual(pack_header(*sizes), bheader)
        self.assertEqual(unpack_header(bheader), sizes)
        self.assertRaisesRegex(ValueError, "invalid BSDIFF40 magic header",
                               unpack_header, 32 * b'\x00')
        for n in 0, 1, 31, 33:
            self.assertRaisesRegex(ValueError, "invalid header size",
                                   unpack_header, n * b'\x00')

    def test_control_block(self):
        bcontrol = bytes.fromhex("""
        1f00000000000000 a007000000000000 0100000000000080
        0200000000000000 3000000000000080 0000000000000000 """)
        controls = [(0x1f, 0x7a0, -1), (2, -0x30, 0)]

        self.assertEqual(pack_control_block(*controls), bcontrol)
        for control in (1, 2), (1, 2, 3, 4):
            self.assertRaises(ValueError, pack_control_block, control)

        self.assertEqual(list(unpack_control_block(bcontrol)), controls)
        for n in 1, 23, 25, 47, 49:
            bcontrol = unpack_control_block(n * b'\x00')
            self.assertRaisesRegex(ValueError, "invalid control block",
                                   list, bcontrol)  # force iteration


class Example:
    src = b'abc'
    dst = b'abd!'
    # BSDIFF40 patch from b'abc' to b'abd!', verified with bspatch.
    # 42 5a 68 39 = BZh9
    patch = bytes.fromhex("""
    42534449 46463430 2a000000 00000000 25000000 00000000 04000000 00000000
    425a6839 31415926 5359d014 9a290000 04c00068 08200030 cd34193f 5209593c
    5dc914e1 42434052 68a4425a 68393141 59265359 4c5a9f48 00000040 00600020
    00210082 8c5dc914 e1424131 6a7d2042 5a683931 41592653 592d15eb 1c000000
    10002000 20002118 4682ee48 a70a1205 a2bd6380 """)
    header_sizes = (0x2a, 0x25, 0x04)  # control_len, diff_len, dst_len
    control_tuples = [(3, 1, 0)]
    diff_block = b'\x00\x00\x01'
    extra_block = b'!'
    blocks = (pack_control_block(*control_tuples), diff_block, extra_block)


class TestExample(unittest.TestCase):

    def test_compatibility(self):
        self.assertEqual(patch(Example.src, Example.patch), Example.dst)

    def test_header(self):
        self.assertEqual(unpack_header(Example.patch[:32]),
                         Example.header_sizes)

    def test_read_write_roundtrip(self):
        blocks = read_patch(BytesIO(Example.patch))
        self.assertEqual(blocks, Example.blocks)
        f = BytesIO()
        write_patch(f, *blocks)
        self.assertEqual(f.getvalue(), Example.patch)
        f.seek(0)
        self.assertEqual(read_patch(f), blocks)


class TestFormat(unittest.TestCase):

    @unittest.skipIf(UNDER_QEMU, "slow under QEMU")
    def test_example(self):
        a = 100_000 * b'a'
        b = bytearray(a)
        b[100:106] = b' diff '
        p = diff(a, bytes(b))
        self.assertEqual(patch(a, p), b)

    def round_trip(self, src, dst):
        p = diff(src, dst)
        self.assertIs(type(p), bytes)
        dst2 = patch(src, p)
        self.assertIs(type(dst2), bytes)
        self.assertEqual(dst, dst2)

    def test_cases(self):
        for a, b in ROUND_TRIP_CASES:
            self.round_trip(a, b)
            self.round_trip(b, a)

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


EMPTY = bz2.compress(b'')  # compressed empty block

class TestFormatErrors(unittest.TestCase):

    def test_invalid_header(self):
        p = b"BSDIFF41" + 24 * b'\x00'
        self.assertRaisesRegex(ValueError, "invalid BSDIFF40 magic header",
                               read_patch, BytesIO(p))

    def test_truncated_patch(self):
        for data in [
            b'',
            b'ABC',
            b'BSDIFF40',
            b'BSDIFF40' + 23 * b'\x00',
            pack_header(len(EMPTY) + 1, 0, 0) + EMPTY,
            pack_header(len(EMPTY), len(EMPTY) + 1, 0) + 2 * EMPTY,
        ]:
            self.assertRaisesRegex(ValueError, "truncated bsdiff4 patch",
                                   read_patch, BytesIO(data))

    def test_negative_lengths(self):
        for lengths in [(-1, 0, 0), (0, -1, 0), (0, 0, -1)]:
            data = pack_header(*lengths) + 3 * EMPTY
            self.assertRaisesRegex(ValueError,
                                   "negative size in bsdiff4 patch",
                                   read_patch, BytesIO(data))

    def test_invalid_control_block(self):
        for n in 1, 23, 25, 47, 49:
            f = BytesIO()
            write_patch(f, n * b'\x00', b'', b'')
            f.seek(0)
            self.assertRaisesRegex(ValueError, "invalid control block",
                                   read_patch, f)

    def test_invalid_blocks(self):
        for data in [
            pack_header(1, len(EMPTY), 0) + b'x' + EMPTY + EMPTY,
            pack_header(len(EMPTY), 1, 0) + EMPTY + b'x' + EMPTY,
            pack_header(len(EMPTY), len(EMPTY), 0) + EMPTY + EMPTY + b'x',
        ]:
            self.assertRaises(OSError, read_patch, BytesIO(data))

    def test_dst_length(self):
        dst_len = 1  # Conflicts with the empty diff and extra block.
        data = pack_header(len(EMPTY), len(EMPTY), dst_len) + 3 * EMPTY
        self.assertRaisesRegex(ValueError, "invalid destination length",
                               read_patch, BytesIO(data))

    @unittest.skipUnless(sys.maxsize < (1 << 31), "requires 32-bit Python")
    def test_header_overflow(self):
        M = 1 << 31
        for lengths in [(M, 0, 0), (0, M, 0), (0, 0, M)]:
            data = pack_header(*lengths) + 3 * EMPTY
            self.assertRaisesRegex(ValueError,
                                   "size too large in bsdiff4 patch",
                                   read_patch, BytesIO(data))


class TestMutate(unittest.TestCase):

    def test_truncated_patch(self):
        for i in range(len(Example.patch)):
            # truncating patch
            self.assertRaises(ValueError, patch,
                              Example.src, Example.patch[:i])

    @unittest.skipIf(UNDER_QEMU, "slow under QEMU")
    def test_mutated_patch(self):
        data = Example.patch
        for i in range(len(data)):
            mut = bytearray(data)
            for j in range(8):
                # mutate j-th bit in i-th byte
                mut[i] = data[i] ^ (1 << j)
                try:
                    dst = patch(Example.src, bytes(mut))
                except (ValueError, MemoryError, OSError):
                    continue
                # mutation could theoretically produce another valid patch
                self.assertEqual(dst, Example.dst)

# ----------------------------- file layer -------------------------------

class TestFile(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def path(self, fn):
        return os.path.join(self.tmpdir, fn)

    def read_data(self, fn):
        with open(self.path(fn), 'rb') as fi:
            return fi.read()

    def write_data(self, fn, data):
        with open(self.path(fn), 'wb') as fo:
            fo.write(data)

    def assert_same_file_content(self, fn1, fn2):
        data1 = self.read_data(fn1)
        data2 = self.read_data(fn2)
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

    def test_cases(self):
        for a, b in ROUND_TRIP_CASES:
            self.write_data('src', a)
            self.write_data('dst', b)
            self.round_trip()

    def test_example(self):
        self.write_data('src', Example.src)
        self.write_data('patch', Example.patch)
        file_patch(self.path('src'), self.path('dst'), self.path('patch'))
        self.assertEqual(self.read_data('dst'), Example.dst)

    def test_example_inplace(self):
        self.write_data('src', Example.src)
        self.write_data('patch', Example.patch)
        file_patch_inplace(self.path('src'), self.path('patch'))
        self.assertEqual(self.read_data('src'), Example.dst)

    def check_preserves_file(self, mode):
        # Verify that patching preserves the inode and its hard-link
        # relationship.
        self.write_data('src', b'source data will be patched with new data')
        self.write_data('dst', b'destination data')
        patch_path = self.path('patch')
        file_diff(self.path('src'), self.path('dst'), patch_path)

        src = self.path('src')
        link = self.path('link')

        os.link(src, link)
        stat_before = os.stat(src)

        if mode == 'inplace':
            file_patch_inplace(src, patch_path)
        elif mode == 'samepath':
            file_patch(src, src, patch_path)
        elif mode == 'samefile':
            file_patch(src, link, patch_path)
        else:
            raise ValueError(mode)

        # Ensure that `src` still refers to the same file.
        stat_after = os.stat(src)
        self.assertEqual((stat_after.st_dev, stat_after.st_ino),
                         (stat_before.st_dev, stat_before.st_ino))
        # Ensure that the hard link was not broken.
        self.assertTrue(samefile(src, link))
        self.assert_same_file_content('src', 'dst')

    def test_preserves_file_inplace(self):
        self.check_preserves_file('inplace')

    def test_preserves_file_samepath(self):
        self.check_preserves_file('samepath')

    def test_preserves_file_samefile(self):
        self.check_preserves_file('samefile')

    def test_patch_error_preserves_files(self):
        # Verify that an invalid patch leaves the target file unchanged.
        self.write_data('src', b'source data')
        self.write_data('dst', b'destination data')
        self.write_data('patch', b'invalid patch')

        self.assertRaises(ValueError, file_patch,
                          self.path('src'), self.path('dst'),
                          self.path('patch'))
        self.assertEqual(self.read_data('dst'), b'destination data')

        self.assertRaises(ValueError, file_patch_inplace,
                          self.path('src'), self.path('patch'))
        self.assertEqual(self.read_data('src'), b'source data')

        self.assertRaises(ValueError, file_patch,
                          self.path('src'), self.path('src'),
                          self.path('patch'))
        self.assertEqual(self.read_data('src'), b'source data')

    def test_patch_error_does_not_create_dst(self):
        # Verify that an invalid patch does not create the target file.
        self.write_data('src', b'source data')
        self.write_data('patch', b'invalid patch')

        self.assertRaises(ValueError, file_patch,
                          self.path('src'), self.path('dst'),
                          self.path('patch'))
        self.assertFalse(exists(self.path('dst')))

# -------------------------- free threading ------------------------------

NTHREADS = 4


def run_concurrently(func):
    """Call func simultaneously in several threads and return the results."""
    barrier = Barrier(NTHREADS)

    def worker():
        barrier.wait()
        return func()

    with ThreadPoolExecutor(max_workers=NTHREADS) as executor:
        futures = [executor.submit(worker) for _ in range(NTHREADS)]
        return [future.result() for future in futures]


@unittest.skipUnless(GIL_DISABLED, "requires free-threaded Python")
class TestFreeThreading(unittest.TestCase):

    def test_gil_disabled(self):
        self.assertFalse(sys._is_gil_enabled())

    def test_core_functions(self):
        src = bytes(range(256)) * 4
        dst = src[:400] + b"free-threading" + src[414:]
        expected_blocks = core.diff(src, dst)
        expected_sa = core.suffix_array(src)
        values = (-2**63 + 1, -1, 0, 1, 2**63 - 1)

        def work():
            for _ in range(5):
                blocks = core.diff(src, dst)
                if blocks != expected_blocks:
                    return False
                if core.patch(src, *blocks) != dst:
                    return False
                if core.suffix_array(src) != expected_sa:
                    return False
                for value in values:
                    if core.decode_int64(core.encode_int64(value)) != value:
                        return False
            return True

        self.assertEqual(run_concurrently(work), NTHREADS * [True])

    def test_format_functions(self):
        src = bytes(range(256)) * 4
        dst = src[:400] + b"free-threading" + src[414:]
        patch_data = diff(src, dst)

        def work():
            for _ in range(5):
                if patch(src, patch_data) != dst:
                    return False
                if patch(src, diff(src, dst)) != dst:
                    return False
            return True

        self.assertEqual(run_concurrently(work), NTHREADS * [True])


def run(verbosity=1):
    from bsdiff4 import __version__
    print('Python version: %s' % sys.version)
    print('bsdiff4 is installed in: %s' % os.path.dirname(__file__))
    print('bsdiff4 version: %s' % __version__)
    print('UNDER_QEMU: %s' % UNDER_QEMU)
    print('GIL_DISABLED: %s' % GIL_DISABLED)
    print('DEBUG: %s' % getattr(core, "DEBUG", 0))

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(sys.modules[__name__]))
    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


if __name__ == '__main__':
    unittest.main()
