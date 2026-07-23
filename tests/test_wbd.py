from __future__ import annotations

import io
import struct
import unittest
import zlib

from fourfury import (
    ImgArchive,
    WbdDocument,
    WbnComposite,
    WbnGeometry,
    WbnMaterialType,
    joaat,
    load_wbd,
)
from test_wbn import _sample_wbn


VIRTUAL_BASE = 0x50000000


def _sample_wbd() -> bytes:
    source = _sample_wbn()
    virtual = bytearray(zlib.decompress(source[12:]))
    struct.pack_into("<4I", virtual, 0, 0x00695360, VIRTUAL_BASE | 0x20, 0, 1)
    struct.pack_into("<IHH", virtual, 16, VIRTUAL_BASE | 0x40, 2, 2)
    struct.pack_into("<IHH", virtual, 24, VIRTUAL_BASE | 0x50, 2, 2)
    struct.pack_into("<2I", virtual, 0x40, joaat("compound"), joaat("mesh"))
    struct.pack_into("<2I", virtual, 0x50, VIRTUAL_BASE | 0x100, VIRTUAL_BASE | 0x300)
    return source[:12] + zlib.compress(virtual)


class WbdTests(unittest.TestCase):
    def test_joaat_matches_stock_name_hashing(self) -> None:
        self.assertEqual(joaat("test"), 0x3F75CCC1)
        self.assertEqual(joaat("ADDER"), 0xB779A091)

    def test_reads_dictionary_entries_and_shared_bounds_losslessly(self) -> None:
        source = _sample_wbd()
        document = WbdDocument.from_bytes(source, name="sample.wbd")

        self.assertEqual(document.name, "sample.wbd")
        self.assertEqual(len(document), 2)
        self.assertEqual(document.hashes, (joaat("compound"), joaat("mesh")))
        self.assertIsInstance(document.find_bound("COMPOUND"), WbnComposite)
        self.assertIsInstance(document.find_bound(joaat("mesh")), WbnGeometry)
        self.assertIsNone(document.find_entry("missing"))
        self.assertEqual(len(list(document.iter_bounds())), 2)
        self.assertEqual(len(document.geometries), 1)
        self.assertEqual(document.to_bytes(), source)

    def test_reads_wbd_from_img_and_binary_stream(self) -> None:
        source = _sample_wbd()
        archive = ImgArchive.empty("map.img")
        archive.add_file("sample.wbd", source, resource_type=0x20, resource_flags=0xC0000010)
        parsed_archive = ImgArchive.from_bytes(archive.to_bytes())
        entry = parsed_archive.find_entry("sample.wbd")

        self.assertIsNotNone(entry)
        document = load_wbd(io.BytesIO(entry.read()))  # type: ignore[union-attr]
        self.assertEqual(len(document.bounds), 2)

    def test_fixed_size_edits_recompress_and_reparse(self) -> None:
        document = WbdDocument.from_bytes(_sample_wbd())
        geometry = document.geometries[0]

        self.assertEqual(geometry.materials[0].name, "RUMBLE_STRIP")
        geometry.materials[0].material_type = WbnMaterialType.ROCK
        document.parent_dictionary = joaat("parent")
        document.usage_count = 2
        document.entries[1].name_hash = joaat("renamed_mesh")
        geometry.vertices[1].x = 12
        changed = document.to_bytes()

        reparsed = WbdDocument.from_bytes(changed)
        self.assertEqual(reparsed.parent_dictionary, joaat("parent"))
        self.assertEqual(reparsed.usage_count, 2)
        self.assertIsNotNone(reparsed.find_entry("renamed_mesh"))
        self.assertEqual(reparsed.geometries[0].vertices[1].x, 12)
        self.assertIs(reparsed.geometries[0].materials[0].material_type, WbnMaterialType.ROCK)

    def test_rejects_dictionary_count_changes(self) -> None:
        document = WbdDocument.from_bytes(_sample_wbd())
        document.entries.pop()

        with self.assertRaisesRegex(ValueError, "cannot change.*entry count"):
            document.to_bytes()

    def test_rejects_mismatched_hash_and_bound_counts(self) -> None:
        source = _sample_wbd()
        virtual = bytearray(zlib.decompress(source[12:]))
        struct.pack_into("<H", virtual, 20, 1)

        with self.assertRaisesRegex(ValueError, "counts do not match"):
            WbdDocument.from_bytes(source[:12] + zlib.compress(virtual))


if __name__ == "__main__":
    unittest.main()
