from __future__ import annotations

import io
import struct
import unittest
import zlib

from fourfury import WDD_RESOURCE_VERSION, WddDocument, joaat, load_wdd


VIRTUAL_BASE = 0x50000000


def _pointer(offset: int) -> int:
    return VIRTUAL_BASE | offset


def _sample_wdd(*, hash_count: int = 1, drawable_count: int = 1) -> bytes:
    virtual = bytearray(0x1000)
    struct.pack_into("<4I", virtual, 0, 0x6953A4, 0, joaat("parent"), 3)
    struct.pack_into("<IHH", virtual, 0x10, _pointer(0x100), hash_count, hash_count)
    struct.pack_into("<IHH", virtual, 0x18, _pointer(0x110), drawable_count, drawable_count)
    struct.pack_into("<I", virtual, 0x100, joaat("sample"))
    struct.pack_into("<I", virtual, 0x110, _pointer(0x200))

    struct.pack_into("<4I", virtual, 0x200, 0x695254, 0, 0, 0)
    struct.pack_into("<4f", virtual, 0x210, 1.0, 2.0, 3.0, 0.0)
    struct.pack_into("<4f", virtual, 0x220, -1.0, -2.0, -3.0, 0.0)
    struct.pack_into("<4f", virtual, 0x230, 4.0, 5.0, 6.0, 0.0)
    struct.pack_into("<4f", virtual, 0x250, 100.0, 200.0, 300.0, 400.0)
    struct.pack_into("<4i", virtual, 0x260, 1, 2, 3, 4)
    struct.pack_into("<f", virtual, 0x270, 7.0)

    flags = 0xC0000010
    return struct.pack("<4sII", b"RSC\x05", WDD_RESOURCE_VERSION, flags) + zlib.compress(
        virtual
    )


class WddTests(unittest.TestCase):
    def test_reads_dictionary_metadata_and_drawables(self) -> None:
        document = WddDocument.from_bytes(_sample_wdd(), name="sample.wdd")

        self.assertEqual(document.parent_dictionary_hash, joaat("parent"))
        self.assertEqual(document.usage_count, 3)
        self.assertEqual(len(document), 1)
        self.assertEqual(document.hashes, (joaat("sample"),))
        self.assertIs(document.find_drawable("sample"), document.drawables[0])
        self.assertIs(document[joaat("sample")], document.entries[0])
        self.assertEqual(document.entries[0].hash_hex, f"{joaat('sample'):08x}")

    def test_projects_an_entry_to_the_neutral_model_api(self) -> None:
        document = WddDocument.from_bytes(_sample_wdd())

        model = document.to_model("sample")

        self.assertEqual(model.name, "sample")
        self.assertEqual(model.bounding_box.minimum, (-1.0, -2.0, -3.0))
        self.assertEqual(model.bounding_box.maximum, (4.0, 5.0, 6.0))
        self.assertEqual(model.bounding_sphere.radius, 7.0)

    def test_loads_stream_and_preserves_resource_losslessly(self) -> None:
        source = _sample_wdd()
        document = load_wdd(io.BytesIO(source))

        self.assertEqual(document.to_bytes(), source)

    def test_rejects_mismatched_parallel_arrays(self) -> None:
        with self.assertRaisesRegex(ValueError, "hash and drawable counts do not match"):
            WddDocument.from_bytes(_sample_wdd(hash_count=1, drawable_count=0))

    def test_rejects_other_rsc5_resource_versions(self) -> None:
        source = bytearray(_sample_wdd())
        struct.pack_into("<I", source, 4, 0x70)

        with self.assertRaisesRegex(ValueError, "unsupported WDD resource version"):
            WddDocument.from_bytes(bytes(source))


if __name__ == "__main__":
    unittest.main()
