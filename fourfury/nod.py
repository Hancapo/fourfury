from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, Literal

from ._utils import atomic_write
from .path import (
    PathEdge,
    PathGraph,
    PathNode,
    PathNodeId,
    PathNodeKind,
    PathSourceMetadata,
    combine_path_graphs,
)


NOD_HEADER_SIZE = 16
NOD_NODE_SIZE = 32
NOD_LINK_SIZE = 8
NOD_XY_SCALE = 8.0
NOD_Z_SCALE = 64.0
NOD_PATH_WIDTH_SCALE = 8.0
NOD_HEURISTIC_SENTINEL = 0x7FFE
NOD_LINK_COUNT_SHIFT = 16
NOD_LINK_COUNT_MASK = 0x000F0000

_HEADER = struct.Struct("<4I")
_NODE = struct.Struct("<IIHHIHHhhhBBI")
_LINK = struct.Struct("<HHBBH")


class NodNodeKind(IntEnum):
    """The node partition selected by the NOD header."""

    VEHICLE = 0
    PEDESTRIAN = 1


class NodNodeFlags(IntFlag):
    """Node flags whose meanings are supported by stock-file evidence.

    GTA IV leaves several bits without reliable public documentation. Those
    bits remain available through :attr:`NodNode.flags` and
    :attr:`NodNode.unresolved_flags` instead of being given speculative names.
    """

    REGULAR_SPEED = 1 << 20
    SCRIPTED_DRIVERS_ONLY = 1 << 21
    INTERSECTION = 1 << 22
    BOAT_MOVEMENT = 1 << 25


NodFlagConfidence = Literal["verified", "inferred", "unresolved"]


@dataclass(frozen=True, slots=True)
class NodNodeFlagInfo:
    flag: NodNodeFlags
    effect: str
    confidence: NodFlagConfidence


NOD_NODE_FLAG_INFO = (
    NodNodeFlagInfo(
        NodNodeFlags.REGULAR_SPEED,
        "Uses regular traffic speed instead of the slow fallback speed.",
        "inferred",
    ),
    NodNodeFlagInfo(
        NodNodeFlags.SCRIPTED_DRIVERS_ONLY,
        "Allows scripted drivers but suppresses ordinary traffic spawning.",
        "inferred",
    ),
    NodNodeFlagInfo(
        NodNodeFlags.INTERSECTION,
        "Marks a node participating in an intersection or road junction.",
        "inferred",
    ),
    NodNodeFlagInfo(
        NodNodeFlags.BOAT_MOVEMENT,
        "Marks a water route used for boat movement.",
        "verified",
    ),
)

_NOD_NAMED_FLAG_MASK = sum(int(info.flag) for info in NOD_NODE_FLAG_INFO)


def explain_node_flags(flags: NodNodeFlags | int) -> tuple[NodNodeFlagInfo, ...]:
    """Describe active behavior bits and the confidence of each meaning."""

    value = int(flags) & ~NOD_LINK_COUNT_MASK
    details = [info for info in NOD_NODE_FLAG_INFO if value & int(info.flag)]
    extra = value & ~_NOD_NAMED_FLAG_MASK
    if extra:
        details.append(
            NodNodeFlagInfo(
                NodNodeFlags(extra),
                "Preserved behavior bits whose runtime effect has not been identified.",
                "unresolved",
            )
        )
    return tuple(details)


@dataclass(slots=True)
class NodVector3:
    """World-space position decoded from GTA IV's fixed-point coordinates."""

    x: float
    y: float
    z: float

    @classmethod
    def from_raw(cls, x: int, y: int, z: int) -> "NodVector3":
        return cls(x / NOD_XY_SCALE, y / NOD_XY_SCALE, z / NOD_Z_SCALE)

    def to_raw(self) -> tuple[int, int, int]:
        values = (
            round(self.x * NOD_XY_SCALE),
            round(self.y * NOD_XY_SCALE),
            round(self.z * NOD_Z_SCALE),
        )
        if any(value < -0x8000 or value > 0x7FFF for value in values):
            raise ValueError("NOD position exceeds the signed 16-bit fixed-point range")
        return values


@dataclass(slots=True)
class NodLink:
    """One directed edge in the path graph."""

    target_area_id: int
    target_node_id: int
    length: int
    pathfinding_cost: int
    traffic_flags: int = 0

    @property
    def target_key(self) -> tuple[int, int]:
        return self.target_area_id, self.target_node_id

    def resolve(self, document: "NodDocument") -> "NodNode | None":
        """Resolve an in-file destination; cross-sector links return ``None``."""

        return document.find_node(self.target_area_id, self.target_node_id)

    def _validate(self) -> None:
        _require_uint(self.target_area_id, 16, "NOD link target area ID")
        _require_uint(self.target_node_id, 16, "NOD link target node ID")
        _require_uint(self.length, 8, "NOD link length")
        _require_uint(self.pathfinding_cost, 8, "NOD link pathfinding cost")
        _require_uint(self.traffic_flags, 16, "NOD link traffic flags")


@dataclass(slots=True)
class NodNode:
    """A vehicle or pedestrian path node.

    ``runtime_address`` and ``source_path_value`` are compiler-originated
    metadata. The former changes between game builds; the latter is copied
    from the tenth value of the source ``vnod`` IPL row. Both are retained so
    edits remain lossless even though the runtime does not document them.
    """

    runtime_address: int
    reserved: int
    area_id: int
    node_id: int
    source_path_value: int
    heuristic_cost: int
    link_start: int
    position: NodVector3
    path_width_code: int
    path_type: int
    flags: NodNodeFlags | int
    kind: NodNodeKind = field(default=NodNodeKind.VEHICLE, compare=False)
    _document: "NodDocument | None" = field(default=None, repr=False, compare=False)

    @property
    def key(self) -> tuple[int, int]:
        return self.area_id, self.node_id

    @property
    def path_width(self) -> float:
        return self.path_width_code / NOD_PATH_WIDTH_SCALE

    @path_width.setter
    def path_width(self, value: float) -> None:
        encoded = round(value * NOD_PATH_WIDTH_SCALE)
        _require_uint(encoded, 8, "NOD path width")
        self.path_width_code = encoded

    @property
    def link_count(self) -> int:
        return (int(self.flags) & NOD_LINK_COUNT_MASK) >> NOD_LINK_COUNT_SHIFT

    @property
    def outgoing_links(self) -> tuple[NodLink, ...]:
        if self._document is None:
            return ()
        end = self.link_start + self.link_count
        return tuple(self._document.links[self.link_start:end])

    @property
    def is_vehicle(self) -> bool:
        return self.kind is NodNodeKind.VEHICLE

    @property
    def is_pedestrian(self) -> bool:
        return self.kind is NodNodeKind.PEDESTRIAN

    @property
    def is_boat(self) -> bool:
        return self.path_type == 1 or bool(int(self.flags) & NodNodeFlags.BOAT_MOVEMENT)

    @property
    def is_intersection(self) -> bool:
        return bool(int(self.flags) & NodNodeFlags.INTERSECTION)

    @property
    def behavior_flags(self) -> NodNodeFlags:
        """Return all node flags except the embedded adjacency count."""

        return NodNodeFlags(int(self.flags) & ~NOD_LINK_COUNT_MASK)

    @property
    def flag_info(self) -> tuple[NodNodeFlagInfo, ...]:
        """Describe active behavior flags without including the link count."""

        return explain_node_flags(self.flags)

    @property
    def unresolved_flags(self) -> int:
        """Return preserved behavior bits without a verified public meaning."""

        return int(self.behavior_flags) & ~_NOD_NAMED_FLAG_MASK

    def set_link_count(self, count: int) -> None:
        """Update the four-bit adjacency count without changing behavior flags."""

        if not 0 <= count <= 15:
            raise ValueError("NOD node link count must be between 0 and 15")
        self.flags = NodNodeFlags(
            (int(self.flags) & ~NOD_LINK_COUNT_MASK) | (count << NOD_LINK_COUNT_SHIFT)
        )

    def _validate(self) -> None:
        _require_uint(self.runtime_address, 32, "NOD runtime address")
        _require_uint(self.reserved, 32, "NOD reserved value")
        _require_uint(self.area_id, 16, "NOD area ID")
        _require_uint(self.node_id, 16, "NOD node ID")
        _require_uint(self.source_path_value, 32, "NOD source path value")
        _require_uint(self.heuristic_cost, 16, "NOD heuristic cost")
        _require_uint(self.link_start, 16, "NOD link start")
        _require_uint(self.path_width_code, 8, "NOD path width code")
        _require_uint(self.path_type, 8, "NOD path type")
        _require_uint(int(self.flags), 32, "NOD node flags")
        self.position.to_raw()


@dataclass(slots=True)
class NodDocument:
    """A GTA IV sector path graph stored in a ``.nod`` file."""

    nodes: list[NodNode] = field(default_factory=list)
    links: list[NodLink] = field(default_factory=list)
    vehicle_node_count: int = 0
    name: str = "nodes.nod"
    source_path: str = ""
    _index: dict[tuple[int, int], NodNode] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        self._bind_nodes()

    @classmethod
    def empty(cls, name: str = "nodes.nod") -> "NodDocument":
        return cls(name=name if name.lower().endswith(".nod") else f"{name}.nod")

    @classmethod
    def from_path(cls, path: str | Path) -> "NodDocument":
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name)
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "nodes.nod") -> "NodDocument":
        if len(data) < NOD_HEADER_SIZE:
            raise ValueError("truncated NOD header")
        node_count, vehicle_count, pedestrian_count, link_count = _HEADER.unpack_from(data)
        if node_count != vehicle_count + pedestrian_count:
            raise ValueError("NOD vehicle and pedestrian counts do not match the node count")
        expected_size = NOD_HEADER_SIZE + node_count * NOD_NODE_SIZE + link_count * NOD_LINK_SIZE
        if len(data) != expected_size:
            qualifier = "truncated" if len(data) < expected_size else "has trailing data"
            raise ValueError(f"NOD file {qualifier}: expected {expected_size} bytes, got {len(data)}")

        nodes: list[NodNode] = []
        offset = NOD_HEADER_SIZE
        for index in range(node_count):
            (
                runtime_address,
                reserved,
                area_id,
                node_id,
                source_path_value,
                heuristic_cost,
                link_start,
                x,
                y,
                z,
                path_width_code,
                path_type,
                flags,
            ) = _NODE.unpack_from(data, offset)
            nodes.append(
                NodNode(
                    runtime_address,
                    reserved,
                    area_id,
                    node_id,
                    source_path_value,
                    heuristic_cost,
                    link_start,
                    NodVector3.from_raw(x, y, z),
                    path_width_code,
                    path_type,
                    NodNodeFlags(flags),
                    NodNodeKind.VEHICLE if index < vehicle_count else NodNodeKind.PEDESTRIAN,
                )
            )
            offset += NOD_NODE_SIZE

        links = [NodLink(*_LINK.unpack_from(data, offset + index * NOD_LINK_SIZE)) for index in range(link_count)]
        document = cls(nodes, links, vehicle_count, name)
        document.validate()
        return document

    @property
    def pedestrian_node_count(self) -> int:
        return len(self.nodes) - self.vehicle_node_count

    @property
    def vehicle_nodes(self) -> tuple[NodNode, ...]:
        return tuple(self.nodes[: self.vehicle_node_count])

    @property
    def pedestrian_nodes(self) -> tuple[NodNode, ...]:
        return tuple(self.nodes[self.vehicle_node_count :])

    def __len__(self) -> int:
        return len(self.nodes)

    def __iter__(self) -> Iterator[NodNode]:
        return iter(self.nodes)

    def _bind_nodes(self) -> None:
        self._index.clear()
        for index, node in enumerate(self.nodes):
            node.kind = (
                NodNodeKind.VEHICLE if index < self.vehicle_node_count else NodNodeKind.PEDESTRIAN
            )
            node._document = self
            self._index[node.key] = node

    def find_node(self, area_id: int, node_id: int) -> NodNode | None:
        return self._index.get((area_id, node_id))

    def iter_path_nodes(
        self, *, include_source_metadata: bool = False
    ) -> Iterator[PathNode]:
        """Yield target-independent node snapshots without copying the graph."""

        for node in self.nodes:
            metadata = None
            if include_source_metadata:
                metadata = PathSourceMetadata(
                    "nod",
                    (
                        ("runtime_address", node.runtime_address),
                        ("reserved", node.reserved),
                        ("source_path_value", node.source_path_value),
                        ("heuristic_cost", node.heuristic_cost),
                        ("link_start", node.link_start),
                        ("link_count", node.link_count),
                        ("path_width_code", node.path_width_code),
                        ("path_type", node.path_type),
                        ("flags", int(node.flags)),
                        ("unresolved_flags", node.unresolved_flags),
                    ),
                )
            yield PathNode(
                PathNodeId(node.area_id, node.node_id),
                (node.position.x, node.position.y, node.position.z),
                (
                    PathNodeKind.PEDESTRIAN
                    if node.is_pedestrian
                    else PathNodeKind.VEHICLE
                ),
                width=node.path_width,
                traits=_path_node_traits(node),
                source_metadata=metadata,
            )

    def iter_path_edges(
        self, *, include_source_metadata: bool = False
    ) -> Iterator[PathEdge]:
        """Yield target-independent directed edges, including external targets."""

        for node in self.nodes:
            source = PathNodeId(node.area_id, node.node_id)
            end = node.link_start + node.link_count
            for link_index in range(node.link_start, end):
                link = self.links[link_index]
                metadata = None
                if include_source_metadata:
                    metadata = PathSourceMetadata(
                        "nod",
                        (
                            ("link_index", link_index),
                            ("length", link.length),
                            ("pathfinding_cost", link.pathfinding_cost),
                            ("traffic_flags", link.traffic_flags),
                        ),
                    )
                yield PathEdge(
                    source,
                    PathNodeId(link.target_area_id, link.target_node_id),
                    length=link.length,
                    cost=link.pathfinding_cost,
                    source_metadata=metadata,
                )

    def to_path_graph(self, *, include_source_metadata: bool = False) -> PathGraph:
        """Project this NOD sector into an immutable, target-independent graph."""

        self.validate()
        return PathGraph(
            name=Path(self.name).stem,
            nodes=tuple(
                self.iter_path_nodes(
                    include_source_metadata=include_source_metadata
                )
            ),
            edges=tuple(
                self.iter_path_edges(
                    include_source_metadata=include_source_metadata
                )
            ),
            source_format="nod",
            source_path=self.source_path,
        )

    def validate(self) -> None:
        if not 0 <= self.vehicle_node_count <= len(self.nodes):
            raise ValueError("NOD vehicle node count exceeds the node count")
        if len(self.nodes) > 0xFFFFFFFF or len(self.links) > 0xFFFFFFFF:
            raise ValueError("NOD node and link counts must fit in 32 bits")
        self._bind_nodes()
        if len(self._index) != len(self.nodes):
            raise ValueError("NOD node area/node identifiers must be unique")

        expected_link_start = 0
        for node in self.nodes:
            node._validate()
            if node.link_start != expected_link_start:
                raise ValueError(
                    f"NOD node {node.area_id}:{node.node_id} starts at link {node.link_start}, "
                    f"expected {expected_link_start}"
                )
            expected_link_start += node.link_count
            if expected_link_start > len(self.links):
                raise ValueError("NOD node adjacency exceeds the link table")
        if expected_link_start != len(self.links):
            raise ValueError("NOD node adjacency does not consume the complete link table")
        for link in self.links:
            link._validate()

    def to_bytes(self) -> bytes:
        self.validate()
        output = bytearray(
            _HEADER.pack(
                len(self.nodes),
                self.vehicle_node_count,
                self.pedestrian_node_count,
                len(self.links),
            )
        )
        for node in self.nodes:
            x, y, z = node.position.to_raw()
            output.extend(
                _NODE.pack(
                    node.runtime_address,
                    node.reserved,
                    node.area_id,
                    node.node_id,
                    node.source_path_value,
                    node.heuristic_cost,
                    node.link_start,
                    x,
                    y,
                    z,
                    node.path_width_code,
                    node.path_type,
                    int(node.flags),
                )
            )
        for link in self.links:
            output.extend(
                _LINK.pack(
                    link.target_area_id,
                    link.target_node_id,
                    link.length,
                    link.pathfinding_cost,
                    link.traffic_flags,
                )
            )
        return bytes(output)

    def save(self, path: str | Path) -> None:
        atomic_write(path, self.to_bytes())


def _require_uint(value: int, bits: int, label: str) -> None:
    if not isinstance(value, int) or not 0 <= value < 1 << bits:
        raise ValueError(f"{label} must fit in {bits} unsigned bits")


def _path_node_traits(node: NodNode) -> frozenset[str]:
    traits: set[str] = set()
    if node.flags & NodNodeFlags.REGULAR_SPEED:
        traits.add("regular_speed")
    if node.flags & NodNodeFlags.SCRIPTED_DRIVERS_ONLY:
        traits.add("scripted_drivers_only")
    if node.is_intersection:
        traits.add("intersection")
    if node.is_boat:
        traits.add("boat")
    return frozenset(traits)


def load_nod(source: str | Path | bytes | BinaryIO) -> NodDocument:
    if isinstance(source, (str, Path)):
        return NodDocument.from_path(source)
    if isinstance(source, bytes):
        return NodDocument.from_bytes(source)
    return NodDocument.from_bytes(source.read())


def load_nod_graph(
    source: str | Path | bytes | BinaryIO,
    *,
    include_source_metadata: bool = False,
) -> PathGraph:
    """Load a NOD source directly into the neutral path graph model."""

    return load_nod(source).to_path_graph(
        include_source_metadata=include_source_metadata
    )


def combine_nod_graphs(
    documents: Iterable[NodDocument],
    *,
    name: str = "gtaiv-paths",
    include_source_metadata: bool = False,
) -> PathGraph:
    """Combine NOD sectors and resolve targets present in the supplied set."""

    return combine_path_graphs(
        (
            document.to_path_graph(
                include_source_metadata=include_source_metadata
            )
            for document in documents
        ),
        name=name,
    )


__all__ = [
    "NOD_HEADER_SIZE", "NOD_HEURISTIC_SENTINEL", "NOD_LINK_COUNT_MASK",
    "NOD_LINK_COUNT_SHIFT", "NOD_LINK_SIZE", "NOD_NODE_SIZE", "NOD_PATH_WIDTH_SCALE",
    "NOD_NODE_FLAG_INFO", "NOD_XY_SCALE", "NOD_Z_SCALE", "NodDocument", "NodFlagConfidence",
    "NodLink", "NodNode", "NodNodeFlagInfo", "NodNodeFlags", "NodNodeKind", "NodVector3",
    "combine_nod_graphs", "explain_node_flags", "load_nod", "load_nod_graph",
]
