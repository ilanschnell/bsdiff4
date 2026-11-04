# demonstration of BSDIFF’s handling of diff addition

import os
from random import randrange
from io import BytesIO

from bsdiff4 import diff, patch
from bsdiff4.cli import show_patch

N = 1_000_000

src = os.urandom(N)
dst = bytearray(src)
for _ in range(N // 100):
    dst[randrange(N)] = randrange(256)
dst = bytes(dst)

print("number of different bytes: %d\n" %
      sum(src[i] != dst[i] for i in range(N)))

patch_data = diff(src, dst)
show_patch(BytesIO(patch_data), verbose=True)

assert patch(src, patch_data) == dst
