=======================================================
bsdiff4: binary diff and patch using the BSDIFF4-format
=======================================================

The code is mostly derived from cx_bsdiff (written by Anthony Tuininga,
http://cx-bsdiff.sourceforge.net/).  The cx_bsdiff code in turn was derived
from bsdiff, the standalone utility produced for BSD which can be found
at http://www.daemonology.net/bsdiff.
In addition to the two functions (diff and patch) cx_bsdiff provides, this
package includes:

  * an interface to the BSDIFF4-format
  * command line interfaces: bsdiff4 and bspatch4
  * tests


The bsdiff4 package defines the following high level functions:

``diff(src_bytes, dst_bytes)`` -> bytes
   Return a BSDIFF4-format patch (from src_bytes to dst_bytes) as bytes.

``patch(src_bytes, patch_bytes)`` -> bytes
   Apply the BSDIFF4-format patch_bytes to src_bytes and return the bytes.

``file_diff(src_path, dst_path, patch_path)``
   Write a BSDIFF4-format patch (from the file src_path to the file dst_path)
   to the file patch_path.

``file_patch(src_path, dst_path, patch_path)``
   Apply the BSDIFF4-format file patch_path to the file src_path and
   write the result to the file dst_path.


Example:

   >>> import bsdiff4
   >>> a = bytes(100000 * 'a')
   >>> b = bytearray(a)
   >>> b[100:106] = ' diff '
   >>> p = bsdiff4.diff(a, bytes(b))
   >>> len(p)
   154
   >>> bsdiff4.patch(a, p) == b
   True
