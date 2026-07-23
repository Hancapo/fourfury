from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator

from .wpl import WplDocument, WplInstance


class WplLodParentScope(str, Enum):
    """The document in which an instance's ``lod_index`` is resolved."""

    LOCAL = "local"
    EXTERNAL = "external"


class WplLodIssueCode(str, Enum):
    """Machine-readable LOD hierarchy validation failures."""

    PARENT_INDEX_OUT_OF_RANGE = "parent_index_out_of_range"
    CYCLE = "cycle"


@dataclass(frozen=True, slots=True)
class WplLodIssue:
    """A malformed parent reference found while resolving a hierarchy."""

    code: WplLodIssueCode
    document: WplDocument = field(repr=False)
    target_document: WplDocument = field(repr=False)
    instance_index: int
    parent_index: int
    scope: WplLodParentScope
    message: str


@dataclass(slots=True, eq=False, repr=False)
class WplLodNode:
    """One WPL instance and its resolved position in the LOD forest."""

    document: WplDocument
    index: int
    instance: WplInstance
    parent_scope: WplLodParentScope | None = None
    parent: WplLodNode | None = field(default=None, init=False)
    depth: int = field(default=0, init=False)
    _children: list[WplLodNode] = field(default_factory=list, init=False, repr=False)

    def __repr__(self) -> str:
        return (
            f"WplLodNode(document={self.document.name!r}, index={self.index}, "
            f"model_hash=0x{self.instance.model_hash:08X}, depth={self.depth})"
        )

    @property
    def parent_index(self) -> int:
        """Return the exact signed index stored in the instance record."""

        return self.instance.lod_index

    @property
    def children(self) -> tuple[WplLodNode, ...]:
        """Return direct children in their original document order."""

        return tuple(self._children)

    @property
    def is_root(self) -> bool:
        """Return whether this node has no resolved parent."""

        return self.parent is None

    @property
    def has_unresolved_parent(self) -> bool:
        """Return whether a stored parent reference failed validation."""

        return self.instance.has_lod_parent and self.parent is None

    @property
    def ancestors(self) -> tuple[WplLodNode, ...]:
        """Return ancestors from the direct parent through the root."""

        result: list[WplLodNode] = []
        current = self.parent
        while current is not None:
            result.append(current)
            current = current.parent
        return tuple(result)

    def iter_descendants(self) -> Iterator[WplLodNode]:
        """Yield all descendants depth-first in document order."""

        stack = list(reversed(self._children))
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node._children))


@dataclass(frozen=True, slots=True)
class WplLodEdge:
    """An explicit, validated parent-to-child LOD relationship."""

    parent: WplLodNode
    child: WplLodNode
    scope: WplLodParentScope


@dataclass(slots=True, repr=False)
class WplLodHierarchy:
    """A validated snapshot of local or streamed WPL LOD parenting."""

    document: WplDocument
    parent_document: WplDocument | None
    nodes: tuple[WplLodNode, ...]
    roots: tuple[WplLodNode, ...]
    edges: tuple[WplLodEdge, ...]
    issues: tuple[WplLodIssue, ...]
    _nodes_by_instance: dict[int, WplLodNode] = field(default_factory=dict, repr=False)
    _nodes_by_document: dict[int, tuple[WplLodNode, ...]] = field(default_factory=dict, repr=False)

    def __repr__(self) -> str:
        parent = self.parent_document.name if self.parent_document is not None else None
        return (
            f"WplLodHierarchy(document={self.document.name!r}, parent_document={parent!r}, "
            f"nodes={len(self.nodes)}, edges={len(self.edges)}, roots={len(self.roots)}, "
            f"issues={len(self.issues)})"
        )

    @classmethod
    def from_document(
        cls,
        document: WplDocument,
        *,
        parent: WplDocument | None = None,
        strict: bool = False,
    ) -> WplLodHierarchy:
        """Build a hierarchy using GTA IV's local/external index semantics."""

        external_parent = parent if parent is not document else None
        documents = (document,) if external_parent is None else (external_parent, document)
        nodes_by_document: dict[int, tuple[WplLodNode, ...]] = {}
        all_nodes: list[WplLodNode] = []
        for current_document in documents:
            document_nodes = tuple(
                WplLodNode(current_document, index, instance)
                for index, instance in enumerate(current_document.instances)
            )
            nodes_by_document[id(current_document)] = document_nodes
            all_nodes.extend(document_nodes)

        relationships: dict[WplLodNode, tuple[WplLodNode, WplLodParentScope]] = {}
        issues: list[WplLodIssue] = []
        for current_document in documents:
            source_nodes = nodes_by_document[id(current_document)]
            is_stream = external_parent is not None and current_document is document
            target_document = external_parent if is_stream else current_document
            assert target_document is not None
            target_nodes = nodes_by_document[id(target_document)]
            scope = WplLodParentScope.EXTERNAL if is_stream else WplLodParentScope.LOCAL
            for node in source_nodes:
                parent_index = node.instance.lod_index
                if parent_index < 0:
                    continue
                node.parent_scope = scope
                if parent_index >= len(target_nodes):
                    issues.append(WplLodIssue(
                        WplLodIssueCode.PARENT_INDEX_OUT_OF_RANGE,
                        current_document,
                        target_document,
                        node.index,
                        parent_index,
                        scope,
                        f"instance {node.index} in {current_document.name!r} references "
                        f"{scope.value} parent {parent_index}, but {target_document.name!r} "
                        f"contains {len(target_nodes)} instances",
                    ))
                    continue
                relationships[node] = (target_nodes[parent_index], scope)

        cycles = _find_cycles(all_nodes, relationships)
        for cycle in cycles:
            description = " -> ".join(
                f"{node.document.name}[{node.index}]" for node in (*cycle, cycle[0])
            )
            first = cycle[0]
            assert first.parent_scope is not None
            issues.append(WplLodIssue(
                WplLodIssueCode.CYCLE,
                first.document,
                relationships[first][0].document,
                first.index,
                first.parent_index,
                first.parent_scope,
                f"LOD parent cycle: {description}",
            ))
            for node in cycle:
                relationships.pop(node, None)

        edges: list[WplLodEdge] = []
        for child, (parent_node, scope) in relationships.items():
            child.parent = parent_node
            parent_node._children.append(child)
            edges.append(WplLodEdge(parent_node, child, scope))

        roots = tuple(node for node in all_nodes if node.parent is None)
        stack = [(root, 0) for root in reversed(roots)]
        while stack:
            node, depth = stack.pop()
            node.depth = depth
            stack.extend((child, depth + 1) for child in reversed(node._children))

        hierarchy = cls(
            document,
            external_parent,
            tuple(all_nodes),
            roots,
            tuple(edges),
            tuple(issues),
            {id(node.instance): node for node in all_nodes},
            nodes_by_document,
        )
        if strict and hierarchy.issues:
            raise WplLodHierarchyError(hierarchy)
        return hierarchy

    def node_for(self, instance: WplInstance) -> WplLodNode:
        """Return the node wrapping ``instance`` or raise ``KeyError``."""

        try:
            return self._nodes_by_instance[id(instance)]
        except KeyError:
            raise KeyError("instance does not belong to this WPL LOD hierarchy") from None

    def node_at(self, index: int, *, document: WplDocument | None = None) -> WplLodNode:
        """Return a node by document-local instance index."""

        owner = self.document if document is None else document
        try:
            nodes = self._nodes_by_document[id(owner)]
        except KeyError:
            raise KeyError("document does not belong to this WPL LOD hierarchy") from None
        return nodes[index]

    def nodes_for(self, document: WplDocument) -> tuple[WplLodNode, ...]:
        """Return all nodes owned by one participating document."""

        try:
            return self._nodes_by_document[id(document)]
        except KeyError:
            raise KeyError("document does not belong to this WPL LOD hierarchy") from None

    def roots_for(self, document: WplDocument) -> tuple[WplLodNode, ...]:
        """Return resolved roots owned by one participating document."""

        return tuple(node for node in self.nodes_for(document) if node.is_root)


class WplLodHierarchyError(ValueError):
    """Raised when strict hierarchy construction finds malformed links."""

    def __init__(self, hierarchy: WplLodHierarchy):
        self.hierarchy = hierarchy
        self.issues = hierarchy.issues
        super().__init__("; ".join(issue.message for issue in self.issues))


def _find_cycles(
    nodes: list[WplLodNode],
    relationships: dict[WplLodNode, tuple[WplLodNode, WplLodParentScope]],
) -> list[tuple[WplLodNode, ...]]:
    """Find cycles in a functional graph without recursion depth limits."""

    state: dict[WplLodNode, int] = {}
    cycles: list[tuple[WplLodNode, ...]] = []
    for start in nodes:
        if state.get(start, 0) != 0:
            continue
        trail: list[WplLodNode] = []
        positions: dict[WplLodNode, int] = {}
        current: WplLodNode | None = start
        while current is not None and state.get(current, 0) == 0:
            state[current] = 1
            positions[current] = len(trail)
            trail.append(current)
            relationship = relationships.get(current)
            current = relationship[0] if relationship is not None else None
        if current is not None and current in positions:
            cycles.append(tuple(trail[positions[current] :]))
        for node in trail:
            state[node] = 2
    return cycles


__all__ = [
    "WplLodEdge", "WplLodHierarchy", "WplLodHierarchyError", "WplLodIssue",
    "WplLodIssueCode", "WplLodNode", "WplLodParentScope",
]
