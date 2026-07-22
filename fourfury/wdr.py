from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass, field
from enum import IntEnum
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
    flags: int
    stride: int
    element_count: int
    declaration_types: int
    elements: tuple[WdrVertexElement, ...]
    _pointer: int = field(repr=False, compare=False)


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


@dataclass(slots=True)
class WdrVertexBuffer:
    vertex_count: int
    stride: int
    layout: WdrVertexLayout
    data: bytes
    secondary_data: bytes
    vertices: tuple[WdrVertex, ...]
    _pointer: int = field(repr=False, compare=False)


@dataclass(slots=True)
class WdrIndexBuffer:
    indices: tuple[int, ...]
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
    version: int
    draw_bucket: int
    usage_count: int
    shader_index: int
    parameters: tuple[WdrShaderParameter, ...]
    _pointer: int = field(repr=False, compare=False)


@dataclass(slots=True)
class WdrShaderGroup:
    shaders: tuple[WdrShader, ...]
    texture_dictionary_pointer: int
    vertex_declaration_usage_flags: tuple[int, ...]
    texture_dictionary: Rsc5TextureDictionary | None = field(repr=False, compare=False)
    _pointer: int = field(repr=False, compare=False)


@dataclass(slots=True)
class WdrGeometry:
    vertex_buffer: WdrVertexBuffer | None
    index_buffer: WdrIndexBuffer | None
    index_count: int
    face_count: int
    vertex_count: int
    primitive_type: int
    vertex_stride: int
    shader_index: int = 0
    bounding_sphere: WdrVector4 | None = None
    shader: WdrShader | None = field(default=None, repr=False, compare=False)
    _pointer: int = field(default=0, repr=False, compare=False)

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


@dataclass(slots=True)
class WdrDrawableModel:
    geometries: tuple[WdrGeometry, ...]
    geometry_bounds: tuple[WdrVector4 | None, ...]
    shader_mappings: tuple[int, ...]
    skeleton_binding: int
    render_mask: int
    flags: int
    _pointer: int = field(repr=False, compare=False)

    @property
    def bone_index(self) -> int:
        return (self.skeleton_binding >> 24) & 0xFF

    @property
    def has_skin(self) -> bool:
        return bool((self.skeleton_binding >> 8) & 0xFF)


@dataclass(slots=True)
class WdrDrawableLod:
    level: WdrLodLevel
    distance: float
    models: tuple[WdrDrawableModel, ...]
    _pointer: int = field(repr=False, compare=False)

    @property
    def geometries(self) -> tuple[WdrGeometry, ...]:
        return tuple(geometry for model in self.models for geometry in model.geometries)


@dataclass(frozen=True, slots=True)
class WdrBoneId:
    bone_id: int
    bone_index: int


@dataclass(slots=True)
class WdrBone:
    name: str
    index: int
    bone_id: int
    mirror_index: int
    flags: int
    parent_index: int | None
    first_child_index: int | None
    next_sibling_index: int | None
    position: WdrVector4
    rotation: WdrVector4
    scale: WdrVector4
    absolute_position: WdrVector4
    _pointer: int = field(repr=False, compare=False)


@dataclass(slots=True)
class WdrSkeleton:
    bones: tuple[WdrBone, ...]
    bone_ids: tuple[WdrBoneId, ...]
    flags: int
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
        flags, stride, _storage, element_count, declaration_types = self.unpack(
            pointer, "<IHBBQ", "WDR vertex layout"
        )
        elements: list[WdrVertexElement] = []
        offset = 0
        for semantic_value in range(16):
            if not flags & (1 << semantic_value):
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
        if len(elements) != element_count:
            raise ValueError(
                f"WDR vertex layout declares {element_count} elements but flags describe {len(elements)}"
            )
        if offset > stride:
            raise ValueError(f"WDR vertex elements exceed their {stride}-byte stride")
        layout = WdrVertexLayout(flags, stride, element_count, declaration_types, tuple(elements), pointer)
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
        data_pointer = struct.unpack_from("<I", raw, 8)[0]
        stride = struct.unpack_from("<I", raw, 12)[0]
        layout_pointer = struct.unpack_from("<I", raw, 16)[0]
        secondary_pointer = struct.unpack_from("<I", raw, 24)[0]
        layout = self.parse_layout(layout_pointer)
        if layout.stride != stride:
            raise ValueError(
                f"WDR vertex buffer stride {stride} does not match layout stride {layout.stride}"
            )
        data_size = vertex_count * stride
        data = b"" if data_pointer == 0 else self.read(data_pointer, data_size, "WDR vertex data")
        if secondary_pointer == data_pointer:
            secondary_data = data
        else:
            secondary_data = (
                b"" if secondary_pointer == 0
                else self.read(secondary_pointer, data_size, "WDR secondary vertex data")
            )
        primary = data or secondary_data
        vertices = tuple(
            self.decode_vertex(primary, index * stride, layout)
            for index in range(vertex_count)
        ) if primary else ()
        buffer = WdrVertexBuffer(
            vertex_count, stride, layout, data, secondary_data, vertices, pointer
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
        buffer = WdrIndexBuffer(indices, pointer)  # type: ignore[arg-type]
        self.index_buffers[pointer] = buffer
        return buffer

    def parse_geometry(self, pointer: int) -> WdrGeometry:
        if pointer in self.geometries:
            return self.geometries[pointer]
        raw = self.read(pointer, WDR_GEOMETRY_SIZE, "WDR geometry")
        vertex_buffer_pointer = struct.unpack_from("<I", raw, 12)[0]
        index_buffer_pointer = struct.unpack_from("<I", raw, 28)[0]
        index_count, face_count = struct.unpack_from("<II", raw, 44)
        vertex_count, primitive_type = struct.unpack_from("<HH", raw, 52)
        vertex_stride = struct.unpack_from("<H", raw, 60)[0]
        vertex_buffer = (
            None if vertex_buffer_pointer == 0 else self.parse_vertex_buffer(vertex_buffer_pointer)
        )
        index_buffer = (
            None if index_buffer_pointer == 0 else self.parse_index_buffer(index_buffer_pointer)
        )
        if vertex_buffer is not None and vertex_buffer.vertex_count != vertex_count:
            raise ValueError("WDR geometry vertex count does not match its vertex buffer")
        if vertex_buffer is not None and vertex_buffer.stride != vertex_stride:
            raise ValueError("WDR geometry vertex stride does not match its vertex buffer")
        if index_buffer is not None and len(index_buffer.indices) < index_count:
            raise ValueError("WDR geometry index count exceeds its index buffer")
        geometry = WdrGeometry(
            vertex_buffer,
            index_buffer,
            index_count,
            face_count,
            vertex_count,
            primitive_type,
            vertex_stride,
            _pointer=pointer,
        )
        self.geometries[pointer] = geometry
        return geometry

    def parse_model(self, pointer: int) -> WdrDrawableModel:
        if pointer in self.models:
            return self.models[pointer]
        raw = self.read(pointer, WDR_MODEL_SIZE, "WDR drawable model")
        geometry_pointers = self.pointer_array(pointer + 4, "WDR model geometry pointers")
        bounds_pointer, shader_mapping_pointer, skeleton_binding = struct.unpack_from("<3I", raw, 12)
        render_mask_flags, geometry_count = struct.unpack_from("<HH", raw, 24)
        if len(geometry_pointers) != geometry_count:
            raise ValueError("WDR model geometry count does not match its pointer array")
        geometries = tuple(self.parse_geometry(item) for item in geometry_pointers)
        bounds = () if geometry_count == 0 else (
            tuple(None for _ in range(geometry_count)) if bounds_pointer == 0 else tuple(
                self.vector4(bounds_pointer + index * 16, "WDR geometry bound")
                for index in range(geometry_count)
            )
        )
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
            bounds,
            tuple(int(value) for value in shader_mappings),
            skeleton_binding,
            render_mask_flags & 0xFF,
            (render_mask_flags >> 8) & 0xFF,
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
        self.read(pointer, WDR_LOD_SIZE, "WDR drawable LOD")
        model_pointers = self.pointer_array(pointer, "WDR LOD model pointers")
        lod = WdrDrawableLod(
            level, distance, tuple(self.parse_model(item) for item in model_pointers), pointer
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
        version, draw_bucket, usage_count = struct.unpack_from("<3B", raw, 8)
        shader_index = struct.unpack_from("<H", raw, 14)[0]
        parameter_data_pointer = struct.unpack_from("<I", raw, 20)[0]
        parameter_count = struct.unpack_from("<I", raw, 28)[0]
        parameter_types_pointer = struct.unpack_from("<I", raw, 36)[0]
        name_hash = struct.unpack_from("<I", raw, 40)[0]
        parameter_names_pointer = struct.unpack_from("<I", raw, 52)[0]
        name_pointer, file_name_pointer = struct.unpack_from("<2I", raw, 68)
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
            version,
            draw_bucket,
            usage_count,
            shader_index,
            tuple(parameters),
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
        return WdrShaderGroup(
            tuple(self.parse_shader(item) for item in shader_pointers),
            texture_dictionary_pointer,
            tuple(int(value) for value in usage_values),
            (
                read_rsc5_texture_dictionary(self.resource, texture_dictionary_pointer)
                if texture_dictionary_pointer else None
            ),
            pointer,
        )

    def parse_skeleton(self, pointer: int) -> WdrSkeleton:
        raw = self.read(pointer, 64, "WDR skeleton")
        bones_pointer = struct.unpack_from("<I", raw, 0)[0]
        bone_count = struct.unpack_from("<H", raw, 20)[0]
        flags = struct.unpack_from("<I", raw, 28)[0]
        bone_ids_pointer, bone_id_count, bone_id_capacity = self.unpack(
            pointer + 32, "<IHH", "WDR bone ID map header"
        )
        if bone_id_capacity < bone_id_count:
            raise ValueError("WDR bone ID map count exceeds its capacity")
        bone_ids = tuple(
            WdrBoneId(*self.unpack(
                bone_ids_pointer + index * 4, "<hh", "WDR bone ID map entry"
            ))
            for index in range(bone_id_count)
        ) if bone_id_count else ()
        pointer_to_index = {
            bones_pointer + index * 224: index for index in range(bone_count)
        }
        bones: list[WdrBone] = []
        for index in range(bone_count):
            bone_pointer = bones_pointer + index * 224
            bone_raw = self.read(bone_pointer, 224, "WDR bone")
            name_pointer = struct.unpack_from("<I", bone_raw, 0)[0]
            bone_flags = struct.unpack_from("<H", bone_raw, 6)[0]
            sibling_pointer, child_pointer, parent_pointer = struct.unpack_from("<3I", bone_raw, 8)
            stored_index, bone_id, mirror_index = struct.unpack_from("<3H", bone_raw, 20)
            bones.append(
                WdrBone(
                    self.string(name_pointer),
                    stored_index,
                    bone_id,
                    mirror_index,
                    bone_flags,
                    pointer_to_index.get(parent_pointer),
                    pointer_to_index.get(child_pointer),
                    pointer_to_index.get(sibling_pointer),
                    self.vector4(bone_pointer + 32, "WDR bone position"),
                    self.vector4(bone_pointer + 64, "WDR bone rotation"),
                    self.vector4(bone_pointer + 80, "WDR bone scale"),
                    self.vector4(bone_pointer + 96, "WDR bone absolute position"),
                    bone_pointer,
                )
            )
        return WdrSkeleton(tuple(bones), bone_ids, flags, pointer)

    def parse_light(self, pointer: int) -> WdrLight:
        raw = self.read(pointer, WDR_LIGHT_SIZE, "WDR light")
        position = WdrVector3(*struct.unpack_from("<3f", raw, 4))
        direction = WdrVector3(*struct.unpack_from("<3f", raw, 16))
        tangent = WdrVector3(*struct.unpack_from("<3f", raw, 28))
        color = struct.unpack_from("<4B", raw, 40)
        values = struct.unpack_from("<8f", raw, 44)
        flags, corona_hash, luminosity_hash = struct.unpack_from("<3I", raw, 76)
        flashiness = raw[88]
        light_type_value = raw[91]
        try:
            light_type: WdrLightType | int = WdrLightType(light_type_value)
        except ValueError:
            light_type = light_type_value
        corona_hdr_multiplier, fade_distance, shadow_fade_distance = struct.unpack_from(
            "<3f", raw, 92
        )
        bone_id = struct.unpack_from("<H", raw, 104)[0]
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
    "WdrBoneId", "WdrDocument", "WdrDrawable", "WdrDrawableLod", "WdrDrawableModel",
    "WdrGeometry", "WdrIndexBuffer", "WdrLight", "WdrLightType", "WdrLodLevel",
    "WdrPrimitiveType", "WdrShader", "WdrShaderGroup", "WdrShaderParameter", "WdrSkeleton",
    "WdrTextureReference", "WdrVector2", "WdrVector3", "WdrVector4", "WdrVertex",
    "WdrVertexBuffer", "WdrVertexElement", "WdrVertexElementType", "WdrVertexLayout",
    "WdrVertexSemantic", "load_wdr",
]
