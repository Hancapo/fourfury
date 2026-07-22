from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator

from ._utils import atomic_write
from .materials import MaterialCatalog, MaterialDefinition
from .rsc import Rsc5Resource, rsc5_pointer_offset

try:
    from . import _native as _native_module
except ImportError:
    _native_module = None


_native_decode_wbn_vertices = (
    None if _native_module is None else getattr(_native_module, "decode_wbn_vertices", None)
)
_native_decode_wbn_polygons = (
    None if _native_module is None else getattr(_native_module, "decode_wbn_polygons", None)
)
_native_decode_wbn_bvh_nodes = (
    None if _native_module is None else getattr(_native_module, "decode_wbn_bvh_nodes", None)
)
_native_decode_wbn_bvh_subtrees = (
    None if _native_module is None else getattr(_native_module, "decode_wbn_bvh_subtrees", None)
)


WBN_RESOURCE_VERSION = 0x20
WBN_BOUND_SIZE = 0x80
WBN_COMPOSITE_SIZE = 0xA0
WBN_GEOMETRY_SIZE = 0xE0
WBN_BVH_GEOMETRY_SIZE = 0xF0


def _same_float(left: float, right: float) -> bool:
    return left == right or (math.isnan(left) and math.isnan(right))


@dataclass(slots=True)
class WbnVector3:
    x: float
    y: float
    z: float
    _raw: bytes | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WbnVector3":
        raw = bytes(data[offset : offset + 12])
        return cls(*struct.unpack("<3f", raw), _raw=raw)

    def to_bytes(self) -> bytes:
        if self._raw is not None:
            original = struct.unpack("<3f", self._raw)
            if all(_same_float(current, previous) for current, previous in zip((self.x, self.y, self.z), original)):
                return self._raw
        return struct.pack("<3f", self.x, self.y, self.z)


@dataclass(slots=True)
class WbnVector4:
    x: float
    y: float
    z: float
    w: float
    _raw: bytes | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WbnVector4":
        raw = bytes(data[offset : offset + 16])
        return cls(*struct.unpack("<4f", raw), _raw=raw)

    @property
    def xyz(self) -> WbnVector3:
        return WbnVector3(self.x, self.y, self.z)

    def to_bytes(self) -> bytes:
        values = (self.x, self.y, self.z, self.w)
        if self._raw is not None:
            original = struct.unpack("<4f", self._raw)
            if all(_same_float(current, previous) for current, previous in zip(values, original)):
                return self._raw
        return struct.pack("<4f", *values)


@dataclass(slots=True)
class WbnAabb:
    minimum: WbnVector4
    maximum: WbnVector4

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WbnAabb":
        return cls(WbnVector4.from_bytes(data, offset), WbnVector4.from_bytes(data, offset + 16))

    def to_bytes(self) -> bytes:
        return self.minimum.to_bytes() + self.maximum.to_bytes()


@dataclass(slots=True)
class WbnMatrix:
    values: list[float]
    _raw: bytes | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.values) != 16:
            raise ValueError("WBN matrices require exactly 16 values")

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WbnMatrix":
        raw = bytes(data[offset : offset + 64])
        return cls(list(struct.unpack("<16f", raw)), raw)

    @property
    def translation(self) -> WbnVector3:
        return WbnVector3(self.values[12], self.values[13], self.values[14])

    def to_bytes(self) -> bytes:
        if self._raw is not None:
            original = struct.unpack("<16f", self._raw)
            if all(_same_float(current, previous) for current, previous in zip(self.values, original)):
                return self._raw
        return struct.pack("<16f", *self.values)


class WbnBoundType(IntEnum):
    SPHERE = 0
    CAPSULE = 1
    BOX = 3
    GEOMETRY = 4
    CURVED_GEOMETRY = 5
    GRID = 6
    RIBBON = 7
    BVH = 10
    SURFACE = 11
    COMPOSITE = 12


class WbnMaterialFlags(IntFlag):
    NONE = 0
    SIDEWALK_SPEC_1 = 0x0020
    SIDEWALK_SPEC_2 = 0x0040
    RESERVED_BIT_7 = 0x0080
    STAIRS = 0x0100
    BLOCK_GRIP = 0x0200
    BLOCK_CLIMB = 0x0400
    SHOOT_THROUGH = 0x0800
    BLOCK_JUMP_OVER = 0x1000
    SIDEWALK_SPEC_3 = 0x2000
    SEE_THROUGH = 0x4000
    RESERVED_BIT_15 = 0x8000


@dataclass(slots=True)
class WbnMaterial:
    material_id: int
    room_id: int
    flags: WbnMaterialFlags = WbnMaterialFlags.NONE
    _catalog: MaterialCatalog | None = field(default=None, repr=False, compare=False)
    _padding: int = field(default=0, repr=False, compare=False)
    _raw: bytes | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WbnMaterial":
        raw = bytes(data[offset : offset + 4])
        material_id, padding, packed = struct.unpack("<BBH", raw)
        return cls(
            material_id,
            packed & 0x1F,
            WbnMaterialFlags(packed & 0xFFE0),
            _padding=padding,
            _raw=raw,
        )

    @property
    def definition(self) -> MaterialDefinition | None:
        """Return the matching entry from materials.dat when a catalog is bound."""

        return None if self._catalog is None else self._catalog.get(self.material_id)

    @property
    def name(self) -> str | None:
        definition = self.definition
        return None if definition is None else definition.name

    def to_bytes(self) -> bytes:
        if not 0 <= self.material_id <= 0xFF:
            raise ValueError("WBN material ID must fit in one byte")
        if not 0 <= self.room_id <= 0x1F:
            raise ValueError("WBN material room ID must be between 0 and 31")
        packed = self.room_id | int(self.flags)
        result = struct.pack("<BBH", self.material_id, self._padding, packed)
        return self._raw if self._raw == result else result


@dataclass(slots=True)
class WbnVertex:
    x: int
    y: int
    z: int

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WbnVertex":
        return cls(*struct.unpack_from("<3h", data, offset))

    def to_bytes(self) -> bytes:
        try:
            return struct.pack("<3h", self.x, self.y, self.z)
        except struct.error as exc:
            raise ValueError("WBN quantized vertex components must fit in signed 16-bit integers") from exc

    def decode(self, quantum: WbnVector4, offset: WbnVector4) -> WbnVector3:
        return WbnVector3(
            self.x * quantum.x + offset.x,
            self.y * quantum.y + offset.y,
            self.z * quantum.z + offset.z,
        )


@dataclass(slots=True)
class WbnPolygon:
    normal: WbnVector3
    material_index: int
    area: float
    vertex_indices: tuple[int, int, int, int]
    neighbor_indices: tuple[int | None, int | None, int | None, int | None]
    _raw: bytes = field(repr=False, compare=False)
    _area_bits: int = field(repr=False, compare=False)
    _vertex_words: tuple[int, int, int, int] = field(repr=False, compare=False)
    _neighbor_words: tuple[int, int, int, int] = field(repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WbnPolygon":
        raw = bytes(data[offset : offset + 32])
        normal = WbnVector3.from_bytes(raw, 0)
        material_and_area = struct.unpack_from("<I", raw, 12)[0]
        area_bits = material_and_area & 0xFFFFFF00
        area = struct.unpack("<f", struct.pack("<I", area_bits))[0]
        vertex_words = struct.unpack_from("<4H", raw, 16)
        neighbor_words = struct.unpack_from("<4H", raw, 24)
        return cls(
            normal,
            material_and_area & 0xFF,
            area,
            tuple(value & 0x7FFF for value in vertex_words),
            tuple(None if value == 0xFFFF else value for value in neighbor_words),
            raw,
            area_bits,
            vertex_words,
            neighbor_words,
        )

    @property
    def is_triangle(self) -> bool:
        """Return whether the fourth vertex word is the triangle sentinel."""

        return self.vertex_indices[3] == 0

    @property
    def is_quad(self) -> bool:
        """Return whether all four vertex words describe polygon corners."""

        return not self.is_triangle

    @property
    def face_vertex_indices(self) -> tuple[int, ...]:
        """Return the three or four vertex indices that form the polygon face."""

        return self.vertex_indices[:3] if self.is_triangle else self.vertex_indices

    @property
    def face_neighbor_indices(self) -> tuple[int | None, ...]:
        """Return adjacency entries for the polygon's three or four edges."""

        return self.neighbor_indices[:3] if self.is_triangle else self.neighbor_indices

    def to_bytes(self) -> bytes:
        if not 0 <= self.material_index <= 0xFF:
            raise ValueError("WBN polygon material index must fit in one byte")
        original_area = struct.unpack("<f", struct.pack("<I", self._area_bits))[0]
        area_bits = self._area_bits if _same_float(self.area, original_area) else struct.unpack("<I", struct.pack("<f", self.area))[0] & 0xFFFFFF00
        vertices = self._vertex_words
        if tuple(value & 0x7FFF for value in vertices) != self.vertex_indices:
            if any(not 0 <= value <= 0x7FFF for value in self.vertex_indices):
                raise ValueError("WBN polygon vertex indices must be between 0 and 32767")
            vertices = self.vertex_indices
        original_neighbors = tuple(None if value == 0xFFFF else value for value in self._neighbor_words)
        neighbors = self._neighbor_words
        if original_neighbors != self.neighbor_indices:
            encoded: list[int] = []
            for value in self.neighbor_indices:
                if value is None:
                    encoded.append(0xFFFF)
                elif 0 <= value <= 0xFFFE:
                    encoded.append(value)
                else:
                    raise ValueError("WBN polygon neighbor indices must fit in 16 bits")
            neighbors = tuple(encoded)  # type: ignore[assignment]
        result = (
            self.normal.to_bytes()
            + struct.pack("<I", area_bits | self.material_index)
            + struct.pack("<4H", *vertices)
            + struct.pack("<4H", *neighbors)
        )
        return self._raw if result == self._raw else result


@dataclass(slots=True)
class WbnBvhNode:
    minimum: tuple[int, int, int]
    maximum: tuple[int, int, int]
    escape_or_polygon_index: int
    polygon_count: int
    _padding: int = field(default=0, repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WbnBvhNode":
        values = struct.unpack_from("<6hHBB", data, offset)
        return cls(tuple(values[:3]), tuple(values[3:6]), values[6], values[7], values[8])

    @property
    def is_leaf(self) -> bool:
        return self.polygon_count > 0

    @property
    def polygon_index(self) -> int | None:
        return self.escape_or_polygon_index if self.is_leaf else None

    @property
    def escape_index(self) -> int | None:
        return None if self.is_leaf else self.escape_or_polygon_index

    def to_bytes(self) -> bytes:
        try:
            return struct.pack(
                "<6hHBB", *self.minimum, *self.maximum,
                self.escape_or_polygon_index, self.polygon_count, self._padding,
            )
        except struct.error as exc:
            raise ValueError("invalid WBN BVH node value") from exc


@dataclass(slots=True)
class WbnBvhSubTree:
    minimum: tuple[int, int, int]
    maximum: tuple[int, int, int]
    first_node: int
    last_node: int

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WbnBvhSubTree":
        values = struct.unpack_from("<6hHH", data, offset)
        return cls(tuple(values[:3]), tuple(values[3:6]), values[6], values[7])

    def to_bytes(self) -> bytes:
        try:
            return struct.pack("<6hHH", *self.minimum, *self.maximum, self.first_node, self.last_node)
        except struct.error as exc:
            raise ValueError("invalid WBN BVH subtree value") from exc


@dataclass(slots=True)
class WbnBvhTree:
    nodes: list[WbnBvhNode]
    bounding_box_minimum: WbnVector4
    bounding_box_maximum: WbnVector4
    center: WbnVector4
    quantum: WbnVector4
    subtrees: list[WbnBvhSubTree]
    depth: int
    _offset: int = field(repr=False, compare=False)
    _nodes_offset: int = field(repr=False, compare=False)
    _node_count: int = field(repr=False, compare=False)
    _node_capacity: int = field(repr=False, compare=False)
    _subtrees_offset: int = field(repr=False, compare=False)
    _subtree_count: int = field(repr=False, compare=False)
    _subtree_capacity: int = field(repr=False, compare=False)

    def _write(self, data: bytearray) -> None:
        if len(self.nodes) != self._node_count:
            raise ValueError("WBN editing cannot change the BVH node count")
        if len(self.subtrees) != self._subtree_count:
            raise ValueError("WBN editing cannot change the BVH subtree count")
        data[self._offset + 0x10 : self._offset + 0x20] = self.bounding_box_minimum.to_bytes()
        data[self._offset + 0x20 : self._offset + 0x30] = self.bounding_box_maximum.to_bytes()
        data[self._offset + 0x30 : self._offset + 0x40] = self.center.to_bytes()
        data[self._offset + 0x40 : self._offset + 0x50] = self.quantum.to_bytes()
        for index, node in enumerate(self.nodes):
            start = self._nodes_offset + index * 16
            data[start : start + 16] = node.to_bytes()
        for index, subtree in enumerate(self.subtrees):
            start = self._subtrees_offset + index * 16
            data[start : start + 16] = subtree.to_bytes()


@dataclass(slots=True)
class WbnBound:
    bound_type: WbnBoundType
    flags: int
    part_index: int
    radius: float
    world_radius: float
    bounding_box_maximum: WbnVector4
    bounding_box_minimum: WbnVector4
    centroid: WbnVector4
    center_of_gravity: WbnVector4
    volume_distribution: WbnVector4
    margin: WbnVector3
    reference_count: int
    _offset: int = field(repr=False, compare=False)

    @property
    def bounding_box(self) -> WbnAabb:
        return WbnAabb(self.bounding_box_minimum, self.bounding_box_maximum)

    def _write_common(self, data: bytearray) -> None:
        if not 0 <= self.flags <= 0xFF:
            raise ValueError("WBN bound flags must fit in one byte")
        if not 0 <= self.part_index <= 0xFFFF:
            raise ValueError("WBN bound part index must fit in 16 bits")
        struct.pack_into("<BBHff", data, self._offset + 4, int(self.bound_type), self.flags, self.part_index, self.radius, self.world_radius)
        data[self._offset + 0x10 : self._offset + 0x20] = self.bounding_box_maximum.to_bytes()
        data[self._offset + 0x20 : self._offset + 0x30] = self.bounding_box_minimum.to_bytes()
        data[self._offset + 0x30 : self._offset + 0x40] = self.centroid.to_bytes()
        data[self._offset + 0x50 : self._offset + 0x60] = self.center_of_gravity.to_bytes()
        data[self._offset + 0x60 : self._offset + 0x70] = self.volume_distribution.to_bytes()
        data[self._offset + 0x70 : self._offset + 0x7C] = self.margin.to_bytes()
        struct.pack_into("<I", data, self._offset + 0x7C, self.reference_count)

    def _write(self, data: bytearray, visited: set[int]) -> None:
        if self._offset in visited:
            return
        visited.add(self._offset)
        self._write_common(data)


@dataclass(slots=True)
class WbnGeometry(WbnBound):
    quantum: WbnVector4
    quantization_offset: WbnVector4
    vertices: list[WbnVertex]
    polygons: list[WbnPolygon]
    materials: list[WbnMaterial]
    shrunk_vertices: list[WbnVertex] | None
    _vertices_offset: int = field(repr=False, compare=False)
    _polygons_offset: int = field(repr=False, compare=False)
    _materials_offset: int = field(repr=False, compare=False)
    _shrunk_vertices_offset: int | None = field(repr=False, compare=False)
    _vertex_count: int = field(repr=False, compare=False)
    _polygon_count: int = field(repr=False, compare=False)
    _material_count: int = field(repr=False, compare=False)

    @property
    def decoded_vertices(self) -> list[WbnVector3]:
        return [vertex.decode(self.quantum, self.quantization_offset) for vertex in self.vertices]

    def material_for_polygon(self, polygon: WbnPolygon | int) -> WbnMaterial:
        """Resolve a polygon's local material slot to its WBN material entry."""

        value = self.polygons[polygon] if isinstance(polygon, int) else polygon
        try:
            return self.materials[value.material_index]
        except IndexError as exc:
            raise ValueError(
                f"WBN polygon references missing material slot {value.material_index}"
            ) from exc

    def _write(self, data: bytearray, visited: set[int]) -> None:
        if self._offset in visited:
            return
        WbnBound._write(self, data, visited)
        if len(self.vertices) != self._vertex_count:
            raise ValueError("WBN editing cannot change the vertex count")
        if len(self.polygons) != self._polygon_count:
            raise ValueError("WBN editing cannot change the polygon count")
        if len(self.materials) != self._material_count:
            raise ValueError("WBN editing cannot change the material count")
        if self.shrunk_vertices is not None and len(self.shrunk_vertices) != self._vertex_count:
            raise ValueError("WBN editing cannot change the shrunk vertex count")
        data[self._offset + 0x90 : self._offset + 0xA0] = self.quantum.to_bytes()
        data[self._offset + 0xA0 : self._offset + 0xB0] = self.quantization_offset.to_bytes()
        for index, vertex in enumerate(self.vertices):
            start = self._vertices_offset + index * 6
            data[start : start + 6] = vertex.to_bytes()
        if self.shrunk_vertices is not None and self._shrunk_vertices_offset is not None:
            for index, vertex in enumerate(self.shrunk_vertices):
                start = self._shrunk_vertices_offset + index * 6
                data[start : start + 6] = vertex.to_bytes()
        for index, polygon in enumerate(self.polygons):
            start = self._polygons_offset + index * 32
            data[start : start + 32] = polygon.to_bytes()
        for index, material in enumerate(self.materials):
            start = self._materials_offset + index * 4
            data[start : start + 4] = material.to_bytes()


@dataclass(slots=True)
class WbnBvhGeometry(WbnGeometry):
    bvh: WbnBvhTree | None

    def _write(self, data: bytearray, visited: set[int]) -> None:
        WbnGeometry._write(self, data, visited)
        if self.bvh is not None:
            self.bvh._write(data)


@dataclass(slots=True)
class WbnComposite(WbnBound):
    children: list[WbnBound]
    current_matrices: list[WbnMatrix] | None
    last_matrices: list[WbnMatrix] | None
    child_bounding_boxes: list[WbnAabb] | None
    capacity: int
    _children_offset: int = field(repr=False, compare=False)
    _current_matrices_offset: int | None = field(repr=False, compare=False)
    _last_matrices_offset: int | None = field(repr=False, compare=False)
    _child_bounding_boxes_offset: int | None = field(repr=False, compare=False)
    _child_count: int = field(repr=False, compare=False)

    def _write(self, data: bytearray, visited: set[int]) -> None:
        if self._offset in visited:
            return
        WbnBound._write(self, data, visited)
        if len(self.children) != self._child_count:
            raise ValueError("WBN editing cannot change the composite child count")
        arrays = (
            (self.current_matrices, self._current_matrices_offset, 64, "current matrix"),
            (self.last_matrices, self._last_matrices_offset, 64, "last matrix"),
            (self.child_bounding_boxes, self._child_bounding_boxes_offset, 32, "child bounding box"),
        )
        for values, offset, size, label in arrays:
            if values is None:
                continue
            if offset is None or len(values) != self._child_count:
                raise ValueError(f"WBN editing cannot change the {label} array")
            for index, value in enumerate(values):
                start = offset + index * size
                data[start : start + size] = value.to_bytes()
        for child in self.children:
            child._write(data, visited)


def _iter_bounds(roots: Iterable[WbnBound]) -> Iterator[WbnBound]:
    pending = list(roots)
    pending.reverse()
    seen: set[int] = set()
    while pending:
        bound = pending.pop()
        if bound._offset in seen:
            continue
        seen.add(bound._offset)
        yield bound
        if isinstance(bound, WbnComposite):
            pending.extend(reversed(bound.children))


def _iter_geometries(bounds: Iterable[WbnBound]) -> Iterator[WbnGeometry]:
    return (bound for bound in bounds if isinstance(bound, WbnGeometry))


class _WbnParser:
    def __init__(self, data: bytes):
        self.data = data
        self.cache: dict[int, WbnBound] = {}
        self.visiting: set[int] = set()

    def _check(self, offset: int, size: int, label: str) -> None:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError(f"WBN {label} points outside the virtual allocation")

    def _u32(self, offset: int) -> int:
        self._check(offset, 4, "integer")
        return struct.unpack_from("<I", self.data, offset)[0]

    def _pointer(self, pointer: int, size: int, label: str) -> int:
        offset = rsc5_pointer_offset(pointer)
        self._check(offset, size, label)
        return offset

    def _optional_pointer(self, pointer: int, size: int, label: str) -> int | None:
        return None if pointer == 0 else self._pointer(pointer, size, label)

    def _vertices(self, offset: int, count: int) -> list[WbnVertex]:
        if _native_decode_wbn_vertices is None:
            return [
                WbnVertex.from_bytes(self.data, offset + index * 6)
                for index in range(count)
            ]
        return [WbnVertex(*values) for values in _native_decode_wbn_vertices(self.data, offset, count)]

    def _polygons(self, offset: int, count: int) -> list[WbnPolygon]:
        if _native_decode_wbn_polygons is None:
            return [
                WbnPolygon.from_bytes(self.data, offset + index * 32)
                for index in range(count)
            ]
        polygons: list[WbnPolygon] = []
        for record in _native_decode_wbn_polygons(self.data, offset, count):
            raw = bytes(record[5])
            polygons.append(
                WbnPolygon(
                    WbnVector3(*record[0], _raw=raw[:12]),
                    int(record[1]),
                    float(record[2]),
                    tuple(record[3]),
                    tuple(record[4]),
                    raw,
                    int(record[6]),
                    tuple(record[7]),
                    tuple(record[8]),
                )
            )
        return polygons

    def _bvh_nodes(self, offset: int, count: int) -> list[WbnBvhNode]:
        if _native_decode_wbn_bvh_nodes is None:
            return [
                WbnBvhNode.from_bytes(self.data, offset + index * 16)
                for index in range(count)
            ]
        return [
            WbnBvhNode(tuple(record[0]), tuple(record[1]), record[2], record[3], record[4])
            for record in _native_decode_wbn_bvh_nodes(self.data, offset, count)
        ]

    def _bvh_subtrees(self, offset: int, count: int) -> list[WbnBvhSubTree]:
        if _native_decode_wbn_bvh_subtrees is None:
            return [
                WbnBvhSubTree.from_bytes(self.data, offset + index * 16)
                for index in range(count)
            ]
        return [
            WbnBvhSubTree(tuple(record[0]), tuple(record[1]), record[2], record[3])
            for record in _native_decode_wbn_bvh_subtrees(self.data, offset, count)
        ]

    def _common(self, offset: int, bound_type: WbnBoundType) -> dict[str, object]:
        self._check(offset, WBN_BOUND_SIZE, "bound")
        flags, part_index, radius, world_radius = struct.unpack_from("<xBHff", self.data, offset + 4)
        return {
            "bound_type": bound_type,
            "flags": flags,
            "part_index": part_index,
            "radius": radius,
            "world_radius": world_radius,
            "bounding_box_maximum": WbnVector4.from_bytes(self.data, offset + 0x10),
            "bounding_box_minimum": WbnVector4.from_bytes(self.data, offset + 0x20),
            "centroid": WbnVector4.from_bytes(self.data, offset + 0x30),
            "center_of_gravity": WbnVector4.from_bytes(self.data, offset + 0x50),
            "volume_distribution": WbnVector4.from_bytes(self.data, offset + 0x60),
            "margin": WbnVector3.from_bytes(self.data, offset + 0x70),
            "reference_count": self._u32(offset + 0x7C),
            "_offset": offset,
        }

    def _geometry(self, offset: int) -> dict[str, object]:
        self._check(offset, WBN_GEOMETRY_SIZE, "geometry bound")
        shrunk_pointer = self._u32(offset + 0x84)
        polygons_pointer = self._u32(offset + 0x8C)
        vertices_pointer = self._u32(offset + 0xB0)
        vertex_count = self._u32(offset + 0xC8)
        polygon_count = self._u32(offset + 0xCC)
        materials_pointer = self._u32(offset + 0xD0)
        material_count = self.data[offset + 0xD8]
        vertices_offset = self._pointer(vertices_pointer, vertex_count * 6, "vertex array")
        polygons_offset = self._pointer(polygons_pointer, polygon_count * 32, "polygon array")
        materials_offset = self._pointer(materials_pointer, material_count * 4, "material array")
        shrunk_offset = self._optional_pointer(shrunk_pointer, vertex_count * 6, "shrunk vertex array")
        return {
            "quantum": WbnVector4.from_bytes(self.data, offset + 0x90),
            "quantization_offset": WbnVector4.from_bytes(self.data, offset + 0xA0),
            "vertices": self._vertices(vertices_offset, vertex_count),
            "polygons": self._polygons(polygons_offset, polygon_count),
            "materials": [WbnMaterial.from_bytes(self.data, materials_offset + index * 4) for index in range(material_count)],
            "shrunk_vertices": None if shrunk_offset is None else self._vertices(shrunk_offset, vertex_count),
            "_vertices_offset": vertices_offset,
            "_polygons_offset": polygons_offset,
            "_materials_offset": materials_offset,
            "_shrunk_vertices_offset": shrunk_offset,
            "_vertex_count": vertex_count,
            "_polygon_count": polygon_count,
            "_material_count": material_count,
        }

    def _bvh(self, pointer: int) -> WbnBvhTree | None:
        if pointer == 0:
            return None
        offset = self._pointer(pointer, 0x58, "BVH tree")
        nodes_pointer, node_count, node_capacity, depth = struct.unpack_from("<4I", self.data, offset)
        subtrees_pointer = self._u32(offset + 0x50)
        subtree_count, subtree_capacity = struct.unpack_from("<HH", self.data, offset + 0x54)
        if node_count > node_capacity or subtree_count > subtree_capacity:
            raise ValueError("WBN BVH array count exceeds its capacity")
        nodes_offset = self._pointer(nodes_pointer, node_count * 16, "BVH node array")
        subtrees_offset = self._pointer(subtrees_pointer, subtree_count * 16, "BVH subtree array")
        return WbnBvhTree(
            self._bvh_nodes(nodes_offset, node_count),
            WbnVector4.from_bytes(self.data, offset + 0x10),
            WbnVector4.from_bytes(self.data, offset + 0x20),
            WbnVector4.from_bytes(self.data, offset + 0x30),
            WbnVector4.from_bytes(self.data, offset + 0x40),
            self._bvh_subtrees(subtrees_offset, subtree_count),
            depth,
            offset,
            nodes_offset,
            node_count,
            node_capacity,
            subtrees_offset,
            subtree_count,
            subtree_capacity,
        )

    def parse_bound(self, offset: int) -> WbnBound:
        if offset in self.cache:
            return self.cache[offset]
        if offset in self.visiting:
            raise ValueError("cyclic WBN bound pointers are not supported")
        self.visiting.add(offset)
        self._check(offset, 5, "bound header")
        try:
            bound_type = WbnBoundType(self.data[offset + 4])
        except ValueError as exc:
            raise ValueError(f"unsupported WBN bound type: {self.data[offset + 4]}") from exc
        common = self._common(offset, bound_type)
        if bound_type == WbnBoundType.BVH:
            bound = WbnBvhGeometry(**common, **self._geometry(offset), bvh=self._bvh(self._u32(offset + 0xE0)))
        elif bound_type == WbnBoundType.GEOMETRY:
            bound = WbnGeometry(**common, **self._geometry(offset))
        elif bound_type == WbnBoundType.COMPOSITE:
            self._check(offset, WBN_COMPOSITE_SIZE, "composite bound")
            bounds_pointer, current_pointer, last_pointer, aabbs_pointer = struct.unpack_from("<4I", self.data, offset + 0x80)
            capacity, count = struct.unpack_from("<HH", self.data, offset + 0x90)
            if count > capacity:
                raise ValueError("WBN composite child count exceeds its capacity")
            children_offset = self._pointer(bounds_pointer, capacity * 4, "composite child pointer array")
            child_pointers = struct.unpack_from(f"<{capacity}I", self.data, children_offset) if capacity else ()
            children = [
                self.parse_bound(self._pointer(child_pointers[index], WBN_BOUND_SIZE, "composite child"))
                for index in range(count)
            ]
            current_offset = self._optional_pointer(current_pointer, count * 64, "current matrix array")
            last_offset = self._optional_pointer(last_pointer, count * 64, "last matrix array")
            aabbs_offset = self._optional_pointer(aabbs_pointer, count * 32, "child bounding box array")
            bound = WbnComposite(
                **common,
                children=children,
                current_matrices=None if current_offset is None else [WbnMatrix.from_bytes(self.data, current_offset + index * 64) for index in range(count)],
                last_matrices=None if last_offset is None else [WbnMatrix.from_bytes(self.data, last_offset + index * 64) for index in range(count)],
                child_bounding_boxes=None if aabbs_offset is None else [WbnAabb.from_bytes(self.data, aabbs_offset + index * 32) for index in range(count)],
                capacity=capacity,
                _children_offset=children_offset,
                _current_matrices_offset=current_offset,
                _last_matrices_offset=last_offset,
                _child_bounding_boxes_offset=aabbs_offset,
                _child_count=count,
            )
        else:
            bound = WbnBound(**common)
        self.cache[offset] = bound
        self.visiting.remove(offset)
        return bound


@dataclass(slots=True)
class WbnDocument:
    root: WbnBound
    resource: Rsc5Resource
    name: str = "bounds.wbn"
    source_path: str = ""
    material_catalog: MaterialCatalog | None = field(default=None, repr=False, compare=False)
    _root_pointer: int = field(default=0, repr=False, compare=False)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        materials: MaterialCatalog | None = None,
    ) -> "WbnDocument":
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name, materials=materials)
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        name: str = "bounds.wbn",
        materials: MaterialCatalog | None = None,
    ) -> "WbnDocument":
        resource = Rsc5Resource.from_bytes(data)
        if resource.version != WBN_RESOURCE_VERSION:
            raise ValueError(f"unsupported WBN resource version: {resource.version:#x}")
        if resource.physical_data:
            raise ValueError("WBN resources with physical allocations are not supported")
        if len(resource.virtual_data) < 12:
            raise ValueError("truncated WBN root wrapper")
        root_pointer = struct.unpack_from("<I", resource.virtual_data, 8)[0]
        root_offset = rsc5_pointer_offset(root_pointer)
        parser = _WbnParser(resource.virtual_data)
        root = parser.parse_bound(root_offset)
        document = cls(root, resource, name, _root_pointer=root_pointer)
        if materials is not None:
            document.bind_materials(materials)
        return document

    def bind_materials(self, catalog: MaterialCatalog) -> "WbnDocument":
        """Resolve every WBN material ID through a materials.dat catalog."""

        self.material_catalog = catalog
        for geometry in _iter_geometries(self):
            for material in geometry.materials:
                material._catalog = catalog
        return self

    def __iter__(self) -> Iterator[WbnBound]:
        yield from _iter_bounds((self.root,))

    @property
    def geometries(self) -> list[WbnGeometry]:
        return list(_iter_geometries(self))

    def to_bytes(self) -> bytes:
        virtual_data = bytearray(self.resource.virtual_data)
        self.root._write(virtual_data, set())
        return self.resource.to_bytes(virtual_data=bytes(virtual_data))

    def save(self, path: str | Path) -> None:
        atomic_write(path, self.to_bytes())


def load_wbn(
    source: str | Path | bytes | BinaryIO,
    *,
    materials: MaterialCatalog | None = None,
) -> WbnDocument:
    if isinstance(source, (str, Path)):
        return WbnDocument.from_path(source, materials=materials)
    if isinstance(source, bytes):
        return WbnDocument.from_bytes(source, materials=materials)
    return WbnDocument.from_bytes(source.read(), materials=materials)


__all__ = [
    "WBN_BOUND_SIZE", "WBN_BVH_GEOMETRY_SIZE", "WBN_COMPOSITE_SIZE", "WBN_GEOMETRY_SIZE",
    "WBN_RESOURCE_VERSION", "WbnAabb", "WbnBound", "WbnBoundType", "WbnBvhGeometry",
    "WbnBvhNode", "WbnBvhSubTree", "WbnBvhTree", "WbnComposite", "WbnDocument",
    "WbnGeometry", "WbnMaterial", "WbnMaterialFlags", "WbnMatrix", "WbnPolygon",
    "WbnVector3", "WbnVector4", "WbnVertex", "load_wbn",
]
