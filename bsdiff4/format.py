import bz2
from StringIO import StringIO

import core


def diff(src, dst):
    """generate a BSDIFF4-format patch from 'src' to 'dst'
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
    return ('BSDIFF40' +
            core.encode_offt(len(bcontrol)) +
            core.encode_offt(len(bdiff)) +
            core.encode_offt(len(dst)) +
            bcontrol + bdiff + bextra)


def patch(src, patch):
    """apply the BSDIFF4-format 'patch' to 'src'
    """
    magic = patch[:8]
    assert magic.startswith('BSDIFF4')
    # length headers
    len_control = core.decode_offt(patch[8:16])
    len_diff = core.decode_offt(patch[16:24])
    len_dst = core.decode_offt(patch[24:32])
    # start positions of blocks
    pos_control = 32
    pos_diff = pos_control + len_control
    pos_extra = pos_diff + len_diff
    # the three data blocks
    bcontrol = bz2.decompress(patch[pos_control:pos_diff])
    bdiff = bz2.decompress(patch[pos_diff:pos_extra])
    bextra = bz2.decompress(patch[pos_extra:])
    # decode the control tuples
    tcontrol = [(core.decode_offt(bcontrol[i:i + 8]),
                 core.decode_offt(bcontrol[i + 8:i + 16]),
                 core.decode_offt(bcontrol[i + 16:i + 24]))
                for i in xrange(0, len(bcontrol), 24)]
    # actually do the patching
    return core.patch(src, len_dst, tcontrol, bdiff, bextra)
