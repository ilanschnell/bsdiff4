import bz2
import sys

if sys.version_info[0] < 3:
    from StringIO import StringIO as BytesIO
else:
    from io import BytesIO

import core


def encode_offt(x):
    """Encode an off_t value as a string.

    This encodes a signed integer into 8 bytes.  I'd prefer some sort of
    signed vint representation, but it's the format used by bsdiff4....
    """
    if x < 0:
        x = -x
        sign = 0x80
    else:
        sign = 0
    bs = [0] * 8
    bs[0] = x % 256
    for b in xrange(7):
        x = (x - bs[b]) / 256
        bs[b+1] = x % 256
    bs[7] |= sign
    if sys.version_info[0] < 3:
        return ''.join(chr(b) for b in bs)
    else:
        return bytes(bs)


def decode_offt(bytes):
    """Decode an off_t value from a string.

    This decodes a signed integer into 8 bytes.  I'd prefer some sort of
    signed vint representation, but it's the format used by bsdiff4....
    """
    if sys.version_info[0] < 3:
        bytes = [ord(x) for x in bytes]
    x = bytes[7] & 0x7F
    for b in xrange(6, -1, -1):
        x = x * 256 + bytes[b]
    if bytes[7] & 0x80:
        x = -x
    return x


def diff(src, dst):
    """Generate a BSDIFF4-format patch from 'src' to 'dst'.
    """
    tcontrol, bdiff, bextra = core.Diff(src, dst)
    # write control tuples as series of offts
    faux = BytesIO()
    for c in tcontrol:
        for x in c:
            faux.write(encode_offt(x))
    # compress each block
    bcontrol = bz2.compress(faux.getvalue())
    bdiff = bz2.compress(bdiff)
    bextra = bz2.compress(bextra)
    return ''.join((
            'BSDIFF40',
            encode_offt(len(bcontrol)),
            encode_offt(len(bdiff)),
            encode_offt(len(dst)),
            bcontrol,
            bdiff,
            bextra,
    ))


def patch(src, patch):
    """Apply a BSDIFF4-format patch to the given string.

    This function returns the result of applying the BSDIFF4-format patch
    'patch' to the input string 'src',
    """
    magic = patch[:8]
    assert magic.startswith('BSDIFF4')
    # read the length headers
    l_bcontrol = decode_offt(patch[8:16])
    l_bdiff = decode_offt(patch[16:24])
    l_target = decode_offt(patch[24:32])
    # read the three data blocks
    bcontrol = bz2.decompress(patch[32:32 + l_bcontrol])
    bdiff = bz2.decompress(patch[32 + l_bcontrol:32 + l_bcontrol + l_bdiff])
    bextra = bz2.decompress(patch[32 + l_bcontrol + l_bdiff:])
    # decode the control tuples
    tcontrol = [(decode_offt(bcontrol[i:i + 8]),
                 decode_offt(bcontrol[i + 8:i + 16]),
                 decode_offt(bcontrol[i + 16:i + 24]))
                for i in xrange(0, len(bcontrol), 24)]
    # actually do the patching
    return core.Patch(src, l_target, tcontrol, bdiff, bextra)
