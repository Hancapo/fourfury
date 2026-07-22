#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <cstdint>
#include <cstring>
#include <limits>
#include <new>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#endif

namespace {

constexpr const char* AES_CAPSULE_NAME = "fourfury._native.AesContext";

#ifdef _WIN32

struct AesContext {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_KEY_HANDLE key = nullptr;
    std::vector<std::uint8_t> key_object;

    ~AesContext() {
        if (key != nullptr) {
            BCryptDestroyKey(key);
        }
        if (algorithm != nullptr) {
            BCryptCloseAlgorithmProvider(algorithm, 0);
        }
    }
};

bool check_status(NTSTATUS status, const char* operation) {
    if (status >= 0) {
        return true;
    }
    PyErr_Format(
        PyExc_OSError,
        "%s failed with NTSTATUS 0x%08lX",
        operation,
        static_cast<unsigned long>(status)
    );
    return false;
}

void destroy_aes_capsule(PyObject* capsule) {
    void* pointer = PyCapsule_GetPointer(capsule, AES_CAPSULE_NAME);
    if (pointer != nullptr) {
        delete static_cast<AesContext*>(pointer);
    } else {
        PyErr_Clear();
    }
}

PyObject* create_aes_context(PyObject*, PyObject* key_object) {
    Py_buffer key_buffer{};
    if (PyObject_GetBuffer(key_object, &key_buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    if (key_buffer.len != 32) {
        PyBuffer_Release(&key_buffer);
        PyErr_SetString(PyExc_ValueError, "the GTA IV AES key must contain 32 bytes");
        return nullptr;
    }

    auto* context = new (std::nothrow) AesContext();
    if (context == nullptr) {
        PyBuffer_Release(&key_buffer);
        return PyErr_NoMemory();
    }

    NTSTATUS status = BCryptOpenAlgorithmProvider(
        &context->algorithm,
        BCRYPT_AES_ALGORITHM,
        nullptr,
        0
    );
    if (!check_status(status, "open AES provider")) {
        PyBuffer_Release(&key_buffer);
        delete context;
        return nullptr;
    }
    status = BCryptSetProperty(
        context->algorithm,
        BCRYPT_CHAINING_MODE,
        reinterpret_cast<PUCHAR>(const_cast<wchar_t*>(BCRYPT_CHAIN_MODE_ECB)),
        sizeof(BCRYPT_CHAIN_MODE_ECB),
        0
    );
    if (!check_status(status, "set AES ECB mode")) {
        PyBuffer_Release(&key_buffer);
        delete context;
        return nullptr;
    }

    ULONG object_size = 0;
    ULONG written = 0;
    status = BCryptGetProperty(
        context->algorithm,
        BCRYPT_OBJECT_LENGTH,
        reinterpret_cast<PUCHAR>(&object_size),
        sizeof(object_size),
        &written,
        0
    );
    if (!check_status(status, "get AES object size")) {
        PyBuffer_Release(&key_buffer);
        delete context;
        return nullptr;
    }

    try {
        context->key_object.resize(object_size);
    } catch (const std::bad_alloc&) {
        PyBuffer_Release(&key_buffer);
        delete context;
        return PyErr_NoMemory();
    }
    status = BCryptGenerateSymmetricKey(
        context->algorithm,
        &context->key,
        context->key_object.data(),
        object_size,
        static_cast<PUCHAR>(key_buffer.buf),
        static_cast<ULONG>(key_buffer.len),
        0
    );
    PyBuffer_Release(&key_buffer);
    if (!check_status(status, "create AES key")) {
        delete context;
        return nullptr;
    }

    PyObject* capsule = PyCapsule_New(context, AES_CAPSULE_NAME, destroy_aes_capsule);
    if (capsule == nullptr) {
        delete context;
    }
    return capsule;
}

PyObject* aes16_decrypt(PyObject*, PyObject* arguments) {
    PyObject* capsule = nullptr;
    PyObject* data_object = nullptr;
    if (!PyArg_ParseTuple(arguments, "OO:aes16_decrypt", &capsule, &data_object)) {
        return nullptr;
    }
    auto* context = static_cast<AesContext*>(
        PyCapsule_GetPointer(capsule, AES_CAPSULE_NAME)
    );
    if (context == nullptr) {
        return nullptr;
    }

    Py_buffer data_buffer{};
    if (PyObject_GetBuffer(data_object, &data_buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    if (data_buffer.len > static_cast<Py_ssize_t>(std::numeric_limits<ULONG>::max())) {
        PyBuffer_Release(&data_buffer);
        PyErr_SetString(PyExc_OverflowError, "native AES buffers cannot exceed 4 GiB");
        return nullptr;
    }
    PyObject* result = PyBytes_FromStringAndSize(nullptr, data_buffer.len);
    if (result == nullptr) {
        PyBuffer_Release(&data_buffer);
        return nullptr;
    }
    auto* output = reinterpret_cast<std::uint8_t*>(PyBytes_AsString(result));
    std::memcpy(output, data_buffer.buf, static_cast<std::size_t>(data_buffer.len));

    const Py_ssize_t aligned_size = data_buffer.len - data_buffer.len % 16;
    if (aligned_size == 0) {
        PyBuffer_Release(&data_buffer);
        return result;
    }

    std::vector<std::uint8_t> temporary;
    try {
        temporary.resize(static_cast<std::size_t>(aligned_size));
    } catch (const std::bad_alloc&) {
        PyBuffer_Release(&data_buffer);
        Py_DECREF(result);
        return PyErr_NoMemory();
    }
    PyBuffer_Release(&data_buffer);

    NTSTATUS status = 0;
    ULONG written = 0;
    auto* source = output;
    auto* target = temporary.data();
    Py_BEGIN_ALLOW_THREADS
    for (int pass = 0; pass < 16; ++pass) {
        status = BCryptDecrypt(
            context->key,
            source,
            static_cast<ULONG>(aligned_size),
            nullptr,
            nullptr,
            0,
            target,
            static_cast<ULONG>(aligned_size),
            &written,
            0
        );
        if (status < 0 || written != static_cast<ULONG>(aligned_size)) {
            break;
        }
        auto* swap = source;
        source = target;
        target = swap;
    }
    Py_END_ALLOW_THREADS

    if (status < 0) {
        Py_DECREF(result);
        check_status(status, "decrypt AES data");
        return nullptr;
    }
    if (written != static_cast<ULONG>(aligned_size)) {
        Py_DECREF(result);
        PyErr_SetString(PyExc_OSError, "AES decryption returned an unexpected size");
        return nullptr;
    }
    if (source != output) {
        std::memcpy(output, source, static_cast<std::size_t>(aligned_size));
    }
    return result;
}

#else

PyObject* create_aes_context(PyObject*, PyObject*) {
    PyErr_SetString(PyExc_RuntimeError, "native GTA IV AES is available only on Windows");
    return nullptr;
}

PyObject* aes16_decrypt(PyObject*, PyObject*) {
    PyErr_SetString(PyExc_RuntimeError, "native GTA IV AES is available only on Windows");
    return nullptr;
}

#endif

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
