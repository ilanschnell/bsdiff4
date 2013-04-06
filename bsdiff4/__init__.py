from .format import diff, patch, file_diff, file_patch, file_patch_inplace

__version__ = '1.1.5'


def test(verbosity=1):
    from .test_all import run
    return run(verbosity=verbosity)
