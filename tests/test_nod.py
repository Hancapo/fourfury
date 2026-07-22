from __future__ import annotations

import io
import struct
import unittest

from fourfury import (
    ImgArchive,
    NOD_HEURISTIC_SENTINEL,
    NodDocument,
    NodNode,
    NodNodeFlags,
    NodNodeKind,
    NodVector3,
    PathNodeId,
    PathNodeKind,
    combine_nod_graphs,
    load_nod,
    load_nod_graph,
)


def _sample_nod() -> bytes:
    node = struct.Struct("<IIHHIHHhhhBBI")
    link = struct.Struct("<HHBBH")
    output = bytearray(struct.pack("<4I", 3, 2, 1, 3))
    output.extend(
        node.pack(
            0x14001000,
            0,
            12,
            100,
            0xA49A3BA8,
            NOD_HEURISTIC_SENTINEL,
            0,
            80,
            -164,
            800,
            24,
            19,
            int(NodNodeFlags.INTERSECTION | NodNodeFlags.REGULAR_SPEED)
            | (2 << 16)
            | 0x80000000,
        )
    )
    output.extend(
        node.pack(
            0x14001020,
            0,
            12,
            101,
            0,
            NOD_HEURISTIC_SENTINEL,
            2,
            128,
            -164,
            800,
            16,
            1,
            int(NodNodeFlags.BOAT_MOVEMENT) | (1 << 16),
        )
    )
    output.extend(
        node.pack(
            0x14001040,
            0,
            12,
            102,
            0,
            NOD_HEURISTIC_SENTINEL,
            3,
            96,
            -120,
            832,
            0,
            224,
            0x10000000,
        )
    )
    output.extend(link.pack(12, 101, 8, 9, 0x0102))
    output.extend(link.pack(11, 500, 42, 16, 0x0304))
    output.extend(link.pack(12, 100, 8, 9, 0x0506))
    return bytes(output)


class NodTests(unittest.TestCase):
    def test_reads_graph_semantics_and_round_trips_losslessly(self) -> None:
        source = _sample_nod()
        document = NodDocument.from_bytes(source, name="nodes12.nod")

        self.assertEqual(document.name, "nodes12.nod")
        self.assertEqual(len(document), 3)
        self.assertEqual(len(document.vehicle_nodes), 2)
        self.assertEqual(len(document.pedestrian_nodes), 1)
        self.assertEqual(document.pedestrian_node_count, 1)
        self.assertEqual(document.to_bytes(), source)

        road = document.nodes[0]
        self.assertEqual(road.kind, NodNodeKind.VEHICLE)
        self.assertEqual(road.position, NodVector3(10.0, -20.5, 12.5))
        self.assertEqual(road.path_width, 3.0)
        self.assertEqual(road.link_count, 2)
        self.assertTrue(road.is_intersection)
        self.assertFalse(road.is_boat)
        self.assertEqual(road.unresolved_flags, 0x80000000)
        self.assertEqual(road.flag_info[0].flag, NodNodeFlags.REGULAR_SPEED)
        self.assertEqual(road.flag_info[0].confidence, "inferred")
        self.assertEqual(road.flag_info[-1].confidence, "unresolved")
        self.assertEqual(len(road.outgoing_links), 2)
        self.assertEqual(road.outgoing_links[0].target_key, (12, 101))
        self.assertIs(road.outgoing_links[0].resolve(document), document.nodes[1])
        self.assertIsNone(road.outgoing_links[1].resolve(document))

        self.assertTrue(document.nodes[1].is_boat)
        self.assertTrue(document.nodes[2].is_pedestrian)
        self.assertEqual(document.find_node(12, 102), document.nodes[2])

    def test_edits_fixed_point_values_flags_and_links(self) -> None:
        document = NodDocument.from_bytes(_sample_nod())
        document.nodes[0].position.x = 10.25
        document.nodes[0].path_width = 4.5
        document.nodes[0].source_path_value = 1234
        document.nodes[0].flags |= NodNodeFlags.BOAT_MOVEMENT
        document.links[0].pathfinding_cost = 12
        document.links[0].traffic_flags = 0xCAFE

        reparsed = NodDocument.from_bytes(document.to_bytes())

        self.assertEqual(reparsed.nodes[0].position.x, 10.25)
        self.assertEqual(reparsed.nodes[0].path_width, 4.5)
        self.assertEqual(reparsed.nodes[0].source_path_value, 1234)
        self.assertEqual(reparsed.nodes[0].link_count, 2)
        self.assertTrue(reparsed.nodes[0].flags & NodNodeFlags.BOAT_MOVEMENT)
        self.assertEqual(reparsed.links[0].pathfinding_cost, 12)
        self.assertEqual(reparsed.links[0].traffic_flags, 0xCAFE)

    def test_loads_from_img_entry_and_stream(self) -> None:
        archive = ImgArchive.empty("paths.img")
        archive.add_file("nodes12.nod", _sample_nod())
        entry = ImgArchive.from_bytes(archive.to_bytes()).find_entry("nodes12.nod")

        self.assertIsNotNone(entry)
        document = load_nod(io.BytesIO(entry.read()))  # type: ignore[union-attr]
        self.assertEqual(len(document.nodes), 3)

    def test_empty_document_has_the_stock_empty_sector_shape(self) -> None:
        source = b"\0" * 16
        document = NodDocument.from_bytes(source)

        self.assertEqual(document.to_bytes(), source)
        self.assertEqual(NodDocument.empty().to_bytes(), source)

    def test_manually_constructed_document_is_writable(self) -> None:
        node = NodNode(
            0,
            0,
            1,
            2,
            0,
            NOD_HEURISTIC_SENTINEL,
            0,
            NodVector3(1.0, 2.0, 3.0),
            0,
            224,
            0,
            NodNodeKind.PEDESTRIAN,
        )
        document = NodDocument([node], [], vehicle_node_count=0)

        reparsed = NodDocument.from_bytes(document.to_bytes())
        self.assertTrue(reparsed.nodes[0].is_pedestrian)

    def test_rejects_invalid_counts_size_and_adjacency(self) -> None:
        source = _sample_nod()
        with self.assertRaisesRegex(ValueError, "counts do not match"):
            NodDocument.from_bytes(struct.pack("<4I", 3, 1, 1, 3) + source[16:])
        with self.assertRaisesRegex(ValueError, "truncated"):
            NodDocument.from_bytes(source[:-1])

        document = NodDocument.from_bytes(source)
        document.nodes[1].link_start = 1
        with self.assertRaisesRegex(ValueError, "starts at link"):
            document.to_bytes()

        document = NodDocument.from_bytes(source)
        document.nodes[0].set_link_count(15)
        with self.assertRaisesRegex(ValueError, "adjacency exceeds"):
            document.to_bytes()

    def test_projects_to_target_independent_path_graph(self) -> None:
        document = NodDocument.from_bytes(_sample_nod(), name="nodes12.nod")

        graph = document.to_path_graph()

        self.assertEqual(graph.name, "nodes12")
        self.assertEqual(graph.source_format, "nod")
        self.assertEqual(len(graph.nodes), 3)
        self.assertEqual(len(graph.edges), 3)
        road = graph.find_node((12, 100))
        self.assertIsNotNone(road)
        self.assertEqual(road.kind, PathNodeKind.VEHICLE)  # type: ignore[union-attr]
        self.assertEqual(road.position, (10.0, -20.5, 12.5))  # type: ignore[union-attr]
        self.assertEqual(road.width, 3.0)  # type: ignore[union-attr]
        self.assertEqual(road.traits, frozenset({"regular_speed", "intersection"}))  # type: ignore[union-attr]
        self.assertEqual(
            graph.outgoing_edges((12, 100))[1].target, PathNodeId(11, 500)
        )
        self.assertEqual(graph.unresolved_targets, (PathNodeId(11, 500),))

    def test_path_iterators_export_source_metadata_only_when_requested(self) -> None:
        document = NodDocument.from_bytes(_sample_nod())

        node = next(document.iter_path_nodes())
        edge = next(document.iter_path_edges())
        detailed_node = next(document.iter_path_nodes(include_source_metadata=True))
        detailed_edge = next(document.iter_path_edges(include_source_metadata=True))

        self.assertIsNone(node.source_metadata)
        self.assertIsNone(edge.source_metadata)
        self.assertEqual(detailed_node.source_metadata.get("flags"), int(document.nodes[0].flags))  # type: ignore[union-attr]
        self.assertEqual(detailed_node.source_metadata.get("unresolved_flags"), 0x80000000)  # type: ignore[union-attr]
        self.assertEqual(detailed_edge.source_metadata.get("traffic_flags"), 0x0102)  # type: ignore[union-attr]

    def test_loads_and_combines_neutral_sector_graphs(self) -> None:
        first = NodDocument.from_bytes(_sample_nod(), name="nodes12.nod")
        external = NodNode(
            0,
            0,
            11,
            500,
            0,
            NOD_HEURISTIC_SENTINEL,
            0,
            NodVector3(20.0, 20.0, 0.0),
            8,
            0,
            0,
        )
        second = NodDocument([external], [], vehicle_node_count=1, name="nodes11.nod")

        direct = load_nod_graph(_sample_nod())
        combined = combine_nod_graphs((first, second), name="city")

        self.assertEqual(len(direct.nodes), 3)
        self.assertEqual(combined.name, "city")
        self.assertEqual(combined.source_format, "nod")
        self.assertEqual(combined.unresolved_targets, ())
        self.assertIsNotNone(combined.find_node((11, 500)))


if __name__ == "__main__":
    unittest.main()
