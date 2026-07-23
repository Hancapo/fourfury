from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


WdrShaderDefaultValue: TypeAlias = int | float


class WdrShaderPreset(StrEnum):
    """Material preset names shipped in GTA IV's shader database."""

    GTA_ALPHA = "gta_alpha"
    GTA_CUBEMAP_REFLECT = "gta_cubemap_reflect"
    GTA_CUTOUT = "gta_cutout"
    GTA_CUTOUT_FENCE = "gta_cutout_fence"
    GTA_DECAL = "gta_decal"
    GTA_DECAL_AMB_ONLY = "gta_decal_amb_only"
    GTA_DECAL_DIRT = "gta_decal_dirt"
    GTA_DECAL_GLUE = "gta_decal_glue"
    GTA_DECAL_NORMAL_ONLY = "gta_decal_normal_only"
    GTA_DEFAULT = "gta_default"
    GTA_DIFFUSE_INSTANCE = "gta_diffuse_instance"
    GTA_EMISSIVE = "gta_emissive"
    GTA_EMISSIVE_ALPHA = "gta_emissive_alpha"
    GTA_EMISSIVENIGHT = "gta_emissivenight"
    GTA_EMISSIVENIGHT_ALPHA = "gta_emissivenight_alpha"
    GTA_EMISSIVESTRONG = "gta_emissivestrong"
    GTA_EMISSIVESTRONG_ALPHA = "gta_emissivestrong_alpha"
    GTA_GLASS = "gta_glass"
    GTA_GLASS_EMISSIVE = "gta_glass_emissive"
    GTA_GLASS_EMISSIVE_ALPHA = "gta_glass_emissive_alpha"
    GTA_GLASS_EMISSIVENIGHT = "gta_glass_emissivenight"
    GTA_GLASS_EMISSIVENIGHT_ALPHA = "gta_glass_emissivenight_alpha"
    GTA_GLASS_NORMAL_SPEC_REFLECT = "gta_glass_normal_spec_reflect"
    GTA_GLASS_REFLECT = "gta_glass_reflect"
    GTA_GLASS_SPEC = "gta_glass_spec"
    GTA_HAIR_SORTED_ALPHA = "gta_hair_sorted_alpha"
    GTA_HAIR_SORTED_ALPHA_EXPENSIVE = "gta_hair_sorted_alpha_expensive"
    GTA_LEAVES = "gta_leaves"
    GTA_MIRROR = "gta_mirror"
    GTA_NORMAL = "gta_normal"
    GTA_NORMAL_ALPHA = "gta_normal_alpha"
    GTA_NORMAL_CUBEMAP_REFLECT = "gta_normal_cubemap_reflect"
    GTA_NORMAL_CUTOUT = "gta_normal_cutout"
    GTA_NORMAL_DECAL = "gta_normal_decal"
    GTA_NORMAL_REFLECT = "gta_normal_reflect"
    GTA_NORMAL_REFLECT_ALPHA = "gta_normal_reflect_alpha"
    GTA_NORMAL_REFLECT_DECAL = "gta_normal_reflect_decal"
    GTA_NORMAL_REFLECT_SCREENDOORALPHA = "gta_normal_reflect_screendooralpha"
    GTA_NORMAL_SCREENDOORALPHA = "gta_normal_screendooralpha"
    GTA_NORMAL_SPEC = "gta_normal_spec"
    GTA_NORMAL_SPEC_ALPHA = "gta_normal_spec_alpha"
    GTA_NORMAL_SPEC_CUBEMAP_REFLECT = "gta_normal_spec_cubemap_reflect"
    GTA_NORMAL_SPEC_DECAL = "gta_normal_spec_decal"
    GTA_NORMAL_SPEC_REFLECT = "gta_normal_spec_reflect"
    GTA_NORMAL_SPEC_REFLECT_ALPHA = "gta_normal_spec_reflect_alpha"
    GTA_NORMAL_SPEC_REFLECT_DECAL = "gta_normal_spec_reflect_decal"
    GTA_NORMAL_SPEC_REFLECT_EMISSIVE = "gta_normal_spec_reflect_emissive"
    GTA_NORMAL_SPEC_REFLECT_EMISSIVE_ALPHA = "gta_normal_spec_reflect_emissive_alpha"
    GTA_NORMAL_SPEC_REFLECT_EMISSIVENIGHT = "gta_normal_spec_reflect_emissivenight"
    GTA_NORMAL_SPEC_REFLECT_EMISSIVENIGHT_ALPHA = "gta_normal_spec_reflect_emissivenight_alpha"
    GTA_NORMAL_SPEC_SCREENDOORALPHA = "gta_normal_spec_screendooralpha"
    GTA_PARALLAX = "gta_parallax"
    GTA_PARALLAX_SPECMAP = "gta_parallax_specmap"
    GTA_PARALLAX_STEEP = "gta_parallax_steep"
    GTA_PED = "gta_ped"
    GTA_PED_ALPHA = "gta_ped_alpha"
    GTA_PED_REFLECT = "gta_ped_reflect"
    GTA_PED_REFLECT_ALPHA = "gta_ped_reflect_alpha"
    GTA_PED_SKIN = "gta_ped_skin"
    GTA_PED_SKIN_BLENDSHAPE = "gta_ped_skin_blendshape"
    GTA_PROJTEX = "gta_projtex"
    GTA_PROJTEX_STEEP = "gta_projtex_steep"
    GTA_RADAR = "gta_radar"
    GTA_REFLECT = "gta_reflect"
    GTA_REFLECT_ALPHA = "gta_reflect_alpha"
    GTA_REFLECT_DECAL = "gta_reflect_decal"
    GTA_RMPTFX_MESH = "gta_rmptfx_mesh"
    GTA_SPEC = "gta_spec"
    GTA_SPEC_ALPHA = "gta_spec_alpha"
    GTA_SPEC_CONST = "gta_spec_const"
    GTA_SPEC_DECAL = "gta_spec_decal"
    GTA_SPEC_REFLECT = "gta_spec_reflect"
    GTA_SPEC_REFLECT_ALPHA = "gta_spec_reflect_alpha"
    GTA_SPEC_REFLECT_DECAL = "gta_spec_reflect_decal"
    GTA_SPEC_REFLECT_SCREENDOORALPHA = "gta_spec_reflect_screendooralpha"
    GTA_SPEC_SCREENDOORALPHA = "gta_spec_screendooralpha"
    GTA_TERRAIN_VA_2LYR = "gta_terrain_va_2lyr"
    GTA_TERRAIN_VA_3LYR = "gta_terrain_va_3lyr"
    GTA_TERRAIN_VA_4LYR = "gta_terrain_va_4lyr"
    GTA_TREES = "gta_trees"
    GTA_TREES_EXTENDED = "gta_trees_extended"
    GTA_VEHICLE = "gta_vehicle"
    GTA_VEHICLE_BADGES = "gta_vehicle_badges"
    GTA_VEHICLE_BASIC = "gta_vehicle_basic"
    GTA_VEHICLE_CHROME = "gta_vehicle_chrome"
    GTA_VEHICLE_DEFAULT = "gta_vehicle_default"
    GTA_VEHICLE_DEFAULT_2LYR = "gta_vehicle_default_2lyr"
    GTA_VEHICLE_DEFAULT_2LYR_DMG = "gta_vehicle_default_2lyr_dmg"
    GTA_VEHICLE_DEFAULT_DMG = "gta_vehicle_default_dmg"
    GTA_VEHICLE_DISC = "gta_vehicle_disc"
    GTA_VEHICLE_GENERIC = "gta_vehicle_generic"
    GTA_VEHICLE_GLASS = "gta_vehicle_glass"
    GTA_VEHICLE_GLASS_DMG = "gta_vehicle_glass_dmg"
    GTA_VEHICLE_GLASS_EMISSIVE = "gta_vehicle_glass_emissive"
    GTA_VEHICLE_INTERIOR = "gta_vehicle_interior"
    GTA_VEHICLE_INTERIOR2 = "gta_vehicle_interior2"
    GTA_VEHICLE_LIGHTS = "gta_vehicle_lights"
    GTA_VEHICLE_LIGHTSEMISSIVE = "gta_vehicle_lightsemissive"
    GTA_VEHICLE_MESH = "gta_vehicle_mesh"
    GTA_VEHICLE_NOSPLASH = "gta_vehicle_nosplash"
    GTA_VEHICLE_NOWATER = "gta_vehicle_nowater"
    GTA_VEHICLE_PAINT1 = "gta_vehicle_paint1"
    GTA_VEHICLE_PAINT2 = "gta_vehicle_paint2"
    GTA_VEHICLE_PAINT3 = "gta_vehicle_paint3"
    GTA_VEHICLE_RIMS1 = "gta_vehicle_rims1"
    GTA_VEHICLE_RIMS1_ALPHA = "gta_vehicle_rims1_alpha"
    GTA_VEHICLE_RIMS2 = "gta_vehicle_rims2"
    GTA_VEHICLE_RUBBER = "gta_vehicle_rubber"
    GTA_VEHICLE_SHUTS = "gta_vehicle_shuts"
    GTA_VEHICLE_SPEC = "gta_vehicle_spec"
    GTA_VEHICLE_SPEC_2LYR = "gta_vehicle_spec_2lyr"
    GTA_VEHICLE_SPEC_2LYR_DMG = "gta_vehicle_spec_2lyr_dmg"
    GTA_VEHICLE_SPEC_BUMP = "gta_vehicle_spec_bump"
    GTA_VEHICLE_SPEC_BUMP_DMG = "gta_vehicle_spec_bump_dmg"
    GTA_VEHICLE_SPEC_DMG = "gta_vehicle_spec_dmg"
    GTA_VEHICLE_SPEC_REFLECT = "gta_vehicle_spec_reflect"
    GTA_VEHICLE_SPEC_REFLECT_2LYR = "gta_vehicle_spec_reflect_2lyr"
    GTA_VEHICLE_SPEC_REFLECT_2LYR_DMG = "gta_vehicle_spec_reflect_2lyr_dmg"
    GTA_VEHICLE_SPEC_REFLECT_ALPHA = "gta_vehicle_spec_reflect_alpha"
    GTA_VEHICLE_SPEC_REFLECT_ALPHA_DMG = "gta_vehicle_spec_reflect_alpha_dmg"
    GTA_VEHICLE_SPEC_REFLECT_BUMP = "gta_vehicle_spec_reflect_bump"
    GTA_VEHICLE_SPEC_REFLECT_BUMP_2LYR = "gta_vehicle_spec_reflect_bump_2lyr"
    GTA_VEHICLE_SPEC_REFLECT_BUMP_2LYR_DMG = "gta_vehicle_spec_reflect_bump_2lyr_dmg"
    GTA_VEHICLE_SPEC_REFLECT_BUMP_ALPHA_DMG = "gta_vehicle_spec_reflect_bump_alpha_dmg"
    GTA_VEHICLE_SPEC_REFLECT_BUMP_DMG = "gta_vehicle_spec_reflect_bump_dmg"
    GTA_VEHICLE_SPEC_REFLECT_BUMPUV = "gta_vehicle_spec_reflect_bumpuv"
    GTA_VEHICLE_SPEC_REFLECT_BUMPUV_2LYR = "gta_vehicle_spec_reflect_bumpuv_2lyr"
    GTA_VEHICLE_SPEC_REFLECT_BUMPUV_2LYR_DMG = "gta_vehicle_spec_reflect_bumpuv_2lyr_dmg"
    GTA_VEHICLE_SPEC_REFLECT_BUMPUV_DMG = "gta_vehicle_spec_reflect_bumpuv_dmg"
    GTA_VEHICLE_SPEC_REFLECT_DMG = "gta_vehicle_spec_reflect_dmg"
    GTA_VEHICLE_TIRE = "gta_vehicle_tire"
    GTA_VEHICLE_VEHGLASS = "gta_vehicle_vehglass"
    GTA_WIRE = "gta_wire"
    RAGE_BILLBOARD_NOBUMP = "rage_billboard_nobump"


class WdrShaderProgram(StrEnum):
    """Compiled shader program names referenced by WDR materials."""

    GTA_CUBEMAP_REFLECT = "gta_cubemap_reflect"
    GTA_CUTOUT_FENCE = "gta_cutout_fence"
    GTA_DECAL_AMB_ONLY = "gta_decal_amb_only"
    GTA_DECAL_DIRT = "gta_decal_dirt"
    GTA_DECAL_GLUE = "gta_decal_glue"
    GTA_DECAL_NORMAL_ONLY = "gta_decal_normal_only"
    GTA_DEFAULT = "gta_default"
    GTA_DIFFUSE_INSTANCE = "gta_diffuse_instance"
    GTA_EMISSIVE = "gta_emissive"
    GTA_EMISSIVENIGHT = "gta_emissivenight"
    GTA_EMISSIVESTRONG = "gta_emissivestrong"
    GTA_GLASS = "gta_glass"
    GTA_GLASS_EMISSIVE = "gta_glass_emissive"
    GTA_GLASS_EMISSIVENIGHT = "gta_glass_emissivenight"
    GTA_GLASS_NORMAL_SPEC_REFLECT = "gta_glass_normal_spec_reflect"
    GTA_GLASS_REFLECT = "gta_glass_reflect"
    GTA_GLASS_SPEC = "gta_glass_spec"
    GTA_HAIR_SORTED_ALPHA = "gta_hair_sorted_alpha"
    GTA_HAIR_SORTED_ALPHA_EXP = "gta_hair_sorted_alpha_exp"
    GTA_NORMAL = "gta_normal"
    GTA_NORMAL_CUBEMAP_REFLECT = "gta_normal_cubemap_reflect"
    GTA_NORMAL_DECAL = "gta_normal_decal"
    GTA_NORMAL_REFLECT = "gta_normal_reflect"
    GTA_NORMAL_REFLECT_DECAL = "gta_normal_reflect_decal"
    GTA_NORMAL_SPEC = "gta_normal_spec"
    GTA_NORMAL_SPEC_CUBEMAP_REFLECT = "gta_normal_spec_cubemap_reflect"
    GTA_NORMAL_SPEC_DECAL = "gta_normal_spec_decal"
    GTA_NORMAL_SPEC_REFLECT = "gta_normal_spec_reflect"
    GTA_NORMAL_SPEC_REFLECT_DECAL = "gta_normal_spec_reflect_decal"
    GTA_NORMAL_SPEC_REFLECT_EMISSIVE = "gta_normal_spec_reflect_emissive"
    GTA_NORMAL_SPEC_REFLECT_EMISSIVENIGHT = "gta_normal_spec_reflect_emissivenight"
    GTA_PARALLAX = "gta_parallax"
    GTA_PARALLAX_SPECMAP = "gta_parallax_specmap"
    GTA_PARALLAX_STEEP = "gta_parallax_steep"
    GTA_PED = "gta_ped"
    GTA_PED_REFLECT = "gta_ped_reflect"
    GTA_PED_SKIN = "gta_ped_skin"
    GTA_PED_SKIN_BLENDSHAPE = "gta_ped_skin_blendshape"
    GTA_PROJTEX = "gta_projtex"
    GTA_PROJTEX_STEEP = "gta_projtex_steep"
    GTA_RADAR = "gta_radar"
    GTA_REFLECT = "gta_reflect"
    GTA_RMPTFX_MESH = "gta_rmptfx_mesh"
    GTA_SPEC = "gta_spec"
    GTA_SPEC_REFLECT = "gta_spec_reflect"
    GTA_TERRAIN_VA_2LYR = "gta_terrain_va_2lyr"
    GTA_TERRAIN_VA_3LYR = "gta_terrain_va_3lyr"
    GTA_TERRAIN_VA_4LYR = "gta_terrain_va_4lyr"
    GTA_TREES = "gta_trees"
    GTA_TREES_EXTENDED = "gta_trees_extended"
    GTA_VEHICLE_BADGES = "gta_vehicle_badges"
    GTA_VEHICLE_BASIC = "gta_vehicle_basic"
    GTA_VEHICLE_CHROME = "gta_vehicle_chrome"
    GTA_VEHICLE_DISC = "gta_vehicle_disc"
    GTA_VEHICLE_GENERIC = "gta_vehicle_generic"
    GTA_VEHICLE_INTERIOR = "gta_vehicle_interior"
    GTA_VEHICLE_INTERIOR2 = "gta_vehicle_interior2"
    GTA_VEHICLE_LIGHTSEMISSIVE = "gta_vehicle_lightsemissive"
    GTA_VEHICLE_MESH = "gta_vehicle_mesh"
    GTA_VEHICLE_PAINT1 = "gta_vehicle_paint1"
    GTA_VEHICLE_PAINT2 = "gta_vehicle_paint2"
    GTA_VEHICLE_PAINT3 = "gta_vehicle_paint3"
    GTA_VEHICLE_RIMS1 = "gta_vehicle_rims1"
    GTA_VEHICLE_RIMS2 = "gta_vehicle_rims2"
    GTA_VEHICLE_RUBBER = "gta_vehicle_rubber"
    GTA_VEHICLE_SHUTS = "gta_vehicle_shuts"
    GTA_VEHICLE_TIRE = "gta_vehicle_tire"
    GTA_VEHICLE_VEHGLASS = "gta_vehicle_vehglass"
    GTA_WIRE = "gta_wire"
    RAGE_BILLBOARD_NOBUMP = "rage_billboard_nobump"
    RAGE_DEFAULT = "rage_default"


class WdrShaderParameterName(StrEnum):
    """Semantic names for shader parameter hashes identified by FourFury."""

    ALTERNATE_REMAP = "alternate_remap"
    AMBIENT_DECAL_MASK = "ambient_decal_mask"
    BONE_DAMAGE_0 = "bone_damage_0"
    BONE_DAMAGE_ENABLED = "bone_damage_enabled"
    BOUND_RADIUS = "bound_radius"
    BUMP_SAMPLER = "bump_sampler"
    BUMPINESS = "bumpiness"
    DAMAGE_SAMPLER = "damage_sampler"
    DAMAGE_SPECULAR_TEXTURE_SAMPLER = "damage_specular_texture_sampler"
    DAMAGE_TEXTURE_SAMPLER = "damage_texture_sampler"
    DAMAGE_VERTEX_BUFFER = "damage_vertex_buffer"
    DIFFUSE_2_SPECULAR_MODIFIER = "diffuse_2_specular_modifier"
    DIFFUSE_COLOR = "diffuse_color"
    DIMMER_SET = "dimmer_set"
    DIRT_COLOR = "dirt_color"
    DIRT_DECAL_MASK = "dirt_decal_mask"
    DIRT_LEVEL = "dirt_level"
    DIRT_SAMPLER = "dirt_sampler"
    DRAW_BUCKET = "draw_bucket"
    EMISSIVE_MULTIPLIER = "emissive_multiplier"
    ENVIRONMENT_SAMPLER = "environment_sampler"
    FACET_MASK = "facet_mask"
    FADE_THICKNESS = "fade_thickness"
    GLOBAL_ANIMATION_UV_0 = "global_animation_uv_0"
    GLOBAL_ANIMATION_UV_1 = "global_animation_uv_1"
    IMPOSTER_DIRECTION = "imposter_direction"
    LUMINANCE_CONSTANTS = "luminance_constants"
    MATERIAL_COLOR_SCALE = "material_color_scale"
    MATERIAL_DIFFUSE = "material_diffuse"
    MATERIAL_DIFFUSE_COLOR = "material_diffuse_color"
    MATERIAL_DIFFUSE_COLOR_2 = "material_diffuse_color_2"
    NORMAL_TABLE = "normal_table"
    ORDER_NUMBER = "order_number"
    PARALLAX_SCALE_BIAS = "parallax_scale_bias"
    REFLECTIVE_POWER = "reflective_power"
    REFLECTIVE_POWER_ENABLED = "reflective_power_enabled"
    SHADOW_MAP_RESOLUTION = "shadow_map_resolution"
    SPEC_MAP_INTENSITY_MASK = "spec_map_intensity_mask"
    SPEC_SAMPLER = "spec_sampler"
    SPECULAR_2_COLOR = "specular_2_color"
    SPECULAR_2_COLOR_INTENSITY = "specular_2_color_intensity"
    SPECULAR_2_COLOR_INTENSITY_REFLECTION = "specular_2_color_intensity_reflection"
    SPECULAR_2_FACTOR = "specular_2_factor"
    SPECULAR_2_FACTOR_ENABLED = "specular_2_factor_enabled"
    SPECULAR_COLOR_FACTOR = "specular_color_factor"
    SPECULAR_COLOR_FACTOR_ENABLED = "specular_color_factor_enabled"
    SPECULAR_FACTOR = "specular_factor"
    SPECULAR_FACTOR_ENABLED = "specular_factor_enabled"
    SUBSURFACE_COLOR = "subsurface_color"
    SUBSURFACE_SCATTERING_WIDTH = "subsurface_scattering_width"
    SUBSURFACE_SCATTERING_WRAP = "subsurface_scattering_wrap"
    SWITCH_ON = "switch_on"
    TEXTURE_SAMPLER = "texture_sampler"
    TEXTURE_SAMPLER_2 = "texture_sampler_2"
    TEXTURE_SAMPLER_LAYER_0 = "texture_sampler_layer_0"
    TEXTURE_SAMPLER_LAYER_1 = "texture_sampler_layer_1"
    TEXTURE_SAMPLER_LAYER_2 = "texture_sampler_layer_2"
    TEXTURE_SAMPLER_LAYER_3 = "texture_sampler_layer_3"
    TYRE_DEFORMATION_ENABLED = "tyre_deformation_enabled"
    TYRE_DEFORMATION_PARAMETERS = "tyre_deformation_parameters"
    TYRE_DEFORMATION_PARAMETERS_2 = "tyre_deformation_parameters_2"
    WHEEL_TRANSFORM = "wheel_transform"
    WORLD_INSTANCE_INVERSE_TRANSPOSE = "world_instance_inverse_transpose"
    WORLD_INSTANCE_MATRIX = "world_instance_matrix"
    Z_SHIFT = "z_shift"
    Z_SHIFT_SCALE = "z_shift_scale"


class WdrShaderDefaultKind(StrEnum):
    INTEGER = "int"
    FLOAT = "float"


@dataclass(frozen=True, slots=True)
class WdrShaderDefault:
    """One scalar default declared by a stock SPS material preset."""

    name: str
    kind: WdrShaderDefaultKind
    value: WdrShaderDefaultValue


@dataclass(frozen=True, slots=True)
class WdrShaderDefinition:
    """Relationship between an SPS preset and its compiled shader program."""

    preset: WdrShaderPreset
    program: WdrShaderProgram
    defaults: tuple[WdrShaderDefault, ...] = ()

    @property
    def file_name(self) -> str:
        return f"{self.preset.value}.sps"

    @property
    def draw_bucket(self) -> int | None:
        value = self.get_default("__rage_drawbucket")
        return value if isinstance(value, int) else None

    def get_default(self, name: str) -> WdrShaderDefaultValue | None:
        key = str(name).casefold()
        item = next(
            (default for default in self.defaults if default.name.casefold() == key),
            None,
        )
        return None if item is None else item.value


# Generated from the stock Complete Edition common/shaders/db SPS files. Presets
# not listed here select the program with the same name.
_WDR_SHADER_PROGRAM_OVERRIDES = {
    WdrShaderPreset.GTA_ALPHA: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_CUTOUT: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_DECAL: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_EMISSIVE_ALPHA: WdrShaderProgram.GTA_EMISSIVE,
    WdrShaderPreset.GTA_EMISSIVENIGHT_ALPHA: WdrShaderProgram.GTA_EMISSIVENIGHT,
    WdrShaderPreset.GTA_EMISSIVESTRONG_ALPHA: WdrShaderProgram.GTA_EMISSIVESTRONG,
    WdrShaderPreset.GTA_GLASS_EMISSIVE_ALPHA: WdrShaderProgram.GTA_GLASS_EMISSIVE,
    WdrShaderPreset.GTA_GLASS_EMISSIVENIGHT_ALPHA: WdrShaderProgram.GTA_GLASS_EMISSIVENIGHT,
    WdrShaderPreset.GTA_HAIR_SORTED_ALPHA_EXPENSIVE: WdrShaderProgram.GTA_HAIR_SORTED_ALPHA_EXP,
    WdrShaderPreset.GTA_LEAVES: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_MIRROR: WdrShaderProgram.GTA_REFLECT,
    WdrShaderPreset.GTA_NORMAL_ALPHA: WdrShaderProgram.GTA_NORMAL,
    WdrShaderPreset.GTA_NORMAL_CUTOUT: WdrShaderProgram.GTA_NORMAL,
    WdrShaderPreset.GTA_NORMAL_REFLECT_ALPHA: WdrShaderProgram.GTA_NORMAL_REFLECT,
    WdrShaderPreset.GTA_NORMAL_REFLECT_SCREENDOORALPHA: WdrShaderProgram.GTA_NORMAL_REFLECT,
    WdrShaderPreset.GTA_NORMAL_SCREENDOORALPHA: WdrShaderProgram.GTA_NORMAL,
    WdrShaderPreset.GTA_NORMAL_SPEC_ALPHA: WdrShaderProgram.GTA_NORMAL_SPEC,
    WdrShaderPreset.GTA_NORMAL_SPEC_REFLECT_ALPHA: WdrShaderProgram.GTA_NORMAL_SPEC_REFLECT,
    WdrShaderPreset.GTA_NORMAL_SPEC_REFLECT_EMISSIVE_ALPHA:
        WdrShaderProgram.GTA_NORMAL_SPEC_REFLECT_EMISSIVE,
    WdrShaderPreset.GTA_NORMAL_SPEC_REFLECT_EMISSIVENIGHT_ALPHA:
        WdrShaderProgram.GTA_NORMAL_SPEC_REFLECT_EMISSIVENIGHT,
    WdrShaderPreset.GTA_NORMAL_SPEC_SCREENDOORALPHA: WdrShaderProgram.GTA_NORMAL_SPEC,
    WdrShaderPreset.GTA_PED_ALPHA: WdrShaderProgram.GTA_PED,
    WdrShaderPreset.GTA_PED_REFLECT_ALPHA: WdrShaderProgram.GTA_PED_REFLECT,
    WdrShaderPreset.GTA_REFLECT_ALPHA: WdrShaderProgram.GTA_REFLECT,
    WdrShaderPreset.GTA_REFLECT_DECAL: WdrShaderProgram.GTA_REFLECT,
    WdrShaderPreset.GTA_SPEC_ALPHA: WdrShaderProgram.GTA_SPEC,
    WdrShaderPreset.GTA_SPEC_CONST: WdrShaderProgram.RAGE_DEFAULT,
    WdrShaderPreset.GTA_SPEC_DECAL: WdrShaderProgram.GTA_SPEC,
    WdrShaderPreset.GTA_SPEC_REFLECT_ALPHA: WdrShaderProgram.GTA_SPEC_REFLECT,
    WdrShaderPreset.GTA_SPEC_REFLECT_DECAL: WdrShaderProgram.GTA_SPEC_REFLECT,
    WdrShaderPreset.GTA_SPEC_REFLECT_SCREENDOORALPHA: WdrShaderProgram.GTA_SPEC_REFLECT,
    WdrShaderPreset.GTA_SPEC_SCREENDOORALPHA: WdrShaderProgram.GTA_SPEC,
    WdrShaderPreset.GTA_VEHICLE: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_DEFAULT: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_DEFAULT_2LYR: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_DEFAULT_2LYR_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_DEFAULT_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_GLASS: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_GLASS_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_GLASS_EMISSIVE: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_LIGHTS: WdrShaderProgram.GTA_VEHICLE_VEHGLASS,
    WdrShaderPreset.GTA_VEHICLE_NOSPLASH: WdrShaderProgram.GTA_VEHICLE_PAINT1,
    WdrShaderPreset.GTA_VEHICLE_NOWATER: WdrShaderProgram.GTA_VEHICLE_PAINT1,
    WdrShaderPreset.GTA_VEHICLE_RIMS1_ALPHA: WdrShaderProgram.GTA_VEHICLE_RIMS1,
    WdrShaderPreset.GTA_VEHICLE_SPEC: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_2LYR: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_2LYR_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_BUMP: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_BUMP_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_2LYR: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_2LYR_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_ALPHA: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_ALPHA_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_BUMP: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_BUMP_2LYR: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_BUMP_2LYR_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_BUMP_ALPHA_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_BUMP_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_BUMPUV: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_BUMPUV_2LYR: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_BUMPUV_2LYR_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_BUMPUV_DMG: WdrShaderProgram.GTA_DEFAULT,
    WdrShaderPreset.GTA_VEHICLE_SPEC_REFLECT_DMG: WdrShaderProgram.GTA_DEFAULT,
}

_WDR_SHADER_DRAW_BUCKET_GROUPS = {
    1: (
        WdrShaderPreset.GTA_ALPHA,
        WdrShaderPreset.GTA_GLASS,
        WdrShaderPreset.GTA_GLASS_NORMAL_SPEC_REFLECT,
        WdrShaderPreset.GTA_GLASS_REFLECT,
        WdrShaderPreset.GTA_GLASS_SPEC,
        WdrShaderPreset.GTA_NORMAL_ALPHA,
        WdrShaderPreset.GTA_NORMAL_REFLECT_ALPHA,
        WdrShaderPreset.GTA_NORMAL_SPEC_ALPHA,
        WdrShaderPreset.GTA_NORMAL_SPEC_REFLECT_ALPHA,
        WdrShaderPreset.GTA_PED_ALPHA,
        WdrShaderPreset.GTA_PED_REFLECT_ALPHA,
        WdrShaderPreset.GTA_REFLECT_ALPHA,
        WdrShaderPreset.GTA_RMPTFX_MESH,
        WdrShaderPreset.GTA_SPEC_ALPHA,
        WdrShaderPreset.GTA_SPEC_REFLECT_ALPHA,
        WdrShaderPreset.GTA_VEHICLE_BADGES,
        WdrShaderPreset.GTA_VEHICLE_DISC,
        WdrShaderPreset.GTA_VEHICLE_LIGHTS,
        WdrShaderPreset.GTA_VEHICLE_LIGHTSEMISSIVE,
        WdrShaderPreset.GTA_VEHICLE_VEHGLASS,
        WdrShaderPreset.GTA_WIRE,
    ),
    2: (
        WdrShaderPreset.GTA_DECAL,
        WdrShaderPreset.GTA_DECAL_AMB_ONLY,
        WdrShaderPreset.GTA_DECAL_DIRT,
        WdrShaderPreset.GTA_DECAL_GLUE,
        WdrShaderPreset.GTA_DECAL_NORMAL_ONLY,
        WdrShaderPreset.GTA_NORMAL_DECAL,
        WdrShaderPreset.GTA_NORMAL_REFLECT_DECAL,
        WdrShaderPreset.GTA_NORMAL_SPEC_DECAL,
        WdrShaderPreset.GTA_NORMAL_SPEC_REFLECT_DECAL,
        WdrShaderPreset.GTA_REFLECT_DECAL,
        WdrShaderPreset.GTA_SPEC_DECAL,
        WdrShaderPreset.GTA_SPEC_REFLECT_DECAL,
    ),
    3: (
        WdrShaderPreset.GTA_CUTOUT,
        WdrShaderPreset.GTA_CUTOUT_FENCE,
        WdrShaderPreset.GTA_HAIR_SORTED_ALPHA,
        WdrShaderPreset.GTA_HAIR_SORTED_ALPHA_EXPENSIVE,
        WdrShaderPreset.GTA_NORMAL_CUTOUT,
        WdrShaderPreset.GTA_NORMAL_REFLECT_SCREENDOORALPHA,
        WdrShaderPreset.GTA_NORMAL_SCREENDOORALPHA,
        WdrShaderPreset.GTA_NORMAL_SPEC_SCREENDOORALPHA,
        WdrShaderPreset.GTA_SPEC_REFLECT_SCREENDOORALPHA,
        WdrShaderPreset.GTA_SPEC_SCREENDOORALPHA,
        WdrShaderPreset.GTA_TREES,
        WdrShaderPreset.GTA_TREES_EXTENDED,
        WdrShaderPreset.GTA_VEHICLE_RIMS1_ALPHA,
    ),
    4: (
        WdrShaderPreset.GTA_EMISSIVE,
        WdrShaderPreset.GTA_EMISSIVENIGHT,
        WdrShaderPreset.GTA_EMISSIVESTRONG,
        WdrShaderPreset.GTA_GLASS_EMISSIVE,
        WdrShaderPreset.GTA_GLASS_EMISSIVENIGHT,
        WdrShaderPreset.GTA_NORMAL_SPEC_REFLECT_EMISSIVE,
        WdrShaderPreset.GTA_NORMAL_SPEC_REFLECT_EMISSIVENIGHT,
    ),
    5: (
        WdrShaderPreset.GTA_EMISSIVE_ALPHA,
        WdrShaderPreset.GTA_EMISSIVENIGHT_ALPHA,
        WdrShaderPreset.GTA_EMISSIVESTRONG_ALPHA,
        WdrShaderPreset.GTA_GLASS_EMISSIVE_ALPHA,
        WdrShaderPreset.GTA_GLASS_EMISSIVENIGHT_ALPHA,
        WdrShaderPreset.GTA_NORMAL_SPEC_REFLECT_EMISSIVE_ALPHA,
        WdrShaderPreset.GTA_NORMAL_SPEC_REFLECT_EMISSIVENIGHT_ALPHA,
    ),
    29: (
        WdrShaderPreset.GTA_VEHICLE_NOSPLASH,
    ),
    30: (
        WdrShaderPreset.GTA_VEHICLE_NOWATER,
    ),
}

_WDR_SHADER_SCALAR_DEFAULTS = {
    WdrShaderPreset.GTA_VEHICLE_CHROME: (
        WdrShaderDefault("SpecularColor", WdrShaderDefaultKind.FLOAT, 0.2),
        WdrShaderDefault("Specular", WdrShaderDefaultKind.FLOAT, 180.0),
    ),
    WdrShaderPreset.GTA_VEHICLE_PAINT1: (
        WdrShaderDefault("SpecularColor", WdrShaderDefaultKind.FLOAT, 0.15),
        WdrShaderDefault("Specular", WdrShaderDefaultKind.FLOAT, 180.0),
        WdrShaderDefault("Specular2Factor", WdrShaderDefaultKind.FLOAT, 40.0),
        WdrShaderDefault("specular2ColorIntensity", WdrShaderDefaultKind.FLOAT, 1.7),
    ),
    WdrShaderPreset.GTA_VEHICLE_PAINT2: (
        WdrShaderDefault("SpecularColor", WdrShaderDefaultKind.FLOAT, 0.15),
        WdrShaderDefault("Specular", WdrShaderDefaultKind.FLOAT, 180.0),
        WdrShaderDefault("Specular2Factor", WdrShaderDefaultKind.FLOAT, 40.0),
        WdrShaderDefault("specular2ColorIntensity", WdrShaderDefaultKind.FLOAT, 1.7),
    ),
    WdrShaderPreset.GTA_VEHICLE_PAINT3: (
        WdrShaderDefault("SpecularColor", WdrShaderDefaultKind.FLOAT, 0.15),
        WdrShaderDefault("Specular", WdrShaderDefaultKind.FLOAT, 180.0),
        WdrShaderDefault("Specular2Factor", WdrShaderDefaultKind.FLOAT, 40.0),
        WdrShaderDefault("specular2ColorIntensity", WdrShaderDefaultKind.FLOAT, 1.7),
    ),
    WdrShaderPreset.GTA_VEHICLE_RIMS1: (
        WdrShaderDefault("SpecularColor", WdrShaderDefaultKind.FLOAT, 0.2),
        WdrShaderDefault("Specular", WdrShaderDefaultKind.FLOAT, 180.0),
    ),
    WdrShaderPreset.GTA_VEHICLE_RIMS1_ALPHA: (
        WdrShaderDefault("SpecularColor", WdrShaderDefaultKind.FLOAT, 0.2),
        WdrShaderDefault("Specular", WdrShaderDefaultKind.FLOAT, 180.0),
    ),
    WdrShaderPreset.GTA_VEHICLE_RIMS2: (
        WdrShaderDefault("SpecularColor", WdrShaderDefaultKind.FLOAT, 0.2),
        WdrShaderDefault("Specular", WdrShaderDefaultKind.FLOAT, 180.0),
    ),
    WdrShaderPreset.GTA_VEHICLE_SHUTS: (
        WdrShaderDefault("SpecularColor", WdrShaderDefaultKind.FLOAT, 0.3),
        WdrShaderDefault("Specular", WdrShaderDefaultKind.FLOAT, 180.0),
    ),
    WdrShaderPreset.GTA_VEHICLE_VEHGLASS: (
        WdrShaderDefault("SpecularColor", WdrShaderDefaultKind.FLOAT, 0.15),
        WdrShaderDefault("Specular", WdrShaderDefaultKind.FLOAT, 180.0),
    ),
}


def _program_for_preset(preset: WdrShaderPreset) -> WdrShaderProgram:
    override = _WDR_SHADER_PROGRAM_OVERRIDES.get(preset)
    if override is not None:
        return override
    return WdrShaderProgram(preset.value)


_WDR_SHADER_DRAW_BUCKETS = {
    preset: bucket
    for bucket, presets in _WDR_SHADER_DRAW_BUCKET_GROUPS.items()
    for preset in presets
}


def _defaults_for_preset(preset: WdrShaderPreset) -> tuple[WdrShaderDefault, ...]:
    defaults: list[WdrShaderDefault] = []
    bucket = _WDR_SHADER_DRAW_BUCKETS.get(preset)
    if bucket is not None:
        defaults.append(
            WdrShaderDefault(
                "__rage_drawbucket", WdrShaderDefaultKind.INTEGER, bucket
            )
        )
    defaults.extend(_WDR_SHADER_SCALAR_DEFAULTS.get(preset, ()))
    return tuple(defaults)


WDR_SHADER_DEFINITIONS: dict[WdrShaderPreset, WdrShaderDefinition] = {
    preset: WdrShaderDefinition(
        preset,
        _program_for_preset(preset),
        _defaults_for_preset(preset),
    )
    for preset in WdrShaderPreset
}

WDR_SHADER_PRESETS_BY_PROGRAM: dict[
    WdrShaderProgram, tuple[WdrShaderDefinition, ...]
] = {
    program: tuple(
        definition
        for definition in WDR_SHADER_DEFINITIONS.values()
        if definition.program is program
    )
    for program in WdrShaderProgram
}


def find_wdr_shader_definition(
    value: str | WdrShaderPreset,
) -> WdrShaderDefinition | None:
    """Look up a material preset by enum, bare name, file name, or path."""

    if isinstance(value, WdrShaderPreset):
        return WDR_SHADER_DEFINITIONS[value]
    name = str(value).replace("\\", "/").rsplit("/", 1)[-1].strip().casefold()
    if name.endswith(".sps"):
        name = name[:-4]
    try:
        preset = WdrShaderPreset(name)
    except ValueError:
        return None
    return WDR_SHADER_DEFINITIONS[preset]


def find_wdr_shader_program(
    value: str | WdrShaderProgram,
) -> WdrShaderProgram | None:
    """Resolve a known compiled shader program name."""

    if isinstance(value, WdrShaderProgram):
        return value
    name = str(value).strip().casefold()
    try:
        return WdrShaderProgram(name)
    except ValueError:
        return None


__all__ = [
    "WDR_SHADER_DEFINITIONS",
    "WDR_SHADER_PRESETS_BY_PROGRAM",
    "WdrShaderDefault",
    "WdrShaderDefaultKind",
    "WdrShaderDefaultValue",
    "WdrShaderDefinition",
    "WdrShaderParameterName",
    "WdrShaderPreset",
    "WdrShaderProgram",
    "find_wdr_shader_definition",
    "find_wdr_shader_program",
]
