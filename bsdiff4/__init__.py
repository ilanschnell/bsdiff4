import bsdiff4.core as core  # type: ignore
from bsdiff4.format import (diff, patch, file_diff, file_patch,
                            file_patch_inplace)


__version__: str = core.BSDIFF4_VERSION

__all__ = ["diff", "patch", "file_diff", "file_patch", "file_patch_inplace"]


def test(verbosity=1):
    """test(verbosity=1) -> TextTestResult

    Run self-test, and return `unittest.runner.TextTestResult` object.
    """
    from bsdiff4.tests import run
    return run(verbosity=verbosity)
