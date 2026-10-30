import bz2
import os
import sys
import random
import shutil
import unittest
import tempfile
from io import BytesIO
from sysconfig import get_config_var
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import bsdiff4.core as core  # type: ignore
from bsdiff4.format import (MAGIC, pack_header, unpack_header,
                            pack_control_block, unpack_control_block,
                            write_patch, read_patch, read_data)
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
        self.assertRaises(TypeError, core.encode_int64, 'x')
        M = 1 << 63
        for n in -M -1, -M, M, M + 1:
            self.assertRaises(OverflowError, core.encode_int64, n)

        self.assertRaises(TypeError, core.decode_int64, 12345)
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


ROUND_TRIP_CASES = [
    (b'', b''),
    (b'', b'x'),
    (b'abc', b'abc'),
    (b'abc', b'abx'),
    (b'abc', b'abxy'),
    (b'abc', b'xbc'),
    (b'abc', b'xybc'),
    (b'123456789 987654321', b'123456789000987654321'),  # issue #14
    (b'', os.urandom(200)),
    (os.urandom(200), os.urandom(200)),
]


class TestCoreDiffPatch(unittest.TestCase):

    def round_trip(self, src, dst):
        control_block, diff_block, extra_block = core.diff(src, dst)
        for b in control_block, diff_block, extra_block:
            self.assertIs(type(b), bytes)
        dst2 = core.patch(src, len(dst),
                          control_block, diff_block, extra_block)
        self.assertIs(type(dst2), bytes)
        self.assertEqual(dst2, dst)

    def test_cases(self):
        for a, b in ROUND_TRIP_CASES:
            self.round_trip(a, b)
            self.round_trip(b, a)

    def test_diff_blocks(self):
        # Check construction of control, diff and extra blocks.
        self.assertEqual(core.diff(b'banana', b'bandana'),
                         (pack_control_block((3, 4, 2)),
                          3 * b'\x00', b'dana'))

        src = 32 * b'a'
        dst = 16 * b'a' + b'b' + 16 * b'a'
        self.assertEqual(core.diff(src, dst),
                         (pack_control_block((32, 1, -1)),
                          16 * b'\x00' + b'\x01' + 15 * b'\x00', b'a'))

        src = 100 * b'a' + 100 * b'b'
        dst = 100 * b'b' + 100 * b'a'
        self.assertEqual(core.diff(src, dst),
                         (pack_control_block((0, 100, 0), (100, 0, -100)),
                          100 * b'\x00', 100 * b'b'))

    def test_diff_adjust_overlap(self):
        # Ensure that an overlapping byte is assigned to the better
        # matching block.
        self.assertEqual(core.diff(b'ccccdabcadcb', b'ccccdcdabcadcb'),
                         (pack_control_block((5, 0, -2), (9, 0, -9)),
                          14 * b'\x00', b''))

    def test_patch(self):
        for controls in [
            [(3, 4, 2)],
            [(3, 4, 2), (0, 0, 0)],  # (0, 0, 0) is a no-op control tuple
            [(0, 0, 0), (3, 4, 2)],
        ]:
            dst = core.patch(b'banana', 7, pack_control_block(*controls),
                             3 * b'\x00', b'dana')
            self.assertEqual(dst, b'bandana')

        # The control block must be binary data, not a list of tuples.
        self.assertRaises(TypeError, core.patch, b'', 0, [], b'', b'')

    # ----- Patch edge cases and error handling -----

    def test_x_y_out_of_range(self):
        for control, var_name in [((-1, 0, 0), 'x'),
                                  ((0, -1, 0), 'y'),
                                  ((5, 0, 0), 'x'),
                                  ((0, 5, 0), 'y')]:
            bcontrol = pack_control_block(control)
            msg = r"corrupt patch \(%s out of range\)" % var_name
            self.assertRaisesRegex(ValueError, msg,
                                   core.patch, b'abcd', 4,
                                   bcontrol, 4 * b'\x00', b'')

    def test_negative_destination_length(self):
        msg = r"corrupt patch \(negative destination length\)"
        self.assertRaisesRegex(ValueError, msg,
                               core.patch, b'', -1, b'', b'', b'')

    def test_invalid_control_block(self):
        msg = r"corrupt patch \(invalid control block\)"
        for n in 1, 23, 25, 47, 49:
            self.assertRaisesRegex(ValueError, msg,
                                   core.patch, b'', 0, n * b'\x00', b'', b'')

    def test_final_state(self):
        for args, msg in [
            ((1, b'', b'', b''),  "incomplete output"),
            ((0, b'', b'x', b''), "unused block data"),
            ((0, b'', b'', b'x'), "unused block data"),
        ]:
            self.assertRaisesRegex(ValueError, r"corrupt patch \(%s\)" % msg,
                                   core.patch, b'', *args)

    def test_src_pos_outside_source(self):
        bcontrol = pack_control_block((0, 0, -1), (2, 0, 0))
        self.assertEqual(
            core.patch(b'ab', 2, bcontrol, b'\x01\x01', b''), b'\x01b')

        bcontrol = pack_control_block((0, 0, 2), (2, 0, 0))
        self.assertEqual(
            core.patch(b'ab', 2, bcontrol, b'\x01\x02', b''), b'\x01\x02')

    def test_src_pos_overflow(self):
        M = 1 << 63
        for z in -M + 1, M - 1:
            bcontrol = pack_control_block((0, 0, z))
            self.assertEqual(core.patch(b'', 0, bcontrol, b'', b''), b'')

        for dst_len, controls, diff_block in [
            (0, [(0, 0, M - 1), (0, 0, 1)],               b''),
            (0, [(0, 0, -M + 1), (0, 0, -1), (0, 0, -1)], b''),
            (2, [(0, 0, M - 1), (2, 0, 0)],               b'\x00\x00'),
        ]:
            bcontrol = pack_control_block(*controls)
            self.assertRaisesRegex(ValueError,
                                   r"corrupt patch \(offset overflow\)",
                                   core.patch, b'', dst_len,
                                   bcontrol, diff_block, b'')

# ----------------------- BSDIFF4 format layer ---------------------------

class TestHelpers(unittest.TestCase):

    def test_header(self):
        bheader = b'BSDIFF40' + bytes.fromhex("""
        c9 02 00 00 00 00 00 00
        a2 07 00 00 00 00 00 00
        c0 0f 02 00 00 00 00 00 """)
        sizes = (0x2c9, 0x7a2, 0x20fc0)

        self.assertEqual(pack_header(*sizes), bheader)
        self.assertEqual(unpack_header(bheader), sizes)
        self.assertRaisesRegex(ValueError, "invalid magic bsdiff4 header",
                               unpack_header, 32 * b'\x00')
        for n in 0, 1, 31, 33:
            self.assertRaisesRegex(ValueError, "invalid header size",
                                   unpack_header, n * b'\x00')

    def test_control_block(self):
        bcontrol = bytes.fromhex("""
        1f00000000000000 a007000000000000 0100000000000080
        0200000000000000 3000000000000080 0000000000000000
        """)
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
    data = bytes.fromhex("""
    42534449 46463430 2a000000 00000000 25000000 00000000 04000000 00000000
    425a6839 31415926 5359d014 9a290000 04c00068 08200030 cd34193f 5209593c
    5dc914e1 42434052 68a4425a 68393141 59265359 4c5a9f48 00000040 00600020
    00210082 8c5dc914 e1424131 6a7d2042 5a683931 41592653 592d15eb 1c000000
    10002000 20002118 4682ee48 a70a1205 a2bd6380
    """)
    header_sizes = (0x2a, 0x25, 0x04)  # control_len, diff_len, dst_len
    control_tuples = [(3, 1, 0)]
    diff_block = b'\x00\x00\x01'
    extra_block = b'!'


class TestExample(unittest.TestCase):

    def test_compatibility(self):
        self.assertEqual(patch(Example.src, Example.data), Example.dst)

    def test_header(self):
        self.assertEqual(unpack_header(Example.data[:32]),
                         Example.header_sizes)

    def test_read_patch(self):
        f = BytesIO(Example.data)
        dst_len, control_block, diff_block, extra_block = read_patch(f)
        self.assertEqual(dst_len, len(Example.dst))
        self.assertEqual(list(unpack_control_block(control_block)),
                         Example.control_tuples)
        self.assertEqual(diff_block, Example.diff_block)
        self.assertEqual(extra_block, Example.extra_block)

    def test_write_patch(self):
        f = BytesIO()
        write_patch(f, len(Example.dst),
                    pack_control_block(*Example.control_tuples),
                    Example.diff_block,
                    Example.extra_block)
        self.assertEqual(f.getvalue(), Example.data)


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

    def test_extra(self):
        src = os.urandom(1000)
        dst = src + os.urandom(10)
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


EMPTY = bz2.compress(b'')  # compressed empty block

class TestFormatErrors(unittest.TestCase):

    def test_invalid_header(self):
        p = b"BSDIFF30" + 24 * b'\x00'
        self.assertRaisesRegex(ValueError, "invalid magic bsdiff4 header",
                               read_patch, BytesIO(p))

    def test_truncated_patch(self):
        for data in [
            MAGIC,
            MAGIC + 23 * b'\x00',
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

    def test_invalid_blocks(self):
        for data in [
            pack_header(1, len(EMPTY), 0) + b'x' + EMPTY + EMPTY,
            pack_header(len(EMPTY), 1, 0) + EMPTY + b'x' + EMPTY,
            pack_header(len(EMPTY), len(EMPTY), 0) + EMPTY + EMPTY + b'x',
        ]:
            self.assertRaises(OSError, read_patch, BytesIO(data))

    @unittest.skipUnless(sys.maxsize < (1 << 31), "requires 32-bit Python")
    def test_header_overflow(self):
        M = 1 << 31
        for lengths in [(M, 0, 0), (0, M, 0), (0, 0, M)]:
            data = pack_header(*lengths) + 3 * bz2.compress(b'')
            self.assertRaisesRegex(ValueError,
                                   "size too large in bsdiff4 patch",
                                   read_patch, BytesIO(data))


class TestMutate(unittest.TestCase):

    def test_truncated_patch(self):
        for i in range(len(Example.data)):
            # truncating patch
            self.assertRaises(ValueError, patch,
                              Example.src, Example.data[:i])

    @unittest.skipIf(UNDER_QEMU, "slow under QEMU")
    def test_mutated_patch(self):
        data = Example.data
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

    def assert_same_file_content(self, fn1, fn2):
        data1 = read_data(self.path(fn1))
        data2 = read_data(self.path(fn2))
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

    def test_cases(self):
        for a, b in ROUND_TRIP_CASES:
            self.write_data('src', a)
            self.write_data('dst', b)
            self.round_trip()

    def test_inplace(self):
        a = 1000 * b'ABCDE'
        b = 1000 * b'XYZ'
        self.write_data('src', a + os.urandom(100) + b)
        self.write_data('dst', a + os.urandom(100) + b)
        file_diff(self.path('src'), self.path('dst'), self.path('patch'))
        file_patch_inplace(self.path('src'), self.path('patch'))
        self.assert_same_file_content('src', 'dst')

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
                if core.patch(src, len(dst), *blocks) != dst:
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

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(sys.modules[__name__]))
    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


if __name__ == '__main__':
    unittest.main()
