#pragma once

#ifndef PY_SSIZE_T_CLEAN
#define PY_SSIZE_T_CLEAN
#endif
#include <Python.h>

namespace fourfury::native {

PyObject* create_aes_context(PyObject* self, PyObject* key_object);
PyObject* aes16_decrypt(PyObject* self, PyObject* arguments);
PyObject* decode_wdr_vertices(PyObject* self, PyObject* arguments);
PyObject* decode_wbn_vertices(PyObject* self, PyObject* arguments);
PyObject* decode_wbn_polygons(PyObject* self, PyObject* arguments);
PyObject* decode_wbn_bvh_nodes(PyObject* self, PyObject* arguments);
PyObject* decode_wbn_bvh_subtrees(PyObject* self, PyObject* arguments);

}  // namespace fourfury::native
