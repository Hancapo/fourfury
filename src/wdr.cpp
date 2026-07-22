#include "binary.hpp"
#include "native.hpp"

#include <cstdint>
#include <cstring>
#include <new>
#include <vector>

namespace fourfury::native {
namespace {

struct VertexElement {
    int semantic;
    int type;
    Py_ssize_t offset;
};

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

}  // namespace

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

}  // namespace fourfury::native
