from __future__ import annotations

import struct
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from enum import IntEnum, IntFlag
from pathlib import Path
from typing import BinaryIO, Literal

from ._utils import atomic_write
from .fragment import FragmentAsset, FragmentPiece
from .model import ModelAsset, ModelBoundingSphere, ModelCoordinateSystem
from .rsc import RSC5_VIRTUAL_BASE, Rsc5Resource
from .wbn import WbnBound, _WbnParser
from .wdr import (
    WdrDocument,
    WdrDrawable,
    WdrDrawableModel,
    WdrGeometry,
    WdrMatrix4,
    WdrShader,
    WdrShaderGroup,
    WdrVector4,
    _WdrReader,
)
from .wtd import Rsc5Texture, Rsc5TextureDictionary

WFT_RESOURCE_VERSION = 0x70
WFT_FRAGMENT_SIZE = 0x204
WFT_DRAWABLE_SIZE = 0xE4
WFT_GROUP_SIZE = 0x150
WFT_CHILD_SIZE = 0x310
WFT_PHYSICS_ARCHETYPE_SIZE = 0xC0


class WftFragmentFlags(IntFlag):
    NONE = 0
    NEEDS_CACHE_ENTRY_TO_ACTIVATE = 1 << 0
    HAS_ARTICULATED_PARTS = 1 << 1
    UNUSED = 1 << 2
    CLONE_BOUND_PARTS_IN_CACHE = 1 << 3
    ALLOCATE_TYPE_AND_INCLUDE_FLAGS = 1 << 4
    FORCE_ARTICULATED_DAMPING = 1 << 5
    FORCE_LOAD_COMMON_DRAWABLE = 1 << 6
    FORCE_ALLOCATE_LINK_ATTACHMENTS = 1 << 7


class WftGroupFlags(IntFlag):
    NONE = 0
    DISAPPEARS_WHEN_DEAD = 1 << 0
    MADE_OF_GLASS = 1 << 1
    DAMAGE_WHEN_BROKEN = 1 << 2
    DOES_NOT_AFFECT_VEHICLES = 1 << 3
    DOES_NOT_PUSH_VEHICLES_DOWN = 1 << 4
    HAS_CLOTH = 1 << 5


class WftChildFlags(IntFlag):
    NONE = 0
    DISABLED = 1 << 0
    CAN_BREAK = 1 << 1
    USES_DAMAGED_DRAWABLE = 1 << 2
    VEHICLE_PART = 1 << 3
    GLASS_PART = 1 << 4
    CLOTH_PART = 1 << 5


class WftDampingKind(IntEnum):
    LINEAR_CONSTANT = 0
    LINEAR_VELOCITY = 1
    LINEAR_VELOCITY_SQUARED = 2
    ANGULAR_CONSTANT = 3
    ANGULAR_VELOCITY = 4
    ANGULAR_VELOCITY_SQUARED = 5


WftFlagConfidence = Literal["verified", "inferred", "unresolved"]
WftFlag = WftFragmentFlags | WftGroupFlags | WftChildFlags


@dataclass(frozen=True, slots=True)
class WftFlagInfo:
    flag: WftFlag
    effect: str
    confidence: WftFlagConfidence


WFT_FRAGMENT_FLAG_INFO = (
    WftFlagInfo(
        WftFragmentFlags.NEEDS_CACHE_ENTRY_TO_ACTIVATE,
        "Requires cached runtime fragment state before activation.",
        "inferred",
    ),
    WftFlagInfo(
        WftFragmentFlags.HAS_ARTICULATED_PARTS,
        "Declares articulated fragment parts.",
        "inferred",
    ),
    WftFlagInfo(
        WftFragmentFlags.UNUSED,
        "Preserves a flag bit whose GTA IV runtime effect is unresolved.",
        "unresolved",
    ),
    WftFlagInfo(
        WftFragmentFlags.CLONE_BOUND_PARTS_IN_CACHE,
        "Requests cloned bound parts in the runtime cache.",
        "inferred",
    ),
    WftFlagInfo(
        WftFragmentFlags.ALLOCATE_TYPE_AND_INCLUDE_FLAGS,
        "Requests allocation of fragment type and include-flag state.",
        "inferred",
    ),
    WftFlagInfo(
        WftFragmentFlags.FORCE_ARTICULATED_DAMPING,
        "Forces articulated damping behavior.",
        "inferred",
    ),
    WftFlagInfo(
        WftFragmentFlags.FORCE_LOAD_COMMON_DRAWABLE,
        "Forces the common drawable to load.",
        "inferred",
    ),
    WftFlagInfo(
        WftFragmentFlags.FORCE_ALLOCATE_LINK_ATTACHMENTS,
        "Forces allocation of link attachments.",
        "inferred",
    ),
)

WFT_GROUP_FLAG_INFO = (
    WftFlagInfo(
        WftGroupFlags.DISAPPEARS_WHEN_DEAD,
        "Makes the group disappear after its health reaches zero.",
        "inferred",
    ),
    WftFlagInfo(
        WftGroupFlags.MADE_OF_GLASS,
        "Marks the group as glass that shatters when broken.",
        "inferred",
    ),
    WftFlagInfo(
        WftGroupFlags.DAMAGE_WHEN_BROKEN,
        "Damages the group after it separates from its parent.",
        "inferred",
    ),
    WftFlagInfo(
        WftGroupFlags.DOES_NOT_AFFECT_VEHICLES,
        "Treats vehicles as infinitely massive for group collisions.",
        "inferred",
    ),
    WftFlagInfo(
        WftGroupFlags.DOES_NOT_PUSH_VEHICLES_DOWN,
        "Prevents group collisions from pushing vehicles downward.",
        "inferred",
    ),
    WftFlagInfo(
        WftGroupFlags.HAS_CLOTH,
        "Associates cloth behavior with the group.",
        "inferred",
    ),
)

WFT_CHILD_FLAG_INFO = (
    WftFlagInfo(
        WftChildFlags.DISABLED,
        "Disables the fragment child.",
        "inferred",
    ),
    WftFlagInfo(
        WftChildFlags.CAN_BREAK,
        "Allows the child to break from its group.",
        "inferred",
    ),
    WftFlagInfo(
        WftChildFlags.USES_DAMAGED_DRAWABLE,
        "Selects the child's damaged drawable state.",
        "inferred",
    ),
    WftFlagInfo(
        WftChildFlags.VEHICLE_PART,
        "Marks the child as a vehicle part.",
        "inferred",
    ),
    WftFlagInfo(
        WftChildFlags.GLASS_PART,
        "Marks the child as a glass part.",
        "inferred",
    ),
    WftFlagInfo(
        WftChildFlags.CLOTH_PART,
        "Marks the child as a cloth part.",
        "inferred",
    ),
)


def _flag_mask(details: tuple[WftFlagInfo, ...]) -> int:
    return sum(int(detail.flag) for detail in details)


def _explain_flags(
    flags: IntFlag | int,
    details: tuple[WftFlagInfo, ...],
    flag_type: type[WftFlag],
) -> tuple[WftFlagInfo, ...]:
    value = int(flags)
    active = [detail for detail in details if value & int(detail.flag)]
    unresolved = value & ~_flag_mask(details)
    if unresolved:
        active.append(WftFlagInfo(
            flag_type(unresolved),
            "Preserved flag bits whose GTA IV runtime effect is unresolved.",
            "unresolved",
        ))
    return tuple(active)


def explain_fragment_flags(
    flags: WftFragmentFlags | int,
) -> tuple[WftFlagInfo, ...]:
    return _explain_flags(flags, WFT_FRAGMENT_FLAG_INFO, WftFragmentFlags)


def explain_group_flags(flags: WftGroupFlags | int) -> tuple[WftFlagInfo, ...]:
    return _explain_flags(flags, WFT_GROUP_FLAG_INFO, WftGroupFlags)


def explain_child_flags(flags: WftChildFlags | int) -> tuple[WftFlagInfo, ...]:
    return _explain_flags(flags, WFT_CHILD_FLAG_INFO, WftChildFlags)


@dataclass(frozen=True, slots=True)
class WftMatrix3x4:
    values: tuple[
        float, float, float, float,
        float, float, float, float,
        float, float, float, float,
    ]

    @property
    def rows(self) -> tuple[tuple[float, float, float, float], ...]:
        return tuple(self.values[index : index + 4] for index in range(0, 12, 4))


@dataclass(frozen=True, slots=True)
class WftSelfCollision:
    first_child_index: int
    second_child_index: int


@dataclass(frozen=True, slots=True)
class WftEventReferences:
    continuous_event_set: int = 0
    collision_event_set: int = 0
    break_event_set: int = 0
    break_from_root_event_set: int = 0
    collision_event_player: int = 0
    break_event_player: int = 0
    break_from_root_event_player: int = 0

    @property
    def has_any(self) -> bool:
        return any(self.as_tuple())

    def as_tuple(self) -> tuple[int, ...]:
        return (
            self.continuous_event_set,
            self.collision_event_set,
            self.break_event_set,
            self.break_from_root_event_set,
            self.collision_event_player,
            self.break_event_player,
            self.break_from_root_event_player,
        )


@dataclass(slots=True)
class WftFragmentDrawable:
    name: str
    drawable: WdrDrawable
    fragment_matrix: WdrMatrix4
    bound: WbnBound | None
    fragment_matrix_indices: tuple[int, ...]
    fragment_matrices: tuple[WdrMatrix4, ...]
    pointer: int = field(repr=False, compare=False)
    inherited_shader_group: WdrShaderGroup | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @property
    def models(self) -> tuple[WdrDrawableModel, ...]:
        return self.drawable.models

    @property
    def geometries(self) -> tuple[WdrGeometry, ...]:
        return self.drawable.geometries

    @property
    def shader_group(self) -> WdrShaderGroup | None:
        return self.drawable.shader_group or self.inherited_shader_group

    @property
    def serialized_shader_group(self) -> WdrShaderGroup | None:
        return self.drawable.shader_group

    @property
    def uses_inherited_shader_group(self) -> bool:
        return (
            self.drawable.shader_group is None
            and self.inherited_shader_group is not None
        )


@dataclass(frozen=True, slots=True)
class WftPhysicsArchetype:
    name: str
    archetype_type: int
    type_flags: int
    include_flags: int
    property_flags: int
    reference_count: int
    mass: float
    inverse_mass: float
    gravity_factor: float
    maximum_speed: float
    maximum_angular_speed: float
    inertia_tensor: WdrVector4
    inverse_inertia_tensor: WdrVector4
    damping: tuple[WdrVector4, ...]
    bound: WbnBound | None
    pointer: int = field(repr=False, compare=False)

    def damping_for(self, kind: WftDampingKind | int) -> WdrVector4:
        return self.damping[int(kind)]


@dataclass(slots=True)
class WftGroup:
    name: str
    strength: float
    force_transmission_scale_up: float
    force_transmission_scale_down: float
    joint_stiffness: float
    minimum_soft_angle_1: float
    maximum_soft_angle_1: float
    maximum_soft_angle_2: float
    maximum_soft_angle_3: float
    rotation_speed: float
    rotation_strength: float
    restoring_strength: float
    restoring_maximum_torque: float
    latch_strength: float
    mass: float
    child_group_index: int
    parent_group_index: int
    child_index: int
    child_count: int
    child_group_count: int
    flags: WftGroupFlags
    minimum_damage_force: float
    damage_health: float
    pointer: int = field(repr=False, compare=False)
    children: tuple[WftChild, ...] = field(default=(), repr=False, compare=False)

    @property
    def is_root(self) -> bool:
        return self.parent_group_index == 0xFF

    @property
    def is_damageable(self) -> bool:
        return self.damage_health > 0.0

    @property
    def is_glass(self) -> bool:
        return bool(self.flags & WftGroupFlags.MADE_OF_GLASS)

    @property
    def flag_info(self) -> tuple[WftFlagInfo, ...]:
        return explain_group_flags(self.flags)

    @property
    def unresolved_flags(self) -> int:
        return int(self.flags) & ~_flag_mask(WFT_GROUP_FLAG_INFO)


@dataclass(slots=True, init=False)
class WftChild:
    undamaged_mass: float
    damaged_mass: float
    group_index: int
    flags: WftChildFlags
    bone_index: int
    bone_attachment: WdrMatrix4
    link_attachment: WdrMatrix4
    events: WftEventReferences
    pointer: int = field(repr=False, compare=False)
    group: WftGroup | None = field(default=None, repr=False, compare=False)
    _undamaged_drawable_pointer: int = field(default=0, repr=False)
    _damaged_drawable_pointer: int = field(default=0, repr=False)
    _drawable_loader: Callable[[int], WftFragmentDrawable | None] | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _undamaged_drawable: WftFragmentDrawable | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _damaged_drawable: WftFragmentDrawable | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __init__(
        self,
        undamaged_mass: float,
        damaged_mass: float,
        group_index: int,
        flags: WftChildFlags,
        bone_index: int,
        bone_attachment: WdrMatrix4,
        link_attachment: WdrMatrix4,
        undamaged_drawable: WftFragmentDrawable | None,
        damaged_drawable: WftFragmentDrawable | None,
        events: WftEventReferences,
        pointer: int,
        group: WftGroup | None = None,
    ) -> None:
        self.undamaged_mass = undamaged_mass
        self.damaged_mass = damaged_mass
        self.group_index = group_index
        self.flags = flags
        self.bone_index = bone_index
        self.bone_attachment = bone_attachment
        self.link_attachment = link_attachment
        self.events = events
        self.pointer = pointer
        self.group = group
        self._undamaged_drawable_pointer = (
            0 if undamaged_drawable is None else undamaged_drawable.pointer
        )
        self._damaged_drawable_pointer = (
            0 if damaged_drawable is None else damaged_drawable.pointer
        )
        self._drawable_loader = None
        self._undamaged_drawable = undamaged_drawable
        self._damaged_drawable = damaged_drawable

    @classmethod
    def _from_pointers(
        cls,
        undamaged_mass: float,
        damaged_mass: float,
        group_index: int,
        flags: WftChildFlags,
        bone_index: int,
        bone_attachment: WdrMatrix4,
        link_attachment: WdrMatrix4,
        undamaged_drawable_pointer: int,
        damaged_drawable_pointer: int,
        events: WftEventReferences,
        pointer: int,
        drawable_loader: Callable[[int], WftFragmentDrawable | None],
    ) -> WftChild:
        child = cls(
            undamaged_mass,
            damaged_mass,
            group_index,
            flags,
            bone_index,
            bone_attachment,
            link_attachment,
            None,
            None,
            events,
            pointer,
        )
        child._undamaged_drawable_pointer = undamaged_drawable_pointer
        child._damaged_drawable_pointer = damaged_drawable_pointer
        child._drawable_loader = drawable_loader
        return child

    @property
    def undamaged_drawable_pointer(self) -> int:
        return self._undamaged_drawable_pointer

    @property
    def damaged_drawable_pointer(self) -> int:
        return self._damaged_drawable_pointer

    @property
    def undamaged_drawable(self) -> WftFragmentDrawable | None:
        if (
            self._undamaged_drawable is None
            and self._undamaged_drawable_pointer
            and self._drawable_loader is not None
        ):
            self._undamaged_drawable = self._drawable_loader(
                self._undamaged_drawable_pointer
            )
        return self._undamaged_drawable

    @property
    def damaged_drawable(self) -> WftFragmentDrawable | None:
        if (
            self._damaged_drawable is None
            and self._damaged_drawable_pointer
            and self._drawable_loader is not None
        ):
            self._damaged_drawable = self._drawable_loader(
                self._damaged_drawable_pointer
            )
        return self._damaged_drawable

    @property
    def has_damaged_drawable(self) -> bool:
        return self._damaged_drawable_pointer != 0

    @property
    def flag_info(self) -> tuple[WftFlagInfo, ...]:
        return explain_child_flags(self.flags)

    @property
    def unresolved_flags(self) -> int:
        return int(self.flags) & ~_flag_mask(WFT_CHILD_FLAG_INFO)


@dataclass(slots=True)
class WftFragment:
    tune_name: str
    smallest_angular_inertia: float
    largest_angular_inertia: float
    bounding_sphere: WdrVector4
    root_center_of_gravity_offset: WdrVector4
    original_root_center_of_gravity_offset: WdrVector4
    unbroken_center_of_gravity_offset: WdrVector4
    damping: tuple[WdrVector4, ...]
    drawable: WftFragmentDrawable | None
    extra_drawables: tuple[WftFragmentDrawable | None, ...]
    extra_drawable_names: tuple[str, ...]
    damaged_drawable_index: int
    root_child_index: int
    groups: tuple[WftGroup, ...]
    children: tuple[WftChild, ...]
    archetype: WftPhysicsArchetype | None
    damaged_archetype: WftPhysicsArchetype | None
    bound: WbnBound | None
    child_inertia: tuple[WdrVector4, ...]
    damaged_child_inertia: tuple[WdrVector4, ...]
    child_matrices: tuple[WftMatrix3x4, ...]
    self_collisions: tuple[WftSelfCollision, ...]
    model_index: int
    estimated_cache_size: int
    estimated_articulated_cache_size: int
    root_group_count: int
    root_damage_region_count: int
    bony_child_count: int
    flags: WftFragmentFlags
    entity_class: int
    become_rope: bool
    art_asset_id: int
    attach_bottom_end: bool
    client_class_id: int
    minimum_move_force: float

    def damping_for(self, kind: WftDampingKind | int) -> WdrVector4:
        return self.damping[int(kind)]

    @property
    def root_groups(self) -> tuple[WftGroup, ...]:
        return tuple(group for group in self.groups if group.is_root)

    def find_group(self, name: str) -> WftGroup | None:
        key = name.casefold()
        return next((group for group in self.groups if group.name.casefold() == key), None)

    @property
    def flag_info(self) -> tuple[WftFlagInfo, ...]:
        return explain_fragment_flags(self.flags)

    @property
    def unresolved_flags(self) -> int:
        return int(self.flags) & ~_flag_mask(WFT_FRAGMENT_FLAG_INFO)

    def iter_drawables(self) -> Iterator[WftFragmentDrawable]:
        seen: set[int] = set()
        candidates = [self.drawable, *self.extra_drawables]
        candidates.extend(child.undamaged_drawable for child in self.children)
        candidates.extend(child.damaged_drawable for child in self.children)
        for drawable in candidates:
            if drawable is None or drawable.pointer in seen:
                continue
            seen.add(drawable.pointer)
            yield drawable


class _WftReader:
    def __init__(self, resource: Rsc5Resource) -> None:
        self.resource = resource
        self.drawable_reader = _WdrReader(resource)
        self.bound_parser = _WbnParser(resource.virtual_data)
        self.drawables: dict[int, WftFragmentDrawable] = {}
        self.archetypes: dict[int, WftPhysicsArchetype] = {}
        self.common_shader_group: WdrShaderGroup | None = None

    def read(self, pointer: int, size: int, label: str) -> bytes:
        return self.drawable_reader.read(pointer, size, label)

    def string(self, pointer: int) -> str:
        return self.drawable_reader.string(pointer)

    def _bound(self, pointer: int) -> WbnBound | None:
        if pointer == 0:
            return None
        if pointer & 0xF0000000 != RSC5_VIRTUAL_BASE:
            raise ValueError("WFT bounds must reside in the RSC5 virtual allocation")
        return self.bound_parser.parse_bound(pointer & 0x0FFFFFFF)

    def _pointer_array(self, pointer: int, count: int, label: str) -> tuple[int, ...]:
        if count == 0:
            return ()
        return struct.unpack(f"<{count}I", self.read(pointer, count * 4, label))

    def _string_array(self, pointer: int, count: int, label: str) -> tuple[str, ...]:
        return tuple(self.string(value) for value in self._pointer_array(pointer, count, label))

    def _vector4_array(self, pointer: int, count: int, label: str) -> tuple[WdrVector4, ...]:
        if pointer == 0 or count == 0:
            return ()
        raw = self.read(pointer, count * 16, label)
        return tuple(WdrVector4(*struct.unpack_from("<4f", raw, index * 16)) for index in range(count))

    def parse_drawable(self, pointer: int) -> WftFragmentDrawable | None:
        if pointer == 0:
            return None
        cached = self.drawables.get(pointer)
        if cached is not None:
            return cached
        raw = self.read(pointer, WFT_DRAWABLE_SIZE, "WFT fragment drawable")
        drawable = self.drawable_reader.parse_drawable(pointer, has_lights=False)
        fragment_matrix = WdrMatrix4(struct.unpack_from("<16f", raw, 0x80))
        bound_pointer = struct.unpack_from("<I", raw, 0xC0)[0]
        indices_pointer, indices_count, _indices_capacity = struct.unpack_from("<IHH", raw, 0xC4)
        matrices_pointer, matrices_count, _matrices_capacity = struct.unpack_from("<IHH", raw, 0xCC)
        indices = (
            ()
            if indices_count == 0
            else struct.unpack(
                f"<{indices_count}I",
                self.read(indices_pointer, indices_count * 4, "WFT fragment matrix indices"),
            )
        )
        matrix_raw = (
            b""
            if matrices_count == 0
            else self.read(matrices_pointer, matrices_count * 64, "WFT fragment matrices")
        )
        matrices = tuple(
            WdrMatrix4(struct.unpack_from("<16f", matrix_raw, index * 64))
            for index in range(matrices_count)
        )
        result = WftFragmentDrawable(
            self.string(struct.unpack_from("<I", raw, 0xE0)[0]),
            drawable,
            fragment_matrix,
            self._bound(bound_pointer),
            indices,
            matrices,
            pointer,
            self.common_shader_group,
        )
        if result.uses_inherited_shader_group:
            assert result.shader_group is not None
            for geometry in result.geometries:
                if geometry.shader_index < len(result.shader_group.shaders):
                    geometry.shader = result.shader_group.shaders[geometry.shader_index]
        self.drawables[pointer] = result
        return result

    def parse_archetype(self, pointer: int) -> WftPhysicsArchetype | None:
        if pointer == 0:
            return None
        cached = self.archetypes.get(pointer)
        if cached is not None:
            return cached
        raw = self.read(pointer, WFT_PHYSICS_ARCHETYPE_SIZE, "WFT physics archetype")
        archetype_type, name_pointer, bound_pointer, type_flags, include_flags = struct.unpack_from(
            "<5I", raw, 4
        )
        property_flags, reference_count = struct.unpack_from("<2H", raw, 0x18)
        mass, inverse_mass, gravity, maximum_speed, maximum_angular_speed = struct.unpack_from(
            "<5f", raw, 0x1C
        )
        inertia = WdrVector4(*struct.unpack_from("<4f", raw, 0x30))
        inverse_inertia = WdrVector4(*struct.unpack_from("<4f", raw, 0x40))
        damping = tuple(
            WdrVector4(*struct.unpack_from("<4f", raw, 0x50 + index * 16))
            for index in range(6)
        )
        result = WftPhysicsArchetype(
            self.string(name_pointer), archetype_type, type_flags, include_flags,
            property_flags, reference_count, mass, inverse_mass, gravity,
            maximum_speed, maximum_angular_speed, inertia, inverse_inertia,
            damping, self._bound(bound_pointer), pointer,
        )
        self.archetypes[pointer] = result
        return result

    def parse_group(self, pointer: int, name: str) -> WftGroup:
        raw = self.read(pointer, WFT_GROUP_SIZE, "WFT fragment group")
        values = struct.unpack_from("<14f", raw, 0xD0)
        (
            child_group_index, parent_group_index, child_index, child_count,
            child_group_count, _padding_1, _padding_2, flags,
        ) = struct.unpack_from("<8B", raw, 0x10C)
        minimum_damage_force, damage_health = struct.unpack_from("<2f", raw, 0x114)
        inline_name = raw[0x11C : 0x148].split(b"\0", 1)[0].decode("utf-8", errors="replace")
        return WftGroup(
            name or inline_name,
            *values,
            child_group_index,
            parent_group_index,
            child_index,
            child_count,
            child_group_count,
            WftGroupFlags(flags),
            minimum_damage_force,
            damage_health,
            pointer,
        )

    def parse_child(self, pointer: int) -> WftChild:
        raw = self.read(pointer, WFT_CHILD_SIZE, "WFT fragment child")
        undamaged_mass, damaged_mass = struct.unpack_from("<2f", raw, 4)
        group_index, flags, bone_index = struct.unpack_from("<BBH", raw, 0x0C)
        bone_attachment = WdrMatrix4(struct.unpack_from("<16f", raw, 0x10))
        link_attachment = WdrMatrix4(struct.unpack_from("<16f", raw, 0x50))
        undamaged_pointer, damaged_pointer = struct.unpack_from("<2I", raw, 0x90)
        event_pointers = (
            *struct.unpack_from("<4I", raw, 0x98),
            struct.unpack_from("<I", raw, 0xB8)[0],
            struct.unpack_from("<I", raw, 0x184)[0],
            struct.unpack_from("<I", raw, 0x250)[0],
        )
        return WftChild._from_pointers(
            undamaged_mass,
            damaged_mass,
            group_index,
            WftChildFlags(flags),
            bone_index,
            bone_attachment,
            link_attachment,
            undamaged_pointer,
            damaged_pointer,
            WftEventReferences(*event_pointers),
            pointer,
            self.parse_drawable,
        )

    def parse_fragment(self) -> WftFragment:
        raw = self.read(RSC5_VIRTUAL_BASE, WFT_FRAGMENT_SIZE, "WFT fragment")
        smallest, largest = struct.unpack_from("<2f", raw, 8)
        bounding_sphere = WdrVector4(*struct.unpack_from("<4f", raw, 0x10))
        root_offset = WdrVector4(*struct.unpack_from("<4f", raw, 0x20))
        original_offset = WdrVector4(*struct.unpack_from("<4f", raw, 0x30))
        unbroken_offset = WdrVector4(*struct.unpack_from("<4f", raw, 0x40))
        damping = tuple(
            WdrVector4(*struct.unpack_from("<4f", raw, 0x50 + index * 16))
            for index in range(6)
        )
        name_pointer, drawable_pointer, extra_pointer, extra_names_pointer = struct.unpack_from(
            "<4I", raw, 0xB0
        )
        extra_count = struct.unpack_from("<I", raw, 0xC0)[0]
        damaged_index, root_child_index = struct.unpack_from("<iI", raw, 0xC4)
        group_names_pointer, groups_pointer, children_pointer = struct.unpack_from("<3I", raw, 0xCC)
        archetype_pointer, damaged_archetype_pointer, bound_pointer = struct.unpack_from(
            "<3I", raw, 0xE4
        )
        inertia_pointer, damaged_inertia_pointer, matrices_pointer = struct.unpack_from(
            "<3I", raw, 0xF0
        )
        collision_first_pointer, collision_second_pointer = struct.unpack_from("<2I", raw, 0xFC)
        model_index = struct.unpack_from("<I", raw, 0x104)[0]
        (
            self_collision_count, maximum_self_collision_count, group_count, child_count,
            root_group_count, root_damage_count, bony_child_count, flags, entity_class,
            become_rope, art_asset_id, attach_bottom_end,
        ) = struct.unpack_from("<12B", raw, 0x1F0)
        if self_collision_count > maximum_self_collision_count:
            raise ValueError("WFT self-collision count exceeds its capacity")
        client_class_id, minimum_move_force = struct.unpack_from("<if", raw, 0x1FC)
        estimated_cache_size, estimated_articulated_cache_size = struct.unpack_from(
            "<2I", raw, 0x1E8
        )

        extra_pointers = self._pointer_array(extra_pointer, extra_count, "WFT extra drawable pointers")
        extra_names = self._string_array(extra_names_pointer, extra_count, "WFT extra drawable names")
        group_names = self._string_array(group_names_pointer, group_count, "WFT group names")
        group_pointers = self._pointer_array(groups_pointer, group_count, "WFT group pointers")
        child_pointers = self._pointer_array(children_pointer, child_count, "WFT child pointers")
        groups = tuple(
            self.parse_group(pointer, group_names[index])
            for index, pointer in enumerate(group_pointers)
        )
        children = tuple(self.parse_child(pointer) for pointer in child_pointers)
        for child in children:
            if child.group_index >= len(groups):
                raise ValueError("WFT child references a missing fragment group")
            child.group = groups[child.group_index]
        for group in groups:
            end = group.child_index + group.child_count
            if end > len(children):
                raise ValueError("WFT fragment group child range exceeds the child array")
            group.children = children[group.child_index:end]

        child_inertia = self._vector4_array(inertia_pointer, child_count, "WFT child inertia")
        damaged_child_inertia = self._vector4_array(
            damaged_inertia_pointer, child_count, "WFT damaged child inertia"
        )
        child_matrix_raw = (
            b"" if matrices_pointer == 0 or child_count == 0
            else self.read(matrices_pointer, child_count * 48, "WFT child matrices")
        )
        child_matrices = tuple(
            WftMatrix3x4(struct.unpack_from("<12f", child_matrix_raw, index * 48))
            for index in range(child_count)
        )
        first_indices = (
            () if self_collision_count == 0
            else tuple(self.read(collision_first_pointer, self_collision_count, "WFT first self-collision indices"))
        )
        second_indices = (
            () if self_collision_count == 0
            else tuple(self.read(collision_second_pointer, self_collision_count, "WFT second self-collision indices"))
        )
        drawable = self.parse_drawable(drawable_pointer)
        self.common_shader_group = (
            None if drawable is None else drawable.serialized_shader_group
        )
        extra_drawables = tuple(
            self.parse_drawable(pointer) for pointer in extra_pointers
        )
        return WftFragment(
            self.string(name_pointer), smallest, largest, bounding_sphere, root_offset,
            original_offset, unbroken_offset, damping, drawable,
            extra_drawables, extra_names,
            damaged_index, root_child_index, groups, children,
            self.parse_archetype(archetype_pointer),
            self.parse_archetype(damaged_archetype_pointer), self._bound(bound_pointer),
            child_inertia, damaged_child_inertia, child_matrices,
            tuple(WftSelfCollision(first, second) for first, second in zip(first_indices, second_indices)),
            model_index, estimated_cache_size, estimated_articulated_cache_size,
            root_group_count, root_damage_count, bony_child_count, WftFragmentFlags(flags),
            entity_class, bool(become_rope), art_asset_id, bool(attach_bottom_end),
            client_class_id, minimum_move_force,
        )


@dataclass(slots=True)
class WftDocument:
    fragment: WftFragment
    resource: Rsc5Resource
    name: str = "fragment.wft"
    source_path: str = ""

    @classmethod
    def from_path(cls, path: str | Path) -> WftDocument:
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name)
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "fragment.wft") -> WftDocument:
        resource = Rsc5Resource.from_bytes(data)
        if resource.version != WFT_RESOURCE_VERSION:
            raise ValueError(f"unsupported WFT resource version: {resource.version:#x}")
        return cls(_WftReader(resource).parse_fragment(), resource, name)

    @property
    def drawable(self) -> WftFragmentDrawable | None:
        return self.fragment.drawable

    @property
    def groups(self) -> tuple[WftGroup, ...]:
        return self.fragment.groups

    @property
    def children(self) -> tuple[WftChild, ...]:
        return self.fragment.children

    @property
    def models(self) -> tuple[WdrDrawableModel, ...]:
        return () if self.drawable is None else self.drawable.models

    @property
    def geometries(self) -> tuple[WdrGeometry, ...]:
        return () if self.drawable is None else self.drawable.geometries

    @property
    def shaders(self) -> tuple[WdrShader, ...]:
        if self.drawable is None or self.drawable.shader_group is None:
            return ()
        return self.drawable.shader_group.shaders

    @property
    def embedded_texture_dictionary(self) -> Rsc5TextureDictionary | None:
        if self.drawable is None or self.drawable.shader_group is None:
            return None
        return self.drawable.shader_group.texture_dictionary

    @property
    def embedded_textures(self) -> tuple[Rsc5Texture, ...]:
        dictionary = self.embedded_texture_dictionary
        return () if dictionary is None else dictionary.textures

    def find_embedded_texture(self, name: str) -> Rsc5Texture | None:
        dictionary = self.embedded_texture_dictionary
        return None if dictionary is None else dictionary.get(name)

    def iter_drawables(self) -> Iterator[WftFragmentDrawable]:
        yield from self.fragment.iter_drawables()

    def _project_drawable(
        self,
        drawable: WftFragmentDrawable,
        *,
        name: str,
    ) -> ModelAsset:
        source = drawable.drawable
        effective_group = drawable.shader_group
        if source.shader_group is not effective_group:
            source = replace(source, shader_group=effective_group)
        document = WdrDocument(source, self.resource, name, self.source_path)
        return document.to_model()

    def to_model(self) -> ModelAsset:
        """Project the common drawable into FourFury's target-independent model contract."""

        if self.drawable is None:
            raise ValueError("WFT fragment has no common drawable")
        return self._project_drawable(self.drawable, name=self.name)

    def to_fragment(self) -> FragmentAsset:
        """Project every visual state and physical piece into a neutral fragment."""

        fragment = self.fragment
        stem = Path(self.name).stem
        models_by_pointer: dict[int, ModelAsset] = {}

        def project(
            drawable: WftFragmentDrawable | None,
            fallback_name: str,
        ) -> ModelAsset | None:
            if drawable is None:
                return None
            cached = models_by_pointer.get(drawable.pointer)
            if cached is not None:
                return cached
            model = self._project_drawable(
                drawable,
                name=drawable.name or fallback_name,
            )
            models_by_pointer[drawable.pointer] = model
            return model

        common_model = project(fragment.drawable, stem)
        pieces = []
        for index, child in enumerate(fragment.children):
            group_name = (
                child.group.name
                if child.group is not None and child.group.name
                else f"piece_{index}"
            )
            inertia = (
                None
                if index >= len(fragment.child_inertia)
                else tuple(fragment.child_inertia[index])
            )
            damaged_inertia = (
                None
                if index >= len(fragment.damaged_child_inertia)
                else tuple(fragment.damaged_child_inertia[index])
            )
            physics_transform = (
                None
                if index >= len(fragment.child_matrices)
                else fragment.child_matrices[index].values
            )
            pieces.append(FragmentPiece(
                index=index,
                name=group_name,
                group_index=child.group_index,
                bone_index=child.bone_index,
                flags=int(child.flags),
                undamaged_mass=child.undamaged_mass,
                damaged_mass=child.damaged_mass,
                bone_attachment=child.bone_attachment.values,
                link_attachment=child.link_attachment.values,
                physics_transform=physics_transform,
                inertia=inertia,
                damaged_inertia=damaged_inertia,
                undamaged_model=project(
                    child.undamaged_drawable,
                    f"{stem}_{group_name}_undamaged",
                ),
                damaged_model=project(
                    child.damaged_drawable,
                    f"{stem}_{group_name}_damaged",
                ),
            ))

        coordinate_system = (
            ModelCoordinateSystem()
            if common_model is None
            else common_model.coordinate_system
        )
        return FragmentAsset(
            name=stem,
            common_model=common_model,
            pieces=tuple(pieces),
            flags=int(fragment.flags),
            root_child_index=fragment.root_child_index,
            model_index=fragment.model_index,
            bounding_sphere=ModelBoundingSphere(
                center=(
                    fragment.bounding_sphere.x,
                    fragment.bounding_sphere.y,
                    fragment.bounding_sphere.z,
                ),
                radius=fragment.bounding_sphere.w,
            ),
            root_center_of_gravity_offset=tuple(
                fragment.root_center_of_gravity_offset
            ),
            original_root_center_of_gravity_offset=tuple(
                fragment.original_root_center_of_gravity_offset
            ),
            unbroken_center_of_gravity_offset=tuple(
                fragment.unbroken_center_of_gravity_offset
            ),
            damping=tuple(tuple(value) for value in fragment.damping),
            source_path=self.source_path,
            coordinate_system=coordinate_system,
        )

    def to_models(self) -> tuple[ModelAsset, ...]:
        """Return every unique drawable model used by the neutral fragment."""

        return self.to_fragment().models

    def to_bytes(self) -> bytes:
        """Return the original lossless RSC5 resource."""

        return self.resource.to_bytes()

    def save(self, path: str | Path) -> None:
        atomic_write(path, self.to_bytes())


def load_wft(source: str | Path | bytes | BinaryIO) -> WftDocument:
    if isinstance(source, (str, Path)):
        return WftDocument.from_path(source)
    if isinstance(source, bytes):
        return WftDocument.from_bytes(source)
    return WftDocument.from_bytes(source.read())


__all__ = [
    "WFT_CHILD_FLAG_INFO",
    "WFT_CHILD_SIZE",
    "WFT_DRAWABLE_SIZE",
    "WFT_FRAGMENT_FLAG_INFO",
    "WFT_FRAGMENT_SIZE",
    "WFT_GROUP_FLAG_INFO",
    "WFT_GROUP_SIZE",
    "WFT_PHYSICS_ARCHETYPE_SIZE",
    "WFT_RESOURCE_VERSION",
    "WftChild",
    "WftChildFlags",
    "WftDampingKind",
    "WftDocument",
    "WftEventReferences",
    "WftFlag",
    "WftFlagConfidence",
    "WftFlagInfo",
    "WftFragment",
    "WftFragmentDrawable",
    "WftFragmentFlags",
    "WftGroup",
    "WftGroupFlags",
    "WftMatrix3x4",
    "WftPhysicsArchetype",
    "WftSelfCollision",
    "explain_child_flags",
    "explain_fragment_flags",
    "explain_group_flags",
    "load_wft",
]
