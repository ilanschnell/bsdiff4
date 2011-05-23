import bz2
from os.path import getsize
from optparse import OptionParser

import core
import format


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


def write_data(path, data):
    fo = open(path, 'wb')
    fo.write(data)
    fo.close()


def read_data(path):
    fi = open(path, 'rb')
    data = fi.read()
    fi.close()
    return data


def file_diff(src_path, dst_path, patch_path, verbose=False):
    src = read_data(src_path)
    dst = read_data(dst_path)
    if verbose:
        print 'src: %s' % human_bytes(len(src))
        print 'dst: %s' % human_bytes(len(dst))
    patch = format.diff(src, dst)
    if verbose:
        print 'patch: %s (%.2f%% of dst)' % (human_bytes(len(patch)),
                                             100.0 * len(patch) / len(dst))
    write_data(patch_path, patch)


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

    file_diff(args[0], args[1], args[2], opts.verbose)


def file_patch(src_path, dst_path, patch_path):
    src = read_data(src_path)
    patch = read_data(patch_path)
    dst = format.patch(src, patch)
    write_data(dst_path, dst)


def show_patch(patch_path):
    fi = open(patch_path, 'rb')
    print 'magic: %r' % fi.read(8)
    size = {'total': getsize(patch_path)}
    for var_name in 'control', 'diff', 'dst':
        size[var_name] = core.decode_int64(fi.read(8))
    size['extra'] = size['total'] - 32 - size['control'] - size['diff']

    for var_name in 'total', 'control', 'diff', 'extra', 'dst':
        print '%s size: %d (%s)' % (var_name, size[var_name],
                                   human_bytes(size[var_name]))
    print 'total / dst = %.2f%%' % (100.0 * size['total'] / size['dst'])
    bcontrol = bz2.decompress(fi.read(size['control']))
    fi.close()
    tcontrol = [(core.decode_int64(bcontrol[i:i + 8]),
                 core.decode_int64(bcontrol[i + 8:i + 16]),
                 core.decode_int64(bcontrol[i + 16:i + 24]))
                for i in xrange(0, len(bcontrol), 24)]
    print 'number of control tuples: %d' % len(tcontrol)
    #for t in tcontrol:
    #    print '%20d %10d %10d' % t


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

    file_patch(args[0], args[1], args[2])
