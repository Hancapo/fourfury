#pragma once

#include <cstdint>
#include <cstring>

namespace fourfury::native {

inline std::uint16_t read_u16(const std::uint8_t* data) {
    return static_cast<std::uint16_t>(data[0])
        | static_cast<std::uint16_t>(data[1]) << 8;
}

inline std::int16_t read_i16(const std::uint8_t* data) {
    const std::uint16_t value = read_u16(data);
    return value < 0x8000
        ? static_cast<std::int16_t>(value)
        : static_cast<std::int16_t>(static_cast<std::int32_t>(value) - 0x10000);
}

inline std::uint32_t read_u32(const std::uint8_t* data) {
    return static_cast<std::uint32_t>(data[0])
        | static_cast<std::uint32_t>(data[1]) << 8
        | static_cast<std::uint32_t>(data[2]) << 16
        | static_cast<std::uint32_t>(data[3]) << 24;
}

inline float read_f32(const std::uint8_t* data) {
    const std::uint32_t bits = read_u32(data);
    float value = 0.0F;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

}  // namespace fourfury::native
