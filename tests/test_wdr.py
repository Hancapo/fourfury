from __future__ import annotations

import io
import struct
import unittest
import zlib

from fourfury.wdr import (
    WDR_RESOURCE_VERSION,
    WdrDocument,
    WdrLightType,
    WdrLodLevel,
    WdrVertexSemantic,
    load_wdr,
)


VIRTUAL_BASE = 0x50000000
PHYSICAL_BASE = 0x60000000


def _virtual(offset: int) -> int:
    return VIRTUAL_BASE | offset


def _physical(offset: int) -> int:
    return PHYSICAL_BASE | offset


def _sample_wdr() -> bytes:
    virtual = bytearray(0x1000)
    physical = bytearray(0x1000)

    struct.pack_into("<4I", virtual, 0, 0x695254, 0, _virtual(0x380), 0)
    struct.pack_into("<4f", virtual, 0x10, 0.5, 0.5, 0.0, 0.0)
    struct.pack_into("<4f", virtual, 0x20, -1.0, -1.0, 0.0, 0.0)
    struct.pack_into("<4f", virtual, 0x30, 1.0, 1.0, 0.0, 0.0)
    struct.pack_into("<4I", virtual, 0x40, _virtual(0x100), 0, 0, 0)
    struct.pack_into("<4f", virtual, 0x50, 100.0, 200.0, 300.0, 400.0)
    struct.pack_into("<4i", virtual, 0x60, 1, 0, 0, 0)
    struct.pack_into("<f", virtual, 0x70, 2.0)
    struct.pack_into("<IHH", virtual, 0x80, _virtual(0x540), 1, 1)

    struct.pack_into("<IHH2I", virtual, 0x100, _virtual(0x120), 1, 1, 0, 0)
    struct.pack_into("<I", virtual, 0x120, _virtual(0x140))

    struct.pack_into("<I", virtual, 0x140, 0x6B0234)
    struct.pack_into("<IHH", virtual, 0x144, _virtual(0x160), 1, 1)
    struct.pack_into("<3I", virtual, 0x14C, _virtual(0x180), _virtual(0x190), 2 << 24)
    struct.pack_into("<HHI", virtual, 0x158, 0x0001, 1, 0)
    struct.pack_into("<I", virtual, 0x160, _virtual(0x200))
    struct.pack_into("<4f", virtual, 0x180, 0.5, 0.5, 0.0, 2.0)
    struct.pack_into("<H", virtual, 0x190, 0)

    struct.pack_into("<I", virtual, 0x200, 0x6B48F4)
    struct.pack_into("<I", virtual, 0x20C, _virtual(0x280))
    struct.pack_into("<I", virtual, 0x21C, _virtual(0x2C0))
    struct.pack_into("<IIHH", virtual, 0x22C, 3, 1, 3, 3)
    struct.pack_into("<H", virtual, 0x23C, 36)

    struct.pack_into(
        "<IHHIIIIII",
        virtual,
        0x280,
        0x6BB2D8,
        3,
        0,
        _physical(0),
        36,
        _virtual(0x340),
        0,
        _physical(0),
        0,
    )
    struct.pack_into("<III", virtual, 0x2C0, 0x6BB070, 3, _physical(108))
    struct.pack_into("<IHBBQ", virtual, 0x340, 0x59, 36, 0, 4, 0x6755555555996996)

    struct.pack_into("<I", virtual, 0x380, 0x6BCA40)
    struct.pack_into("<IHH", virtual, 0x388, _virtual(0x3E0), 1, 1)
    struct.pack_into("<I", virtual, 0x3E0, _virtual(0x400))

    struct.pack_into("<I", virtual, 0x400, 0x6BC4EC)
    struct.pack_into("<3B", virtual, 0x408, 2, 0, 1)
    struct.pack_into("<H", virtual, 0x40E, 0)
    struct.pack_into("<I", virtual, 0x414, _virtual(0x490))
    struct.pack_into("<I", virtual, 0x41C, 2)
    struct.pack_into("<I", virtual, 0x424, _virtual(0x498))
    struct.pack_into("<I", virtual, 0x428, 0x12345678)
    struct.pack_into("<I", virtual, 0x434, _virtual(0x4A0))
    struct.pack_into("<2I", virtual, 0x444, _virtual(0x470), _virtual(0x480))
    shader_name = b"gta_default\0"
    shader_file_name = b"default.sps\0"
    virtual[0x470:0x470 + len(shader_name)] = shader_name
    virtual[0x480:0x480 + len(shader_file_name)] = shader_file_name
    struct.pack_into("<2I", virtual, 0x490, _virtual(0x4C0), _virtual(0x4E0))
    struct.pack_into("<2B", virtual, 0x498, 0, 1)
    struct.pack_into("<2I", virtual, 0x4A0, 0x2B5170FD, 0x166E0FD1)
    struct.pack_into("<I", virtual, 0x4D4, _virtual(0x500))
    texture_name = b"pack:/sample.dds\0"
    virtual[0x500:0x500 + len(texture_name)] = texture_name
    struct.pack_into("<4f", virtual, 0x4E0, 35.0, 0.0, 0.0, 0.0)

    struct.pack_into("<I", virtual, 0x540, 0x69514C)
    struct.pack_into("<3f", virtual, 0x544, 1.0, 2.0, 3.0)
    struct.pack_into("<3f", virtual, 0x550, 0.0, 0.0, -1.0)
    struct.pack_into("<3f", virtual, 0x55C, 1.0, 0.0, 0.0)
    struct.pack_into("<4B", virtual, 0x568, 255, 128, 64, 255)
    struct.pack_into("<8f", virtual, 0x56C, 50.0, 1.0, 2.0, 20.0, 4.0, 0.5, 30.0, 45.0)
    struct.pack_into("<3I", virtual, 0x58C, 7, 8, 9)
    struct.pack_into("<BHB", virtual, 0x598, 0, 0, 1)
    struct.pack_into("<3fHH", virtual, 0x59C, 1.0, 100.0, 80.0, 2, 0)

    vertices = (
        ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (255, 0, 0, 255), (0.0, 0.0)),
        ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0, 255, 0, 255), (1.0, 0.0)),
        ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0, 0, 255, 255), (0.0, 1.0)),
    )
    for index, (position, normal, color, uv) in enumerate(vertices):
        struct.pack_into("<3f3f4B2f", physical, index * 36, *position, *normal, *color, *uv)
    struct.pack_into("<3H", physical, 108, 0, 1, 2)

    flags = 0xC0080010
    return struct.pack("<4sII", b"RSC\x05", WDR_RESOURCE_VERSION, flags) + zlib.compress(
        virtual + physical
    )


def _sample_wdr_with_embedded_texture() -> bytes:
    source = _sample_wdr()
    payload = bytearray(zlib.decompress(source[12:]))
    virtual = memoryview(payload)[:0x1000]
    physical = memoryview(payload)[0x1000:]
    struct.pack_into("<I", virtual, 0x384, _virtual(0x600))
    struct.pack_into("<4I", virtual, 0x600, 0, 0, 0, 1)
    struct.pack_into("<IHH", virtual, 0x610, _virtual(0x620), 1, 1)
    struct.pack_into("<IHH", virtual, 0x618, _virtual(0x624), 1, 1)
    struct.pack_into("<I", virtual, 0x620, 0x12345678)
    struct.pack_into("<I", virtual, 0x624, _virtual(0x680))
    struct.pack_into("<I", virtual, 0x694, _virtual(0x6D0))
    struct.pack_into("<HHIHBB", virtual, 0x69C, 4, 4, 0x31545844, 2, 0, 1)
    struct.pack_into("<I", virtual, 0x6C8, _physical(0x200))
    name = b"pack:/sample.dds\0"
    virtual[0x6D0:0x6D0 + len(name)] = name
    struct.pack_into("<HHI", physical, 0x200, 0xF800, 0, 0)
    return source[:12] + zlib.compress(payload)


class WdrTests(unittest.TestCase):
    def test_reads_and_resolves_embedded_texture_dictionary(self) -> None:
        document = WdrDocument.from_bytes(_sample_wdr_with_embedded_texture())

        self.assertEqual(len(document.embedded_textures), 1)
        texture = document.find_embedded_texture("sample.dds")
        self.assertIsNotNone(texture)
        self.assertEqual(texture.name, "sample")  # type: ignore[union-attr]
        self.assertEqual(texture.data, struct.pack("<HHI", 0xF800, 0, 0))  # type: ignore[union-attr]

    def test_allows_skinned_models_without_per_geometry_bounds(self) -> None:
        source = _sample_wdr()
        payload = bytearray(zlib.decompress(source[12:]))
        struct.pack_into("<I", payload, 0x14C, 0)
        changed = source[:12] + zlib.compress(payload)

        document = WdrDocument.from_bytes(changed)

        self.assertEqual(document.models[0].geometry_bounds, (None,))
        self.assertIsNone(document.geometries[0].bounding_sphere)

    def test_reads_geometry_shaders_and_lights_losslessly(self) -> None:
        source = _sample_wdr()
        document = WdrDocument.from_bytes(source, name="sample.wdr")

        self.assertEqual(document.name, "sample.wdr")
        self.assertEqual(document.to_bytes(), source)
        self.assertEqual(document.lods[0].level, WdrLodLevel.HIGH)  # type: ignore[union-attr]
        self.assertEqual(len(document.models), 1)
        self.assertEqual(len(document.geometries), 1)

        geometry = document.geometries[0]
        self.assertEqual(geometry.vertex_count, 3)
        self.assertEqual(geometry.triangles, ((0, 1, 2),))
        self.assertEqual(tuple(geometry.vertices[1].position), (1.0, 0.0, 0.0))  # type: ignore[arg-type]
        self.assertEqual(tuple(geometry.vertices[0].normal), (0.0, 0.0, 1.0))  # type: ignore[arg-type]
        self.assertEqual(geometry.vertices[2].colors[0], (0, 0, 255, 255))
        self.assertEqual(tuple(geometry.vertices[2].texcoords[0]), (0.0, 1.0))
        self.assertIn(WdrVertexSemantic.POSITION, geometry.vertices[0].attributes)

        self.assertEqual(geometry.shader.name, "gta_default")  # type: ignore[union-attr]
        self.assertEqual(document.shaders[0].parameters[0].name, "texture_sampler")
        self.assertEqual(document.shaders[0].parameters[0].texture.name, "sample")  # type: ignore[union-attr]
        self.assertEqual(document.shaders[0].parameters[1].name, "specular_factor")
        self.assertEqual(document.shaders[0].parameters[1].value.x, 35.0)  # type: ignore[union-attr]

        light = document.drawable.lights[0]
        self.assertEqual(light.light_type, WdrLightType.POINT)
        self.assertEqual(tuple(light.position), (1.0, 2.0, 3.0))
        self.assertEqual(light.color, (255, 128, 64, 255))
        self.assertEqual(light.bone_id, 2)

    def test_loads_from_binary_stream(self) -> None:
        document = load_wdr(io.BytesIO(_sample_wdr()))
        self.assertEqual(document.geometries[0].face_count, 1)

    def test_rejects_other_rsc5_resource_versions(self) -> None:
        source = bytearray(_sample_wdr())
        struct.pack_into("<I", source, 4, 0x20)
        with self.assertRaisesRegex(ValueError, "unsupported WDR resource version"):
            WdrDocument.from_bytes(bytes(source))


if __name__ == "__main__":
    unittest.main()
