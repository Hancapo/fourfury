from __future__ import annotations

import io
import struct
import unittest
import zlib
from dataclasses import replace

from fourfury import (
    WAD_RESOURCE_VERSION,
    WadAnimationFlags,
    WadBoneId,
    WadBoneName,
    WadChannelType,
    WadDocument,
    WadTrackId,
    joaat,
    load_wad,
)


VIRTUAL_BASE = 0x50000000


def _pointer(offset: int) -> int:
    return VIRTUAL_BASE | offset


def _sample_wad(*, hash_count: int = 1, animation_count: int = 1) -> bytes:
    virtual = bytearray(0x1000)
    struct.pack_into("<4I", virtual, 0, 0x695374, 0, 0, 1)
    struct.pack_into("<IHH", virtual, 0x10, _pointer(0x100), hash_count, hash_count)
    struct.pack_into(
        "<IHH",
        virtual,
        0x18,
        _pointer(0x110),
        animation_count,
        animation_count,
    )
    struct.pack_into("<I", virtual, 0x100, joaat("walk"))
    struct.pack_into("<I", virtual, 0x110, _pointer(0x200))
    struct.pack_into("<I", virtual, 0x120, _pointer(0x240))
    struct.pack_into("<3I", virtual, 0x130, _pointer(0x300), _pointer(0x320), _pointer(0x340))
    virtual[0x180 : 0x190] = b"pack:/walk.anim\0"

    struct.pack_into(
        "<I4HfI",
        virtual,
        0x200,
        0x6AEF64,
        int(WadAnimationFlags.LOOPED),
        0x1F1,
        3,
        3,
        2.0 / 30.0,
        0x815B97EA,
    )
    struct.pack_into("<IHHI", virtual, 0x214, _pointer(0x120), 1, 1, _pointer(0x180))

    struct.pack_into(
        "<IHHBBHHH",
        virtual,
        0x240,
        _pointer(0x130),
        3,
        3,
        0,
        0,
        0,
        3,
        0,
    )

    struct.pack_into(
        "<BBH4I",
        virtual,
        0x300,
        0,
        0,
        417,
        _pointer(0x400),
        _pointer(0x430),
        _pointer(0x460),
        0,
    )
    struct.pack_into("<BBH4I", virtual, 0x320, 1, 1, 417, _pointer(0x480), 0, 0, 0)
    struct.pack_into("<BBH4I", virtual, 0x340, 128, 3, 0, _pointer(0x500), _pointer(0x530), 0, 0)

    struct.pack_into(
        "<IBBHIHH",
        virtual,
        0x400,
        0x6AF92C,
        0,
        WadChannelType.RAW_FLOAT,
        0,
        _pointer(0x700),
        3,
        3,
    )
    struct.pack_into("<3f", virtual, 0x700, 1.0, 2.0, 3.0)

    struct.pack_into(
        "<IBBHIIIff",
        virtual,
        0x430,
        0x6AFDDC,
        0,
        WadChannelType.QUANTIZED_FLOAT,
        0,
        _pointer(0x740),
        2,
        3,
        1.0,
        10.0,
    )
    struct.pack_into("<2I", virtual, 0x740, 0b100100, 0)

    struct.pack_into("<IBBHf", virtual, 0x460, 0x6AF77C, 0, WadChannelType.STATIC_FLOAT, 0, 5.0)
    struct.pack_into("<IBBHI", virtual, 0x480, 0x6AF86C, 0, WadChannelType.STATIC_QUATERNION, 0, _pointer(0x780))
    struct.pack_into("<4f", virtual, 0x780, 0.0, 0.0, 0.0, 1.0)

    struct.pack_into(
        "<IBBHIHHIII",
        virtual,
        0x500,
        0x6AFE7C,
        0,
        WadChannelType.RLE_INT,
        0,
        _pointer(0x760),
        2,
        2,
        _pointer(0x770),
        8,
        2,
    )
    struct.pack_into("<2i", virtual, 0x760, 2048, 0)
    struct.pack_into("<I", virtual, 0x770, 0b0111)

    struct.pack_into(
        "<IBBHIHH",
        virtual,
        0x530,
        0x6AF98C,
        0,
        WadChannelType.RAW_INT,
        0,
        _pointer(0x800),
        3,
        3,
    )
    struct.pack_into("<3i", virtual, 0x800, 7, 8, 9)

    flags = 0xC0000010
    return struct.pack("<4sII", b"RSC\x05", WAD_RESOURCE_VERSION, flags) + zlib.compress(
        virtual
    )


class WadTests(unittest.TestCase):
    def test_reads_dictionary_animation_tracks_and_channels(self) -> None:
        document = WadDocument.from_bytes(_sample_wad(), name="sample.wad")

        self.assertEqual(len(document), 1)
        self.assertEqual(document.hashes, (joaat("walk"),))
        self.assertIs(document["walk"], document["pack:/walk.anim"])
        animation = document.find_animation("walk")
        assert animation is not None
        self.assertEqual(animation.name, "pack:/walk.anim")
        self.assertEqual(animation.short_name, "walk")
        self.assertEqual(animation.frame_count, 3)
        self.assertAlmostEqual(animation.frame_rate, 30.0, places=5)
        self.assertEqual(len(animation.tracks), 1)
        self.assertEqual(len(animation.bone_ids), 3)

        translation = animation.tracks[0].chunks[0]
        self.assertEqual(translation.bone_id.track, WadTrackId.BONE_TRANSLATION)
        self.assertEqual(translation.bone_id.bone, WadBoneName.CHAR_PELVIS)
        self.assertEqual(translation.bone_id.track_name, "BONE_TRANSLATION")
        self.assertEqual(translation.bone_id.bone_name, "CHAR_PELVIS")
        self.assertEqual(translation.bone_id.type_name, "VECTOR3")
        self.assertEqual(
            [channel.channel_type for channel in translation.channels],
            [
                WadChannelType.RAW_FLOAT,
                WadChannelType.QUANTIZED_FLOAT,
                WadChannelType.STATIC_FLOAT,
            ],
        )
        self.assertEqual(translation.channels[1].quantized_values, (0, 1, 2))
        self.assertEqual(translation.channels[1].values, (10.0, 11.0, 12.0))

    def test_evaluates_scalar_vector_and_quaternion_channels(self) -> None:
        animation = WadDocument.from_bytes(_sample_wad()).animations[0]

        self.assertEqual(
            animation.vector_at(1, 417, WadTrackId.BONE_TRANSLATION),
            (2.0, 11.0, 5.0, 0.0),
        )
        self.assertEqual(
            animation.vector_at(2, 417, WadTrackId.BONE_ROTATION),
            (0.0, 0.0, 0.0, 1.0),
        )
        sampled = animation.sample(1.0 / 60.0, 417, WadTrackId.BONE_TRANSLATION)
        self.assertAlmostEqual(sampled[0], 1.5)
        self.assertAlmostEqual(sampled[1], 10.5)
        self.assertAlmostEqual(sampled[2], 5.0)

    def test_exposes_raw_integer_and_packed_rle_data(self) -> None:
        action = WadDocument.from_bytes(_sample_wad()).animations[0].tracks[0].chunks[2]
        rle, raw = action.channels

        self.assertEqual(rle.run_values, (2048, 0))
        self.assertEqual(rle.packed_sequence, (3,))
        self.assertEqual(rle.packed_sequence_words, (0b0111,))
        self.assertEqual(rle.packed_sequence_bit_count, 8)
        self.assertEqual(rle.packed_sequence_divisor, 2)
        with self.assertRaisesRegex(NotImplementedError, "timing expansion"):
            rle.value_at(0)
        self.assertEqual(raw.values, (7, 8, 9))
        self.assertEqual(raw.value_at(1), 8)

    def test_models_uv_identity_without_misclassifying_it_as_integer(self) -> None:
        identifier = WadBoneId(WadTrackId.SHADER_SLIDE_U, 0xFF, 3)

        self.assertTrue(identifier.is_uv_channel)
        self.assertEqual(identifier.uv_index, 3)
        self.assertIsNone(identifier.track_type)
        self.assertIsNone(identifier.packing)
        self.assertEqual(identifier.type_name, "UV")
        self.assertEqual(identifier.track_name, "SHADER_SLIDE_U")
        self.assertEqual(identifier.bone_name, "UV_3")
        self.assertEqual(
            WadBoneId(WadTrackId.SHADER_SLIDE_V, 0, 417).bind_uv(5),
            WadBoneId(WadTrackId.SHADER_SLIDE_V, 0xFF, 5),
        )
        with self.assertRaisesRegex(ValueError, "unsigned 16-bit"):
            identifier.bind_uv(0x10000)

    def test_recognizes_exporter_uv_animation_name_convention(self) -> None:
        animation = WadDocument.from_bytes(_sample_wad()).animations[0]

        self.assertFalse(animation.is_uv_animation)
        self.assertIsNone(animation.uv_material_index)
        self.assertIsNone(animation.uv_base_name)

        animation = replace(animation, name="pack:/television_uv_12.anim")
        self.assertTrue(animation.is_uv_animation)
        self.assertEqual(animation.uv_material_index, 12)
        self.assertEqual(animation.uv_base_name, "television")

    def test_loads_stream_and_preserves_resource_losslessly(self) -> None:
        source = _sample_wad()
        document = load_wad(io.BytesIO(source))

        self.assertEqual(document.to_bytes(), source)

    def test_rejects_mismatched_parallel_arrays(self) -> None:
        with self.assertRaisesRegex(ValueError, "hash and animation counts do not match"):
            WadDocument.from_bytes(_sample_wad(hash_count=1, animation_count=0))

    def test_rejects_other_rsc5_resource_versions(self) -> None:
        source = bytearray(_sample_wad())
        struct.pack_into("<I", source, 4, 2)

        with self.assertRaisesRegex(ValueError, "unsupported WAD resource version"):
            WadDocument.from_bytes(bytes(source))


if __name__ == "__main__":
    unittest.main()
