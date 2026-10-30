import bz2
import sys
from io import BytesIO

import bsdiff4.core as core  # type: ignore


MAGIC = b'BSDIFF40'


def pack_header(control_len, diff_len, dst_len):
    return (MAGIC +
            core.encode_int64(control_len) +
            core.encode_int64(diff_len) +
            core.encode_int64(dst_len))


def unpack_header(header):
    if len(header) != 32:
        raise ValueError("invalid header size")
    if header[:7] != MAGIC[:7]:
        raise ValueError("invalid magic bsdiff4 header")
    return tuple(core.decode_int64(header[i:i + 8]) for i in range(8, 32, 8))


def pack_control_block(*controls):
    "pack binary control block from control tuples"
    return b''.join(core.encode_int64(value)
                    for x, y, z in controls
                    for value in (x, y, z))


def unpack_control_block(control_block):
    "unpack the binary control block and generate control tuples"
    if len(control_block) % 24:
        raise ValueError("invalid control block")

    for i in range(0, len(control_block), 24):
        yield tuple(core.decode_int64(control_block[j:j + 8])
                    for j in range(i, i + 24, 8))


def check_size(size):
    if size < 0:
        raise ValueError("negative size in bsdiff4 patch")
    if size > sys.maxsize:
        raise ValueError("size too large in bsdiff4 patch")


def read_exact(fi, size):
    check_size(size)
    data = fi.read(size)
    if len(data) != size:
        raise ValueError("truncated bsdiff4 patch")
    return data


def read_patch(fi):
    "read a BSDIFF4-format patch from stream 'fi'"
    sizes = unpack_header(read_exact(fi, 32))
    for size in sizes:
        check_size(size)
    control_len, diff_len, dst_len = sizes
    control_block = bz2.decompress(read_exact(fi, control_len))
    diff_block = bz2.decompress(read_exact(fi, diff_len))
    extra_block = bz2.decompress(fi.read())
    return dst_len, control_block, diff_block, extra_block


def write_patch(fo, dst_len, control_block, diff_block, extra_block):
    "write a BSDIFF4-format patch to stream 'fo'"
    # compress each block
    control_block = bz2.compress(control_block)
    diff_block = bz2.compress(diff_block)
    extra_block = bz2.compress(extra_block)
    fo.write(pack_header(len(control_block), len(diff_block), dst_len))
    fo.write(control_block)
    fo.write(diff_block)
    fo.write(extra_block)


def read_data(path):
    with open(path, 'rb') as fi:
        data = fi.read()
    return data


def diff(src_bytes: bytes, dst_bytes: bytes) -> bytes:
    """diff(src_bytes, dst_bytes) -> bytes

    Return a BSDIFF4-format patch (from src_bytes to dst_bytes) as bytes.
    """
    faux = BytesIO()
    write_patch(faux, len(dst_bytes), *core.diff(src_bytes, dst_bytes))
    return faux.getvalue()


def file_diff(src_path: str, dst_path: str, patch_path: str) -> None:
    """file_diff(src_path, dst_path, patch_path)

    Write a BSDIFF4-format patch (from the file src_path to the file dst_path)
    to the file patch_path.
    """
    src = read_data(src_path)
    dst = read_data(dst_path)
    with open(patch_path, 'wb') as fo:
        write_patch(fo, len(dst), *core.diff(src, dst))


def patch(src_bytes: bytes, patch_bytes: bytes) -> bytes:
    """patch(src_bytes, patch_bytes) -> bytes

    Apply the BSDIFF4-format patch_bytes to src_bytes and return the bytes.
    """
    return core.patch(src_bytes, *read_patch(BytesIO(patch_bytes)))


def file_patch_inplace(path: str, patch_path: str) -> None:
    """file_patch_inplace(path, patch_path)

    Apply the BSDIFF4-format file patch_path to the file 'path' in place.
    """
    with open(patch_path, 'rb') as fi:
        with open(path, 'r+b') as fo:
            data = fo.read()
            fo.seek(0)
            fo.write(core.patch(data, *read_patch(fi)))
            fo.truncate()


def file_patch(src_path: str, dst_path: str, patch_path: str) -> None:
    """file_patch(src_path, dst_path, patch_path)

    Apply the BSDIFF4-format file patch_path to the file src_path and
    write the result to the file dst_path.
    """
    from os.path import abspath

    if abspath(dst_path) == abspath(src_path):
        file_patch_inplace(src_path, patch_path)
        return

    with open(patch_path, 'rb') as fi:
        with open(dst_path, 'wb') as fo:
            fo.write(core.patch(read_data(src_path), *read_patch(fi)))
