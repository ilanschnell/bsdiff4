from os.path import getsize
from optparse import OptionParser

from bsdiff4.format import file_diff, file_patch, read_patch


def display_version():
    from bsdiff4 import __version__
    print("bsdiff4 %s" % __version__)


def human_bytes(n):
    """
    return the number of bytes 'n' in more human readable form
    """
    if n < 1024:
        return '%i B' % n
    k = (n - 1) / 1024 + 1
    if k < 1024:
        return '%i KB' % k
    return '%.2f MB' % (float(n) / (2 ** 20))


def show_filesizes(*args):
    for i, name in enumerate(['src', 'dst', 'patch']):
        size = getsize(args[i])
        print('%s: %s (%s)' % (name, args[i], human_bytes(size)))


def main_bsdiff4():
    p = OptionParser(
        usage="usage: %prog [options] SRC DST PATCH",
        description=("generate a BSDIFF4-format PATCH from SRC to DST "
                     "and write it to PATCH"))

    p.add_option('-v', "--verbose",
                 action="store_true")

    p.add_option("--version",
                 action="store_true")

    opts, args = p.parse_args()

    if opts.version:
        display_version()
        return

    if len(args) != 3:
        p.error('requies 3 arguments, try -h')

    file_diff(*args)
    if opts.verbose:
        show_filesizes(*args)


def show_patch(patch_path, verbose=False):
    s_total = getsize(patch_path)
    with open(patch_path, 'rb') as fi:
        s_control, s_diff, s_dst, tcontrol = read_patch(fi, header_only=True)

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
    print('number of control tuples: %d' % len(tcontrol))
    if verbose:
        print('%20s %10s %10s' % ('x', 'y', 'z'))
        for t in tcontrol:
            print('%20d %10d %10d' % t)


def main_bspatch4():
    p = OptionParser(
        usage="usage: %prog [options] SRC DST PATCH",
        description=("genertaes DST, by applying the BSDIFF4-format PATCH "
                     "file to SRC"))

    p.add_option('-v', "--verbose",
                 action="store_true")

    p.add_option("--version",
                 action="store_true")

    opts, args = p.parse_args()

    if opts.version:
        display_version()
        return

    if len(args) == 1:
        show_patch(args[0], opts.verbose)
        return

    if len(args) != 3:
        p.error('requies 3 arguments, try -h')

    file_patch(*args)
    if opts.verbose:
        show_filesizes(*args)
