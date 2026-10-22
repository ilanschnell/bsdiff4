#!/bin/bash
set -ex

python -m pip install .

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
cd "$tmpdir"

pwd
python -c "import bsdiff4; assert bsdiff4.test().wasSuccessful()"

bsdiff4 --version
bsdiff4 --help
bspatch4 --version
bspatch4 --help
bsdiff4 -v /bin/ls /bin/mv diff.bin
bspatch4 /bin/ls mv diff.bin
bspatch4 -v /bin/ls mv diff.bin >verbose-info.txt
cmp /bin/mv mv
bspatch4 -v diff.bin

if bsdiff4 mv; then
    echo "bsdiff4 unexpectedly succeeded" >&2
    exit 1
fi

if bspatch4 mv mv; then
    echo "bspatch4 unexpectedly succeeded" >&2
    exit 1
fi

# Apply a patch produced by the system bsdiff using bsdiff4.
bsdiff /bin/ls /bin/mv system.diff
bspatch4 /bin/ls from_system system.diff
cmp /bin/mv from_system

# Apply a patch produced by bsdiff4 using the system bspatch.
bsdiff4 /bin/ls /bin/mv python.diff
bspatch /bin/ls from_python python.diff
cmp /bin/mv from_python

ls -l /bin
