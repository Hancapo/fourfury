from __future__ import annotations

import json
import unittest

from fourfury import (
    PathEdge,
    PathGraph,
    PathNode,
    PathNodeId,
    PathNodeKind,
    PathSourceMetadata,
    combine_path_graphs,
)


class PathGraphTests(unittest.TestCase):
    def test_indexes_nodes_and_directed_edges(self) -> None:
        first = PathNode(PathNodeId(1, 10), (1, 2, 3), PathNodeKind.VEHICLE)
        second = PathNode(PathNodeId(1, 11), (4, 5, 6), PathNodeKind.PEDESTRIAN)
        external = PathNodeId(2, 20)
        local_edge = PathEdge(first.id, second.id, length=5, cost=6)
        external_edge = PathEdge(first.id, external)

        graph = PathGraph("sector", (first, second), (local_edge, external_edge))

        self.assertIs(graph.find_node((1, 10)), first)
        self.assertEqual(tuple(graph.iter_nodes("pedestrian")), (second,))
        self.assertEqual(graph.outgoing_edges(first.id), (local_edge, external_edge))
        self.assertEqual(graph.incoming_edges(second.id), (local_edge,))
        self.assertEqual(graph.unresolved_targets, (external,))

    def test_serializes_to_stable_primitive_data(self) -> None:
        metadata = PathSourceMetadata("nod", (("flags", 0x1234), ("reserved", 0)))
        node = PathNode(
            PathNodeId(3, 7),
            (1.25, 2.5, 5.0),
            PathNodeKind.VEHICLE,
            width=4,
            traits=frozenset({"intersection", "water"}),
            source_metadata=metadata,
        )
        graph = PathGraph("nodes3", (node,), (), source_format="nod", source_path="nodes3.nod")

        exported = json.loads(graph.to_json(indent=None))

        self.assertEqual(exported["schema"], "fourfury.path-graph")
        self.assertEqual(exported["version"], 1)
        self.assertEqual(exported["nodes"][0]["id"], {"area_id": 3, "node_id": 7})
        self.assertEqual(exported["nodes"][0]["traits"], ["intersection", "water"])
        self.assertEqual(exported["nodes"][0]["source_metadata"]["values"]["flags"], 0x1234)

    def test_combines_partial_graphs_and_resolves_external_targets(self) -> None:
        first = PathNode(PathNodeId(1, 0), (0, 0, 0))
        second = PathNode(PathNodeId(2, 0), (10, 0, 0))
        edge = PathEdge(first.id, second.id)

        combined = combine_path_graphs(
            (
                PathGraph("first", (first,), (edge,), source_format="nod"),
                PathGraph("second", (second,), (), source_format="nod"),
            ),
            name="city",
        )

        self.assertEqual(combined.name, "city")
        self.assertEqual(combined.source_format, "nod")
        self.assertEqual(combined.unresolved_targets, ())
        self.assertIs(combined.find_node(second.id), second)

    def test_rejects_duplicate_node_ids_and_missing_edge_sources(self) -> None:
        node = PathNode(PathNodeId(1, 0), (0, 0, 0))
        with self.assertRaisesRegex(ValueError, "identifiers must be unique"):
            PathGraph("duplicate", (node, node), ())
        with self.assertRaisesRegex(ValueError, "edge source"):
            PathGraph("missing", (), (PathEdge(node.id, PathNodeId(2, 0)),))


if __name__ == "__main__":
    unittest.main()
