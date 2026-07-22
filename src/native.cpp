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

struct VertexElement {
    int semantic;
    int type;
    Py_ssize_t offset;
};

std::uint16_t read_u16(const std::uint8_t* data) {
    return static_cast<std::uint16_t>(data[0])
        | static_cast<std::uint16_t>(data[1]) << 8;
}

std::uint32_t read_u32(const std::uint8_t* data) {
    return static_cast<std::uint32_t>(data[0])
        | static_cast<std::uint32_t>(data[1]) << 8
        | static_cast<std::uint32_t>(data[2]) << 16
        | static_cast<std::uint32_t>(data[3]) << 24;
}

float read_f32(const std::uint8_t* data) {
    const std::uint32_t bits = read_u32(data);
    float value = 0.0F;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

float half_to_float(std::uint16_t value) {
    const std::uint32_t sign = static_cast<std::uint32_t>(value & 0x8000U) << 16;
    std::uint32_t exponent = (value >> 10) & 0x1FU;
    std::uint32_t mantissa = value & 0x03FFU;
    std::uint32_t bits = 0;
    if (exponent == 0) {
        if (mantissa == 0) {
            bits = sign;
        } else {
            exponent = 127U - 15U + 1U;
            while ((mantissa & 0x0400U) == 0) {
                mantissa <<= 1;
                --exponent;
            }
            mantissa &= 0x03FFU;
            bits = sign | exponent << 23 | mantissa << 13;
        }
    } else if (exponent == 0x1FU) {
        bits = sign | 0x7F800000U | mantissa << 13;
    } else {
        bits = sign | (exponent + 112U) << 23 | mantissa << 13;
    }
    float result = 0.0F;
    std::memcpy(&result, &bits, sizeof(result));
    return result;
}

int vertex_element_size(int type) {
    switch (type) {
        case 1: return 4;   // HALF2
        case 2: return 4;   // FLOAT
        case 3: return 8;   // HALF4
        case 4: return 4;   // FLOAT_SINGLE
        case 5: return 8;   // FLOAT2
        case 6: return 12;  // FLOAT3
        case 7: return 16;  // FLOAT4
        case 8: return 4;   // UBYTE4
        case 9: return 4;   // COLOR
        case 10: return 4;  // DEC3N
        default: return 0;
    }
}

PyObject* make_float_tuple(const std::uint8_t* data, int count, bool half) {
    PyObject* tuple = PyTuple_New(count);
    if (tuple == nullptr) {
        return nullptr;
    }
    for (int index = 0; index < count; ++index) {
        const double value = half
            ? static_cast<double>(half_to_float(read_u16(data + index * 2)))
            : static_cast<double>(read_f32(data + index * 4));
        PyObject* item = PyFloat_FromDouble(value);
        if (item == nullptr) {
            Py_DECREF(tuple);
            return nullptr;
        }
        PyTuple_SetItem(tuple, index, item);
    }
    return tuple;
}

PyObject* make_byte_tuple(const std::uint8_t* data) {
    PyObject* tuple = PyTuple_New(4);
    if (tuple == nullptr) {
        return nullptr;
    }
    for (int index = 0; index < 4; ++index) {
        PyObject* item = PyLong_FromLong(data[index]);
        if (item == nullptr) {
            Py_DECREF(tuple);
            return nullptr;
        }
        PyTuple_SetItem(tuple, index, item);
    }
    return tuple;
}

PyObject* make_dec3n_tuple(const std::uint8_t* data) {
    const std::uint32_t packed = read_u32(data);
    PyObject* tuple = PyTuple_New(4);
    if (tuple == nullptr) {
        return nullptr;
    }
    for (int index = 0; index < 3; ++index) {
        const std::uint32_t component = (packed >> (index * 10)) & 0x3FFU;
        const int signed_component = component < 0x200U
            ? static_cast<int>(component)
            : static_cast<int>(component) - 0x400;
        double decoded = static_cast<double>(signed_component) / 511.0;
        if (decoded < -1.0) {
            decoded = -1.0;
        }
        PyObject* item = PyFloat_FromDouble(decoded);
        if (item == nullptr) {
            Py_DECREF(tuple);
            return nullptr;
        }
        PyTuple_SetItem(tuple, index, item);
    }
    const std::uint32_t w_bits = packed >> 30;
    PyObject* w = PyFloat_FromDouble(w_bits == 3 ? -1.0 : static_cast<double>(w_bits));
    if (w == nullptr) {
        Py_DECREF(tuple);
        return nullptr;
    }
    PyTuple_SetItem(tuple, 3, w);
    return tuple;
}

PyObject* decode_vertex_value(const std::uint8_t* data, int type) {
    switch (type) {
        case 1: return make_float_tuple(data, 2, true);
        case 2:
        case 4: return PyFloat_FromDouble(read_f32(data));
        case 3: return make_float_tuple(data, 4, true);
        case 5: return make_float_tuple(data, 2, false);
        case 6: return make_float_tuple(data, 3, false);
        case 7: return make_float_tuple(data, 4, false);
        case 8:
        case 9: return make_byte_tuple(data);
        case 10: return make_dec3n_tuple(data);
        default:
            PyErr_Format(PyExc_ValueError, "unsupported WDR vertex element type: %d", type);
            return nullptr;
    }
}

PyObject* decode_wdr_vertices(PyObject*, PyObject* arguments) {
    PyObject* data_object = nullptr;
    PyObject* elements_object = nullptr;
    Py_ssize_t vertex_count = 0;
    Py_ssize_t stride = 0;
    if (!PyArg_ParseTuple(
        arguments,
        "OnnO:decode_wdr_vertices",
        &data_object,
        &vertex_count,
        &stride,
        &elements_object
    )) {
        return nullptr;
    }
    if (vertex_count < 0 || stride < 0 || (vertex_count != 0 && stride == 0)) {
        PyErr_SetString(PyExc_ValueError, "invalid WDR vertex count or stride");
        return nullptr;
    }

    Py_buffer data_buffer{};
    if (PyObject_GetBuffer(data_object, &data_buffer, PyBUF_SIMPLE) < 0) {
        return nullptr;
    }
    if (vertex_count > 0 && stride > data_buffer.len / vertex_count) {
        PyBuffer_Release(&data_buffer);
        PyErr_SetString(PyExc_ValueError, "WDR vertex data is smaller than its declaration");
        return nullptr;
    }

    PyObject* elements_tuple = PySequence_Tuple(elements_object);
    if (elements_tuple == nullptr) {
        PyBuffer_Release(&data_buffer);
        return nullptr;
    }
    std::vector<VertexElement> elements;
    try {
        elements.reserve(static_cast<std::size_t>(PyTuple_Size(elements_tuple)));
    } catch (const std::bad_alloc&) {
        Py_DECREF(elements_tuple);
        PyBuffer_Release(&data_buffer);
        return PyErr_NoMemory();
    }
    for (Py_ssize_t index = 0; index < PyTuple_Size(elements_tuple); ++index) {
        PyObject* item = PyTuple_GetItem(elements_tuple, index);
        int semantic = 0;
        int type = 0;
        Py_ssize_t offset = 0;
        if (!PyArg_ParseTuple(item, "iin", &semantic, &type, &offset)) {
            Py_DECREF(elements_tuple);
            PyBuffer_Release(&data_buffer);
            return nullptr;
        }
        const int size = vertex_element_size(type);
        if (semantic < 0 || semantic > 15 || size == 0 || offset < 0 || offset + size > stride) {
            Py_DECREF(elements_tuple);
            PyBuffer_Release(&data_buffer);
            PyErr_SetString(PyExc_ValueError, "invalid WDR vertex element declaration");
            return nullptr;
        }
        elements.push_back({semantic, type, offset});
    }
    Py_DECREF(elements_tuple);

    PyObject* result = PyDict_New();
    if (result == nullptr) {
        PyBuffer_Release(&data_buffer);
        return nullptr;
    }
    const auto* data = static_cast<const std::uint8_t*>(data_buffer.buf);
    for (const VertexElement& element : elements) {
        PyObject* values = PyTuple_New(vertex_count);
        if (values == nullptr) {
            Py_DECREF(result);
            PyBuffer_Release(&data_buffer);
            return nullptr;
        }
        for (Py_ssize_t vertex = 0; vertex < vertex_count; ++vertex) {
            PyObject* value = decode_vertex_value(
                data + vertex * stride + element.offset,
                element.type
            );
            if (value == nullptr) {
                Py_DECREF(values);
                Py_DECREF(result);
                PyBuffer_Release(&data_buffer);
                return nullptr;
            }
            PyTuple_SetItem(values, vertex, value);
        }
        PyObject* key = PyLong_FromLong(element.semantic);
        if (key == nullptr || PyDict_SetItem(result, key, values) < 0) {
            Py_XDECREF(key);
            Py_DECREF(values);
            Py_DECREF(result);
            PyBuffer_Release(&data_buffer);
            return nullptr;
        }
        Py_DECREF(key);
        Py_DECREF(values);
    }
    PyBuffer_Release(&data_buffer);
    return result;
}

std::int16_t read_i16(const std::uint8_t* data) {
    const std::uint16_t value = read_u16(data);
    return value < 0x8000
        ? static_cast<std::int16_t>(value)
        : static_cast<std::int16_t>(static_cast<std::int32_t>(value) - 0x10000);
}

bool parse_record_arguments(
    PyObject* arguments,
    Py_ssize_t record_size,
    Py_buffer* buffer,
    const std::uint8_t** records,
    Py_ssize_t* count
) {
    PyObject* data_object = nullptr;
    Py_ssize_t offset = 0;
    if (!PyArg_ParseTuple(arguments, "Onn", &data_object, &offset, count)) {
        return false;
    }
    if (offset < 0 || *count < 0) {
        PyErr_SetString(PyExc_ValueError, "record offset and count cannot be negative");
        return false;
    }
    if (PyObject_GetBuffer(data_object, buffer, PyBUF_SIMPLE) < 0) {
        return false;
    }
    if (offset > buffer->len || *count > (buffer->len - offset) / record_size) {
        PyBuffer_Release(buffer);
        PyErr_SetString(PyExc_ValueError, "record array points outside the input buffer");
        return false;
    }
    *records = static_cast<const std::uint8_t*>(buffer->buf) + offset;
    return true;
}

PyObject* make_int_tuple3(const std::uint8_t* data) {
    PyObject* result = PyTuple_New(3);
    if (result == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < 3; ++index) {
        PyObject* value = PyLong_FromLong(read_i16(data + index * 2));
        if (value == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        PyTuple_SetItem(result, index, value);
    }
    return result;
}

PyObject* make_word_tuple4(const std::uint8_t* data, bool mask_vertex_index) {
    PyObject* result = PyTuple_New(4);
    if (result == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < 4; ++index) {
        std::uint16_t value = read_u16(data + index * 2);
        if (mask_vertex_index) {
            value &= 0x7FFF;
        }
        PyObject* item = PyLong_FromUnsignedLong(value);
        if (item == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        PyTuple_SetItem(result, index, item);
    }
    return result;
}

PyObject* make_neighbor_tuple(const std::uint8_t* data) {
    PyObject* result = PyTuple_New(4);
    if (result == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < 4; ++index) {
        const std::uint16_t value = read_u16(data + index * 2);
        PyObject* item = value == 0xFFFF
            ? Py_NewRef(Py_None)
            : PyLong_FromUnsignedLong(value);
        if (item == nullptr) {
            Py_DECREF(result);
            return nullptr;
        }
        PyTuple_SetItem(result, index, item);
    }
    return result;
}

PyObject* decode_wbn_vertices(PyObject*, PyObject* arguments) {
    Py_buffer buffer{};
    const std::uint8_t* records = nullptr;
    Py_ssize_t count = 0;
    if (!parse_record_arguments(arguments, 6, &buffer, &records, &count)) {
        return nullptr;
    }
    PyObject* result = PyTuple_New(count);
    if (result == nullptr) {
        PyBuffer_Release(&buffer);
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < count; ++index) {
        PyObject* vertex = make_int_tuple3(records + index * 6);
        if (vertex == nullptr) {
            Py_DECREF(result);
            PyBuffer_Release(&buffer);
            return nullptr;
        }
        PyTuple_SetItem(result, index, vertex);
    }
    PyBuffer_Release(&buffer);
    return result;
}

PyObject* decode_wbn_polygons(PyObject*, PyObject* arguments) {
    Py_buffer buffer{};
    const std::uint8_t* records = nullptr;
    Py_ssize_t count = 0;
    if (!parse_record_arguments(arguments, 32, &buffer, &records, &count)) {
        return nullptr;
    }
    PyObject* result = PyTuple_New(count);
    if (result == nullptr) {
        PyBuffer_Release(&buffer);
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < count; ++index) {
        const std::uint8_t* record = records + index * 32;
        const std::uint32_t material_and_area = read_u32(record + 12);
        const std::uint32_t area_bits = material_and_area & 0xFFFFFF00U;
        std::uint8_t area_bytes[4] = {
            static_cast<std::uint8_t>(area_bits),
            static_cast<std::uint8_t>(area_bits >> 8),
            static_cast<std::uint8_t>(area_bits >> 16),
            static_cast<std::uint8_t>(area_bits >> 24),
        };
        PyObject* polygon = PyTuple_New(9);
        PyObject* normal = make_float_tuple(record, 3, false);
        PyObject* material = PyLong_FromUnsignedLong(material_and_area & 0xFFU);
        PyObject* area = PyFloat_FromDouble(read_f32(area_bytes));
        PyObject* vertex_indices = make_word_tuple4(record + 16, true);
        PyObject* neighbors = make_neighbor_tuple(record + 24);
        PyObject* raw = PyBytes_FromStringAndSize(reinterpret_cast<const char*>(record), 32);
        PyObject* area_bits_object = PyLong_FromUnsignedLong(area_bits);
        PyObject* vertex_words = make_word_tuple4(record + 16, false);
        PyObject* neighbor_words = make_word_tuple4(record + 24, false);
        PyObject* values[] = {
            normal, material, area, vertex_indices, neighbors, raw,
            area_bits_object, vertex_words, neighbor_words,
        };
        bool failed = polygon == nullptr;
        for (PyObject* value : values) {
            failed = failed || value == nullptr;
        }
        if (failed) {
            Py_XDECREF(polygon);
            for (PyObject* value : values) {
                Py_XDECREF(value);
            }
            Py_DECREF(result);
            PyBuffer_Release(&buffer);
            return nullptr;
        }
        for (Py_ssize_t field = 0; field < 9; ++field) {
            PyTuple_SetItem(polygon, field, values[field]);
        }
        PyTuple_SetItem(result, index, polygon);
    }
    PyBuffer_Release(&buffer);
    return result;
}

PyObject* decode_wbn_bvh_nodes(PyObject*, PyObject* arguments) {
    Py_buffer buffer{};
    const std::uint8_t* records = nullptr;
    Py_ssize_t count = 0;
    if (!parse_record_arguments(arguments, 16, &buffer, &records, &count)) {
        return nullptr;
    }
    PyObject* result = PyTuple_New(count);
    if (result == nullptr) {
        PyBuffer_Release(&buffer);
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < count; ++index) {
        const std::uint8_t* record = records + index * 16;
        PyObject* node = PyTuple_New(5);
        PyObject* values[] = {
            make_int_tuple3(record),
            make_int_tuple3(record + 6),
            PyLong_FromUnsignedLong(read_u16(record + 12)),
            PyLong_FromUnsignedLong(record[14]),
            PyLong_FromUnsignedLong(record[15]),
        };
        bool failed = node == nullptr;
        for (PyObject* value : values) {
            failed = failed || value == nullptr;
        }
        if (failed) {
            Py_XDECREF(node);
            for (PyObject* value : values) {
                Py_XDECREF(value);
            }
            Py_DECREF(result);
            PyBuffer_Release(&buffer);
            return nullptr;
        }
        for (Py_ssize_t field = 0; field < 5; ++field) {
            PyTuple_SetItem(node, field, values[field]);
        }
        PyTuple_SetItem(result, index, node);
    }
    PyBuffer_Release(&buffer);
    return result;
}

PyObject* decode_wbn_bvh_subtrees(PyObject*, PyObject* arguments) {
    Py_buffer buffer{};
    const std::uint8_t* records = nullptr;
    Py_ssize_t count = 0;
    if (!parse_record_arguments(arguments, 16, &buffer, &records, &count)) {
        return nullptr;
    }
    PyObject* result = PyTuple_New(count);
    if (result == nullptr) {
        PyBuffer_Release(&buffer);
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < count; ++index) {
        const std::uint8_t* record = records + index * 16;
        PyObject* subtree = PyTuple_New(4);
        PyObject* values[] = {
            make_int_tuple3(record),
            make_int_tuple3(record + 6),
            PyLong_FromUnsignedLong(read_u16(record + 12)),
            PyLong_FromUnsignedLong(read_u16(record + 14)),
        };
        bool failed = subtree == nullptr;
        for (PyObject* value : values) {
            failed = failed || value == nullptr;
        }
        if (failed) {
            Py_XDECREF(subtree);
            for (PyObject* value : values) {
                Py_XDECREF(value);
            }
            Py_DECREF(result);
            PyBuffer_Release(&buffer);
            return nullptr;
        }
        for (Py_ssize_t field = 0; field < 4; ++field) {
            PyTuple_SetItem(subtree, field, values[field]);
        }
        PyTuple_SetItem(result, index, subtree);
    }
    PyBuffer_Release(&buffer);
    return result;
}

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
