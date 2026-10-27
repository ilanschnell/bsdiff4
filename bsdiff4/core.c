/*
  The code below is mostly derived from cx_bsdiff (written by Anthony
  Tuininga, http://cx-bsdiff.sourceforge.net/).  The cx_bsdiff code in
  turn was derived from bsdiff, the standalone utility produced for BSD
  which can be found at http://www.daemonology.net/bsdiff.
*/

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>


/* swap two suffix array entries */
static inline void
swap_indices(Py_ssize_t *a, Py_ssize_t *b)
{
    Py_ssize_t tmp = *a;
    *a = *b;
    *b = tmp;
}

/* sort and rank a small suffix group */
static void
split_small(Py_ssize_t *I, Py_ssize_t *V, Py_ssize_t start,
            Py_ssize_t len, Py_ssize_t h)
{
    Py_ssize_t j, k;

    for (k = start; k < start + len; k += j) {
        Py_ssize_t i, x;

        j = 1;
        x = V[I[k] + h];
        for (i = 1; k + i < start + len; i++) {
            if (V[I[k + i] + h] < x) {
                x = V[I[k + i] + h];
                j = 0;
            }
            if (V[I[k + i] + h] == x) {
                swap_indices(&I[k + j], &I[k + i]);
                j++;
            }
        }
        for (i = 0; i < j; i++)
            V[I[k + i]] = k + j - 1;
        if (j == 1)
            I[k] = -1;
    }
}

/* partition a suffix group around a pivot rank */
static void
partition_group(Py_ssize_t *I, Py_ssize_t *V, Py_ssize_t start,
                Py_ssize_t len, Py_ssize_t h,
                Py_ssize_t *lower, Py_ssize_t *upper)
{
    Py_ssize_t i, j, k, x, jj = 0, kk = 0;

    x = V[I[start + len / 2] + h];
    for (i = start; i < start + len; i++) {
        if (V[I[i] + h] < x)
            jj++;
        if (V[I[i] + h] == x)
            kk++;
    }
    jj += start;
    kk += jj;

    j = k = 0;
    i = start;
    while (i < jj) {
        if (V[I[i] + h] < x) {
            i++;
        }
        else if (V[I[i] + h] == x) {
            swap_indices(&I[i], &I[jj + j]);
            j++;
        }
        else {
            swap_indices(&I[i], &I[kk + k]);
            k++;
        }
    }

    while (jj + j < kk) {
        if (V[I[jj + j] + h] == x) {
            j++;
        }
        else {
            swap_indices(&I[jj + j], &I[kk + k]);
            k++;
        }
    }

    *lower = jj;
    *upper = kk;
}

/* recursively split and rank a suffix group */
static void
split(Py_ssize_t *I, Py_ssize_t *V, Py_ssize_t start,
      Py_ssize_t len, Py_ssize_t h)
{
    Py_ssize_t lower, upper, i;

    if (len < 16) {
        split_small(I, V, start, len, h);
        return;
    }

    partition_group(I, V, start, len, h, &lower, &upper);

    if (lower > start)
        split(I, V, start, lower - start, h);

    for (i = lower; i < upper; i++)
        V[I[i]] = upper - 1;
    if (upper - lower == 1)
        I[lower] = -1;
    if (start + len > upper)
        split(I, V, upper, start + len - upper, h);
}

/* construct the suffix array for old */
static void
qsufsort(Py_ssize_t *I, Py_ssize_t *V,
         const unsigned char *old, Py_ssize_t oldsize)
{
    Py_ssize_t buckets[256], i, h;

    for (i = 0; i < 256; i++)
        buckets[i] = 0;
    for (i = 0; i < oldsize; i++)
        buckets[old[i]]++;
    for (i = 1; i < 256; i++)
        buckets[i] += buckets[i - 1];
    for (i = 255; i > 0; i--)
        buckets[i] = buckets[i - 1];
    buckets[0] = 0;

    for (i = 0; i < oldsize; i++)
        I[++buckets[old[i]]] = i;
    I[0] = oldsize;
    for (i = 0; i < oldsize; i++)
        V[i] = buckets[old[i]];
    V[oldsize] = 0;
    for (i = 1; i < 256; i++)
        if (buckets[i] == buckets[i - 1] + 1)
            I[buckets[i]] = -1;
    I[0] = -1;

    for (h = 1; I[0] != -(oldsize + 1); h += h) {
        Py_ssize_t len = 0;

        for (i = 0; i < oldsize + 1;) {
            if (I[i] < 0) {
                len -= I[i];
                i -= I[i];
            }
            else {
                if (len)
                    I[i - len] = -len;
                len = V[I[i]] + 1 - i;
                split(I, V, i, len, h);
                i += len;
                len=0;
            }
        }
        if (len)
            I[i - len] = -len;
    }

    for (i = 0; i < oldsize + 1; i++)
        I[V[i]] = i;
}

/* construct suffix array */
static Py_ssize_t *
build_suffix_array(const char *old, Py_ssize_t oldsize)
{
    Py_ssize_t *I;  /* suffix array */
    Py_ssize_t *V;  /* temporary rank storage */

    I = PyMem_Malloc((oldsize + 1) * sizeof(Py_ssize_t));
    if (I == NULL) {
        PyErr_NoMemory();
        return NULL;
    }

    V = PyMem_Malloc((oldsize + 1) * sizeof(Py_ssize_t));
    if (V == NULL) {
        PyErr_NoMemory();
        PyMem_Free(I);
        return NULL;
    }

    Py_BEGIN_ALLOW_THREADS  /* release GIL */
    qsufsort(I, V, (const unsigned char *) old, oldsize);
    Py_END_ALLOW_THREADS

    PyMem_Free(V);
    return I;
}

/* return the length of the common prefix */
static Py_ssize_t
matchlen(const unsigned char *old, Py_ssize_t oldsize,
         const unsigned char *new, Py_ssize_t newsize)
{
    Py_ssize_t i = 0;

    while (i < oldsize && i < newsize && old[i] == new[i])
        i++;
    return i;
}

/* find the suffix with the longest prefix match */
static Py_ssize_t
search(const Py_ssize_t *I,
       const unsigned char *old, Py_ssize_t oldsize,
       const unsigned char *new, Py_ssize_t newsize,
       Py_ssize_t st, Py_ssize_t en, Py_ssize_t *pos)
{
    Py_ssize_t x, y;

    if (en - st < 2) {
        x = matchlen(old + I[st], oldsize - I[st], new, newsize);
        y = matchlen(old + I[en], oldsize - I[en], new, newsize);

        if (x > y) {
            *pos = I[st];
            return x;
        }
        else {
            *pos = I[en];
            return y;
        }
    }

    x = st + (en - st) / 2;
    if (memcmp(old + I[x], new, Py_MIN(oldsize - I[x], newsize)) < 0)
        return search(I, old, oldsize, new, newsize, x, en, pos);
    else
        return search(I, old, oldsize, new, newsize, st, x, pos);
}

typedef struct {
    PyObject *control;      /* control block as bytearray */
    unsigned char *diff;    /* difference block */
    unsigned char *extra;   /* extra block */
    Py_ssize_t diff_len;    /* length of difference block */
    Py_ssize_t extra_len;   /* length of extra block */
} DiffResult;

/* release resources owned by a diff result */
static void
clear_diff_result(DiffResult *result)
{
    Py_XDECREF(result->control);
    PyMem_Free(result->diff);
    PyMem_Free(result->extra);
}

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

/* append tuple to control block */
static int
append_control(PyObject *control, Py_ssize_t x, Py_ssize_t y, Py_ssize_t z)
{
    char *str;
    Py_ssize_t size;

    size = PyByteArray_GET_SIZE(control);
    if (size > PY_SSIZE_T_MAX - 24) {
        PyErr_NoMemory();
        return -1;
    }
    if (PyByteArray_Resize(control, size + 24) < 0)
        return -1;

    str = (char *) PyByteArray_AS_STRING(control) + size;
    if (encode_int64(str, x) < 0 ||
        encode_int64(str + 8, y) < 0 ||
        encode_int64(str + 16, z) < 0)
        return -1;

    return 0;
}

/* find the best forward match length */
static Py_ssize_t
forward_match_length(const char *origData, Py_ssize_t origDataLength,
                     const char *newData, Py_ssize_t lastscan,
                     Py_ssize_t lastpos, Py_ssize_t scan)
{
    Py_ssize_t i, score = 0, best_score = 0, best_length = 0;

    for (i = 0; lastscan + i < scan && lastpos + i < origDataLength;) {
        if (origData[lastpos + i] == newData[lastscan + i])
            score++;
        i++;
        if (score * 2 - i > best_score * 2 - best_length) {
            best_score = score;
            best_length = i;
        }
    }
    return best_length;
}

/* find the best backward match length */
static Py_ssize_t
backward_match_length(const char *origData, const char *newData,
                      Py_ssize_t lastscan, Py_ssize_t scan, Py_ssize_t pos)
{
    Py_ssize_t i, score = 0, best_score = 0, best_length = 0;

    for (i = 1; scan >= lastscan + i && pos >= i; i++) {
        if (origData[pos - i] == newData[scan - i])
            score++;
        if (score * 2 - i > best_score * 2 - best_length) {
            best_score = score;
            best_length = i;
        }
    }
    return best_length;
}

/* resolve overlap between forward and backward matches */
static void
adjust_overlap(const char *origData, const char *newData,
               Py_ssize_t lastscan, Py_ssize_t lastpos, Py_ssize_t scan,
               Py_ssize_t pos, Py_ssize_t *lenf, Py_ssize_t *lenb)
{
    Py_ssize_t score = 0, best_score = 0, best_length = 0, i;
    Py_ssize_t overlap;

    if (lastscan + *lenf <= scan - *lenb)
        return;
    overlap = (lastscan + *lenf) - (scan - *lenb);

    for (i = 0; i < overlap; i++) {
        if (newData[lastscan + *lenf - overlap + i] ==
                origData[lastpos + *lenf - overlap + i])
            score++;
        if (newData[scan - *lenb + i] == origData[pos - *lenb + i])
            score--;
        if (score > best_score) {
            best_score = score;
            best_length = i + 1;
        }
    }

    *lenf += best_length - overlap;
    *lenb -= best_length;
}

/* construct the control, diff and extra blocks */
static int
compute_diff(const char *origData, Py_ssize_t origDataLength,
             const char *newData, Py_ssize_t newDataLength,
             DiffResult *result)
{
    Py_ssize_t lastscan, lastpos, lastoffset;
    Py_ssize_t scan, pos, len;
    Py_ssize_t *I;

    result->control = PyByteArray_FromStringAndSize(NULL, 0);
    if (result->control == NULL)
        return -1;

    /* perform sort on original data */
    I = build_suffix_array(origData, origDataLength);
    if (I == NULL)
        return -1;

    /* allocate memory for the diff and extra blocks */
    result->diff = PyMem_Malloc(newDataLength + 1);
    if (result->diff == NULL) {
        PyErr_NoMemory();
        goto error;
    }
    result->extra = PyMem_Malloc(newDataLength + 1);
    if (result->extra == NULL) {
        PyErr_NoMemory();
        goto error;
    }
    result->diff_len = 0;
    result->extra_len = 0;

    /* perform the diff */
    len = scan = lastscan = lastpos = lastoffset = pos = 0;
    while (scan < newDataLength) {
        Py_ssize_t oldscore = 0, scsc;

        if (PyErr_CheckSignals() < 0)
            goto error;

        Py_BEGIN_ALLOW_THREADS  /* release GIL */
        for (scsc = scan += len; scan < newDataLength; scan++) {
            len = search(I, (const unsigned char *) origData, origDataLength,
                         (const unsigned char *) newData + scan,
                         newDataLength - scan, 0, origDataLength, &pos);
            for (; scsc < scan + len; scsc++)
                if (scsc + lastoffset < origDataLength &&
                          origData[scsc + lastoffset] == newData[scsc])
                    oldscore++;
            if ((len == oldscore && len != 0) || len > oldscore + 8)
                break;
            if (scan + lastoffset < origDataLength &&
                      origData[scan + lastoffset] == newData[scan])
                oldscore--;
        }
        Py_END_ALLOW_THREADS

        if (len != oldscore || scan == newDataLength) {
            Py_ssize_t lenb = 0, lenf, i;

            lenf = forward_match_length(origData, origDataLength, newData,
                                        lastscan, lastpos, scan);
            if (scan < newDataLength)
                lenb = backward_match_length(origData, newData,
                                             lastscan, scan, pos);
            adjust_overlap(origData, newData, lastscan, lastpos, scan, pos,
                           &lenf, &lenb);

            for (i = 0; i < lenf; i++)
                result->diff[result->diff_len + i] =
                    newData[lastscan + i] - origData[lastpos + i];
            for (i = 0; i < (scan - lenb) - (lastscan + lenf); i++)
                result->extra[result->extra_len + i] =
                    newData[lastscan + lenf + i];

            result->diff_len += lenf;
            result->extra_len += (scan - lenb) - (lastscan + lenf);

            if (append_control(result->control,
                               lenf,
                               (scan - lenb) - (lastscan + lenf),
                               (pos - lenb) - (lastpos + lenf)) < 0)
                goto error;

            lastscan = scan - lenb;
            lastpos = pos - lenb;
            lastoffset = pos - scan;
        }
    }

    PyMem_Free(I);
    return 0;

error:
    PyMem_Free(I);
    return -1;
}

/* convert a diff result into Python objects */
static PyObject *
build_diff_result(DiffResult *result)
{
    PyObject *control, *diff, *extra, *res;

    control = PyBytes_FromObject(result->control);
    if (control == NULL)
        return NULL;

    diff = PyBytes_FromStringAndSize((char *) result->diff,
                                     result->diff_len);
    if (diff == NULL) {
        Py_DECREF(control);
        return NULL;
    }

    extra = PyBytes_FromStringAndSize((char *) result->extra,
                                      result->extra_len);
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

/* return the control, diff and extra blocks for two byte strings */
static PyObject *
mod_diff(PyObject *module, PyObject *args)
{
    DiffResult diff = {NULL, NULL, NULL, 0, 0};
    Py_ssize_t origDataLength, newDataLength;
    char *origData, *newData;
    PyObject *result;

    if (!PyArg_ParseTuple(args, "s#s#",
                          &origData, &origDataLength,
                          &newData, &newDataLength))
        return NULL;

    if (compute_diff(origData, origDataLength,
                     newData, newDataLength, &diff) < 0)
        result = NULL;
    else
        result = build_diff_result(&diff);

    clear_diff_result(&diff);
    return result;
}

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

/* update the source offset while checking for overflow */
static int
update_oldpos(int64_t *oldpos, int64_t increment)
{
    if ((increment > 0 && *oldpos > INT64_MAX - increment) ||
        (increment < 0 && *oldpos < INT64_MIN - increment)) {
        PyErr_SetString(PyExc_ValueError, "corrupt patch (offset overflow)");
        return -1;
    }
    *oldpos += increment;
    return 0;
}

/* apply control, diff and extra blocks to the original data */
static PyObject *
mod_patch(PyObject *module, PyObject *args)
{
    char *origData, *newData, *controlBlock, *diffBlock, *extraBlock;
    Py_ssize_t origDataLength, newDataLength, controlBlockLength;
    Py_ssize_t diffRemaining, extraRemaining;
    PyObject *result;
    Py_ssize_t newpos = 0, i;
    int64_t oldpos = 0;

    if (!PyArg_ParseTuple(args, "s#ns#s#s#",
                          &origData, &origDataLength, &newDataLength,
                          &controlBlock, &controlBlockLength,
                          &diffBlock, &diffRemaining,
                          &extraBlock, &extraRemaining))
        return NULL;

    if (newDataLength < 0) {
        PyErr_SetString(PyExc_ValueError, "negative new data length");
        return NULL;
    }
    if (controlBlockLength % 24) {
        PyErr_SetString(PyExc_ValueError, "incorrect control block");
        return NULL;
    }

    result = PyBytes_FromStringAndSize(NULL, newDataLength);
    if (result == NULL)
        return NULL;
    newData = PyBytes_AS_STRING(result);

    for (i = 0; i < controlBlockLength; i += 24) {
        int64_t x, y, z, j;

        decode_tuple(controlBlock + i, &x, &y, &z);
        if (x < 0 || x > newDataLength - newpos || x > diffRemaining) {
            PyErr_SetString(PyExc_ValueError, "corrupt patch (overflow)");
            goto error;
        }
        memcpy(newData + newpos, diffBlock, x);
        diffBlock += x;
        diffRemaining -= x;
        /* Check bounds without overflowing oldpos + j. */
        for (j = 0; j < x; j++)
            if (oldpos >= -j && oldpos < origDataLength - j)
                newData[newpos + j] += origData[oldpos + j];
        newpos += x;
        if (y < 0 || y > newDataLength - newpos || y > extraRemaining) {
            PyErr_SetString(PyExc_ValueError, "corrupt patch (overflow)");
            goto error;
        }
        memcpy(newData + newpos, extraBlock, y);
        extraBlock += y;
        extraRemaining -= y;
        newpos += y;
        if (update_oldpos(&oldpos, x) < 0 ||
            update_oldpos(&oldpos, z) < 0)
            goto error;
    }

    /* confirm that a valid patch was applied */
    if (newpos != newDataLength || diffRemaining != 0 ||
            extraRemaining != 0) {
        PyErr_SetString(PyExc_ValueError, "corrupt patch (underflow)");
        goto error;
    }

    return result;

error:
    Py_DECREF(result);
    return NULL;
}


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
    Py_ssize_t *I;
    PyObject *list;
    Py_ssize_t size, i;
    char *str;

    if (PyBytes_AsStringAndSize(bytes, &str, &size) < 0)
        return NULL;

    I = build_suffix_array(str, size);
    if (I == NULL)
        return NULL;

    list = PyList_New(size + 1);
    if (list == NULL)
        goto error;

    for (i = 0; i <= size; i++) {
        PyObject *item = PyLong_FromSsize_t(I[i]);
        if (item == NULL)
            goto error;
        PyList_SET_ITEM(list, i, item);
    }

    PyMem_Free(I);
    return list;
 error:
    Py_XDECREF(list);
    PyMem_Free(I);
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

#ifdef Py_GIL_DISABLED
    PyUnstable_Module_SetGIL(m, Py_MOD_GIL_NOT_USED);
#endif

    return m;
}
