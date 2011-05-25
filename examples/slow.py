import os
from cStringIO import StringIO

from bsdiff4.format import read_patch


def slow_patch(src_path, dst_path, patch_path):
    fi_patch = open(patch_path, 'rb')
    len_dst, tcontrol, bdiff, bextra = read_patch(fi_patch)
    fi_patch.close()

    fi = open(src_path, 'rb')
    fo = open(dst_path, 'wb')
    faux_diff = StringIO(bdiff)
    faux_extra = StringIO(bextra)
    for x, y, z in tcontrol:
        diff_data = faux_diff.read(x)
        src_data = fi.read(x)
        for i in xrange(len(diff_data)):
            fo.write(chr((ord(diff_data[i]) + ord(src_data[i])) % 256))
        fo.write(faux_extra.read(y))
        fi.seek(z, os.SEEK_CUR)
    fo.close()
    fi.close()


if __name__ == '__main__':
    slow_patch('numpy-1.6.0-1.egg', 'slow.egg', 'np.patch')
