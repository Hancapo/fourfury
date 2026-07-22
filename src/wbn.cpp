#include "binary.hpp"
#include "native.hpp"

#include <cstdint>

namespace fourfury::native {
namespace {

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

PyObject* make_float_tuple3(const std::uint8_t* data) {
    PyObject* result = PyTuple_New(3);
    if (result == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < 3; ++index) {
        PyObject* value = PyFloat_FromDouble(read_f32(data + index * 4));
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

}  // namespace

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
        PyObject* normal = make_float_tuple3(record);
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

}  // namespace fourfury::native
