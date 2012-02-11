/*
  The code below is mostly derived from cx_bsdiff (written by Anthony
  Tuininga, http://cx-bsdiff.sourceforge.net/).  The cx_bsdiff code in
  turn was derived from bsdiff, the standalone utility produced for BSD
  which can be found at http://www.daemonology.net/bsdiff.
*/

#include <Python.h>

#if PY_MAJOR_VERSION >= 3
#define IS_PY3K
#endif

#ifdef IS_PY3K
#include "bytesobject.h"
#define PyString_FromStringAndSize  PyBytes_FromStringAndSize
#define PyString_Check  PyBytes_Check
#define PyString_Size  PyBytes_Size
#define PyString_AsString  PyBytes_AsString
#endif

#define MIN(x, y)  (((x) < (y)) ? (x) : (y))


static void split(off_t *I, off_t *V, off_t start, off_t len, off_t h)
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


static void qsufsort(off_t *I, off_t *V, unsigned char *old, off_t oldsize)
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
                    I[i - len] =- len;
                len = V[I[i]] + 1 - i;
                split(I, V, i, len, h);
                i += len;
                len=0;
            }
        }
        if (len)
            I[i - len] =- len;
    }

    for (i = 0; i < oldsize + 1; i++)
        I[V[i]] = i;
}


static off_t matchlen(unsigned char *old, off_t oldsize,
                      unsigned char *new, off_t newsize)
{
    off_t i;

    for (i = 0; (i < oldsize) && (i < newsize); i++)
        if (old[i] != new[i])
            break;
    return i;
}


static off_t search(off_t *I,
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
    if (memcmp(old + I[x], new, MIN(oldsize - I[x], newsize)) < 0) {
        return search(I, old, oldsize, new, newsize, x, en, pos);
    } else {
        return search(I, old, oldsize, new, newsize, st, x, pos);
    }
}


/* performs a diff between the two data streams and returns a tuple
   containing the control, diff and extra blocks that bsdiff produces
*/
static PyObject* diff(PyObject* self, PyObject* args)
{
    off_t lastscan, lastpos, lastoffset, oldscore, scsc, overlap, Ss, lens;
    off_t *I, *V, dblen, eblen, scan, pos, len, s, Sf, lenf, Sb, lenb, i;
    PyObject *controlTuples, *tuple, *results, *temp;
    int origDataLength, newDataLength;
    char *origData, *newData;
    unsigned char *db, *eb;

    if (!PyArg_ParseTuple(args, "s#s#",
                          &origData, &origDataLength,
                          &newData, &newDataLength))
        return NULL;

    /* create the control tuple */
    controlTuples = PyList_New(0);
    if (!controlTuples)
        return NULL;

    /* perform sort on original data */
    I = PyMem_Malloc((origDataLength + 1) * sizeof(off_t));
    if (!I) {
        Py_DECREF(controlTuples);
        return PyErr_NoMemory();
    }
    V = PyMem_Malloc((origDataLength + 1) * sizeof(off_t));
    if (!V) {
        Py_DECREF(controlTuples);
        PyMem_Free(I);
        return PyErr_NoMemory();
    }
    qsufsort(I, V, (unsigned char *) origData, origDataLength);
    PyMem_Free(V);

    /* allocate memory for the diff and extra blocks */
    db = PyMem_Malloc(newDataLength + 1);
    if (!db) {
        Py_DECREF(controlTuples);
        PyMem_Free(I);
        return PyErr_NoMemory();
    }
    eb = PyMem_Malloc(newDataLength + 1);
    if (!eb) {
        Py_DECREF(controlTuples);
        PyMem_Free(I);
        PyMem_Free(db);
        return PyErr_NoMemory();
    }
    dblen = 0;
    eblen = 0;

    /* perform the diff */
    len = 0;
    scan = 0;
    lastscan = 0;
    lastpos = 0;
    lastoffset = 0;
    while (scan < newDataLength) {
        oldscore = 0;

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
                    if (newData[scan - lenb + i]== origData[pos - lenb + i])
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
                db[dblen + i] = newData[lastscan + i] - origData[lastpos + i];
            for (i = 0; i < (scan - lenb) - (lastscan + lenf); i++)
                eb[eblen + i] = newData[lastscan + lenf + i];

            dblen += lenf;
            eblen += (scan - lenb) - (lastscan + lenf);

            tuple = PyTuple_New(3);
            if (!tuple) {
                Py_DECREF(controlTuples);
                PyMem_Free(I);
                PyMem_Free(db);
                PyMem_Free(eb);
                return NULL;
            }
            PyTuple_SET_ITEM(tuple, 0, PyLong_FromLong(lenf));
            PyTuple_SET_ITEM(tuple, 1,
                    PyLong_FromLong((scan - lenb) - (lastscan + lenf)));
            PyTuple_SET_ITEM(tuple, 2,
                    PyLong_FromLong((pos - lenb) - (lastpos + lenf)));
            if (PyList_Append(controlTuples, tuple) < 0) {
                Py_DECREF(controlTuples);
                Py_DECREF(tuple);
                PyMem_Free(I);
                PyMem_Free(db);
                PyMem_Free(eb);
                return NULL;
            }
            Py_DECREF(tuple);

            lastscan = scan - lenb;
            lastpos = pos - lenb;
            lastoffset = pos - scan;
        }
    }

    PyMem_Free(I);
    results = PyTuple_New(3);
    if (!results) {
        PyMem_Free(db);
        PyMem_Free(eb);
        return NULL;
    }
    PyTuple_SET_ITEM(results, 0, controlTuples);
    temp = PyString_FromStringAndSize((char *) db, dblen);
    PyMem_Free(db);
    if (!temp) {
        PyMem_Free(eb);
        Py_DECREF(results);
        return NULL;
    }
    PyTuple_SET_ITEM(results, 1, temp);
    temp = PyString_FromStringAndSize((char *) eb, eblen);
    PyMem_Free(eb);
    if (!temp) {
        Py_DECREF(results);
        return NULL;
    }
    PyTuple_SET_ITEM(results, 2, temp);

    return results;
}


/* takes the original data and the control, diff and extra blocks produced
   by bsdiff and returns the new data
*/
static PyObject* patch(PyObject* self, PyObject* args)
{
    char *origData, *newData, *diffBlock, *extraBlock, *diffPtr, *extraPtr;
    int origDataLength, newDataLength, diffBlockLength, extraBlockLength;
    PyObject *controlTuples, *tuple, *results;
    off_t oldpos, newpos, x, y, z;
    int i, j, numTuples;

    if (!PyArg_ParseTuple(args, "s#iO!s#s#",
                          &origData, &origDataLength,
                          &newDataLength, &PyList_Type, &controlTuples,
                          &diffBlock, &diffBlockLength, &extraBlock,
                          &extraBlockLength))
        return NULL;

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
        y = PyLong_AsLong(PyTuple_GET_ITEM(tuple, 1));
        z = PyLong_AsLong(PyTuple_GET_ITEM(tuple, 2));
        if (newpos + x > newDataLength ||
                diffPtr + x > diffBlock + diffBlockLength ||
                extraPtr + y > extraBlock + extraBlockLength) {
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

    results = PyString_FromStringAndSize(newData, newDataLength);
    PyMem_Free(newData);
    return results;
}


/* encode an integer value as a string of 8 bytes */
static PyObject *encode_int64(PyObject *self, PyObject *value)
{
    long long x;
    char bs[8], sign = 0x00;
    int i;

    if (!PyArg_Parse(value, "L", &x))
        return NULL;

    if (x < 0) {
        x = -x;
        sign = 0x80;
    }
    for (i = 0; i < 8; i++) {
        bs[i] = x % 256;
        x /= 256;
    }
    bs[7] |= sign;
    return PyString_FromStringAndSize(bs, 8);
}


/* decode an off_t value from an 8 byte string */
static PyObject *decode_int64(PyObject *self, PyObject *string)
{
    long long x;
    char *bs;
    int i;

    if (!PyString_Check(string)) {
        PyErr_SetString(PyExc_TypeError, "string expected");
        return NULL;
    }
    if (PyString_Size(string) != 8) {
        PyErr_SetString(PyExc_ValueError, "8 bytes expected");
        return NULL;
    }
    bs = PyString_AsString(string);

    x = bs[7] & 0x7F;
    for (i = 6; i >= 0; i--)
        x = x * 256 + (unsigned char) bs[i];
    if (bs[7] & 0x80)
        x = -x;
    return PyLong_FromLongLong(x);
}


/* declaration of methods supported by this module */
static PyMethodDef module_functions[] = {
    {"diff", diff, METH_VARARGS},
    {"patch", patch, METH_VARARGS},
    {"encode_int64", encode_int64, METH_O},
    {"decode_int64", decode_int64, METH_O},
    {NULL, NULL, 0, NULL}  /* Sentinel */
};

/* initialization routine for the shared libary */
#ifdef IS_PY3K
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
#else
PyMODINIT_FUNC
initcore(void)
{
    Py_InitModule("core", module_functions);
}
#endif
