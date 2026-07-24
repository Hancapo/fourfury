from __future__ import annotations

import io
import pickle
import struct
import unittest
import zlib

from fourfury.wdr import (
    WDR_RESOURCE_VERSION,
    WdrBoneFlags,
    WdrDocument,
    WdrLightType,
    WdrLightFlags,
    WdrLightTypeFlags,
    WdrLodLevel,
    WdrShaderParameter,
    WdrVertex,
    WdrVector4,
    WdrVertexSemantic,
    load_wdr,
)
from fourfury.shaders import (
    WdrShaderParameterName,
    WdrShaderPreset,
    WdrShaderProgram,
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
    struct.pack_into("<2I", virtual, 0x14C, _virtual(0x180), _virtual(0x190))
    struct.pack_into("<4B", virtual, 0x154, 2, 4, 0xCD, 2)
    struct.pack_into("<2BHI", virtual, 0x158, 0, 1, 1, 0)
    struct.pack_into("<I", virtual, 0x160, _virtual(0x200))
    struct.pack_into("<4f", virtual, 0x180, 0.5, 0.5, 0.0, 2.0)
    struct.pack_into("<H", virtual, 0x190, 0)

    struct.pack_into("<I", virtual, 0x200, 0x6B48F4)
    struct.pack_into("<I", virtual, 0x20C, _virtual(0x280))
    struct.pack_into("<I", virtual, 0x21C, _virtual(0x2C0))
    struct.pack_into("<IIHH", virtual, 0x22C, 3, 1, 3, 3)
    struct.pack_into("<IHH", virtual, 0x238, _virtual(0x1B0), 36, 2)
    struct.pack_into("<2H", virtual, 0x1B0, 7, 9)

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
    struct.pack_into("<IBBBBQ", virtual, 0x340, 0x59, 36, 0, 0, 4, 0x6755555555996996)

    struct.pack_into("<I", virtual, 0x380, 0x6BCA40)
    struct.pack_into("<IHH", virtual, 0x388, _virtual(0x3E0), 1, 1)
    struct.pack_into("<IHH", virtual, 0x3C8, _virtual(0x4B0), 2, 2)
    struct.pack_into("<I", virtual, 0x3E0, _virtual(0x400))
    struct.pack_into("<2I", virtual, 0x4B0, 0x11111111, 0x22222222)

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


def _sample_wdr_with_skeleton() -> bytes:
    source = _sample_wdr()
    payload = bytearray(zlib.decompress(source[12:]))
    virtual = memoryview(payload)[:0x1000]
    struct.pack_into("<I", virtual, 0x0C, _virtual(0x740))
    struct.pack_into(
        "<5I4HI",
        virtual,
        0x740,
        _virtual(0x800),
        _virtual(0xB80),
        _virtual(0xA00),
        _virtual(0xA80),
        _virtual(0xB00),
        2,
        3,
        4,
        5,
        0x1234,
    )
    struct.pack_into("<IHH", virtual, 0x760, _virtual(0xB90), 2, 2)
    struct.pack_into("<6I", virtual, 0x768, 1, 0xAABBCCDD, 10, 11, 12, 13)
    struct.pack_into("<2i", virtual, 0xB80, -1, 0)
    struct.pack_into("<4H", virtual, 0xB90, 0, 0, 40000, 1)

    identity = (
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )
    for base in (0xA00, 0xA80, 0xB00):
        struct.pack_into("<16f", virtual, base, *identity)
        struct.pack_into("<16f", virtual, base + 64, *identity)

    root_name = b"root\0"
    child_name = b"child\0"
    virtual[0xBC0:0xBC0 + len(root_name)] = root_name
    virtual[0xBD0:0xBD0 + len(child_name)] = child_name

    def write_bone(
        offset: int,
        name_pointer: int,
        flags: int,
        index: int,
        bone_id: int,
        position: tuple[float, float, float, float],
        *,
        parent_pointer: int = 0,
        child_pointer: int = 0,
    ) -> None:
        struct.pack_into("<II3I4HI", virtual, offset, name_pointer, flags, 0, child_pointer,
                         parent_pointer, index, bone_id, 0, 0, 0)
        struct.pack_into("<4f", virtual, offset + 32, *position)
        struct.pack_into("<4f", virtual, offset + 64, 0.0, 0.0, 0.0, 1.0)
        struct.pack_into("<4f", virtual, offset + 80, 1.0, 1.0, 1.0, 1.0)

    write_bone(
        0x800,
        _virtual(0xBC0),
        int(WdrBoneFlags.ROTATE_X | WdrBoneFlags.TRANSLATE_Y),
        0,
        0,
        (1.0, 0.0, 0.0, 1.0),
        child_pointer=_virtual(0x8E0),
    )
    write_bone(
        0x8E0,
        _virtual(0xBD0),
        int(WdrBoneFlags.INVISIBLE),
        1,
        40000,
        (0.0, 2.0, 0.0, 1.0),
        parent_pointer=_virtual(0x800),
    )
    return source[:12] + zlib.compress(payload)


class WdrTests(unittest.TestCase):
    def test_public_types_keep_the_original_module_identity(self) -> None:
        value = WdrVector4(1.0, 2.0, 3.0, 4.0)

        self.assertEqual(WdrVector4.__module__, "fourfury.wdr")
        self.assertEqual(pickle.loads(pickle.dumps(value)), value)

    def test_reads_model_skinning_metadata_and_geometry_palette(self) -> None:
        document = WdrDocument.from_bytes(_sample_wdr())
        model = document.models[0]
        geometry = document.geometries[0]

        self.assertEqual(model.matrix_count, 2)
        self.assertEqual(model.flags, 4)
        self.assertEqual(model.model_type, 0xCD)
        self.assertEqual(model.matrix_index, 2)
        self.assertEqual(model.skin_flag, 1)
        self.assertTrue(model.has_skin)
        self.assertEqual(model.bone_index, 2)
        self.assertEqual(geometry.bone_ids, (7, 9))
        vertex = WdrVertex({WdrVertexSemantic.BLEND_INDICES: (1, 0, 3, 2)})
        self.assertEqual(geometry.resolve_bone_indices(vertex), (9, 7, 3, 2))

    def test_reads_vertex_buffer_and_layout_metadata(self) -> None:
        geometry = WdrDocument.from_bytes(_sample_wdr()).geometries[0]
        buffer = geometry.vertex_buffer

        self.assertIsNotNone(buffer)
        self.assertEqual(buffer.locked, 0)  # type: ignore[union-attr]
        self.assertEqual(buffer.flags, 0)  # type: ignore[union-attr]
        self.assertEqual(buffer.layout.fvf, 0x59)  # type: ignore[union-attr]
        self.assertEqual(buffer.layout.fvf_size, 36)  # type: ignore[union-attr]
        self.assertEqual(buffer.layout.dynamic_order, 0)  # type: ignore[union-attr]
        self.assertEqual(buffer.layout.channel_count, 4)  # type: ignore[union-attr]
        self.assertEqual(buffer.data, buffer.locked_data)  # type: ignore[union-attr]

    def test_keeps_vertex_rows_lazy_when_projecting_columns(self) -> None:
        document = WdrDocument.from_bytes(_sample_wdr())
        buffer = document.geometries[0].vertex_buffer

        self.assertIsNotNone(buffer)
        self.assertIsNone(buffer._vertices)  # type: ignore[union-attr]
        self.assertEqual(
            buffer.attribute_channels[WdrVertexSemantic.POSITION][1],  # type: ignore[union-attr]
            (1.0, 0.0, 0.0),
        )

        model = document.to_model()

        self.assertEqual(model.meshes[0].positions[1], (1.0, 0.0, 0.0))
        self.assertIsNone(buffer._vertices)  # type: ignore[union-attr]
        self.assertEqual(tuple(buffer.vertices[1].position), (1.0, 0.0, 0.0))  # type: ignore[union-attr,arg-type]
        self.assertIsNotNone(buffer._vertices)  # type: ignore[union-attr]

    def test_reads_model_and_per_geometry_bounds_without_offset_shift(self) -> None:
        source = _sample_wdr()
        payload = bytearray(zlib.decompress(source[12:]))
        struct.pack_into("<IHH", payload, 0x144, _virtual(0x160), 2, 2)
        struct.pack_into("<2I", payload, 0x160, _virtual(0x200), _virtual(0x200))
        struct.pack_into("<I", payload, 0x150, _virtual(0x1D0))
        struct.pack_into("<H", payload, 0x15A, 2)
        struct.pack_into("<4f", payload, 0x180, 10.0, 0.0, 0.0, 10.0)
        struct.pack_into("<4f", payload, 0x190, 1.0, 0.0, 0.0, 1.0)
        struct.pack_into("<4f", payload, 0x1A0, 2.0, 0.0, 0.0, 2.0)
        struct.pack_into("<2H", payload, 0x1D0, 0, 0)
        document = WdrDocument.from_bytes(source[:12] + zlib.compress(payload))

        model = document.models[0]
        self.assertEqual(tuple(model.bounding_sphere), (10.0, 0.0, 0.0, 10.0))  # type: ignore[arg-type]
        self.assertEqual(tuple(model.geometry_bounds[0]), (1.0, 0.0, 0.0, 1.0))  # type: ignore[arg-type]
        self.assertEqual(tuple(model.geometry_bounds[1]), (2.0, 0.0, 0.0, 2.0))  # type: ignore[arg-type]
        self.assertEqual(tuple(document.geometries[0].bounding_sphere), (2.0, 0.0, 0.0, 2.0))  # type: ignore[arg-type]

    def test_reads_skeleton_matrices_flags_and_bind_transforms(self) -> None:
        skeleton = WdrDocument.from_bytes(_sample_wdr_with_skeleton()).drawable.skeleton

        self.assertIsNotNone(skeleton)
        self.assertEqual(skeleton.parent_indices, (-1, 0))  # type: ignore[union-attr]
        self.assertEqual(skeleton.translation_dof_count, 3)  # type: ignore[union-attr]
        self.assertEqual(skeleton.rotation_dof_count, 4)  # type: ignore[union-attr]
        self.assertEqual(skeleton.scale_dof_count, 5)  # type: ignore[union-attr]
        self.assertEqual(skeleton.reference_count, 1)  # type: ignore[union-attr]
        self.assertEqual(skeleton.signature, 0xAABBCCDD)  # type: ignore[union-attr]
        self.assertEqual(skeleton.bone_ids[1].bone_id, 40000)  # type: ignore[union-attr]
        root, child = skeleton.bones  # type: ignore[union-attr]
        self.assertEqual(root.flags, WdrBoneFlags.ROTATE_X | WdrBoneFlags.TRANSLATE_Y)
        self.assertEqual(child.flags, WdrBoneFlags.INVISIBLE)
        self.assertEqual(child.parent_index, 0)
        self.assertEqual(tuple(child.absolute_transform.translation), (1.0, 2.0, 0.0))
        self.assertEqual(tuple(child.inverse_bind_transform.translation), (-1.0, -2.0, 0.0))
        for actual, expected in zip(child.skin_transform, child.skin_transform.identity(), strict=True):
            self.assertAlmostEqual(actual, expected)

    def test_names_all_shader_parameters_seen_in_stock_map_wdrs(self) -> None:
        expected = {
            0xFC2BC0AA: "shadow_map_resolution",
            0xF07391A4: "facet_mask",
            0xD79BFC1E: "global_animation_uv_0",
            0xBA54C190: "global_animation_uv_1",
            0x104E0B0E: "z_shift_scale",
            0xA38C0E4A: "z_shift",
            0x0C451B1A: "fade_thickness",
            0x1948C16C: "material_diffuse",
            0x00E67F02: "imposter_direction",
            0x1C8B0AFF: "normal_table",
            0x1105818B: "alternate_remap",
            0xDBB6BF5B: "ambient_decal_mask",
        }
        from fourfury.wdr import WDR_SHADER_PARAMETER_NAMES

        self.assertEqual(
            {key: WDR_SHADER_PARAMETER_NAMES[key] for key in expected},
            expected,
        )

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
        self.assertIs(
            document.shaders[0].parameters[0].known_name,
            WdrShaderParameterName.TEXTURE_SAMPLER,
        )
        self.assertIs(document.shaders[0].program, WdrShaderProgram.GTA_DEFAULT)
        self.assertIs(document.shaders[0].preset, WdrShaderPreset.GTA_DEFAULT)
        self.assertIs(
            document.shaders[0].get_parameter("texture_sampler"),
            document.shaders[0].parameters[0],
        )
        self.assertEqual(
            document.find_shaders(WdrShaderProgram.GTA_DEFAULT), document.shaders
        )
        self.assertEqual(document.unknown_shaders, ())
        self.assertEqual(document.shaders[0].parameters[0].texture.name, "sample")  # type: ignore[union-attr]
        self.assertEqual(document.shaders[0].parameters[1].name, "specular_factor")
        self.assertEqual(document.shaders[0].parameters[1].value.x, 35.0)  # type: ignore[union-attr]
        self.assertEqual(
            document.drawable.shader_group.reserved_data,  # type: ignore[union-attr]
            (0x11111111, 0x22222222),
        )

        light = document.drawable.lights[0]
        self.assertEqual(light.light_type, WdrLightType.POINT)
        self.assertEqual(tuple(light.position), (1.0, 2.0, 3.0))
        self.assertEqual(light.color, (255, 128, 64, 255))
        self.assertEqual(light.bone_id, 2)
        self.assertIsInstance(light.flags, WdrLightFlags)
        self.assertIsInstance(light.flashiness, WdrLightTypeFlags)

    def test_loads_from_binary_stream(self) -> None:
        document = load_wdr(io.BytesIO(_sample_wdr()))
        self.assertEqual(document.geometries[0].face_count, 1)

    def test_resolves_sps_aliases_without_hiding_unknown_values(self) -> None:
        document = WdrDocument.from_bytes(_sample_wdr())
        shader = document.shaders[0]
        shader.file_name = "gta_alpha.sps"

        self.assertIs(shader.preset, WdrShaderPreset.GTA_ALPHA)
        self.assertIs(shader.program, WdrShaderProgram.GTA_DEFAULT)
        self.assertEqual(shader.definition.draw_bucket, 1)  # type: ignore[union-attr]
        self.assertEqual(document.find_shaders(WdrShaderPreset.GTA_ALPHA), (shader,))

        unknown = WdrShaderParameter(
            0xDEADBEEF,
            1,
            value=WdrVector4(1.0, 2.0, 3.0, 4.0),
        )
        shader.parameters += (unknown,)
        shader.name = "custom_shader"
        shader.file_name = "custom_shader.sps"

        self.assertIsNone(shader.program)
        self.assertIsNone(shader.preset)
        self.assertEqual(shader.unknown_parameters, (unknown,))
        self.assertEqual(unknown.name, "hash_deadbeef")
        self.assertEqual(document.unknown_shaders, (shader,))

    def test_exposes_default_uv_animation_rows_as_a_neutral_transform(self) -> None:
        shader = WdrDocument.from_bytes(_sample_wdr()).shaders[0]
        shader.parameters += (
            WdrShaderParameter(
                0xD79BFC1E,
                1,
                value=WdrVector4(1.0, 0.0, 0.25, 0.0),
            ),
            WdrShaderParameter(
                0xBA54C190,
                1,
                value=WdrVector4(0.0, 1.0, -0.5, 0.0),
            ),
        )

        self.assertTrue(shader.has_uv_transform_parameters)
        transform = shader.uv_transform
        assert transform is not None
        self.assertEqual(transform.apply((0.5, 0.75)), (0.75, 0.25))

    def test_rejects_other_rsc5_resource_versions(self) -> None:
        source = bytearray(_sample_wdr())
        struct.pack_into("<I", source, 4, 0x20)
        with self.assertRaisesRegex(ValueError, "unsupported WDR resource version"):
            WdrDocument.from_bytes(bytes(source))


if __name__ == "__main__":
    unittest.main()
