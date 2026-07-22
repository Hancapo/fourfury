from __future__ import annotations

import unittest

from fourfury import (
    ModelAsset,
    ModelLightType,
    ModelParameterKind,
    ModelTextureFormat,
    ModelTextureKind,
    WdrDocument,
)

from test_wdr import (
    _sample_wdr,
    _sample_wdr_with_embedded_texture,
    _sample_wdr_with_skeleton,
)


class ModelProjectionTests(unittest.TestCase):
    def test_projects_geometry_materials_and_lights(self) -> None:
        model = WdrDocument.from_bytes(_sample_wdr(), name="sample.wdr").to_model()

        self.assertIsInstance(model, ModelAsset)
        self.assertEqual(model.name, "sample")
        self.assertEqual(model.coordinate_system.handedness, "right")
        self.assertEqual(model.coordinate_system.up_axis, "+z")
        self.assertEqual(model.bounding_box.minimum, (-1.0, -1.0, 0.0))  # type: ignore[union-attr]
        self.assertEqual(model.bounding_box.maximum, (1.0, 1.0, 0.0))  # type: ignore[union-attr]
        self.assertEqual(model.bounding_sphere.center, (0.5, 0.5, 0.0))  # type: ignore[union-attr]
        self.assertEqual(model.bounding_sphere.radius, 2.0)  # type: ignore[union-attr]

        high = model.get_lod("high")
        self.assertIsNotNone(high)
        self.assertEqual(high.distance, 100.0)  # type: ignore[union-attr]
        self.assertEqual(high.draw_bucket_mask, 1)  # type: ignore[union-attr]
        mesh = high.meshes[0]  # type: ignore[union-attr]
        self.assertEqual(mesh.vertex_count, 3)
        self.assertEqual(mesh.triangle_count, 1)
        self.assertEqual(mesh.indices, (0, 1, 2))
        self.assertEqual(mesh.positions[1], (1.0, 0.0, 0.0))
        self.assertEqual(mesh.normals[0], (0.0, 0.0, 1.0))
        self.assertEqual(mesh.get_texcoords(0)[2], (0.0, 1.0))
        self.assertEqual(mesh.get_colors(0)[0], (1.0, 0.0, 0.0, 1.0))
        self.assertEqual(mesh.material_index, 0)
        self.assertEqual(mesh.bone_palette, (7, 9))

        material = model.get_material(0)
        self.assertEqual(material.shader_name, "gta_default")  # type: ignore[union-attr]
        self.assertEqual(material.shader_file, "default.sps")  # type: ignore[union-attr]
        self.assertEqual(material.shader_hash, 0x12345678)  # type: ignore[union-attr]
        self.assertEqual(material.texture_names, ("sample",))  # type: ignore[union-attr]
        texture_parameter = material.get_parameter("texture_sampler")  # type: ignore[union-attr]
        self.assertEqual(texture_parameter.kind, ModelParameterKind.TEXTURE)  # type: ignore[union-attr]
        self.assertEqual(texture_parameter.texture.name, "sample")  # type: ignore[union-attr]
        specular = material.get_parameter(0x166E0FD1)  # type: ignore[union-attr]
        self.assertEqual(specular.value, (35.0, 0.0, 0.0, 0.0))  # type: ignore[union-attr]
        self.assertEqual(model.texture_names, ("sample",))

        light = model.lights[0]
        self.assertEqual(light.light_type, ModelLightType.POINT)
        self.assertEqual(light.position, (1.0, 2.0, 3.0))
        self.assertEqual(light.color, (1.0, 128.0 / 255.0, 64.0 / 255.0, 1.0))
        self.assertEqual(light.range, 20.0)
        self.assertEqual(light.intensity, 4.0)
        self.assertEqual(light.corona_hash, 8)
        self.assertEqual(light.luminosity_hash, 9)
        self.assertEqual(light.source_type, 1)

    def test_projects_embedded_texture_without_reencoding(self) -> None:
        document = WdrDocument.from_bytes(_sample_wdr_with_embedded_texture())
        source = document.embedded_textures[0]

        texture = document.to_model().textures[0]

        self.assertEqual(texture.name, "sample")
        self.assertEqual(texture.format, ModelTextureFormat.BC1)
        self.assertEqual(texture.kind, ModelTextureKind.TEXTURE_2D)
        self.assertEqual(texture.mip_count, 1)
        self.assertEqual(texture.mip_sizes, (8,))
        self.assertEqual(texture.data, source.data)
        self.assertEqual(texture.source_format, int(source.format))

    def test_projects_skeleton_hierarchy_and_matrices(self) -> None:
        model = WdrDocument.from_bytes(_sample_wdr_with_skeleton()).to_model()

        skeleton = model.skeleton
        self.assertIsNotNone(skeleton)
        self.assertEqual(skeleton.signature, 0xAABBCCDD)  # type: ignore[union-attr]
        self.assertEqual(tuple(bone.name for bone in skeleton.bones), ("root", "child"))  # type: ignore[union-attr]
        self.assertEqual(tuple(bone.name for bone in skeleton.roots), ("root",))  # type: ignore[union-attr]
        child = skeleton.get_bone(40000)  # type: ignore[union-attr]
        self.assertEqual(child.parent_index, 0)  # type: ignore[union-attr]
        self.assertEqual(child.world_transform[12:15], (1.0, 2.0, 0.0))  # type: ignore[union-attr]
        self.assertEqual(child.inverse_bind_transform[12:15], (-1.0, -2.0, 0.0))  # type: ignore[union-attr]
        high = model.get_lod("high")
        self.assertIsNone(high.objects[0].bone_index)  # type: ignore[union-attr]
        self.assertTrue(high.objects[0].is_skinned)  # type: ignore[union-attr]
        self.assertEqual(high.objects[0].bone_count, 2)  # type: ignore[union-attr]
        self.assertEqual(high.objects[0].flags, 4)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
