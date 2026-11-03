from bsdiff4.format import (diff, patch, file_diff, file_patch,
                            file_patch_inplace)

__version__ = "1.4.2"

__all__ = ["diff", "patch", "file_diff", "file_patch", "file_patch_inplace"]


def test(verbosity=1):
    from bsdiff4.test_all import run
    return run(verbosity=verbosity)
