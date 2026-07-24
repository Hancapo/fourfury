from __future__ import annotations

import unittest

from fourfury import (
    AnimationTrackFrame,
    AnimationTrackInterpolation,
    AnimationTrackTarget,
    AnimationTrackValue,
    SkeletalAnimationClip,
    SkeletalBonePose,
    SkeletalPose,
    SkeletalTransform,
    TrackAnimationClip,
    UvAnimationClip,
    UvAnimationFrame,
    UvTransform,
    interpolate_quaternion,
    normalize_quaternion,
)


class UvAnimationTests(unittest.TestCase):
    def test_applies_interpolates_and_serializes_neutral_uv_transforms(self) -> None:
        start = UvTransform()
        end = UvTransform((2.0, 0.0, 1.0, 0.0), (0.0, 3.0, -1.0, 0.0))
        clip = UvAnimationClip(
            "screen",
            2,
            1.0,
            False,
            (UvAnimationFrame(0.0, start), UvAnimationFrame(1.0, end)),
        )

        middle = clip.sample(0.5)

        self.assertEqual(middle.row_u, (1.5, 0.0, 0.5, 0.0))
        self.assertEqual(middle.row_v, (0.0, 2.0, -0.5, 0.0))
        self.assertEqual(middle.apply((2.0, 3.0)), (3.5, 5.5))
        self.assertEqual(
            middle.to_matrix3(),
            (1.5, 0.0, 0.5, 0.0, 2.0, -0.5, 0.0, 0.0, 1.0),
        )
        self.assertEqual(clip.material_index, 2)
        self.assertEqual(clip.to_data()["target_index"], 2)

    def test_loops_and_validates_frame_data(self) -> None:
        first = UvAnimationFrame(0.0, UvTransform())
        last = UvAnimationFrame(
            1.0,
            UvTransform((1.0, 0.0, 2.0, 0.0), (0.0, 1.0, 0.0, 0.0)),
        )
        clip = UvAnimationClip("loop", 0, 1.0, True, (first, last))

        self.assertEqual(clip.sample(1.25), clip.sample(0.25))
        with self.assertRaisesRegex(ValueError, "ordered"):
            UvAnimationClip("bad", 0, 1.0, False, (last, first))


class QuaternionTests(unittest.TestCase):
    def test_normalizes_and_interpolates_over_the_shortest_path(self) -> None:
        self.assertEqual(normalize_quaternion((0.0, 0.0, 0.0, 0.0)), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(
            interpolate_quaternion(
                (0.0, 0.0, 0.0, 2.0),
                (0.0, 0.0, 0.0, -4.0),
                0.5,
            ),
            (0.0, 0.0, 0.0, 1.0),
        )


class TrackAnimationTests(unittest.TestCase):
    def test_interpolates_arbitrary_tracks_by_declared_policy(self) -> None:
        position = AnimationTrackTarget(
            1,
            0,
            3,
            AnimationTrackInterpolation.LINEAR,
            "root",
            "position",
        )
        state = AnimationTrackTarget(
            0,
            128,
            1,
            AnimationTrackInterpolation.STEP,
            track_name="action_flags",
        )
        first = AnimationTrackFrame(
            0.0,
            (
                AnimationTrackValue(position, (0.0, 0.0, 0.0)),
                AnimationTrackValue(state, 4),
            ),
        )
        last = AnimationTrackFrame(
            1.0,
            (
                AnimationTrackValue(position, (2.0, 4.0, 6.0)),
                AnimationTrackValue(state, 8),
            ),
        )
        clip = TrackAnimationClip(
            "generic",
            1.0,
            False,
            (position, state),
            (first, last),
            0x1234,
        )

        middle = clip.sample(0.5)

        self.assertEqual(middle.get(1, 0).value, (1.0, 2.0, 3.0))  # type: ignore[union-attr]
        self.assertEqual(middle.get(0, 128).value, 4)  # type: ignore[union-attr]
        self.assertIs(clip.get_target(1, 0), position)
        self.assertEqual(clip.to_data()["signature"], 0x1234)

    def test_rejects_incompatible_track_values(self) -> None:
        target = AnimationTrackTarget(
            1,
            0,
            3,
            AnimationTrackInterpolation.LINEAR,
        )

        with self.assertRaisesRegex(ValueError, "expects 3 components"):
            AnimationTrackValue(target, (1.0, 2.0))


class SkeletalAnimationTests(unittest.TestCase):
    def test_interpolates_optional_bone_and_root_motion_components(self) -> None:
        first = SkeletalPose(
            0.0,
            (
                SkeletalBonePose(
                    417,
                    SkeletalTransform(
                        translation=(0.0, 0.0, 0.0),
                        rotation=(0.0, 0.0, 0.0, 1.0),
                    ),
                    SkeletalTransform(translation=(0.0, 0.0, 0.0)),
                ),
            ),
        )
        last = SkeletalPose(
            1.0,
            (
                SkeletalBonePose(
                    417,
                    SkeletalTransform(
                        translation=(2.0, 0.0, 0.0),
                        rotation=(0.0, 0.0, 1.0, 0.0),
                        scale=(2.0, 2.0, 2.0),
                    ),
                    SkeletalTransform(translation=(0.0, 4.0, 0.0)),
                ),
            ),
        )
        clip = SkeletalAnimationClip("walk", 1.0, False, (first, last), 0x1234)

        pose = clip.sample(0.5)
        bone = pose.get_bone(417)
        assert bone is not None
        self.assertEqual(bone.translation, (1.0, 0.0, 0.0))
        self.assertEqual(bone.scale, (2.0, 2.0, 2.0))
        self.assertAlmostEqual(bone.rotation[2], 2 ** -0.5)  # type: ignore[index]
        self.assertAlmostEqual(bone.rotation[3], 2 ** -0.5)  # type: ignore[index]
        self.assertEqual(bone.mover_transform.translation, (0.0, 2.0, 0.0))
        self.assertEqual(pose.root_motion_bones, (bone,))
        self.assertEqual(clip.to_data()["signature"], 0x1234)

    def test_rejects_incompatible_pose_layouts(self) -> None:
        transform = SkeletalTransform(translation=(0.0, 0.0, 0.0))
        first = SkeletalPose(0.0, (SkeletalBonePose(1, transform),))
        other = SkeletalPose(1.0, (SkeletalBonePose(2, transform),))

        with self.assertRaisesRegex(ValueError, "ordered bones"):
            first.interpolate(other, 0.5)


if __name__ == "__main__":
    unittest.main()
