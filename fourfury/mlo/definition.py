from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import chain
from typing import TYPE_CHECKING, Iterable

from ..ide import IdeArchetypeFlags, IdeDocument, IdeEntry
from ..wbd import joaat

if TYPE_CHECKING:
    from ..wpl import WplDocument, WplInstance, WplInstanceFlags

MloVector3 = tuple[float, float, float]
MloQuaternion = tuple[float, float, float, float]


def _require(entry: IdeEntry, count: int, label: str) -> None:
    if len(entry.values) < count:
        location = (
            ""
            if entry.line_number is None
            else f" at IDE line {entry.line_number}"
        )
        raise ValueError(
            f"{label}{location} requires at least {count} comma-separated values"
        )


def _vector3(entry: IdeEntry, offset: int) -> MloVector3:
    return (
        float(entry.values[offset]),
        float(entry.values[offset + 1]),
        float(entry.values[offset + 2]),
    )


def _set_vector3(entry: IdeEntry, offset: int, value: MloVector3) -> None:
    entry.values[offset : offset + 3] = [str(float(item)) for item in value]


def _quaternion(entry: IdeEntry, offset: int) -> MloQuaternion:
    return (
        float(entry.values[offset]),
        float(entry.values[offset + 1]),
        float(entry.values[offset + 2]),
        float(entry.values[offset + 3]),
    )


def _set_quaternion(
    entry: IdeEntry,
    offset: int,
    value: MloQuaternion,
) -> None:
    entry.values[offset : offset + 4] = [str(float(item)) for item in value]


@dataclass(slots=True)
class MloEntity:
    """An entity placed in an MLO archetype's local coordinate system."""

    entry: IdeEntry = field(repr=False)
    index: int = 0

    def __post_init__(self) -> None:
        _require(self.entry, 10, "MLO entity")

    @property
    def name(self) -> str:
        return self.entry.values[0]

    @name.setter
    def name(self, value: str) -> None:
        self.entry.values[0] = value

    @property
    def model_hash(self) -> int:
        return joaat(self.name)

    @property
    def position(self) -> MloVector3:
        return _vector3(self.entry, 1)

    @position.setter
    def position(self, value: MloVector3) -> None:
        _set_vector3(self.entry, 1, value)

    @property
    def orientation(self) -> MloQuaternion:
        return _quaternion(self.entry, 4)

    @orientation.setter
    def orientation(self, value: MloQuaternion) -> None:
        _set_quaternion(self.entry, 4, value)

    @property
    def lod_level(self) -> int:
        return int(self.entry.values[8], 0)

    @lod_level.setter
    def lod_level(self, value: int) -> None:
        self.entry.values[8] = str(int(value))

    @property
    def flags(self) -> WplInstanceFlags:
        from ..wpl import WplInstanceFlags

        return WplInstanceFlags(int(self.entry.values[9], 0))

    @flags.setter
    def flags(self, value: WplInstanceFlags | int) -> None:
        self.entry.values[9] = str(int(value))

    def to_data(self) -> dict[str, object]:
        return {
            "index": self.index,
            "name": self.name,
            "model_hash": self.model_hash,
            "position": list(self.position),
            "orientation": list(self.orientation),
            "lod_level": self.lod_level,
            "flags": int(self.flags),
        }


@dataclass(slots=True)
class MloRoom:
    """An MLO room with bounds and references to local entities."""

    entry: IdeEntry = field(repr=False)
    entity_rows: tuple[IdeEntry, ...] = field(default=(), repr=False)
    index: int = 0

    def __post_init__(self) -> None:
        _require(self.entry, 12, "MLO room")

    @property
    def name(self) -> str:
        return self.entry.values[0]

    @name.setter
    def name(self, value: str) -> None:
        self.entry.values[0] = value

    @property
    def declared_entity_count(self) -> int:
        return int(self.entry.values[1], 0)

    @declared_entity_count.setter
    def declared_entity_count(self, value: int) -> None:
        self.entry.values[1] = str(int(value))

    @property
    def declared_portal_count(self) -> int:
        return int(self.entry.values[2], 0)

    @declared_portal_count.setter
    def declared_portal_count(self, value: int) -> None:
        self.entry.values[2] = str(int(value))

    @property
    def bounds_max(self) -> MloVector3:
        return _vector3(self.entry, 3)

    @bounds_max.setter
    def bounds_max(self, value: MloVector3) -> None:
        _set_vector3(self.entry, 3, value)

    @property
    def bounds_min(self) -> MloVector3:
        return _vector3(self.entry, 6)

    @bounds_min.setter
    def bounds_min(self, value: MloVector3) -> None:
        _set_vector3(self.entry, 6, value)

    @property
    def blend(self) -> float:
        return float(self.entry.values[9])

    @blend.setter
    def blend(self, value: float) -> None:
        self.entry.values[9] = str(float(value))

    @property
    def time_cycle_hash(self) -> int:
        return int(self.entry.values[10], 0)

    @time_cycle_hash.setter
    def time_cycle_hash(self, value: int) -> None:
        self.entry.values[10] = str(int(value))

    @property
    def flags(self) -> int:
        return int(self.entry.values[11], 0)

    @flags.setter
    def flags(self, value: int) -> None:
        self.entry.values[11] = str(int(value))

    @property
    def entity_ids(self) -> tuple[int, ...]:
        result: list[int] = []
        for row in self.entity_rows:
            for raw in row.values:
                raw = raw.strip()
                if not raw:
                    continue
                value = int(raw, 0)
                if value < 0:
                    break
                result.append(value)
        return tuple(result)

    def contains_local_point(self, point: MloVector3) -> bool:
        minimum = self.bounds_min
        maximum = self.bounds_max
        return all(
            low <= value <= high
            for value, low, high in zip(point, minimum, maximum, strict=True)
        )

    def to_data(self) -> dict[str, object]:
        return {
            "index": self.index,
            "name": self.name,
            "entity_count": self.declared_entity_count,
            "portal_count": self.declared_portal_count,
            "bounds_min": list(self.bounds_min),
            "bounds_max": list(self.bounds_max),
            "blend": self.blend,
            "time_cycle_hash": self.time_cycle_hash,
            "flags": self.flags,
            "entity_ids": list(self.entity_ids),
        }


@dataclass(slots=True)
class MloPortal:
    """A four-corner opening connecting two rooms in local MLO space."""

    entry: IdeEntry = field(repr=False)
    index: int = 0

    def __post_init__(self) -> None:
        _require(self.entry, 21, "MLO portal")

    @property
    def room_from(self) -> int:
        return int(self.entry.values[0], 0)

    @room_from.setter
    def room_from(self, value: int) -> None:
        self.entry.values[0] = str(int(value))

    @property
    def room_to(self) -> int:
        return int(self.entry.values[1], 0)

    @room_to.setter
    def room_to(self, value: int) -> None:
        self.entry.values[1] = str(int(value))

    @property
    def corners(self) -> tuple[MloVector3, MloVector3, MloVector3, MloVector3]:
        return (
            _vector3(self.entry, 2),
            _vector3(self.entry, 5),
            _vector3(self.entry, 8),
            _vector3(self.entry, 11),
        )

    @corners.setter
    def corners(
        self,
        value: tuple[MloVector3, MloVector3, MloVector3, MloVector3],
    ) -> None:
        if len(value) != 4:
            raise ValueError("MLO portals require exactly four corners")
        for offset, corner in zip((2, 5, 8, 11), value, strict=True):
            _set_vector3(self.entry, offset, corner)

    @property
    def entity_ids(self) -> tuple[int, ...]:
        return tuple(
            value
            for value in (int(raw, 0) for raw in self.entry.values[14:18])
            if value >= 0
        )

    @property
    def flags(self) -> int:
        return int(self.entry.values[18], 0)

    @flags.setter
    def flags(self, value: int) -> None:
        self.entry.values[18] = str(int(value))

    @property
    def time_flags(self) -> int:
        return int(self.entry.values[19], 0)

    @time_flags.setter
    def time_flags(self, value: int) -> None:
        self.entry.values[19] = str(int(value))

    @property
    def active_hours(self) -> tuple[int, ...]:
        return tuple(hour for hour in range(24) if self.time_flags & (1 << hour))

    def is_active_at(self, hour: int) -> bool:
        if not 0 <= hour <= 23:
            raise ValueError("MLO portal hour must be between 0 and 23")
        return bool(self.time_flags & (1 << hour))

    @property
    def parameter(self) -> float:
        """Preserved final portal parameter whose runtime role is unresolved."""

        return float(self.entry.values[20])

    @parameter.setter
    def parameter(self, value: float) -> None:
        self.entry.values[20] = str(float(value))

    def to_data(self) -> dict[str, object]:
        return {
            "index": self.index,
            "room_from": self.room_from,
            "room_to": self.room_to,
            "corners": [list(corner) for corner in self.corners],
            "entity_ids": list(self.entity_ids),
            "flags": self.flags,
            "time_flags": self.time_flags,
            "active_hours": list(self.active_hours),
            "parameter": self.parameter,
        }


class MloIssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class MloValidationIssue:
    code: str
    message: str
    severity: MloIssueSeverity = MloIssueSeverity.ERROR
    room_index: int | None = None
    portal_index: int | None = None
    entity_index: int | None = None

    def to_data(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "room_index": self.room_index,
            "portal_index": self.portal_index,
            "entity_index": self.entity_index,
        }


@dataclass(slots=True)
class MloArchetype:
    """A complete MLO definition parsed from an IDE ``mlo`` section."""

    entry: IdeEntry = field(repr=False)
    entities: tuple[MloEntity, ...] = ()
    rooms: tuple[MloRoom, ...] = ()
    portals: tuple[MloPortal, ...] = ()
    source_name: str = ""

    def __post_init__(self) -> None:
        _require(self.entry, 8, "MLO archetype")

    @property
    def name(self) -> str:
        return self.entry.values[0]

    @name.setter
    def name(self, value: str) -> None:
        self.entry.values[0] = value

    @property
    def name_hash(self) -> int:
        return joaat(self.name)

    @property
    def flags(self) -> IdeArchetypeFlags:
        return IdeArchetypeFlags(int(self.entry.values[1], 0))

    @flags.setter
    def flags(self, value: IdeArchetypeFlags | int) -> None:
        self.entry.values[1] = str(int(value))

    @property
    def declared_room_count(self) -> int:
        return int(self.entry.values[2], 0)

    @declared_room_count.setter
    def declared_room_count(self, value: int) -> None:
        self.entry.values[2] = str(int(value))

    @property
    def declared_portal_count(self) -> int:
        return int(self.entry.values[3], 0)

    @declared_portal_count.setter
    def declared_portal_count(self, value: int) -> None:
        self.entry.values[3] = str(int(value))

    @property
    def hd_entity_count(self) -> int:
        return int(self.entry.values[4], 0)

    @hd_entity_count.setter
    def hd_entity_count(self, value: int) -> None:
        self.entry.values[4] = str(int(value))

    @property
    def lod_distances(self) -> tuple[float, float, float]:
        return (
            float(self.entry.values[5]),
            float(self.entry.values[6]),
            float(self.entry.values[7]),
        )

    @lod_distances.setter
    def lod_distances(self, value: tuple[float, float, float]) -> None:
        self.entry.values[5:8] = [str(float(item)) for item in value]

    @property
    def draw_distance(self) -> float:
        return self.lod_distances[0] if self.lod_distances[0] > 0.0 else 100.0

    @property
    def lod_parent_indices(self) -> tuple[int | None, ...]:
        lod_1 = next(
            (entity.index for entity in reversed(self.entities) if entity.lod_level == 1),
            None,
        )
        lod_2 = next(
            (entity.index for entity in reversed(self.entities) if entity.lod_level == 2),
            None,
        )
        return tuple(
            lod_1
            if entity.lod_level == 0
            else lod_2 if entity.lod_level == 1 else None
            for entity in self.entities
        )

    def find_room(self, name_or_index: str | int) -> MloRoom | None:
        if isinstance(name_or_index, int):
            return (
                self.rooms[name_or_index]
                if 0 <= name_or_index < len(self.rooms)
                else None
            )
        key = name_or_index.casefold()
        return next(
            (room for room in self.rooms if room.name.casefold() == key),
            None,
        )

    def portal_indices_for_room(self, room_index: int) -> tuple[int, ...]:
        if not 0 <= room_index < len(self.rooms):
            raise IndexError("MLO room index is out of range")
        return tuple(
            portal.index
            for portal in self.portals
            if portal.room_from == room_index or portal.room_to == room_index
        )

    def validate(self) -> tuple[MloValidationIssue, ...]:
        issues: list[MloValidationIssue] = []
        if self.declared_room_count != len(self.rooms):
            issues.append(MloValidationIssue(
                "room_count",
                f"MLO declares {self.declared_room_count} rooms but contains {len(self.rooms)}",
            ))
        if self.declared_portal_count != len(self.portals):
            issues.append(MloValidationIssue(
                "portal_count",
                f"MLO declares {self.declared_portal_count} portals but contains {len(self.portals)}",
            ))
        if not 0 <= self.hd_entity_count <= len(self.entities):
            issues.append(MloValidationIssue(
                "hd_entity_count",
                f"MLO HD entity count {self.hd_entity_count} exceeds "
                f"the {len(self.entities)} local entities",
            ))
        for room in self.rooms:
            if room.declared_entity_count != len(room.entity_ids):
                issues.append(MloValidationIssue(
                    "room_entity_count",
                    f"room declares {room.declared_entity_count} entities but "
                    f"references {len(room.entity_ids)}",
                    room_index=room.index,
                ))
            connected = self.portal_indices_for_room(room.index)
            if room.declared_portal_count != len(connected):
                issues.append(MloValidationIssue(
                    "room_portal_count",
                    f"room declares {room.declared_portal_count} portals but "
                    f"is connected to {len(connected)}",
                    room_index=room.index,
                ))
            for entity_id in room.entity_ids:
                if not 0 <= entity_id < len(self.entities):
                    issues.append(MloValidationIssue(
                        "room_entity_reference",
                        f"room references out-of-range entity {entity_id}",
                        room_index=room.index,
                        entity_index=entity_id,
                    ))
        for portal in self.portals:
            for room_index in (portal.room_from, portal.room_to):
                if not 0 <= room_index < len(self.rooms):
                    issues.append(MloValidationIssue(
                        "portal_room_reference",
                        f"portal references out-of-range room {room_index}",
                        room_index=room_index,
                        portal_index=portal.index,
                    ))
            for entity_id in portal.entity_ids:
                if not 0 <= entity_id < len(self.entities):
                    issues.append(MloValidationIssue(
                        "portal_entity_reference",
                        f"portal references out-of-range entity {entity_id}",
                        portal_index=portal.index,
                        entity_index=entity_id,
                    ))
        return tuple(issues)

    def to_data(self) -> dict[str, object]:
        return {
            "name": self.name,
            "name_hash": self.name_hash,
            "flags": int(self.flags),
            "hd_entity_count": self.hd_entity_count,
            "lod_distances": list(self.lod_distances),
            "lod_parent_indices": list(self.lod_parent_indices),
            "entities": [entity.to_data() for entity in self.entities],
            "rooms": [room.to_data() for room in self.rooms],
            "portals": [portal.to_data() for portal in self.portals],
        }


def _token(entry: IdeEntry) -> str | None:
    values = [value.strip() for value in entry.values if value.strip()]
    if len(values) != 1:
        return None
    value = values[0].casefold()
    return (
        value
        if value in {"mloroomstart", "roomend", "mloportalstart", "mloend"}
        else None
    )


def parse_mlo_archetypes(document: IdeDocument) -> tuple[MloArchetype, ...]:
    """Parse all nested MLO definitions without changing the lossless IDE lines."""

    entries = list(document.iter_entries("mlo"))
    result: list[MloArchetype] = []
    index = 0

    def expect(value: str) -> None:
        nonlocal index
        if index >= len(entries) or _token(entries[index]) != value:
            location = (
                "at end of section"
                if index >= len(entries)
                else f"at IDE line {entries[index].line_number}"
            )
            raise ValueError(f"expected {value!r} in MLO section {location}")
        index += 1

    while index < len(entries):
        header = entries[index]
        if _token(header) is not None:
            raise ValueError(
                f"expected MLO header at IDE line {header.line_number}, "
                f"found {_token(header)!r}"
            )
        _require(header, 8, "MLO archetype")
        index += 1

        entity_entries: list[IdeEntry] = []
        while index < len(entries) and _token(entries[index]) != "mloroomstart":
            if _token(entries[index]) is not None:
                raise ValueError(
                    f"unexpected MLO token {_token(entries[index])!r} "
                    f"at IDE line {entries[index].line_number}"
                )
            entity_entries.append(entries[index])
            index += 1
        expect("mloroomstart")

        rooms: list[MloRoom] = []
        while index < len(entries) and _token(entries[index]) != "mloportalstart":
            room_header = entries[index]
            if _token(room_header) is not None:
                raise ValueError(
                    f"expected MLO room at IDE line {room_header.line_number}"
                )
            _require(room_header, 12, "MLO room")
            index += 1
            entity_rows: list[IdeEntry] = []
            while index < len(entries) and _token(entries[index]) != "roomend":
                if _token(entries[index]) is not None:
                    raise ValueError(
                        f"unexpected room token {_token(entries[index])!r} "
                        f"at IDE line {entries[index].line_number}"
                    )
                entity_rows.append(entries[index])
                index += 1
            expect("roomend")
            rooms.append(MloRoom(room_header, tuple(entity_rows), len(rooms)))
        expect("mloportalstart")

        portal_entries: list[IdeEntry] = []
        while index < len(entries) and _token(entries[index]) != "mloend":
            if _token(entries[index]) is not None:
                raise ValueError(
                    f"unexpected portal token {_token(entries[index])!r} "
                    f"at IDE line {entries[index].line_number}"
                )
            portal_entries.append(entries[index])
            index += 1
        expect("mloend")

        result.append(MloArchetype(
            header,
            tuple(
                MloEntity(entry, entity_index)
                for entity_index, entry in enumerate(entity_entries)
            ),
            tuple(rooms),
            tuple(
                MloPortal(entry, portal_index)
                for portal_index, entry in enumerate(portal_entries)
            ),
            document.name,
        ))
    return tuple(result)


def _normalize_quaternion(value: MloQuaternion) -> MloQuaternion:
    length = math.sqrt(sum(component * component for component in value))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(component / length for component in value)  # type: ignore[return-value]


def _multiply_quaternions(
    left: MloQuaternion,
    right: MloQuaternion,
) -> MloQuaternion:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return _normalize_quaternion((
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    ))


def _rotate_vector(value: MloVector3, rotation: MloQuaternion) -> MloVector3:
    x, y, z, w = _normalize_quaternion(rotation)
    vx, vy, vz = value
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + (w * tx) + (y * tz - z * ty),
        vy + (w * ty) + (z * tx - x * tz),
        vz + (w * tz) + (x * ty - y * tx),
    )


def _transform_point(
    value: MloVector3,
    position: MloVector3,
    rotation: MloQuaternion,
) -> MloVector3:
    rotated = _rotate_vector(value, rotation)
    return tuple(
        component + origin
        for component, origin in zip(rotated, position, strict=True)
    )  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class MloPlacedEntity:
    index: int
    name: str
    model_hash: int
    position: MloVector3
    orientation: MloQuaternion
    lod_level: int
    lod_parent_index: int | None
    flags: WplInstanceFlags

    def to_data(self) -> dict[str, object]:
        return {
            "index": self.index,
            "name": self.name,
            "model_hash": self.model_hash,
            "position": list(self.position),
            "orientation": list(self.orientation),
            "lod_level": self.lod_level,
            "lod_parent_index": self.lod_parent_index,
            "flags": int(self.flags),
        }


@dataclass(frozen=True, slots=True)
class MloPlacedRoom:
    index: int
    name: str
    corners: tuple[MloVector3, ...]
    entity_ids: tuple[int, ...]
    portal_ids: tuple[int, ...]
    blend: float
    time_cycle_hash: int
    flags: int

    def to_data(self) -> dict[str, object]:
        return {
            "index": self.index,
            "name": self.name,
            "corners": [list(corner) for corner in self.corners],
            "entity_ids": list(self.entity_ids),
            "portal_ids": list(self.portal_ids),
            "blend": self.blend,
            "time_cycle_hash": self.time_cycle_hash,
            "flags": self.flags,
        }


@dataclass(frozen=True, slots=True)
class MloPlacedPortal:
    index: int
    room_from: int
    room_to: int
    corners: tuple[MloVector3, MloVector3, MloVector3, MloVector3]
    entity_ids: tuple[int, ...]
    flags: int
    time_flags: int
    parameter: float

    def to_data(self) -> dict[str, object]:
        return {
            "index": self.index,
            "room_from": self.room_from,
            "room_to": self.room_to,
            "corners": [list(corner) for corner in self.corners],
            "entity_ids": list(self.entity_ids),
            "flags": self.flags,
            "time_flags": self.time_flags,
            "parameter": self.parameter,
        }


@dataclass(slots=True)
class MloInstance:
    """A WPL placement resolved against its IDE MLO archetype."""

    placement_index: int
    placement: WplInstance = field(repr=False)
    archetype: MloArchetype

    @property
    def position(self) -> MloVector3:
        return (
            self.placement.position_x,
            self.placement.position_y,
            self.placement.position_z,
        )

    @property
    def orientation(self) -> MloQuaternion:
        return _normalize_quaternion((
            self.placement.rotation_x,
            self.placement.rotation_y,
            self.placement.rotation_z,
            self.placement.rotation_w,
        ))

    @property
    def entities(self) -> tuple[MloPlacedEntity, ...]:
        parents = self.archetype.lod_parent_indices
        return tuple(
            MloPlacedEntity(
                entity.index,
                entity.name,
                entity.model_hash,
                _transform_point(entity.position, self.position, self.orientation),
                _multiply_quaternions(self.orientation, entity.orientation),
                entity.lod_level,
                parents[entity.index],
                entity.flags,
            )
            for entity in self.archetype.entities
        )

    @property
    def rooms(self) -> tuple[MloPlacedRoom, ...]:
        result: list[MloPlacedRoom] = []
        for room in self.archetype.rooms:
            minimum = room.bounds_min
            maximum = room.bounds_max
            corners = tuple(
                _transform_point((x, y, z), self.position, self.orientation)
                for x in (minimum[0], maximum[0])
                for y in (minimum[1], maximum[1])
                for z in (minimum[2], maximum[2])
            )
            result.append(MloPlacedRoom(
                room.index,
                room.name,
                corners,
                room.entity_ids,
                self.archetype.portal_indices_for_room(room.index),
                room.blend,
                room.time_cycle_hash,
                room.flags,
            ))
        return tuple(result)

    @property
    def portals(self) -> tuple[MloPlacedPortal, ...]:
        return tuple(
            MloPlacedPortal(
                portal.index,
                portal.room_from,
                portal.room_to,
                tuple(
                    _transform_point(corner, self.position, self.orientation)
                    for corner in portal.corners
                ),  # type: ignore[arg-type]
                portal.entity_ids,
                portal.flags,
                portal.time_flags,
                portal.parameter,
            )
            for portal in self.archetype.portals
        )

    def to_data(self) -> dict[str, object]:
        return {
            "placement_index": self.placement_index,
            "name": self.archetype.name,
            "name_hash": self.archetype.name_hash,
            "position": list(self.position),
            "orientation": list(self.orientation),
            "entities": [entity.to_data() for entity in self.entities],
            "rooms": [room.to_data() for room in self.rooms],
            "portals": [portal.to_data() for portal in self.portals],
        }


@dataclass(slots=True)
class MloRegistry:
    """Hash registry used to resolve WPL placements into complete MLO instances."""

    archetypes: tuple[MloArchetype, ...] = ()
    _by_hash: dict[int, MloArchetype] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _all_by_hash: dict[int, tuple[MloArchetype, ...]] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        grouped: dict[int, list[MloArchetype]] = {}
        for archetype in self.archetypes:
            grouped.setdefault(archetype.name_hash, []).append(archetype)
        self._all_by_hash = {
            name_hash: tuple(values)
            for name_hash, values in grouped.items()
        }
        # Later IDE documents intentionally override earlier definitions,
        # matching normal GTA data load order while keeping all collisions visible.
        self._by_hash = {
            name_hash: values[-1]
            for name_hash, values in self._all_by_hash.items()
        }

    @classmethod
    def from_ide_documents(
        cls,
        documents: Iterable[IdeDocument],
    ) -> MloRegistry:
        return cls(tuple(chain.from_iterable(
            parse_mlo_archetypes(document)
            for document in documents
        )))

    @property
    def duplicate_hashes(self) -> tuple[int, ...]:
        return tuple(
            sorted(
                name_hash
                for name_hash, values in self._all_by_hash.items()
                if len(values) > 1
            )
        )

    def find(self, name_or_hash: str | int) -> MloArchetype | None:
        name_hash = (
            name_or_hash
            if isinstance(name_or_hash, int)
            else joaat(name_or_hash)
        )
        return self._by_hash.get(name_hash)

    def find_all(self, name_or_hash: str | int) -> tuple[MloArchetype, ...]:
        name_hash = (
            name_or_hash
            if isinstance(name_or_hash, int)
            else joaat(name_or_hash)
        )
        return self._all_by_hash.get(name_hash, ())

    def resolve(self, document: WplDocument) -> tuple[MloInstance, ...]:
        return tuple(
            MloInstance(index, placement, archetype)
            for index, placement in enumerate(document.instances)
            if (archetype := self.find(placement.model_hash)) is not None
        )


__all__ = [
    "MloArchetype",
    "MloEntity",
    "MloInstance",
    "MloIssueSeverity",
    "MloPlacedEntity",
    "MloPlacedPortal",
    "MloPlacedRoom",
    "MloPortal",
    "MloQuaternion",
    "MloRegistry",
    "MloRoom",
    "MloValidationIssue",
    "MloVector3",
    "parse_mlo_archetypes",
]
