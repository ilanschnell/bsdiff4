import re
import sys
from os.path import join
try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup, Extension


kwds = {}

kwds['long_description'] = open('README.rst').read()

# Read version from core/__init__.py
pat = re.compile(r'__version__\s*=\s*(.+)', re.M)
data = open(join('bsdiff4', '__init__.py')).read()
kwds['version'] = eval(pat.search(data).group(1))


setup(
    name = "bsdiff4",
    author = "Ilan Schnell",
    author_email = "ilanschnell@gmail.com",
    url = "http://pypi.python.org/pypi/bsdiff4/",
    license = "BSD",
    classifiers = [
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: C",
        "Programming Language :: Python",
        "Topic :: Utilities",
    ],
    description = "efficient arrays of booleans -- C extension",
    packages = ["bsdiff4"],
    ext_modules = [Extension(name = "bsdiff4.core",
                             sources = ["bsdiff4/core.c"])],
    entry_points = {
        'console_scripts': [
            'bsdiff4 = bsdiff4.cli:main_bsdiff4',
            'bspatch4 = bsdiff4.cli:main_bspatch4',
        ],
    },
    **kwds
)
