#!/bin/bash
set -ex

python -m pip install .

bsdiff4 --version
bsdiff4 --help
bspatch4 --version
bspatch4 --help
bsdiff4 -v /bin/ls /bin/mv diff.bin
bspatch4 -v /bin/ls mv diff.bin
cmp /bin/mv mv
bspatch4 -v diff.bin
