from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from enum import IntFlag
from pathlib import Path
from typing import BinaryIO, Iterator

from ._utils import atomic_write
from .rsc import Rsc5Resource, rsc5_pointer_offset


WNV_RESOURCE_VERSION = 1
WNV_HEADER_SIZE = 0x94
WNV_VERTEX_SIZE = 6
WNV_EDGE_SIZE = 8
WNV_POLYGON_SIZE = 40
WNV_QUADTREE_SIZE = 64
WNV_QUADTREE_DATA_SIZE = 16
WNV_COVER_POINT_SIZE = 8
WNV_QUANTIZED_SCALE = 0xFFFF
WNV_AABB_SCALE = 4.0


def _same_float(left: float, right: float) -> bool:
    return left == right or (math.isnan(left) and math.isnan(right))


def _require_uint(value: int, bits: int, label: str) -> None:
    if not 0 <= value < 1 << bits:
        raise ValueError(f"{label} must fit in {bits} bits")


def _replace_bits(original: int, value: int, shift: int, mask: int, label: str) -> int:
    if not 0 <= value <= mask:
        raise ValueError(f"{label} must be between 0 and {mask}")
    return (original & ~(mask << shift)) | (value << shift)


class WnvFlags(IntFlag):
    NONE = 0
    POLYGONS = 1 << 0
    PORTALS = 1 << 1
    VEHICLE = 1 << 2
    RESERVED_8 = 1 << 3
    RESERVED_16 = 1 << 4
    RESERVED_32 = 1 << 5


class WnvEdgeFlags(IntFlag):
    NONE = 0
    ADJACENCY_DISABLED = 1 << 0
    PROVIDES_COVER = 1 << 1
    HIGH_DROP = 1 << 2
    EXTERNAL_EDGE = 1 << 3


class WnvPolygonFlags(IntFlag):
    NONE = 0
    SMALL = 1 << 0
    LARGE = 1 << 1
    PAVEMENT = 1 << 2
    SHELTERED = 1 << 3
    RESERVED_16 = 1 << 4
    RESERVED_32 = 1 << 5
    TOO_STEEP = 1 << 6
    WATER = 1 << 7
    DEBUG_MARKED = 1 << 8
    NEAR_CAR_NODE = 1 << 9
    INTERIOR = 1 << 10
    ISOLATED = 1 << 11


_WNV_EDGE_NAMED_FLAG_MASK = sum(int(flag) for flag in WnvEdgeFlags)
_WNV_POLYGON_NAMED_FLAG_MASK = sum(int(flag) for flag in WnvPolygonFlags)


@dataclass(slots=True)
class WnvVector3:
    x: float
    y: float
    z: float


@dataclass(slots=True)
class WnvVector4:
    x: float
    y: float
    z: float
    w: float
    _raw: bytes | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WnvVector4":
        raw = bytes(data[offset : offset + 16])
        return cls(*struct.unpack("<4f", raw), _raw=raw)

    @property
    def xyz(self) -> WnvVector3:
        return WnvVector3(self.x, self.y, self.z)

    def to_bytes(self) -> bytes:
        values = (self.x, self.y, self.z, self.w)
        if self._raw is not None:
            original = struct.unpack("<4f", self._raw)
            output = bytearray(self._raw)
            for index, (current, previous) in enumerate(zip(values, original)):
                if not _same_float(current, previous):
                    struct.pack_into("<f", output, index * 4, current)
            return bytes(output)
        return struct.pack("<4f", *values)


@dataclass(slots=True)
class WnvMatrix:
    values: list[float]
    _raw: bytes | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.values) != 16:
            raise ValueError("WNV transforms require exactly 16 values")

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0) -> "WnvMatrix":
        raw = bytes(data[offset : offset + 64])
        return cls(list(struct.unpack("<16f", raw)), raw)

    def to_bytes(self) -> bytes:
        if len(self.values) != 16:
            raise ValueError("WNV transforms require exactly 16 values")
        if self._raw is not None:
            original = struct.unpack("<16f", self._raw)
            output = bytearray(self._raw)
            for index, (current, previous) in enumerate(zip(self.values, original)):
                if not _same_float(current, previous):
                    struct.pack_into("<f", output, index * 4, current)
            return bytes(output)
        return struct.pack("<16f", *self.values)


@dataclass(slots=True)
class WnvAabb:
    min_x: int
    max_x: int
    min_y: int
    max_y: int
    min_z: int
    max_z: int

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WnvAabb":
        return cls(*struct.unpack_from("<6h", data, offset))

    @property
    def minimum(self) -> WnvVector3:
        return WnvVector3(
            self.min_x / WNV_AABB_SCALE,
            self.min_y / WNV_AABB_SCALE,
            self.min_z / WNV_AABB_SCALE,
        )

    @minimum.setter
    def minimum(self, value: WnvVector3) -> None:
        self.min_x = math.floor(value.x * WNV_AABB_SCALE)
        self.min_y = math.floor(value.y * WNV_AABB_SCALE)
        self.min_z = math.floor(value.z * WNV_AABB_SCALE)

    @property
    def maximum(self) -> WnvVector3:
        return WnvVector3(
            self.max_x / WNV_AABB_SCALE,
            self.max_y / WNV_AABB_SCALE,
            self.max_z / WNV_AABB_SCALE,
        )

    @maximum.setter
    def maximum(self, value: WnvVector3) -> None:
        self.max_x = math.ceil(value.x * WNV_AABB_SCALE)
        self.max_y = math.ceil(value.y * WNV_AABB_SCALE)
        self.max_z = math.ceil(value.z * WNV_AABB_SCALE)

    def to_bytes(self) -> bytes:
        try:
            return struct.pack(
                "<6h",
                self.min_x,
                self.max_x,
                self.min_y,
                self.max_y,
                self.min_z,
                self.max_z,
            )
        except struct.error as exc:
            raise ValueError("WNV AABB values must fit in signed 16-bit integers") from exc


@dataclass(slots=True)
class WnvVertex:
    x: int
    y: int
    z: int

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WnvVertex":
        return cls(*struct.unpack_from("<3H", data, offset))

    def decode(self, minimum: WnvVector3, extents: WnvVector4) -> WnvVector3:
        return WnvVector3(
            minimum.x + extents.x * self.x / WNV_QUANTIZED_SCALE,
            minimum.y + extents.y * self.y / WNV_QUANTIZED_SCALE,
            minimum.z + extents.z * self.z / WNV_QUANTIZED_SCALE,
        )

    def to_bytes(self) -> bytes:
        try:
            return struct.pack("<3H", self.x, self.y, self.z)
        except struct.error as exc:
            raise ValueError("WNV vertex components must fit in unsigned 16-bit integers") from exc


@dataclass(slots=True)
class WnvEdge:
    data_1: int
    data_2: int

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WnvEdge":
        return cls(*struct.unpack_from("<2I", data, offset))

    @property
    def area_id_1(self) -> int:
        return self.data_1 & 0x1F

    @area_id_1.setter
    def area_id_1(self, value: int) -> None:
        self.data_1 = _replace_bits(self.data_1, value, 0, 0x1F, "WNV edge area ID")

    @property
    def area_id_2(self) -> int:
        return self.data_2 & 0x1F

    @area_id_2.setter
    def area_id_2(self, value: int) -> None:
        self.data_2 = _replace_bits(self.data_2, value, 0, 0x1F, "WNV edge area ID")

    @property
    def polygon_id_1(self) -> int:
        return (self.data_1 >> 5) & 0x7FFF

    @polygon_id_1.setter
    def polygon_id_1(self, value: int) -> None:
        self.data_1 = _replace_bits(self.data_1, value, 5, 0x7FFF, "WNV edge polygon ID")

    @property
    def polygon_id_2(self) -> int:
        return (self.data_2 >> 5) & 0x7FFF

    @polygon_id_2.setter
    def polygon_id_2(self, value: int) -> None:
        self.data_2 = _replace_bits(self.data_2, value, 5, 0x7FFF, "WNV edge polygon ID")

    @property
    def adjacency_type(self) -> int:
        return (self.data_1 >> 20) & 0x3

    @adjacency_type.setter
    def adjacency_type(self, value: int) -> None:
        self.data_1 = _replace_bits(self.data_1, value, 20, 0x3, "WNV edge adjacency type")

    @property
    def space_around_vertex(self) -> int:
        return (self.data_1 >> 22) & 0x1F

    @space_around_vertex.setter
    def space_around_vertex(self, value: int) -> None:
        self.data_1 = _replace_bits(self.data_1, value, 22, 0x1F, "WNV vertex clearance")

    @property
    def space_beyond_edge(self) -> int:
        return (self.data_1 >> 27) & 0x1F

    @space_beyond_edge.setter
    def space_beyond_edge(self, value: int) -> None:
        self.data_1 = _replace_bits(self.data_1, value, 27, 0x1F, "WNV edge clearance")

    @property
    def flags(self) -> WnvEdgeFlags:
        return WnvEdgeFlags((self.data_2 >> 20) & 0xFFF)

    @flags.setter
    def flags(self, value: WnvEdgeFlags | int) -> None:
        self.data_2 = _replace_bits(self.data_2, int(value), 20, 0xFFF, "WNV edge flags")

    @property
    def unresolved_flags(self) -> int:
        """Return preserved edge bits whose runtime behavior is not documented."""

        return int(self.flags) & ~_WNV_EDGE_NAMED_FLAG_MASK

    def to_bytes(self) -> bytes:
        _require_uint(self.data_1, 32, "WNV edge data 1")
        _require_uint(self.data_2, 32, "WNV edge data 2")
        return struct.pack("<2I", self.data_1, self.data_2)


@dataclass(slots=True)
class WnvPolygon:
    data_1: int
    data_index: int
    metadata_08: int
    metadata_0c: int
    cell_aabb: WnvAabb
    data_2: int
    centroid_x: int
    centroid_y: int
    cover_directions: int
    immediate_mode_flags: int
    data_3: int

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WnvPolygon":
        data_1, data_index, metadata_08, metadata_0c = struct.unpack_from("<4I", data, offset)
        data_2 = struct.unpack_from("<I", data, offset + 28)[0]
        centroid_x, centroid_y, cover_directions, immediate_mode_flags = struct.unpack_from(
            "<4B", data, offset + 32
        )
        data_3 = struct.unpack_from("<I", data, offset + 36)[0]
        return cls(
            data_1,
            data_index,
            metadata_08,
            metadata_0c,
            WnvAabb.from_bytes(data, offset + 16),
            data_2,
            centroid_x,
            centroid_y,
            cover_directions,
            immediate_mode_flags,
            data_3,
        )

    @property
    def flags(self) -> WnvPolygonFlags:
        return WnvPolygonFlags((self.data_1 & 0xFF) | (((self.data_2 >> 4) & 0x3FF) << 8))

    @flags.setter
    def flags(self, value: WnvPolygonFlags | int) -> None:
        encoded = int(value)
        _require_uint(encoded, 18, "WNV polygon flags")
        self.data_1 = (self.data_1 & ~0xFF) | (encoded & 0xFF)
        self.data_2 = _replace_bits(self.data_2, (encoded >> 8) & 0x3FF, 4, 0x3FF, "WNV polygon flags")

    @property
    def unresolved_flags(self) -> int:
        """Return preserved polygon bits whose runtime behavior is not documented."""

        return int(self.flags) & ~_WNV_POLYGON_NAMED_FLAG_MASK

    @property
    def index_count(self) -> int:
        return (self.data_1 >> 21) & 0xF

    @index_count.setter
    def index_count(self, value: int) -> None:
        self.data_1 = _replace_bits(self.data_1, value, 21, 0xF, "WNV polygon index count")

    @property
    def index_start(self) -> int:
        return self.data_index & 0x1FFFF

    @index_start.setter
    def index_start(self, value: int) -> None:
        self.data_index = _replace_bits(self.data_index, value, 0, 0x1FFFF, "WNV polygon index start")

    @property
    def area_id(self) -> int:
        return (self.data_index >> 17) & 0xFFF

    @area_id.setter
    def area_id(self, value: int) -> None:
        self.data_index = _replace_bits(self.data_index, value, 17, 0xFFF, "WNV polygon area ID")

    @property
    def pedestrian_density(self) -> int:
        return (self.data_index >> 29) & 0x7

    @pedestrian_density.setter
    def pedestrian_density(self, value: int) -> None:
        self.data_index = _replace_bits(self.data_index, value, 29, 0x7, "WNV pedestrian density")

    @property
    def part_id(self) -> int:
        return (self.data_3 >> 4) & 0xFF

    @part_id.setter
    def part_id(self, value: int) -> None:
        self.data_3 = _replace_bits(self.data_3, value, 4, 0xFF, "WNV polygon part ID")

    @property
    def link_count(self) -> int:
        return (self.data_3 >> 12) & 0x7

    @link_count.setter
    def link_count(self, value: int) -> None:
        self.data_3 = _replace_bits(self.data_3, value, 12, 0x7, "WNV polygon link count")

    @property
    def link_start(self) -> int:
        return (self.data_3 >> 15) & 0x1FFFF

    @link_start.setter
    def link_start(self, value: int) -> None:
        self.data_3 = _replace_bits(self.data_3, value, 15, 0x1FFFF, "WNV polygon link start")

    def vertex_indices(self, indices: list[int]) -> tuple[int, ...]:
        end = self.index_start + self.index_count
        return tuple(indices[self.index_start:end])

    def to_bytes(self) -> bytes:
        for value, label in (
            (self.data_1, "data 1"),
            (self.data_index, "index data"),
            (self.metadata_08, "metadata 08"),
            (self.metadata_0c, "metadata 0C"),
            (self.data_2, "data 2"),
            (self.data_3, "data 3"),
        ):
            _require_uint(value, 32, f"WNV polygon {label}")
        for value, label in (
            (self.centroid_x, "centroid X"),
            (self.centroid_y, "centroid Y"),
            (self.cover_directions, "cover directions"),
            (self.immediate_mode_flags, "immediate-mode flags"),
        ):
            _require_uint(value, 8, f"WNV polygon {label}")
        return (
            struct.pack("<4I", self.data_1, self.data_index, self.metadata_08, self.metadata_0c)
            + self.cell_aabb.to_bytes()
            + struct.pack(
                "<I4BI",
                self.data_2,
                self.centroid_x,
                self.centroid_y,
                self.cover_directions,
                self.immediate_mode_flags,
                self.data_3,
            )
        )


@dataclass(slots=True)
class WnvCoverPoint:
    position: WnvVertex
    cover_flags: int

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "WnvCoverPoint":
        return cls(WnvVertex.from_bytes(data, offset), struct.unpack_from("<H", data, offset + 6)[0])

    @property
    def direction(self) -> int:
        return self.cover_flags & 0xFF

    @direction.setter
    def direction(self, value: int) -> None:
        self.cover_flags = _replace_bits(self.cover_flags, value, 0, 0xFF, "WNV cover direction")

    @property
    def cover_type(self) -> int:
        return (self.cover_flags >> 8) & 0x7

    @cover_type.setter
    def cover_type(self, value: int) -> None:
        self.cover_flags = _replace_bits(self.cover_flags, value, 8, 0x7, "WNV cover type")

    @property
    def disabled(self) -> bool:
        return bool(self.cover_flags & (1 << 11))

    @disabled.setter
    def disabled(self, value: bool) -> None:
        if value:
            self.cover_flags |= 1 << 11
        else:
            self.cover_flags &= ~(1 << 11)

    def to_bytes(self) -> bytes:
        _require_uint(self.cover_flags, 16, "WNV cover flags")
        return self.position.to_bytes() + struct.pack("<H", self.cover_flags)


@dataclass(slots=True)
class WnvQuadTreeData:
    cover_points_start: int
    metadata_02: int
    metadata_03: int
    polygon_ids: list[int]
    cover_points: list[WnvCoverPoint]
    _offset: int = field(repr=False, compare=False)
    _polygon_ids_offset: int | None = field(repr=False, compare=False)
    _cover_points_offset: int | None = field(repr=False, compare=False)
    _polygon_count: int = field(repr=False, compare=False)
    _cover_point_count: int = field(repr=False, compare=False)

    def _write(self, data: bytearray) -> None:
        if len(self.polygon_ids) != self._polygon_count:
            raise ValueError("WNV editing cannot change a quadtree leaf polygon count")
        if len(self.cover_points) != self._cover_point_count:
            raise ValueError("WNV editing cannot change a quadtree leaf cover-point count")
        _require_uint(self.cover_points_start, 16, "WNV cover-point start ID")
        _require_uint(self.metadata_02, 8, "WNV quadtree leaf metadata 02")
        _require_uint(self.metadata_03, 8, "WNV quadtree leaf metadata 03")
        struct.pack_into(
            "<HBB",
            data,
            self._offset,
            self.cover_points_start,
            self.metadata_02,
            self.metadata_03,
        )
        if self._polygon_ids_offset is not None:
            for index, polygon_id in enumerate(self.polygon_ids):
                _require_uint(polygon_id, 16, "WNV quadtree polygon ID")
                struct.pack_into("<H", data, self._polygon_ids_offset + index * 2, polygon_id)
        if self._cover_points_offset is not None:
            for index, point in enumerate(self.cover_points):
                start = self._cover_points_offset + index * WNV_COVER_POINT_SIZE
                data[start : start + WNV_COVER_POINT_SIZE] = point.to_bytes()


@dataclass(slots=True)
class WnvQuadTree:
    aabb_minimum: WnvVector4
    aabb_maximum: WnvVector4
    cell_aabb: WnvAabb
    data: WnvQuadTreeData | None
    children: list["WnvQuadTree | None"]
    _offset: int = field(repr=False, compare=False)
    _has_data: bool = field(repr=False, compare=False)
    _child_presence: tuple[bool, bool, bool, bool] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.children) != 4:
            raise ValueError("WNV quadtree nodes require exactly four child slots")

    def __iter__(self) -> Iterator["WnvQuadTree"]:
        pending = [self]
        while pending:
            node = pending.pop()
            yield node
            pending.extend(child for child in reversed(node.children) if child is not None)

    def _write(self, output: bytearray, visited: set[int]) -> None:
        if self._offset in visited:
            return
        visited.add(self._offset)
        if (self.data is not None) != self._has_data:
            raise ValueError("WNV editing cannot add or remove quadtree leaf data")
        presence = tuple(child is not None for child in self.children)
        if presence != self._child_presence:
            raise ValueError("WNV editing cannot change quadtree child topology")
        output[self._offset : self._offset + 16] = self.aabb_minimum.to_bytes()
        output[self._offset + 16 : self._offset + 32] = self.aabb_maximum.to_bytes()
        output[self._offset + 32 : self._offset + 44] = self.cell_aabb.to_bytes()
        if self.data is not None:
            self.data._write(output)
        for child in self.children:
            if child is not None:
                child._write(output, visited)


class _WnvParser:
    def __init__(self, data: bytes):
        self.data = data
        self.quadtree_cache: dict[int, WnvQuadTree] = {}
        self.quadtree_data_cache: dict[int, WnvQuadTreeData] = {}
        self.visiting: set[int] = set()

    def _check(self, offset: int, size: int, label: str) -> None:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError(f"WNV {label} points outside the virtual allocation")

    def _pointer(self, pointer: int, size: int, label: str) -> int:
        offset = rsc5_pointer_offset(pointer)
        self._check(offset, size, label)
        return offset

    def _array_offset(self, pointer: int, count: int, size: int, label: str) -> int | None:
        if count == 0 and pointer == 0:
            return None
        return self._pointer(pointer, count * size, label)

    def parse_quadtree_data(self, pointer: int) -> WnvQuadTreeData | None:
        if pointer == 0:
            return None
        offset = self._pointer(pointer, WNV_QUADTREE_DATA_SIZE, "quadtree leaf")
        if offset in self.quadtree_data_cache:
            return self.quadtree_data_cache[offset]
        cover_start, metadata_02, metadata_03, polygon_pointer, cover_pointer, polygon_count, cover_count = (
            struct.unpack_from("<HBBIIHH", self.data, offset)
        )
        polygon_offset = self._array_offset(polygon_pointer, polygon_count, 2, "quadtree polygon IDs")
        cover_offset = self._array_offset(
            cover_pointer,
            cover_count,
            WNV_COVER_POINT_SIZE,
            "quadtree cover points",
        )
        polygon_ids = (
            []
            if polygon_offset is None
            else list(struct.unpack_from(f"<{polygon_count}H", self.data, polygon_offset))
        )
        cover_points = (
            []
            if cover_offset is None
            else [
                WnvCoverPoint.from_bytes(self.data, cover_offset + index * WNV_COVER_POINT_SIZE)
                for index in range(cover_count)
            ]
        )
        result = WnvQuadTreeData(
            cover_start,
            metadata_02,
            metadata_03,
            polygon_ids,
            cover_points,
            offset,
            polygon_offset,
            cover_offset,
            polygon_count,
            cover_count,
        )
        self.quadtree_data_cache[offset] = result
        return result

    def parse_quadtree(self, pointer: int) -> WnvQuadTree | None:
        if pointer == 0:
            return None
        offset = self._pointer(pointer, WNV_QUADTREE_SIZE, "quadtree node")
        if offset in self.quadtree_cache:
            return self.quadtree_cache[offset]
        if offset in self.visiting:
            raise ValueError("cyclic WNV quadtree pointers are not supported")
        self.visiting.add(offset)
        data_pointer, *child_pointers = struct.unpack_from("<5I", self.data, offset + 44)
        data = self.parse_quadtree_data(data_pointer)
        children = [self.parse_quadtree(child_pointer) for child_pointer in child_pointers]
        node = WnvQuadTree(
            WnvVector4.from_bytes(self.data, offset),
            WnvVector4.from_bytes(self.data, offset + 16),
            WnvAabb.from_bytes(self.data, offset + 32),
            data,
            children,
            offset,
            data is not None,
            tuple(child is not None for child in children),
        )
        self.quadtree_cache[offset] = node
        self.visiting.remove(offset)
        return node


@dataclass(slots=True)
class WnvDocument:
    transform: WnvMatrix
    extents: WnvVector4
    flags: WnvFlags | int
    metadata_54: int
    metadata_56: int
    metadata_5c: int
    indices: list[int]
    vertices: list[WnvVertex]
    edges: list[WnvEdge]
    polygons: list[WnvPolygon]
    quadtree: WnvQuadTree | None
    metadata_74: int
    metadata_tail: list[int]
    resource: Rsc5Resource
    name: str = "navmesh.wnv"
    source_path: str = ""
    _vertices_offset: int | None = field(default=None, repr=False, compare=False)
    _indices_offset: int | None = field(default=None, repr=False, compare=False)
    _edges_offset: int | None = field(default=None, repr=False, compare=False)
    _polygons_offset: int | None = field(default=None, repr=False, compare=False)
    _vertex_count: int = field(default=0, repr=False, compare=False)
    _index_count: int = field(default=0, repr=False, compare=False)
    _polygon_count: int = field(default=0, repr=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.metadata_tail) != 5:
            raise ValueError("WNV header metadata requires exactly five values")

    @classmethod
    def from_path(cls, path: str | Path) -> "WnvDocument":
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name)
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "navmesh.wnv") -> "WnvDocument":
        resource = Rsc5Resource.from_bytes(data)
        if resource.version != WNV_RESOURCE_VERSION:
            raise ValueError(f"unsupported WNV resource version: {resource.version:#x}")
        if resource.physical_data:
            raise ValueError("WNV resources with physical allocations are not supported")
        virtual = resource.virtual_data
        if len(virtual) < WNV_HEADER_SIZE:
            raise ValueError("truncated WNV navmesh header")

        parser = _WnvParser(virtual)
        flags = struct.unpack_from("<I", virtual, 0x50)[0]
        metadata_54, metadata_56 = struct.unpack_from("<2H", virtual, 0x54)
        vertices_pointer = struct.unpack_from("<I", virtual, 0x58)[0]
        metadata_5c = struct.unpack_from("<I", virtual, 0x5C)[0]
        indices_pointer, edges_pointer, index_count, polygons_pointer, quadtree_pointer = struct.unpack_from(
            "<5I", virtual, 0x60
        )
        metadata_74, vertex_count, polygon_count = struct.unpack_from("<3I", virtual, 0x74)
        metadata_tail = list(struct.unpack_from("<5I", virtual, 0x80))

        vertices_offset = parser._array_offset(
            vertices_pointer,
            vertex_count,
            WNV_VERTEX_SIZE,
            "vertex array",
        )
        indices_offset = parser._array_offset(indices_pointer, index_count, 2, "index array")
        edges_offset = parser._array_offset(edges_pointer, index_count, WNV_EDGE_SIZE, "edge array")
        polygons_offset = parser._array_offset(
            polygons_pointer,
            polygon_count,
            WNV_POLYGON_SIZE,
            "polygon array",
        )
        vertices = (
            []
            if vertices_offset is None
            else [
                WnvVertex.from_bytes(virtual, vertices_offset + index * WNV_VERTEX_SIZE)
                for index in range(vertex_count)
            ]
        )
        indices = (
            []
            if indices_offset is None
            else list(struct.unpack_from(f"<{index_count}H", virtual, indices_offset))
        )
        edges = (
            []
            if edges_offset is None
            else [
                WnvEdge.from_bytes(virtual, edges_offset + index * WNV_EDGE_SIZE)
                for index in range(index_count)
            ]
        )
        polygons = (
            []
            if polygons_offset is None
            else [
                WnvPolygon.from_bytes(virtual, polygons_offset + index * WNV_POLYGON_SIZE)
                for index in range(polygon_count)
            ]
        )
        quadtree = parser.parse_quadtree(quadtree_pointer)

        document = cls(
            WnvMatrix.from_bytes(virtual),
            WnvVector4.from_bytes(virtual, 0x40),
            WnvFlags(flags),
            metadata_54,
            metadata_56,
            metadata_5c,
            indices,
            vertices,
            edges,
            polygons,
            quadtree,
            metadata_74,
            metadata_tail,
            resource,
            name,
            _vertices_offset=vertices_offset,
            _indices_offset=indices_offset,
            _edges_offset=edges_offset,
            _polygons_offset=polygons_offset,
            _vertex_count=vertex_count,
            _index_count=index_count,
            _polygon_count=polygon_count,
        )
        document._validate_references()
        return document

    @property
    def aabb_minimum(self) -> WnvVector3:
        if self.quadtree is not None:
            return self.quadtree.aabb_minimum.xyz
        return WnvVector3(-self.extents.x * 0.5, -self.extents.y * 0.5, -self.extents.z * 0.5)

    @property
    def aabb_maximum(self) -> WnvVector3:
        if self.quadtree is not None:
            return self.quadtree.aabb_maximum.xyz
        return WnvVector3(self.extents.x * 0.5, self.extents.y * 0.5, self.extents.z * 0.5)

    @property
    def decoded_vertices(self) -> list[WnvVector3]:
        minimum = self.aabb_minimum
        return [vertex.decode(minimum, self.extents) for vertex in self.vertices]

    def polygon_vertex_indices(self, polygon: WnvPolygon | int) -> tuple[int, ...]:
        value = self.polygons[polygon] if isinstance(polygon, int) else polygon
        return value.vertex_indices(self.indices)

    def polygon_vertices(self, polygon: WnvPolygon | int) -> tuple[WnvVector3, ...]:
        minimum = self.aabb_minimum
        return tuple(
            self.vertices[index].decode(minimum, self.extents)
            for index in self.polygon_vertex_indices(polygon)
        )

    def iter_quadtree(self) -> Iterator[WnvQuadTree]:
        if self.quadtree is not None:
            yield from self.quadtree

    def _validate_references(self) -> None:
        if len(self.edges) != len(self.indices):
            raise ValueError("WNV edge and index counts do not match")
        for index, vertex_id in enumerate(self.indices):
            if vertex_id >= len(self.vertices):
                raise ValueError(f"WNV index {index} references a missing vertex")
        for index, polygon in enumerate(self.polygons):
            if polygon.index_start + polygon.index_count > len(self.indices):
                raise ValueError(f"WNV polygon {index} index range exceeds the index array")
        for node in self.iter_quadtree():
            if node.data is None:
                continue
            for polygon_id in node.data.polygon_ids:
                if polygon_id >= len(self.polygons):
                    raise ValueError("WNV quadtree leaf references a missing polygon")

    def to_bytes(self) -> bytes:
        if len(self.vertices) != self._vertex_count:
            raise ValueError("WNV editing cannot change the vertex count")
        if len(self.indices) != self._index_count:
            raise ValueError("WNV editing cannot change the index count")
        if len(self.edges) != self._index_count:
            raise ValueError("WNV editing cannot change the edge count")
        if len(self.polygons) != self._polygon_count:
            raise ValueError("WNV editing cannot change the polygon count")
        if len(self.metadata_tail) != 5:
            raise ValueError("WNV header metadata requires exactly five values")
        self._validate_references()

        output = bytearray(self.resource.virtual_data)
        output[0:64] = self.transform.to_bytes()
        output[0x40:0x50] = self.extents.to_bytes()
        _require_uint(int(self.flags), 32, "WNV flags")
        _require_uint(self.metadata_54, 16, "WNV header metadata 54")
        _require_uint(self.metadata_56, 16, "WNV header metadata 56")
        _require_uint(self.metadata_5c, 32, "WNV header metadata 5C")
        _require_uint(self.metadata_74, 32, "WNV header metadata 74")
        struct.pack_into("<I2H", output, 0x50, int(self.flags), self.metadata_54, self.metadata_56)
        struct.pack_into("<I", output, 0x5C, self.metadata_5c)
        struct.pack_into("<I", output, 0x74, self.metadata_74)
        for index, value in enumerate(self.metadata_tail):
            _require_uint(value, 32, f"WNV header metadata {0x80 + index * 4:02X}")
        struct.pack_into("<5I", output, 0x80, *self.metadata_tail)

        if self._vertices_offset is not None:
            for index, vertex in enumerate(self.vertices):
                start = self._vertices_offset + index * WNV_VERTEX_SIZE
                output[start : start + WNV_VERTEX_SIZE] = vertex.to_bytes()
        if self._indices_offset is not None:
            for index, vertex_id in enumerate(self.indices):
                _require_uint(vertex_id, 16, "WNV vertex index")
                struct.pack_into("<H", output, self._indices_offset + index * 2, vertex_id)
        if self._edges_offset is not None:
            for index, edge in enumerate(self.edges):
                start = self._edges_offset + index * WNV_EDGE_SIZE
                output[start : start + WNV_EDGE_SIZE] = edge.to_bytes()
        if self._polygons_offset is not None:
            for index, polygon in enumerate(self.polygons):
                start = self._polygons_offset + index * WNV_POLYGON_SIZE
                output[start : start + WNV_POLYGON_SIZE] = polygon.to_bytes()
        if self.quadtree is not None:
            self.quadtree._write(output, set())
        return self.resource.to_bytes(virtual_data=bytes(output))

    def save(self, path: str | Path) -> None:
        atomic_write(path, self.to_bytes())


def load_wnv(source: str | Path | bytes | BinaryIO) -> WnvDocument:
    if isinstance(source, (str, Path)):
        return WnvDocument.from_path(source)
    if isinstance(source, bytes):
        return WnvDocument.from_bytes(source)
    return WnvDocument.from_bytes(source.read())


__all__ = [
    "WNV_AABB_SCALE", "WNV_COVER_POINT_SIZE", "WNV_EDGE_SIZE", "WNV_HEADER_SIZE",
    "WNV_POLYGON_SIZE", "WNV_QUADTREE_DATA_SIZE", "WNV_QUADTREE_SIZE",
    "WNV_QUANTIZED_SCALE", "WNV_RESOURCE_VERSION", "WNV_VERTEX_SIZE", "WnvAabb",
    "WnvCoverPoint", "WnvDocument", "WnvEdge", "WnvEdgeFlags", "WnvFlags", "WnvMatrix",
    "WnvPolygon", "WnvPolygonFlags", "WnvQuadTree", "WnvQuadTreeData", "WnvVector3",
    "WnvVector4", "WnvVertex", "load_wnv",
]
