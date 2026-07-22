from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from pathlib import Path
from typing import BinaryIO, Iterator

from .rsc import (
    RSC5_PHYSICAL_BASE,
    RSC5_VIRTUAL_BASE,
    Rsc5Resource,
)
from .wtd import Rsc5Texture, Rsc5TextureDictionary, read_rsc5_texture_dictionary


WDR_RESOURCE_VERSION = 0x6E
WDR_DRAWABLE_SIZE = 0x90
WDR_LOD_SIZE = 0x10
WDR_MODEL_SIZE = 0x20
WDR_GEOMETRY_SIZE = 0x50
WDR_VERTEX_BUFFER_SIZE = 0x20
WDR_INDEX_BUFFER_SIZE = 0x30
WDR_VERTEX_LAYOUT_SIZE = 0x10
WDR_SHADER_SIZE = 0x60
WDR_LIGHT_SIZE = 0x6C


WDR_SHADER_PARAMETER_NAMES: dict[int, str] = {
    0x2B5170FD: "texture_sampler",
    0x46B7C64F: "bump_sampler",
    0x608799C6: "spec_sampler",
    0xC5BBAE28: "environment_sampler",
    0x7E9A27FE: "dirt_sampler",
    0x05645204: "texture_sampler_2",
    0xD52B11DF: "texture_sampler_layer_0",
    0x2420AFD1: "texture_sampler_layer_1",
    0x31934AB6: "texture_sampler_layer_2",
    0x78B758FD: "texture_sampler_layer_3",
    0xF6712B81: "bumpiness",
    0xFF11711D: "spec_map_intensity_mask",
    0x166E0FD1: "specular_factor",
    0x484A5EBD: "specular_color_factor",
    0x3BC8669F: "reflective_power",
    0x5EEBED48: "emissive_multiplier",
    0x3E95FA90: "dirt_decal_mask",
    0x84153DD7: "luminance_constants",
    0x948A54F2: "material_color_scale",
    0x185F047C: "material_diffuse_color",
    0x5E0E088C: "material_diffuse_color_2",
    0x1EAef6F0: "draw_bucket",
    0x6063CE32: "order_number",
    0x84F7D5D9: "bound_radius",
    0x02D01730: "dirt_level",
    0x44546346: "dirt_color",
    0x81DB4C55: "parallax_scale_bias",
    0x5A7625DF: "diffuse_color",
    0x001D37B7: "world_instance_inverse_transpose",
    0x00E67F02: "imposter_direction",
    0x0C451B1A: "fade_thickness",
    0x104E0B0E: "z_shift_scale",
    0x1105818B: "alternate_remap",
    0x1948C16C: "material_diffuse",
    0x1C8B0AFF: "normal_table",
    0x1D6CE221: "bone_damage_0",
    0x1E7C18F3: "subsurface_scattering_wrap",
    0x257DF714: "specular_2_factor",
    0x288FD3FA: "reflective_power_enabled",
    0x28E1926B: "specular_2_color",
    0x3A7D3D1D: "world_instance_matrix",
    0x3B397BBC: "subsurface_scattering_width",
    0x4A8804FE: "specular_color_factor_enabled",
    0x4E96F308: "tyre_deformation_enabled",
    0x5ACBE867: "dimmer_set",
    0x5DC44EB2: "tyre_deformation_parameters",
    0x6A99768C: "diffuse_2_specular_modifier",
    0x7717EDC1: "specular_2_color_intensity",
    0x94D7098F: "specular_factor_enabled",
    0xA38C0E4A: "z_shift",
    0xA78EAAA7: "damage_vertex_buffer",
    0xA8A03862: "wheel_transform",
    0xBA54C190: "global_animation_uv_1",
    0xBBCF983D: "switch_on",
    0xC5CD0E78: "subsurface_color",
    0xCC26609B: "specular_2_factor_enabled",
    0xCD5F0A56: "bone_damage_enabled",
    0xD5588AFC: "damage_sampler",
    0xD79BFC1E: "global_animation_uv_0",
    0xDBB6BF5B: "ambient_decal_mask",
    0xE3BA8919: "damage_specular_texture_sampler",
    0xF07391A4: "facet_mask",
    0xF38696B0: "tyre_deformation_parameters_2",
    0xF6543DD6: "damage_texture_sampler",
    0xF8B1F013: "specular_2_color_intensity_reflection",
    0xFC2BC0AA: "shadow_map_resolution",
}


@dataclass(frozen=True, slots=True)
class WdrVector2:
    x: float
    y: float

    def __iter__(self) -> Iterator[float]:
        return iter((self.x, self.y))


@dataclass(frozen=True, slots=True)
class WdrVector3:
    x: float
    y: float
    z: float

    def __iter__(self) -> Iterator[float]:
        return iter((self.x, self.y, self.z))


@dataclass(frozen=True, slots=True)
class WdrVector4:
    x: float
    y: float
    z: float
    w: float

    def __iter__(self) -> Iterator[float]:
        return iter((self.x, self.y, self.z, self.w))


@dataclass(frozen=True, slots=True)
class WdrMatrix4:
    """A row-major 4x4 matrix using the same convention as RAGE/System.Numerics."""

    values: tuple[
        float, float, float, float,
        float, float, float, float,
        float, float, float, float,
        float, float, float, float,
    ]

    @classmethod
    def identity(cls) -> "WdrMatrix4":
        return cls((
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ))

    @classmethod
    def transformation(
        cls,
        scale: WdrVector3,
        rotation: WdrVector4,
        translation: WdrVector3,
    ) -> "WdrMatrix4":
        x, y, z, w = rotation
        sx, sy, sz = scale
        return cls((
            sx * (1.0 - 2.0 * (y * y + z * z)),
            sx * (2.0 * (x * y + z * w)),
            sx * (2.0 * (x * z - y * w)),
            0.0,
            sy * (2.0 * (x * y - z * w)),
            sy * (1.0 - 2.0 * (z * z + x * x)),
            sy * (2.0 * (y * z + x * w)),
            0.0,
            sz * (2.0 * (x * z + y * w)),
            sz * (2.0 * (y * z - x * w)),
            sz * (1.0 - 2.0 * (y * y + x * x)),
            0.0,
            translation.x, translation.y, translation.z, 1.0,
        ))

    @property
    def rows(self) -> tuple[tuple[float, float, float, float], ...]:
        return tuple(
            self.values[index:index + 4] for index in range(0, 16, 4)
        )

    @property
    def translation(self) -> WdrVector3:
        return WdrVector3(*self.values[12:15])

    def __iter__(self) -> Iterator[float]:
        return iter(self.values)

    def __matmul__(self, other: "WdrMatrix4") -> "WdrMatrix4":
        left = self.values
        right = other.values
        return WdrMatrix4(tuple(
            sum(left[row * 4 + item] * right[item * 4 + column] for item in range(4))
            for row in range(4)
            for column in range(4)
        ))  # type: ignore[arg-type]

    def inverse(self) -> "WdrMatrix4":
        augmented = [
            list(self.values[row * 4:(row + 1) * 4])
            + [1.0 if row == column else 0.0 for column in range(4)]
            for row in range(4)
        ]
        for column in range(4):
            pivot = max(range(column, 4), key=lambda row: abs(augmented[row][column]))
            if abs(augmented[pivot][column]) < 1e-12:
                raise ValueError("WDR matrix is singular")
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
            divisor = augmented[column][column]
            augmented[column] = [value / divisor for value in augmented[column]]
            for row in range(4):
                if row == column:
                    continue
                factor = augmented[row][column]
                augmented[row] = [
                    value - factor * pivot_value
                    for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
                ]
        return WdrMatrix4(tuple(
            augmented[row][column] for row in range(4) for column in range(4, 8)
        ))  # type: ignore[arg-type]


class WdrLodLevel(IntEnum):
    HIGH = 0
    MEDIUM = 1
    LOW = 2
    VERY_LOW = 3


class WdrPrimitiveType(IntEnum):
    TRIANGLE_LIST = 3


class WdrVertexElementType(IntEnum):
    NOTHING = 0
    HALF2 = 1
    FLOAT = 2
    HALF4 = 3
    FLOAT_SINGLE = 4
    FLOAT2 = 5
    FLOAT3 = 6
    FLOAT4 = 7
    UBYTE4 = 8
    COLOR = 9
    DEC3N = 10


class WdrVertexSemantic(IntEnum):
    POSITION = 0
    BLEND_WEIGHTS = 1
    BLEND_INDICES = 2
    NORMAL = 3
    COLOR_0 = 4
    COLOR_1 = 5
    TEXCOORD_0 = 6
    TEXCOORD_1 = 7
    TEXCOORD_2 = 8
    TEXCOORD_3 = 9
    TEXCOORD_4 = 10
    TEXCOORD_5 = 11
    TEXCOORD_6 = 12
    TEXCOORD_7 = 13
    TANGENT = 14
    BINORMAL = 15


_ELEMENT_SIZES = {
    WdrVertexElementType.HALF2: 4,
    WdrVertexElementType.FLOAT: 4,
    WdrVertexElementType.HALF4: 8,
    WdrVertexElementType.FLOAT_SINGLE: 4,
    WdrVertexElementType.FLOAT2: 8,
    WdrVertexElementType.FLOAT3: 12,
    WdrVertexElementType.FLOAT4: 16,
    WdrVertexElementType.UBYTE4: 4,
    WdrVertexElementType.COLOR: 4,
    WdrVertexElementType.DEC3N: 4,
}


@dataclass(frozen=True, slots=True)
class WdrVertexElement:
    semantic: WdrVertexSemantic
    element_type: WdrVertexElementType
    offset: int

    @property
    def size(self) -> int:
        return _ELEMENT_SIZES[self.element_type]


@dataclass(frozen=True, slots=True)
class WdrVertexLayout:
    fvf: int
    fvf_size: int
    flags: int
    dynamic_order: int
    channel_count: int
    declaration_types: int
    elements: tuple[WdrVertexElement, ...]
    _pointer: int = field(repr=False, compare=False)

    @property
    def stride(self) -> int:
        """Compatibility alias for :attr:`fvf_size`."""
        return self.fvf_size

    @property
    def element_count(self) -> int:
        """Compatibility alias for :attr:`channel_count`."""
        return self.channel_count


VertexValue = float | int | tuple[float | int, ...]


@dataclass(frozen=True, slots=True)
class WdrVertex:
    attributes: dict[WdrVertexSemantic, VertexValue]

    def get(self, semantic: WdrVertexSemantic) -> VertexValue | None:
        return self.attributes.get(semantic)

    @property
    def position(self) -> WdrVector3 | None:
        value = self.attributes.get(WdrVertexSemantic.POSITION)
        return None if value is None else WdrVector3(*value)  # type: ignore[arg-type]

    @property
    def normal(self) -> WdrVector3 | None:
        value = self.attributes.get(WdrVertexSemantic.NORMAL)
        return None if value is None else WdrVector3(*value[:3])  # type: ignore[index,arg-type]

    @property
    def texcoords(self) -> tuple[WdrVector2, ...]:
        result: list[WdrVector2] = []
        for semantic in range(WdrVertexSemantic.TEXCOORD_0, WdrVertexSemantic.TEXCOORD_7 + 1):
            value = self.attributes.get(WdrVertexSemantic(semantic))
            if value is not None:
                result.append(WdrVector2(*value[:2]))  # type: ignore[index,arg-type]
        return tuple(result)

    @property
    def colors(self) -> tuple[tuple[int, int, int, int], ...]:
        result: list[tuple[int, int, int, int]] = []
        for semantic in (WdrVertexSemantic.COLOR_0, WdrVertexSemantic.COLOR_1):
            value = self.attributes.get(semantic)
            if value is not None:
                result.append(tuple(value))  # type: ignore[arg-type]
        return tuple(result)

    @property
    def blend_weights(self) -> VertexValue | None:
        return self.attributes.get(WdrVertexSemantic.BLEND_WEIGHTS)

    @property
    def blend_indices(self) -> VertexValue | None:
        return self.attributes.get(WdrVertexSemantic.BLEND_INDICES)

    @property
    def tangent(self) -> VertexValue | None:
        return self.attributes.get(WdrVertexSemantic.TANGENT)

    @property
    def binormal(self) -> VertexValue | None:
        return self.attributes.get(WdrVertexSemantic.BINORMAL)


@dataclass(slots=True)
class WdrVertexBuffer:
    vertex_count: int
    locked: int
    flags: int
    stride: int
    layout: WdrVertexLayout
    locked_data: bytes
    lock_thread_id: int
    vertex_data: bytes
    d3d_vertex_buffer: int
    vertices: tuple[WdrVertex, ...]
    _pointer: int = field(repr=False, compare=False)

    @property
    def data(self) -> bytes:
        """Compatibility alias for the locked vertex data."""
        return self.locked_data

    @property
    def secondary_data(self) -> bytes:
        """Compatibility alias for the regular vertex data."""
        return self.vertex_data


@dataclass(slots=True)
class WdrIndexBuffer:
    indices: tuple[int, ...]
    reserved: tuple[int, int, int, int, int, int, int, int, int]
    _pointer: int = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class WdrTextureReference:
    file_name: str
    name: str
    _pointer: int = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class WdrShaderParameter:
    name_hash: int
    parameter_type: int
    texture: WdrTextureReference | None = None
    value: WdrVector4 | tuple[WdrVector4, ...] | None = None

    @property
    def name(self) -> str:
        return WDR_SHADER_PARAMETER_NAMES.get(self.name_hash, f"hash_{self.name_hash:08x}")

    @property
    def is_texture(self) -> bool:
        return self.parameter_type == 0


@dataclass(slots=True)
class WdrShader:
    name: str
    file_name: str
    name_hash: int
    block_map_address: int
    version: int
    draw_bucket: int
    usage_count: int
    shader_index: int
    parameters: tuple[WdrShaderParameter, ...]
    reserved: tuple[int, ...]
    _pointer: int = field(repr=False, compare=False)


@dataclass(slots=True)
class WdrShaderGroup:
    shaders: tuple[WdrShader, ...]
    texture_dictionary_pointer: int
    vertex_declaration_usage_flags: tuple[int, ...]
    reserved: tuple[int, int, int, int, int, int, int, int, int, int, int, int]
    reserved_data: tuple[int, ...]
    texture_dictionary: Rsc5TextureDictionary | None = field(repr=False, compare=False)
    _pointer: int = field(repr=False, compare=False)


@dataclass(slots=True)
class WdrGeometry:
    vertex_buffers: tuple[
        WdrVertexBuffer | None,
        WdrVertexBuffer | None,
        WdrVertexBuffer | None,
        WdrVertexBuffer | None,
    ]
    index_buffers: tuple[
        WdrIndexBuffer | None,
        WdrIndexBuffer | None,
        WdrIndexBuffer | None,
        WdrIndexBuffer | None,
    ]
    index_count: int
    face_count: int
    vertex_count: int
    primitive_type: int
    bone_ids: tuple[int, ...]
    vertex_stride: int
    reserved_header: tuple[int, int]
    reserved_tail: tuple[int, int, int, int]
    shader_index: int = 0
    bounding_sphere: WdrVector4 | None = None
    shader: WdrShader | None = field(default=None, repr=False, compare=False)
    _pointer: int = field(default=0, repr=False, compare=False)

    @property
    def vertex_buffer(self) -> WdrVertexBuffer | None:
        return self.vertex_buffers[0]

    @property
    def index_buffer(self) -> WdrIndexBuffer | None:
        return self.index_buffers[0]

    @property
    def vertices(self) -> tuple[WdrVertex, ...]:
        return () if self.vertex_buffer is None else self.vertex_buffer.vertices

    @property
    def indices(self) -> tuple[int, ...]:
        return () if self.index_buffer is None else self.index_buffer.indices

    @property
    def triangles(self) -> tuple[tuple[int, int, int], ...]:
        if self.primitive_type != WdrPrimitiveType.TRIANGLE_LIST:
            raise ValueError(f"unsupported WDR primitive type: {self.primitive_type}")
        count = min(self.index_count, len(self.indices))
        return tuple(
            (self.indices[index], self.indices[index + 1], self.indices[index + 2])
            for index in range(0, count - 2, 3)
        )

    def resolve_bone_indices(self, vertex: WdrVertex) -> tuple[int, ...]:
        """Resolve a vertex's local blend indices through this geometry's matrix palette."""
        value = vertex.blend_indices
        if value is None:
            return ()
        local_indices = (value,) if isinstance(value, int) else value
        return tuple(
            self.bone_ids[index] if self.bone_ids and index < len(self.bone_ids) else index
            for index in (int(item) for item in local_indices)
        )


@dataclass(slots=True)
class WdrDrawableModel:
    geometries: tuple[WdrGeometry, ...]
    bounding_sphere: WdrVector4 | None
    geometry_bounds: tuple[WdrVector4 | None, ...]
    shader_mappings: tuple[int, ...]
    matrix_count: int
    flags: int
    model_type: int
    matrix_index: int
    stride: int
    skin_flag: int
    reserved: int
    _pointer: int = field(repr=False, compare=False)

    @property
    def bone_index(self) -> int:
        """Compatibility alias for rigid models bound to one matrix."""
        return self.matrix_index

    @property
    def has_skin(self) -> bool:
        return self.skin_flag == 1

    @property
    def skeleton_binding(self) -> int:
        """Return the legacy packed representation of the four matrix metadata bytes."""
        return (
            self.matrix_count
            | (self.flags << 8)
            | (self.model_type << 16)
            | (self.matrix_index << 24)
        )


@dataclass(slots=True)
class WdrDrawableLod:
    level: WdrLodLevel
    distance: float
    models: tuple[WdrDrawableModel, ...]
    reserved: tuple[int, int]
    _pointer: int = field(repr=False, compare=False)

    @property
    def geometries(self) -> tuple[WdrGeometry, ...]:
        return tuple(geometry for model in self.models for geometry in model.geometries)


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


class WdrLightType(IntEnum):
    POINT = 1
    SPOT = 2


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
    flags: int
    corona_hash: int
    luminosity_hash: int
    flashiness: int
    light_type: WdrLightType | int
    corona_hdr_multiplier: float
    fade_distance: float
    shadow_fade_distance: float
    bone_id: int
    reserved_1: int
    reserved_2: int


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
    reserved: tuple[int, int, int, int, int]

    @property
    def models(self) -> tuple[WdrDrawableModel, ...]:
        return tuple(model for lod in self.lods if lod is not None for model in lod.models)

    @property
    def geometries(self) -> tuple[WdrGeometry, ...]:
        return tuple(geometry for model in self.models for geometry in model.geometries)


class _WdrReader:
    def __init__(self, resource: Rsc5Resource) -> None:
        self.resource = resource
        self.layouts: dict[int, WdrVertexLayout] = {}
        self.vertex_buffers: dict[int, WdrVertexBuffer] = {}
        self.index_buffers: dict[int, WdrIndexBuffer] = {}
        self.geometries: dict[int, WdrGeometry] = {}
        self.models: dict[int, WdrDrawableModel] = {}
        self.lods: dict[int, WdrDrawableLod] = {}
        self.shaders: dict[int, WdrShader] = {}
        self.textures: dict[int, WdrTextureReference] = {}

    def _allocation(self, pointer: int) -> tuple[bytes, int, str]:
        base = pointer & 0xF0000000
        offset = pointer & 0x0FFFFFFF
        if base == RSC5_VIRTUAL_BASE:
            return self.resource.virtual_data, offset, "virtual"
        if base == RSC5_PHYSICAL_BASE:
            return self.resource.physical_data, offset, "physical"
        raise ValueError(f"invalid RSC5 pointer: {pointer:#x}")

    def read(self, pointer: int, size: int, label: str) -> bytes:
        if pointer == 0:
            raise ValueError(f"null pointer for {label}")
        data, offset, allocation = self._allocation(pointer)
        if size < 0 or offset + size > len(data):
            raise ValueError(f"{label} exceeds the RSC5 {allocation} allocation")
        return data[offset : offset + size]

    def unpack(self, pointer: int, format_string: str, label: str) -> tuple[object, ...]:
        size = struct.calcsize(format_string)
        return struct.unpack(format_string, self.read(pointer, size, label))

    def string(self, pointer: int) -> str:
        if pointer == 0:
            return ""
        data, offset, allocation = self._allocation(pointer)
        end = data.find(b"\0", offset)
        if end < 0:
            raise ValueError(f"unterminated WDR string in the {allocation} allocation")
        return data[offset:end].decode("utf-8", errors="replace")

    def vector3(self, pointer: int, label: str) -> WdrVector3:
        return WdrVector3(*self.unpack(pointer, "<3f", label))  # type: ignore[arg-type]

    def vector4(self, pointer: int, label: str) -> WdrVector4:
        return WdrVector4(*self.unpack(pointer, "<4f", label))  # type: ignore[arg-type]

    def matrix4(self, pointer: int, label: str) -> WdrMatrix4:
        return WdrMatrix4(self.unpack(pointer, "<16f", label))  # type: ignore[arg-type]

    def pointer_array(self, header_pointer: int, label: str) -> tuple[int, ...]:
        array_pointer, count, capacity = self.unpack(header_pointer, "<IHH", f"{label} header")
        if capacity < count:
            raise ValueError(f"{label} count exceeds its capacity")
        if count == 0:
            return ()
        return self.unpack(array_pointer, f"<{count}I", label)  # type: ignore[arg-type]

    def plain_array(
        self,
        header_pointer: int,
        format_code: str,
        item_size: int,
        label: str,
    ) -> tuple[object, ...]:
        array_pointer, count, capacity = self.unpack(header_pointer, "<IHH", f"{label} header")
        if capacity < count:
            raise ValueError(f"{label} count exceeds its capacity")
        if count == 0:
            return ()
        if struct.calcsize(f"<{format_code}") != item_size:
            raise ValueError(f"invalid item size for {label}")
        return self.unpack(array_pointer, f"<{count}{format_code}", label)

    def parse_layout(self, pointer: int) -> WdrVertexLayout:
        if pointer in self.layouts:
            return self.layouts[pointer]
        fvf, fvf_size, flags, dynamic_order, channel_count, declaration_types = self.unpack(
            pointer, "<IBBBBQ", "WDR vertex layout"
        )
        elements: list[WdrVertexElement] = []
        offset = 0
        for semantic_value in range(16):
            if not fvf & (1 << semantic_value):
                continue
            type_value = (declaration_types >> (semantic_value * 4)) & 0xF
            try:
                element_type = WdrVertexElementType(type_value)
                size = _ELEMENT_SIZES[element_type]
            except (ValueError, KeyError) as exc:
                raise ValueError(
                    f"unsupported WDR vertex element type {type_value} for semantic {semantic_value}"
                ) from exc
            elements.append(
                WdrVertexElement(WdrVertexSemantic(semantic_value), element_type, offset)
            )
            offset += size
        if len(elements) != channel_count:
            raise ValueError(
                f"WDR vertex layout declares {channel_count} channels but its FVF describes {len(elements)}"
            )
        if offset > fvf_size:
            raise ValueError(f"WDR vertex elements exceed their {fvf_size}-byte FVF size")
        layout = WdrVertexLayout(
            int(fvf),
            int(fvf_size),
            int(flags),
            int(dynamic_order),
            int(channel_count),
            int(declaration_types),
            tuple(elements),
            pointer,
        )
        self.layouts[pointer] = layout
        return layout

    @staticmethod
    def _decode_dec3n(value: int) -> tuple[float, float, float, float]:
        result: list[float] = []
        for shift in (0, 10, 20):
            component = (value >> shift) & 0x3FF
            signed = component if component < 0x200 else component - 0x400
            result.append(max(-1.0, signed / 511.0))
        w_bits = (value >> 30) & 0x3
        result.append(-1.0 if w_bits == 3 else float(w_bits))
        return tuple(result)  # type: ignore[return-value]

    def decode_vertex(self, data: bytes, base: int, layout: WdrVertexLayout) -> WdrVertex:
        attributes: dict[WdrVertexSemantic, VertexValue] = {}
        for element in layout.elements:
            offset = base + element.offset
            element_type = element.element_type
            if element_type == WdrVertexElementType.HALF2:
                value: VertexValue = struct.unpack_from("<2e", data, offset)
            elif element_type == WdrVertexElementType.HALF4:
                value = struct.unpack_from("<4e", data, offset)
            elif element_type in (WdrVertexElementType.FLOAT, WdrVertexElementType.FLOAT_SINGLE):
                value = struct.unpack_from("<f", data, offset)[0]
            elif element_type == WdrVertexElementType.FLOAT2:
                value = struct.unpack_from("<2f", data, offset)
            elif element_type == WdrVertexElementType.FLOAT3:
                value = struct.unpack_from("<3f", data, offset)
            elif element_type == WdrVertexElementType.FLOAT4:
                value = struct.unpack_from("<4f", data, offset)
            elif element_type in (WdrVertexElementType.UBYTE4, WdrVertexElementType.COLOR):
                value = struct.unpack_from("<4B", data, offset)
            elif element_type == WdrVertexElementType.DEC3N:
                value = self._decode_dec3n(struct.unpack_from("<I", data, offset)[0])
            else:  # pragma: no cover - parse_layout rejects these first
                raise ValueError(f"unsupported WDR vertex element type: {element_type}")
            attributes[element.semantic] = value
        return WdrVertex(attributes)

    def parse_vertex_buffer(self, pointer: int) -> WdrVertexBuffer:
        if pointer in self.vertex_buffers:
            return self.vertex_buffers[pointer]
        raw = self.read(pointer, WDR_VERTEX_BUFFER_SIZE, "WDR vertex buffer")
        vertex_count = struct.unpack_from("<H", raw, 4)[0]
        locked, flags = struct.unpack_from("<2B", raw, 6)
        locked_data_pointer = struct.unpack_from("<I", raw, 8)[0]
        stride = struct.unpack_from("<I", raw, 12)[0]
        layout_pointer = struct.unpack_from("<I", raw, 16)[0]
        lock_thread_id = struct.unpack_from("<I", raw, 20)[0]
        vertex_data_pointer = struct.unpack_from("<I", raw, 24)[0]
        d3d_vertex_buffer = struct.unpack_from("<I", raw, 28)[0]
        layout = self.parse_layout(layout_pointer)
        if layout.stride != stride:
            raise ValueError(
                f"WDR vertex buffer stride {stride} does not match layout stride {layout.stride}"
            )
        data_size = vertex_count * stride
        locked_data = (
            b"" if locked_data_pointer == 0
            else self.read(locked_data_pointer, data_size, "WDR locked vertex data")
        )
        if vertex_data_pointer == locked_data_pointer:
            vertex_data = locked_data
        else:
            vertex_data = (
                b"" if vertex_data_pointer == 0
                else self.read(vertex_data_pointer, data_size, "WDR vertex data")
            )
        primary = locked_data or vertex_data
        vertices = tuple(
            self.decode_vertex(primary, index * stride, layout)
            for index in range(vertex_count)
        ) if primary else ()
        buffer = WdrVertexBuffer(
            vertex_count,
            locked,
            flags,
            stride,
            layout,
            locked_data,
            lock_thread_id,
            vertex_data,
            d3d_vertex_buffer,
            vertices,
            pointer,
        )
        self.vertex_buffers[pointer] = buffer
        return buffer

    def parse_index_buffer(self, pointer: int) -> WdrIndexBuffer:
        if pointer in self.index_buffers:
            return self.index_buffers[pointer]
        raw = self.read(pointer, WDR_INDEX_BUFFER_SIZE, "WDR index buffer")
        count, data_pointer = struct.unpack_from("<II", raw, 4)
        indices = () if count == 0 else self.unpack(
            data_pointer, f"<{count}H", "WDR index data"
        )
        reserved = struct.unpack_from("<9I", raw, 12)
        buffer = WdrIndexBuffer(indices, reserved, pointer)  # type: ignore[arg-type]
        self.index_buffers[pointer] = buffer
        return buffer

    def parse_geometry(self, pointer: int) -> WdrGeometry:
        if pointer in self.geometries:
            return self.geometries[pointer]
        raw = self.read(pointer, WDR_GEOMETRY_SIZE, "WDR geometry")
        reserved_header = struct.unpack_from("<2I", raw, 4)
        vertex_buffer_pointers = struct.unpack_from("<4I", raw, 12)
        index_buffer_pointers = struct.unpack_from("<4I", raw, 28)
        index_count, face_count = struct.unpack_from("<II", raw, 44)
        vertex_count, primitive_type = struct.unpack_from("<HH", raw, 52)
        bone_ids_pointer, vertex_stride, bone_ids_count = struct.unpack_from("<IHH", raw, 56)
        reserved_tail = struct.unpack_from("<4I", raw, 64)
        vertex_buffers = tuple(
            None if item == 0 else self.parse_vertex_buffer(item)
            for item in vertex_buffer_pointers
        )
        index_buffers = tuple(
            None if item == 0 else self.parse_index_buffer(item)
            for item in index_buffer_pointers
        )
        vertex_buffer = vertex_buffers[0]
        index_buffer = index_buffers[0]
        if vertex_count == 0 and vertex_buffer is not None:
            vertex_count = vertex_buffer.vertex_count
        if vertex_buffer is not None and vertex_buffer.vertex_count != vertex_count:
            raise ValueError("WDR geometry vertex count does not match its vertex buffer")
        if vertex_buffer is not None and vertex_buffer.stride != vertex_stride:
            raise ValueError("WDR geometry vertex stride does not match its vertex buffer")
        if index_buffer is not None and len(index_buffer.indices) < index_count:
            raise ValueError("WDR geometry index count exceeds its index buffer")
        bone_ids = () if bone_ids_count == 0 else self.unpack(
            bone_ids_pointer, f"<{bone_ids_count}H", "WDR geometry bone palette"
        )
        geometry = WdrGeometry(
            vertex_buffers,  # type: ignore[arg-type]
            index_buffers,  # type: ignore[arg-type]
            index_count,
            face_count,
            vertex_count,
            primitive_type,
            tuple(int(value) for value in bone_ids),
            vertex_stride,
            reserved_header,
            reserved_tail,
            _pointer=pointer,
        )
        self.geometries[pointer] = geometry
        return geometry

    def parse_model(self, pointer: int) -> WdrDrawableModel:
        if pointer in self.models:
            return self.models[pointer]
        raw = self.read(pointer, WDR_MODEL_SIZE, "WDR drawable model")
        geometry_pointers = self.pointer_array(pointer + 4, "WDR model geometry pointers")
        bounds_pointer, shader_mapping_pointer = struct.unpack_from("<2I", raw, 12)
        matrix_count, flags, model_type, matrix_index, stride, skin_flag = struct.unpack_from(
            "<6B", raw, 20
        )
        geometry_count = struct.unpack_from("<H", raw, 26)[0]
        reserved = struct.unpack_from("<I", raw, 28)[0]
        if len(geometry_pointers) != geometry_count:
            raise ValueError("WDR model geometry count does not match its pointer array")
        geometries = tuple(self.parse_geometry(item) for item in geometry_pointers)
        raw_bound_count = geometry_count + 1 if geometry_count > 1 else geometry_count
        raw_bounds = () if raw_bound_count == 0 or bounds_pointer == 0 else tuple(
            self.vector4(bounds_pointer + index * 16, "WDR model geometry bound")
            for index in range(raw_bound_count)
        )
        if not raw_bounds:
            bounding_sphere = None
            bounds = tuple(None for _ in range(geometry_count))
        elif geometry_count > 1:
            bounding_sphere = raw_bounds[0]
            bounds = raw_bounds[1:]
        else:
            bounding_sphere = raw_bounds[0]
            bounds = raw_bounds
        shader_mappings = () if geometry_count == 0 else (
            tuple(0 for _ in range(geometry_count)) if shader_mapping_pointer == 0 else self.unpack(
                shader_mapping_pointer, f"<{geometry_count}H", "WDR shader mappings"
            )
        )
        for index, geometry in enumerate(geometries):
            geometry.shader_index = int(shader_mappings[index])
            geometry.bounding_sphere = bounds[index]
        model = WdrDrawableModel(
            geometries,
            bounding_sphere,
            bounds,
            tuple(int(value) for value in shader_mappings),
            matrix_count,
            flags,
            model_type,
            matrix_index,
            stride,
            skin_flag,
            reserved,
            pointer,
        )
        self.models[pointer] = model
        return model

    def parse_lod(self, pointer: int, level: WdrLodLevel, distance: float) -> WdrDrawableLod:
        if pointer in self.lods:
            lod = self.lods[pointer]
            lod.level = level
            lod.distance = distance
            return lod
        raw = self.read(pointer, WDR_LOD_SIZE, "WDR drawable LOD")
        model_pointers = self.pointer_array(pointer, "WDR LOD model pointers")
        reserved = struct.unpack_from("<2I", raw, 8)
        lod = WdrDrawableLod(
            level,
            distance,
            tuple(self.parse_model(item) for item in model_pointers),
            reserved,
            pointer,
        )
        self.lods[pointer] = lod
        return lod

    def parse_texture_reference(self, pointer: int) -> WdrTextureReference:
        if pointer in self.textures:
            return self.textures[pointer]
        raw = self.read(pointer, 28, "WDR texture reference")
        file_name_pointer = struct.unpack_from("<I", raw, 20)[0]
        file_name = self.string(file_name_pointer)
        name = file_name.removeprefix("pack:/").removesuffix(".dds")
        texture = WdrTextureReference(file_name, name, pointer)
        self.textures[pointer] = texture
        return texture

    def parse_shader(self, pointer: int) -> WdrShader:
        if pointer in self.shaders:
            return self.shaders[pointer]
        raw = self.read(pointer, WDR_SHADER_SIZE, "WDR shader")
        block_map_address = struct.unpack_from("<I", raw, 4)[0]
        version, draw_bucket, usage_count = struct.unpack_from("<3B", raw, 8)
        shader_index = struct.unpack_from("<H", raw, 14)[0]
        parameter_data_pointer = struct.unpack_from("<I", raw, 20)[0]
        parameter_count = struct.unpack_from("<I", raw, 28)[0]
        parameter_types_pointer = struct.unpack_from("<I", raw, 36)[0]
        name_hash = struct.unpack_from("<I", raw, 40)[0]
        parameter_names_pointer = struct.unpack_from("<I", raw, 52)[0]
        name_pointer, file_name_pointer = struct.unpack_from("<2I", raw, 68)
        reserved = (
            raw[11],
            struct.unpack_from("<H", raw, 12)[0],
            struct.unpack_from("<I", raw, 16)[0],
            struct.unpack_from("<I", raw, 24)[0],
            struct.unpack_from("<I", raw, 32)[0],
            struct.unpack_from("<I", raw, 44)[0],
            struct.unpack_from("<I", raw, 48)[0],
            struct.unpack_from("<I", raw, 56)[0],
            struct.unpack_from("<I", raw, 60)[0],
            struct.unpack_from("<I", raw, 64)[0],
            *struct.unpack_from("<5I", raw, 76),
        )
        parameter_pointers = () if parameter_count == 0 else self.unpack(
            parameter_data_pointer, f"<{parameter_count}I", "WDR shader parameter pointers"
        )
        parameter_types = () if parameter_count == 0 else self.unpack(
            parameter_types_pointer, f"<{parameter_count}B", "WDR shader parameter types"
        )
        parameter_hashes = () if parameter_count == 0 else self.unpack(
            parameter_names_pointer, f"<{parameter_count}I", "WDR shader parameter hashes"
        )
        parameters: list[WdrShaderParameter] = []
        for index in range(parameter_count):
            parameter_pointer = int(parameter_pointers[index])
            parameter_type = int(parameter_types[index])
            parameter_hash = int(parameter_hashes[index])
            if parameter_type == 0:
                texture = (
                    None if parameter_pointer == 0
                    else self.parse_texture_reference(parameter_pointer)
                )
                parameters.append(WdrShaderParameter(parameter_hash, parameter_type, texture=texture))
            elif parameter_type == 1:
                value = self.vector4(parameter_pointer, "WDR shader vector parameter")
                parameters.append(WdrShaderParameter(parameter_hash, parameter_type, value=value))
            else:
                values = tuple(
                    self.vector4(
                        parameter_pointer + item * 16,
                        "WDR shader vector array parameter",
                    )
                    for item in range(parameter_type)
                )
                parameters.append(WdrShaderParameter(parameter_hash, parameter_type, value=values))
        shader = WdrShader(
            self.string(name_pointer),
            self.string(file_name_pointer),
            name_hash,
            block_map_address,
            version,
            draw_bucket,
            usage_count,
            shader_index,
            tuple(parameters),
            reserved,
            pointer,
        )
        self.shaders[pointer] = shader
        return shader

    def parse_shader_group(self, pointer: int) -> WdrShaderGroup:
        raw = self.read(pointer, 80, "WDR shader group")
        texture_dictionary_pointer = struct.unpack_from("<I", raw, 4)[0]
        shader_pointers = self.pointer_array(pointer + 8, "WDR shader pointers")
        usage_values = self.plain_array(
            pointer + 64, "I", 4, "WDR vertex declaration usage flags"
        )
        reserved = struct.unpack_from("<12I", raw, 16)
        reserved_data = self.plain_array(pointer + 72, "I", 4, "WDR shader group reserved data")
        return WdrShaderGroup(
            tuple(self.parse_shader(item) for item in shader_pointers),
            texture_dictionary_pointer,
            tuple(int(value) for value in usage_values),
            reserved,
            tuple(int(value) for value in reserved_data),
            (
                read_rsc5_texture_dictionary(self.resource, texture_dictionary_pointer)
                if texture_dictionary_pointer else None
            ),
            pointer,
        )

    def parse_skeleton(self, pointer: int) -> WdrSkeleton:
        raw = self.read(pointer, 64, "WDR skeleton")
        (
            bones_pointer,
            parent_indices_pointer,
            cumulative_inverse_pointer,
            cumulative_pointer,
            default_transforms_pointer,
        ) = struct.unpack_from("<5I", raw, 0)
        (
            bone_count,
            translation_dof_count,
            rotation_dof_count,
            scale_dof_count,
        ) = struct.unpack_from("<4H", raw, 20)
        flags = struct.unpack_from("<I", raw, 28)[0]
        bone_ids_pointer, bone_id_count, bone_id_capacity = self.unpack(
            pointer + 32, "<IHH", "WDR bone ID map header"
        )
        if bone_id_capacity < bone_id_count:
            raise ValueError("WDR bone ID map count exceeds its capacity")
        bone_ids = tuple(
            WdrBoneId(*self.unpack(
                bone_ids_pointer + index * 4, "<HH", "WDR bone ID map entry"
            ))
            for index in range(bone_id_count)
        ) if bone_id_count else ()
        reference_count, signature, *reserved = struct.unpack_from("<6I", raw, 40)
        parent_indices = (
            tuple(-1 for _ in range(bone_count))
            if parent_indices_pointer == 0 else tuple(int(value) for value in self.unpack(
                parent_indices_pointer, f"<{bone_count}i", "WDR skeleton parent indices"
            ))
        )

        def read_matrices(array_pointer: int, label: str) -> tuple[WdrMatrix4, ...]:
            if array_pointer == 0:
                return tuple(WdrMatrix4.identity() for _ in range(bone_count))
            return tuple(
                self.matrix4(array_pointer + index * 64, label)
                for index in range(bone_count)
            )

        cumulative_inverse = read_matrices(
            cumulative_inverse_pointer, "WDR cumulative inverse joint scale orientation"
        )
        cumulative = read_matrices(
            cumulative_pointer, "WDR cumulative joint scale orientation"
        )
        default_transforms = read_matrices(
            default_transforms_pointer, "WDR default bone transform"
        )
        pointer_to_index = {
            bones_pointer + index * 224: index for index in range(bone_count)
        }
        bones: list[WdrBone] = []
        for index in range(bone_count):
            bone_pointer = bones_pointer + index * 224
            bone_raw = self.read(bone_pointer, 224, "WDR bone")
            name_pointer = struct.unpack_from("<I", bone_raw, 0)[0]
            bone_flags = struct.unpack_from("<I", bone_raw, 4)[0]
            sibling_pointer, child_pointer, parent_pointer = struct.unpack_from("<3I", bone_raw, 8)
            stored_index, bone_id, mirror_index, reserved_short = struct.unpack_from(
                "<4H", bone_raw, 20
            )
            reserved_value = struct.unpack_from("<I", bone_raw, 28)[0]
            parent_index = parent_indices[index]
            if bone_id == 0 or not 0 <= parent_index < bone_count:
                parent_index = None
            bones.append(
                WdrBone(
                    self.string(name_pointer),
                    stored_index,
                    bone_id,
                    mirror_index,
                    WdrBoneFlags(bone_flags),
                    parent_index,
                    pointer_to_index.get(child_pointer),
                    pointer_to_index.get(sibling_pointer),
                    self.vector4(bone_pointer + 32, "WDR bone original position"),
                    self.vector4(bone_pointer + 48, "WDR bone original Euler rotation"),
                    self.vector4(bone_pointer + 64, "WDR bone original rotation"),
                    self.vector4(bone_pointer + 80, "WDR bone original scale"),
                    self.vector4(bone_pointer + 96, "WDR bone absolute position"),
                    self.vector4(bone_pointer + 112, "WDR bone absolute Euler rotation"),
                    self.vector4(bone_pointer + 128, "WDR bone scale orientation"),
                    self.vector4(bone_pointer + 144, "WDR bone minimum translation"),
                    self.vector4(bone_pointer + 160, "WDR bone maximum translation"),
                    self.vector4(bone_pointer + 176, "WDR bone minimum rotation"),
                    self.vector4(bone_pointer + 192, "WDR bone maximum rotation"),
                    self.vector4(bone_pointer + 208, "WDR bone reserved vector"),
                    reserved_short,
                    reserved_value,
                    cumulative_inverse[index],
                    cumulative[index],
                    default_transforms[index],
                    bone_pointer,
                )
            )

        completed: set[int] = set()
        active: set[int] = set()

        def update_transform(index: int) -> WdrMatrix4:
            bone = bones[index]
            if index in completed:
                return bone.absolute_transform
            if index in active:
                raise ValueError("cyclic WDR skeleton parent hierarchy")
            active.add(index)
            bone.local_transform = WdrMatrix4.transformation(
                WdrVector3(1.0, 1.0, 1.0),
                bone.original_rotation,
                WdrVector3(*tuple(bone.original_position)[:3]),
            )
            bone.absolute_transform = (
                bone.local_transform
                if bone.parent_index is None
                else bone.local_transform @ update_transform(bone.parent_index)
            )
            bone.inverse_bind_transform = bone.absolute_transform.inverse()
            bone.skin_transform = bone.inverse_bind_transform @ bone.absolute_transform
            active.remove(index)
            completed.add(index)
            return bone.absolute_transform

        for index in range(bone_count):
            update_transform(index)

        return WdrSkeleton(
            tuple(bones),
            bone_ids,
            parent_indices,
            cumulative_inverse,
            cumulative,
            default_transforms,
            translation_dof_count,
            rotation_dof_count,
            scale_dof_count,
            flags,
            reference_count,
            signature,
            tuple(reserved),  # type: ignore[arg-type]
            pointer,
        )

    def parse_light(self, pointer: int) -> WdrLight:
        raw = self.read(pointer, WDR_LIGHT_SIZE, "WDR light")
        position = WdrVector3(*struct.unpack_from("<3f", raw, 4))
        direction = WdrVector3(*struct.unpack_from("<3f", raw, 16))
        tangent = WdrVector3(*struct.unpack_from("<3f", raw, 28))
        color = struct.unpack_from("<4B", raw, 40)
        values = struct.unpack_from("<8f", raw, 44)
        flags, corona_hash, luminosity_hash = struct.unpack_from("<3I", raw, 76)
        flashiness = raw[88]
        reserved_1 = struct.unpack_from("<H", raw, 89)[0]
        light_type_value = raw[91]
        try:
            light_type: WdrLightType | int = WdrLightType(light_type_value)
        except ValueError:
            light_type = light_type_value
        corona_hdr_multiplier, fade_distance, shadow_fade_distance = struct.unpack_from(
            "<3f", raw, 92
        )
        bone_id = struct.unpack_from("<H", raw, 104)[0]
        reserved_2 = struct.unpack_from("<H", raw, 106)[0]
        return WdrLight(
            position,
            direction,
            tangent,
            color,
            *values,
            flags,
            corona_hash,
            luminosity_hash,
            flashiness,
            light_type,
            corona_hdr_multiplier,
            fade_distance,
            shadow_fade_distance,
            bone_id,
            reserved_1,
            reserved_2,
        )

    def parse_drawable(self) -> WdrDrawable:
        pointer = RSC5_VIRTUAL_BASE
        raw = self.read(pointer, WDR_DRAWABLE_SIZE, "WDR drawable")
        shader_group_pointer, skeleton_pointer = struct.unpack_from("<2I", raw, 8)
        bounding_center = WdrVector4(*struct.unpack_from("<4f", raw, 16))
        bounding_box_minimum = WdrVector4(*struct.unpack_from("<4f", raw, 32))
        bounding_box_maximum = WdrVector4(*struct.unpack_from("<4f", raw, 48))
        lod_pointers = struct.unpack_from("<4I", raw, 64)
        lod_distances = struct.unpack_from("<4f", raw, 80)
        draw_bucket_masks = struct.unpack_from("<4i", raw, 96)
        bounding_sphere_radius = struct.unpack_from("<f", raw, 112)[0]
        shader_group = (
            None if shader_group_pointer == 0 else self.parse_shader_group(shader_group_pointer)
        )
        skeleton = None if skeleton_pointer == 0 else self.parse_skeleton(skeleton_pointer)
        lods: list[WdrDrawableLod | None] = []
        for level in WdrLodLevel:
            lod_pointer = lod_pointers[level]
            lods.append(
                None if lod_pointer == 0
                else self.parse_lod(lod_pointer, level, lod_distances[level])
            )
        if shader_group is not None:
            for lod in lods:
                if lod is None:
                    continue
                for geometry in lod.geometries:
                    if geometry.shader_index < len(shader_group.shaders):
                        geometry.shader = shader_group.shaders[geometry.shader_index]
        lights_pointer, light_count, light_capacity = struct.unpack_from("<IHH", raw, 128)
        if light_capacity < light_count:
            raise ValueError("WDR light count exceeds its capacity")
        lights = tuple(
            self.parse_light(lights_pointer + index * WDR_LIGHT_SIZE)
            for index in range(light_count)
        ) if light_count else ()
        reserved = (*struct.unpack_from("<3I", raw, 116), *struct.unpack_from("<2I", raw, 136))
        return WdrDrawable(
            bounding_center,
            bounding_box_minimum,
            bounding_box_maximum,
            bounding_sphere_radius,
            tuple(lods),
            draw_bucket_masks,
            shader_group,
            skeleton,
            lights,
            reserved,
        )


@dataclass(slots=True)
class WdrDocument:
    drawable: WdrDrawable
    resource: Rsc5Resource
    name: str = "drawable.wdr"
    source_path: str = ""

    @classmethod
    def from_path(cls, path: str | Path) -> "WdrDocument":
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name)
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "drawable.wdr") -> "WdrDocument":
        resource = Rsc5Resource.from_bytes(data)
        if resource.version != WDR_RESOURCE_VERSION:
            raise ValueError(f"unsupported WDR resource version: {resource.version:#x}")
        drawable = _WdrReader(resource).parse_drawable()
        return cls(drawable, resource, name)

    @property
    def lods(self) -> tuple[WdrDrawableLod | None, ...]:
        return self.drawable.lods

    @property
    def models(self) -> tuple[WdrDrawableModel, ...]:
        return self.drawable.models

    @property
    def geometries(self) -> tuple[WdrGeometry, ...]:
        return self.drawable.geometries

    @property
    def shaders(self) -> tuple[WdrShader, ...]:
        group = self.drawable.shader_group
        return () if group is None else group.shaders

    @property
    def embedded_texture_dictionary(self) -> Rsc5TextureDictionary | None:
        group = self.drawable.shader_group
        return None if group is None else group.texture_dictionary

    @property
    def embedded_textures(self) -> tuple[Rsc5Texture, ...]:
        dictionary = self.embedded_texture_dictionary
        return () if dictionary is None else dictionary.textures

    def find_embedded_texture(self, name: str) -> Rsc5Texture | None:
        dictionary = self.embedded_texture_dictionary
        return None if dictionary is None else dictionary.get(name)

    def to_bytes(self) -> bytes:
        """Return the original lossless RSC5 resource.

        WDR structures are currently a read-only semantic view. Fixed-size binary
        editing will be added once every drawable extension field is identified.
        """

        return self.resource.to_bytes()

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(self.to_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


def load_wdr(source: str | Path | bytes | BinaryIO) -> WdrDocument:
    if isinstance(source, (str, Path)):
        return WdrDocument.from_path(source)
    if isinstance(source, bytes):
        return WdrDocument.from_bytes(source)
    return WdrDocument.from_bytes(source.read())


__all__ = [
    "WDR_DRAWABLE_SIZE", "WDR_GEOMETRY_SIZE", "WDR_INDEX_BUFFER_SIZE", "WDR_LIGHT_SIZE",
    "WDR_LOD_SIZE", "WDR_MODEL_SIZE", "WDR_RESOURCE_VERSION", "WDR_SHADER_PARAMETER_NAMES",
    "WDR_SHADER_SIZE", "WDR_VERTEX_BUFFER_SIZE", "WDR_VERTEX_LAYOUT_SIZE", "WdrBone",
    "WdrBoneFlags", "WdrBoneId", "WdrDocument", "WdrDrawable", "WdrDrawableLod", "WdrDrawableModel",
    "WdrGeometry", "WdrIndexBuffer", "WdrLight", "WdrLightType", "WdrLodLevel",
    "WdrPrimitiveType", "WdrShader", "WdrShaderGroup", "WdrShaderParameter", "WdrSkeleton",
    "WdrMatrix4", "WdrTextureReference", "WdrVector2", "WdrVector3", "WdrVector4", "WdrVertex",
    "WdrVertexBuffer", "WdrVertexElement", "WdrVertexElementType", "WdrVertexLayout",
    "WdrVertexSemantic", "load_wdr",
]
