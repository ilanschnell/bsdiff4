from os.path import getsize
from optparse import OptionParser

from format import file_diff, file_patch, read_patch


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


def main_bsdiff4():
    p = OptionParser(
        usage="usage: %prog [options] SRC DST PATCH",
        description=("generate a BSDIFF4-format PATCH from SRC to DST "
                     "and write it to PATCH"))

    p.add_option('-v', "--verbose",
                 action="store_true")

    opts, args = p.parse_args()

    if len(args) != 3:
        p.error('requies 3 arguments, try -h')

    file_diff(*args)
    if opts.verbose:
        size = [getsize(args[i]) for i in xrange(3)]
        print('src: %s' % human_bytes(size[0]))
        print('dst: %s' % human_bytes(size[1]))
        print('patch: %s (%.2f%% of dst)' % (human_bytes(size[2]),
                                             100.0 * size[2] / size[1]))


def show_patch(patch_path):
    s_total = getsize(patch_path)
    fi = open(patch_path, 'rb')
    s_control, s_diff, s_dst, tcontrol = read_patch(fi, header_only=True)
    fi.close()
    s_extra = s_total - 32 - s_control - s_diff

    for var_name in 'total', 'control', 'diff', 'extra', 'dst':
        size = eval('s_' + var_name)
        print('%s size: %d (%s)' % (var_name, size, human_bytes(size)))
    print('total / dst = %.2f%%' % (100.0 * s_total / s_dst))
    print('number of control tuples: %d' % len(tcontrol))
    #for t in tcontrol:
    #    print('%20d %10d %10d' % t)


def main_bspatch4():
    p = OptionParser(
        usage="usage: %prog [options] SRC DST PATCH",
        description=("genertaes DST, by applying the BSDIFF4-format PATCH "
                     "file to SRC"))

    opts, args = p.parse_args()

    if len(args) == 1:
        show_patch(args[0])
        return

    if len(args) != 3:
        p.error('requies 3 arguments, try -h')

    file_patch(*args)
