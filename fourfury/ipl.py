from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .ide import IdeDocument, IdeEntry


@dataclass(frozen=True, slots=True)
class IplOccluder:
    """One GTA IV ``OCCL`` box from a text IPL."""

    center_x: float
    center_y: float
    bottom_z: float
    width_x: float
    width_y: float
    height: float
    rotation: float
    unused_1: float = 0.0
    unused_2: float = 0.0
    flags: int = 0
    line_number: int | None = None

    @classmethod
    def from_entry(cls, entry: IdeEntry) -> "IplOccluder":
        if entry.section.casefold() != "occl":
            raise ValueError(f"IPL entry is not in the OCCL section: {entry.section!r}")
        if len(entry.values) != 10:
            location = f" on line {entry.line_number}" if entry.line_number else ""
            raise ValueError(
                f"IPL OCCL entry{location} requires exactly 10 values, got {len(entry.values)}"
            )
        try:
            numeric = [float(value) for value in entry.values[:9]]
            flags = int(entry.values[9], 0)
        except ValueError as exc:
            location = f" on line {entry.line_number}" if entry.line_number else ""
            raise ValueError(f"invalid IPL OCCL value{location}: {exc}") from exc
        return cls(*numeric, flags, entry.line_number)

    @property
    def center(self) -> tuple[float, float, float]:
        return (
            self.center_x,
            self.center_y,
            self.bottom_z + self.height * 0.5,
        )

    @property
    def size(self) -> tuple[float, float, float]:
        return (abs(self.width_x), abs(self.width_y), abs(self.height))


class IplDocument(IdeDocument):
    """Section-preserving reader/writer for GTA IV text IPL files."""

    @classmethod
    def empty(cls, name: str = "placement.ipl", *, newline: str = "\r\n") -> "IplDocument":
        return cls(
            name=name if name.lower().endswith(".ipl") else f"{name}.ipl",
            default_newline=newline,
        )

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        name: str = "placement.ipl",
        encoding: str = "utf-8",
    ) -> "IplDocument":
        return super().from_bytes(data, name=name, encoding=encoding)

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        name: str = "placement.ipl",
        encoding: str = "utf-8",
        has_bom: bool = False,
    ) -> "IplDocument":
        return super().from_text(
            text,
            name=name,
            encoding=encoding,
            has_bom=has_bom,
        )

    @property
    def occluders(self) -> list[IplOccluder]:
        return [
            IplOccluder.from_entry(entry)
            for entry in self.iter_entries("occl")
        ]


def load_ipl(source: str | Path | bytes | BinaryIO, *, encoding: str = "utf-8") -> IplDocument:
    if isinstance(source, (str, Path)):
        return IplDocument.from_path(source, encoding=encoding)
    if isinstance(source, bytes):
        return IplDocument.from_bytes(source, encoding=encoding)
    return IplDocument.from_bytes(source.read(), encoding=encoding)


def create_ipl(name: str = "placement.ipl") -> IplDocument:
    return IplDocument.empty(name)


__all__ = ["IplDocument", "IplOccluder", "create_ipl", "load_ipl"]
