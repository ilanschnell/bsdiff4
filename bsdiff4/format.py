import bz2
import sys

is_py3k = bool(sys.version_info[0] == 3)

if is_py3k:
    from io import BytesIO as StringIO
    MAGIC = bytes('BSDIFF40'.encode('latin1'))
else:
    from cStringIO import StringIO
    if sys.version_info[:2] >= (2, 6):
        MAGIC = bytes('BSDIFF40')
    else: # 2.5
        MAGIC = 'BSDIFF40'

import bsdiff4.core as core


def write_patch(fo, len_dst, tcontrol, bdiff, bextra):
    """write a BSDIFF4-format patch to stream 'fo'
    """
    fo.write(MAGIC)
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
    fo.write(bcontrol)
    fo.write(bdiff)
    fo.write(bextra)


def read_patch(fi, header_only=False):
    """read a BSDIFF4-format patch from stream 'fi'
    """
    magic = fi.read(8)
    assert magic[:7] == MAGIC[:7]
    # length headers
    len_control = core.decode_int64(fi.read(8))
    len_diff = core.decode_int64(fi.read(8))
    len_dst = core.decode_int64(fi.read(8))
    # read the control header
    bcontrol = bz2.decompress(fi.read(len_control))
    tcontrol = [(core.decode_int64(bcontrol[i:i + 8]),
                 core.decode_int64(bcontrol[i + 8:i + 16]),
                 core.decode_int64(bcontrol[i + 16:i + 24]))
                for i in range(0, len(bcontrol), 24)]
    if header_only:
        return len_control, len_diff, len_dst, tcontrol
    # read the diff and extra blocks
    bdiff = bz2.decompress(fi.read(len_diff))
    bextra = bz2.decompress(fi.read())
    return len_dst, tcontrol, bdiff, bextra


def read_data(path):
    fi = open(path, 'rb')
    data = fi.read()
    fi.close()
    return data


def diff(src_bytes, dst_bytes):
    """diff(src_bytes, dst_bytes) -> bytes

    Return a BSDIFF4-format patch (from src_bytes to dst_bytes) as bytes.
    """
    faux = StringIO()
    write_patch(faux, len(dst_bytes), *core.diff(src_bytes, dst_bytes))
    return faux.getvalue()


def file_diff(src_path, dst_path, patch_path):
    """file_diff(src_path, dst_path, patch_path)

    Write a BSDIFF4-format patch (from the file src_path to the file dst_path)
    to the file patch_path.
    """
    src = read_data(src_path)
    dst = read_data(dst_path)
    fo = open(patch_path, 'wb')
    write_patch(fo, len(dst), *core.diff(src, dst))
    fo.close()


def patch(src_bytes, patch_bytes):
    """patch(src_bytes, patch_bytes) -> bytes

    Apply the BSDIFF4-format patch_bytes to src_bytes and return the bytes.
    """
    return core.patch(src_bytes, *read_patch(StringIO(patch_bytes)))


def file_patch(src_path, dst_path, patch_path):
    """file_patch(src_path, dst_path, patch_path)

    Apply the BSDIFF4-format file patch_path to the file src_path and
    write the result to the file dst_path.
    """
    fi = open(patch_path, 'rb')
    fo = open(dst_path, 'wb')
    fo.write(core.patch(read_data(src_path), *read_patch(fi)))
    fo.close()
    fi.close()
