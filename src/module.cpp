#include "native.hpp"

namespace {

using namespace fourfury::native;

PyMethodDef native_methods[] = {
    {
        "create_aes_context",
        reinterpret_cast<PyCFunction>(create_aes_context),
        METH_O,
        "Create a cached native GTA IV AES context."
    },
    {
        "aes16_decrypt",
        aes16_decrypt,
        METH_VARARGS,
        "Decrypt a buffer with GTA IV's sixteen-pass AES scheme."
    },
    {
        "decode_wdr_vertices",
        decode_wdr_vertices,
        METH_VARARGS,
        "Decode a WDR vertex stream into semantic columns."
    },
    {
        "decode_wbn_vertices",
        decode_wbn_vertices,
        METH_VARARGS,
        "Decode quantized WBN vertex records."
    },
    {
        "decode_wbn_polygons",
        decode_wbn_polygons,
        METH_VARARGS,
        "Decode WBN polygon records."
    },
    {
        "decode_wbn_bvh_nodes",
        decode_wbn_bvh_nodes,
        METH_VARARGS,
        "Decode WBN BVH node records."
    },
    {
        "decode_wbn_bvh_subtrees",
        decode_wbn_bvh_subtrees,
        METH_VARARGS,
        "Decode WBN BVH subtree records."
    },
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef native_module = {
    PyModuleDef_HEAD_INIT,
    "_native",
    "Optional native acceleration kernels for FourFury.",
    -1,
    native_methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__native() {
    return PyModule_Create(&native_module);
}
