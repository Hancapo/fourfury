from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntFlag
from pathlib import Path
from typing import BinaryIO, Iterator


MATERIALS_VERSION = 2.0
MATERIALS_RELATIVE_PATH = Path("common/data/materials/materials.dat")


class MaterialFlags(IntFlag):
    NONE = 0
    SEE_THROUGH = 0x1
    SHOOT_THROUGH = 0x2
    NATURALLY_WET = 0x4


@dataclass(frozen=True, slots=True)
class MaterialDefinition:
    material_id: int
    name: str
    fx_group: str
    helicopter_fx: str
    friction: float
    elasticity: float
    density: float
    tyre_grip: float
    wet_grip: float
    roughness: int
    pedestrian_density: float
    flammability: float
    burn_time: float
    burn_strength: float
    flags: MaterialFlags
    display_name: str
    line_number: int | None = field(default=None, compare=False)

    @property
    def see_through(self) -> bool:
        return bool(self.flags & MaterialFlags.SEE_THROUGH)

    @property
    def shoot_through(self) -> bool:
        return bool(self.flags & MaterialFlags.SHOOT_THROUGH)

    @property
    def naturally_wet(self) -> bool:
        return bool(self.flags & MaterialFlags.NATURALLY_WET)


@dataclass(slots=True)
class MaterialCatalog:
    version: float
    materials: tuple[MaterialDefinition, ...]
    source_path: str = ""
    _by_name: dict[str, MaterialDefinition] = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if any(material.material_id != index for index, material in enumerate(self.materials)):
            raise ValueError("materials.dat IDs must match their file order")
        self._by_name = {material.name.casefold(): material for material in self.materials}
        if len(self._by_name) != len(self.materials):
            raise ValueError("materials.dat contains duplicate material names")

    @classmethod
    def from_game(cls, game_path: str | Path) -> "MaterialCatalog":
        return cls.from_path(Path(game_path) / MATERIALS_RELATIVE_PATH)

    @classmethod
    def from_path(cls, path: str | Path, *, encoding: str = "utf-8-sig") -> "MaterialCatalog":
        source = Path(path)
        catalog = cls.from_bytes(source.read_bytes(), encoding=encoding)
        catalog.source_path = str(source)
        return catalog

    @classmethod
    def from_bytes(cls, data: bytes, *, encoding: str = "utf-8-sig") -> "MaterialCatalog":
        return cls.from_text(data.decode(encoding))

    @classmethod
    def from_text(cls, text: str) -> "MaterialCatalog":
        version: float | None = None
        materials: list[MaterialDefinition] = []
        for line_number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if version is None:
                try:
                    version = float(stripped)
                except ValueError as exc:
                    raise ValueError("materials.dat does not start with a numeric version") from exc
                if version != MATERIALS_VERSION:
                    raise ValueError(f"unsupported materials.dat version: {version:g}")
                continue
            values = stripped.split()
            if len(values) != 17:
                raise ValueError(
                    f"invalid materials.dat record on line {line_number}: expected 17 fields, got {len(values)}"
                )
            try:
                flag_values = tuple(int(value, 10) for value in values[13:16])
                if any(value not in (0, 1) for value in flag_values):
                    raise ValueError("material flags must be 0 or 1")
                flags = MaterialFlags(
                    (flag_values[0] << 0) | (flag_values[1] << 1) | (flag_values[2] << 2)
                )
                material = MaterialDefinition(
                    material_id=len(materials),
                    name=values[0],
                    fx_group=values[1],
                    helicopter_fx=values[2],
                    friction=float(values[3]),
                    elasticity=float(values[4]),
                    density=float(values[5]),
                    tyre_grip=float(values[6]),
                    wet_grip=float(values[7]),
                    roughness=int(values[8], 10),
                    pedestrian_density=float(values[9]),
                    flammability=float(values[10]),
                    burn_time=float(values[11]),
                    burn_strength=float(values[12]),
                    flags=flags,
                    display_name=values[16],
                    line_number=line_number,
                )
            except ValueError as exc:
                raise ValueError(f"invalid materials.dat value on line {line_number}: {exc}") from exc
            materials.append(material)
        if version is None:
            raise ValueError("empty materials.dat")
        if len(materials) > 0x100:
            raise ValueError("materials.dat exceeds the 256 IDs representable by WBN")
        return cls(version, tuple(materials))

    def __len__(self) -> int:
        return len(self.materials)

    def __iter__(self) -> Iterator[MaterialDefinition]:
        return iter(self.materials)

    def __getitem__(self, key: int | str) -> MaterialDefinition:
        if isinstance(key, int):
            return self.materials[key]
        return self._by_name[key.casefold()]

    def get(self, key: int | str) -> MaterialDefinition | None:
        if isinstance(key, int):
            return self.materials[key] if 0 <= key < len(self.materials) else None
        return self._by_name.get(key.casefold())


def load_materials(
    source: str | Path | bytes | BinaryIO,
    *,
    encoding: str = "utf-8-sig",
) -> MaterialCatalog:
    if isinstance(source, (str, Path)):
        return MaterialCatalog.from_path(source, encoding=encoding)
    if isinstance(source, bytes):
        return MaterialCatalog.from_bytes(source, encoding=encoding)
    return MaterialCatalog.from_bytes(source.read(), encoding=encoding)


__all__ = [
    "MATERIALS_RELATIVE_PATH", "MATERIALS_VERSION", "MaterialCatalog", "MaterialDefinition",
    "MaterialFlags", "load_materials",
]
