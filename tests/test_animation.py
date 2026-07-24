from __future__ import annotations

import unittest

from fourfury import UvAnimationClip, UvAnimationFrame, UvTransform


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


if __name__ == "__main__":
    unittest.main()
