from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass, field
from enum import IntFlag
from pathlib import Path
from typing import BinaryIO, ClassVar, Iterator, Literal, cast


WPL_VERSION = 3
WPL_HEADER_SIZE = 68
WPL_SECTION_SIZES = (48, 0, 48, 56, 44, 0, 0, 0, 64, 388, 24, 0, 0, 0, 0, 132)


class WplInstanceFlags(IntFlag):
    """Flags stored in a GTA IV WPL instance record.

    Names marked as inferred in :data:`WPL_INSTANCE_FLAG_INFO` come from
    matching the GTA IV loader behavior with later RAGE flag names. The
    runtime-state flags are deliberately named by the bit they set because
    their higher-level gameplay effect has not been established yet.
    """

    NONE = 0
    STREAM_LOW_PRIORITY = 0x001
    FULL_ROTATION = 0x002
    DISABLE_EMBEDDED_COLLISIONS = 0x004
    STATIC_ENTITY = 0x020
    INTERIOR_LOD = 0x040
    RUNTIME_STATE_BIT_2 = 0x080
    RUNTIME_STATE_BIT_3 = 0x100
    RUNTIME_STATE_BIT_1 = 0x200
    DETAIL_LEVEL_1 = 0x400
    DETAIL_LEVEL_2 = 0x800

    DETAIL_LEVEL_MASK = DETAIL_LEVEL_1 | DETAIL_LEVEL_2
    DEFAULT = RUNTIME_STATE_BIT_2 | RUNTIME_STATE_BIT_3


FlagConfidence = Literal["verified", "inferred", "unresolved"]


@dataclass(frozen=True, slots=True)
class WplInstanceFlagInfo:
    flag: WplInstanceFlags
    effect: str
    confidence: FlagConfidence


WPL_INSTANCE_FLAG_INFO = (
    WplInstanceFlagInfo(
        WplInstanceFlags.STREAM_LOW_PRIORITY,
        "Requests lower-priority streaming for the entity.",
        "inferred",
    ),
    WplInstanceFlagInfo(
        WplInstanceFlags.FULL_ROTATION,
        "Preserves the complete quaternion instead of using the upright fast path.",
        "verified",
    ),
    WplInstanceFlagInfo(
        WplInstanceFlags.DISABLE_EMBEDDED_COLLISIONS,
        "Disables collision data embedded in the drawable.",
        "inferred",
    ),
    WplInstanceFlagInfo(
        WplInstanceFlags.STATIC_ENTITY,
        "Marks the placement as a static entity.",
        "inferred",
    ),
    WplInstanceFlagInfo(
        WplInstanceFlags.INTERIOR_LOD,
        "Marks the placement as an interior LOD entity.",
        "inferred",
    ),
    WplInstanceFlagInfo(
        WplInstanceFlags.RUNTIME_STATE_BIT_2,
        "Sets bit 2 in the entity's secondary runtime-state word.",
        "unresolved",
    ),
    WplInstanceFlagInfo(
        WplInstanceFlags.RUNTIME_STATE_BIT_3,
        "Sets bit 3 in the entity's secondary runtime-state word.",
        "unresolved",
    ),
    WplInstanceFlagInfo(
        WplInstanceFlags.RUNTIME_STATE_BIT_1,
        "Sets bit 1 in the entity's secondary runtime-state word.",
        "unresolved",
    ),
)


_WPL_INSTANCE_SIMPLE_FLAG_MASK = sum(int(info.flag) for info in WPL_INSTANCE_FLAG_INFO)
_WPL_INSTANCE_KNOWN_FLAG_MASK = _WPL_INSTANCE_SIMPLE_FLAG_MASK | int(WplInstanceFlags.DETAIL_LEVEL_MASK)


def explain_instance_flags(flags: WplInstanceFlags | int) -> tuple[WplInstanceFlagInfo, ...]:
    """Return structured descriptions for every active instance flag."""

    value = int(flags)
    details = [info for info in WPL_INSTANCE_FLAG_INFO if value & int(info.flag)]
    detail_level = (value & int(WplInstanceFlags.DETAIL_LEVEL_MASK)) >> 10
    if detail_level:
        details.append(WplInstanceFlagInfo(
            WplInstanceFlags(value & int(WplInstanceFlags.DETAIL_LEVEL_MASK)),
            f"Requires placement detail level {detail_level}.",
            "verified",
        ))
    extra = value & ~_WPL_INSTANCE_KNOWN_FLAG_MASK
    if extra:
        details.append(WplInstanceFlagInfo(
            WplInstanceFlags(extra),
            "Preserved flag bits whose loader behavior has not been identified.",
            "unresolved",
        ))
    return tuple(details)


def _decode_string(value: bytes) -> str:
    return value.split(b"\0", 1)[0].decode("latin-1")


def _encode_string(value: str, size: int) -> bytes:
    encoded = value.encode("latin-1")
    if len(encoded) > size:
        raise ValueError(f"string exceeds its {size}-byte WPL field")
    return encoded.ljust(size, b"\0")


def _encode_preserved_string(value: str, size: int, original: bytes | None) -> bytes:
    if original is not None and _decode_string(original) == value:
        return original
    return _encode_string(value, size)


@dataclass(slots=True)
class WplInstance:
    """A section-0 map placement.

    ``lod_index`` selects the parent LOD placement. ``block_index`` is the
    BLOK association observed in stock files and may reference inherited map
    block data. A non-positive ``lod_distance`` uses the model's IDE draw
    distance instead of overriding it.
    """

    SECTION: ClassVar[int] = 0
    position_x: float
    position_y: float
    position_z: float
    rotation_x: float
    rotation_y: float
    rotation_z: float
    rotation_w: float
    model_hash: int
    flags: WplInstanceFlags = WplInstanceFlags.DEFAULT
    lod_index: int = -1
    block_index: int = 0
    lod_distance: float = -1.0

    @classmethod
    def from_bytes(cls, data: bytes) -> "WplInstance":
        values = struct.unpack("<7fIIiif", data)
        return cls(*values[:8], WplInstanceFlags(values[8]), *values[9:])

    @property
    def detail_level(self) -> int:
        """Return the two-bit placement detail level (0 through 3)."""

        return (int(self.flags) & int(WplInstanceFlags.DETAIL_LEVEL_MASK)) >> 10

    @detail_level.setter
    def detail_level(self, value: int) -> None:
        if not 0 <= value <= 3:
            raise ValueError("WPL instance detail level must be between 0 and 3")
        flags = int(self.flags) & ~int(WplInstanceFlags.DETAIL_LEVEL_MASK)
        self.flags = WplInstanceFlags(flags | (value << 10))

    @property
    def flag_info(self) -> tuple[WplInstanceFlagInfo, ...]:
        """Describe all active flag bits and the confidence of each name."""

        return explain_instance_flags(self.flags)

    def to_bytes(self) -> bytes:
        return struct.pack(
            "<7fIIiif",
            self.position_x, self.position_y, self.position_z,
            self.rotation_x, self.rotation_y, self.rotation_z, self.rotation_w,
            self.model_hash, int(self.flags), self.lod_index, self.block_index, self.lod_distance,
        )


@dataclass(slots=True)
class WplGarage:
    SECTION: ClassVar[int] = 2
    position_x1: float
    position_y1: float
    position_z1: float
    position_x2: float
    position_y2: float
    position_x3: float
    position_y3: float
    position_z3: float
    door_type: int
    garage_type: int
    garage_name: str
    _garage_name_raw: bytes | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes) -> "WplGarage":
        values = struct.unpack("<8fII8s", data)
        return cls(*values[:10], _decode_string(values[10]), _garage_name_raw=values[10])

    def to_bytes(self) -> bytes:
        return struct.pack("<8fII8s", *(
            self.position_x1, self.position_y1, self.position_z1,
            self.position_x2, self.position_y2,
            self.position_x3, self.position_y3, self.position_z3,
            self.door_type, self.garage_type,
            _encode_preserved_string(self.garage_name, 8, self._garage_name_raw),
        ))


@dataclass(slots=True)
class WplParkedCar:
    SECTION: ClassVar[int] = 3
    position_x: float
    position_y: float
    position_z: float
    placement_w: float
    rotation_x: float
    rotation_y: float
    model_hash: int
    primary_color: int = 0
    secondary_color: int = 0
    tertiary_color: int = 0
    specular_color: int = 0
    flags: int = 0
    alarm_probability: int = 0
    reserved: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> "WplParkedCar":
        return cls(*struct.unpack("<6fI7i", data))

    def to_bytes(self) -> bytes:
        return struct.pack("<6fI7i", *(
            self.position_x, self.position_y, self.position_z,
            self.placement_w, self.rotation_x, self.rotation_y,
            self.model_hash, self.primary_color, self.secondary_color, self.tertiary_color,
            self.specular_color, self.flags, self.alarm_probability, self.reserved,
        ))


@dataclass(slots=True)
class WplTimeCycleModifier:
    SECTION: ClassVar[int] = 4
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float
    parameter_1: int = 0
    parameter_2: int = 0
    parameter_3: int = 0
    parameter_4: int = 0
    model_hash: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> "WplTimeCycleModifier":
        return cls(*struct.unpack("<6f4iI", data))

    def to_bytes(self) -> bytes:
        return struct.pack("<6f4iI", *(
            self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z,
            self.parameter_1, self.parameter_2, self.parameter_3, self.parameter_4, self.model_hash,
        ))


# Kept as an alias for code written against fourfury's initial name for section 4.
WplCull = WplTimeCycleModifier


@dataclass(slots=True)
class WplStrBig:
    SECTION: ClassVar[int] = 8
    model_name: str
    flags: int
    interior_index: int
    reserved: int
    position_x: float
    position_y: float
    position_z: float
    rotation_x: float
    rotation_y: float
    rotation_z: float
    rotation_w: float
    _model_name_raw: bytes | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes) -> "WplStrBig":
        values = struct.unpack("<24sIII7f", data)
        return cls(_decode_string(values[0]), *values[1:], _model_name_raw=values[0])

    def to_bytes(self) -> bytes:
        return struct.pack(
            "<24sIII7f", _encode_preserved_string(self.model_name, 24, self._model_name_raw),
            self.flags, self.interior_index, self.reserved,
            self.position_x, self.position_y, self.position_z,
            self.rotation_x, self.rotation_y, self.rotation_z, self.rotation_w,
        )


@dataclass(slots=True)
class WplLodCull:
    SECTION: ClassVar[int] = 9
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float
    reserved: int
    hashes: tuple[int, ...]
    model_names: tuple[str, ...]
    _model_names_raw: tuple[bytes, ...] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.hashes) != 10 or len(self.model_names) != 10:
            raise ValueError("WPL LOD cull records require exactly ten hashes and model names")

    @classmethod
    def from_bytes(cls, data: bytes) -> "WplLodCull":
        prefix = struct.unpack_from("<6f11I", data)
        raw_names = tuple(data[68 + index * 32 : 100 + index * 32] for index in range(10))
        names = tuple(_decode_string(value) for value in raw_names)
        return cls(*prefix[:7], tuple(prefix[7:]), names, raw_names)

    def to_bytes(self) -> bytes:
        output = bytearray(struct.pack(
            "<6f11I", self.min_x, self.min_y, self.min_z,
            self.max_x, self.max_y, self.max_z, self.reserved, *self.hashes,
        ))
        for index, name in enumerate(self.model_names):
            original = self._model_names_raw[index] if self._model_names_raw is not None else None
            output.extend(_encode_preserved_string(name, 32, original))
        return bytes(output)


@dataclass(slots=True)
class WplZone:
    SECTION: ClassVar[int] = 10
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @classmethod
    def from_bytes(cls, data: bytes) -> "WplZone":
        return cls(*struct.unpack("<6f", data))

    def to_bytes(self) -> bytes:
        return struct.pack("<6f", self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z)


@dataclass(slots=True)
class WplBlock:
    SECTION: ClassVar[int] = 15
    reserved_1: int
    text: str
    reserved_2: int
    x1: float
    y1: float
    x2: float
    y2: float
    x3: float
    y3: float
    x4: float
    y4: float
    _text_raw: bytes | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_bytes(cls, data: bytes) -> "WplBlock":
        values = struct.unpack("<I92sI8f", data)
        return cls(values[0], _decode_string(values[1]), *values[2:], _text_raw=values[1])

    def to_bytes(self) -> bytes:
        return struct.pack(
            "<I92sI8f", self.reserved_1, _encode_preserved_string(self.text, 92, self._text_raw), self.reserved_2,
            self.x1, self.y1, self.x2, self.y2, self.x3, self.y3, self.x4, self.y4,
        )


WplRecord = WplInstance | WplGarage | WplParkedCar | WplTimeCycleModifier | WplStrBig | WplLodCull | WplZone | WplBlock
_RECORD_TYPES = {
    0: WplInstance, 2: WplGarage, 3: WplParkedCar, 4: WplTimeCycleModifier,
    8: WplStrBig, 9: WplLodCull, 10: WplZone, 15: WplBlock,
}


@dataclass(slots=True)
class WplDocument:
    name: str = "placement.wpl"
    source_path: str = ""
    version: int = WPL_VERSION
    sections: dict[int, list[WplRecord]] = field(default_factory=dict)
    trailing_data: bytes = b""

    @classmethod
    def empty(cls, name: str = "placement.wpl") -> "WplDocument":
        return cls(name=name if name.lower().endswith(".wpl") else f"{name}.wpl")

    @classmethod
    def from_path(cls, path: str | Path) -> "WplDocument":
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name)
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "placement.wpl") -> "WplDocument":
        if len(data) < WPL_HEADER_SIZE:
            raise ValueError("truncated WPL header")
        header = struct.unpack_from("<17I", data)
        if header[0] != WPL_VERSION:
            raise ValueError(f"unsupported WPL version: {header[0]}")
        document = cls(name=name, version=header[0])
        cursor = WPL_HEADER_SIZE
        for section, count in enumerate(header[1:]):
            if not count:
                continue
            size = WPL_SECTION_SIZES[section]
            record_type = _RECORD_TYPES.get(section)
            if not size or record_type is None:
                raise ValueError(f"unsupported non-empty WPL section: {section}")
            end = cursor + count * size
            if end > len(data):
                raise ValueError(f"truncated WPL section {section}")
            document.sections[section] = [
                record_type.from_bytes(data[offset : offset + size])
                for offset in range(cursor, end, size)
            ]
            cursor = end
        document.trailing_data = bytes(data[cursor:])
        return document

    def records(self, section: int) -> list[WplRecord]:
        if not 0 <= section < 16:
            raise ValueError("WPL section must be between 0 and 15")
        return self.sections.setdefault(section, [])

    @property
    def instances(self) -> list[WplInstance]:
        return cast(list[WplInstance], self.records(0))

    @property
    def garages(self) -> list[WplGarage]:
        return cast(list[WplGarage], self.records(2))

    @property
    def parked_cars(self) -> list[WplParkedCar]:
        return cast(list[WplParkedCar], self.records(3))

    @property
    def culls(self) -> list[WplCull]:
        return cast(list[WplCull], self.records(4))

    @property
    def time_cycle_modifiers(self) -> list[WplTimeCycleModifier]:
        return cast(list[WplTimeCycleModifier], self.records(4))

    @property
    def strbig(self) -> list[WplStrBig]:
        return cast(list[WplStrBig], self.records(8))

    @property
    def lod_culls(self) -> list[WplLodCull]:
        return cast(list[WplLodCull], self.records(9))

    @property
    def zones(self) -> list[WplZone]:
        return cast(list[WplZone], self.records(10))

    @property
    def blocks(self) -> list[WplBlock]:
        return cast(list[WplBlock], self.records(15))

    def add(self, record: WplRecord) -> WplRecord:
        self.records(record.SECTION).append(record)
        return record

    def __iter__(self) -> Iterator[WplRecord]:
        for section in range(16):
            yield from self.sections.get(section, ())

    def to_bytes(self) -> bytes:
        counts = [0] * 16
        payload = bytearray()
        for section in range(16):
            records = self.sections.get(section, [])
            counts[section] = len(records)
            for record in records:
                if record.SECTION != section:
                    raise ValueError(f"record type does not belong in WPL section {section}")
                raw = record.to_bytes()
                if len(raw) != WPL_SECTION_SIZES[section]:
                    raise ValueError(f"invalid WPL section {section} record size")
                payload.extend(raw)
        return struct.pack("<17I", self.version, *counts) + payload + self.trailing_data

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(self.to_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


def load_wpl(source: str | Path | bytes | BinaryIO) -> WplDocument:
    if isinstance(source, (str, Path)):
        return WplDocument.from_path(source)
    if isinstance(source, bytes):
        return WplDocument.from_bytes(source)
    return WplDocument.from_bytes(source.read())


def create_wpl(name: str = "placement.wpl") -> WplDocument:
    return WplDocument.empty(name)


__all__ = [
    "FlagConfidence", "WPL_HEADER_SIZE", "WPL_INSTANCE_FLAG_INFO", "WPL_SECTION_SIZES",
    "WPL_VERSION", "WplBlock", "WplCull", "WplDocument", "WplGarage", "WplInstance",
    "WplInstanceFlagInfo", "WplInstanceFlags", "WplLodCull", "WplParkedCar", "WplRecord",
    "WplStrBig", "WplTimeCycleModifier", "WplZone", "create_wpl", "explain_instance_flags",
    "load_wpl",
]
