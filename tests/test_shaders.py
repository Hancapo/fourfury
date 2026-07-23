from __future__ import annotations

import unittest

from fourfury import (
    WDR_SHADER_DEFINITIONS,
    WDR_SHADER_PRESETS_BY_PROGRAM,
    WdrShaderDefaultKind,
    WdrShaderParameterName,
    WdrShaderPreset,
    WdrShaderProgram,
    find_wdr_shader_definition,
    find_wdr_shader_program,
)


class ShaderCatalogTests(unittest.TestCase):
    def test_contains_complete_edition_presets_and_programs(self) -> None:
        self.assertEqual(len(WdrShaderPreset), 134)
        self.assertEqual(len(WdrShaderProgram), 71)
        self.assertEqual(len(WDR_SHADER_DEFINITIONS), 134)
        self.assertIn(WdrShaderPreset.GTA_TREES_EXTENDED, WDR_SHADER_DEFINITIONS)

    def test_resolves_preset_aliases_and_paths(self) -> None:
        definition = find_wdr_shader_definition(
            r"common\shaders\db\gta_alpha.sps"
        )

        self.assertIsNotNone(definition)
        self.assertIs(definition.preset, WdrShaderPreset.GTA_ALPHA)  # type: ignore[union-attr]
        self.assertIs(definition.program, WdrShaderProgram.GTA_DEFAULT)  # type: ignore[union-attr]
        self.assertEqual(definition.draw_bucket, 1)  # type: ignore[union-attr]
        self.assertIn(
            definition,
            WDR_SHADER_PRESETS_BY_PROGRAM[WdrShaderProgram.GTA_DEFAULT],
        )

    def test_exposes_scalar_defaults_without_treating_them_as_wdr_values(self) -> None:
        definition = WDR_SHADER_DEFINITIONS[WdrShaderPreset.GTA_VEHICLE_PAINT1]

        self.assertEqual(definition.get_default("SpecularColor"), 0.15)
        self.assertEqual(definition.get_default("specular2factor"), 40.0)
        self.assertIsNone(definition.draw_bucket)
        self.assertTrue(
            all(
                default.kind is WdrShaderDefaultKind.FLOAT
                for default in definition.defaults
            )
        )

    def test_typed_names_are_string_compatible(self) -> None:
        self.assertEqual(
            find_wdr_shader_program("GTA_DEFAULT"), WdrShaderProgram.GTA_DEFAULT
        )
        self.assertEqual(WdrShaderParameterName.TEXTURE_SAMPLER, "texture_sampler")
        self.assertIsNone(find_wdr_shader_definition("missing.sps"))


if __name__ == "__main__":
    unittest.main()
