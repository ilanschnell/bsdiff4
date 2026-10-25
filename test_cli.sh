#!/bin/bash
set -ex

python -m pip install .
source_dir=$(pwd)

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
cd "$tmpdir"

pwd
python -c "import bsdiff4; assert bsdiff4.test().wasSuccessful()"
python "$source_dir/test_suffix_array.py"

bsdiff4 --version
bsdiff4 --help
bspatch4 --version
bspatch4 --help
bsdiff4 -v /bin/head /bin/tail a.diff
bspatch4 -v /bin/head tail a.diff
cmp /bin/tail tail

bspatch4 -v a.diff >info.txt
test -s info.txt
head -n 20 info.txt

# Apply patch in-place
cp /bin/head foo
bspatch4 -v foo foo a.diff
cmp foo /bin/tail

if bsdiff4 tail; then
    echo "bsdiff4 unexpectedly succeeded" >&2
    exit 1
fi

if bspatch4 tail tail; then
    echo "bspatch4 unexpectedly succeeded" >&2
    exit 1
fi

# Apply a patch produced by the system bsdiff using bsdiff4.
bsdiff /bin/ls /bin/mv system.diff
bspatch4 /bin/ls from_system system.diff
cmp /bin/mv from_system
xxd -l 48 system.diff

# Apply a patch produced by bsdiff4 using the system bspatch.
bsdiff4 /bin/ls /bin/mv python.diff
bspatch /bin/ls from_python python.diff
cmp /bin/mv from_python

md5sum *.diff
ls -l .
