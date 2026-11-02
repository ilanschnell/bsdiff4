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
    _, control_block, diff_block, extra_block = read_patch(fi)
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

    print('\nnumber of control tuples: %d' % (len(control_block) // 24))
    if verbose:
        print('%10s %10s %10s' % ('x', 'y', 'z'))
        totals = [0, 0, 0]
        for ct in unpack_control_block(control_block):
            print('%10d %10d %10d' % ct)
            totals = [totals[i] + ct[i] for i in range(3)]
        print('%10s %10s %10s' % (3 * ('------',)))
        print('%10d %10d %10d' % tuple(totals))


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
    file_diff(*paths)
    if args.verbose:
        show_filesizes(*paths)


def main_bspatch4():
    p = ArgumentParser(
        usage="%(prog)s [options] SRC DST PATCH\n"
              "       %(prog)s [options] PATCH",
        description=("generate DST by applying the BSDIFF4-format PATCH "
                     "file to SRC, or display information about PATCH"))
    p.add_argument('-v', '--verbose', action='store_true',
                   help="show file sizes or control tuples")
    p.add_argument('--version', action='version',
                   version="bsdiff4 %s" % __version__)
    p.add_argument('paths', nargs='+', metavar='PATH')
    args = p.parse_args()

    if len(args.paths) == 1:
        with open(args.paths[0], 'rb') as fi:
            show_patch(fi, args.verbose)
        return

    if len(args.paths) != 3:
        p.error("requires either PATCH or SRC DST PATCH")

    file_patch(*args.paths)
    if args.verbose:
        show_filesizes(*args.paths)
