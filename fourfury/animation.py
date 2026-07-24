from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from operator import attrgetter
from typing import TypeAlias


UvVector2: TypeAlias = tuple[float, float]
UvVector4: TypeAlias = tuple[float, float, float, float]
Vector3: TypeAlias = tuple[float, float, float]
Quaternion: TypeAlias = tuple[float, float, float, float]
SkeletalMatrix4: TypeAlias = tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    float,
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
_FRAME_TIME = attrgetter("time")


def normalize_quaternion(value: Quaternion) -> Quaternion:
    """Return a unit quaternion, using identity for a zero-length value."""

    x, y, z, w = value
    length_squared = (x * x) + (y * y) + (z * z) + (w * w)
    if length_squared <= 0.0:
        return (0.0, 0.0, 0.0, 1.0)
    inverse_length = length_squared ** -0.5
    return (
        x * inverse_length,
        y * inverse_length,
        z * inverse_length,
        w * inverse_length,
    )


def interpolate_quaternion(
    start: Quaternion,
    end: Quaternion,
    alpha: float,
) -> Quaternion:
    """Shortest-path normalized linear interpolation between two quaternions."""

    if not 0.0 <= alpha <= 1.0:
        raise ValueError("quaternion interpolation alpha must be between zero and one")
    ax, ay, az, aw = normalize_quaternion(start)
    bx, by, bz, bw = normalize_quaternion(end)
    dot = (ax * bx) + (ay * by) + (az * bz) + (aw * bw)
    if dot < 0.0:
        bx, by, bz, bw = -bx, -by, -bz, -bw
    return normalize_quaternion(
        (
            ax + ((bx - ax) * alpha),
            ay + ((by - ay) * alpha),
            az + ((bz - az) * alpha),
            aw + ((bw - aw) * alpha),
        )
    )


@dataclass(frozen=True, slots=True)
class SkeletalTransform:
    """Optional local transform components for one skeletal target."""

    translation: Vector3 | None = None
    rotation: Quaternion | None = None
    scale: Vector3 | None = None

    def __post_init__(self) -> None:
        if self.rotation is not None:
            object.__setattr__(self, "rotation", normalize_quaternion(self.rotation))

    @property
    def is_empty(self) -> bool:
        return (
            self.translation is None
            and self.rotation is None
            and self.scale is None
        )

    def interpolate(
        self,
        other: SkeletalTransform,
        alpha: float,
    ) -> SkeletalTransform:
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("skeletal interpolation alpha must be between zero and one")

        def vector(
            start: Vector3 | None,
            end: Vector3 | None,
        ) -> Vector3 | None:
            if start is None:
                return end
            if end is None:
                return start
            return tuple(
                left + ((right - left) * alpha)
                for left, right in zip(start, end, strict=True)
            )  # type: ignore[return-value]

        if self.rotation is None:
            rotation = other.rotation
        elif other.rotation is None:
            rotation = self.rotation
        else:
            rotation = interpolate_quaternion(self.rotation, other.rotation, alpha)
        return SkeletalTransform(
            translation=vector(self.translation, other.translation),
            rotation=rotation,
            scale=vector(self.scale, other.scale),
        )

    def to_data(self) -> dict[str, list[float] | None]:
        return {
            "translation": (
                None if self.translation is None else list(self.translation)
            ),
            "rotation": None if self.rotation is None else list(self.rotation),
            "scale": None if self.scale is None else list(self.scale),
        }


@dataclass(frozen=True, slots=True)
class SkeletalBonePose:
    bone_id: int
    transform: SkeletalTransform = SkeletalTransform()
    mover_transform: SkeletalTransform = SkeletalTransform()

    def __post_init__(self) -> None:
        if self.bone_id < 0:
            raise ValueError("skeletal bone ID cannot be negative")
        if self.transform.is_empty and self.mover_transform.is_empty:
            raise ValueError("skeletal bone pose must contain at least one transform")

    @property
    def translation(self) -> Vector3 | None:
        return self.transform.translation

    @property
    def rotation(self) -> Quaternion | None:
        return self.transform.rotation

    @property
    def scale(self) -> Vector3 | None:
        return self.transform.scale

    @property
    def has_root_motion(self) -> bool:
        return not self.mover_transform.is_empty

    def interpolate(
        self,
        other: SkeletalBonePose,
        alpha: float,
    ) -> SkeletalBonePose:
        if self.bone_id != other.bone_id:
            raise ValueError("cannot interpolate poses for different skeletal bones")
        return SkeletalBonePose(
            self.bone_id,
            self.transform.interpolate(other.transform, alpha),
            self.mover_transform.interpolate(other.mover_transform, alpha),
        )

    def to_data(self) -> dict[str, object]:
        return {
            "bone_id": self.bone_id,
            "transform": self.transform.to_data(),
            "mover_transform": self.mover_transform.to_data(),
        }


@dataclass(frozen=True, slots=True)
class SkeletalPose:
    time: float
    bones: tuple[SkeletalBonePose, ...]

    def __post_init__(self) -> None:
        if self.time < 0.0:
            raise ValueError("skeletal pose time cannot be negative")
        if not self.bones:
            raise ValueError("skeletal pose must contain at least one bone")
        bone_ids = tuple(bone.bone_id for bone in self.bones)
        if len(bone_ids) != len(set(bone_ids)):
            raise ValueError("skeletal pose contains duplicate bone IDs")

    def get_bone(self, bone_id: int) -> SkeletalBonePose | None:
        target = int(bone_id)
        return next((bone for bone in self.bones if bone.bone_id == target), None)

    @property
    def bone_ids(self) -> tuple[int, ...]:
        return tuple(bone.bone_id for bone in self.bones)

    @property
    def root_motion_bones(self) -> tuple[SkeletalBonePose, ...]:
        return tuple(bone for bone in self.bones if bone.has_root_motion)

    def interpolate(self, other: SkeletalPose, alpha: float) -> SkeletalPose:
        if self.bone_ids != other.bone_ids:
            raise ValueError("skeletal poses do not target the same ordered bones")
        return SkeletalPose(
            self.time + ((other.time - self.time) * alpha),
            tuple(
                start.interpolate(end, alpha)
                for start, end in zip(self.bones, other.bones, strict=True)
            ),
        )

    def to_data(self) -> dict[str, object]:
        return {
            "time": self.time,
            "bones": [bone.to_data() for bone in self.bones],
        }


@dataclass(frozen=True, slots=True)
class SkeletalBoneTarget:
    """Skeleton metadata bound to an animated bone ID."""

    bone_id: int
    bone_index: int | None = None
    name: str | None = None
    parent_index: int | None = None
    local_transform: SkeletalMatrix4 | None = None
    world_transform: SkeletalMatrix4 | None = None
    inverse_bind_transform: SkeletalMatrix4 | None = None

    def __post_init__(self) -> None:
        if self.bone_id < 0:
            raise ValueError("skeletal target bone ID cannot be negative")
        if self.bone_index is not None and self.bone_index < 0:
            raise ValueError("skeletal target bone index cannot be negative")
        if self.parent_index is not None and self.parent_index < 0:
            raise ValueError("skeletal target parent index cannot be negative")

    @property
    def is_bound(self) -> bool:
        return self.bone_index is not None

    def to_data(self) -> dict[str, object]:
        def matrix(value: SkeletalMatrix4 | None) -> list[float] | None:
            return None if value is None else list(value)

        return {
            "bone_id": self.bone_id,
            "bone_index": self.bone_index,
            "name": self.name,
            "parent_index": self.parent_index,
            "local_transform": matrix(self.local_transform),
            "world_transform": matrix(self.world_transform),
            "inverse_bind_transform": matrix(self.inverse_bind_transform),
        }


@dataclass(frozen=True, slots=True)
class SkeletalAnimationClip:
    """Format-neutral sampled skeletal animation for converters and tooling."""

    name: str
    duration: float
    looping: bool
    frames: tuple[SkeletalPose, ...]
    signature: int = 0
    targets: tuple[SkeletalBoneTarget, ...] = ()
    _targets_by_id: dict[int, SkeletalBoneTarget] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.duration < 0.0:
            raise ValueError("skeletal animation duration cannot be negative")
        if not self.frames:
            raise ValueError("skeletal animation must contain at least one frame")
        previous = -1.0
        bone_ids = self.frames[0].bone_ids
        for frame in self.frames:
            if frame.time < previous:
                raise ValueError("skeletal animation frames must be ordered")
            if frame.bone_ids != bone_ids:
                raise ValueError("skeletal animation frames target different bones")
            previous = frame.time
        if self.frames[-1].time > self.duration:
            raise ValueError("skeletal animation frame time exceeds its duration")
        if self.targets:
            target_ids = tuple(target.bone_id for target in self.targets)
            if target_ids != bone_ids:
                raise ValueError(
                    "skeletal animation targets do not match its ordered bones"
                )
        object.__setattr__(
            self,
            "_targets_by_id",
            {target.bone_id: target for target in self.targets},
        )

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def bone_ids(self) -> tuple[int, ...]:
        return self.frames[0].bone_ids

    @property
    def is_bound(self) -> bool:
        return bool(self.targets) and all(target.is_bound for target in self.targets)

    @property
    def unbound_bone_ids(self) -> tuple[int, ...]:
        if not self.targets:
            return self.bone_ids
        return tuple(
            target.bone_id for target in self.targets if not target.is_bound
        )

    def get_target(self, bone_id: int) -> SkeletalBoneTarget | None:
        return self._targets_by_id.get(int(bone_id))

    def with_targets(
        self,
        targets: tuple[SkeletalBoneTarget, ...],
    ) -> SkeletalAnimationClip:
        return SkeletalAnimationClip(
            self.name,
            self.duration,
            self.looping,
            self.frames,
            self.signature,
            targets,
        )

    def sample(self, time: float, *, loop: bool | None = None) -> SkeletalPose:
        if time < 0.0:
            raise ValueError("skeletal animation time cannot be negative")
        if len(self.frames) == 1 or self.duration <= 0.0:
            return self.frames[0]
        should_loop = self.looping if loop is None else loop
        if should_loop:
            time %= self.duration
        else:
            time = min(time, self.duration)
        upper = bisect_right(self.frames, time, key=_FRAME_TIME)
        if upper == 0:
            return self.frames[0]
        if upper >= len(self.frames):
            return self.frames[-1]
        frame0 = self.frames[upper - 1]
        frame1 = self.frames[upper]
        span = frame1.time - frame0.time
        alpha = 0.0 if span <= 0.0 else (time - frame0.time) / span
        return frame0.interpolate(frame1, alpha)

    def to_data(self) -> dict[str, object]:
        return {
            "name": self.name,
            "duration": self.duration,
            "looping": self.looping,
            "signature": self.signature,
            "targets": [target.to_data() for target in self.targets],
            "frames": [frame.to_data() for frame in self.frames],
        }


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
        upper = bisect_right(self.frames, time, key=_FRAME_TIME)
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
    "Quaternion",
    "SkeletalAnimationClip",
    "SkeletalBonePose",
    "SkeletalBoneTarget",
    "SkeletalMatrix4",
    "SkeletalPose",
    "SkeletalTransform",
    "UvAnimationClip",
    "UvAnimationFrame",
    "UvMatrix3",
    "UvTransform",
    "UvVector2",
    "UvVector4",
    "Vector3",
    "interpolate_quaternion",
    "normalize_quaternion",
]
