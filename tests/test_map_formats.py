from __future__ import annotations

import struct
import unittest

from fourfury import (
    IdeArchetypeFlags,
    IdeDocument,
    IplDocument,
    MloRegistry,
    WplBlock,
    WplCull,
    WplDocument,
    WplGarage,
    WplInstance,
    WplInstanceFlags,
    WplLodCull,
    WplLodHierarchyError,
    WplLodIssueCode,
    WplLodParentScope,
    WplMloPortal,
    WplParkedCar,
    WplStrBig,
    WplZone,
    joaat,
)


class IdeTests(unittest.TestCase):
    def test_round_trip_preserves_formatting_comments_and_nested_mlo_tokens(self) -> None:
        source = (
            b"# Object definitions\r\n"
            b"objs\r\n"
            b"model, drawable, 60, 1\r\n"
            b"end\r\n"
            b"mlo\r\n"
            b"mloroomstart\r\n"
            b"room, 0, 1\r\n"
            b"mloend\r\n"
            b"end\r\n"
        )

        document = IdeDocument.from_bytes(source)

        self.assertEqual(document.to_bytes(), source)
        self.assertEqual(document.section_names, ["objs", "mlo"])
        self.assertEqual(len(document.get_entries("MLO")), 3)
        self.assertEqual(document.get_entries("objs")[0].get_int(2), 60)

    def test_edit_and_add_entry(self) -> None:
        document = IdeDocument.from_text("objs\nmodel, drawable, 60\nend\n")
        document.get_entries("objs")[0].values[2] = "120"
        document.add_entry("objs", ["second", "second_drawable", "80"])

        self.assertEqual(
            document.to_text(),
            "objs\nmodel, drawable, 120\nsecond, second_drawable, 80\nend\n",
        )

    def test_modified_entry_quotes_csv_metacharacters(self) -> None:
        document = IdeDocument.from_text("objs\nmodel, drawable\nend\n")
        document.get_entries("objs")[0].values[0] = 'model, "variant"'

        reparsed = IdeDocument.from_text(document.to_text())

        self.assertEqual(reparsed.get_entries("objs")[0].values[0], 'model, "variant"')

    def test_models_uv_animated_archetypes_and_edits_flags_losslessly(self) -> None:
        source = (
            "anim\n"
            "screen, screen_txd, screen_anims, 100, 1536\n"
            "static_sign, sign_txd, sign_anims, 80, 0\n"
            "end\n"
        )
        document = IdeDocument.from_text(source)

        screen = document.find_archetype("SCREEN")
        assert screen is not None
        self.assertEqual(screen.animation_dictionary, "screen_anims")
        self.assertEqual(screen.uv_animation_dictionary, "screen_anims")
        self.assertTrue(screen.has_animation)
        self.assertTrue(screen.has_uv_animation)
        self.assertEqual(
            screen.flags,
            IdeArchetypeFlags.HAS_ANIMATION | IdeArchetypeFlags.HAS_UV_ANIMATION,
        )
        self.assertEqual(document.uv_animated_archetypes, (screen,))

        screen.flags &= ~IdeArchetypeFlags.HAS_UV_ANIMATION
        self.assertFalse(screen.has_uv_animation)
        self.assertIsNone(screen.uv_animation_dictionary)
        reparsed = IdeDocument.from_bytes(document.to_bytes())
        self.assertEqual(
            reparsed.find_archetype("screen").flags,  # type: ignore[union-attr]
            IdeArchetypeFlags.HAS_ANIMATION,
        )

    def test_rejects_non_archetype_sections_for_typed_iteration(self) -> None:
        document = IdeDocument.from_text("txdp\nchild, parent\nend\n")

        with self.assertRaisesRegex(ValueError, "not an archetype section"):
            tuple(document.iter_archetypes("txdp"))

    def test_parses_complete_mlo_topology_and_preserves_edits(self) -> None:
        source = (
            "mlo\n"
            "test_mlo, 0, 2, 1, 2, 100, 200, 300\n"
            "chair, 1, 0, 0, 0, 0, 0, 1, 0, 384,\n"
            "interior_lod, 0, 0, 0, 0, 0, 0, 1, 1, 384,\n"
            "mloroomstart\n"
            "limbo, 0, 1, 2, 2, 2, -2, -2, -2, 1, 0, 0\n"
            "-1, -1\n"
            "roomend\n"
            "main, 2, 1, 2, 2, 2, -2, -2, -2, 1, 1234, 96\n"
            "0, 1, -1\n"
            "roomend\n"
            "mloportalstart\n"
            "1, 0, 0, 0, 0, 0, 0, 2, 0, 2, 2, 0, 2, 0, "
            "-1, -1, -1, -1, 64, 3, 1\n"
            "mloend\n"
            "end\n"
        )
        document = IdeDocument.from_text(source, name="interior.ide")

        self.assertEqual(document.to_text(), source)
        self.assertEqual(len(document.mlo_archetypes), 1)
        archetype = document.find_mlo_archetype("TEST_MLO")
        assert archetype is not None
        self.assertEqual(archetype.name_hash, joaat("test_mlo"))
        self.assertEqual(archetype.hd_entity_count, 2)
        self.assertEqual(archetype.lod_distances, (100.0, 200.0, 300.0))
        self.assertEqual(archetype.lod_parent_indices, (1, None))
        self.assertEqual(archetype.rooms[1].entity_ids, (0, 1))
        self.assertEqual(archetype.portal_indices_for_room(1), (0,))
        self.assertEqual(archetype.portals[0].corners[2], (0.0, 2.0, 2.0))
        self.assertEqual(archetype.portals[0].active_hours, (0, 1))
        self.assertEqual(archetype.validate(), ())

        archetype.rooms[1].time_cycle_hash = 4321
        reparsed = IdeDocument.from_text(document.to_text())
        self.assertEqual(
            reparsed.mlo_archetypes[0].rooms[1].time_cycle_hash,
            4321,
        )

    def test_mlo_validation_reports_broken_cross_references(self) -> None:
        document = IdeDocument.from_text(
            "mlo\n"
            "broken, 0, 1, 1, 0, 100, -1, -1\n"
            "mloroomstart\n"
            "room, 1, 0, 1, 1, 1, 0, 0, 0, 1, 0, 0\n"
            "9, -1\n"
            "roomend\n"
            "mloportalstart\n"
            "0, 4, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 1, 0, "
            "-1, -1, -1, -1, 0, 16777215, 1\n"
            "mloend\n"
            "end\n"
        )

        issues = document.mlo_archetypes[0].validate()

        self.assertEqual(
            {issue.code for issue in issues},
            {
                "room_portal_count",
                "room_entity_reference",
                "portal_room_reference",
            },
        )


class IplTests(unittest.TestCase):
    def test_occluder_parsing_preserves_text_and_normalizes_geometry(self) -> None:
        source = (
            b"# Visual occlusion\r\n"
            b"occl\r\n"
            b"10.0, 20.0, 30.0, 8.0, 6.0, -10.0, 45.0, 0.0, 0.0, 0\r\n"
            b"end\r\n"
        )

        document = IplDocument.from_bytes(source, name="occlu.ipl")

        self.assertEqual(document.to_bytes(), source)
        self.assertEqual(len(document.occluders), 1)
        occluder = document.occluders[0]
        self.assertEqual(occluder.center, (10.0, 20.0, 25.0))
        self.assertEqual(occluder.size, (8.0, 6.0, 10.0))
        self.assertEqual(occluder.rotation, 45.0)
        self.assertEqual(occluder.flags, 0)

    def test_occluder_requires_all_ten_fields(self) -> None:
        document = IplDocument.from_text("occl\n1, 2, 3\nend\n")

        with self.assertRaisesRegex(ValueError, "requires exactly 10 values"):
            _ = document.occluders


class WplTests(unittest.TestCase):
    @staticmethod
    def make_instance(*, lod_index: int = -1, model_hash: int = 1) -> WplInstance:
        return WplInstance(
            0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
            model_hash,
            lod_index=lod_index,
        )

    def test_all_supported_section_types_round_trip(self) -> None:
        document = WplDocument.empty()
        document.add(WplGarage(*([1.0] * 8), 1, 2, "GARAGE1"))
        document.add(WplParkedCar(*([2.0] * 6), 0x12345678))
        document.add(WplCull(*([3.0] * 6), model_hash=0xABCDEF01))
        document.add(WplStrBig("large_model", 1, 2, 3, *([4.0] * 7)))
        document.add(WplLodCull(
            *([5.0] * 6),
            7,
            tuple(range(10)),
            tuple(f"lod_{index}" for index in range(10)),
        ))
        document.add(WplZone(*([6.0] * 6)))
        document.add(WplBlock(1, "0:0:1:0:1:1:0:1", 2, *([7.0] * 8)))

        parsed = WplDocument.from_bytes(document.to_bytes())

        self.assertEqual(parsed.garages[0].garage_type, 2)
        self.assertEqual(parsed.parked_cars[0].model_hash, 0x12345678)
        self.assertEqual(parsed.culls[0].model_hash, 0xABCDEF01)
        self.assertEqual(parsed.strbig[0].model_name, "large_model")
        self.assertIsInstance(parsed.mlo_portals[0], WplMloPortal)
        self.assertIs(parsed.strbig[0], parsed.mlo_portals[0])
        self.assertEqual(parsed.lod_culls[0].model_names[-1], "lod_9")
        self.assertEqual(parsed.blocks[0].reserved_2, 2)

    def test_round_trip_instances_zones_and_trailing_padding(self) -> None:
        document = WplDocument.empty("map")
        document.add(WplInstance(
            1.0, 2.0, 3.0,
            0.0, 0.0, 0.0, 1.0,
            0xD70FDB44,
            flags=WplInstanceFlags.DEFAULT | WplInstanceFlags.FULL_ROTATION,
            lod_index=12,
            block_index=23,
            lod_distance=-1.0,
        ))
        document.add(WplZone(-10.0, -20.0, -30.0, 10.0, 20.0, 30.0))
        document.trailing_data = b"\0" * 16

        packed = document.to_bytes()
        parsed = WplDocument.from_bytes(packed)

        self.assertEqual(struct.unpack_from("<I", packed)[0], 3)
        self.assertEqual(parsed.to_bytes(), packed)
        self.assertEqual(parsed.instances[0].model_hash, 0xD70FDB44)
        self.assertEqual(parsed.instances[0].lod_index, 12)
        self.assertEqual(parsed.instances[0].block_index, 23)
        self.assertIn(WplInstanceFlags.FULL_ROTATION, parsed.instances[0].flags)
        self.assertEqual(parsed.zones[0].max_z, 30.0)
        self.assertEqual(parsed.trailing_data, b"\0" * 16)

    def test_resolves_mlo_placements_and_world_space_contents(self) -> None:
        definitions = IdeDocument.from_text(
            "mlo\n"
            "test_mlo, 0, 2, 1, 2, 100, 200, 300\n"
            "chair, 1, 0, 0, 0, 0, 0, 1, 0, 384\n"
            "interior_lod, 0, 0, 0, 0, 0, 0, 1, 1, 384\n"
            "mloroomstart\n"
            "limbo, 0, 1, 2, 2, 2, -2, -2, -2, 1, 0, 0\n"
            "-1\n"
            "roomend\n"
            "main, 2, 1, 2, 2, 2, -2, -2, -2, 1, 0, 0\n"
            "0, 1, -1\n"
            "roomend\n"
            "mloportalstart\n"
            "1, 0, 0, 0, 0, 0, 0, 2, 0, 2, 2, 0, 2, 0, "
            "-1, -1, -1, -1, 64, 16777215, 1\n"
            "mloend\n"
            "end\n"
        )
        registry = MloRegistry.from_ide_documents((definitions,))
        placement = WplInstance(
            10.0, 20.0, 30.0,
            0.0, 0.0, 2**-0.5, 2**-0.5,
            joaat("test_mlo"),
        )
        document = WplDocument.empty()
        document.add(placement)
        document.add(self.make_instance(model_hash=joaat("ordinary_model")))

        instances = document.resolve_mlos(registry)

        self.assertEqual(len(instances), 1)
        instance = instances[0]
        self.assertEqual(instance.placement_index, 0)
        self.assertAlmostEqual(instance.entities[0].position[0], 10.0)
        self.assertAlmostEqual(instance.entities[0].position[1], 21.0)
        self.assertAlmostEqual(instance.entities[0].position[2], 30.0)
        self.assertEqual(instance.entities[0].lod_parent_index, 1)
        self.assertEqual(instance.rooms[1].portal_ids, (0,))
        self.assertEqual(instance.portals[0].corners[0], (10.0, 20.0, 30.0))
        self.assertEqual(instance.to_data()["name"], "test_mlo")

    def test_instance_flags_have_explanations_and_editable_detail_level(self) -> None:
        instance = WplInstance(
            1.0, 2.0, 3.0,
            0.01, 0.02, 0.0, 1.0,
            0xD70FDB44,
            flags=WplInstanceFlags.DEFAULT | WplInstanceFlags.FULL_ROTATION,
        )

        self.assertEqual(instance.detail_level, 0)
        self.assertEqual(
            next(info for info in instance.flag_info if info.flag == WplInstanceFlags.FULL_ROTATION).confidence,
            "verified",
        )

        instance.detail_level = 2
        self.assertEqual(instance.detail_level, 2)
        self.assertTrue(instance.flags & WplInstanceFlags.DETAIL_LEVEL_2)
        with self.assertRaisesRegex(ValueError, "between 0 and 3"):
            instance.detail_level = 4

        instance.flags |= WplInstanceFlags(0x10000)
        self.assertEqual(instance.flag_info[-1].flag, WplInstanceFlags(0x10000))
        self.assertEqual(instance.flag_info[-1].confidence, "unresolved")

    def test_local_lod_hierarchy_models_roots_depth_and_traversal(self) -> None:
        document = WplDocument.empty("local")
        root = document.add(self.make_instance(model_hash=10))
        child = document.add(self.make_instance(lod_index=0, model_hash=11))
        grandchild = document.add(self.make_instance(lod_index=1, model_hash=12))
        second_root = document.add(self.make_instance(model_hash=13))

        hierarchy = document.build_lod_hierarchy(strict=True)
        root_node = hierarchy.node_for(root)
        child_node = hierarchy.node_for(child)
        grandchild_node = hierarchy.node_for(grandchild)

        self.assertEqual(hierarchy.roots, (root_node, hierarchy.node_for(second_root)))
        self.assertEqual(root_node.children, (child_node,))
        self.assertEqual(tuple(root_node.iter_descendants()), (child_node, grandchild_node))
        self.assertEqual(grandchild_node.ancestors, (child_node, root_node))
        self.assertEqual((root_node.depth, child_node.depth, grandchild_node.depth), (0, 1, 2))
        self.assertEqual(child_node.parent_scope, WplLodParentScope.LOCAL)
        self.assertEqual(child_node.parent_index, 0)
        self.assertFalse(child_node.has_unresolved_parent)

    def test_stream_lod_indices_resolve_against_external_parent_document(self) -> None:
        parent = WplDocument.empty("manhat01")
        parent_root = parent.add(self.make_instance(model_hash=20))
        parent_child = parent.add(self.make_instance(lod_index=0, model_hash=21))
        stream = WplDocument.empty("manhat01_6")
        stream_child = stream.add(self.make_instance(lod_index=1, model_hash=22))
        stream_root = stream.add(self.make_instance(model_hash=23))

        hierarchy = stream.build_lod_hierarchy(parent=parent, strict=True)
        parent_root_node = hierarchy.node_for(parent_root)
        parent_child_node = hierarchy.node_for(parent_child)
        stream_child_node = hierarchy.node_for(stream_child)

        self.assertIs(stream_child_node.parent, parent_child_node)
        self.assertEqual(stream_child_node.parent_scope, WplLodParentScope.EXTERNAL)
        self.assertEqual(stream_child_node.depth, 2)
        self.assertEqual(parent_child_node.parent_scope, WplLodParentScope.LOCAL)
        self.assertEqual(parent_root_node.children, (parent_child_node,))
        self.assertEqual(parent_child_node.children, (stream_child_node,))
        self.assertIn(hierarchy.node_for(stream_root), hierarchy.roots)
        self.assertEqual(hierarchy.roots_for(stream), (hierarchy.node_for(stream_root),))
        self.assertEqual(hierarchy.nodes_for(stream), (stream_child_node, hierarchy.node_for(stream_root)))

    def test_lod_hierarchy_reports_invalid_indices_without_changing_binary_data(self) -> None:
        document = WplDocument.empty("broken")
        instance = document.add(self.make_instance(lod_index=7))
        packed = document.to_bytes()

        hierarchy = document.build_lod_hierarchy()

        self.assertEqual(document.to_bytes(), packed)
        self.assertTrue(hierarchy.node_for(instance).has_unresolved_parent)
        self.assertEqual(hierarchy.issues[0].code, WplLodIssueCode.PARENT_INDEX_OUT_OF_RANGE)
        self.assertIs(hierarchy.issues[0].target_document, document)
        with self.assertRaises(WplLodHierarchyError) as caught:
            document.build_lod_hierarchy(strict=True)
        self.assertEqual(caught.exception.issues, hierarchy.issues)

    def test_lod_hierarchy_detects_cycles_and_rebuilds_after_edits(self) -> None:
        document = WplDocument.empty("cycle")
        first = document.add(self.make_instance(lod_index=1))
        second = document.add(self.make_instance(lod_index=0))

        malformed = document.build_lod_hierarchy()

        self.assertEqual(malformed.issues[0].code, WplLodIssueCode.CYCLE)
        self.assertTrue(malformed.node_for(first).has_unresolved_parent)
        self.assertTrue(malformed.node_for(second).has_unresolved_parent)

        first.lod_index = -1
        repaired = document.build_lod_hierarchy(strict=True)
        self.assertIs(repaired.node_for(second).parent, repaired.node_for(first))
        self.assertEqual(repaired.roots, (repaired.node_for(first),))

    def test_rejects_truncated_section(self) -> None:
        header = struct.pack("<17I", 3, 1, *([0] * 15))
        with self.assertRaisesRegex(ValueError, "truncated WPL section 0"):
            WplDocument.from_bytes(header)


if __name__ == "__main__":
    unittest.main()
