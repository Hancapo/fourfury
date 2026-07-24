from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Iterator, TypeAlias

from .animation import SkeletalAnimationClip, SkeletalBoneTarget


ModelVector2: TypeAlias = tuple[float, float]
ModelVector3: TypeAlias = tuple[float, float, float]
ModelVector4: TypeAlias = tuple[float, float, float, float]
ModelColor: TypeAlias = tuple[float, float, float, float]
ModelMatrix4: TypeAlias = tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
]
ModelParameterValue: TypeAlias = (
    float | int | tuple[float, ...] | tuple[tuple[float, ...], ...]
)


class ModelPrimitive(StrEnum):
    TRIANGLES = "triangles"


class ModelParameterKind(StrEnum):
    VALUE = "value"
    TEXTURE = "texture"


class ModelTextureFormat(StrEnum):
    BC1 = "bc1"
    BC2 = "bc2"
    BC3 = "bc3"
    BGRA8 = "bgra8"
    R8 = "r8"


class ModelTextureKind(StrEnum):
    TEXTURE_2D = "2d"
    CUBE = "cube"


class ModelLightType(StrEnum):
    POINT = "point"
    SPOT = "spot"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ModelCoordinateSystem:
    """Coordinate convention attached to a neutral model asset."""

    handedness: str = "right"
    up_axis: str = "+z"
    forward_axis: str = "+y"
    units_per_meter: float = 1.0


@dataclass(frozen=True, slots=True)
class ModelAabb:
    minimum: ModelVector3
    maximum: ModelVector3


@dataclass(frozen=True, slots=True)
class ModelBoundingSphere:
    center: ModelVector3
    radius: float


@dataclass(frozen=True, slots=True)
class ModelTextureReference:
    name: str
    file_name: str = ""


@dataclass(frozen=True, slots=True)
class ModelMaterialParameter:
    name_hash: int
    kind: ModelParameterKind
    name: str | None = None
    value: ModelParameterValue | None = None
    texture: ModelTextureReference | None = None

    @property
    def is_texture(self) -> bool:
        return self.kind is ModelParameterKind.TEXTURE

    @property
    def is_bound(self) -> bool:
        return self.texture is not None if self.is_texture else self.value is not None


@dataclass(frozen=True, slots=True)
class ModelMaterial:
    index: int
    name: str
    shader_name: str
    shader_file: str
    render_bucket: int
    parameters: tuple[ModelMaterialParameter, ...] = ()
    shader_hash: int | None = None

    def get_parameter(self, value: str | int) -> ModelMaterialParameter | None:
        if isinstance(value, str):
            key = value.casefold()
            return next(
                (
                    parameter
                    for parameter in self.parameters
                    if parameter.name and parameter.name.casefold() == key
                ),
                None,
            )
        return next(
            (
                parameter
                for parameter in self.parameters
                if parameter.name_hash == int(value)
            ),
            None,
        )

    @property
    def texture_names(self) -> tuple[str, ...]:
        names: list[str] = []
        seen: set[str] = set()
        for parameter in self.parameters:
            if parameter.texture is None:
                continue
            key = parameter.texture.name.casefold()
            if key not in seen:
                seen.add(key)
                names.append(parameter.texture.name)
        return tuple(names)


@dataclass(frozen=True, slots=True)
class ModelTexture:
    name: str
    file_name: str
    width: int
    height: int
    format: ModelTextureFormat
    kind: ModelTextureKind
    mip_count: int
    data: bytes = field(repr=False)
    mip_sizes: tuple[int, ...] = ()
    source_format: int | str | None = None


@dataclass(frozen=True, slots=True)
class ModelTexCoordChannel:
    index: int
    values: tuple[ModelVector2, ...]


@dataclass(frozen=True, slots=True)
class ModelColorChannel:
    index: int
    values: tuple[ModelColor, ...]


@dataclass(frozen=True, slots=True)
class ModelMesh:
    positions: tuple[ModelVector3, ...]
    indices: tuple[int, ...]
    material_index: int = -1
    primitive: ModelPrimitive = ModelPrimitive.TRIANGLES
    normals: tuple[ModelVector3, ...] = ()
    tangents: tuple[ModelVector4, ...] = ()
    binormals: tuple[ModelVector3, ...] = ()
    texcoord_channels: tuple[ModelTexCoordChannel, ...] = ()
    color_channels: tuple[ModelColorChannel, ...] = ()
    blend_weights: tuple[ModelVector4, ...] = ()
    blend_indices: tuple[tuple[int, int, int, int], ...] = ()
    bone_palette: tuple[int, ...] = ()
    bounding_sphere: ModelBoundingSphere | None = None

    @property
    def vertex_count(self) -> int:
        return len(self.positions)

    @property
    def index_count(self) -> int:
        return len(self.indices)

    @property
    def triangle_count(self) -> int:
        return (
            self.index_count // 3 if self.primitive is ModelPrimitive.TRIANGLES else 0
        )

    @property
    def is_skinned(self) -> bool:
        return bool(self.blend_weights or self.blend_indices or self.bone_palette)

    def get_texcoords(self, index: int) -> tuple[ModelVector2, ...]:
        channel = next(
            (item for item in self.texcoord_channels if item.index == index), None
        )
        return () if channel is None else channel.values

    def get_colors(self, index: int) -> tuple[ModelColor, ...]:
        channel = next(
            (item for item in self.color_channels if item.index == index), None
        )
        return () if channel is None else channel.values


@dataclass(frozen=True, slots=True)
class ModelObject:
    index: int
    meshes: tuple[ModelMesh, ...]
    bounding_sphere: ModelBoundingSphere | None = None
    bone_index: int | None = None
    is_skinned: bool = False
    bone_count: int = 0
    flags: int = 0

    @property
    def material_indices(self) -> tuple[int, ...]:
        return tuple(
            dict.fromkeys(
                mesh.material_index for mesh in self.meshes if mesh.material_index >= 0
            )
        )


@dataclass(frozen=True, slots=True)
class ModelLod:
    level: str
    distance: float
    objects: tuple[ModelObject, ...]
    draw_bucket_mask: int = 0

    @property
    def meshes(self) -> tuple[ModelMesh, ...]:
        return tuple(mesh for item in self.objects for mesh in item.meshes)


@dataclass(frozen=True, slots=True)
class ModelBone:
    index: int
    name: str
    id: int
    parent_index: int | None
    mirror_index: int | None
    flags: int
    local_transform: ModelMatrix4
    world_transform: ModelMatrix4
    inverse_bind_transform: ModelMatrix4


@dataclass(frozen=True, slots=True)
class ModelSkeleton:
    bones: tuple[ModelBone, ...]
    signature: int = 0
    _bones_by_name: dict[str, ModelBone] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _bones_by_id: dict[int, ModelBone] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _bones_by_index: dict[int, ModelBone] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        by_name: dict[str, ModelBone] = {}
        by_id: dict[int, ModelBone] = {}
        by_index: dict[int, ModelBone] = {}
        for bone in self.bones:
            by_name.setdefault(bone.name.casefold(), bone)
            by_id.setdefault(bone.id, bone)
            by_index.setdefault(bone.index, bone)
        object.__setattr__(self, "_bones_by_name", by_name)
        object.__setattr__(self, "_bones_by_id", by_id)
        object.__setattr__(self, "_bones_by_index", by_index)

    def get_bone(self, value: str | int) -> ModelBone | None:
        if isinstance(value, str):
            return self._bones_by_name.get(value.casefold())
        return self._bones_by_id.get(int(value))

    def get_bone_by_index(self, index: int) -> ModelBone | None:
        return self._bones_by_index.get(int(index))

    @property
    def roots(self) -> tuple[ModelBone, ...]:
        return tuple(bone for bone in self.bones if bone.parent_index is None)

    def bind_animation(
        self,
        clip: SkeletalAnimationClip,
        *,
        strict: bool = True,
    ) -> SkeletalAnimationClip:
        """Attach hierarchy and bind-pose metadata to a neutral animation clip."""

        if (
            strict
            and clip.signature
            and self.signature
            and clip.signature != self.signature
        ):
            raise ValueError(
                "skeletal animation signature does not match the model skeleton"
            )

        targets: list[SkeletalBoneTarget] = []
        missing: list[int] = []
        for bone_id in clip.bone_ids:
            bone = self.get_bone(bone_id)
            if bone is None:
                missing.append(bone_id)
                targets.append(SkeletalBoneTarget(bone_id))
                continue
            targets.append(
                SkeletalBoneTarget(
                    bone_id=bone.id,
                    bone_index=bone.index,
                    name=bone.name,
                    parent_index=bone.parent_index,
                    local_transform=bone.local_transform,
                    world_transform=bone.world_transform,
                    inverse_bind_transform=bone.inverse_bind_transform,
                )
            )
        if strict and missing:
            missing_text = ", ".join(str(bone_id) for bone_id in missing)
            raise KeyError(f"model skeleton is missing animated bone IDs: {missing_text}")
        return clip.with_targets(tuple(targets))


@dataclass(frozen=True, slots=True)
class ModelLight:
    light_type: ModelLightType
    position: ModelVector3
    direction: ModelVector3
    tangent: ModelVector3
    color: ModelColor
    intensity: float
    range: float
    inner_cone_angle: float = 0.0
    outer_cone_angle: float = 0.0
    bone_id: int = 0
    flags: int = 0
    lod_distance: float = 0.0
    fade_distance: float = 0.0
    shadow_fade_distance: float = 0.0
    volume_intensity: float = 0.0
    volume_size: float = 0.0
    corona_size: float = 0.0
    corona_hdr_multiplier: float = 0.0
    corona_hash: int = 0
    luminosity_hash: int = 0
    flashiness: int = 0
    source_type: int | str | None = None


@dataclass(frozen=True, slots=True)
class ModelAsset:
    name: str
    lods: tuple[ModelLod, ...]
    materials: tuple[ModelMaterial, ...] = ()
    textures: tuple[ModelTexture, ...] = ()
    skeleton: ModelSkeleton | None = None
    lights: tuple[ModelLight, ...] = ()
    bounding_box: ModelAabb | None = None
    bounding_sphere: ModelBoundingSphere | None = None
    coordinate_system: ModelCoordinateSystem = field(
        default_factory=ModelCoordinateSystem
    )
    source_path: str = ""

    @property
    def objects(self) -> tuple[ModelObject, ...]:
        return tuple(item for lod in self.lods for item in lod.objects)

    @property
    def meshes(self) -> tuple[ModelMesh, ...]:
        return tuple(mesh for lod in self.lods for mesh in lod.meshes)

    def get_lod(self, level: str) -> ModelLod | None:
        key = str(level).strip().casefold().replace("-", "_").replace(" ", "_")
        aliases = {"med": "medium", "vlow": "very_low", "verylow": "very_low"}
        key = aliases.get(key, key)
        return next((lod for lod in self.lods if lod.level.casefold() == key), None)

    def get_material(self, value: str | int) -> ModelMaterial | None:
        if isinstance(value, str):
            key = value.casefold()
            return next(
                (
                    material
                    for material in self.materials
                    if material.name.casefold() == key
                    or material.shader_name.casefold() == key
                ),
                None,
            )
        return next(
            (material for material in self.materials if material.index == int(value)),
            None,
        )

    @property
    def texture_names(self) -> tuple[str, ...]:
        names: list[str] = []
        seen: set[str] = set()
        for material in self.materials:
            for name in material.texture_names:
                key = name.casefold()
                if key not in seen:
                    seen.add(key)
                    names.append(name)
        return tuple(names)

    def iter_meshes(self, lod: str | None = None) -> Iterator[ModelMesh]:
        if lod is None:
            yield from self.meshes
            return
        selected = self.get_lod(lod)
        if selected is not None:
            yield from selected.meshes

    @property
    def stem(self) -> str:
        return Path(self.name).stem


__all__ = [
    "ModelAabb",
    "ModelAsset",
    "ModelBone",
    "ModelBoundingSphere",
    "ModelColor",
    "ModelColorChannel",
    "ModelCoordinateSystem",
    "ModelLight",
    "ModelLightType",
    "ModelLod",
    "ModelMaterial",
    "ModelMaterialParameter",
    "ModelMatrix4",
    "ModelMesh",
    "ModelObject",
    "ModelParameterKind",
    "ModelParameterValue",
    "ModelPrimitive",
    "ModelSkeleton",
    "ModelTexCoordChannel",
    "ModelTexture",
    "ModelTextureFormat",
    "ModelTextureKind",
    "ModelTextureReference",
    "ModelVector2",
    "ModelVector3",
    "ModelVector4",
]
