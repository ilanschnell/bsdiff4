/*
  The code below is mostly derived from cx_bsdiff (written by Anthony
  Tuininga, http://cx-bsdiff.sourceforge.net/).  The cx_bsdiff code in
  turn was derived from bsdiff, the standalone utility produced for BSD
  which can be found at http://www.daemonology.net/bsdiff.
*/

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <assert.h>
#include <stdint.h>

#define BSDIFF4_VERSION  "1.4.4"

/* ----------------------  suffix-array construction  -------------------- */

/* swap two values */
static inline void
swap(Py_ssize_t *a, Py_ssize_t *b)
{
    Py_ssize_t tmp = *a;
    *a = *b;
    *b = tmp;
}

/* sort and rank a small suffix group */
static void
split_small(Py_ssize_t *sa, Py_ssize_t *rank, Py_ssize_t start,
            Py_ssize_t len, Py_ssize_t h)
{
    Py_ssize_t j, k;

    for (k = start; k < start + len; k += j) {
        Py_ssize_t i, x;

        j = 1;
        x = rank[sa[k] + h];
        for (i = 1; k + i < start + len; i++) {
            if (rank[sa[k + i] + h] < x) {
                x = rank[sa[k + i] + h];
                j = 0;
            }
            if (rank[sa[k + i] + h] == x) {
                swap(&sa[k + j], &sa[k + i]);
                j++;
            }
        }
        for (i = 0; i < j; i++)
            rank[sa[k + i]] = k + j - 1;
        if (j == 1)
            sa[k] = -1;
    }
}

/* partition a suffix group around a pivot rank */
static void
partition_group(Py_ssize_t *sa, Py_ssize_t *rank, Py_ssize_t start,
                Py_ssize_t len, Py_ssize_t h,
                Py_ssize_t *lower, Py_ssize_t *upper)
{
    Py_ssize_t i, j, k, x, jj = 0, kk = 0;

    x = rank[sa[start + len / 2] + h];
    for (i = start; i < start + len; i++) {
        if (rank[sa[i] + h] < x)
            jj++;
        if (rank[sa[i] + h] == x)
            kk++;
    }
    jj += start;
    kk += jj;

    j = k = 0;
    i = start;
    while (i < jj) {
        if (rank[sa[i] + h] < x) {
            i++;
        }
        else if (rank[sa[i] + h] == x) {
            swap(&sa[i], &sa[jj + j]);
            j++;
        }
        else {
            swap(&sa[i], &sa[kk + k]);
            k++;
        }
    }

    while (jj + j < kk) {
        if (rank[sa[jj + j] + h] == x) {
            j++;
        }
        else {
            swap(&sa[jj + j], &sa[kk + k]);
            k++;
        }
    }

    *lower = jj;
    *upper = kk;
}

/* recursively split and rank a suffix group */
static void
split(Py_ssize_t *sa, Py_ssize_t *rank, Py_ssize_t start,
      Py_ssize_t len, Py_ssize_t h)
{
    Py_ssize_t lower, upper, i;

    if (len < 16) {
        split_small(sa, rank, start, len, h);
        return;
    }

    partition_group(sa, rank, start, len, h, &lower, &upper);
    assert(start <= lower);
    assert(lower < upper);
    assert(upper <= start + len);

    if (lower > start)
        split(sa, rank, start, lower - start, h);

    for (i = lower; i < upper; i++)
        rank[sa[i]] = upper - 1;
    if (upper - lower == 1)
        sa[lower] = -1;
    if (start + len > upper)
        split(sa, rank, upper, start + len - upper, h);
}

/* construct suffix array for a byte string */
static int
qsufsort(Py_ssize_t *sa, Py_ssize_t *rank,
         const unsigned char *str, Py_ssize_t size)
{
    Py_ssize_t buckets[256], i, h;

    Py_BEGIN_ALLOW_THREADS  /* release GIL */
    for (i = 0; i < 256; i++)
        buckets[i] = 0;
    for (i = 0; i < size; i++)
        buckets[str[i]]++;
    for (i = 1; i < 256; i++)
        buckets[i] += buckets[i - 1];
    for (i = 255; i > 0; i--)
        buckets[i] = buckets[i - 1];
    buckets[0] = 0;

    for (i = 0; i < size; i++)
        sa[++buckets[str[i]]] = i;
    sa[0] = size;
    for (i = 0; i < size; i++)
        rank[i] = buckets[str[i]];
    rank[size] = 0;
    for (i = 1; i < 256; i++)
        if (buckets[i] == buckets[i - 1] + 1)
            sa[buckets[i]] = -1;
    sa[0] = -1;
    Py_END_ALLOW_THREADS

    for (h = 1; sa[0] != -(size + 1); h += h) {
        Py_ssize_t len = 0;

        if (PyErr_CheckSignals() < 0)
            return -1;

        Py_BEGIN_ALLOW_THREADS  /* release GIL */
        for (i = 0; i <= size;) {
            if (sa[i] < 0) {
                len -= sa[i];
                i -= sa[i];
            }
            else {
                if (len)
                    sa[i - len] = -len;
                len = rank[sa[i]] + 1 - i;
                split(sa, rank, i, len, h);
                i += len;
                len = 0;
            }
        }
        if (len)
            sa[i - len] = -len;
        Py_END_ALLOW_THREADS
    }

    if (PyErr_CheckSignals() < 0)
        return -1;

    Py_BEGIN_ALLOW_THREADS  /* release GIL */
    for (i = 0; i <= size; i++)
        sa[rank[i]] = i;
    Py_END_ALLOW_THREADS

    return PyErr_CheckSignals();
}

/* construct suffix array */
static Py_ssize_t *
build_suffix_array(const char *str, Py_ssize_t size)
{
    Py_ssize_t *sa;    /* suffix array */
    Py_ssize_t *rank;  /* temporary rank storage */

    sa = PyMem_Malloc((size + 1) * sizeof(Py_ssize_t));
    if (sa == NULL) {
        PyErr_NoMemory();
        return NULL;
    }

    rank = PyMem_Malloc((size + 1) * sizeof(Py_ssize_t));
    if (rank == NULL) {
        PyErr_NoMemory();
        PyMem_Free(sa);
        return NULL;
    }

    if (qsufsort(sa, rank, (const unsigned char *) str, size) < 0) {
        PyMem_Free(sa);
        sa = NULL;
    }
    PyMem_Free(rank);
    return sa;
}

/* -----------------------  diff output construction  -------------------- */

/* encode int64 as 8 bytes */
static int
encode_int64(char *str, int64_t x)
{
    char sign = 0x00;
    int i;

    if (x == INT64_MIN) {
        PyErr_SetString(PyExc_OverflowError, "cannot encode -2**63");
        return -1;
    }

    if (x < 0) {
        x = -x;
        sign = 0x80;
    }
    for (i = 0; i < 8; i++) {
        str[i] = x & 0xff;
        x >>= 8;
    }
    str[7] |= sign;
    return 0;
}

typedef struct {
    PyObject *control;      /* control block as bytearray */
    unsigned char *diff;    /* difference block */
    char *extra;            /* extra block */
    Py_ssize_t diff_len;    /* length of difference block */
    Py_ssize_t extra_len;   /* length of extra block */
    Py_ssize_t px, py, pz;  /* pending control values */
    int has_pending;        /* whether we received any control tuple yet */
} DiffResult;

/* initialize diff result structure */
static int
diff_init(DiffResult *result, Py_ssize_t dst_len)
{
    result->control = PyByteArray_FromStringAndSize(NULL, 0);
    if (result->control == NULL)
        return -1;

    /* allocate memory for the diff and extra blocks */
    result->diff = PyMem_Malloc(dst_len);
    if (result->diff == NULL) {
        PyErr_NoMemory();
        Py_DECREF(result->control);
        return -1;
    }
    result->extra = PyMem_Malloc(dst_len);
    if (result->extra == NULL) {
        PyErr_NoMemory();
        Py_DECREF(result->control);
        PyMem_Free(result->diff);
        return -1;
    }

    result->diff_len = 0;
    result->extra_len = 0;
    result->px = result->py = result->pz = 0;
    result->has_pending = 0;
    return 0;
}

/* release resources owned by a diff result */
static void
diff_clear(DiffResult *result)
{
    Py_XDECREF(result->control);
    PyMem_Free(result->diff);
    PyMem_Free(result->extra);
}

/* append pending tuple to control block */
static int
diff_append_pending(DiffResult *result)
{
    PyObject *control = result->control;
    Py_ssize_t size;
    char *str;

    size = PyByteArray_GET_SIZE(control);
    if (size > PY_SSIZE_T_MAX - 24) {
        PyErr_NoMemory();
        return -1;
    }
    if (PyByteArray_Resize(control, size + 24) < 0)
        return -1;

    str = (char *) PyByteArray_AS_STRING(control) + size;
    if (encode_int64(str, result->px) < 0 ||
        encode_int64(str + 8, result->py) < 0 ||
        encode_int64(str + 16, result->pz) < 0)
        return -1;

    return 0;
}

/* Append the final pending tuple, unless it produces no output. */
static int
diff_flush_pending(DiffResult *result)
{
    if (result->has_pending == 0)
        return 0;

    /* The final source seek is irrelevant. */
    if (result->px == 0 && result->py == 0)
        return 0;

    result->pz = 0;
    return diff_append_pending(result);
}

/* convert a diff result into Python objects */
static PyObject *
diff_build(DiffResult *result)
{
    PyObject *control, *diff, *extra, *res;

    if (diff_flush_pending(result) < 0)
        return NULL;

    control = PyBytes_FromObject(result->control);
    if (control == NULL)
        return NULL;

    diff = PyBytes_FromStringAndSize((char *) result->diff, result->diff_len);
    if (diff == NULL) {
        Py_DECREF(control);
        return NULL;
    }

    extra = PyBytes_FromStringAndSize(result->extra, result->extra_len);
    if (extra == NULL) {
        Py_DECREF(control);
        Py_DECREF(diff);
        return NULL;
    }

    res = PyTuple_Pack(3, control, diff, extra);
    Py_DECREF(control);
    Py_DECREF(diff);
    Py_DECREF(extra);
    return res;
}

/* Retain one control tuple so it can be merged with the next. */
static int
diff_add_control(DiffResult *result, Py_ssize_t x, Py_ssize_t y, Py_ssize_t z)
{
    if (result->has_pending == 0) {
        result->px = x;
        result->py = y;
        result->pz = z;
        result->has_pending = 1;
        return 0;
    }

    /* A tuple with no diff range does not access the source; any data it
       emits is extra data.  Merge it into the preceding tuple:
       (px, py, pz), (0, y, z) -> (px, py + y, pz + z). */
    if (x == 0) {
        assert(y <= PY_SSIZE_T_MAX - result->py);
        assert((z >= 0 && result->pz <= PY_SSIZE_T_MAX - z) ||
               (z < 0 && result->pz >= -PY_SSIZE_T_MAX - 1 - z));
        result->py += y;
        result->pz += z;
        return 0;
    }

    /* The preceding rule may cancel intervening source seeks, leaving
       (px, 0, 0), (x, y, z).  Merge these into (px + x, y, z), since
       both diff ranges access consecutive source data. */
    if (result->py == 0 && result->pz == 0) {
        assert(x <= PY_SSIZE_T_MAX - result->px);
        result->px += x;
        result->py = y;
        result->pz = z;
        return 0;
    }

    if (diff_append_pending(result) < 0)
        return -1;
    result->px = x;
    result->py = y;
    result->pz = z;
    return 0;
}

/* emit diff and extra data and queue the corresponding control tuple */
static int
emit_data(const char *src, const char *dst, DiffResult *result,
          Py_ssize_t diff_len, Py_ssize_t extra_len, Py_ssize_t z,
          Py_ssize_t dst_pos, Py_ssize_t src_pos)
{
    Py_ssize_t i;

    assert(diff_len >= 0 && extra_len >= 0 && dst_pos >= 0 && src_pos >= 0);

    for (i = 0; i < diff_len; i++)
        result->diff[result->diff_len + i] = (dst[dst_pos + i] -
                                              src[src_pos + i]);

    memcpy(result->extra + result->extra_len,
           dst + dst_pos + diff_len, extra_len);

    result->diff_len += diff_len;
    result->extra_len += extra_len;

    return diff_add_control(result, diff_len, extra_len, z);
}

/* -------------------------  diff calculation  -------------------------- */

/* return the length of the common prefix */
static Py_ssize_t
matchlen(const char *a, Py_ssize_t a_len,
         const char *b, Py_ssize_t b_len)
{
    Py_ssize_t i = 0;

    while (i < a_len && i < b_len && a[i] == b[i])
        i++;
    return i;
}

/* find a prefix match using the suffix array */
static Py_ssize_t
search(const Py_ssize_t *sa,
       const char *a, Py_ssize_t a_len,
       const char *b, Py_ssize_t b_len,
       Py_ssize_t lo, Py_ssize_t hi, Py_ssize_t *pos)
{
    Py_ssize_t x, y;

    if (hi - lo < 2) {
        x = matchlen(a + sa[lo], a_len - sa[lo], b, b_len);
        y = matchlen(a + sa[hi], a_len - sa[hi], b, b_len);

        if (x > y) {
            *pos = sa[lo];
            return x;
        }
        else {
            *pos = sa[hi];
            return y;
        }
    }

    x = lo + (hi - lo) / 2;
    if (memcmp(a + sa[x], b, Py_MIN(a_len - sa[x], b_len)) < 0)
        return search(sa, a, a_len, b, b_len, x, hi, pos);
    else
        return search(sa, a, a_len, b, b_len, lo, x, pos);
}

/* find the best forward match length */
static Py_ssize_t
forward_match_length(const char *src, Py_ssize_t src_len,
                     const char *dst, Py_ssize_t lastscan,
                     Py_ssize_t lastpos, Py_ssize_t scan)
{
    Py_ssize_t i, score = 0, best_score = 0, best_length = 0;

    for (i = 0; lastscan + i < scan && lastpos + i < src_len;) {
        if (src[lastpos + i] == dst[lastscan + i])
            score++;
        i++;
        if (2 * score - i > 2 * best_score - best_length) {
            best_score = score;
            best_length = i;
        }
    }
    return best_length;
}

/* find the best backward match length */
static Py_ssize_t
backward_match_length(const char *src, const char *dst,
                      Py_ssize_t lastscan, Py_ssize_t scan, Py_ssize_t pos)
{
    Py_ssize_t i, score = 0, best_score = 0, best_length = 0;

    for (i = 1; scan >= lastscan + i && pos >= i; i++) {
        if (src[pos - i] == dst[scan - i])
            score++;
        if (2 * score - i > 2 * best_score - best_length) {
            best_score = score;
            best_length = i;
        }
    }
    return best_length;
}

/* resolve overlap between forward and backward matches */
static void
adjust_overlap(const char *src, const char *dst,
               Py_ssize_t lastscan, Py_ssize_t lastpos, Py_ssize_t scan,
               Py_ssize_t pos, Py_ssize_t *lenf, Py_ssize_t *lenb)
{
    Py_ssize_t score = 0, best_score = 0, best_length = 0, i;
    Py_ssize_t overlap;

    if (lastscan + *lenf <= scan - *lenb)
        return;
    overlap = (lastscan + *lenf) - (scan - *lenb);

    for (i = 0; i < overlap; i++) {
        if (dst[lastscan + *lenf - overlap + i] ==
            src[lastpos + *lenf - overlap + i])
            score++;
        if (dst[scan - *lenb + i] == src[pos - *lenb + i])
            score--;
        if (score > best_score) {
            best_score = score;
            best_length = i + 1;
        }
    }

    *lenf += best_length - overlap;
    *lenb -= best_length;
}

/* find the next match worth switching to */
static Py_ssize_t
find_next_match(const Py_ssize_t *sa,
                const char *src, Py_ssize_t src_len,
                const char *dst, Py_ssize_t dst_len,
                Py_ssize_t lastoffset,
                Py_ssize_t *scan, Py_ssize_t *pos, Py_ssize_t *len)
{
    Py_ssize_t cont_score = 0;  /* matches at previous source offset */
    Py_ssize_t dst_pos;         /* current destination search position */
    Py_ssize_t score_end;       /* end of destination range scored so far */

    Py_BEGIN_ALLOW_THREADS  /* release GIL */
    dst_pos = *scan + *len;
    for (score_end = dst_pos; dst_pos < dst_len; dst_pos++) {
        *len = search(sa, src, src_len, dst + dst_pos, dst_len - dst_pos,
                      0, src_len, pos);
        for (; score_end < dst_pos + *len; score_end++)
            if (score_end + lastoffset < src_len &&
                      src[score_end + lastoffset] == dst[score_end])
                cont_score++;
        if ((*len == cont_score && *len != 0) || *len > cont_score + 8)
            break;
        if (dst_pos + lastoffset < src_len &&
                  src[dst_pos + lastoffset] == dst[dst_pos])
            cont_score--;
    }
    Py_END_ALLOW_THREADS

    *scan = dst_pos;
    return cont_score;
}

/* construct the control, diff and extra blocks */
static int
compute_diff(const char *src, Py_ssize_t src_len,
             const char *dst, Py_ssize_t dst_len,
             const Py_ssize_t *sa, DiffResult *result)
{
    Py_ssize_t lastscan = 0;    /* destination position of previous match */
    Py_ssize_t lastpos = 0;     /* source position of previous match */
    Py_ssize_t lastoffset = 0;  /* source minus destination position */
    Py_ssize_t scan = 0;        /* current destination search position */
    Py_ssize_t pos = 0;         /* source position of best match */
    Py_ssize_t len = 0;         /* length of best match */

    /* perform diff */
    while (scan < dst_len) {
        Py_ssize_t cont_score;  /* matches at previous source offset */

        if (PyErr_CheckSignals() < 0)
            return -1;

        cont_score = find_next_match(sa, src, src_len, dst, dst_len,
                                     lastoffset, &scan, &pos, &len);

        /* emit data preceding the new match, or all remaining data at EOF */
        if (len != cont_score || scan == dst_len) {
            Py_ssize_t lenb = 0;  /* length of backward match */
            Py_ssize_t lenf;      /* length of forward match */
            Py_ssize_t extra_len, z;

            lenf = forward_match_length(src, src_len, dst,
                                        lastscan, lastpos, scan);
            if (scan < dst_len)
                lenb = backward_match_length(src, dst, lastscan, scan, pos);
            adjust_overlap(src, dst, lastscan, lastpos, scan, pos,
                           &lenf, &lenb);

            assert(lenf >= 0 && lenb >= 0);
            assert(lastpos >= 0 && lenf <= src_len - lastpos);
            assert(lastscan >= 0 && lenf <= dst_len - lastscan);
            assert(lastscan + lenf <= scan - lenb);

            extra_len = (scan - lenb) - (lastscan + lenf);
            z = (pos - lenb) - (lastpos + lenf);
            if (emit_data(src, dst, result,
                          lenf, extra_len, z, lastscan, lastpos) < 0)
                return -1;

            lastscan = scan - lenb;
            lastpos = pos - lenb;
            lastoffset = pos - scan;
        }
    }

    assert(result->diff_len <= dst_len && result->extra_len <= dst_len);
    assert(result->diff_len + result->extra_len == dst_len);
    assert(PyByteArray_GET_SIZE(result->control) % 24 == 0);
    return 0;
}


/* return the control, diff and extra blocks for two byte strings */
static PyObject *
mod_diff(PyObject *module, PyObject *args)
{
    DiffResult diff;
    Py_ssize_t src_len, dst_len, *sa = NULL;
    char *src, *dst;
    PyObject *result = NULL;

    if (!PyArg_ParseTuple(args, "s#s#",
                          &src, &src_len,
                          &dst, &dst_len))
        return NULL;

    if (diff_init(&diff, dst_len) < 0)
        return NULL;

    /* perform suffix sort on source data */
    sa = build_suffix_array(src, src_len);
    if (sa == NULL)
        goto finish;

    if (compute_diff(src, src_len, dst, dst_len, sa, &diff) < 0)
        goto finish;

    result = diff_build(&diff);
 finish:
    PyMem_Free(sa);
    diff_clear(&diff);
    return result;
}

/* -------------------------  patch application  ------------------------- */

/* decode 8 bytes to int64 */
static int64_t
decode_int64(const char *str)
{
    uint64_t value = 0;
    int64_t magnitude;
    int i;

    for (i = 0; i < 8; i++)
        value |= ((uint64_t) (unsigned char) str[i]) << (i * 8);

    magnitude = value & INT64_MAX;
    return value >> 63 ? -magnitude : magnitude;
}

/* decode a 24-byte control tuple */
static void
decode_tuple(const char *str, int64_t *x, int64_t *y, int64_t *z)
{
    *x = decode_int64(str);
    *y = decode_int64(str + 8);
    *z = decode_int64(str + 16);
}

#define CORRUPT(s) PyErr_SetString(PyExc_ValueError, "corrupt patch (" s ")")

/* update the source offset while checking for overflow */
static int
update_src_pos(int64_t *src_pos, int64_t increment)
{
    if ((increment > 0 && *src_pos > INT64_MAX - increment) ||
        (increment < 0 && *src_pos < INT64_MIN - increment)) {
        CORRUPT("offset overflow");
        return -1;
    }
    *src_pos += increment;
    return 0;
}

/* apply control, diff and extra blocks to the source data */
static PyObject *
mod_patch(PyObject *module, PyObject *args)
{
    char *src, *dst, *control_block, *diff_block, *extra_block;
    Py_ssize_t src_len, control_len;
    Py_ssize_t diff_remaining, extra_remaining, dst_remaining, i;
    PyObject *result;
    int64_t src_pos = 0;

    if (!PyArg_ParseTuple(args, "s#s#s#s#",
                          &src, &src_len,
                          &control_block, &control_len,
                          &diff_block, &diff_remaining,
                          &extra_block, &extra_remaining))
        return NULL;

    if (diff_remaining > PY_SSIZE_T_MAX - extra_remaining) {
        PyErr_NoMemory();
        return NULL;
    }
    dst_remaining = diff_remaining + extra_remaining;

    if (control_len % 24) {
        CORRUPT("invalid control block");
        return NULL;
    }

    result = PyBytes_FromStringAndSize(NULL, dst_remaining);
    if (result == NULL)
        return NULL;
    dst = PyBytes_AS_STRING(result);

    for (i = 0; i < control_len; i += 24) {
        int64_t x, y, z, j;

        decode_tuple(control_block + i, &x, &y, &z);
        if (x < 0 || x > diff_remaining) {
            CORRUPT("x out of range");
            goto error;
        }
        memcpy(dst, diff_block, x);
        diff_block += x;
        diff_remaining -= x;
        for (j = 0; j < x; j++) {
            /* Check bounds without overflowing src_pos + j. */
            if (src_pos >= -j && src_pos < src_len - j)
                dst[j] += src[src_pos + j];
        }
        dst += x;
        dst_remaining -= x;
        if (y < 0 || y > extra_remaining) {
            CORRUPT("y out of range");
            goto error;
        }
        memcpy(dst, extra_block, y);
        extra_block += y;
        extra_remaining -= y;
        dst += y;
        dst_remaining -= y;
        if (update_src_pos(&src_pos, x) < 0 ||
            update_src_pos(&src_pos, z) < 0)
            goto error;
        assert(diff_remaining + extra_remaining == dst_remaining);
    }

    if (dst_remaining != 0) {
        CORRUPT("incomplete output");
        goto error;
    }
    /* Complete output implies that both input blocks were fully consumed. */
    assert(diff_remaining == 0 && extra_remaining == 0);

    return result;

error:
    Py_DECREF(result);
    return NULL;
}

#undef CORRUPT

/* ----------------------  auxiliary Python bindings  -------------------- */

/* encode an integer as 8 bytes */
static PyObject *
mod_encode_int64(PyObject *module, PyObject *value)
{
    char str[8];
    int64_t x;

    x = PyLong_AsLongLong(value);
    if (x == -1 && PyErr_Occurred())
        return NULL;
    if (encode_int64(str, x) < 0)
        return NULL;
    return PyBytes_FromStringAndSize((char *) str, 8);
}

/* decode an integer from 8 bytes */
static PyObject *
mod_decode_int64(PyObject *module, PyObject *bytes)
{
    Py_ssize_t size;
    char *str;

    if (PyBytes_AsStringAndSize(bytes, &str, &size) < 0)
        return NULL;
    if (size != 8) {
        PyErr_SetString(PyExc_ValueError, "8 bytes expected");
        return NULL;
    }
    return PyLong_FromLongLong(decode_int64(str));
}

/* return the suffix array for a byte string */
static PyObject *
mod_suffix_array(PyObject *module, PyObject *bytes)
{
    Py_ssize_t *sa;
    PyObject *list;
    Py_ssize_t size, i;
    char *str;

    if (PyBytes_AsStringAndSize(bytes, &str, &size) < 0)
        return NULL;

    sa = build_suffix_array(str, size);
    if (sa == NULL)
        return NULL;

    list = PyList_New(size + 1);
    if (list == NULL)
        goto error;

    for (i = 0; i <= size; i++) {
        PyObject *item = PyLong_FromSsize_t(sa[i]);
        if (item == NULL)
            goto error;
        PyList_SET_ITEM(list, i, item);
    }

    PyMem_Free(sa);
    return list;
 error:
    Py_XDECREF(list);
    PyMem_Free(sa);
    return NULL;
}

/* declaration of methods supported by this module */
static PyMethodDef module_functions[] = {
    {"diff",         mod_diff,         METH_VARARGS},
    {"patch",        mod_patch,        METH_VARARGS},
    {"encode_int64", mod_encode_int64, METH_O},
    {"decode_int64", mod_decode_int64, METH_O},
    {"suffix_array", mod_suffix_array, METH_O},
    {NULL}  /* Sentinel */
};

static PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT, "core", 0, -1, module_functions,
};

/* initialize extension module */
PyMODINIT_FUNC
PyInit_core(void)
{
    PyObject *m;

    m = PyModule_Create(&moduledef);
    if (m == NULL)
        return NULL;

    if (PyModule_AddStringMacro(m, BSDIFF4_VERSION) < 0)
        goto error;

#ifdef Py_GIL_DISABLED
    if (PyUnstable_Module_SetGIL(m, Py_MOD_GIL_NOT_USED) < 0)
        goto error;
#endif

#ifndef NDEBUG
    if (PyModule_AddIntConstant(m, "DEBUG", 1) < 0)
        goto error;
#endif

    return m;
 error:
    Py_DECREF(m);
    return NULL;
}
