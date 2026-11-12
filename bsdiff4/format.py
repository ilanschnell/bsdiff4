import bz2
import sys
from io import BytesIO

import bsdiff4.core as core  # type: ignore


MAGIC = b'BSDIFF40'


def pack_header(control_len, diff_len, dst_len):
    lengths = control_len, diff_len, dst_len
    return MAGIC + b''.join(core.encode_int64(n) for n in lengths)


def unpack_header(header):
    if len(header) != 32:
        raise ValueError("invalid header size")
    if header[:8] != MAGIC:
        raise ValueError("invalid BSDIFF40 magic header, got %r" % header[:8])
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


class NonCanonicalError(ValueError):
    "Raised when a valid control block is not canonical."


def validate_canonical(control_block, src_len=None):
    "Raise NonCanonicalError unless a valid control block is canonical."
    controls = list(unpack_control_block(control_block))

    negative_zero = 7 * b'\x00' + b'\x80'
    for j in range(0, len(control_block), 8):
        if control_block[j:j + 8] == negative_zero:
            raise NonCanonicalError("negative zero found")

    src_pos = 0
    for i, (x, y, z) in enumerate(controls):
        if src_pos < 0:
            raise NonCanonicalError("negative source position")

        if src_len is not None:
            if src_pos > src_len:
                raise NonCanonicalError("source position not in source range")

            if src_pos + x > src_len:
                raise NonCanonicalError("diff range not in source range")

        if x == y == z == 0:
            raise NonCanonicalError("no-op tuple found")

        if i and x == 0:
            raise NonCanonicalError("empty diff range")

        if i == len(controls) - 1:
            if z:
                raise NonCanonicalError("final z not zero")
        else:
            if y == z == 0:
                raise NonCanonicalError("adjacent diff ranges not merged")

        src_pos += x + z


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
    if len(control_block) % 24:
        raise ValueError("invalid control block")
    diff_block = bz2.decompress(read_exact(fi, diff_len))
    extra_block = bz2.decompress(fi.read())
    if dst_len != len(diff_block) + len(extra_block):
        raise ValueError("invalid destination length")
    return control_block, diff_block, extra_block


def write_patch(fo, control_block, diff_block, extra_block):
    "write a BSDIFF4-format patch to stream 'fo'"
    # compress each block
    dst_len = len(diff_block) + len(extra_block)
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
    fo = BytesIO()
    write_patch(fo, *core.diff(src_bytes, dst_bytes))
    return fo.getvalue()


def patch(src_bytes: bytes, patch_bytes: bytes) -> bytes:
    """patch(src_bytes, patch_bytes) -> bytes

    Apply the BSDIFF4-format patch_bytes to src_bytes and return the bytes.
    """
    return core.patch(src_bytes, *read_patch(BytesIO(patch_bytes)))


def file_diff(src_path: str, dst_path: str, patch_path: str) -> None:
    """file_diff(src_path, dst_path, patch_path) -> None

    Write a BSDIFF4-format patch (from the file src_path to the file dst_path)
    to the file patch_path.
    """
    blocks = core.diff(read_data(src_path), read_data(dst_path))
    with open(patch_path, 'wb') as fo:
        write_patch(fo, *blocks)


def file_patch_inplace(path: str, patch_path: str) -> None:
    """file_patch_inplace(path, patch_path) -> None

    Apply the BSDIFF4-format file patch_path to the file 'path' in place.
    """
    with open(patch_path, 'rb') as fi:
        blocks = read_patch(fi)
    with open(path, 'r+b') as f:
        dst = core.patch(f.read(), *blocks)
        f.seek(0)
        f.write(dst)
        f.truncate()


def file_patch(src_path: str, dst_path: str, patch_path: str) -> None:
    """file_patch(src_path, dst_path, patch_path) -> None

    Apply the BSDIFF4-format file patch_path to the file src_path and
    write the result to the file dst_path.
    """
    with open(patch_path, 'rb') as fi:
        dst = core.patch(read_data(src_path), *read_patch(fi))
    with open(dst_path, 'wb') as fo:
        fo.write(dst)
