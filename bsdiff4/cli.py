from argparse import ArgumentParser
from os.path import getsize

from bsdiff4 import __version__
from bsdiff4.format import (file_diff, file_patch, read_patch,
                            unpack_control_block)


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


def show_patch(patch_path, verbose=False):
    s_total = getsize(patch_path)
    with open(patch_path, 'rb') as fi:
        s_control, s_diff, s_dst, bcontrol = read_patch(fi, header_only=True)

    for name, size in [
            ('total', s_total),
            ('control', s_control),
            ('diff', s_diff),
            ('extra', s_total - 32 - s_control - s_diff),
            ('dst', s_dst),
    ]:
        print('%s size: %d (%s)' % (name, size, human_bytes(size)))

    if s_dst:
        print('total / dst = %.2f%%' % (100.0 * s_total / s_dst))

    print('number of control tuples: %d' % (len(bcontrol) // 24))
    if verbose:
        print('%20s %10s %10s' % ('x', 'y', 'z'))
        for ct in unpack_control_block(bcontrol):
            print('%20d %10d %10d' % ct)


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
        show_patch(args.paths[0], args.verbose)
        return

    if len(args.paths) != 3:
        p.error("requires either PATCH or SRC DST PATCH")

    file_patch(*args.paths)
    if args.verbose:
        show_filesizes(*args.paths)
