import bz2
from StringIO import StringIO

import core


def write_data(path, data):
    fo = open(path, 'wb')
    fo.write(data)
    fo.close()


def read_data(path):
    fi = open(path, 'rb')
    data = fi.read()
    fi.close()
    return data


def write_patch(fo, len_dst, tcontrol, bdiff, bextra):
    fo.write('BSDIFF40')
    faux = StringIO()
    # write control tuples as series of offts
    for c in tcontrol:
        for x in c:
            faux.write(core.encode_int64(x))
    # compress each block
    bcontrol = bz2.compress(faux.getvalue())
    bdiff = bz2.compress(bdiff)
    bextra = bz2.compress(bextra)
    for n in len(bcontrol), len(bdiff), len_dst:
        fo.write(core.encode_int64(n))
    for data in bcontrol, bdiff, bextra:
        fo.write(data)


def diff(src, dst):
    """generate a BSDIFF4-format patch from 'src' to 'dst'
    """
    tcontrol, bdiff, bextra = core.diff(src, dst)
    faux = StringIO()
    write_patch(faux, len(dst), tcontrol, bdiff, bextra)
    return faux.getvalue()


def file_diff(src_path, dst_path, patch_path):
    src = read_data(src_path)
    dst = read_data(dst_path)
    tcontrol, bdiff, bextra = core.diff(src, dst)
    fo = open(patch_path, 'wb')
    write_patch(fo, len(dst), tcontrol, bdiff, bextra)
    fo.close()


def read_patch(f, header_only=False):
    magic = f.read(8)
    assert magic.startswith('BSDIFF4')
    # length headers
    len_control = core.decode_int64(f.read(8))
    len_diff = core.decode_int64(f.read(8))
    len_dst = core.decode_int64(f.read(8))
    # read the control header
    bcontrol = bz2.decompress(f.read(len_control))
    tcontrol = [(core.decode_int64(bcontrol[i:i + 8]),
                 core.decode_int64(bcontrol[i + 8:i + 16]),
                 core.decode_int64(bcontrol[i + 16:i + 24]))
                for i in xrange(0, len(bcontrol), 24)]
    if header_only:
        return len_control, len_diff, len_dst, tcontrol
    # read the diff and extra blocks
    bdiff = bz2.decompress(f.read(len_diff))
    bextra = bz2.decompress(f.read())
    return len_dst, tcontrol, bdiff, bextra


def patch(src, patch):
    """apply the BSDIFF4-format 'patch' to 'src'
    """
    f = StringIO(patch)
    len_dst, tcontrol, bdiff, bextra = read_patch(f)
    f.close()
    return core.patch(src, len_dst, tcontrol, bdiff, bextra)


def file_patch(src_path, dst_path, patch_path):
    src = read_data(src_path)
    fi = open(patch_path, 'rb')
    len_dst, tcontrol, bdiff, bextra = read_patch(fi)
    fi.close()
    write_data(dst_path,
               core.patch(src, len_dst, tcontrol, bdiff, bextra))
