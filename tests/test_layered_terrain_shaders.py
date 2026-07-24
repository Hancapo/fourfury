from fourfury.shaders import (
    WdrShaderParameterName,
    WdrShaderPreset,
    WdrShaderProgram,
    find_wdr_shader_definition,
)
from fourfury.wdr import WDR_SHADER_PARAMETER_NAMES


def test_layered_bump_and_spec_parameter_hashes_are_semantic() -> None:
    expected = {
        0x3FFF9563: WdrShaderParameterName.BUMP_SAMPLER_LAYER_0,
        0xB1597815: WdrShaderParameterName.BUMP_SAMPLER_LAYER_3,
        0x60D59498: WdrShaderParameterName.SPEC_SAMPLER_LAYER_0,
        0x69382509: WdrShaderParameterName.SPEC_SAMPLER_LAYER_3,
        0x88CC3D90: WdrShaderParameterName.LOOKUP_SAMPLER,
        0x1D976344: WdrShaderParameterName.SPECULAR_FACTOR_LAYER_0,
        0x3FA1ECE6: WdrShaderParameterName.SPECULAR_COLOR_FACTOR_LAYER_3,
        0x8FBCF203: WdrShaderParameterName.BUMPINESS_LAYER_0,
        0x1DC50E19: WdrShaderParameterName.BUMPINESS_LAYER_3,
    }

    assert {
        name_hash: WDR_SHADER_PARAMETER_NAMES[name_hash]
        for name_hash in expected
    } == expected


def test_layered_terrain_presets_resolve_to_their_programs() -> None:
    for layers in (2, 3, 4):
        name = f"gta_terrain_c_cb_w_{layers}lyr_2tex_blend_spm"
        definition = find_wdr_shader_definition(f"{name}.sps")

        assert definition is not None
        assert definition.preset is WdrShaderPreset(name)
        assert definition.program is WdrShaderProgram(name)
