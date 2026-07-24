from __future__ import annotations

import io
import struct
import unittest
import zlib
from dataclasses import replace

from fourfury import (
    WAD_RESOURCE_VERSION,
    WadAnimation,
    WadAnimationFlags,
    WadBoneId,
    WadBoneName,
    WadChannelType,
    WadChannel,
    WadChunk,
    WadDocument,
    WadTrack,
    WadTrackId,
    WadTrackKind,
    joaat,
    load_wad,
    wad_animation_hash,
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


def _sample_uv_wad() -> bytes:
    source = _sample_wad()
    virtual = bytearray(zlib.decompress(source[12:]))
    struct.pack_into("<I", virtual, 0x100, joaat("television_uv_2"))
    virtual[0x180:0x200] = b"\0" * 0x80
    name = b"pack:/television_uv_2.anim\0"
    virtual[0x180 : 0x180 + len(name)] = name
    struct.pack_into("<BBH", virtual, 0x300, WadTrackId.SHADER_SLIDE_U, 0, 0)
    struct.pack_into("<BBH", virtual, 0x320, WadTrackId.SHADER_SLIDE_V, 0, 0)
    struct.pack_into("<3f", virtual, 0x700, 1.0, 1.0, 1.0)
    struct.pack_into(
        "<IBBHf",
        virtual,
        0x430,
        0x6AF77C,
        0,
        WadChannelType.STATIC_FLOAT,
        0,
        0.0,
    )
    struct.pack_into(
        "<IBBHIHH",
        virtual,
        0x460,
        0x6AF92C,
        0,
        WadChannelType.RAW_FLOAT,
        0,
        _pointer(0x820),
        3,
        3,
    )
    struct.pack_into("<3f", virtual, 0x820, 0.0, 1.0, 2.0)
    struct.pack_into("<4f", virtual, 0x780, 0.0, 1.0, 0.0, 0.0)
    return source[:12] + zlib.compress(virtual)


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

    def test_projects_selected_logical_tracks_into_neutral_frames(self) -> None:
        animation = WadDocument.from_bytes(_sample_wad()).animations[0]

        self.assertEqual(
            tuple(target.key for target in animation.targets),
            (
                (417, int(WadTrackId.BONE_TRANSLATION)),
                (417, int(WadTrackId.BONE_ROTATION)),
                (0, int(WadTrackId.ACTION_FLAGS)),
            ),
        )
        self.assertEqual(tuple(animation.iter_tracks()), animation.targets)
        self.assertEqual(
            animation.evaluate_tracks(
                1,
                track_ids=(
                    WadTrackId.BONE_TRANSLATION,
                    WadTrackId.BONE_ROTATION,
                ),
            ),
            {
                (417, int(WadTrackId.BONE_TRANSLATION)): (2.0, 11.0, 5.0),
                (417, int(WadTrackId.BONE_ROTATION)): (0.0, 0.0, 0.0, 1.0),
            },
        )
        sampled = animation.sample_tracks(
            1.0 / 60.0,
            track_ids=(WadTrackId.BONE_TRANSLATION,),
        )
        sampled_translation = sampled[
            (417, int(WadTrackId.BONE_TRANSLATION))
        ]
        assert isinstance(sampled_translation, tuple)
        self.assertAlmostEqual(sampled_translation[0], 1.5)
        self.assertAlmostEqual(sampled_translation[1], 10.5)
        self.assertAlmostEqual(sampled_translation[2], 5.0)

        clip = animation.to_track_animation(
            track_ids=(
                WadTrackId.BONE_TRANSLATION,
                WadTrackId.BONE_ROTATION,
            ),
        )
        self.assertEqual(clip.name, "walk")
        self.assertEqual(clip.frame_count, 3)
        self.assertEqual(len(clip.targets), 2)
        self.assertEqual(
            clip.frames[1].get(417, WadTrackId.BONE_TRANSLATION).value,  # type: ignore[union-attr]
            (2.0, 11.0, 5.0),
        )
        self.assertEqual(
            animation.to_data(
                track_ids=(WadTrackId.BONE_TRANSLATION,),
            )["name"],
            "walk",
        )

    def test_classifies_and_audits_logical_track_families(self) -> None:
        document = WadDocument.from_bytes(_sample_wad(), name="sample.wad")
        animation = document.animations[0]

        self.assertEqual(
            animation.kinds,
            (WadTrackKind.SKELETAL, WadTrackKind.ACTION),
        )
        self.assertTrue(animation.has_skeletal_tracks)
        self.assertTrue(animation.has_action_tracks)
        self.assertFalse(animation.has_material_tracks)
        self.assertFalse(animation.has_morph_tracks)
        self.assertFalse(animation.has_camera_tracks)
        self.assertFalse(animation.has_light_tracks)
        self.assertFalse(animation.has_custom_tracks)
        self.assertEqual(animation.validate(), ())

        report = document.audit()

        self.assertTrue(report.is_valid)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)
        self.assertEqual(report.animation_count, 1)
        self.assertEqual(report.track_group_count, 1)
        self.assertEqual(report.target_count, 3)
        self.assertEqual(report.channel_count, 6)
        self.assertEqual(report.track_kinds, {"action": 1, "skeletal": 2})
        self.assertEqual(report.custom_track_ids, ())
        self.assertEqual(report.to_data()["is_valid"], True)

    def test_reports_custom_tracks_and_inconsistent_group_layouts(self) -> None:
        skeletal = WadChunk(
            WadBoneId(WadTrackId.BONE_TRANSLATION, 0, 417),
            (WadChannel(WadChannelType.STATIC_VECTOR3, 0, vector=(0.0, 0.0, 0.0)),),
        )
        custom = WadChunk(
            WadBoneId(143, 2, 0),
            (WadChannel(WadChannelType.STATIC_FLOAT, 0, (1.0,)),),
        )
        animation = WadAnimation(
            "pack:/custom.anim",
            WadAnimationFlags.NONE,
            0,
            4,
            2,
            1.0,
            0,
            (
                WadTrack((skeletal, custom), skeletal.bone_id, 3, 0),
                WadTrack((skeletal,), skeletal.bone_id, 2, 0),
            ),
        )

        self.assertEqual(
            animation.kinds,
            (WadTrackKind.SKELETAL, WadTrackKind.CUSTOM),
        )
        self.assertTrue(animation.has_custom_tracks)
        issues = animation.validate()
        self.assertEqual(
            {issue.code for issue in issues},
            {"inconsistent_targets"},
        )

    def test_uses_inclusive_sequence_limit_for_track_group_boundaries(self) -> None:
        identifier = WadBoneId(WadTrackId.BONE_TRANSLATION, 2, 417)
        first = WadChunk(
            identifier,
            (WadChannel(WadChannelType.RAW_FLOAT, 0, (10.0, 11.0, 12.0)),),
        )
        second = WadChunk(
            identifier,
            (WadChannel(WadChannelType.RAW_FLOAT, 0, (12.0, 13.0)),),
        )
        animation = WadAnimation(
            "pack:/groups.anim",
            WadAnimationFlags.NONE,
            0,
            4,
            2,
            1.0,
            0,
            (
                WadTrack((first,), identifier, 3, 0),
                WadTrack((second,), identifier, 2, 0),
            ),
        )

        self.assertEqual(animation.frames_per_group, 3)
        self.assertEqual(animation.frame_group_stride, 2)
        self.assertEqual(animation.vector_at(1, 417), (11.0, 0.0, 0.0, 0.0))
        self.assertEqual(animation.vector_at(2, 417), (12.0, 0.0, 0.0, 0.0))
        self.assertEqual(animation.vector_at(3, 417), (13.0, 0.0, 0.0, 0.0))
        self.assertEqual(animation.validate(), ())

    def test_resolves_stock_uv_dictionary_hash_convention(self) -> None:
        source = _sample_uv_wad()
        virtual = bytearray(zlib.decompress(source[12:]))
        canonical_hash = wad_animation_hash("pack:/television_uv_2.anim")
        struct.pack_into("<I", virtual, 0x100, canonical_hash)
        document = WadDocument.from_bytes(source[:12] + zlib.compress(virtual))

        self.assertEqual(canonical_hash, (joaat("television") + 3) & 0xFFFFFFFF)
        self.assertIsNotNone(document.find_animation("television_uv_2"))
        self.assertEqual(document.validate(), ())

    def test_defers_sampled_channel_materialization(self) -> None:
        animation = WadDocument.from_bytes(_sample_wad()).animations[0]
        translation = animation.tracks[0].chunks[0]
        raw, quantized, _static = translation.channels

        self.assertEqual(raw._values, ())
        self.assertEqual(quantized._values, ())
        self.assertEqual(quantized._quantized_values, ())
        self.assertEqual(raw.value_at(1), 2.0)
        self.assertEqual(quantized.value_at(1), 11.0)
        self.assertEqual(raw._values, ())
        self.assertEqual(quantized._values, ())
        self.assertEqual(quantized._quantized_values, ())
        self.assertEqual(quantized.values, (10.0, 11.0, 12.0))
        self.assertEqual(quantized.quantized_values, (0, 1, 2))
        self.assertEqual(
            quantized,
            WadChannel(
                WadChannelType.QUANTIZED_FLOAT,
                quantized.flags,
                (10.0, 11.0, 12.0),
                scale=quantized.scale,
                offset=quantized.offset,
                quantized_values=(0, 1, 2),
            ),
        )

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
        self.assertEqual(action.bone_id.track, WadTrackId.ACTION_FLAGS)
        self.assertFalse(action.bone_id.is_skeletal_transform)

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

    def test_models_skeletal_targets_independently_from_chunk_encoding(self) -> None:
        compact = WadBoneId(WadTrackId.BONE_ROTATION, 0x11, 417)
        raw = WadBoneId(WadTrackId.BONE_ROTATION, 0x01, 417)

        self.assertTrue(compact.targets(raw))
        self.assertEqual(compact.target_key, (417, int(WadTrackId.BONE_ROTATION)))
        self.assertTrue(compact.is_bone_transform)
        self.assertTrue(compact.is_skeletal_transform)
        self.assertTrue(compact.is_rotation)
        self.assertFalse(compact.is_mover_transform)

    def test_samples_skeletal_quaternions_normalized_over_the_shortest_path(self) -> None:
        identifier = WadBoneId(WadTrackId.BONE_ROTATION, 0x11, 417)
        chunk = WadChunk(
            identifier,
            (
                WadChannel(WadChannelType.RAW_FLOAT, 0, (0.0, 0.0)),
                WadChannel(WadChannelType.RAW_FLOAT, 0, (0.0, 0.0)),
                WadChannel(WadChannelType.RAW_FLOAT, 0, (0.0, 0.0)),
                WadChannel(WadChannelType.RAW_FLOAT, 0, (2.0, -4.0)),
            ),
        )
        animation = WadAnimation(
            "pack:/turn.anim",
            WadAnimationFlags.NONE,
            0,
            2,
            2,
            1.0,
            0,
            (WadTrack((chunk,), identifier, 2, 0),),
        )

        self.assertEqual(
            animation.sample(0.5, 417, WadTrackId.BONE_ROTATION),
            (0.0, 0.0, 0.0, 1.0),
        )
        self.assertEqual(animation.skeletal_bone_ids, (417,))

    def test_projects_complete_skeletal_poses_into_the_neutral_contract(self) -> None:
        animation = WadDocument.from_bytes(_sample_wad()).animations[0]

        pose = animation.skeletal_pose_at(1)
        pelvis = pose.get_bone(417)
        assert pelvis is not None
        self.assertEqual(pose.bone_ids, (417,))
        self.assertEqual(pelvis.translation, (2.0, 11.0, 5.0))
        self.assertEqual(pelvis.rotation, (0.0, 0.0, 0.0, 1.0))
        self.assertFalse(pelvis.has_root_motion)

        sampled = animation.sample_skeletal(1.0 / 60.0)
        sampled_pelvis = sampled.get_bone(417)
        assert sampled_pelvis is not None
        self.assertAlmostEqual(sampled_pelvis.translation[0], 1.5)  # type: ignore[index]

        clip = animation.to_skeletal_animation()
        self.assertEqual(tuple(animation.iter_skeletal_poses()), clip.frames)
        self.assertEqual(clip.name, "walk")
        self.assertEqual(clip.frame_count, 3)
        self.assertEqual(clip.bone_ids, (417,))
        self.assertEqual(clip.signature, animation.signature)
        self.assertEqual(clip.to_data()["name"], "walk")

    def test_recognizes_exporter_uv_animation_name_convention(self) -> None:
        animation = WadDocument.from_bytes(_sample_wad()).animations[0]

        self.assertFalse(animation.is_uv_animation)
        self.assertIsNone(animation.uv_material_index)
        self.assertIsNone(animation.uv_base_name)

        animation = replace(animation, name="pack:/television_uv_12.anim")
        self.assertTrue(animation.is_uv_animation)
        self.assertEqual(animation.uv_material_index, 12)
        self.assertEqual(animation.uv_base_name, "television")

    def test_projects_uv_rows_into_the_neutral_animation_contract(self) -> None:
        animation = WadDocument.from_bytes(_sample_uv_wad()).animations[0]

        clip = animation.to_uv_animation()

        self.assertEqual(clip.name, "television")
        self.assertEqual(clip.target_index, 2)
        self.assertEqual(clip.frame_count, 3)
        self.assertEqual(clip.frames[0].transform.row_u, (1.0, 0.0, 0.0, 0.0))
        self.assertEqual(clip.frames[2].transform.row_u, (1.0, 0.0, 2.0, 0.0))
        self.assertEqual(clip.frames[2].transform.row_v, (0.0, 1.0, 0.0, 0.0))
        sampled_uv = clip.sample(1.0 / 60.0).apply((0.25, 0.75))
        self.assertAlmostEqual(sampled_uv[0], 0.75)
        self.assertAlmostEqual(sampled_uv[1], 0.75)
        self.assertEqual(clip.to_data()["name"], "television")

    def test_uv_projection_requires_rows_and_a_target_index(self) -> None:
        animation = WadDocument.from_bytes(_sample_wad()).animations[0]

        with self.assertRaisesRegex(ValueError, "material index"):
            animation.to_uv_animation()
        with self.assertRaisesRegex(ValueError, "no UV matrix-row tracks"):
            animation.to_uv_animation(material_index=0)

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
