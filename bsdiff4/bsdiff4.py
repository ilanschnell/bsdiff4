import bz2
from StringIO import StringIO

import core


def diff(src, dst):
    """Generate a BSDIFF4-format patch from 'src' to 'dst'.
    """
    tcontrol, bdiff, bextra = core.diff(src, dst)
    # write control tuples as series of offts
    faux = StringIO()
    for c in tcontrol:
        for x in c:
            faux.write(core.encode_offt(x))
    # compress each block
    bcontrol = bz2.compress(faux.getvalue())
    bdiff = bz2.compress(bdiff)
    bextra = bz2.compress(bextra)
    return ''.join((
            'BSDIFF40',
            core.encode_offt(len(bcontrol)),
            core.encode_offt(len(bdiff)),
            core.encode_offt(len(dst)),
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
    l_bcontrol = core.decode_offt(patch[8:16])
    l_bdiff = core.decode_offt(patch[16:24])
    l_target = core.decode_offt(patch[24:32])
    # read the three data blocks
    bcontrol = bz2.decompress(patch[32:32 + l_bcontrol])
    bdiff = bz2.decompress(patch[32 + l_bcontrol:32 + l_bcontrol + l_bdiff])
    bextra = bz2.decompress(patch[32 + l_bcontrol + l_bdiff:])
    # decode the control tuples
    tcontrol = [(core.decode_offt(bcontrol[i:i + 8]),
                 core.decode_offt(bcontrol[i + 8:i + 16]),
                 core.decode_offt(bcontrol[i + 16:i + 24]))
                for i in xrange(0, len(bcontrol), 24)]
    # actually do the patching
    return core.patch(src, l_target, tcontrol, bdiff, bextra)
