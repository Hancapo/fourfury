from __future__ import annotations

import io
import struct
import unittest
import zlib

from fourfury import (
    ImgArchive,
    WnvDocument,
    WnvEdgeFlags,
    WnvFlags,
    WnvPolygonFlags,
    WnvVector3,
    WnvVertex,
    load_wnv,
)


VIRTUAL_BASE = 0x50000000


def _pointer(offset: int) -> int:
    return VIRTUAL_BASE | offset


def _sample_wnv() -> bytes:
    data = bytearray([0xCD]) * 0x1000
    transform = (
        1.0, 0.0, 0.0, float("nan"),
        0.0, 1.0, 0.0, float("nan"),
        0.0, 0.0, 1.0, float("nan"),
        0.0, 0.0, 0.0, float("nan"),
    )
    struct.pack_into("<16f", data, 0, *transform)
    struct.pack_into("<4f", data, 0x40, 100.0, 100.0, 50.0, float("nan"))
    struct.pack_into("<I2H", data, 0x50, int(WnvFlags.POLYGONS | WnvFlags.RESERVED_8), 5, 1)
    struct.pack_into("<I", data, 0x58, _pointer(0xD0))
    struct.pack_into("<I", data, 0x5C, 0x1234)
    struct.pack_into(
        "<5I",
        data,
        0x60,
        _pointer(0xE8),
        _pointer(0xF0),
        3,
        _pointer(0xA0),
        _pointer(0x120),
    )
    struct.pack_into("<3I", data, 0x74, 7, 3, 1)
    struct.pack_into("<5I", data, 0x80, 11, 12, 13, 14, 15)

    polygon_flags_1 = int(WnvPolygonFlags.PAVEMENT)
    polygon_flags_2 = int(WnvPolygonFlags.INTERIOR) >> 8
    data_1 = polygon_flags_1 | (3 << 21)
    data_index = (12 << 17) | (2 << 29)
    data_2 = polygon_flags_2 << 4
    data_3 = 3 << 4
    struct.pack_into(
        "<4I6hI4BI",
        data,
        0xA0,
        data_1,
        data_index,
        0,
        0,
        -200,
        200,
        -200,
        200,
        0,
        200,
        data_2,
        128,
        128,
        0x55,
        2,
        data_3,
    )
    struct.pack_into("<9H", data, 0xD0, 0, 0, 0, 0xFFFF, 0, 0, 0, 0xFFFF, 0)
    struct.pack_into("<3H", data, 0xE8, 0, 1, 2)
    for index in range(3):
        data_1 = 1 | (2 << 20) | (8 << 22)
        data_2 = 1 | (int(WnvEdgeFlags.EXTERNAL_EDGE) << 20)
        struct.pack_into("<2I", data, 0xF0 + index * 8, data_1, data_2)

    struct.pack_into("<4f", data, 0x120, -50.0, -50.0, 0.0, float("nan"))
    struct.pack_into("<4f", data, 0x130, 50.0, 50.0, 50.0, float("nan"))
    struct.pack_into("<6h", data, 0x140, -200, 200, -200, 200, 0, 200)
    struct.pack_into("<5I", data, 0x14C, _pointer(0x160), 0, 0, 0, 0)
    struct.pack_into("<HBBIIHH", data, 0x160, 4, 0, 0, _pointer(0x170), _pointer(0x180), 1, 1)
    struct.pack_into("<H", data, 0x170, 0)
    struct.pack_into("<3HH", data, 0x180, 0x8000, 0x8000, 0, 64 | (2 << 8))

    flags = 0xC0000010
    return struct.pack("<4sII", b"RSC\x05", 1, flags) + zlib.compress(data)


class WnvTests(unittest.TestCase):
    def test_reads_navmesh_geometry_flags_and_quadtree_losslessly(self) -> None:
        source = _sample_wnv()
        document = WnvDocument.from_bytes(source, name="sample.wnv")

        self.assertEqual(document.name, "sample.wnv")
        self.assertEqual(len(document.vertices), 3)
        self.assertEqual(len(document.indices), 3)
        self.assertEqual(len(document.edges), 3)
        self.assertEqual(len(document.polygons), 1)
        self.assertTrue(document.flags & WnvFlags.POLYGONS)
        polygon = document.polygons[0]
        self.assertEqual(document.polygon_vertex_indices(polygon), (0, 1, 2))
        self.assertEqual(polygon.area_id, 12)
        self.assertEqual(polygon.pedestrian_density, 2)
        self.assertEqual(polygon.part_id, 3)
        self.assertTrue(polygon.flags & WnvPolygonFlags.PAVEMENT)
        self.assertTrue(polygon.flags & WnvPolygonFlags.INTERIOR)
        self.assertTrue(document.edges[0].flags & WnvEdgeFlags.EXTERNAL_EDGE)
        document.edges[0].flags |= 0x100
        self.assertEqual(document.edges[0].unresolved_flags, 0x100)
        document.polygons[0].flags |= 0x1000
        self.assertEqual(document.polygons[0].unresolved_flags, 0x1000)
        self.assertEqual(document.decoded_vertices[1].x, 50.0)
        self.assertEqual(len(list(document.iter_quadtree())), 1)
        assert document.quadtree is not None
        assert document.quadtree.data is not None
        self.assertEqual(document.quadtree.data.polygon_ids, [0])
        self.assertEqual(document.quadtree.data.cover_points[0].cover_type, 2)
        document.edges[0].flags &= ~0x100
        document.polygons[0].flags &= ~0x1000
        self.assertEqual(document.to_bytes(), source)

    def test_fixed_size_edits_recompress_and_reparse(self) -> None:
        document = WnvDocument.from_bytes(_sample_wnv())
        document.vertices[0].z = 0x4000
        document.edges[0].flags |= WnvEdgeFlags.ADJACENCY_DISABLED
        document.polygons[0].flags |= WnvPolygonFlags.WATER
        document.polygons[0].area_id = 42
        assert document.quadtree is not None
        assert document.quadtree.data is not None
        document.quadtree.cell_aabb.minimum = WnvVector3(-49.5, -49.5, 0.0)
        document.quadtree.data.cover_points[0].disabled = True

        changed = document.to_bytes()
        self.assertNotEqual(changed, _sample_wnv())
        reparsed = WnvDocument.from_bytes(changed)
        self.assertEqual(reparsed.vertices[0].z, 0x4000)
        self.assertTrue(reparsed.edges[0].flags & WnvEdgeFlags.ADJACENCY_DISABLED)
        self.assertTrue(reparsed.polygons[0].flags & WnvPolygonFlags.WATER)
        self.assertEqual(reparsed.polygons[0].area_id, 42)
        assert reparsed.quadtree is not None
        assert reparsed.quadtree.data is not None
        self.assertEqual(reparsed.quadtree.cell_aabb.minimum.x, -49.5)
        self.assertTrue(reparsed.quadtree.data.cover_points[0].disabled)

    def test_loads_from_img_and_binary_stream(self) -> None:
        source = _sample_wnv()
        archive = ImgArchive.empty("navmeshes.img")
        archive.add_file("sample.wnv", source, resource_type=1, resource_flags=0xC0000010)
        parsed = ImgArchive.from_bytes(archive.to_bytes())
        entry = parsed.find_entry("sample.wnv")

        self.assertIsNotNone(entry)
        document = load_wnv(io.BytesIO(entry.read()))  # type: ignore[union-attr]
        self.assertEqual(len(document.polygons), 1)

    def test_rejects_topology_changes(self) -> None:
        document = WnvDocument.from_bytes(_sample_wnv())
        document.vertices.append(WnvVertex(0, 0, 0))

        with self.assertRaisesRegex(ValueError, "cannot change the vertex count"):
            document.to_bytes()

    def test_rejects_invalid_polygon_ranges(self) -> None:
        source = _sample_wnv()
        payload = bytearray(zlib.decompress(source[12:]))
        struct.pack_into("<I", payload, 0xA4, 0x1FFFF)
        broken = source[:12] + zlib.compress(payload)

        with self.assertRaisesRegex(ValueError, "index range exceeds"):
            WnvDocument.from_bytes(broken)


if __name__ == "__main__":
    unittest.main()
