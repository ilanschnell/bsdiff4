import re
from os.path import join
try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup, Extension


kwds = {}

kwds['long_description'] = open('README.rst').read()

# Read version from bsdiff/__init__.py
pat = re.compile(r'__version__\s*=\s*(\S+)', re.M)
data = open(join('bsdiff4', '__init__.py')).read()
kwds['version'] = eval(pat.search(data).group(1))

setup(
    name = "bsdiff4",
    author = "Ilan Schnell",
    author_email = "ilanschnell@gmail.com",
    url = "https://github.com/ilanschnell/bsdiff4",
    license = "BSD",
    classifiers = [
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: C",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.5",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.2",
        "Topic :: Utilities",
    ],
    description = "binary diff and patch using the BSDIFF4-format",
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
