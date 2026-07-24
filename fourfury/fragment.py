from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

from .model import (
    ModelAsset,
    ModelBoundingSphere,
    ModelCoordinateSystem,
    ModelMatrix4,
    ModelVector4,
)

FragmentMatrix3x4: TypeAlias = tuple[
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


@dataclass(frozen=True, slots=True)
class FragmentPiece:
    """One renderer-neutral breakable piece and its two visual states."""

    index: int
    name: str
    group_index: int
    bone_index: int
    flags: int
    undamaged_mass: float
    damaged_mass: float
    bone_attachment: ModelMatrix4
    link_attachment: ModelMatrix4
    physics_transform: FragmentMatrix3x4 | None = None
    inertia: ModelVector4 | None = None
    damaged_inertia: ModelVector4 | None = None
    undamaged_model: ModelAsset | None = None
    damaged_model: ModelAsset | None = None

    @property
    def has_damaged_state(self) -> bool:
        return self.damaged_model is not None

    @property
    def models(self) -> tuple[ModelAsset, ...]:
        models = []
        if self.undamaged_model is not None:
            models.append(self.undamaged_model)
        if (
            self.damaged_model is not None
            and self.damaged_model is not self.undamaged_model
        ):
            models.append(self.damaged_model)
        return tuple(models)

    def to_data(self) -> dict[str, object]:
        return {
            "index": self.index,
            "name": self.name,
            "group_index": self.group_index,
            "bone_index": self.bone_index,
            "flags": self.flags,
            "undamaged_mass": self.undamaged_mass,
            "damaged_mass": self.damaged_mass,
            "bone_attachment": self.bone_attachment,
            "link_attachment": self.link_attachment,
            "physics_transform": self.physics_transform,
            "inertia": self.inertia,
            "damaged_inertia": self.damaged_inertia,
            "undamaged_model": (
                None if self.undamaged_model is None else self.undamaged_model.name
            ),
            "damaged_model": (
                None if self.damaged_model is None else self.damaged_model.name
            ),
        }


@dataclass(frozen=True, slots=True)
class FragmentAsset:
    """Target-independent visual and physical projection of a fragment."""

    name: str
    common_model: ModelAsset | None
    pieces: tuple[FragmentPiece, ...]
    flags: int
    root_child_index: int
    model_index: int
    bounding_sphere: ModelBoundingSphere
    root_center_of_gravity_offset: ModelVector4
    original_root_center_of_gravity_offset: ModelVector4
    unbroken_center_of_gravity_offset: ModelVector4
    damping: tuple[ModelVector4, ...]
    source_path: str = ""
    coordinate_system: ModelCoordinateSystem = field(
        default_factory=ModelCoordinateSystem
    )

    @property
    def models(self) -> tuple[ModelAsset, ...]:
        result: list[ModelAsset] = []
        seen: set[int] = set()
        candidates = [self.common_model]
        candidates.extend(model for piece in self.pieces for model in piece.models)
        for model in candidates:
            if model is None or id(model) in seen:
                continue
            seen.add(id(model))
            result.append(model)
        return tuple(result)

    def find_piece(self, value: str | int) -> FragmentPiece | None:
        if isinstance(value, str):
            key = value.casefold()
            return next(
                (piece for piece in self.pieces if piece.name.casefold() == key),
                None,
            )
        return next(
            (piece for piece in self.pieces if piece.index == int(value)),
            None,
        )

    def to_data(self) -> dict[str, object]:
        return {
            "name": self.name,
            "common_model": (
                None if self.common_model is None else self.common_model.name
            ),
            "pieces": [piece.to_data() for piece in self.pieces],
            "flags": self.flags,
            "root_child_index": self.root_child_index,
            "model_index": self.model_index,
            "bounding_sphere": {
                "center": self.bounding_sphere.center,
                "radius": self.bounding_sphere.radius,
            },
            "root_center_of_gravity_offset": self.root_center_of_gravity_offset,
            "original_root_center_of_gravity_offset": (
                self.original_root_center_of_gravity_offset
            ),
            "unbroken_center_of_gravity_offset": (
                self.unbroken_center_of_gravity_offset
            ),
            "damping": self.damping,
            "source_path": self.source_path,
        }


__all__ = [
    "FragmentAsset",
    "FragmentMatrix3x4",
    "FragmentPiece",
]
