/*
  The code below is mostly derived from cx_bsdiff (written by Anthony
  Tuininga, http://cx-bsdiff.sourceforge.net/).  The cx_bsdiff code in
  turn was derived from bsdiff, the standalone utility produced for BSD
  which can be found at http://www.daemonology.net/bsdiff.
*/

#define PY_SSIZE_T_CLEAN
#include <Python.h>


static void
split(off_t *I, off_t *V, off_t start, off_t len, off_t h)
{
    off_t i, j, k, x, tmp, jj, kk;

    if (len < 16) {
        for (k = start; k < start + len; k += j) {
            j = 1;
            x = V[I[k] + h];
            for (i = 1; k + i < start + len; i++) {
                if (V[I[k + i] + h] < x) {
                    x = V[I[k + i] + h];
                    j = 0;
                }
                if (V[I[k + i] + h] == x) {
                    tmp = I[k + j];
                    I[k + j] = I[k + i];
                    I[k + i] = tmp;
                    j++;
                }
            }
            for (i = 0; i < j; i++)
                V[I[k + i]] = k + j - 1;
            if (j == 1)
                I[k] = -1;
        }

    } else {

        jj = 0;
        kk = 0;
        x = V[I[start + len / 2] + h];
        for (i = start; i < start + len; i++) {
            if (V[I[i] + h] < x)
                jj++;
            if (V[I[i] + h] == x)
                kk++;
        }
        jj += start;
        kk += jj;

        j = 0;
        k = 0;
        i = start;
        while (i < jj) {
            if (V[I[i] + h] < x) {
                i++;
            } else if (V[I[i] + h] == x) {
                tmp = I[i];
                I[i] = I[jj + j];
                I[jj + j] = tmp;
                j++;
            } else {
                tmp = I[i];
                I[i] = I[kk + k];
                I[kk + k] = tmp;
                k++;
            }
        }

        while (jj + j < kk) {
            if (V[I[jj + j] + h] == x) {
                j++;
            } else {
                tmp = I[jj + j];
                I[jj + j] = I[kk + k];
                I[kk + k] = tmp;
                k++;
            }
        }

        if (jj > start)
            split(I, V, start, jj - start, h);

        for (i = 0; i < kk - jj; i++)
            V[I[jj + i]] = kk - 1;
        if (jj == kk - 1)
            I[jj] = -1;
        if (start + len > kk)
            split(I, V, kk, start + len - kk, h);
    }
}


static void
qsufsort(off_t *I, off_t *V, unsigned char *old, off_t oldsize)
{
    off_t buckets[256], i, h, len;

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
        len = 0;
        for (i = 0; i < oldsize + 1;) {
            if (I[i] < 0) {
                len -= I[i];
                i -= I[i];
            } else {
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


static off_t
matchlen(unsigned char *old, off_t oldsize,
         unsigned char *new, off_t newsize)
{
    off_t i;

    for (i = 0; (i < oldsize) && (i < newsize); i++)
        if (old[i] != new[i])
            break;
    return i;
}


static off_t
search(off_t *I,
       unsigned char *old, off_t oldsize,
       unsigned char *new, off_t newsize,
       off_t st, off_t en, off_t *pos)
{
    off_t x, y;

    if (en - st < 2) {
        x = matchlen(old + I[st], oldsize - I[st], new, newsize);
        y = matchlen(old + I[en], oldsize - I[en], new, newsize);

        if (x > y) {
            *pos = I[st];
            return x;
        } else {
            *pos = I[en];
            return y;
        }
    }

    x = st + (en - st) / 2;
    if (memcmp(old + I[x], new, Py_MIN(oldsize - I[x], newsize)) < 0) {
        return search(I, old, oldsize, new, newsize, x, en, pos);
    } else {
        return search(I, old, oldsize, new, newsize, st, x, pos);
    }
}


typedef struct {
    PyObject *controls;     /* list of control tuples */
    unsigned char *diff;    /* difference block */
    unsigned char *extra;   /* extra block */
    off_t diff_len;         /* length of difference block */
    off_t extra_len;        /* length of extra block */
} DiffResult;

static void
clear_diff_result(DiffResult *result)
{
    Py_XDECREF(result->controls);
    PyMem_Free(result->diff);
    PyMem_Free(result->extra);
}

static int
append_control(PyObject *controls, off_t x, off_t y, off_t z)
{
    PyObject *tuple;
    int res;

    tuple = Py_BuildValue("(LLL)",
                          (long long) x, (long long) y, (long long) z);
    if (!tuple)
        return -1;
    res = PyList_Append(controls, tuple);
    Py_DECREF(tuple);
    return res;
}

static int
compute_diff(char *origData, Py_ssize_t origDataLength,
             char *newData, Py_ssize_t newDataLength, DiffResult *result)
{
    off_t lastscan, lastpos, lastoffset, oldscore, scsc, overlap, Ss, lens;
    off_t *I = NULL, *V = NULL;
    off_t scan, pos, len, s, Sf, lenf, Sb, lenb, i;

    result->controls = PyList_New(0);
    if (!result->controls)
        goto error;

    /* perform sort on original data */
    I = PyMem_Malloc((origDataLength + 1) * sizeof(off_t));
    if (!I) {
        PyErr_NoMemory();
        goto error;
    }
    V = PyMem_Malloc((origDataLength + 1) * sizeof(off_t));
    if (!V) {
        PyErr_NoMemory();
        goto error;
    }
    Py_BEGIN_ALLOW_THREADS  /* release GIL */
    qsufsort(I, V, (unsigned char *) origData, origDataLength);
    Py_END_ALLOW_THREADS
    PyMem_Free(V);
    V = NULL;

    /* allocate memory for the diff and extra blocks */
    result->diff = PyMem_Malloc(newDataLength + 1);
    if (!result->diff) {
        PyErr_NoMemory();
        goto error;
    }
    result->extra = PyMem_Malloc(newDataLength + 1);
    if (!result->extra) {
        PyErr_NoMemory();
        goto error;
    }
    result->diff_len = 0;
    result->extra_len = 0;

    /* perform the diff */
    len = 0;
    scan = 0;
    lastscan = 0;
    lastpos = 0;
    lastoffset = 0;
    pos = 0;
    while (scan < newDataLength) {
        if (PyErr_CheckSignals() < 0)
            goto error;
        oldscore = 0;

        Py_BEGIN_ALLOW_THREADS  /* release GIL */
        for (scsc = scan += len; scan < newDataLength; scan++) {
            len = search(I, (unsigned char *) origData, origDataLength,
                         (unsigned char *) newData + scan,
                         newDataLength - scan, 0, origDataLength, &pos);
            for (; scsc < scan + len; scsc++)
                if ((scsc + lastoffset < origDataLength) &&
                          (origData[scsc + lastoffset] == newData[scsc]))
                    oldscore++;
            if (((len == oldscore) && (len != 0)) || (len > oldscore + 8))
                break;
            if ((scan + lastoffset < origDataLength) &&
                      (origData[scan + lastoffset] == newData[scan]))
                oldscore--;
        }
        Py_END_ALLOW_THREADS

        if ((len != oldscore) || (scan == newDataLength)) {
            s = 0;
            Sf = 0;
            lenf = 0;
            for (i = 0; (lastscan + i < scan) &&
                     (lastpos + i < origDataLength);) {
                if (origData[lastpos + i] == newData[lastscan + i])
                    s++;
                i++;
                if (s * 2 - i > Sf * 2 - lenf) {
                    Sf = s;
                    lenf = i;
                }
            }

            lenb = 0;
            if (scan < newDataLength) {
                s = 0;
                Sb = 0;
                for (i = 1; (scan >= lastscan + i) && (pos >= i); i++) {
                    if (origData[pos - i] == newData[scan - i])
                        s++;
                    if (s * 2 - i > Sb * 2 - lenb) {
                        Sb = s;
                        lenb = i;
                    }
                }
            }

            if (lastscan + lenf > scan - lenb) {
                overlap = (lastscan + lenf) - (scan - lenb);
                s = 0;
                Ss = 0;
                lens = 0;
                for (i = 0; i < overlap; i++) {
                    if (newData[lastscan + lenf - overlap + i] ==
                            origData[lastpos + lenf - overlap + i])
                        s++;
                    if (newData[scan - lenb + i] == origData[pos - lenb + i])
                        s--;
                    if (s > Ss) {
                        Ss = s;
                        lens = i + 1;
                    }
                }

                lenf += lens - overlap;
                lenb -= lens;
            }

            for (i = 0; i < lenf; i++)
                result->diff[result->diff_len + i] =
                    newData[lastscan + i] - origData[lastpos + i];
            for (i = 0; i < (scan - lenb) - (lastscan + lenf); i++)
                result->extra[result->extra_len + i] =
                    newData[lastscan + lenf + i];

            result->diff_len += lenf;
            result->extra_len += (scan - lenb) - (lastscan + lenf);

            if (append_control(
                    result->controls,
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
    PyMem_Free(V);
    return -1;
}

static PyObject *
build_diff_result(DiffResult *result)
{
    PyObject *diff, *extra, *res;

    diff = PyBytes_FromStringAndSize((char *) result->diff, result->diff_len);
    if (!diff)
        return NULL;
    extra = PyBytes_FromStringAndSize((char *) result->extra,
                                      result->extra_len);
    if (!extra) {
        Py_DECREF(diff);
        return NULL;
    }
    res = PyTuple_Pack(3, result->controls, diff, extra);
    Py_DECREF(diff);
    Py_DECREF(extra);
    return res;
}

/* performs a diff between the two data streams and returns a tuple
   containing the control, diff and extra blocks that bsdiff produces
*/
static PyObject *
diff(PyObject *self, PyObject *args)
{
    DiffResult result = {NULL, NULL, NULL, 0, 0};
    Py_ssize_t origDataLength, newDataLength;
    char *origData, *newData;
    PyObject *res;

    if (!PyArg_ParseTuple(args, "s#s#",
                          &origData, &origDataLength,
                          &newData, &newDataLength))
        return NULL;

    if (compute_diff(origData, origDataLength,
                     newData, newDataLength, &result) < 0)
        res = NULL;
    else
        res = build_diff_result(&result);
    clear_diff_result(&result);
    return res;
}


/* takes the original data and the control, diff and extra blocks produced
   by bsdiff and returns the new data
*/
static PyObject *
patch(PyObject *self, PyObject *args)
{
    char *origData, *newData, *diffBlock, *extraBlock, *diffPtr, *extraPtr;
    Py_ssize_t origDataLength, newDataLength, diffBlockLength, extraBlockLength;
    PyObject *controlTuples, *tuple, *results;
    off_t oldpos, newpos, x, y, z;
    Py_ssize_t i, j, numTuples;

    if (!PyArg_ParseTuple(args, "s#nO!s#s#",
                          &origData, &origDataLength, &newDataLength,
                          &PyList_Type, &controlTuples,
                          &diffBlock, &diffBlockLength,
                          &extraBlock, &extraBlockLength))
        return NULL;

    if (newDataLength < 0) {
        PyErr_SetString(PyExc_ValueError, "negative new data length");
        return NULL;
    }

    /* allocate the memory for the new data */
    newData = PyMem_Malloc(newDataLength + 1);
    if (!newData)
        return PyErr_NoMemory();

    oldpos = 0;
    newpos = 0;
    diffPtr = diffBlock;
    extraPtr = extraBlock;
    numTuples = PyList_GET_SIZE(controlTuples);
    for (i = 0; i < numTuples; i++) {
        tuple = PyList_GET_ITEM(controlTuples, i);
        if (!PyTuple_Check(tuple)) {
            PyMem_Free(newData);
            PyErr_SetString(PyExc_TypeError, "expecting tuple");
            return NULL;
        }
        if (PyTuple_GET_SIZE(tuple) != 3) {
            PyMem_Free(newData);
            PyErr_SetString(PyExc_TypeError, "expecting tuple of size 3");
            return NULL;
        }
        x = PyLong_AsLong(PyTuple_GET_ITEM(tuple, 0));
        if (x == -1 && PyErr_Occurred())
            goto error;
        y = PyLong_AsLong(PyTuple_GET_ITEM(tuple, 1));
        if (y == -1 && PyErr_Occurred())
            goto error;
        z = PyLong_AsLong(PyTuple_GET_ITEM(tuple, 2));
        if (z == -1 && PyErr_Occurred())
            goto error;
        if (x < 0 || x > newDataLength - newpos ||
                x > diffBlock + diffBlockLength - diffPtr) {
            PyMem_Free(newData);
            PyErr_SetString(PyExc_ValueError, "corrupt patch (overflow)");
            return NULL;
        }
        memcpy(newData + newpos, diffPtr, x);
        diffPtr += x;
        for (j = 0; j < x; j++)
            if ((oldpos + j >= 0) && (oldpos + j < origDataLength))
                newData[newpos + j] += origData[oldpos + j];
        newpos += x;
        oldpos += x;
        if (y < 0 || y > newDataLength - newpos ||
                y > extraBlock + extraBlockLength - extraPtr) {
            PyMem_Free(newData);
            PyErr_SetString(PyExc_ValueError, "corrupt patch (overflow)");
            return NULL;
        }
        memcpy(newData + newpos, extraPtr, y);
        extraPtr += y;
        newpos += y;
        oldpos += z;
    }

    /* confirm that a valid patch was applied */
    if (newpos != newDataLength ||
            diffPtr != diffBlock + diffBlockLength ||
            extraPtr != extraBlock + extraBlockLength) {
        PyMem_Free(newData);
        PyErr_SetString(PyExc_ValueError, "corrupt patch (underflow)");
        return NULL;
    }

    results = PyBytes_FromStringAndSize(newData, newDataLength);
    PyMem_Free(newData);
    return results;

error:
    PyMem_Free(newData);
    return NULL;
}


/* encode an integer value as 8 bytes */
static PyObject *
encode_int64(PyObject *self, PyObject *value)
{
    PY_INT64_T x;
    char str[8], sign = 0x00;
    int i;

    x = PyLong_AsLongLong(value);
    if (x == -1 && PyErr_Occurred())
        return NULL;

    if (x == PY_LLONG_MIN) {
        PyErr_SetString(PyExc_OverflowError, "cannot encode -2**63");
        return NULL;
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
    return PyBytes_FromStringAndSize(str, 8);
}

/* decode an off_t value from 8 bytes */
static PyObject *
decode_int64(PyObject *self, PyObject *bytes)
{
    PY_UINT64_T value = 0;
    PY_INT64_T magnitude;
    Py_ssize_t size;
    char *str;
    int i;

    if (PyBytes_AsStringAndSize(bytes, &str, &size) < 0)
        return NULL;
    if (size != 8) {
        PyErr_SetString(PyExc_ValueError, "8 bytes expected");
        return NULL;
    }

    for (i = 0; i < 8; i++)
        value |= ((PY_UINT64_T) (unsigned char) str[i]) << (i * 8);

    magnitude = value & PY_LLONG_MAX;
    return PyLong_FromLongLong(value >> 63 ? -magnitude : magnitude);
}


/* declaration of methods supported by this module */
static PyMethodDef module_functions[] = {
    {"diff",         diff,         METH_VARARGS},
    {"patch",        patch,        METH_VARARGS},
    {"encode_int64", encode_int64, METH_O},
    {"decode_int64", decode_int64, METH_O},
    {NULL}  /* Sentinel */
};

static PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT, "core", 0, -1, module_functions,
};

PyMODINIT_FUNC
PyInit_core(void)
{
    PyObject *m;

    m = PyModule_Create(&moduledef);
    if (m == NULL)
        return NULL;

    return m;
}
