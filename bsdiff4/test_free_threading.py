"""
Tests specific to free-threaded CPython.
"""
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import bsdiff4.core as core  # type: ignore
from bsdiff4 import diff, patch


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


class TestFreeThreading(unittest.TestCase):

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


if __name__ == '__main__':
    unittest.main()
