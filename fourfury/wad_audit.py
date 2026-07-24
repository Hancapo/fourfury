from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .model import ModelSkeleton
from .wbd import joaat

if TYPE_CHECKING:
    from .wad import WadAnimation, WadDocument, WadTrackId


class WadTrackKind(StrEnum):
    """Stable semantic family for a logical WAD track."""

    SKELETAL = "skeletal"
    MATERIAL = "material"
    MORPH = "morph"
    CAMERA = "camera"
    LIGHT = "light"
    GENERIC = "generic"
    ACTION = "action"
    CUSTOM = "custom"


class WadIssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class WadValidationIssue:
    code: str
    message: str
    severity: WadIssueSeverity
    animation_name: str = ""
    name_hash: int | None = None
    group_index: int | None = None
    target_id: int | None = None
    track_id: int | None = None

    def to_data(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "animation_name": self.animation_name,
            "name_hash": self.name_hash,
            "group_index": self.group_index,
            "target_id": self.target_id,
            "track_id": self.track_id,
        }


@dataclass(frozen=True, slots=True)
class WadAuditReport:
    name: str
    animation_count: int
    track_group_count: int
    target_count: int
    channel_count: int
    track_kinds: dict[str, int]
    track_ids: dict[int, int]
    channel_types: dict[str, int]
    custom_track_ids: tuple[int, ...]
    issues: tuple[WadValidationIssue, ...]

    @property
    def error_count(self) -> int:
        return sum(
            issue.severity is WadIssueSeverity.ERROR
            for issue in self.issues
        )

    @property
    def warning_count(self) -> int:
        return sum(
            issue.severity is WadIssueSeverity.WARNING
            for issue in self.issues
        )

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0

    def to_data(self) -> dict[str, object]:
        return {
            "name": self.name,
            "animation_count": self.animation_count,
            "track_group_count": self.track_group_count,
            "target_count": self.target_count,
            "channel_count": self.channel_count,
            "track_kinds": dict(self.track_kinds),
            "track_ids": dict(self.track_ids),
            "channel_types": dict(self.channel_types),
            "custom_track_ids": list(self.custom_track_ids),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "is_valid": self.is_valid,
            "issues": [issue.to_data() for issue in self.issues],
        }


_MATERIAL_TRACKS = frozenset(
    {
        16,  # SHADER_FRAME_INDEX
        17,  # SHADER_SLIDE_U
        18,  # SHADER_SLIDE_V
        19,  # SHADER_ROTATE_UV
        23,  # ANIMATED_NORMAL_MAPS
    }
)
_MORPH_TRACKS = frozenset(
    {
        21,  # BLEND_SHAPE
        22,  # VISEMES
        24,  # FACIAL_CONTROL
        25,  # FACIAL_TRANSLATION
        26,  # FACIAL_ROTATION
        37,  # FACIAL_SCALE
        50,  # FACIAL_TINTING
    }
)
_CAMERA_TRACKS = frozenset(
    {
        7, 8, 9, 10, 11, 12, 13, 14, 15,
        27, 28, 36, 39, 40, 43, 44, 45, 46,
        48, 49, 51, 52, 53,
    }
)
_LIGHT_TRACKS = frozenset(
    {
        30,  # LIGHT_INTENSITY
        31,  # LIGHT_FALL_OFF
        32,  # LIGHT_CONE_ANGLE
        42,  # LIGHT_DIRECTION
        47,  # LIGHT_EXPONENTIAL_FALL_OFF
    }
)
_GENERIC_TRACKS = frozenset(
    {
        3,  # BONE_CONSTRAINT
        4,  # VISIBILITY
        29,  # COLOR
        33,  # GENERIC_CONTROL
        34,  # GENERIC_TRANSLATION
        35,  # GENERIC_ROTATION
        38,  # GENERIC_SCALE
        41,  # PARTICLE_DATA
    }
)
_SKELETAL_TRACK_IDS = frozenset({0, 1, 2, 5, 6, 20})
_KNOWN_TRACK_IDS = frozenset(range(54)) | frozenset({128})


def classify_wad_track(track_id: int | WadTrackId) -> WadTrackKind:
    value = int(track_id)
    if value in _SKELETAL_TRACK_IDS:
        return WadTrackKind.SKELETAL
    if value not in _KNOWN_TRACK_IDS:
        return WadTrackKind.CUSTOM
    if value in _MATERIAL_TRACKS:
        return WadTrackKind.MATERIAL
    if value in _MORPH_TRACKS:
        return WadTrackKind.MORPH
    if value in _CAMERA_TRACKS:
        return WadTrackKind.CAMERA
    if value in _LIGHT_TRACKS:
        return WadTrackKind.LIGHT
    if value == 128:
        return WadTrackKind.ACTION
    if value in _GENERIC_TRACKS:
        return WadTrackKind.GENERIC
    return WadTrackKind.CUSTOM


def validate_wad_animation(
    animation: WadAnimation,
    *,
    skeleton: ModelSkeleton | None = None,
) -> tuple[WadValidationIssue, ...]:
    issues: list[WadValidationIssue] = []

    def add(
        code: str,
        message: str,
        severity: WadIssueSeverity,
        *,
        group_index: int | None = None,
        target_id: int | None = None,
        track_id: int | None = None,
    ) -> None:
        issues.append(
            WadValidationIssue(
                code,
                message,
                severity,
                animation.short_name,
                group_index=group_index,
                target_id=target_id,
                track_id=track_id,
            )
        )

    if not math.isfinite(animation.duration) or animation.duration < 0.0:
        add(
            "invalid_duration",
            f"animation duration is not a finite non-negative value: {animation.duration}",
            WadIssueSeverity.ERROR,
        )
    if animation.frame_count == 0:
        add(
            "empty_animation",
            "animation declares zero frames",
            WadIssueSeverity.WARNING,
        )
    if not animation.tracks:
        add(
            "missing_track_groups",
            "animation has no serialized track groups",
            WadIssueSeverity.WARNING,
        )
        return tuple(issues)

    frames_per_group = animation.frames_per_group
    group_stride = animation.frame_group_stride
    if frames_per_group <= 0 or group_stride <= 0:
        add(
            "invalid_frames_per_chunk",
            "animation has track groups but no positive frames-per-chunk value",
            WadIssueSeverity.ERROR,
        )
    elif animation.frame_count:
        expected = max(
            math.ceil(max(animation.frame_count - 1, 0) / group_stride),
            1,
        )
        if len(animation.tracks) != expected:
            add(
                "track_group_count",
                f"animation has {len(animation.tracks)} track groups; expected {expected}",
                WadIssueSeverity.WARNING,
            )

    reference = {
        chunk.bone_id.target_key: (
            chunk.bone_id.track_type,
            chunk.component_count,
        )
        for chunk in animation.tracks[0].chunks
    }
    for group_index, group in enumerate(animation.tracks):
        remaining = max(
            animation.frame_count - (group_index * group_stride),
            0,
        )
        expected_group_frames = min(frames_per_group, remaining)
        if (
            animation.frame_count
            and group.frames_per_chunk not in {0, expected_group_frames}
        ):
            add(
                "group_frames_per_chunk",
                f"track group declares {group.frames_per_chunk} samples; "
                f"expected {expected_group_frames}",
                WadIssueSeverity.WARNING,
                group_index=group_index,
            )
        current = {
            chunk.bone_id.target_key: (
                chunk.bone_id.track_type,
                chunk.component_count,
            )
            for chunk in group.chunks
        }
        if current.keys() != reference.keys():
            missing = sorted(reference.keys() - current.keys())
            extra = sorted(current.keys() - reference.keys())
            add(
                "inconsistent_targets",
                f"track group target layout differs from the first group; "
                f"missing={missing}, extra={extra}",
                WadIssueSeverity.ERROR,
                group_index=group_index,
            )
        for key in current.keys() & reference.keys():
            expected_type, expected_components = reference[key]
            current_type, current_components = current[key]
            if current_type != expected_type:
                add(
                    "inconsistent_track_type",
                    f"logical track type changes from {expected_type} to {current_type}",
                    WadIssueSeverity.ERROR,
                    group_index=group_index,
                    target_id=key[0],
                    track_id=key[1],
                )
            if current_components != expected_components:
                add(
                    "inconsistent_component_count",
                    f"logical track component count changes from "
                    f"{expected_components} to {current_components}",
                    WadIssueSeverity.ERROR,
                    group_index=group_index,
                    target_id=key[0],
                    track_id=key[1],
                )

    if skeleton is not None:
        if (
            animation.signature
            and skeleton.signature
            and animation.signature != skeleton.signature
        ):
            add(
                "skeleton_signature",
                "animation signature does not match the supplied skeleton",
                WadIssueSeverity.ERROR,
            )
        missing = tuple(
            bone_id
            for bone_id in animation.skeletal_bone_ids
            if skeleton.get_bone(bone_id) is None
        )
        if missing:
            add(
                "missing_skeleton_bones",
                f"supplied skeleton is missing animated bone IDs: {missing}",
                WadIssueSeverity.ERROR,
            )

    return tuple(issues)


def validate_wad_document(
    document: WadDocument,
    *,
    skeleton: ModelSkeleton | None = None,
) -> tuple[WadValidationIssue, ...]:
    from .wad import wad_animation_hash

    issues: list[WadValidationIssue] = []
    for entry in document.entries:
        animation_issues = validate_wad_animation(entry.animation, skeleton=skeleton)
        issues.extend(
            WadValidationIssue(
                issue.code,
                issue.message,
                issue.severity,
                issue.animation_name,
                entry.name_hash,
                issue.group_index,
                issue.target_id,
                issue.track_id,
            )
            for issue in animation_issues
        )
        expected_hashes = {
            wad_animation_hash(entry.animation.short_name),
            joaat(entry.animation.short_name),
        }
        if entry.name_hash not in expected_hashes:
            issues.append(
                WadValidationIssue(
                    "animation_hash",
                    f"dictionary hash {entry.name_hash:08x} does not match "
                    "a supported animation name hash",
                    WadIssueSeverity.WARNING,
                    entry.animation.short_name,
                    entry.name_hash,
                )
            )
    return tuple(issues)


def audit_wad_document(
    document: WadDocument,
    *,
    skeleton: ModelSkeleton | None = None,
) -> WadAuditReport:
    track_kinds: Counter[str] = Counter()
    track_ids: Counter[int] = Counter()
    channel_types: Counter[str] = Counter()
    track_group_count = 0
    target_count = 0
    channel_count = 0

    for animation in document.animations:
        track_group_count += len(animation.tracks)
        target_count += len(animation.targets)
        for target in animation.targets:
            track_kinds[classify_wad_track(target.track_id).value] += 1
            track_ids[target.track_id] += 1
        for group in animation.tracks:
            for chunk in group.chunks:
                for channel in chunk.channels:
                    channel_count += 1
                    channel_types[channel.channel_type.name] += 1

    custom_track_ids = tuple(
        sorted(
            track_id
            for track_id in track_ids
            if classify_wad_track(track_id) is WadTrackKind.CUSTOM
        )
    )
    return WadAuditReport(
        name=document.name,
        animation_count=len(document.animations),
        track_group_count=track_group_count,
        target_count=target_count,
        channel_count=channel_count,
        track_kinds=dict(sorted(track_kinds.items())),
        track_ids=dict(sorted(track_ids.items())),
        channel_types=dict(sorted(channel_types.items())),
        custom_track_ids=custom_track_ids,
        issues=validate_wad_document(document, skeleton=skeleton),
    )


__all__ = [
    "WadAuditReport",
    "WadIssueSeverity",
    "WadTrackKind",
    "WadValidationIssue",
    "audit_wad_document",
    "classify_wad_track",
    "validate_wad_animation",
    "validate_wad_document",
]
