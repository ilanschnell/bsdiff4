"""
Generate and store raw inputs matching the broadest condition for the
second control-tuple merge rule.  The saved cases can later be filtered,
minimized, and alphabetized without repeating the expensive search.
"""
from random import randrange, choice, shuffle

from bsdiff4 import core
from bsdiff4.format import unpack_control_block

from util import append_case


def random_bytes(size, alphabet=256):
    return bytes(randrange(alphabet) for _ in range(size))


def make_case():
    """Return related byte strings with repeated and rearranged data."""
    block_count = randrange(3, 12)
    blocks = [random_bytes(randrange(9, 65), choice((4, 16, 256)))
              for _ in range(block_count)]

    # Reusing blocks creates competing suffix matches, while the mutations
    # exercise the boundaries at which compute_diff() changes matches.
    src_blocks = [choice(blocks) for _ in range(randrange(3, 16))]
    dst_blocks = src_blocks[:]
    for _ in range(randrange(1, 8)):
        operation = randrange(5)
        pos = randrange(len(dst_blocks) + 1)
        if operation == 0 and dst_blocks:
            del dst_blocks[min(pos, len(dst_blocks) - 1)]
        elif operation == 1:
            dst_blocks.insert(pos, choice(blocks))
        elif operation == 2 and dst_blocks:
            shuffle(dst_blocks)
        elif operation == 3 and dst_blocks:
            i = min(pos, len(dst_blocks) - 1)
            block = bytearray(dst_blocks[i])
            block[randrange(len(block))] ^= randrange(1, 256)
            dst_blocks[i] = bytes(block)
        else:
            dst_blocks.insert(pos, random_bytes(randrange(1, 33)))

    return b''.join(src_blocks), b''.join(dst_blocks)


def has_branch2(control_block):
    controls = list(unpack_control_block(control_block))
    for px, py, pz in controls[:-1]:
        if py == 0 and pz == 0:
            return True
    return False


def search():
    attempt = 0
    while True:
        attempt += 1
        src, dst = make_case()
        blocks = core.diff(src, dst)
        assert core.patch(src, *blocks) == dst
        if has_branch2(blocks[0]):
            print("attempt:", attempt)
            print("lengths:", len(src), len(dst))
            print("alphabet size:", len(set(src + dst)))
            append_case(src, dst, "branch2.raw")

        if attempt % 1_000_000 == 0:
            print("searched:", attempt)


if __name__ == '__main__':
    search()
