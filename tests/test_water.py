from __future__ import annotations

import unittest
from io import BytesIO

from fourfury import (
    WaterDocument,
    WaterIssueSeverity,
    WaterSurface,
    WaterSurfaceFlags,
    WaterSurfaceShape,
    WaterVertex,
    create_water,
    load_water,
)


def _vertex_values(x: float, y: float, z: float) -> str:
    return f"{x} {y} {z} 0 0 0 1"


class WaterTests(unittest.TestCase):
    def test_quad_round_trip_preserves_original_text_and_metadata(self) -> None:
        record = "  ".join((
            _vertex_values(0, 0, 5),
            _vertex_values(10, 0, 5),
            _vertex_values(0, 10, 5),
            _vertex_values(10, 10, 5),
            "13",
            "0.5",
        ))
        source = (
            b"\xef\xbb\xbf; water surfaces\r\n"
            b"processed\r\n"
            + record.encode()
            + b"\r\n"
        )

        document = WaterDocument.from_bytes(source)
        surface = document[0]

        self.assertEqual(document.to_bytes(), source)
        self.assertTrue(document.has_bom)
        self.assertEqual(surface.shape, WaterSurfaceShape.QUAD)
        self.assertEqual(
            surface.flags,
            WaterSurfaceFlags.VISIBLE
            | WaterSurfaceFlags.RENDER
            | WaterSurfaceFlags.DYNAMIC,
        )
        self.assertTrue(surface.is_visible)
        self.assertTrue(surface.is_rendered)
        self.assertTrue(surface.is_dynamic)
        self.assertEqual(surface.unresolved_flags, 0)
        self.assertEqual(surface.wave_scale, 0.5)
        self.assertEqual(surface.vertices[0].legacy_values, (0.0, 0.0, 0.0, 1.0))

    def test_quad_geometry_follows_serialized_triangle_strip(self) -> None:
        surface = WaterSurface(
            [
                WaterVertex(0, 0, 2),
                WaterVertex(10, 0, 4),
                WaterVertex(0, 10, 6),
                WaterVertex(10, 10, 8),
            ],
            WaterSurfaceFlags.VISIBLE | WaterSurfaceFlags.RENDER,
            0.0,
        )
        document = create_water()
        document.add_surface(surface)

        self.assertEqual(surface.triangle_indices, ((0, 1, 2), (2, 1, 3)))
        self.assertEqual(surface.area_xy, 100.0)
        self.assertTrue(surface.is_axis_aligned())
        self.assertTrue(surface.contains_xy(5, 5))
        self.assertIsNone(surface.height_at(20, 20))
        self.assertAlmostEqual(surface.height_at(2, 2), 3.2)
        self.assertIsNone(surface.height)
        mesh = document.to_mesh_data()
        self.assertEqual(
            mesh["vertices"],
            [(0, 0, 2), (10, 0, 4), (0, 10, 6), (10, 10, 8)],
        )
        self.assertEqual(mesh["triangles"], [(0, 1, 2), (2, 1, 3)])
        self.assertEqual(mesh["surface_indices"], [0, 0])

    def test_edit_rewrites_only_the_changed_surface(self) -> None:
        first = " ".join((
            _vertex_values(0, 0, 1),
            _vertex_values(1, 0, 1),
            _vertex_values(0, 1, 1),
            _vertex_values(1, 1, 1),
            "5",
            "0",
        ))
        second = " ".join((
            _vertex_values(2, 2, 2),
            _vertex_values(3, 2, 2),
            _vertex_values(2, 3, 2),
            _vertex_values(3, 3, 2),
            "9",
            "1",
        ))
        document = WaterDocument.from_text(f"{first}\n{second}\n")
        document[0].wave_scale = 0.25

        output = document.to_text()
        reparsed = WaterDocument.from_text(output)

        self.assertIn("\n" + second + "\n", output)
        self.assertEqual(reparsed[0].wave_scale, 0.25)
        self.assertEqual(reparsed[1].wave_scale, 1.0)

    def test_legacy_triangle_round_trip_and_queries(self) -> None:
        record = " ".join((
            _vertex_values(0, 0, 7),
            _vertex_values(4, 0, 7),
            _vertex_values(0, 4, 7),
            "5",
        ))
        document = load_water(BytesIO((record + "\n").encode()))
        surface = document[0]

        self.assertEqual(document.to_text(), record + "\n")
        self.assertEqual(surface.shape, WaterSurfaceShape.TRIANGLE)
        self.assertIsNone(surface.wave_scale)
        self.assertEqual(surface.height, 7.0)
        self.assertEqual(tuple(surface.iter_triangles()), (
            ((0.0, 0.0, 7.0), (4.0, 0.0, 7.0), (0.0, 4.0, 7.0)),
        ))
        self.assertEqual(document.surfaces_at(1, 1), (surface,))

    def test_mutation_and_visible_mesh_filter(self) -> None:
        document = WaterDocument.empty("custom")
        hidden = document.add_surface(WaterSurface(
            [
                WaterVertex(0, 0, 0),
                WaterVertex(1, 0, 0),
                WaterVertex(0, 1, 0),
            ],
            WaterSurfaceFlags.NONE,
        ))
        visible = document.add_surface(WaterSurface(
            [
                WaterVertex(2, 2, 0),
                WaterVertex(3, 2, 0),
                WaterVertex(2, 3, 0),
            ],
            WaterSurfaceFlags.VISIBLE,
        ))

        self.assertEqual(document.name, "custom.dat")
        self.assertEqual(document.to_mesh_data(visible_only=True)["surface_indices"], [1])
        self.assertTrue(document.remove_surface(hidden))
        self.assertFalse(document.remove_surface(hidden))
        self.assertEqual(document.surfaces, (visible,))

    def test_validation_reports_degenerate_unknown_and_non_finite_data(self) -> None:
        document = WaterDocument.empty()
        document.add_surface(WaterSurface(
            [
                WaterVertex(0, 0, 0),
                WaterVertex(1, 0, 0),
                WaterVertex(2, 0, float("nan")),
            ],
            WaterSurfaceFlags.VISIBLE | WaterSurfaceFlags(0x10),
        ))

        issues = document.validate()

        self.assertEqual(
            {issue.code for issue in issues},
            {"degenerate_surface", "non_finite_value", "unresolved_flags"},
        )
        self.assertEqual(
            next(issue.severity for issue in issues if issue.code == "non_finite_value"),
            WaterIssueSeverity.ERROR,
        )
        with self.assertRaisesRegex(ValueError, "must be finite"):
            document.to_text()

    def test_numeric_records_require_a_supported_field_count(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "line 2 requires 22 or 30 values, got 3",
        ):
            WaterDocument.from_text("; header\n1 2 3\n")


if __name__ == "__main__":
    unittest.main()
