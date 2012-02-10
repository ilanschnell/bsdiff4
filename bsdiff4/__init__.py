from .format import diff, patch

__version__ = '1.0.2'


def test(verbosity=1):
    from .test_all import run
    return run(verbosity=verbosity)
