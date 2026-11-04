import sys
from argparse import ArgumentParser
from os.path import getsize

import bsdiff4.core as core  # type: ignore
from bsdiff4 import __version__
from bsdiff4.format import (file_diff, file_patch, read_patch,
                            unpack_header, unpack_control_block)


def human_bytes(n):
    """
    return the number of bytes 'n' in more human readable form
    """
    if n < 1024:
        return '%d B' % n
    k = n / 1024
    if k < 1024:
        return '%.1f K' % k
    m = k / 1024
    if m < 1024:
        return '%.1f M' % m
    g = m / 1024
    return '%.2f G' % g


def show_filesizes(*args):
    for i, name in enumerate(['src', 'dst', 'patch']):
        size = getsize(args[i])
        print('%s: %s (%s)' % (name, args[i], human_bytes(size)))


def show_header(fi):
    total_len = fi.seek(0, 2)  # go to EOF and return position
    fi.seek(0)
    control_len, diff_len, dst_len = unpack_header(fi.read(32))
    print("sizes:")
    for name, size in [
        ('total', total_len),
        ('control', control_len),
        ('diff', diff_len),
        ('extra', total_len - 32 - control_len - diff_len),
        ('dst', dst_len),
    ]:
        print('%10s: %10d (%s)' % (name, size, human_bytes(size)))


def show_control(control_block, verbose=False):
    print('\nnumber of control tuples: %d' % (len(control_block) // 24))
    print('%10s %10s %10s %10s' % ('x', 'y', 'z', 'src pos'))
    omitted = False
    src_pos = 0
    totals = (0, 0)  # x, y totals
    for i, (x, y, z) in enumerate(unpack_control_block(control_block)):
        if i < 5 or verbose:
            print('%10d %10d %10d %10d' % (x, y, z, src_pos))
        else:
            omitted = True
        totals = (totals[0] + x, totals[1] + y)
        src_pos += x + z

    if omitted:
        print('%10s %10s %10s' % (3 * ('...',)))
    print('%10s %10s' % (2 * ('------',)))
    print('%10d %10d' % totals)


def show_patch(fi, verbose=False):
    show_header(fi)
    fi.seek(0)
    control_block, diff_block, extra_block = read_patch(fi)
    print("\nuncompressed block sizes:")
    for name, size in [
        ('control', len(control_block)),
        ('diff', len(diff_block)),
        ('extra', len(extra_block)),
    ]:
        note = ""
        if name == 'diff' and diff_block:
            nonzero = len(diff_block) - diff_block.count(b'\x00')
            note = '  (non-zero bytes: %d)' % nonzero
        print('%10s: %10d (%s)%s' % (name, size, human_bytes(size), note))

    show_control(control_block, verbose)
    # validate by applying to empty source
    core.patch(b'', control_block, diff_block, extra_block)


def main_bsdiff4():
    """
    Generate a BSDIFF4-format PATCH from SRC to DST and write it to PATCH.
    """
    p = ArgumentParser(description=main_bsdiff4.__doc__)
    p.add_argument('-v', '--verbose', action='store_true',
                   help="show file sizes")
    p.add_argument('--version', action='version',
                   version="bsdiff4 %s" % __version__)
    p.add_argument('src', metavar='SRC')
    p.add_argument('dst', metavar='DST')
    p.add_argument('patch', metavar='PATCH')
    args = p.parse_args()

    paths = args.src, args.dst, args.patch
    try:
        file_diff(*paths)
    except OSError as e:
        sys.exit("%s: %s" % (p.prog, e))
    if args.verbose:
        show_filesizes(*paths)


def main_bspatch4():
    """
    Generate DST by applying the BSDIFF4-format PATCH file to SRC;
    with only PATCH, display information about and verify the patch.
    """
    p = ArgumentParser(
        usage="%(prog)s [options] SRC DST PATCH\n"
              "       %(prog)s [options] PATCH",
        description=main_bspatch4.__doc__,
    )
    p.add_argument('-v', '--verbose', action='store_true',
                   help="show file sizes or all control tuples")
    p.add_argument('--version', action='version',
                   version="bsdiff4 %s" % __version__)
    p.add_argument('paths', nargs='+', metavar='PATH')
    args = p.parse_args()

    if len(args.paths) == 1:
        try:
            with open(args.paths[0], 'rb') as fi:
                show_patch(fi, args.verbose)
        except (ValueError, OSError) as e:
            sys.exit("%s: %s" % (p.prog, e))
        return

    if len(args.paths) != 3:
        p.error("requires either PATCH or SRC DST PATCH")

    try:
        file_patch(*args.paths)
    except (ValueError, OSError) as e:
        sys.exit("%s: %s" % (p.prog, e))
    if args.verbose:
        show_filesizes(*args.paths)
