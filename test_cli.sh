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
bspatch4 -v /bin/ls mv diff.bin
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
