from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum

from ..model import (
    ModelBoundingSphere,
    ModelColorChannel,
    ModelLod,
    ModelMesh,
    ModelObject,
    ModelPrimitive,
    ModelTexCoordChannel,
)
from .material import WdrShader
from .math import WdrVector2, WdrVector3, WdrVector4


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
VertexChannels = dict[WdrVertexSemantic, tuple[VertexValue, ...]]


class _LazyAttributeChannels(VertexChannels):
    """Dictionary-compatible vertex channels decoded on their first access."""

    def __init__(self, loader: Callable[[], VertexChannels]) -> None:
        super().__init__()
        self._loader: Callable[[], VertexChannels] | None = loader

    @property
    def is_loaded(self) -> bool:
        return self._loader is None

    def _load(self) -> None:
        loader = self._loader
        if loader is None:
            return
        values = loader()
        super().update(values)
        self._loader = None

    def __getitem__(
        self,
        key: WdrVertexSemantic,
    ) -> tuple[VertexValue, ...]:
        self._load()
        return super().__getitem__(key)

    def __setitem__(
        self,
        key: WdrVertexSemantic,
        value: tuple[VertexValue, ...],
    ) -> None:
        self._load()
        super().__setitem__(key, value)

    def __delitem__(self, key: WdrVertexSemantic) -> None:
        self._load()
        super().__delitem__(key)

    def __iter__(self):
        self._load()
        return super().__iter__()

    def __len__(self) -> int:
        self._load()
        return super().__len__()

    def __contains__(self, key: object) -> bool:
        self._load()
        return super().__contains__(key)

    def __repr__(self) -> str:
        if not self.is_loaded:
            return "<lazy WDR vertex channels>"
        return super().__repr__()

    def __eq__(self, other: object) -> bool:
        self._load()
        if isinstance(other, _LazyAttributeChannels):
            other._load()
        return super().__eq__(other)

    def get(self, key: WdrVertexSemantic, default=None):
        self._load()
        return super().get(key, default)

    def items(self):
        self._load()
        return super().items()

    def keys(self):
        self._load()
        return super().keys()

    def values(self):
        self._load()
        return super().values()

    def copy(self) -> VertexChannels:
        self._load()
        return super().copy()

    def clear(self) -> None:
        self._load()
        super().clear()

    def pop(self, key: WdrVertexSemantic, default=None):
        self._load()
        return super().pop(key, default)

    def popitem(self):
        self._load()
        return super().popitem()

    def setdefault(self, key: WdrVertexSemantic, default=()):
        self._load()
        return super().setdefault(key, default)

    def update(self, *args, **kwargs) -> None:
        self._load()
        super().update(*args, **kwargs)


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
    attribute_channels: VertexChannels
    _pointer: int = field(repr=False, compare=False)
    _vertices: tuple[WdrVertex, ...] | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    @property
    def vertices(self) -> tuple[WdrVertex, ...]:
        """Materialize row-oriented vertices only when compatibility callers need them."""

        if self._vertices is None:
            channels = tuple(self.attribute_channels.items())
            self._vertices = tuple(
                WdrVertex({semantic: values[index] for semantic, values in channels})
                for index in range(self.vertex_count)
            )
        return self._vertices

    @property
    def are_attribute_channels_loaded(self) -> bool:
        channels = self.attribute_channels
        return not isinstance(channels, _LazyAttributeChannels) or channels.is_loaded

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


def _attribute_channel(
    vertex_buffer: WdrVertexBuffer | None,
    semantic: WdrVertexSemantic,
) -> tuple[VertexValue, ...]:
    if vertex_buffer is None:
        return ()
    values = vertex_buffer.attribute_channels.get(semantic, ())
    if values and len(values) != vertex_buffer.vertex_count:
        raise ValueError(
            f"WDR vertex semantic {semantic.name} is present only on some vertices"
        )
    return values


def _components(value: VertexValue) -> tuple[float | int, ...]:
    return value if isinstance(value, tuple) else (value,)


def _vector2(value: VertexValue, label: str) -> tuple[float, float]:
    components = _components(value)
    if len(components) < 2:
        raise ValueError(f"{label} requires at least two components")
    return float(components[0]), float(components[1])


def _vector3(value: VertexValue, label: str) -> tuple[float, float, float]:
    components = _components(value)
    if len(components) < 3:
        raise ValueError(f"{label} requires at least three components")
    return float(components[0]), float(components[1]), float(components[2])


def _vector4(
    value: VertexValue,
    label: str,
    *,
    default_w: float = 0.0,
) -> tuple[float, float, float, float]:
    components = _components(value)
    if not components:
        raise ValueError(f"{label} has no components")
    result = [float(component) for component in components[:4]]
    while len(result) < 4:
        result.append(default_w if len(result) == 3 else 0.0)
    return tuple(result)  # type: ignore[return-value]


def _indices4(value: VertexValue) -> tuple[int, int, int, int]:
    result = [int(component) for component in _components(value)[:4]]
    result.extend([0] * (4 - len(result)))
    return tuple(result)  # type: ignore[return-value]


def _weights4(value: VertexValue) -> tuple[float, float, float, float]:
    components = _components(value)[:4]
    divisor = (
        255.0
        if components and all(isinstance(item, int) for item in components)
        else 1.0
    )
    result = [float(component) / divisor for component in components]
    result.extend([0.0] * (4 - len(result)))
    return tuple(result)  # type: ignore[return-value]


def _color4(value: VertexValue) -> tuple[float, float, float, float]:
    components = _components(value)
    if len(components) < 3:
        raise ValueError("WDR vertex color requires at least three components")
    divisor = 255.0 if all(isinstance(item, int) for item in components) else 1.0
    result = [float(component) / divisor for component in components[:4]]
    if len(result) == 3:
        result.append(1.0)
    return tuple(result)  # type: ignore[return-value]


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

    def to_model_mesh(self) -> ModelMesh:
        """Decode this geometry into immutable, renderer-neutral mesh data."""

        if self.primitive_type != WdrPrimitiveType.TRIANGLE_LIST:
            raise ValueError(f"unsupported WDR primitive type: {self.primitive_type}")
        vertex_buffer = self.vertex_buffer
        if self.vertex_count and vertex_buffer is None:
            raise ValueError("WDR geometry has no complete decoded vertex stream")

        positions = tuple(
            _vector3(value, "WDR position")
            for value in _attribute_channel(vertex_buffer, WdrVertexSemantic.POSITION)
        )
        if self.vertex_count and len(positions) != self.vertex_count:
            raise ValueError("WDR geometry has vertices without positions")
        normals = tuple(
            _vector3(value, "WDR normal")
            for value in _attribute_channel(vertex_buffer, WdrVertexSemantic.NORMAL)
        )
        tangents = tuple(
            _vector4(value, "WDR tangent", default_w=1.0)
            for value in _attribute_channel(vertex_buffer, WdrVertexSemantic.TANGENT)
        )
        binormals = tuple(
            _vector3(value, "WDR binormal")
            for value in _attribute_channel(vertex_buffer, WdrVertexSemantic.BINORMAL)
        )
        texcoord_channels: list[ModelTexCoordChannel] = []
        for index in range(8):
            semantic = WdrVertexSemantic(WdrVertexSemantic.TEXCOORD_0 + index)
            values = _attribute_channel(vertex_buffer, semantic)
            if values:
                texcoord_channels.append(
                    ModelTexCoordChannel(
                        index=index,
                        values=tuple(
                            _vector2(value, f"WDR texcoord {index}") for value in values
                        ),
                    )
                )
        color_channels: list[ModelColorChannel] = []
        for index, semantic in enumerate(
            (WdrVertexSemantic.COLOR_0, WdrVertexSemantic.COLOR_1)
        ):
            values = _attribute_channel(vertex_buffer, semantic)
            if values:
                color_channels.append(
                    ModelColorChannel(
                        index=index,
                        values=tuple(_color4(value) for value in values),
                    )
                )
        blend_weights = tuple(
            _weights4(value)
            for value in _attribute_channel(vertex_buffer, WdrVertexSemantic.BLEND_WEIGHTS)
        )
        blend_indices = tuple(
            _indices4(value)
            for value in _attribute_channel(vertex_buffer, WdrVertexSemantic.BLEND_INDICES)
        )
        sphere = (
            None
            if self.bounding_sphere is None
            else ModelBoundingSphere(
                center=(
                    self.bounding_sphere.x,
                    self.bounding_sphere.y,
                    self.bounding_sphere.z,
                ),
                radius=self.bounding_sphere.w,
            )
        )
        return ModelMesh(
            positions=positions,
            indices=tuple(int(value) for value in self.indices[: self.index_count]),
            material_index=self.shader_index,
            primitive=ModelPrimitive.TRIANGLES,
            normals=normals,
            tangents=tangents,
            binormals=binormals,
            texcoord_channels=tuple(texcoord_channels),
            color_channels=tuple(color_channels),
            blend_weights=blend_weights,
            blend_indices=blend_indices,
            bone_palette=self.bone_ids,
            bounding_sphere=sphere,
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

    def to_model_object(
        self,
        *,
        index: int,
        has_skeleton: bool = False,
    ) -> ModelObject:
        sphere = (
            None
            if self.bounding_sphere is None
            else ModelBoundingSphere(
                center=(
                    self.bounding_sphere.x,
                    self.bounding_sphere.y,
                    self.bounding_sphere.z,
                ),
                radius=self.bounding_sphere.w,
            )
        )
        return ModelObject(
            index=int(index),
            meshes=tuple(geometry.to_model_mesh() for geometry in self.geometries),
            bounding_sphere=sphere,
            bone_index=(
                self.matrix_index if has_skeleton and not self.has_skin else None
            ),
            is_skinned=self.has_skin,
            bone_count=self.matrix_count,
            flags=self.flags,
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

    def to_model_lod(
        self,
        *,
        draw_bucket_mask: int = 0,
        has_skeleton: bool = False,
    ) -> ModelLod:
        return ModelLod(
            level=self.level.name.casefold(),
            distance=self.distance,
            objects=tuple(
                model.to_model_object(index=index, has_skeleton=has_skeleton)
                for index, model in enumerate(self.models)
            ),
            draw_bucket_mask=int(draw_bucket_mask),
        )


__all__ = [
    "WdrLodLevel",
    "WdrPrimitiveType",
    "WdrVertexElementType",
    "WdrVertexSemantic",
    "WdrVertexElement",
    "WdrVertexLayout",
    "VertexValue",
    "WdrVertex",
    "WdrVertexBuffer",
    "WdrIndexBuffer",
    "WdrGeometry",
    "WdrDrawableModel",
    "WdrDrawableLod",
]
