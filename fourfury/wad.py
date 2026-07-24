from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from pathlib import Path
from typing import BinaryIO, Iterator

from ._utils import atomic_write
from .rsc import (
    RSC5_PHYSICAL_BASE,
    RSC5_VIRTUAL_BASE,
    Rsc5Resource,
    rsc5_pointer_offset,
)
from .wbd import joaat


WAD_RESOURCE_VERSION = 1
WAD_DICTIONARY_SIZE = 0x20
WAD_ANIMATION_SIZE = 0x20
WAD_TRACK_SIZE = 0x10
WAD_CHUNK_SIZE = 0x18
WAD_CHANNEL_HEADER_SIZE = 0x08


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
    def track_type(self) -> WadTrackType:
        return WadTrackType(self.type_id & 0x03)

    @property
    def packing(self) -> WadTrackPacking:
        return WadTrackPacking(self.type_id & 0x0C)

    @property
    def action_flags(self) -> bool:
        return bool(self.track_id & 0x80)

    @property
    def track(self) -> WadTrackId | None:
        try:
            return WadTrackId(self.track_id & 0x7F)
        except ValueError:
            return None

    @property
    def track_name(self) -> str:
        track = self.track
        name = track.name if track is not None else f"TRACK_{self.track_id & 0x7F}"
        return f"ACTION_FLAGS|{name}" if self.action_flags else name

    @property
    def bone(self) -> WadBoneName | None:
        try:
            return WadBoneName(self.bone_id)
        except ValueError:
            return None

    @property
    def bone_name(self) -> str:
        bone = self.bone
        return bone.name if bone is not None else f"BONE_{self.bone_id}"


Scalar = float | int
ChannelValue = Scalar | tuple[float, ...]


@dataclass(frozen=True, slots=True)
class WadChannel:
    channel_type: WadChannelType
    flags: int
    values: tuple[Scalar, ...] = ()
    vector: tuple[float, ...] | None = None
    scale: float | None = None
    offset: float | None = None
    quantized_values: tuple[int, ...] = ()
    run_values: tuple[int, ...] = ()
    packed_sequence: tuple[int, ...] = ()
    packed_sequence_words: tuple[int, ...] = ()
    packed_sequence_bit_count: int = 0
    packed_sequence_divisor: int = 0
    vft: int = field(default=0, repr=False, compare=False)
    pointer: int = field(default=0, repr=False, compare=False)

    @property
    def is_static(self) -> bool:
        return self.channel_type in {
            WadChannelType.STATIC_FLOAT,
            WadChannelType.STATIC_INT,
            WadChannelType.STATIC_VECTOR3,
            WadChannelType.STATIC_QUATERNION,
        }

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
        if self.channel_type == WadChannelType.RLE_INT:
            raise NotImplementedError(
                "WAD RLE integer timing expansion is not currently implemented"
            )
        if self.vector is not None:
            return self.vector
        if not self.values:
            return 0.0
        return self.values[frame % len(self.values)]

    evaluate = value_at


@dataclass(frozen=True, slots=True)
class WadChunk:
    bone_id: WadBoneId
    channels: tuple[WadChannel, ...]
    pointer: int = field(default=0, repr=False, compare=False)

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

    def find_chunk(self, bone_id: int, track_id: int | WadTrackId | None = None) -> WadChunk | None:
        track_value = None if track_id is None else int(track_id)
        for chunk in self.chunks:
            identifier = chunk.bone_id
            if identifier.bone_id != bone_id:
                continue
            if track_value is None or identifier.track_id == track_value:
                return chunk
        return None


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

    @property
    def short_name(self) -> str:
        name = self.name.replace("\\", "/").rsplit("/", 1)[-1]
        return name[:-5] if name.casefold().endswith(".anim") else name

    @property
    def frame_rate(self) -> float:
        if self.duration <= 0.0 or self.frame_count <= 1:
            return 0.0
        return (self.frame_count - 1) / self.duration

    @property
    def bone_ids(self) -> tuple[WadBoneId, ...]:
        return () if not self.tracks else tuple(chunk.bone_id for chunk in self.tracks[0].chunks)

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
        frames_per_chunk = self.frames_per_chunk or self.tracks[0].frames_per_chunk
        if frames_per_chunk <= 0:
            raise ValueError("WAD animation has no valid frames-per-chunk value")
        group_index = min(frame // frames_per_chunk, len(self.tracks) - 1)
        chunk = self.tracks[group_index].find_chunk(bone_id, track_id)
        if chunk is None:
            suffix = "" if track_id is None else f" on track {int(track_id)}"
            raise KeyError(f"WAD animation has no bone {bone_id}{suffix}")
        return chunk.vector_at(frame % frames_per_chunk)

    evaluate_frame = vector_at

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
        return tuple(
            start + ((end - start) * alpha) for start, end in zip(value0, value1, strict=True)
        )  # type: ignore[return-value]


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
            target = name_or_hash
        else:
            if isinstance(name_or_hash, bytes):
                value = name_or_hash.decode("utf-8", errors="replace")
            else:
                value = name_or_hash
            value = value.replace("\\", "/").rsplit("/", 1)[-1]
            if value.casefold().endswith(".anim"):
                value = value[:-5]
            target = joaat(value)
        return self._entries_by_hash.get(target)

    def find_animation(self, name_or_hash: str | bytes | int) -> WadAnimation | None:
        entry = self.find_entry(name_or_hash)
        return None if entry is None else entry.animation

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
        vft, flags, type_value, _padding = self.unpack(
            pointer,
            "<IBBH",
            "WAD animation channel",
        )
        try:
            channel_type = WadChannelType(type_value)
        except ValueError as exc:
            raise ValueError(f"unsupported WAD animation channel type: {type_value}") from exc

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
            code = "f" if channel_type == WadChannelType.RAW_FLOAT else "i"
            values = self.plain_array(pointer + 8, code, f"WAD {channel_type.name} values")
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
            words = self.unpack(
                data_pointer,
                f"<{word_count + 1}I",
                "WAD quantized float bits",
            )
            mask = 0xFFFFFFFF if element_size == 32 else (1 << element_size) - 1
            decoded: list[int] = []
            for index in range(element_count):
                bit_address = index * element_size
                block = bit_address >> 5
                bit = bit_address & 31
                pair = words[block] | (words[block + 1] << 32)
                decoded.append((pair >> bit) & mask)
            quantized_values = tuple(decoded)
            values = tuple((value * scale) + offset for value in quantized_values)
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
            # The packed sequence contains one signed transition code between
            # adjacent values. GTA IV's runtime expansion of those codes is not
            # yet understood well enough to present it as frame values.
            packed_sequence = self._decode_packed_sequence(
                words,
                sequence_bits,
                divisor,
                max(0, len(run_values) - 1),
            )
            packed_sequence_words = words
            packed_sequence_bit_count = sequence_bits
            packed_sequence_divisor = divisor
        else:
            raise ValueError(
                f"WAD animation channel type {channel_type.name} is not implemented"
            )

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
                remainder = 0
                for bit in range(divisor):
                    remainder |= get_bit() << bit
                quotient = 0
                while get_bit() == 0:
                    quotient += 1
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
    "WAD_CHANNEL_HEADER_SIZE",
    "WAD_CHUNK_SIZE",
    "WAD_DICTIONARY_SIZE",
    "WAD_RESOURCE_VERSION",
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
]
