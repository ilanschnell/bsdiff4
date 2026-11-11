"""
Select small, alphabetized examples from minimized branch-two cases.
"""
from bsdiff4 import core
from bsdiff4.format import unpack_control_block

from util import alphabetize, read_cases
from minimize_cases import has_consecutive_ranges


def main():
    for src, dst in read_cases('branch2.min'):
        try:
            src, dst = alphabetize(src, dst)
        except ValueError:
            continue
        blocks = core.diff(src, dst)
        assert core.patch(src, *blocks) == dst
        controls = list(unpack_control_block(blocks[0]))
        assert has_consecutive_ranges(controls)
        if len(src) + len(dst) < 120:
            print("# %d %d (%d)   %r" % (len(src), len(dst),
                                         len(set(src + dst)), controls))
            print("src = %r" % src)
            print("dst = %r" % dst)


if __name__ == '__main__':
    main()
