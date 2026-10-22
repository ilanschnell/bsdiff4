#!/bin/bash
set -ex

python -m pip install .

bsdiff4 --version
bspatch4 --version
