from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import TypeAlias


UvVector2: TypeAlias = tuple[float, float]
UvVector4: TypeAlias = tuple[float, float, float, float]
UvMatrix3: TypeAlias = tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
]


@dataclass(frozen=True, slots=True)
class UvTransform:
    """Target-independent affine UV transform stored as two RAGE-style rows."""

    row_u: UvVector4 = (1.0, 0.0, 0.0, 0.0)
    row_v: UvVector4 = (0.0, 1.0, 0.0, 0.0)

    @classmethod
    def identity(cls) -> UvTransform:
        return cls()

    def apply(self, uv: UvVector2) -> UvVector2:
        u, v = uv
        return (
            (self.row_u[0] * u) + (self.row_u[1] * v) + self.row_u[2],
            (self.row_v[0] * u) + (self.row_v[1] * v) + self.row_v[2],
        )

    def interpolate(self, other: UvTransform, alpha: float) -> UvTransform:
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("UV interpolation alpha must be between zero and one")

        def row(start: UvVector4, end: UvVector4) -> UvVector4:
            return tuple(
                left + ((right - left) * alpha)
                for left, right in zip(start, end, strict=True)
            )  # type: ignore[return-value]

        return UvTransform(row(self.row_u, other.row_u), row(self.row_v, other.row_v))

    def to_matrix3(self) -> UvMatrix3:
        return (
            self.row_u[0],
            self.row_u[1],
            self.row_u[2],
            self.row_v[0],
            self.row_v[1],
            self.row_v[2],
            0.0,
            0.0,
            1.0,
        )

    def to_data(self) -> dict[str, list[float]]:
        return {"row_u": list(self.row_u), "row_v": list(self.row_v)}


@dataclass(frozen=True, slots=True)
class UvAnimationFrame:
    time: float
    transform: UvTransform

    def to_data(self) -> dict[str, object]:
        return {"time": self.time, "transform": self.transform.to_data()}


@dataclass(frozen=True, slots=True)
class UvAnimationClip:
    """Format-neutral UV animation ready for converters and other tooling."""

    name: str
    target_index: int
    duration: float
    looping: bool
    frames: tuple[UvAnimationFrame, ...]

    def __post_init__(self) -> None:
        if self.target_index < 0:
            raise ValueError("UV animation target index cannot be negative")
        if self.duration < 0.0:
            raise ValueError("UV animation duration cannot be negative")
        if not self.frames:
            raise ValueError("UV animation must contain at least one frame")
        previous = -1.0
        for frame in self.frames:
            if frame.time < 0.0 or frame.time < previous:
                raise ValueError("UV animation frame times must be non-negative and ordered")
            previous = frame.time
        if self.frames[-1].time > self.duration:
            raise ValueError("UV animation frame time exceeds its duration")

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def material_index(self) -> int:
        """Compatibility name for GTA IV's material-index target."""

        return self.target_index

    def sample(self, time: float, *, loop: bool | None = None) -> UvTransform:
        if time < 0.0:
            raise ValueError("UV animation time cannot be negative")
        if len(self.frames) == 1 or self.duration <= 0.0:
            return self.frames[0].transform
        should_loop = self.looping if loop is None else loop
        if should_loop:
            time %= self.duration
        else:
            time = min(time, self.duration)
        times = tuple(frame.time for frame in self.frames)
        upper = bisect_right(times, time)
        if upper == 0:
            return self.frames[0].transform
        if upper >= len(self.frames):
            return self.frames[-1].transform
        frame0 = self.frames[upper - 1]
        frame1 = self.frames[upper]
        span = frame1.time - frame0.time
        alpha = 0.0 if span <= 0.0 else (time - frame0.time) / span
        return frame0.transform.interpolate(frame1.transform, alpha)

    def to_data(self) -> dict[str, object]:
        return {
            "name": self.name,
            "target_index": self.target_index,
            "duration": self.duration,
            "looping": self.looping,
            "frames": [frame.to_data() for frame in self.frames],
        }


__all__ = [
    "UvAnimationClip",
    "UvAnimationFrame",
    "UvMatrix3",
    "UvTransform",
    "UvVector2",
    "UvVector4",
]
