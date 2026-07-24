from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True, slots=True)
class WdrVector2:
    x: float
    y: float

    def __iter__(self) -> Iterator[float]:
        return iter((self.x, self.y))


@dataclass(frozen=True, slots=True)
class WdrVector3:
    x: float
    y: float
    z: float

    def __iter__(self) -> Iterator[float]:
        return iter((self.x, self.y, self.z))


@dataclass(frozen=True, slots=True)
class WdrVector4:
    x: float
    y: float
    z: float
    w: float

    def __iter__(self) -> Iterator[float]:
        return iter((self.x, self.y, self.z, self.w))


@dataclass(frozen=True, slots=True)
class WdrMatrix4:
    """A row-major 4x4 matrix using the same convention as RAGE/System.Numerics."""

    values: tuple[
        float, float, float, float,
        float, float, float, float,
        float, float, float, float,
        float, float, float, float,
    ]

    @classmethod
    def identity(cls) -> "WdrMatrix4":
        return cls((
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ))

    @classmethod
    def transformation(
        cls,
        scale: WdrVector3,
        rotation: WdrVector4,
        translation: WdrVector3,
    ) -> "WdrMatrix4":
        x, y, z, w = rotation
        sx, sy, sz = scale
        return cls((
            sx * (1.0 - 2.0 * (y * y + z * z)),
            sx * (2.0 * (x * y + z * w)),
            sx * (2.0 * (x * z - y * w)),
            0.0,
            sy * (2.0 * (x * y - z * w)),
            sy * (1.0 - 2.0 * (z * z + x * x)),
            sy * (2.0 * (y * z + x * w)),
            0.0,
            sz * (2.0 * (x * z + y * w)),
            sz * (2.0 * (y * z - x * w)),
            sz * (1.0 - 2.0 * (y * y + x * x)),
            0.0,
            translation.x, translation.y, translation.z, 1.0,
        ))

    @property
    def rows(self) -> tuple[tuple[float, float, float, float], ...]:
        return tuple(
            self.values[index:index + 4] for index in range(0, 16, 4)
        )

    @property
    def translation(self) -> WdrVector3:
        return WdrVector3(*self.values[12:15])

    def __iter__(self) -> Iterator[float]:
        return iter(self.values)

    def __matmul__(self, other: "WdrMatrix4") -> "WdrMatrix4":
        left = self.values
        right = other.values
        return WdrMatrix4(tuple(
            sum(left[row * 4 + item] * right[item * 4 + column] for item in range(4))
            for row in range(4)
            for column in range(4)
        ))  # type: ignore[arg-type]

    def inverse(self) -> "WdrMatrix4":
        augmented = [
            list(self.values[row * 4:(row + 1) * 4])
            + [1.0 if row == column else 0.0 for column in range(4)]
            for row in range(4)
        ]
        for column in range(4):
            pivot = max(range(column, 4), key=lambda row: abs(augmented[row][column]))
            if abs(augmented[pivot][column]) < 1e-12:
                raise ValueError("WDR matrix is singular")
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
            divisor = augmented[column][column]
            augmented[column] = [value / divisor for value in augmented[column]]
            for row in range(4):
                if row == column:
                    continue
                factor = augmented[row][column]
                augmented[row] = [
                    value - factor * pivot_value
                    for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
                ]
        return WdrMatrix4(tuple(
            augmented[row][column] for row in range(4) for column in range(4, 8)
        ))  # type: ignore[arg-type]


__all__ = [
    "WdrVector2",
    "WdrVector3",
    "WdrVector4",
    "WdrMatrix4",
]
