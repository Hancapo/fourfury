from __future__ import annotations

import io
import struct
import unittest
import zlib

from fourfury import Rsc5TextureFormat, WTD_RESOURCE_VERSION, WtdDocument, load_wtd


VIRTUAL_BASE = 0x50000000
PHYSICAL_BASE = 0x60000000


def _sample_wtd() -> bytes:
    virtual = bytearray(0x1000)
    physical = bytearray(0x1000)
    struct.pack_into("<4I", virtual, 0, 0, 0, 0, 1)
    struct.pack_into("<IHH", virtual, 0x10, VIRTUAL_BASE | 0x30, 1, 1)
    struct.pack_into("<IHH", virtual, 0x18, VIRTUAL_BASE | 0x34, 1, 1)
    struct.pack_into("<I", virtual, 0x30, 0x12345678)
    struct.pack_into("<I", virtual, 0x34, VIRTUAL_BASE | 0x80)
    struct.pack_into("<I", virtual, 0x94, VIRTUAL_BASE | 0xD0)
    struct.pack_into(
        "<HHIHBB", virtual, 0x9C, 4, 4, Rsc5TextureFormat.DXT1, 2, 0, 1
    )
    struct.pack_into("<I", virtual, 0xC8, PHYSICAL_BASE)
    name = b"pack:/sample.dds\0"
    virtual[0xD0:0xD0 + len(name)] = name
    struct.pack_into("<HHI", physical, 0, 0xF800, 0, 0)
    flags = 0xC0080010
    return struct.pack("<4sII", b"RSC\x05", WTD_RESOURCE_VERSION, flags) + zlib.compress(
        virtual + physical
    )


class WtdTests(unittest.TestCase):
    def test_reads_texture_payload_and_writes_dds(self) -> None:
        source = _sample_wtd()
        document = WtdDocument.from_bytes(source, name="sample.wtd")

        self.assertEqual(document.to_bytes(), source)
        self.assertEqual(len(document.textures), 1)
        texture = document.get("sample.dds")
        self.assertIsNotNone(texture)
        self.assertEqual(texture.name, "sample")  # type: ignore[union-attr]
        self.assertEqual(texture.format, Rsc5TextureFormat.DXT1)  # type: ignore[union-attr]
        self.assertEqual(texture.mip_sizes, (8,))  # type: ignore[union-attr]
        dds = texture.to_dds_bytes()  # type: ignore[union-attr]
        self.assertEqual(dds[:4], b"DDS ")
        self.assertEqual(struct.unpack_from("<2I", dds, 12), (4, 4))
        self.assertEqual(dds[84:88], b"DXT1")
        self.assertEqual(dds[128:], struct.pack("<HHI", 0xF800, 0, 0))

    def test_loads_from_binary_stream(self) -> None:
        self.assertEqual(load_wtd(io.BytesIO(_sample_wtd())).textures[0].width, 4)


if __name__ == "__main__":
    unittest.main()
