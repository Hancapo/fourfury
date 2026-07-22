from __future__ import annotations

import struct
import unittest

from fourfury import (
    IdeDocument,
    WplBlock,
    WplCull,
    WplDocument,
    WplGarage,
    WplInstance,
    WplInstanceFlags,
    WplLodCull,
    WplParkedCar,
    WplStrBig,
    WplZone,
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


class WplTests(unittest.TestCase):
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

    def test_rejects_truncated_section(self) -> None:
        header = struct.pack("<17I", 3, 1, *([0] * 15))
        with self.assertRaisesRegex(ValueError, "truncated WPL section 0"):
            WplDocument.from_bytes(header)


if __name__ == "__main__":
    unittest.main()
