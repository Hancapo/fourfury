from __future__ import annotations

import math
import re
import struct
from bisect import bisect_right
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from pathlib import Path
from typing import BinaryIO, Callable, Iterable, Iterator

from ._utils import atomic_write
from .animation import (
    AnimationTrackFrame,
    AnimationTrackInterpolation,
    AnimationTrackTarget,
    AnimationTrackValue,
    AnimationValue,
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
from .model import ModelSkeleton
from .rsc import (
    RSC5_PHYSICAL_BASE,
    RSC5_VIRTUAL_BASE,
    Rsc5Resource,
    rsc5_pointer_offset,
)
from .wbd import joaat
from .wad_audit import (
    WadAuditReport,
    WadTrackKind,
    WadValidationIssue,
    audit_wad_document,
    classify_wad_track,
    validate_wad_animation,
    validate_wad_document,
)


WAD_RESOURCE_VERSION = 1
WAD_DICTIONARY_SIZE = 0x20
WAD_ANIMATION_SIZE = 0x20
WAD_TRACK_SIZE = 0x10
WAD_CHUNK_SIZE = 0x18
WAD_CHANNEL_HEADER_SIZE = 0x08
_WAD_UV_ANIMATION_NAME = re.compile(r"^(?P<name>.+)_uv_(?P<material>\d+)$", re.IGNORECASE)


def _wad_short_name(value: str) -> str:
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-5] if name.casefold().endswith(".anim") else name


def wad_animation_hash(value: str | bytes) -> int:
    """Return the stock dictionary hash for an animation name."""

    text = (
        value.decode("utf-8", errors="replace")
        if isinstance(value, bytes)
        else value
    )
    short_name = _wad_short_name(text)
    match = _WAD_UV_ANIMATION_NAME.fullmatch(short_name)
    if match is None:
        return joaat(short_name)
    base_hash = joaat(match.group("name"))
    return (base_hash + int(match.group("material")) + 1) & 0xFFFFFFFF


class WadAnimationFlags(IntFlag):
    NONE = 0
    LOOPED = 1 << 0
    RAW = 1 << 3
    MOVER_TRACKS = 1 << 4
    PACKED = 1 << 8
    COMPACT = 1 << 10


class WadChannelType(IntEnum):
    NONE = 0
    RAW_FLOAT = 1
    VECTOR3 = 2
    QUATERNION = 3
    STATIC_FLOAT = 4
    CURVE_FLOAT = 5
    QUANTIZED_FLOAT = 6
    RAW_INT = 7
    RAW_BOOL = 8
    STATIC_QUATERNION = 9
    DELTA_FLOAT = 10
    STATIC_INT = 11
    RLE_INT = 12
    STATIC_VECTOR3 = 13
    SMALLEST_THREE_QUATERNION = 14
    VARIABLE_QUANTIZED_FLOAT = 15
    INDIRECT_QUANTIZED_FLOAT = 16
    LINEAR_FLOAT = 17
    QUADRATIC_BSPLINE = 18
    CUBIC_BSPLINE = 19
    STATIC_SMALLEST_THREE_QUATERNION = 20


_SUPPORTED_WAD_CHANNEL_TYPES = frozenset(
    {
        WadChannelType.RAW_FLOAT,
        WadChannelType.STATIC_FLOAT,
        WadChannelType.QUANTIZED_FLOAT,
        WadChannelType.RAW_INT,
        WadChannelType.STATIC_QUATERNION,
        WadChannelType.STATIC_INT,
        WadChannelType.RLE_INT,
        WadChannelType.STATIC_VECTOR3,
    }
)

_VECTOR3_WAD_CHANNEL_TYPES = frozenset(
    {
        WadChannelType.VECTOR3,
        WadChannelType.STATIC_VECTOR3,
    }
)

_QUATERNION_WAD_CHANNEL_TYPES = frozenset(
    {
        WadChannelType.QUATERNION,
        WadChannelType.STATIC_QUATERNION,
        WadChannelType.SMALLEST_THREE_QUATERNION,
        WadChannelType.STATIC_SMALLEST_THREE_QUATERNION,
    }
)


class WadTrackType(IntEnum):
    VECTOR3 = 0
    QUATERNION = 1
    FLOAT = 2
    INTEGER = 3


class WadTrackPacking(IntEnum):
    RAW = 0
    XYZW = 4
    QUATERNION_XYZ_RECONSTRUCT = 8
    RESERVED = 12


class WadTrackId(IntEnum):
    BONE_TRANSLATION = 0
    BONE_ROTATION = 1
    BONE_SCALE = 2
    BONE_CONSTRAINT = 3
    VISIBILITY = 4
    MOVER_TRANSLATION = 5
    MOVER_ROTATION = 6
    CAMERA_TRANSLATION = 7
    CAMERA_ROTATION = 8
    CAMERA_SCALE = 9
    CAMERA_FOCAL_LENGTH = 10
    CAMERA_HORIZONTAL_FILM_APERTURE = 11
    CAMERA_APERTURE = 12
    CAMERA_FOCAL_POINT = 13
    CAMERA_F_STOP = 14
    CAMERA_FOCUS_DISTANCE = 15
    SHADER_FRAME_INDEX = 16
    SHADER_SLIDE_U = 17
    SHADER_SLIDE_V = 18
    SHADER_ROTATE_UV = 19
    MOVER_SCALE = 20
    BLEND_SHAPE = 21
    VISEMES = 22
    ANIMATED_NORMAL_MAPS = 23
    FACIAL_CONTROL = 24
    FACIAL_TRANSLATION = 25
    FACIAL_ROTATION = 26
    CAMERA_FIELD_OF_VIEW = 27
    CAMERA_DEPTH_OF_FIELD = 28
    COLOR = 29
    LIGHT_INTENSITY = 30
    LIGHT_FALL_OFF = 31
    LIGHT_CONE_ANGLE = 32
    GENERIC_CONTROL = 33
    GENERIC_TRANSLATION = 34
    GENERIC_ROTATION = 35
    CAMERA_DEPTH_OF_FIELD_STRENGTH = 36
    FACIAL_SCALE = 37
    GENERIC_SCALE = 38
    CAMERA_SHALLOW_DEPTH_OF_FIELD = 39
    CAMERA_MOTION_BLUR = 40
    PARTICLE_DATA = 41
    LIGHT_DIRECTION = 42
    CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE = 43
    CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE = 44
    CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE = 45
    CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE = 46
    LIGHT_EXPONENTIAL_FALL_OFF = 47
    CAMERA_SIMPLE_DEPTH_OF_FIELD = 48
    CAMERA_CIRCLE_OF_CONFUSION = 49
    FACIAL_TINTING = 50
    CAMERA_FOCUS = 51
    CAMERA_NIGHT_CIRCLE_OF_CONFUSION = 52
    CAMERA_LIMIT = 53
    ACTION_FLAGS = 128


WAD_BONE_TRANSFORM_TRACKS = frozenset(
    {
        WadTrackId.BONE_TRANSLATION,
        WadTrackId.BONE_ROTATION,
        WadTrackId.BONE_SCALE,
    }
)
WAD_MOVER_TRANSFORM_TRACKS = frozenset(
    {
        WadTrackId.MOVER_TRANSLATION,
        WadTrackId.MOVER_ROTATION,
        WadTrackId.MOVER_SCALE,
    }
)
WAD_SKELETAL_TRACKS = WAD_BONE_TRANSFORM_TRACKS | WAD_MOVER_TRANSFORM_TRACKS


class WadBoneName(IntEnum):
    CHAR = 0
    HUB_LF = 42
    HUB_RF = 43
    HUB_LR = 51
    HUB_RR = 52
    CHAR_PELVIS = 417
    CHAR_L_THIGH = 418
    CHAR_L_CALF = 419
    CHAR_L_FOOT = 420
    CHAR_L_TOE0 = 421
    CHAR_R_THIGH = 423
    CHAR_R_CALF = 424
    CHAR_R_FOOT = 425
    CHAR_R_TOE0 = 1200
    CHAR_SPINE = 1202
    CHAR_SPINE1 = 1203
    CHAR_NECK = 1204
    CHAR_HEAD = 1205
    CHAR_L_CLAVICLE = 1216
    CHAR_L_UPPERARM = 1217
    CHAR_L_FOREARM = 1218
    CHAR_L_HAND = 1219
    CHAR_R_CLAVICLE = 1223
    CHAR_R_UPPERARM = 1224
    CHAR_R_FOREARM = 1225
    CHAR_R_HAND = 1232
    CHAR_R_FINGER0 = 13744
    CHAR_R_FINGER01 = 13745
    CHAR_R_FINGER02 = 13746
    CHAR_R_FINGER1 = 13747
    CHAR_R_FINGER11 = 13748
    CHAR_R_FINGER12 = 13749
    CHAR_R_FINGER2 = 13750
    CHAR_R_FINGER21 = 13751
    CHAR_R_FINGER22 = 13752
    CHAR_R_FINGER3 = 13753
    CHAR_R_FINGER31 = 13760
    CHAR_R_FINGER32 = 13761
    CHAR_L_FINGER0 = 13776
    CHAR_L_FINGER01 = 13777
    CHAR_L_FINGER02 = 13778
    CHAR_L_FINGER1 = 13779
    CHAR_L_FINGER11 = 13780
    CHAR_L_FINGER12 = 13781
    CHAR_L_FINGER2 = 13782
    CHAR_L_FINGER21 = 13783
    CHAR_L_FINGER22 = 13784
    CHAR_L_FINGER3 = 13785
    CHAR_L_FINGER31 = 13792
    CHAR_L_FINGER32 = 13793
    CHAR_SPINE2 = 13984
    CHAR_SPINE3 = 13985
    NECK_ROLL = 14240
    L_UPPERARM_ROLL = 14496
    CHAR_L_FORETWIST = 14497
    L_CALF_ROLL = 14512
    R_UPPERARM_ROLL = 14752
    CHAR_R_FORETWIST = 14753
    R_CALF_ROLL = 14768
    SUSPENSION_LF = 15288
    SUSPENSION_LR = 15289
    SUSPENSION_RF = 15296
    SUSPENSION_RR = 15297
    WHEEL_LF = 15298
    WHEEL_LR = 15299
    WHEEL_RF = 15300
    WHEEL_RR = 15301
    L_ARM_ROLL = 15857
    R_ARM_ROLL = 15873
    BEAN_MACHINE_ROTATING_CUP = 20808
    FB_C_BROW = 32660
    FB_R_BROW = 32661
    FB_R_EYELID = 32662
    FB_R_EYEBALL = 32663
    FB_L_EYEBALL = 32664
    FB_L_EYELID = 32665
    FB_L_BROW = 32666
    FB_C_JAW = 32667
    FB_R_LIP_UPPER = 32668
    FB_L_LIP_UPPER = 32669
    FB_R_CORNER_MOUTH = 32676
    FB_L_CORNER_MOUTH = 32677
    FB_R_LIP_LOWER = 32678
    FB_L_LIP_LOWER = 32679
    FB_C_CHEEKS = 32692
    TS_CLUCKTXTAN01 = 43227
    EXTRA_01 = 45156
    EXTRA_02 = 45157
    EXTRA_03 = 45158
    POINT_FB_C_JAW = 51524
    POINT_FB_R_LIP_UPPER = 51525
    POINT_FB_L_LIP_UPPER = 51526
    POINT_FB_R_LIP_LOWER = 51527
    POINT_FB_L_LIP_LOWER = 51528


@dataclass(frozen=True, slots=True)
class WadBoneId:
    track_id: int
    type_id: int
    bone_id: int

    @property
    def is_uv_channel(self) -> bool:
        """Whether this identifier targets a material UV slot instead of a bone."""

        return self.type_id == 0xFF

    @property
    def target_key(self) -> tuple[int, int]:
        """Logical target shared by equivalent chunks with different encodings."""

        return (self.bone_id, self.track_id)

    def targets(self, other: WadBoneId) -> bool:
        return self.target_key == other.target_key

    @property
    def uv_index(self) -> int | None:
        """Return the material/UV target index encoded in this identifier."""

        return self.bone_id if self.is_uv_channel else None

    @property
    def track_type(self) -> WadTrackType | None:
        if self.is_uv_channel:
            return None
        return WadTrackType(self.type_id & 0x03)

    @property
    def packing(self) -> WadTrackPacking | None:
        if self.is_uv_channel:
            return None
        return WadTrackPacking(self.type_id & 0x0C)

    @property
    def type_name(self) -> str:
        track_type = self.track_type
        return "UV" if track_type is None else track_type.name

    @property
    def action_flags(self) -> bool:
        return self.track is WadTrackId.ACTION_FLAGS

    @property
    def track(self) -> WadTrackId | None:
        try:
            return WadTrackId(self.track_id)
        except ValueError:
            return None

    @property
    def track_name(self) -> str:
        track = self.track
        return track.name if track is not None else f"TRACK_{self.track_id}"

    @property
    def is_bone_transform(self) -> bool:
        return self.track in WAD_BONE_TRANSFORM_TRACKS

    @property
    def is_mover_transform(self) -> bool:
        return self.track in WAD_MOVER_TRANSFORM_TRACKS

    @property
    def is_skeletal_transform(self) -> bool:
        return self.track in WAD_SKELETAL_TRACKS and not self.is_uv_channel

    @property
    def is_rotation(self) -> bool:
        return self.track in {
            WadTrackId.BONE_ROTATION,
            WadTrackId.MOVER_ROTATION,
        }

    @property
    def bone(self) -> WadBoneName | None:
        try:
            return WadBoneName(self.bone_id)
        except ValueError:
            return None

    @property
    def bone_name(self) -> str:
        if self.is_uv_channel:
            return f"UV_{self.bone_id}"
        bone = self.bone
        return bone.name if bone is not None else f"BONE_{self.bone_id}"

    def bind_uv(self, uv_index: int) -> WadBoneId:
        """Return this track retargeted to a material UV index."""

        if not 0 <= uv_index <= 0xFFFF:
            raise ValueError("WAD UV index must fit in an unsigned 16-bit integer")
        return WadBoneId(self.track_id, 0xFF, uv_index)


Scalar = float | int
ChannelValue = Scalar | tuple[float, ...]


@dataclass(frozen=True, slots=True, init=False, eq=False)
class WadChannel:
    channel_type: WadChannelType | int
    flags: int
    vector: tuple[float, ...] | None = None
    scale: float | None = None
    offset: float | None = None
    run_values: tuple[int, ...] = ()
    packed_sequence: tuple[int, ...] = ()
    packed_sequence_words: tuple[int, ...] = ()
    packed_sequence_bit_count: int = 0
    packed_sequence_divisor: int = 0
    header_bytes: bytes = field(default=b"", repr=False, compare=False)
    vft: int = field(default=0, repr=False, compare=False)
    pointer: int = field(default=0, repr=False, compare=False)
    _run_ends: tuple[int, ...] = field(default=(), repr=False, compare=False)
    _values: tuple[Scalar, ...] = field(default=(), repr=False)
    _quantized_values: tuple[int, ...] = field(default=(), repr=False)
    _raw_data: bytes = field(default=b"", repr=False, compare=False)
    _raw_code: str = field(default="", repr=False, compare=False)
    _raw_count: int = field(default=0, repr=False, compare=False)
    _quantized_data: bytes = field(default=b"", repr=False, compare=False)
    _quantized_element_size: int = field(default=0, repr=False, compare=False)
    _quantized_element_count: int = field(default=0, repr=False, compare=False)

    def __init__(
        self,
        channel_type: WadChannelType | int,
        flags: int,
        values: tuple[Scalar, ...] = (),
        vector: tuple[float, ...] | None = None,
        scale: float | None = None,
        offset: float | None = None,
        quantized_values: tuple[int, ...] = (),
        run_values: tuple[int, ...] = (),
        packed_sequence: tuple[int, ...] = (),
        packed_sequence_words: tuple[int, ...] = (),
        packed_sequence_bit_count: int = 0,
        packed_sequence_divisor: int = 0,
        vft: int = 0,
        pointer: int = 0,
        *,
        header_bytes: bytes = b"",
        _raw_data: bytes = b"",
        _raw_code: str = "",
        _raw_count: int = 0,
        _quantized_data: bytes = b"",
        _quantized_element_size: int = 0,
        _quantized_element_count: int = 0,
    ) -> None:
        object.__setattr__(self, "channel_type", channel_type)
        object.__setattr__(self, "flags", flags)
        object.__setattr__(self, "vector", vector)
        object.__setattr__(self, "scale", scale)
        object.__setattr__(self, "offset", offset)
        object.__setattr__(self, "run_values", tuple(run_values))
        object.__setattr__(self, "packed_sequence", tuple(packed_sequence))
        object.__setattr__(
            self,
            "packed_sequence_words",
            tuple(packed_sequence_words),
        )
        object.__setattr__(
            self,
            "packed_sequence_bit_count",
            packed_sequence_bit_count,
        )
        object.__setattr__(
            self,
            "packed_sequence_divisor",
            packed_sequence_divisor,
        )
        object.__setattr__(self, "header_bytes", bytes(header_bytes))
        object.__setattr__(self, "vft", vft)
        object.__setattr__(self, "pointer", pointer)
        run_total = 0
        run_ends: list[int] = []
        for length in packed_sequence:
            run_total += length
            run_ends.append(run_total)
        object.__setattr__(self, "_run_ends", tuple(run_ends))
        object.__setattr__(self, "_values", tuple(values))
        object.__setattr__(self, "_quantized_values", tuple(quantized_values))
        object.__setattr__(self, "_raw_data", _raw_data)
        object.__setattr__(self, "_raw_code", _raw_code)
        object.__setattr__(self, "_raw_count", _raw_count)
        object.__setattr__(self, "_quantized_data", _quantized_data)
        object.__setattr__(
            self,
            "_quantized_element_size",
            _quantized_element_size,
        )
        object.__setattr__(
            self,
            "_quantized_element_count",
            _quantized_element_count,
        )

    @property
    def values(self) -> tuple[Scalar, ...]:
        values = self._values
        if not values and self._raw_data:
            values = struct.unpack(
                f"<{self._raw_count}{self._raw_code}",
                self._raw_data,
            )
            object.__setattr__(self, "_values", values)
        elif (
            not values
            and self._quantized_data
            and self._quantized_element_count
            and self.scale is not None
            and self.offset is not None
        ):
            values = tuple(
                (self._quantized_value_at(index) * self.scale) + self.offset
                for index in range(self._quantized_element_count)
            )
            object.__setattr__(self, "_values", values)
        return values

    @property
    def quantized_values(self) -> tuple[int, ...]:
        values = self._quantized_values
        if (
            not values
            and self._quantized_data
            and self._quantized_element_count
        ):
            values = tuple(
                self._quantized_value_at(index)
                for index in range(self._quantized_element_count)
            )
            object.__setattr__(self, "_quantized_values", values)
        return values

    def _quantized_value_at(self, index: int) -> int:
        bit_address = index * self._quantized_element_size
        block = bit_address >> 5
        bit = bit_address & 31
        low = struct.unpack_from("<I", self._quantized_data, block * 4)[0]
        high = struct.unpack_from("<I", self._quantized_data, (block + 1) * 4)[0]
        mask = (
            0xFFFFFFFF
            if self._quantized_element_size == 32
            else (1 << self._quantized_element_size) - 1
        )
        return ((low | (high << 32)) >> bit) & mask

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WadChannel):
            return NotImplemented
        return (
            self.channel_type,
            self.flags,
            self.values,
            self.vector,
            self.scale,
            self.offset,
            self.quantized_values,
            self.run_values,
            self.packed_sequence,
            self.packed_sequence_words,
            self.packed_sequence_bit_count,
            self.packed_sequence_divisor,
        ) == (
            other.channel_type,
            other.flags,
            other.values,
            other.vector,
            other.scale,
            other.offset,
            other.quantized_values,
            other.run_values,
            other.packed_sequence,
            other.packed_sequence_words,
            other.packed_sequence_bit_count,
            other.packed_sequence_divisor,
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.channel_type,
                self.flags,
                self.values,
                self.vector,
                self.scale,
                self.offset,
                self.quantized_values,
                self.run_values,
                self.packed_sequence,
                self.packed_sequence_words,
                self.packed_sequence_bit_count,
                self.packed_sequence_divisor,
            )
        )

    @property
    def is_static(self) -> bool:
        return self.channel_type in {
            WadChannelType.STATIC_FLOAT,
            WadChannelType.STATIC_INT,
            WadChannelType.STATIC_VECTOR3,
            WadChannelType.STATIC_QUATERNION,
        }

    @property
    def channel_type_value(self) -> int:
        return int(self.channel_type)

    @property
    def channel_type_name(self) -> str:
        if isinstance(self.channel_type, WadChannelType):
            return self.channel_type.name
        return f"UNKNOWN_{self.channel_type_value}"

    @property
    def is_supported(self) -> bool:
        return self.channel_type in _SUPPORTED_WAD_CHANNEL_TYPES

    @property
    def component_count(self) -> int:
        if self.vector is not None:
            return len(self.vector)
        if self.channel_type in _VECTOR3_WAD_CHANNEL_TYPES:
            return 3
        if self.channel_type in _QUATERNION_WAD_CHANNEL_TYPES:
            return 4
        return 1

    @property
    def run_lengths(self) -> tuple[int, ...]:
        """Decoded frame count for each RLE integer value."""

        return self.packed_sequence

    @property
    def value(self) -> ChannelValue | tuple[Scalar, ...] | None:
        if self.vector is not None:
            return self.vector
        if len(self.values) == 1:
            return self.values[0]
        return self.values or None

    def value_at(self, frame: int) -> ChannelValue:
        if frame < 0:
            raise ValueError("WAD channel frame cannot be negative")
        if not self.is_supported:
            raise NotImplementedError(
                f"WAD channel type {self.channel_type_name} "
                f"({self.channel_type_value}) cannot be evaluated"
            )
        if self.channel_type == WadChannelType.RLE_INT:
            if not self.run_values:
                raise ValueError("WAD RLE integer channel has no values")
            if len(self.run_values) != len(self.run_lengths):
                raise ValueError(
                    "WAD RLE integer value and run-length counts do not match"
                )
            if any(length <= 0 for length in self.run_lengths):
                raise ValueError("WAD RLE integer run lengths must be positive")
            run_index = bisect_right(self._run_ends, frame)
            return self.run_values[min(run_index, len(self.run_values) - 1)]
        if self.vector is not None:
            return self.vector
        if self._raw_data:
            index = frame % self._raw_count
            return struct.unpack_from(
                f"<{self._raw_code}",
                self._raw_data,
                index * struct.calcsize(self._raw_code),
            )[0]
        if (
            self._quantized_data
            and self._quantized_element_count
            and self.scale is not None
            and self.offset is not None
        ):
            index = frame % self._quantized_element_count
            return (self._quantized_value_at(index) * self.scale) + self.offset
        if not self.values:
            return 0.0
        return self.values[frame % len(self.values)]

    evaluate = value_at


@dataclass(frozen=True, slots=True)
class WadChunk:
    bone_id: WadBoneId
    channels: tuple[WadChannel, ...]
    pointer: int = field(default=0, repr=False, compare=False)

    @property
    def component_count(self) -> int:
        return sum(channel.component_count for channel in self.channels)

    def value_at(self, frame: int) -> AnimationValue:
        """Evaluate the serialized components without coercing integers to floats."""

        result: list[Scalar] = []
        for channel in self.channels:
            value = channel.value_at(frame)
            if isinstance(value, tuple):
                result.extend(value)
            else:
                result.append(value)
        if not result:
            return 0.0
        if len(result) == 1:
            return result[0]
        return tuple(result)

    def vector_at(self, frame: int) -> tuple[float, float, float, float]:
        result = [0.0, 0.0, 0.0, 0.0]
        component = 0
        for channel in self.channels:
            value = channel.value_at(frame)
            values = value if isinstance(value, tuple) else (value,)
            for item in values:
                if component >= 4:
                    break
                result[component] = float(item)
                component += 1
        return tuple(result)  # type: ignore[return-value]

    evaluate = vector_at


@dataclass(frozen=True, slots=True)
class WadTrack:
    chunks: tuple[WadChunk, ...]
    descriptor: WadBoneId
    frames_per_chunk: int
    flags: int
    pointer: int = field(default=0, repr=False, compare=False)
    _chunks_by_target: dict[tuple[int, int], WadChunk] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _chunks_by_bone: dict[int, WadChunk] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _chunks_by_track: dict[int, WadChunk] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        by_target: dict[tuple[int, int], WadChunk] = {}
        by_bone: dict[int, WadChunk] = {}
        by_track: dict[int, WadChunk] = {}
        for chunk in self.chunks:
            identifier = chunk.bone_id
            by_target.setdefault(identifier.target_key, chunk)
            by_bone.setdefault(identifier.bone_id, chunk)
            by_track.setdefault(identifier.track_id, chunk)
        object.__setattr__(self, "_chunks_by_target", by_target)
        object.__setattr__(self, "_chunks_by_bone", by_bone)
        object.__setattr__(self, "_chunks_by_track", by_track)

    def find_chunk(self, bone_id: int, track_id: int | WadTrackId | None = None) -> WadChunk | None:
        if track_id is None:
            return self._chunks_by_bone.get(bone_id)
        return self._chunks_by_target.get((bone_id, int(track_id)))

    def find_track_chunk(self, track_id: int | WadTrackId) -> WadChunk | None:
        return self._chunks_by_track.get(int(track_id))


@dataclass(frozen=True, slots=True)
class WadAnimation:
    name: str
    flags: WadAnimationFlags
    project_flags: int
    frame_count: int
    frames_per_chunk: int
    duration: float
    signature: int
    tracks: tuple[WadTrack, ...]
    vft: int = field(default=0, repr=False, compare=False)
    pointer: int = field(default=0, repr=False, compare=False)
    _targets: tuple[AnimationTrackTarget, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _targets_by_key: dict[tuple[int, int], AnimationTrackTarget] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _skeletal_tracks: tuple[WadBoneId, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _skeletal_bone_ids: tuple[int, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _skeletal_target_keys: frozenset[tuple[int, int]] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        unique: dict[tuple[int, int], WadBoneId] = {}
        target_chunks: dict[tuple[int, int], WadChunk] = {}
        for group in self.tracks:
            for chunk in group.chunks:
                identifier = chunk.bone_id
                unique.setdefault(identifier.target_key, identifier)
                target_chunks.setdefault(identifier.target_key, chunk)
                if identifier.is_skeletal_transform:
                    continue
        targets = tuple(
            self._make_track_target(identifier, target_chunks[key])
            for key, identifier in unique.items()
        )
        target_index = {target.key: target for target in targets}
        object.__setattr__(self, "_targets", targets)
        object.__setattr__(self, "_targets_by_key", target_index)
        skeletal = tuple(
            identifier
            for identifier in unique.values()
            if identifier.is_skeletal_transform
        )
        object.__setattr__(self, "_skeletal_tracks", skeletal)
        object.__setattr__(
            self,
            "_skeletal_bone_ids",
            tuple(dict.fromkeys(item.bone_id for item in skeletal)),
        )
        object.__setattr__(
            self,
            "_skeletal_target_keys",
            frozenset(item.target_key for item in skeletal),
        )

    @staticmethod
    def _make_track_target(
        identifier: WadBoneId,
        chunk: WadChunk,
    ) -> AnimationTrackTarget:
        track_type = identifier.track_type
        if track_type is WadTrackType.INTEGER:
            interpolation = AnimationTrackInterpolation.STEP
        elif track_type is WadTrackType.QUATERNION:
            interpolation = AnimationTrackInterpolation.QUATERNION
        else:
            interpolation = AnimationTrackInterpolation.LINEAR
        component_count = chunk.component_count
        if interpolation is AnimationTrackInterpolation.QUATERNION:
            component_count = 4
        return AnimationTrackTarget(
            target_id=identifier.bone_id,
            track_id=identifier.track_id,
            component_count=max(component_count, 1),
            interpolation=interpolation,
            target_name=identifier.bone_name,
            track_name=identifier.track_name,
        )

    @property
    def short_name(self) -> str:
        return _wad_short_name(self.name)

    @property
    def uv_material_index(self) -> int | None:
        """Infer the material index from the conventional ``_uv_<index>`` suffix."""

        match = _WAD_UV_ANIMATION_NAME.fullmatch(self.short_name)
        return None if match is None else int(match.group("material"))

    @property
    def uv_base_name(self) -> str | None:
        """Return the UV animation name without its material-index suffix."""

        match = _WAD_UV_ANIMATION_NAME.fullmatch(self.short_name)
        return None if match is None else match.group("name")

    @property
    def is_uv_animation(self) -> bool:
        return self.uv_material_index is not None

    @property
    def frame_rate(self) -> float:
        if self.duration <= 0.0 or self.frame_count <= 1:
            return 0.0
        return (self.frame_count - 1) / self.duration

    @property
    def frames_per_group(self) -> int:
        """Decoded sample count covered by a full serialized track group."""

        if self.frames_per_chunk > 0:
            # Adjacent groups share their boundary sample. The animation field
            # is the stride, while a full group contains one extra sample.
            return self.frames_per_chunk + 1
        return 0 if not self.tracks else self.tracks[0].frames_per_chunk

    @property
    def frame_group_stride(self) -> int:
        """Frame distance between adjacent overlapping track groups."""

        if self.frames_per_chunk > 0:
            return self.frames_per_chunk
        frames_per_group = self.frames_per_group
        return max(frames_per_group - 1, 1) if frames_per_group else 0

    @property
    def bone_ids(self) -> tuple[WadBoneId, ...]:
        """Compatibility view of the first serialized track group."""

        return () if not self.tracks else tuple(chunk.bone_id for chunk in self.tracks[0].chunks)

    @property
    def targets(self) -> tuple[AnimationTrackTarget, ...]:
        """All logical targets across every serialized track group."""

        return self._targets

    @property
    def kinds(self) -> tuple[WadTrackKind, ...]:
        """Semantic track families present in this animation."""

        present = {
            classify_wad_track(target.track_id)
            for target in self.targets
        }
        return tuple(kind for kind in WadTrackKind if kind in present)

    def _has_kind(self, kind: WadTrackKind) -> bool:
        return any(
            classify_wad_track(target.track_id) is kind
            for target in self.targets
        )

    @property
    def has_skeletal_tracks(self) -> bool:
        return self._has_kind(WadTrackKind.SKELETAL)

    @property
    def has_material_tracks(self) -> bool:
        return self._has_kind(WadTrackKind.MATERIAL)

    @property
    def has_morph_tracks(self) -> bool:
        return self._has_kind(WadTrackKind.MORPH)

    @property
    def has_camera_tracks(self) -> bool:
        return self._has_kind(WadTrackKind.CAMERA)

    @property
    def has_light_tracks(self) -> bool:
        return self._has_kind(WadTrackKind.LIGHT)

    @property
    def has_action_tracks(self) -> bool:
        return self._has_kind(WadTrackKind.ACTION)

    @property
    def has_custom_tracks(self) -> bool:
        return self._has_kind(WadTrackKind.CUSTOM)

    def iter_tracks(self) -> Iterator[AnimationTrackTarget]:
        """Iterate logical tracks independently from per-block channel encoding."""

        return iter(self.targets)

    def validate(
        self,
        *,
        skeleton: ModelSkeleton | None = None,
    ) -> tuple[WadValidationIssue, ...]:
        """Return structured diagnostics without mutating the animation."""

        return validate_wad_animation(self, skeleton=skeleton)

    @property
    def skeletal_tracks(self) -> tuple[WadBoneId, ...]:
        """Logical skeletal targets, independent of per-block channel encoding."""

        return self._skeletal_tracks

    @property
    def skeletal_bone_ids(self) -> tuple[int, ...]:
        return self._skeletal_bone_ids

    def _build_skeletal_pose(
        self,
        time: float,
        evaluate: Callable[
            [int, WadTrackId],
            tuple[float, float, float, float],
        ],
    ) -> SkeletalPose:
        targets = self._skeletal_target_keys

        def transform(
            bone_id: int,
            translation_track: WadTrackId,
            rotation_track: WadTrackId,
            scale_track: WadTrackId,
        ) -> SkeletalTransform:
            def value(
                track_id: WadTrackId,
            ) -> tuple[float, float, float, float] | None:
                if (bone_id, int(track_id)) not in targets:
                    return None
                return evaluate(bone_id, track_id)

            translation = value(translation_track)
            rotation = value(rotation_track)
            scale = value(scale_track)
            return SkeletalTransform(
                translation=(
                    None
                    if translation is None
                    else (translation[0], translation[1], translation[2])
                ),
                rotation=(
                    None
                    if rotation is None
                    else normalize_quaternion(rotation)
                ),
                scale=(
                    None if scale is None else (scale[0], scale[1], scale[2])
                ),
            )

        bones = tuple(
            SkeletalBonePose(
                bone_id,
                transform(
                    bone_id,
                    WadTrackId.BONE_TRANSLATION,
                    WadTrackId.BONE_ROTATION,
                    WadTrackId.BONE_SCALE,
                ),
                transform(
                    bone_id,
                    WadTrackId.MOVER_TRANSLATION,
                    WadTrackId.MOVER_ROTATION,
                    WadTrackId.MOVER_SCALE,
                ),
            )
            for bone_id in self.skeletal_bone_ids
        )
        if not bones:
            raise ValueError("WAD animation has no skeletal transform tracks")
        return SkeletalPose(time, bones)

    def skeletal_pose_at(self, frame: int) -> SkeletalPose:
        """Project an integer WAD frame into a format-neutral skeletal pose."""

        if frame < 0:
            raise ValueError("WAD animation frame cannot be negative")
        count = max(self.frame_count, 1)
        frame = min(frame, count - 1)
        time = (
            0.0
            if count <= 1 or self.duration <= 0.0
            else (frame / (count - 1)) * self.duration
        )
        return self._build_skeletal_pose(
            time,
            lambda bone_id, track_id: self.vector_at(frame, bone_id, track_id),
        )

    def sample_skeletal(
        self,
        time: float,
        *,
        loop: bool | None = None,
    ) -> SkeletalPose:
        """Sample all bone and mover tracks at a time in seconds."""

        if time < 0.0:
            raise ValueError("WAD animation time cannot be negative")
        should_loop = bool(self.flags & WadAnimationFlags.LOOPED) if loop is None else loop
        sample_time = time
        if self.duration > 0.0:
            sample_time = (
                time % self.duration
                if should_loop
                else min(time, self.duration)
            )
        return self._build_skeletal_pose(
            sample_time,
            lambda bone_id, track_id: self.sample(
                time,
                bone_id,
                track_id,
                loop=should_loop,
            ),
        )

    def to_skeletal_animation(
        self,
        *,
        skeleton: ModelSkeleton | None = None,
        strict: bool = True,
    ) -> SkeletalAnimationClip:
        """Project every WAD frame into the neutral skeletal contract."""

        frames = tuple(self.iter_skeletal_poses())
        clip = SkeletalAnimationClip(
            name=self.short_name,
            duration=max(self.duration, 0.0),
            looping=bool(self.flags & WadAnimationFlags.LOOPED),
            frames=frames,
            signature=self.signature,
        )
        return (
            clip
            if skeleton is None
            else skeleton.bind_animation(clip, strict=strict)
        )

    def iter_skeletal_poses(self) -> Iterator[SkeletalPose]:
        """Yield neutral skeletal poses without retaining the complete clip."""

        for frame in range(max(self.frame_count, 1)):
            yield self.skeletal_pose_at(frame)

    def find_bone(
        self,
        bone_id: int,
        track_id: int | WadTrackId | None = None,
    ) -> WadBoneId | None:
        if not self.tracks:
            return None
        chunk = self.tracks[0].find_chunk(bone_id, track_id)
        return None if chunk is None else chunk.bone_id

    def vector_at(
        self,
        frame: int,
        bone_id: int,
        track_id: int | WadTrackId | None = None,
    ) -> tuple[float, float, float, float]:
        if not self.tracks:
            raise ValueError("WAD animation has no track groups")
        if frame < 0:
            raise ValueError("WAD animation frame cannot be negative")
        if self.frame_count:
            frame = min(frame, self.frame_count - 1)
        group_stride = self.frame_group_stride
        if group_stride <= 0:
            raise ValueError("WAD animation has no valid frames-per-chunk value")
        group_index = min(frame // group_stride, len(self.tracks) - 1)
        chunk = self.tracks[group_index].find_chunk(bone_id, track_id)
        if chunk is None:
            suffix = "" if track_id is None else f" on track {int(track_id)}"
            raise KeyError(f"WAD animation has no bone {bone_id}{suffix}")
        return chunk.vector_at(frame - (group_index * group_stride))

    evaluate_frame = vector_at

    def _group_at(self, frame: int) -> tuple[WadTrack, int]:
        if not self.tracks:
            raise ValueError("WAD animation has no track groups")
        if frame < 0:
            raise ValueError("WAD animation frame cannot be negative")
        if self.frame_count:
            frame = min(frame, self.frame_count - 1)
        group_stride = self.frame_group_stride
        if group_stride <= 0:
            raise ValueError("WAD animation has no valid frames-per-chunk value")
        group_index = min(frame // group_stride, len(self.tracks) - 1)
        return (
            self.tracks[group_index],
            frame - (group_index * group_stride),
        )

    @staticmethod
    def _track_filter(
        track_ids: Iterable[int | WadTrackId] | None,
    ) -> frozenset[int] | None:
        return (
            None
            if track_ids is None
            else frozenset(int(track_id) for track_id in track_ids)
        )

    def evaluate_tracks(
        self,
        frame: int,
        *,
        track_ids: Iterable[int | WadTrackId] | None = None,
    ) -> dict[tuple[int, int], AnimationValue]:
        """Evaluate every selected logical track at an integer frame."""

        selected = self._track_filter(track_ids)
        group, local_frame = self._group_at(frame)
        return {
            chunk.bone_id.target_key: chunk.value_at(local_frame)
            for chunk in group.chunks
            if selected is None or chunk.bone_id.track_id in selected
        }

    def track_frame_at(
        self,
        frame: int,
        *,
        track_ids: Iterable[int | WadTrackId] | None = None,
    ) -> AnimationTrackFrame:
        count = max(self.frame_count, 1)
        frame = min(max(int(frame), 0), count - 1)
        time = (
            0.0
            if count <= 1 or self.duration <= 0.0
            else (frame / (count - 1)) * self.duration
        )
        values = self.evaluate_tracks(frame, track_ids=track_ids)
        return AnimationTrackFrame(
            time,
            tuple(
                AnimationTrackValue(self._targets_by_key[key], value)
                for key, value in values.items()
            ),
        )

    def sample_tracks(
        self,
        time: float,
        *,
        track_ids: Iterable[int | WadTrackId] | None = None,
        loop: bool | None = None,
    ) -> dict[tuple[int, int], AnimationValue]:
        """Sample selected logical tracks at a time in seconds."""

        if time < 0.0:
            raise ValueError("WAD animation time cannot be negative")
        selected = self._track_filter(track_ids)
        if self.frame_count <= 1 or self.duration <= 0.0:
            return self.evaluate_tracks(0, track_ids=selected)
        should_loop = bool(self.flags & WadAnimationFlags.LOOPED) if loop is None else loop
        if should_loop:
            time %= self.duration
        else:
            time = min(time, self.duration)
        frame = time * self.frame_rate
        frame0 = min(math.floor(frame), self.frame_count - 1)
        frame1 = frame0 + 1
        if frame1 >= self.frame_count:
            frame1 = 0 if should_loop else self.frame_count - 1
        alpha = frame - frame0
        values0 = self.evaluate_tracks(frame0, track_ids=selected)
        values1 = self.evaluate_tracks(frame1, track_ids=selected)
        result: dict[tuple[int, int], AnimationValue] = {}
        for key in dict.fromkeys((*values0, *values1)):
            value0 = values0.get(key)
            value1 = values1.get(key)
            if value0 is None:
                assert value1 is not None
                result[key] = value1
            elif value1 is None:
                result[key] = value0
            else:
                result[key] = AnimationTrackValue(
                    self._targets_by_key[key],
                    value0,
                ).interpolate(
                    AnimationTrackValue(self._targets_by_key[key], value1),
                    alpha,
                ).value
        return result

    def sample_track_frame(
        self,
        time: float,
        *,
        track_ids: Iterable[int | WadTrackId] | None = None,
        loop: bool | None = None,
    ) -> AnimationTrackFrame:
        should_loop = bool(self.flags & WadAnimationFlags.LOOPED) if loop is None else loop
        sample_time = time
        if self.duration > 0.0:
            sample_time = (
                time % self.duration
                if should_loop
                else min(time, self.duration)
            )
        values = self.sample_tracks(time, track_ids=track_ids, loop=should_loop)
        return AnimationTrackFrame(
            sample_time,
            tuple(
                AnimationTrackValue(self._targets_by_key[key], value)
                for key, value in values.items()
            ),
        )

    def iter_frames(
        self,
        *,
        track_ids: Iterable[int | WadTrackId] | None = None,
    ) -> Iterator[AnimationTrackFrame]:
        """Yield neutral arbitrary-track frames without retaining a full clip."""

        for frame in range(max(self.frame_count, 1)):
            yield self.track_frame_at(frame, track_ids=track_ids)

    def to_track_animation(
        self,
        *,
        track_ids: Iterable[int | WadTrackId] | None = None,
    ) -> TrackAnimationClip:
        """Project selected WAD tracks into the format-neutral track contract."""

        selected = self._track_filter(track_ids)
        targets = tuple(
            target
            for target in self.targets
            if selected is None or target.track_id in selected
        )
        return TrackAnimationClip(
            name=self.short_name,
            duration=max(self.duration, 0.0),
            looping=bool(self.flags & WadAnimationFlags.LOOPED),
            targets=targets,
            frames=tuple(self.iter_frames(track_ids=selected)),
            signature=self.signature,
        )

    def to_data(
        self,
        *,
        track_ids: Iterable[int | WadTrackId] | None = None,
    ) -> dict[str, object]:
        """Return primitive neutral track data for external converters."""

        return self.to_track_animation(track_ids=track_ids).to_data()

    def sample(
        self,
        time: float,
        bone_id: int,
        track_id: int | WadTrackId | None = None,
        *,
        loop: bool | None = None,
    ) -> tuple[float, float, float, float]:
        if time < 0.0:
            raise ValueError("WAD animation time cannot be negative")
        if self.frame_count <= 1 or self.duration <= 0.0:
            return self.vector_at(0, bone_id, track_id)
        should_loop = bool(self.flags & WadAnimationFlags.LOOPED) if loop is None else loop
        if should_loop:
            time %= self.duration
        else:
            time = min(time, self.duration)
        frame = time * self.frame_rate
        frame0 = min(math.floor(frame), self.frame_count - 1)
        frame1 = frame0 + 1
        if frame1 >= self.frame_count:
            frame1 = 0 if should_loop else self.frame_count - 1
        alpha = frame - frame0
        value0 = self.vector_at(frame0, bone_id, track_id)
        value1 = self.vector_at(frame1, bone_id, track_id)
        identifier = self.find_bone(bone_id, track_id)
        if identifier is not None and identifier.track_type is WadTrackType.QUATERNION:
            return interpolate_quaternion(value0, value1, alpha)
        return tuple(
            start + ((end - start) * alpha) for start, end in zip(value0, value1, strict=True)
        )  # type: ignore[return-value]

    def uv_transform_at(self, frame: int) -> UvTransform:
        """Evaluate the two UV matrix-row tracks at an integer frame."""

        if not self.tracks:
            raise ValueError("WAD animation has no track groups")
        if frame < 0:
            raise ValueError("WAD animation frame cannot be negative")
        if self.frame_count:
            frame = min(frame, self.frame_count - 1)
        group_stride = self.frame_group_stride
        if group_stride <= 0:
            raise ValueError("WAD animation has no valid frames-per-chunk value")
        group_index = min(frame // group_stride, len(self.tracks) - 1)
        group = self.tracks[group_index]
        local_frame = frame - (group_index * group_stride)
        row_u_chunk = group.find_track_chunk(WadTrackId.SHADER_SLIDE_U)
        row_v_chunk = group.find_track_chunk(WadTrackId.SHADER_SLIDE_V)
        if row_u_chunk is None and row_v_chunk is None:
            raise ValueError("WAD animation has no UV matrix-row tracks")
        row_u = (
            UvTransform.identity().row_u
            if row_u_chunk is None
            else row_u_chunk.vector_at(local_frame)
        )
        row_v = (
            UvTransform.identity().row_v
            if row_v_chunk is None
            else row_v_chunk.vector_at(local_frame)
        )
        return UvTransform(row_u, row_v)

    def to_uv_animation(self, *, material_index: int | None = None) -> UvAnimationClip:
        """Project this WAD animation into the target-independent UV contract."""

        target_index = self.uv_material_index if material_index is None else material_index
        if target_index is None:
            raise ValueError(
                "WAD UV animation needs an explicit material index or a _uv_<index> suffix"
            )
        if target_index < 0:
            raise ValueError("WAD UV material index cannot be negative")
        count = max(self.frame_count, 1)
        if count == 1 or self.duration <= 0.0:
            times = (0.0,)
        else:
            times = tuple((index / (count - 1)) * self.duration for index in range(count))
        frames = tuple(
            UvAnimationFrame(time, self.uv_transform_at(index))
            for index, time in enumerate(times)
        )
        return UvAnimationClip(
            name=self.uv_base_name or self.short_name,
            target_index=target_index,
            duration=max(self.duration, 0.0),
            looping=bool(self.flags & WadAnimationFlags.LOOPED),
            frames=frames,
        )


@dataclass(frozen=True, slots=True)
class WadEntry:
    name_hash: int
    animation: WadAnimation
    pointer: int = field(default=0, repr=False, compare=False)

    @property
    def hash_hex(self) -> str:
        return f"{self.name_hash:08x}"


@dataclass(slots=True)
class WadDocument:
    entries: tuple[WadEntry, ...]
    resource: Rsc5Resource
    reserved: int = 0
    usage_count: int = 1
    name: str = "animations.wad"
    source_path: str = ""
    _entries_by_hash: dict[int, WadEntry] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._entries_by_hash = {entry.name_hash: entry for entry in self.entries}
        if len(self._entries_by_hash) != len(self.entries):
            raise ValueError("WAD contains duplicate animation hashes")

    @classmethod
    def from_path(cls, path: str | Path) -> WadDocument:
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name)
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "animations.wad") -> WadDocument:
        resource = Rsc5Resource.from_bytes(data)
        if resource.version != WAD_RESOURCE_VERSION:
            raise ValueError(f"unsupported WAD resource version: {resource.version:#x}")
        if len(resource.virtual_data) < WAD_DICTIONARY_SIZE:
            raise ValueError("truncated WAD animation dictionary")
        reader = _WadReader(resource)
        reserved, usage_count = struct.unpack_from("<2I", resource.virtual_data, 8)
        hashes = reader.plain_array(RSC5_VIRTUAL_BASE + 0x10, "I", "WAD animation hashes")
        pointers = reader.plain_array(
            RSC5_VIRTUAL_BASE + 0x18,
            "I",
            "WAD animation pointers",
        )
        if len(hashes) != len(pointers):
            raise ValueError("WAD hash and animation counts do not match")
        entries: list[WadEntry] = []
        seen_hashes: set[int] = set()
        for name_hash, pointer in zip(hashes, pointers, strict=True):
            if name_hash in seen_hashes:
                raise ValueError(f"WAD contains duplicate animation hash: {name_hash:08x}")
            if pointer == 0:
                raise ValueError(f"WAD animation {name_hash:08x} has a null pointer")
            seen_hashes.add(name_hash)
            entries.append(WadEntry(name_hash, reader.parse_animation(pointer), pointer))
        return cls(tuple(entries), resource, reserved, usage_count, name)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[WadEntry]:
        return iter(self.entries)

    def __getitem__(self, name_or_hash: str | bytes | int) -> WadEntry:
        entry = self.find_entry(name_or_hash)
        if entry is None:
            raise KeyError(name_or_hash)
        return entry

    @property
    def hashes(self) -> tuple[int, ...]:
        return tuple(entry.name_hash for entry in self.entries)

    @property
    def animations(self) -> tuple[WadAnimation, ...]:
        return tuple(entry.animation for entry in self.entries)

    def find_entry(self, name_or_hash: str | bytes | int) -> WadEntry | None:
        if isinstance(name_or_hash, int):
            return self._entries_by_hash.get(name_or_hash)
        if isinstance(name_or_hash, bytes):
            value = name_or_hash.decode("utf-8", errors="replace")
        else:
            value = name_or_hash
        short_name = _wad_short_name(value)
        candidates = (
            wad_animation_hash(short_name),
            joaat(short_name),
        )
        return next(
            (
                entry
                for candidate in dict.fromkeys(candidates)
                if (entry := self._entries_by_hash.get(candidate)) is not None
            ),
            None,
        )

    def find_animation(self, name_or_hash: str | bytes | int) -> WadAnimation | None:
        entry = self.find_entry(name_or_hash)
        return None if entry is None else entry.animation

    def validate(
        self,
        *,
        skeleton: ModelSkeleton | None = None,
    ) -> tuple[WadValidationIssue, ...]:
        """Return structured dictionary and animation diagnostics."""

        return validate_wad_document(self, skeleton=skeleton)

    def audit(
        self,
        *,
        skeleton: ModelSkeleton | None = None,
    ) -> WadAuditReport:
        """Summarize structures, semantic track families, and validation issues."""

        return audit_wad_document(self, skeleton=skeleton)

    def to_bytes(self) -> bytes:
        """Return the original lossless RSC5 resource."""

        return self.resource.to_bytes()

    def save(self, path: str | Path) -> None:
        atomic_write(path, self.to_bytes())


class _WadReader:
    def __init__(self, resource: Rsc5Resource):
        self.resource = resource
        self._channels: dict[int, WadChannel] = {}

    def _allocation(self, pointer: int) -> tuple[bytes, int, str]:
        base = pointer & 0xF0000000
        if base == RSC5_VIRTUAL_BASE:
            return self.resource.virtual_data, rsc5_pointer_offset(pointer), "virtual"
        if base == RSC5_PHYSICAL_BASE:
            return (
                self.resource.physical_data,
                rsc5_pointer_offset(pointer, physical=True),
                "physical",
            )
        raise ValueError(f"invalid WAD RSC5 pointer: {pointer:#x}")

    def read(self, pointer: int, size: int, label: str) -> bytes:
        if pointer == 0:
            raise ValueError(f"{label} has a null pointer")
        data, offset, allocation = self._allocation(pointer)
        if size < 0 or offset + size > len(data):
            raise ValueError(f"{label} exceeds the WAD {allocation} allocation")
        return data[offset : offset + size]

    def unpack(self, pointer: int, format_: str, label: str) -> tuple:
        return struct.unpack(format_, self.read(pointer, struct.calcsize(format_), label))

    def string(self, pointer: int, label: str) -> str:
        data, offset, allocation = self._allocation(pointer)
        end = data.find(b"\0", offset)
        if end < 0:
            raise ValueError(f"unterminated {label} in the WAD {allocation} allocation")
        return data[offset:end].decode("utf-8", errors="replace")

    def array_header(self, pointer: int, label: str) -> tuple[int, int]:
        data_pointer, count, capacity = self.unpack(pointer, "<IHH", f"{label} header")
        if count > capacity:
            raise ValueError(f"{label} count exceeds its capacity")
        if count and data_pointer == 0:
            raise ValueError(f"{label} has a null data pointer")
        return data_pointer, count

    def plain_array(self, header_pointer: int, code: str, label: str) -> tuple:
        data_pointer, count = self.array_header(header_pointer, label)
        if not count:
            return ()
        format_ = f"<{count}{code}"
        return self.unpack(data_pointer, format_, label)

    def pointer_array(self, header_pointer: int, label: str) -> tuple[int, ...]:
        return self.plain_array(header_pointer, "I", label)

    def bone_id(self, pointer: int, label: str) -> WadBoneId:
        track_id, type_id, bone_id = self.unpack(pointer, "<BBH", label)
        return WadBoneId(track_id, type_id, bone_id)

    def parse_animation(self, pointer: int) -> WadAnimation:
        raw = self.read(pointer, WAD_ANIMATION_SIZE, "WAD animation")
        (
            vft,
            flags,
            project_flags,
            frame_count,
            frames_per_chunk,
            duration,
            signature,
        ) = struct.unpack_from("<I4HfI", raw)
        track_pointers = self.pointer_array(pointer + 0x14, "WAD animation track groups")
        name_pointer = struct.unpack_from("<I", raw, 0x1C)[0]
        name = "" if name_pointer == 0 else self.string(name_pointer, "WAD animation name")
        tracks = tuple(self.parse_track(value) for value in track_pointers)
        return WadAnimation(
            name,
            WadAnimationFlags(flags),
            project_flags,
            frame_count,
            frames_per_chunk,
            duration,
            signature,
            tracks,
            vft,
            pointer,
        )

    def parse_track(self, pointer: int) -> WadTrack:
        raw = self.read(pointer, WAD_TRACK_SIZE, "WAD animation track group")
        chunk_pointers = self.pointer_array(pointer, "WAD animation chunks")
        descriptor = WadBoneId(*struct.unpack_from("<BBH", raw, 8))
        frames_per_chunk, flags = struct.unpack_from("<HH", raw, 12)
        chunks = tuple(self.parse_chunk(value) for value in chunk_pointers)
        return WadTrack(chunks, descriptor, frames_per_chunk, flags, pointer)

    def parse_chunk(self, pointer: int) -> WadChunk:
        raw = self.read(pointer, WAD_CHUNK_SIZE, "WAD animation chunk")
        bone_id = WadBoneId(*struct.unpack_from("<BBH", raw))
        channel_pointers = struct.unpack_from("<4I", raw, 4)
        channels = tuple(
            self.parse_channel(value) for value in channel_pointers if value != 0
        )
        return WadChunk(bone_id, channels, pointer)

    def parse_channel(self, pointer: int) -> WadChannel:
        cached = self._channels.get(pointer)
        if cached is not None:
            return cached
        raw_header = self.read(pointer, WAD_CHANNEL_HEADER_SIZE, "WAD animation channel")
        vft, flags, type_value, _padding = struct.unpack("<IBBH", raw_header)
        channel_type = WadChannelType._value2member_map_.get(type_value, type_value)

        values: tuple[Scalar, ...] = ()
        vector: tuple[float, ...] | None = None
        scale: float | None = None
        offset: float | None = None
        quantized_values: tuple[int, ...] = ()
        run_values: tuple[int, ...] = ()
        packed_sequence: tuple[int, ...] = ()
        packed_sequence_words: tuple[int, ...] = ()
        packed_sequence_bit_count = 0
        packed_sequence_divisor = 0
        raw_data = b""
        raw_code = ""
        raw_count = 0
        quantized_data = b""
        quantized_element_size = 0
        quantized_element_count = 0

        if channel_type == WadChannelType.STATIC_FLOAT:
            values = (self.unpack(pointer + 8, "<f", "WAD static float channel")[0],)
        elif channel_type == WadChannelType.STATIC_INT:
            values = (self.unpack(pointer + 8, "<i", "WAD static integer channel")[0],)
        elif channel_type == WadChannelType.STATIC_VECTOR3:
            value_pointer = self.unpack(pointer + 8, "<I", "WAD static vector channel")[0]
            vector = self.unpack(value_pointer, "<3f", "WAD static vector value")
        elif channel_type == WadChannelType.STATIC_QUATERNION:
            value_pointer = self.unpack(pointer + 8, "<I", "WAD static quaternion channel")[0]
            vector = self.unpack(value_pointer, "<4f", "WAD static quaternion value")
        elif channel_type in {WadChannelType.RAW_FLOAT, WadChannelType.RAW_INT}:
            raw_code = "f" if channel_type == WadChannelType.RAW_FLOAT else "i"
            data_pointer, raw_count = self.array_header(
                pointer + 8,
                f"WAD {WadChannelType(type_value).name} values",
            )
            raw_data = (
                b""
                if raw_count == 0
                else self.read(
                    data_pointer,
                    raw_count * 4,
                    f"WAD {WadChannelType(type_value).name} values",
                )
            )
        elif channel_type == WadChannelType.QUANTIZED_FLOAT:
            data_pointer, element_size, element_count, scale, offset = self.unpack(
                pointer + 8,
                "<IIIff",
                "WAD quantized float channel",
            )
            if element_size > 32:
                raise ValueError(
                    f"WAD quantized float element size exceeds 32 bits: {element_size}"
                )
            word_count = ((element_size * element_count) + 31) >> 5
            quantized_data = self.read(
                data_pointer,
                (word_count + 1) * 4,
                "WAD quantized float bits",
            )
            quantized_element_size = element_size
            quantized_element_count = element_count
        elif channel_type == WadChannelType.RLE_INT:
            run_values = self.plain_array(pointer + 8, "i", "WAD RLE integer values")
            sequence_pointer, sequence_bits, divisor = self.unpack(
                pointer + 16,
                "<III",
                "WAD RLE integer sequence",
            )
            if divisor > 15:
                raise ValueError(f"WAD RLE integer divisor exceeds 15 bits: {divisor}")
            word_count = (sequence_bits + 31) >> 5
            words = (
                self.unpack(
                    sequence_pointer,
                    f"<{word_count}I",
                    "WAD RLE integer bits",
                )
                if word_count
                else ()
            )
            packed_sequence = self._decode_packed_sequence(
                words,
                sequence_bits,
                divisor,
                len(run_values),
            )
            packed_sequence_words = words
            packed_sequence_bit_count = sequence_bits
            packed_sequence_divisor = divisor

        channel = WadChannel(
            channel_type,
            flags,
            values,
            vector,
            scale,
            offset,
            quantized_values,
            run_values,
            packed_sequence,
            packed_sequence_words,
            packed_sequence_bit_count,
            packed_sequence_divisor,
            vft,
            pointer,
            header_bytes=raw_header,
            _raw_data=raw_data,
            _raw_code=raw_code,
            _raw_count=raw_count,
            _quantized_data=quantized_data,
            _quantized_element_size=quantized_element_size,
            _quantized_element_count=quantized_element_count,
        )
        self._channels[pointer] = channel
        return channel

    @staticmethod
    def _decode_packed_sequence(
        words: tuple[int, ...],
        bit_count: int,
        divisor: int,
        count: int,
    ) -> tuple[int, ...]:
        address = 0

        def get_bit() -> int:
            nonlocal address
            if address >= bit_count:
                raise EOFError
            value = (words[address >> 5] >> (address & 31)) & 1
            address += 1
            return value

        result: list[int] = []
        for _ in range(count):
            try:
                quotient = 0
                while get_bit() == 0:
                    quotient += 1
                remainder = 0
                for bit in range(divisor):
                    remainder |= get_bit() << bit
                value = (quotient << divisor) | remainder
                if value and get_bit():
                    value = -value
                result.append(value)
            except EOFError:
                break
        return tuple(result)


def load_wad(source: str | Path | bytes | BinaryIO) -> WadDocument:
    if isinstance(source, (str, Path)):
        return WadDocument.from_path(source)
    if isinstance(source, bytes):
        return WadDocument.from_bytes(source)
    return WadDocument.from_bytes(source.read())


__all__ = [
    "WAD_ANIMATION_SIZE",
    "WAD_BONE_TRANSFORM_TRACKS",
    "WAD_CHANNEL_HEADER_SIZE",
    "WAD_CHUNK_SIZE",
    "WAD_DICTIONARY_SIZE",
    "WAD_MOVER_TRANSFORM_TRACKS",
    "WAD_RESOURCE_VERSION",
    "WAD_SKELETAL_TRACKS",
    "WAD_TRACK_SIZE",
    "WadAnimation",
    "WadAnimationFlags",
    "WadBoneId",
    "WadBoneName",
    "WadChannel",
    "WadChannelType",
    "WadChunk",
    "WadDocument",
    "WadEntry",
    "WadTrack",
    "WadTrackId",
    "WadTrackPacking",
    "WadTrackType",
    "load_wad",
    "wad_animation_hash",
]
