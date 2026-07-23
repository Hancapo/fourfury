from __future__ import annotations

import io
import struct
import unittest
import zlib

from fourfury import (
    WFT_RESOURCE_VERSION,
    WftDampingKind,
    WftDocument,
    WftFragmentFlags,
    load_wft,
)


VIRTUAL_BASE = 0x50000000


def _pointer(offset: int) -> int:
    return VIRTUAL_BASE | offset


def _identity() -> tuple[float, ...]:
    return (
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )


def _sample_wft() -> bytes:
    virtual = bytearray(0x2000)

    struct.pack_into("<2I2f", virtual, 0, 0x695238, 0, 2.0, 8.0)
    struct.pack_into("<4f", virtual, 0x10, 1.0, 2.0, 3.0, 4.0)
    struct.pack_into("<4f", virtual, 0x20, 0.1, 0.2, 0.3, 0.0)
    struct.pack_into("<4f", virtual, 0x30, 0.4, 0.5, 0.6, 0.0)
    struct.pack_into("<4f", virtual, 0x40, 0.7, 0.8, 0.9, 0.0)
    for index in range(6):
        struct.pack_into("<4f", virtual, 0x50 + index * 16, float(index), 0.0, 0.0, 0.0)
    struct.pack_into(
        "<4I IiI 3I",
        virtual,
        0xB0,
        _pointer(0xD00),
        _pointer(0x300),
        0,
        0,
        0,
        -1,
        0,
        _pointer(0xD20),
        _pointer(0xD24),
        _pointer(0xD28),
    )
    struct.pack_into("<3I", virtual, 0xE4, _pointer(0xB80), 0, 0)
    struct.pack_into("<3I", virtual, 0xF0, _pointer(0xC80), _pointer(0xC90), _pointer(0xCA0))
    struct.pack_into("<2I", virtual, 0xE8, 0, 0)
    struct.pack_into("<2I", virtual, 0x1E8, 100, 200)
    struct.pack_into("<12B", virtual, 0x1F0, 0, 0, 1, 1, 1, 0, 1, 0x23, 7, 0, 255, 0)
    struct.pack_into("<if", virtual, 0x1FC, -1, 12.5)

    struct.pack_into("<4I", virtual, 0x300, 0x695254, 0, 0, 0)
    struct.pack_into("<4f", virtual, 0x310, 0.0, 0.0, 0.0, 0.0)
    struct.pack_into("<4f", virtual, 0x320, -1.0, -2.0, -3.0, 0.0)
    struct.pack_into("<4f", virtual, 0x330, 1.0, 2.0, 3.0, 0.0)
    struct.pack_into("<4f", virtual, 0x350, 100.0, 200.0, 300.0, 400.0)
    struct.pack_into("<f", virtual, 0x370, 4.0)
    struct.pack_into("<16f", virtual, 0x380, *_identity())
    struct.pack_into("<I", virtual, 0x3E0, _pointer(0xD50))

    struct.pack_into("<14f", virtual, 0x5D0, 100.0, 0.25, 0.5, 1.0, -1.0, 1.0,
                     2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 50.0)
    struct.pack_into("<8B", virtual, 0x60C, 0, 0xFF, 0, 1, 0, 0xCD, 0xCD, 0)
    struct.pack_into("<2f", virtual, 0x614, 25.0, 1000.0)
    virtual[0x61C:0x624] = b"chassis\0"

    struct.pack_into("<IffBBH", virtual, 0x700, 0x6A35F4, 50.0, 40.0, 0, 0, 7)
    struct.pack_into("<16f", virtual, 0x710, *_identity())
    struct.pack_into("<16f", virtual, 0x750, *_identity())
    struct.pack_into("<2I", virtual, 0x790, _pointer(0x300), 0)

    struct.pack_into("<5I", virtual, 0xB84, 2, _pointer(0xD00), 0, 1, 0xFFFFFFFF)
    struct.pack_into("<2H5f", virtual, 0xB98, 0, 1, 90.0, 1.0 / 90.0, 1.0, 20.0, 6.0)
    struct.pack_into("<4f", virtual, 0xBB0, 1.0, 2.0, 3.0, 0.0)
    struct.pack_into("<4f", virtual, 0xBC0, 1.0, 0.5, 1.0 / 3.0, 0.0)
    for index in range(6):
        struct.pack_into("<4f", virtual, 0xBD0 + index * 16, float(index + 10), 0.0, 0.0, 0.0)

    struct.pack_into("<4f", virtual, 0xC80, 1.0, 2.0, 3.0, 50.0)
    struct.pack_into("<4f", virtual, 0xC90, 4.0, 5.0, 6.0, 40.0)
    struct.pack_into("<12f", virtual, 0xCA0, *_identity()[:12])
    struct.pack_into("<I", virtual, 0xD20, _pointer(0xD40))
    struct.pack_into("<I", virtual, 0xD24, _pointer(0x500))
    struct.pack_into("<I", virtual, 0xD28, _pointer(0x700))
    virtual[0xD00:0xD0D] = b"pack:/sample\0"
    virtual[0xD40:0xD48] = b"chassis\0"
    virtual[0xD50:0xD57] = b"common\0"

    flags = 0xC0000020
    return struct.pack("<4sII", b"RSC\x05", WFT_RESOURCE_VERSION, flags) + zlib.compress(virtual)


class WftTests(unittest.TestCase):
    def test_reads_fragment_physics_and_relationships(self) -> None:
        document = WftDocument.from_bytes(_sample_wft(), name="sample.wft")
        fragment = document.fragment

        self.assertEqual(fragment.tune_name, "pack:/sample")
        self.assertEqual(
            fragment.flags,
            WftFragmentFlags.NEEDS_CACHE_ENTRY_TO_ACTIVATE
            | WftFragmentFlags.HAS_ARTICULATED_PARTS
            | WftFragmentFlags.FORCE_ARTICULATED_DAMPING,
        )
        self.assertEqual(fragment.damping_for(WftDampingKind.ANGULAR_VELOCITY).x, 4.0)
        self.assertEqual(fragment.archetype.mass, 90.0)  # type: ignore[union-attr]
        self.assertEqual(fragment.child_inertia[0].w, 50.0)
        self.assertEqual(fragment.child_matrices[0].rows[0], (1.0, 0.0, 0.0, 0.0))

        group = fragment.find_group("CHASSIS")
        self.assertIsNotNone(group)
        self.assertTrue(group.is_root)  # type: ignore[union-attr]
        self.assertEqual(group.children, fragment.children)  # type: ignore[union-attr]
        self.assertIs(fragment.children[0].group, group)
        self.assertEqual(fragment.children[0].bone_index, 7)
        self.assertIs(fragment.children[0].undamaged_drawable, fragment.drawable)

    def test_exposes_common_drawable_and_target_independent_model(self) -> None:
        document = WftDocument.from_bytes(_sample_wft())

        self.assertEqual(document.drawable.name, "common")  # type: ignore[union-attr]
        self.assertEqual(tuple(document.iter_drawables()), (document.drawable,))
        self.assertEqual(document.to_model().name, "fragment")
        self.assertEqual(document.to_model().bounding_box.minimum, (-1.0, -2.0, -3.0))

    def test_loads_stream_and_preserves_resource_losslessly(self) -> None:
        source = _sample_wft()
        document = load_wft(io.BytesIO(source))

        self.assertEqual(document.to_bytes(), source)

    def test_rejects_other_rsc5_resource_versions(self) -> None:
        source = bytearray(_sample_wft())
        struct.pack_into("<I", source, 4, 0x6E)

        with self.assertRaisesRegex(ValueError, "unsupported WFT resource version"):
            WftDocument.from_bytes(bytes(source))


if __name__ == "__main__":
    unittest.main()
