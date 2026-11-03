import sys
from argparse import ArgumentParser
from os.path import getsize

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


def check_overflow(n):
    M = 1 << 63
    if not -M <= n < M:
        raise ValueError("corrupt patch (offset overflow)")


def show_control(control_block, dst_len, diff_len, extra_len, verbose=False):
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
        if x < 0 or totals[0] > diff_len:
            raise ValueError("corrupt patch (x out of range): "
                             "%d %d %d" % (x, y, z))
        if y < 0 or totals[1] > extra_len:
            raise ValueError("corrupt patch (y out of range): "
                             "%d %d %d" % (x, y, z))
        src_pos += x
        check_overflow(src_pos)
        src_pos += z
        check_overflow(src_pos)

    if omitted:
        print('%10s %10s %10s' % (3 * ('...',)))
    print('%10s %10s' % (2 * ('------',)))
    print('%10d %10d' % totals)

    if sum(totals) != dst_len:
        raise ValueError("corrupt patch (output size mismatch)")
    assert totals == (diff_len, extra_len)


def show_patch(fi, verbose=False):
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

    show_control(control_block, dst_len, len(diff_block), len(extra_block),
                 verbose)


def main_bsdiff4():
    p = ArgumentParser(
        description=("generate a BSDIFF4-format PATCH from SRC to DST "
                     "and write it to PATCH"))
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
    p = ArgumentParser(
        usage="%(prog)s [options] SRC DST PATCH\n"
              "       %(prog)s [options] PATCH",
        description=("generate DST by applying the BSDIFF4-format PATCH "
                     "file to SRC, or display information about PATCH"))
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
