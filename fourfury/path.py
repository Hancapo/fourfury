from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Iterable, Iterator, TypeAlias

from ._utils import atomic_write


PathVector3: TypeAlias = tuple[float, float, float]
PathMetadataValue: TypeAlias = str | int | float | bool | None


class PathNodeKind(StrEnum):
    """Target-independent navigation node category."""

    VEHICLE = "vehicle"
    PEDESTRIAN = "pedestrian"
    OTHER = "other"


@dataclass(frozen=True, slots=True, order=True)
class PathNodeId:
    """Stable source identifier for a node in a partitioned path graph."""

    area_id: int
    node_id: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "area_id", int(self.area_id))
        object.__setattr__(self, "node_id", int(self.node_id))

    @classmethod
    def coerce(cls, value: PathNodeKey) -> "PathNodeId":
        if isinstance(value, cls):
            return value
        return cls(*value)

    def to_dict(self) -> dict[str, int]:
        return {"area_id": self.area_id, "node_id": self.node_id}


PathNodeKey: TypeAlias = PathNodeId | tuple[int, int]


@dataclass(frozen=True, slots=True)
class PathSourceMetadata:
    """Optional format-specific scalar values retained beside neutral data."""

    format: str
    values: tuple[tuple[str, PathMetadataValue], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "format", str(self.format))
        object.__setattr__(
            self,
            "values",
            tuple((str(name), value) for name, value in self.values),
        )
        names = [name for name, _ in self.values]
        if len(set(names)) != len(names):
            raise ValueError("path source metadata names must be unique")

    def get(self, name: str, default: PathMetadataValue = None) -> PathMetadataValue:
        return next((value for key, value in self.values if key == name), default)

    def to_dict(self) -> dict[str, object]:
        return {"format": self.format, "values": dict(self.values)}


@dataclass(frozen=True, slots=True)
class PathNode:
    """One node in a target-independent navigation graph."""

    id: PathNodeId
    position: PathVector3
    kind: PathNodeKind = PathNodeKind.OTHER
    width: float | None = None
    traits: frozenset[str] = frozenset()
    source_metadata: PathSourceMetadata | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", PathNodeId.coerce(self.id))
        if len(self.position) != 3:
            raise ValueError("path node positions must contain three components")
        object.__setattr__(self, "position", tuple(float(value) for value in self.position))
        object.__setattr__(self, "kind", PathNodeKind(self.kind))
        object.__setattr__(self, "width", None if self.width is None else float(self.width))
        object.__setattr__(self, "traits", frozenset(str(value) for value in self.traits))

    def to_dict(self) -> dict[str, object]:
        output: dict[str, object] = {
            "id": self.id.to_dict(),
            "position": list(self.position),
            "kind": self.kind.value,
            "width": self.width,
            "traits": sorted(self.traits),
        }
        if self.source_metadata is not None:
            output["source_metadata"] = self.source_metadata.to_dict()
        return output


@dataclass(frozen=True, slots=True)
class PathEdge:
    """One directed connection between two navigation nodes."""

    source: PathNodeId
    target: PathNodeId
    length: float | None = None
    cost: float | None = None
    traits: frozenset[str] = frozenset()
    source_metadata: PathSourceMetadata | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", PathNodeId.coerce(self.source))
        object.__setattr__(self, "target", PathNodeId.coerce(self.target))
        object.__setattr__(self, "length", None if self.length is None else float(self.length))
        object.__setattr__(self, "cost", None if self.cost is None else float(self.cost))
        object.__setattr__(self, "traits", frozenset(str(value) for value in self.traits))

    def to_dict(self) -> dict[str, object]:
        output: dict[str, object] = {
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "length": self.length,
            "cost": self.cost,
            "traits": sorted(self.traits),
        }
        if self.source_metadata is not None:
            output["source_metadata"] = self.source_metadata.to_dict()
        return output


@dataclass(frozen=True, slots=True)
class PathGraph:
    """Immutable, target-independent snapshot of a navigation graph."""

    name: str
    nodes: tuple[PathNode, ...]
    edges: tuple[PathEdge, ...]
    source_format: str = ""
    source_path: str = ""
    _node_index: dict[PathNodeId, PathNode] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _outgoing_index: dict[PathNodeId, tuple[PathEdge, ...]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _incoming_index: dict[PathNodeId, tuple[PathEdge, ...]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "source_format", str(self.source_format))
        object.__setattr__(self, "source_path", str(self.source_path))

        node_index = {node.id: node for node in self.nodes}
        if len(node_index) != len(self.nodes):
            raise ValueError("path graph node identifiers must be unique")

        outgoing: dict[PathNodeId, list[PathEdge]] = {}
        incoming: dict[PathNodeId, list[PathEdge]] = {}
        for edge in self.edges:
            if edge.source not in node_index:
                raise ValueError(f"path edge source {edge.source!r} is not present in the graph")
            outgoing.setdefault(edge.source, []).append(edge)
            incoming.setdefault(edge.target, []).append(edge)

        object.__setattr__(self, "_node_index", node_index)
        object.__setattr__(
            self, "_outgoing_index", {key: tuple(value) for key, value in outgoing.items()}
        )
        object.__setattr__(
            self, "_incoming_index", {key: tuple(value) for key, value in incoming.items()}
        )

    def __len__(self) -> int:
        return len(self.nodes)

    def __iter__(self) -> Iterator[PathNode]:
        return iter(self.nodes)

    def find_node(self, value: PathNodeKey) -> PathNode | None:
        return self._node_index.get(PathNodeId.coerce(value))

    def iter_nodes(self, kind: PathNodeKind | str | None = None) -> Iterator[PathNode]:
        if kind is None:
            yield from self.nodes
            return
        selected = PathNodeKind(kind)
        yield from (node for node in self.nodes if node.kind is selected)

    def outgoing_edges(self, value: PathNodeKey) -> tuple[PathEdge, ...]:
        return self._outgoing_index.get(PathNodeId.coerce(value), ())

    def incoming_edges(self, value: PathNodeKey) -> tuple[PathEdge, ...]:
        return self._incoming_index.get(PathNodeId.coerce(value), ())

    @property
    def unresolved_targets(self) -> tuple[PathNodeId, ...]:
        return tuple(
            dict.fromkeys(edge.target for edge in self.edges if edge.target not in self._node_index)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "fourfury.path-graph",
            "version": 1,
            "name": self.name,
            "source_format": self.source_format,
            "source_path": self.source_path,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)

    def save_json(self, destination: str | Path, *, indent: int | None = 2) -> Path:
        target = Path(destination)
        atomic_write(target, (self.to_json(indent=indent) + "\n").encode("utf-8"))
        return target


def combine_path_graphs(
    graphs: Iterable[PathGraph], *, name: str = "combined"
) -> PathGraph:
    """Combine partial graph snapshots without changing their identifiers."""

    items = tuple(graphs)
    source_formats = {graph.source_format for graph in items if graph.source_format}
    return PathGraph(
        name=name,
        nodes=tuple(node for graph in items for node in graph.nodes),
        edges=tuple(edge for graph in items for edge in graph.edges),
        source_format=next(iter(source_formats)) if len(source_formats) == 1 else "",
    )


__all__ = [
    "PathEdge",
    "PathGraph",
    "PathMetadataValue",
    "PathNode",
    "PathNodeId",
    "PathNodeKind",
    "PathNodeKey",
    "PathSourceMetadata",
    "PathVector3",
    "combine_path_graphs",
]
