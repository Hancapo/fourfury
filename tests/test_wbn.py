from __future__ import annotations

import struct
import unittest
import zlib

from fourfury import (
    ImgArchive,
    Rsc5Resource,
    WbnBvhGeometry,
    WbnComposite,
    WbnDocument,
    WbnMaterialFlags,
    WbnMaterialType,
    WbnPolygon,
    WbnVertex,
    rsc5_physical_size,
    rsc5_virtual_size,
)


VIRTUAL_BASE = 0x50000000


def _pointer(offset: int) -> int:
    return VIRTUAL_BASE | offset


def _write_bound_base(data: bytearray, offset: int, bound_type: int) -> None:
    struct.pack_into("<I", data, offset, 0x12345678)
    struct.pack_into("<BBHff", data, offset + 4, bound_type, 1, 2, 8.0, 9.0)
    struct.pack_into("<4f", data, offset + 0x10, 10.0, 11.0, 12.0, float("nan"))
    struct.pack_into("<4f", data, offset + 0x20, -10.0, -11.0, -12.0, float("nan"))
    struct.pack_into("<4f", data, offset + 0x30, 1.0, 2.0, 3.0, float("nan"))
    struct.pack_into("<4f", data, offset + 0x40, 0.0, 0.0, 0.0, float("nan"))
    struct.pack_into("<4f", data, offset + 0x50, 4.0, 5.0, 6.0, float("nan"))
    struct.pack_into("<4f", data, offset + 0x60, 1.0, 1.0, 1.0, float("nan"))
    struct.pack_into("<3fI", data, offset + 0x70, 0.04, 0.04, 0.04, 2)


def _sample_wbn() -> bytes:
    data = bytearray(0x1000)
    struct.pack_into("<III", data, 0, 0x695328, _pointer(0x20), _pointer(0x100))

    _write_bound_base(data, 0x100, 12)
    struct.pack_into(
        "<4IHH3I",
        data,
        0x180,
        _pointer(0x1A0),
        _pointer(0x1C0),
        _pointer(0x200),
        _pointer(0x240),
        1,
        1,
        0,
        0,
        0,
    )
    struct.pack_into("<I", data, 0x1A0, _pointer(0x300))

    identity = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 20.0, 30.0, 40.0, 1.0]
    struct.pack_into("<16f", data, 0x1C0, *identity)
    struct.pack_into("<16f", data, 0x200, *identity)
    struct.pack_into("<8f", data, 0x240, -1.0, -2.0, -3.0, 0.0, 1.0, 2.0, 3.0, 0.0)

    _write_bound_base(data, 0x300, 10)
    struct.pack_into("<I", data, 0x384, _pointer(0x420))
    struct.pack_into("<I", data, 0x38C, _pointer(0x440))
    struct.pack_into("<4f", data, 0x390, 0.5, 0.5, 0.5, float("nan"))
    struct.pack_into("<4f", data, 0x3A0, 10.0, 20.0, 30.0, float("nan"))
    struct.pack_into("<I", data, 0x3B0, _pointer(0x400))
    struct.pack_into("<II", data, 0x3C8, 3, 1)
    struct.pack_into("<I", data, 0x3D0, _pointer(0x460))
    struct.pack_into("<B", data, 0x3D8, 1)
    struct.pack_into("<I", data, 0x3E0, _pointer(0x480))

    struct.pack_into("<9h", data, 0x400, 0, 0, 0, 2, 0, 0, 0, 2, 0)
    struct.pack_into("<9h", data, 0x420, 0, 0, 0, 1, 0, 0, 0, 1, 0)
    area_bits = struct.unpack("<I", struct.pack("<f", 1.25))[0] & 0xFFFFFF00
    struct.pack_into("<3fI4H4H", data, 0x440, 0.0, 0.0, 1.0, area_bits, 0, 1, 2, 0, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF)
    material_flags = 3 | int(WbnMaterialFlags.STAIRS | WbnMaterialFlags.SEE_THROUGH)
    struct.pack_into("<BBH", data, 0x460, 7, 0, material_flags)

    struct.pack_into("<4I", data, 0x480, _pointer(0x4E0), 1, 1, 1)
    struct.pack_into("<4f", data, 0x490, -1.0, -1.0, -1.0, 0.0)
    struct.pack_into("<4f", data, 0x4A0, 1.0, 1.0, 1.0, 0.0)
    struct.pack_into("<4f", data, 0x4B0, 0.0, 0.0, 0.0, 0.0)
    struct.pack_into("<4f", data, 0x4C0, 1.0, 1.0, 1.0, 0.0)
    struct.pack_into("<IHH", data, 0x4D0, _pointer(0x500), 1, 1)
    struct.pack_into("<6hHBB", data, 0x4E0, -1, -1, -1, 1, 1, 1, 0, 1, 0)
    struct.pack_into("<6hHH", data, 0x500, -1, -1, -1, 1, 1, 1, 0, 0)

    flags = 0xC0000010
    return struct.pack("<4sII", b"RSC\x05", 0x20, flags) + zlib.compress(data)


class Rsc5Tests(unittest.TestCase):
    def test_decodes_allocation_sizes_and_preserves_source(self) -> None:
        source = _sample_wbn()
        resource = Rsc5Resource.from_bytes(source)

        self.assertEqual(rsc5_virtual_size(resource.flags), 0x1000)
        self.assertEqual(rsc5_physical_size(resource.flags), 0)
        self.assertEqual(resource.to_bytes(), source)


class WbnTests(unittest.TestCase):
    def test_preserves_null_composite_child_slots(self) -> None:
        source = _sample_wbn()
        payload = bytearray(zlib.decompress(source[12:]))
        struct.pack_into("<I", payload, 0x1A0, 0)
        source = source[:12] + zlib.compress(payload)

        document = WbnDocument.from_bytes(source)

        self.assertIsInstance(document.root, WbnComposite)
        self.assertEqual(document.root.children, [None])
        self.assertEqual(document.to_bytes(), source)
        document.root.children[0] = document.root
        with self.assertRaisesRegex(ValueError, "null composite child slots"):
            document.to_bytes()

    def test_distinguishes_triangle_sentinels_from_quad_vertices(self) -> None:
        raw = struct.pack(
            "<3fI4H4H",
            0.0, 0.0, 1.0, 0,
            4, 5, 6, 7,
            10, 11, 12, 13,
        )
        polygon = WbnPolygon.from_bytes(raw, 0)

        self.assertFalse(polygon.is_triangle)
        self.assertTrue(polygon.is_quad)
        self.assertEqual(polygon.face_vertex_indices, (4, 5, 6, 7))
        self.assertEqual(polygon.face_neighbor_indices, (10, 11, 12, 13))

    def test_reads_wbn_extracted_from_img(self) -> None:
        source = _sample_wbn()
        archive = ImgArchive.empty("map.img")
        archive.add_file(
            "sample.wbn",
            source,
            resource_type=0x20,
            resource_flags=0xC0000010,
        )

        parsed_archive = ImgArchive.from_bytes(archive.to_bytes())
        entry = parsed_archive.find_entry("sample.wbn")
        self.assertIsNotNone(entry)
        document = WbnDocument.from_bytes(entry.read(), name=entry.name)  # type: ignore[union-attr]

        self.assertEqual(len(document.geometries), 1)
        self.assertEqual(document.to_bytes(), source)

    def test_reads_composite_geometry_materials_and_bvh_losslessly(self) -> None:
        source = _sample_wbn()
        document = WbnDocument.from_bytes(source)

        self.assertIsInstance(document.root, WbnComposite)
        root = document.root
        assert isinstance(root, WbnComposite)
        self.assertEqual(len(root.children), 1)
        self.assertEqual(root.current_matrices[0].translation.x, 20.0)  # type: ignore[index]

        geometry = root.children[0]
        self.assertIsInstance(geometry, WbnBvhGeometry)
        assert isinstance(geometry, WbnBvhGeometry)
        self.assertEqual(len(geometry.vertices), 3)
        self.assertEqual(geometry.decoded_vertices[1].x, 11.0)
        self.assertEqual(geometry.polygons[0].vertex_indices[:3], (0, 1, 2))
        self.assertTrue(geometry.polygons[0].is_triangle)
        self.assertFalse(geometry.polygons[0].is_quad)
        self.assertEqual(geometry.polygons[0].face_vertex_indices, (0, 1, 2))
        self.assertEqual(geometry.polygons[0].face_neighbor_indices, (None, None, None))
        self.assertEqual(geometry.polygons[0].neighbor_indices, (None, None, None, None))
        self.assertAlmostEqual(geometry.polygons[0].area, 1.25, places=4)
        self.assertEqual(geometry.materials[0].material_id, 7)
        self.assertEqual(geometry.materials[0].room_id, 3)
        self.assertTrue(geometry.materials[0].flags & WbnMaterialFlags.STAIRS)
        self.assertTrue(geometry.bvh.nodes[0].is_leaf)  # type: ignore[union-attr]
        self.assertEqual(document.to_bytes(), source)

    def test_resolves_builtin_material_names_and_edits_enum(self) -> None:
        document = WbnDocument.from_bytes(_sample_wbn())
        material = document.geometries[0].materials[0]

        self.assertEqual(material.material_id, 7)
        self.assertIs(material.material_type, WbnMaterialType.RUMBLE_STRIP)
        self.assertEqual(material.name, "RUMBLE_STRIP")
        self.assertIs(document.geometries[0].material_for_polygon(0), material)

        material.material_type = WbnMaterialType.ROCK
        self.assertEqual(material.material_id, 11)
        self.assertEqual(material.name, "ROCK")

        reparsed = WbnDocument.from_bytes(document.to_bytes())
        self.assertIs(reparsed.geometries[0].materials[0].material_type, WbnMaterialType.ROCK)

    def test_preserves_unknown_material_ids(self) -> None:
        document = WbnDocument.from_bytes(_sample_wbn())
        material = document.geometries[0].materials[0]

        material.material_id = 250
        self.assertIsNone(material.material_type)
        self.assertIsNone(material.name)
        reparsed = WbnDocument.from_bytes(document.to_bytes())
        self.assertEqual(reparsed.geometries[0].materials[0].material_id, 250)

    def test_fixed_size_edits_recompress_and_reparse(self) -> None:
        source = _sample_wbn()
        document = WbnDocument.from_bytes(source)
        root = document.root
        assert isinstance(root, WbnComposite)
        geometry = root.children[0]
        assert isinstance(geometry, WbnBvhGeometry)

        geometry.vertices[1].x = 4
        geometry.materials[0].flags |= WbnMaterialFlags.BLOCK_CLIMB
        root.current_matrices[0].values[12] = 99.0  # type: ignore[index]
        root.child_bounding_boxes[0].minimum.x = -5.0  # type: ignore[index]

        changed = document.to_bytes()
        self.assertNotEqual(changed, source)
        reparsed = WbnDocument.from_bytes(changed)
        reparsed_root = reparsed.root
        assert isinstance(reparsed_root, WbnComposite)
        reparsed_geometry = reparsed_root.children[0]
        assert isinstance(reparsed_geometry, WbnBvhGeometry)
        self.assertEqual(reparsed_geometry.vertices[1].x, 4)
        self.assertTrue(reparsed_geometry.materials[0].flags & WbnMaterialFlags.BLOCK_CLIMB)
        self.assertEqual(reparsed_root.current_matrices[0].translation.x, 99.0)  # type: ignore[index]
        self.assertEqual(reparsed_root.child_bounding_boxes[0].minimum.x, -5.0)  # type: ignore[index]

    def test_rejects_topology_changes(self) -> None:
        document = WbnDocument.from_bytes(_sample_wbn())
        geometry = document.geometries[0]
        geometry.vertices.append(WbnVertex(0, 0, 0))

        with self.assertRaisesRegex(ValueError, "cannot change the vertex count"):
            document.to_bytes()


if __name__ == "__main__":
    unittest.main()
