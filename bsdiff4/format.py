import bz2
import sys
from io import BytesIO

import bsdiff4.core as core  # type: ignore


MAGIC = b'BSDIFF40'


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
        bt = control_block[i:i + 24]
        yield tuple(core.decode_int64(bt[j:j + 8]) for j in range(0, 24, 8))


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


def read_patch(fi, header_only=False):
    "read a BSDIFF4-format patch from stream 'fi'"
    magic = fi.read(8)
    if magic[:7] != MAGIC[:7]:
        raise ValueError("invalid magic bsdiff4 header")
    # length headers
    control_len = core.decode_int64(fi.read(8))
    diff_len = core.decode_int64(fi.read(8))
    dst_len = core.decode_int64(fi.read(8))
    for size in control_len, diff_len, dst_len:
        check_size(size)
    # read the control header
    control_block = bz2.decompress(read_exact(fi, control_len))
    if len(control_block) % 24:
        raise ValueError("invalid control block")
    if header_only:
        return control_len, diff_len, dst_len, control_block
    # read the diff and extra blocks
    diff_block = bz2.decompress(read_exact(fi, diff_len))
    extra_block = bz2.decompress(fi.read())
    return dst_len, control_block, diff_block, extra_block


def write_patch(fo, dst_len, control_block, diff_block, extra_block):
    "write a BSDIFF4-format patch to stream 'fo'"
    fo.write(MAGIC)
    # compress each block
    control_block = bz2.compress(control_block)
    diff_block = bz2.compress(diff_block)
    extra_block = bz2.compress(extra_block)
    for n in len(control_block), len(diff_block), dst_len:
        fo.write(core.encode_int64(n))
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
