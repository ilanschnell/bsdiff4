# demonstration of BSDIFF’s handling of moved and modified data

import os
from io import BytesIO
from random import randrange, shuffle

from bsdiff4 import diff, patch
from bsdiff4.cli import show_patch

blocks = [bytearray(os.urandom(randrange(10, 1000))) for _ in range(20)]
src = b''.join(blocks)

blocks.extend(bytearray(block) for block in blocks[:5])
for block in blocks:
    block[randrange(len(block))] ^= randrange(1, 256)
shuffle(blocks)
dst = b''.join(blocks)

print("source size: %s\n" % len(src))

patch_data = diff(src, dst)
show_patch(BytesIO(patch_data), verbose=True)

assert patch(src, patch_data) == dst
