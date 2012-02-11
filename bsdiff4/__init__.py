from .format import diff, patch, file_diff, file_patch

__version__ = '1.1.0'


def test(verbosity=1):
    from .test_all import run
    return run(verbosity=verbosity)
