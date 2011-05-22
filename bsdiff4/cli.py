from optparse import OptionParser

import api


def human_bytes(n):
    """
    Return the number of bytes n in more human readable form.
    """
    if n < 1024:
        return '%i B' % n
    k = (n - 1) / 1024 + 1
    if k < 1024:
        return '%i KB' % k
    return '%.2f MB' % (float(n) / (2**20))


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
    patch = api.diff(src, dst)
    if verbose:
        print 'src: %s' % human_bytes(len(src))
        print 'dst: %s' % human_bytes(len(dst))
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
    dst = api.patch(src, patch)
    write_data(dst_path, dst)


def main_bspatch4():
    p = OptionParser(
        usage="usage: %prog [options] SRC DST PATCH",
        description=("genertaes DST, by applying the BSDIFF4-format PATCH "
                     "file to SRC"))

    opts, args = p.parse_args()

    if len(args) != 3:
        p.error('requies 3 arguments, try -h')

    file_patch(args[0], args[1], args[2])
