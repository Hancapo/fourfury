from __future__ import annotations

import unittest

from fourfury import WbnMaterialType


class WbnMaterialTypeTests(unittest.TestCase):
    def test_exposes_stock_material_names_with_binary_ids(self) -> None:
        self.assertEqual(len(WbnMaterialType), 156)
        self.assertEqual(WbnMaterialType.DEFAULT, 0)
        self.assertEqual(WbnMaterialType.ROCK, 11)
        self.assertEqual(WbnMaterialType.WATER, 98)
        self.assertEqual(WbnMaterialType.POOLTABLE_POCKET, 155)

    def test_resolves_ids_and_names_without_external_data(self) -> None:
        material = WbnMaterialType(76)

        self.assertIs(material, WbnMaterialType.GLASS_WEAK)
        self.assertEqual(material.name, "GLASS_WEAK")


if __name__ == "__main__":
    unittest.main()
