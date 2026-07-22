from __future__ import annotations

import struct
import unittest
import zlib

from fourfury import GTAIVCrypto, ImgArchive, RpfArchive


class ArchiveTests(unittest.TestCase):
    def test_rpf2_round_trip_with_directories_and_case_insensitive_lookup(self) -> None:
        archive = RpfArchive.empty("example")
        archive.add_file("data/readme.txt", b"hello GTA IV")
        archive.add_file("models/cube.bin", b"\x01\x02\x03")

        packed = archive.to_bytes()
        self.assertEqual(packed[:4], b"RPF2")
        parsed = RpfArchive.from_bytes(packed)

        readme = parsed.find_entry("DATA/README.TXT")
        cube = parsed.find_entry("models/cube.bin")
        self.assertIsNotNone(readme)
        self.assertIsNotNone(cube)
        self.assertEqual(readme.read(), b"hello GTA IV")  # type: ignore[union-attr]
        self.assertEqual(cube.read(), b"\x01\x02\x03")  # type: ignore[union-attr]
        self.assertFalse(parsed.encrypted)

    def test_rpf2_resource_preserves_rsc5_flags(self) -> None:
        flags = 0xC0001234
        resource = b"RSC\x05" + struct.pack("<2I", 0x6E, flags) + zlib.compress(b"model")
        archive = RpfArchive.empty()
        archive.add_file("model.wdr", resource, resource_type=0x6E)

        parsed = RpfArchive.from_bytes(archive.to_bytes())
        entry = parsed.find_entry("model.wdr")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.resource_type, 0x6E)  # type: ignore[union-attr]
        self.assertEqual(entry.uncompressed_size, flags)  # type: ignore[union-attr]
        self.assertEqual(entry.read(), resource)  # type: ignore[union-attr]

    def test_img3_round_trip_flat_files(self) -> None:
        archive = ImgArchive.empty("scripts")
        archive.add_file("first.sco", b"first", resource_type=0x5C617467)
        archive.add_file("second.sco", b"second")

        packed = archive.to_bytes()
        self.assertEqual(packed[:4], struct.pack("<I", 0xA94E2A52))
        parsed = ImgArchive.from_bytes(packed)

        first = parsed.find_entry("FIRST.SCO")
        second = parsed.find_entry("second.sco")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first.read(), b"first")  # type: ignore[union-attr]
        self.assertEqual(second.read(), b"second")  # type: ignore[union-attr]
        self.assertTrue(all(entry.offset % 2048 == 0 for entry in parsed.entries))

    def test_img3_resource_trims_sector_padding(self) -> None:
        flags = 0xC0000040
        resource = b"RSC\x05" + struct.pack("<2I", 0x20, flags) + zlib.compress(b"bounds" * 100)
        archive = ImgArchive.empty()
        archive.add_file("bounds.wbn", resource, resource_type=0x20, resource_flags=flags)

        parsed = ImgArchive.from_bytes(archive.to_bytes())
        entry = parsed.find_entry("bounds.wbn")
        self.assertIsNotNone(entry)
        self.assertTrue(entry.is_resource)  # type: ignore[union-attr]
        self.assertEqual(entry.table_value, flags)  # type: ignore[union-attr]
        self.assertEqual(entry.read(), resource)  # type: ignore[union-attr]

    def test_img_rejects_directory_paths(self) -> None:
        with self.assertRaisesRegex(ValueError, "flat"):
            ImgArchive.empty().add_file("folder/file.bin", b"x")

    def test_crypto_rejects_wrong_key_length(self) -> None:
        with self.assertRaisesRegex(ValueError, "32 bytes"):
            GTAIVCrypto(b"short")


if __name__ == "__main__":
    unittest.main()
