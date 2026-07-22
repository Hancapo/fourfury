from __future__ import annotations

import unittest

from fourfury import MaterialCatalog, MaterialFlags


SAMPLE_MATERIALS = """\
2.00

# name fx heli and physical properties
DEFAULT GENERIC DEFAULT 1.0 0.1 500.0 1.00 -0.15 0 0.0 0.0 5.0 0.5 0 0 0 DEFAULT
GLASS_WEAK GLASS DEFAULT 0.4 0.1 2500.0 0.90 -0.12 0 0.0 0.0 0.0 0.0 1 0 0 GLASS_WEAK
WATER WATER DEFAULT 0.5 0.1 1700.0 0.90 -0.10 2 0.0 0.0 0.0 0.0 0 0 1 WATER
"""


class MaterialCatalogTests(unittest.TestCase):
    def test_parses_real_columns_and_assigns_file_order_ids(self) -> None:
        catalog = MaterialCatalog.from_text(SAMPLE_MATERIALS)

        self.assertEqual(catalog.version, 2.0)
        self.assertEqual(len(catalog), 3)
        self.assertEqual(catalog[0].name, "DEFAULT")
        self.assertEqual(catalog["glass_weak"].material_id, 1)
        self.assertEqual(catalog[1].density, 2500.0)
        self.assertEqual(catalog[1].tyre_grip, 0.9)
        self.assertTrue(catalog[1].flags & MaterialFlags.SEE_THROUGH)
        self.assertTrue(catalog[2].naturally_wet)

    def test_rejects_records_with_missing_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 17 fields"):
            MaterialCatalog.from_text("2.00\nBROKEN GENERIC\n")


if __name__ == "__main__":
    unittest.main()
