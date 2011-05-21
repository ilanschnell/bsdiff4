import re
import sys
from os.path import join
from distutils.core import setup, Extension


kwds = {}

kwds['long_description'] = open('README.rst').read()

# Read version from core/__init__.py
pat = re.compile(r'__version__\s*=\s*(.+)', re.M)
data = open(join('bsdiff', '__init__.py')).read()
kwds['version'] = eval(pat.search(data).group(1))


setup(
    name = "bsdiff",
    author = "Ilan Schnell",
    author_email = "ilanschnell@gmail.com",
    url = "http://pypi.python.org/pypi/bsdiff/",
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
    packages = ["bsdiff"],
    ext_modules = [Extension(name = "bsdiff.core",
                             sources = ["bsdiff/core.c"])],
    **kwds
)