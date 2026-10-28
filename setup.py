import re
from sysconfig import get_config_var
try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup, Extension


kwds = {}
kwds['long_description'] = open('README.rst').read()

# Read version from bsdiff/__init__.py
pat = re.compile(r'__version__\s*=\s*"(\S+)"', re.M)
data = open('bsdiff4/__init__.py').read()
kwds['version'] = pat.search(data).group(1)

macros = []
if get_config_var("Py_GIL_DISABLED") in (1, "1"):
    macros.append(("Py_GIL_DISABLED", "1"))

setup(
    name = "bsdiff4",
    author = "Ilan Schnell",
    author_email = "ilanschnell@gmail.com",
    url = "https://github.com/ilanschnell/bsdiff4",
    license = "BSD",
    python_requires = ">=3.7",
    classifiers = [
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: C",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Programming Language :: Python :: 3.15",
        "Programming Language :: Python :: Free Threading :: 3 - Stable",
        "Topic :: Utilities",
    ],
    description = "binary diff and patch using the BSDIFF4-format",
    packages = ["bsdiff4"],
    package_data = {"bsdiff4": ["py.typed"]},  # see PEP 561
    ext_modules = [Extension(name = "bsdiff4.core",
                             sources = ["bsdiff4/core.c"],
                             define_macros = macros,
                             )],
    entry_points = {
        'console_scripts': [
            'bsdiff4 = bsdiff4.cli:main_bsdiff4',
            'bspatch4 = bsdiff4.cli:main_bspatch4',
        ],
    },
    **kwds
)
