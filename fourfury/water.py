from __future__ import annotations

import codecs
import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from enum import Enum, IntFlag
from pathlib import Path
from typing import BinaryIO

WATER_TRIANGLE_VALUE_COUNT = 22
WATER_QUAD_VALUE_COUNT = 30
WATER_VERTEX_VALUE_COUNT = 7


class WaterSurfaceShape(Enum):
    """Serialized GTA IV water surface geometry."""

    TRIANGLE = "triangle"
    QUAD = "quad"


class WaterSurfaceFlags(IntFlag):
    """Flags consumed by GTA IV's water loader."""

    NONE = 0
    VISIBLE = 1 << 0
    RENDER = 1 << 2
    DYNAMIC = 1 << 3


WATER_KNOWN_FLAGS = (
    WaterSurfaceFlags.VISIBLE
    | WaterSurfaceFlags.RENDER
    | WaterSurfaceFlags.DYNAMIC
)


class WaterIssueSeverity(Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class WaterValidationIssue:
    code: str
    message: str
    surface_index: int
    severity: WaterIssueSeverity = WaterIssueSeverity.WARNING

    def to_data(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "surface_index": self.surface_index,
            "severity": self.severity.value,
        }


@dataclass(slots=True)
class WaterVertex:
    """One water vertex and the four legacy values retained by GTA IV."""

    x: float
    y: float
    z: float
    legacy_1: float = 0.0
    legacy_2: float = 0.0
    legacy_3: float = 0.0
    legacy_4: float = 0.0

    @property
    def position(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    @property
    def legacy_values(self) -> tuple[float, float, float, float]:
        return (self.legacy_1, self.legacy_2, self.legacy_3, self.legacy_4)

    def to_data(self) -> dict[str, object]:
        return {
            "position": self.position,
            "legacy_values": self.legacy_values,
        }


@dataclass(slots=True)
class WaterSurface:
    """A triangle or quad from GTA IV's ``water.dat``."""

    vertices: list[WaterVertex]
    flags: WaterSurfaceFlags | int = WaterSurfaceFlags.VISIBLE | WaterSurfaceFlags.RENDER
    wave_scale: float | None = None
    line_number: int | None = None
    _source_text: str | None = field(default=None, repr=False, compare=False)
    _source_signature: tuple[object, ...] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if len(self.vertices) not in (3, 4):
            raise ValueError(
                f"water surfaces require three or four vertices, got {len(self.vertices)}"
            )
        self.flags = WaterSurfaceFlags(int(self.flags))
        if len(self.vertices) == 3 and self.wave_scale is not None:
            raise ValueError("legacy water triangles do not serialize a wave scale")
        if len(self.vertices) == 4 and self.wave_scale is None:
            self.wave_scale = 0.0

    @property
    def shape(self) -> WaterSurfaceShape:
        return (
            WaterSurfaceShape.TRIANGLE
            if len(self.vertices) == 3
            else WaterSurfaceShape.QUAD
        )

    @property
    def is_visible(self) -> bool:
        return bool(self.flags & WaterSurfaceFlags.VISIBLE)

    @property
    def is_rendered(self) -> bool:
        return bool(self.flags & WaterSurfaceFlags.RENDER)

    @property
    def is_dynamic(self) -> bool:
        return bool(self.flags & WaterSurfaceFlags.DYNAMIC)

    @property
    def unresolved_flags(self) -> int:
        return int(self.flags) & ~int(WATER_KNOWN_FLAGS)

    @property
    def bounds(
        self,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        return (
            (
                min(vertex.x for vertex in self.vertices),
                min(vertex.y for vertex in self.vertices),
                min(vertex.z for vertex in self.vertices),
            ),
            (
                max(vertex.x for vertex in self.vertices),
                max(vertex.y for vertex in self.vertices),
                max(vertex.z for vertex in self.vertices),
            ),
        )

    @property
    def triangle_indices(self) -> tuple[tuple[int, int, int], ...]:
        if self.shape is WaterSurfaceShape.TRIANGLE:
            return ((0, 1, 2),)
        return ((0, 1, 2), (2, 1, 3))

    @property
    def area_xy(self) -> float:
        area = 0.0
        for first, second, third in self.triangle_indices:
            a = self.vertices[first]
            b = self.vertices[second]
            c = self.vertices[third]
            area += abs(
                (b.x - a.x) * (c.y - a.y)
                - (c.x - a.x) * (b.y - a.y)
            ) * 0.5
        return area

    def is_flat(self, *, tolerance: float = 1e-3) -> bool:
        height = self.vertices[0].z
        return all(
            abs(vertex.z - height) <= tolerance
            for vertex in self.vertices[1:]
        )

    @property
    def height(self) -> float | None:
        return self.vertices[0].z if self.is_flat() else None

    def is_axis_aligned(self, *, tolerance: float = 1e-3) -> bool:
        if self.shape is not WaterSurfaceShape.QUAD:
            return False
        minimum, maximum = self.bounds
        corners = (
            (minimum[0], minimum[1]),
            (maximum[0], minimum[1]),
            (minimum[0], maximum[1]),
            (maximum[0], maximum[1]),
        )
        return all(
            any(
                abs(vertex.x - x) <= tolerance
                and abs(vertex.y - y) <= tolerance
                for vertex in self.vertices
            )
            for x, y in corners
        )

    def height_at(
        self,
        x: float,
        y: float,
        *,
        tolerance: float = 1e-6,
    ) -> float | None:
        for indices in self.triangle_indices:
            a, b, c = (self.vertices[index] for index in indices)
            denominator = (
                (b.y - c.y) * (a.x - c.x)
                + (c.x - b.x) * (a.y - c.y)
            )
            if abs(denominator) <= tolerance:
                continue
            weight_a = (
                (b.y - c.y) * (x - c.x)
                + (c.x - b.x) * (y - c.y)
            ) / denominator
            weight_b = (
                (c.y - a.y) * (x - c.x)
                + (a.x - c.x) * (y - c.y)
            ) / denominator
            weight_c = 1.0 - weight_a - weight_b
            if min(weight_a, weight_b, weight_c) >= -tolerance:
                return weight_a * a.z + weight_b * b.z + weight_c * c.z
        return None

    def contains_xy(
        self,
        x: float,
        y: float,
        *,
        tolerance: float = 1e-6,
    ) -> bool:
        return self.height_at(x, y, tolerance=tolerance) is not None

    def iter_triangles(
        self,
    ) -> Iterator[
        tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ]:
        for indices in self.triangle_indices:
            yield tuple(  # type: ignore[return-value]
                self.vertices[index].position
                for index in indices
            )

    def to_data(self) -> dict[str, object]:
        traits = []
        if self.is_visible:
            traits.append("visible")
        if self.is_rendered:
            traits.append("render")
        if self.is_dynamic:
            traits.append("dynamic")
        return {
            "shape": self.shape.value,
            "vertices": [vertex.to_data() for vertex in self.vertices],
            "flags": int(self.flags),
            "traits": traits,
            "unresolved_flags": self.unresolved_flags,
            "wave_scale": self.wave_scale,
        }

    def _signature(self) -> tuple[object, ...]:
        return (
            tuple(
                (
                    vertex.x,
                    vertex.y,
                    vertex.z,
                    vertex.legacy_1,
                    vertex.legacy_2,
                    vertex.legacy_3,
                    vertex.legacy_4,
                )
                for vertex in self.vertices
            ),
            int(self.flags),
            self.wave_scale,
        )

    def _record_text(self) -> str:
        values: list[str] = []
        for vertex in self.vertices:
            values.extend(
                _format_float(value)
                for value in (
                    vertex.x,
                    vertex.y,
                    vertex.z,
                    vertex.legacy_1,
                    vertex.legacy_2,
                    vertex.legacy_3,
                    vertex.legacy_4,
                )
            )
        values.append(str(int(self.flags)))
        if self.shape is WaterSurfaceShape.QUAD:
            assert self.wave_scale is not None
            values.append(_format_float(self.wave_scale))
        return " ".join(values)


@dataclass(slots=True)
class _WaterLine:
    text: str
    newline: str
    surface: WaterSurface | None = None


class WaterDocument:
    """Lossless reader/writer for GTA IV ``water.dat`` files."""

    def __init__(
        self,
        *,
        name: str = "water.dat",
        lines: Iterable[_WaterLine] = (),
        encoding: str = "utf-8",
        has_bom: bool = False,
        default_newline: str = "\r\n",
        source_path: str = "",
    ) -> None:
        self.name = name if name.lower().endswith(".dat") else f"{name}.dat"
        self.encoding = encoding
        self.has_bom = has_bom
        self.default_newline = default_newline
        self.source_path = source_path
        self._lines = list(lines)

    @classmethod
    def empty(
        cls,
        name: str = "water.dat",
        *,
        newline: str = "\r\n",
    ) -> WaterDocument:
        return cls(name=name, default_newline=newline)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        encoding: str = "utf-8",
    ) -> WaterDocument:
        source = Path(path)
        document = cls.from_bytes(
            source.read_bytes(),
            name=source.name,
            encoding=encoding,
        )
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        name: str = "water.dat",
        encoding: str = "utf-8",
    ) -> WaterDocument:
        has_bom = data.startswith(codecs.BOM_UTF8)
        payload = data[len(codecs.BOM_UTF8):] if has_bom else data
        return cls.from_text(
            payload.decode(encoding),
            name=name,
            encoding=encoding,
            has_bom=has_bom,
        )

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        name: str = "water.dat",
        encoding: str = "utf-8",
        has_bom: bool = False,
    ) -> WaterDocument:
        split = text.splitlines(keepends=True)
        if text and not split:
            split = [text]
        default_newline = next(
            (
                newline
                for raw in split
                if (newline := _line_ending(raw))
            ),
            "\r\n",
        )
        lines: list[_WaterLine] = []
        for line_number, raw in enumerate(split, 1):
            newline = _line_ending(raw)
            content = raw[:-len(newline)] if newline else raw
            surface = _parse_surface(content, line_number)
            lines.append(_WaterLine(content, newline, surface))
        return cls(
            name=name,
            lines=lines,
            encoding=encoding,
            has_bom=has_bom,
            default_newline=default_newline,
        )

    @property
    def surfaces(self) -> tuple[WaterSurface, ...]:
        return tuple(
            line.surface
            for line in self._lines
            if line.surface is not None
        )

    def __len__(self) -> int:
        return sum(line.surface is not None for line in self._lines)

    def __iter__(self) -> Iterator[WaterSurface]:
        return iter(self.surfaces)

    def __getitem__(self, index: int) -> WaterSurface:
        return self.surfaces[index]

    def add_surface(
        self,
        surface: WaterSurface,
        *,
        index: int | None = None,
    ) -> WaterSurface:
        if not isinstance(surface, WaterSurface):
            raise TypeError("surface must be a WaterSurface")
        new_line = _WaterLine("", self.default_newline, surface)
        if index is None:
            if self._lines and not self._lines[-1].newline:
                self._lines[-1].newline = self.default_newline
            self._lines.append(new_line)
            return surface

        positions = [
            line_index
            for line_index, line in enumerate(self._lines)
            if line.surface is not None
        ]
        normalized = index if index >= 0 else max(len(positions) + index, 0)
        if normalized >= len(positions):
            return self.add_surface(surface)
        self._lines.insert(positions[normalized], new_line)
        return surface

    def remove_surface(self, surface: WaterSurface) -> bool:
        for index, line in enumerate(self._lines):
            if line.surface is surface:
                del self._lines[index]
                return True
        return False

    def surfaces_at(
        self,
        x: float,
        y: float,
        *,
        visible_only: bool = False,
    ) -> tuple[WaterSurface, ...]:
        return tuple(
            surface
            for surface in self
            if (not visible_only or surface.is_visible)
            and surface.contains_xy(x, y)
        )

    def validate(self) -> tuple[WaterValidationIssue, ...]:
        issues: list[WaterValidationIssue] = []
        for surface_index, surface in enumerate(self):
            values = [
                value
                for vertex in surface.vertices
                for value in (
                    vertex.x,
                    vertex.y,
                    vertex.z,
                    vertex.legacy_1,
                    vertex.legacy_2,
                    vertex.legacy_3,
                    vertex.legacy_4,
                )
            ]
            if surface.wave_scale is not None:
                values.append(surface.wave_scale)
            if not all(math.isfinite(value) for value in values):
                issues.append(WaterValidationIssue(
                    "non_finite_value",
                    "surface contains a non-finite numeric value",
                    surface_index,
                    WaterIssueSeverity.ERROR,
                ))
            if surface.area_xy <= 1e-6:
                issues.append(WaterValidationIssue(
                    "degenerate_surface",
                    "surface has no measurable area in the XY plane",
                    surface_index,
                ))
            if surface.unresolved_flags:
                issues.append(WaterValidationIssue(
                    "unresolved_flags",
                    f"surface retains unresolved flag bits {surface.unresolved_flags:#x}",
                    surface_index,
                ))
        return tuple(issues)

    def to_data(self) -> dict[str, object]:
        return {
            "name": self.name,
            "surfaces": [surface.to_data() for surface in self],
        }

    def to_mesh_data(
        self,
        *,
        visible_only: bool = False,
    ) -> dict[str, object]:
        vertices: list[tuple[float, float, float]] = []
        triangles: list[tuple[int, int, int]] = []
        surface_indices: list[int] = []
        for surface_index, surface in enumerate(self):
            if visible_only and not surface.is_visible:
                continue
            base = len(vertices)
            vertices.extend(vertex.position for vertex in surface.vertices)
            for triangle in surface.triangle_indices:
                triangles.append(tuple(base + index for index in triangle))
                surface_indices.append(surface_index)
        return {
            "vertices": vertices,
            "triangles": triangles,
            "surface_indices": surface_indices,
        }

    def to_text(self) -> str:
        parts: list[str] = []
        for line in self._lines:
            if line.surface is None:
                content = line.text
            elif (
                line.surface._source_text is not None
                and line.surface._source_signature == line.surface._signature()
            ):
                content = line.surface._source_text
            else:
                content = line.surface._record_text()
            parts.append(content + line.newline)
        return "".join(parts)

    def to_bytes(self) -> bytes:
        payload = self.to_text().encode(self.encoding)
        return (codecs.BOM_UTF8 + payload) if self.has_bom else payload

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())


def _parse_surface(text: str, line_number: int) -> WaterSurface | None:
    stripped = text.strip()
    if not stripped or stripped[0] in ";*#":
        return None
    if stripped.casefold().startswith("processed"):
        return None

    values = stripped.split()
    if len(values) not in (WATER_TRIANGLE_VALUE_COUNT, WATER_QUAD_VALUE_COUNT):
        try:
            float(values[0])
        except (ValueError, IndexError):
            return None
        raise ValueError(
            f"water surface on line {line_number} requires "
            f"{WATER_TRIANGLE_VALUE_COUNT} or {WATER_QUAD_VALUE_COUNT} values, "
            f"got {len(values)}"
        )

    vertex_count = 3 if len(values) == WATER_TRIANGLE_VALUE_COUNT else 4
    try:
        vertices = [
            WaterVertex(*(
                float(value)
                for value in values[
                    index * WATER_VERTEX_VALUE_COUNT:
                    (index + 1) * WATER_VERTEX_VALUE_COUNT
                ]
            ))
            for index in range(vertex_count)
        ]
        flags = int(values[vertex_count * WATER_VERTEX_VALUE_COUNT], 0)
        wave_scale = (
            float(values[-1])
            if vertex_count == 4
            else None
        )
    except ValueError as exc:
        raise ValueError(f"invalid water value on line {line_number}: {exc}") from exc

    surface = WaterSurface(
        vertices,
        WaterSurfaceFlags(flags),
        wave_scale,
        line_number,
        text,
    )
    surface._source_signature = surface._signature()
    return surface


def _line_ending(value: str) -> str:
    if value.endswith("\r\n"):
        return "\r\n"
    if value.endswith("\n"):
        return "\n"
    if value.endswith("\r"):
        return "\r"
    return ""


def _format_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError(f"water values must be finite, got {value!r}")
    return repr(float(value))


def load_water(
    source: str | Path | bytes | BinaryIO,
    *,
    encoding: str = "utf-8",
) -> WaterDocument:
    if isinstance(source, bytes):
        return WaterDocument.from_bytes(source, encoding=encoding)
    if isinstance(source, (str, Path)):
        return WaterDocument.from_path(source, encoding=encoding)
    return WaterDocument.from_bytes(source.read(), encoding=encoding)


def create_water(name: str = "water.dat") -> WaterDocument:
    return WaterDocument.empty(name)


__all__ = [
    "WATER_KNOWN_FLAGS",
    "WATER_QUAD_VALUE_COUNT",
    "WATER_TRIANGLE_VALUE_COUNT",
    "WATER_VERTEX_VALUE_COUNT",
    "WaterDocument",
    "WaterIssueSeverity",
    "WaterSurface",
    "WaterSurfaceFlags",
    "WaterSurfaceShape",
    "WaterValidationIssue",
    "WaterVertex",
    "create_water",
    "load_water",
]
