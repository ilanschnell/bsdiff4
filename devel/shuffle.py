# demonstration of BSDIFF’s handling of moved data

import os
import random
from io import BytesIO

from bsdiff4 import diff
from bsdiff4.cli import show_patch

blocks = [os.urandom(random.randrange(10, 1000)) for _ in range(20)]
src = b''.join(blocks)
blocks.extend(blocks[:5])
random.shuffle(blocks)
dst = b''.join(blocks)

show_patch(BytesIO(diff(src, dst)), verbose=True)
