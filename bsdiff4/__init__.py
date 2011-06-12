from format import diff, patch

__version__ = '1.0.2'


def test(verbosity=1):
    import test_all
    return test_all.run(verbosity=verbosity)
