from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, IntFlag

from ..model import (
    ModelBone,
    ModelLight,
    ModelLightType,
    ModelSkeleton,
    ModelTexture,
    ModelTextureFormat,
    ModelTextureKind,
)
from ..wtd import Rsc5Texture, Rsc5TextureFormat
from .geometry import WdrDrawableLod, WdrDrawableModel, WdrGeometry
from .material import WdrShaderGroup
from .math import WdrMatrix4, WdrVector3, WdrVector4


@dataclass(frozen=True, slots=True)
class WdrBoneId:
    bone_id: int
    bone_index: int


class WdrBoneFlags(IntFlag):
    NONE = 0
    ROTATION_ONLY = 0x000001
    ROTATE_X = 0x000002
    ROTATE_Y = 0x000004
    ROTATE_Z = 0x000008
    ROTATE_X_LIMITED = 0x000010
    ROTATE_Y_LIMITED = 0x000020
    ROTATE_Z_LIMITED = 0x000040
    TRANSLATE_X = 0x000080
    TRANSLATE_Y = 0x000100
    TRANSLATE_Z = 0x000200
    TRANSLATE_X_LIMITED = 0x000400
    TRANSLATE_Y_LIMITED = 0x000800
    TRANSLATE_Z_LIMITED = 0x001000
    SCALE_X = 0x002000
    SCALE_Y = 0x004000
    SCALE_Z = 0x008000
    SCALE_X_LIMITED = 0x010000
    SCALE_Y_LIMITED = 0x020000
    SCALE_Z_LIMITED = 0x040000
    INVISIBLE = 0x080000


@dataclass(slots=True)
class WdrBone:
    name: str
    index: int
    bone_id: int
    mirror_index: int
    flags: WdrBoneFlags
    parent_index: int | None
    first_child_index: int | None
    next_sibling_index: int | None
    original_position: WdrVector4
    original_rotation_euler: WdrVector4
    original_rotation: WdrVector4
    original_scale: WdrVector4
    absolute_position: WdrVector4
    absolute_rotation_euler: WdrVector4
    scale_orientation: WdrVector4
    translation_minimum: WdrVector4
    translation_maximum: WdrVector4
    rotation_minimum: WdrVector4
    rotation_maximum: WdrVector4
    reserved_vector: WdrVector4
    reserved_short: int
    reserved_value: int
    cumulative_inverse_joint_scale_orientation: WdrMatrix4
    cumulative_joint_scale_orientation: WdrMatrix4
    default_transform: WdrMatrix4
    _pointer: int = field(repr=False, compare=False)
    local_transform: WdrMatrix4 = field(default_factory=WdrMatrix4.identity)
    absolute_transform: WdrMatrix4 = field(default_factory=WdrMatrix4.identity)
    inverse_bind_transform: WdrMatrix4 = field(default_factory=WdrMatrix4.identity)
    skin_transform: WdrMatrix4 = field(default_factory=WdrMatrix4.identity)

    @property
    def position(self) -> WdrVector4:
        return self.original_position

    @property
    def rotation(self) -> WdrVector4:
        return self.original_rotation

    @property
    def scale(self) -> WdrVector4:
        return self.original_scale


@dataclass(slots=True)
class WdrSkeleton:
    bones: tuple[WdrBone, ...]
    bone_ids: tuple[WdrBoneId, ...]
    parent_indices: tuple[int, ...]
    cumulative_inverse_joint_scale_orientations: tuple[WdrMatrix4, ...]
    cumulative_joint_scale_orientations: tuple[WdrMatrix4, ...]
    default_transforms: tuple[WdrMatrix4, ...]
    translation_dof_count: int
    rotation_dof_count: int
    scale_dof_count: int
    flags: int
    reference_count: int
    signature: int
    reserved: tuple[int, int, int, int]
    _pointer: int = field(repr=False, compare=False)

    def to_model_skeleton(self) -> ModelSkeleton:
        """Project the hierarchy and bind transforms without changing coordinates."""

        return ModelSkeleton(
            bones=tuple(
                ModelBone(
                    index=bone.index,
                    name=bone.name,
                    id=bone.bone_id,
                    parent_index=bone.parent_index,
                    mirror_index=bone.mirror_index,
                    flags=int(bone.flags),
                    local_transform=bone.local_transform.values,
                    world_transform=bone.absolute_transform.values,
                    inverse_bind_transform=bone.inverse_bind_transform.values,
                )
                for bone in self.bones
            ),
            signature=self.signature,
        )


class WdrLightType(IntEnum):
    POINT = 1
    SPOT = 2


class WdrLightFlags(IntFlag):
    """GTA IV drawable-light behavior flags used by GIMS IV."""

    RANDOM_FLASHING_1 = 1 << 0
    RANDOM_FLASHING_2 = 1 << 1
    HAZARD_FLASHING_1 = 1 << 2
    SLOW_HAZARD_FLASHING = 1 << 3
    VERY_SLOW_HAZARD_FLASHING = 1 << 4
    ALL_DAY = 1 << 5
    NIGHT_ONLY = 1 << 6
    WEAK_LIGHT = 1 << 7
    VERY_FAST_HAZARD_FLASHING = 1 << 8
    FAST_HAZARD_FLASHING = 1 << 9
    VERY_SLOW_FADE_1 = 1 << 10
    VERY_SLOW_FADE_2 = 1 << 11
    SLOW_FADE = 1 << 12
    HAZARD_FLASHING_2 = 1 << 13
    TINY_FLICKERING = 1 << 14
    DYNAMIC_SHADOW = 1 << 15
    WEATHER_MODIFIED_COLOR = 1 << 16
    UNKNOWN_18 = 1 << 17
    UNKNOWN_19 = 1 << 18
    SHOW_RAYS = 1 << 19
    NO_CORONA_REFLECTION = 1 << 20
    UNKNOWN_22 = 1 << 21
    UNKNOWN_23 = 1 << 22
    UNKNOWN_24 = 1 << 23
    UNKNOWN_25 = 1 << 24
    UNKNOWN_26 = 1 << 25
    UNKNOWN_27 = 1 << 26
    UNKNOWN_28 = 1 << 27
    UNKNOWN_29 = 1 << 28
    UNKNOWN_30 = 1 << 29
    UNKNOWN_31 = 1 << 30
    UNKNOWN_32 = 1 << 31


class WdrLightTypeFlags(IntFlag):
    FIVE_SECONDS_ON_THREE_SECONDS_FLICKER_1 = 1 << 0
    FIVE_SECONDS_ON_THREE_SECONDS_FLICKER_2 = 1 << 1
    ONE_SECOND_ON_OFF = 1 << 2
    OFF = 1 << 3


@dataclass(frozen=True, slots=True)
class WdrLight:
    position: WdrVector3
    direction: WdrVector3
    tangent: WdrVector3
    color: tuple[int, int, int, int]
    lod_distance: float
    volume_intensity: float
    volume_size: float
    attenuation_end: float
    intensity: float
    corona_size: float
    hotspot_angle: float
    falloff_angle: float
    flags: WdrLightFlags
    corona_hash: int
    luminosity_hash: int
    flashiness: WdrLightTypeFlags
    light_type: WdrLightType | int
    corona_hdr_multiplier: float
    fade_distance: float
    shadow_fade_distance: float
    bone_id: int
    reserved_1: int
    reserved_2: int

    def to_model_light(self) -> ModelLight:
        """Return a normalized light while retaining RAGE-specific identifiers."""

        if self.light_type == WdrLightType.POINT:
            light_type = ModelLightType.POINT
        elif self.light_type == WdrLightType.SPOT:
            light_type = ModelLightType.SPOT
        else:
            light_type = ModelLightType.OTHER
        return ModelLight(
            light_type=light_type,
            position=(self.position.x, self.position.y, self.position.z),
            direction=(self.direction.x, self.direction.y, self.direction.z),
            tangent=(self.tangent.x, self.tangent.y, self.tangent.z),
            color=(
                self.color[0] / 255.0,
                self.color[1] / 255.0,
                self.color[2] / 255.0,
                self.color[3] / 255.0,
            ),
            intensity=self.intensity,
            range=self.attenuation_end,
            inner_cone_angle=self.hotspot_angle,
            outer_cone_angle=self.falloff_angle,
            bone_id=self.bone_id,
            flags=int(self.flags),
            lod_distance=self.lod_distance,
            fade_distance=self.fade_distance,
            shadow_fade_distance=self.shadow_fade_distance,
            volume_intensity=self.volume_intensity,
            volume_size=self.volume_size,
            corona_size=self.corona_size,
            corona_hdr_multiplier=self.corona_hdr_multiplier,
            corona_hash=self.corona_hash,
            luminosity_hash=self.luminosity_hash,
            flashiness=int(self.flashiness),
            source_type=int(self.light_type),
        )


_MODEL_TEXTURE_FORMATS: dict[Rsc5TextureFormat | int, ModelTextureFormat] = {
    Rsc5TextureFormat.DXT1: ModelTextureFormat.BC1,
    Rsc5TextureFormat.DXT3: ModelTextureFormat.BC2,
    Rsc5TextureFormat.DXT5: ModelTextureFormat.BC3,
    Rsc5TextureFormat.A8R8G8B8: ModelTextureFormat.BGRA8,
    Rsc5TextureFormat.L8: ModelTextureFormat.R8,
}


def _texture_to_model(texture: Rsc5Texture) -> ModelTexture:
    try:
        texture_format = _MODEL_TEXTURE_FORMATS[texture.format]
    except KeyError as error:
        raise ValueError(
            f"unsupported neutral texture format: {int(texture.format):#x}"
        ) from error
    return ModelTexture(
        name=texture.name,
        file_name=texture.file_name,
        width=texture.width,
        height=texture.height,
        format=texture_format,
        kind=(
            ModelTextureKind.CUBE if texture.is_cube else ModelTextureKind.TEXTURE_2D
        ),
        mip_count=texture.mip_levels,
        data=texture.data,
        mip_sizes=texture.mip_sizes,
        source_format=int(texture.format),
    )


@dataclass(slots=True)
class WdrDrawable:
    bounding_center: WdrVector4
    bounding_box_minimum: WdrVector4
    bounding_box_maximum: WdrVector4
    bounding_sphere_radius: float
    lods: tuple[WdrDrawableLod | None, ...]
    draw_bucket_masks: tuple[int, int, int, int]
    shader_group: WdrShaderGroup | None
    skeleton: WdrSkeleton | None
    lights: tuple[WdrLight, ...]
    reserved: tuple[int, ...]

    @property
    def models(self) -> tuple[WdrDrawableModel, ...]:
        return tuple(model for lod in self.lods if lod is not None for model in lod.models)

    @property
    def geometries(self) -> tuple[WdrGeometry, ...]:
        return tuple(geometry for model in self.models for geometry in model.geometries)


__all__ = [
    "WdrBoneId",
    "WdrBoneFlags",
    "WdrBone",
    "WdrSkeleton",
    "WdrLightType",
    "WdrLightFlags",
    "WdrLightTypeFlags",
    "WdrLight",
    "WdrDrawable",
]
