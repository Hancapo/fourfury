from __future__ import annotations

import csv
from dataclasses import dataclass, field
from enum import IntFlag
from pathlib import Path
from typing import BinaryIO, Iterator, Literal

from ._utils import atomic_write

IdeLineKind = Literal["blank", "comment", "section", "end", "raw"]
IDE_ARCHETYPE_SECTIONS = frozenset({"objs", "tobj", "anim", "tanm"})


class IdeArchetypeFlags(IntFlag):
    NONE = 0
    RESERVED_01 = 1 << 0
    RESERVED_02 = 1 << 1
    ALPHA = 1 << 2
    RESERVED_04 = 1 << 3
    RESERVED_05 = 1 << 4
    TREE = 1 << 5
    RESERVED_07 = 1 << 6
    INSTANCE = 1 << 7
    RESERVED_09 = 1 << 8
    HAS_ANIMATION = 1 << 9
    HAS_UV_ANIMATION = 1 << 10
    SHADOW_ONLY = 1 << 11
    RESERVED_13 = 1 << 12
    DONT_CAST_SHADOWS = 1 << 13
    RESERVED_15 = 1 << 14
    RESERVED_16 = 1 << 15
    RESERVED_17 = 1 << 16
    DYNAMIC = 1 << 17
    RESERVED_19 = 1 << 18
    RESERVED_20 = 1 << 19
    RESERVED_21 = 1 << 20
    NO_BACKFACE_CULL = 1 << 21
    RESERVED_23 = 1 << 22
    RESERVED_24 = 1 << 23
    RESERVED_25 = 1 << 24
    RESERVED_26 = 1 << 25
    ENABLE_SPECIAL = 1 << 26
    RESERVED_28 = 1 << 27
    RESERVED_29 = 1 << 28
    RESERVED_30 = 1 << 29
    RESERVED_31 = 1 << 30
    RESERVED_32 = 1 << 31


@dataclass(slots=True)
class IdeLine:
    text: str
    newline: str = ""
    kind: IdeLineKind = "raw"
    section: str | None = None

    def render(self) -> str:
        return self.text + self.newline


@dataclass(slots=True)
class IdeEntry:
    section: str
    values: list[str]
    line_number: int | None = None
    newline: str = ""
    _original_text: str | None = field(default=None, repr=False, compare=False)
    _original_values: tuple[str, ...] = field(default=(), repr=False, compare=False)

    @classmethod
    def parse(cls, section: str, text: str, newline: str, line_number: int) -> "IdeEntry":
        try:
            values = next(csv.reader([text], skipinitialspace=True))
        except csv.Error:
            values = [part.strip() for part in text.split(",")]
        return cls(section, values, line_number, newline, text, tuple(values))

    def render(self) -> str:
        if self._original_text is not None and tuple(self.values) == self._original_values:
            text = self._original_text
        else:
            def encode(value: str) -> str:
                if any(character in value for character in ',"\r\n'):
                    return f'"{value.replace(chr(34), chr(34) * 2)}"'
                return value

            text = ", ".join(encode(value) for value in self.values)
        return text + self.newline

    def get_int(self, index: int, *, base: int = 0) -> int:
        return int(self.values[index], base)

    def get_float(self, index: int) -> float:
        return float(self.values[index])


@dataclass(slots=True)
class IdeArchetype:
    """Typed, editable view over an IDE archetype entry."""

    entry: IdeEntry = field(repr=False)

    def __post_init__(self) -> None:
        if self.entry.section.casefold() not in IDE_ARCHETYPE_SECTIONS:
            raise ValueError(f"IDE section is not an archetype section: {self.entry.section!r}")
        if len(self.entry.values) <= self._flags_index:
            raise ValueError(
                f"IDE {self.entry.section} archetype requires at least "
                f"{self._flags_index + 1} values"
            )

    @property
    def _is_animated(self) -> bool:
        return self.entry.section.casefold() in {"anim", "tanm"}

    @property
    def _flags_index(self) -> int:
        return 4 if self._is_animated else 3

    @property
    def name(self) -> str:
        return self.entry.values[0]

    @name.setter
    def name(self, value: str) -> None:
        self.entry.values[0] = value

    @property
    def texture_dictionary(self) -> str:
        return self.entry.values[1]

    @texture_dictionary.setter
    def texture_dictionary(self, value: str) -> None:
        self.entry.values[1] = value

    @property
    def animation_dictionary(self) -> str | None:
        return self.entry.values[2] if self._is_animated else None

    @animation_dictionary.setter
    def animation_dictionary(self, value: str | None) -> None:
        if not self._is_animated:
            if value is not None:
                raise ValueError("static IDE archetypes do not have an animation dictionary")
            return
        if value is None:
            raise ValueError("animated IDE archetypes require an animation dictionary")
        self.entry.values[2] = value

    @property
    def draw_distance(self) -> float:
        return float(self.entry.values[3 if self._is_animated else 2])

    @draw_distance.setter
    def draw_distance(self, value: float) -> None:
        self.entry.values[3 if self._is_animated else 2] = str(float(value))

    @property
    def flags(self) -> IdeArchetypeFlags:
        return IdeArchetypeFlags(int(self.entry.values[self._flags_index], 0))

    @flags.setter
    def flags(self, value: IdeArchetypeFlags | int) -> None:
        self.entry.values[self._flags_index] = str(int(value))

    @property
    def has_animation(self) -> bool:
        return bool(self.flags & IdeArchetypeFlags.HAS_ANIMATION)

    @property
    def has_uv_animation(self) -> bool:
        return bool(self.flags & IdeArchetypeFlags.HAS_UV_ANIMATION)

    @property
    def uv_animation_dictionary(self) -> str | None:
        return self.animation_dictionary if self.has_uv_animation else None

    @property
    def time_flags(self) -> int | None:
        if self.entry.section.casefold() == "tobj" and len(self.entry.values) > 16:
            return int(self.entry.values[16], 0)
        if self.entry.section.casefold() == "tanm" and len(self.entry.values) > 17:
            return int(self.entry.values[17], 0)
        return None


@dataclass(slots=True)
class IdeDocument:
    name: str = "definitions.ide"
    source_path: str = ""
    lines: list[IdeLine | IdeEntry] = field(default_factory=list)
    encoding: str = "utf-8"
    has_bom: bool = False
    default_newline: str = "\r\n"

    @classmethod
    def empty(cls, name: str = "definitions.ide", *, newline: str = "\r\n") -> "IdeDocument":
        return cls(name=name if name.lower().endswith(".ide") else f"{name}.ide", default_newline=newline)

    @classmethod
    def from_path(cls, path: str | Path, *, encoding: str = "utf-8") -> "IdeDocument":
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name, encoding=encoding)
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "definitions.ide", encoding: str = "utf-8") -> "IdeDocument":
        has_bom = data.startswith(b"\xef\xbb\xbf") and encoding.replace("_", "-").casefold() in {"utf-8", "utf8"}
        payload = data[3:] if has_bom else data
        return cls.from_text(payload.decode(encoding), name=name, encoding=encoding, has_bom=has_bom)

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        name: str = "definitions.ide",
        encoding: str = "utf-8",
        has_bom: bool = False,
    ) -> "IdeDocument":
        document = cls(name=name, encoding=encoding, has_bom=has_bom)
        active_section: str | None = None
        source_lines = text.splitlines(keepends=True)
        if not source_lines and text:
            source_lines = [text]
        for line_number, raw in enumerate(source_lines, 1):
            body, newline = cls._split_newline(raw)
            if newline and not any(isinstance(line, (IdeLine, IdeEntry)) and line.newline for line in document.lines):
                document.default_newline = newline
            stripped = body.strip()
            if not stripped:
                document.lines.append(IdeLine(body, newline, "blank", active_section))
            elif stripped.startswith("#"):
                document.lines.append(IdeLine(body, newline, "comment", active_section))
            elif active_section is None:
                if stripped.casefold() == "end":
                    document.lines.append(IdeLine(body, newline, "end"))
                else:
                    active_section = stripped.casefold()
                    document.lines.append(IdeLine(body, newline, "section", active_section))
            elif stripped.casefold() == "end":
                document.lines.append(IdeLine(body, newline, "end", active_section))
                active_section = None
            else:
                document.lines.append(IdeEntry.parse(active_section, body, newline, line_number))
        return document

    @staticmethod
    def _split_newline(line: str) -> tuple[str, str]:
        if line.endswith("\r\n"):
            return line[:-2], "\r\n"
        if line.endswith(("\r", "\n")):
            return line[:-1], line[-1]
        return line, ""

    @property
    def section_names(self) -> list[str]:
        return [line.section for line in self.lines if isinstance(line, IdeLine) and line.kind == "section" and line.section is not None]

    def iter_entries(self, section: str | None = None) -> Iterator[IdeEntry]:
        key = section.casefold() if section is not None else None
        for line in self.lines:
            if isinstance(line, IdeEntry) and (key is None or line.section.casefold() == key):
                yield line

    def get_entries(self, section: str) -> list[IdeEntry]:
        return list(self.iter_entries(section))

    def iter_archetypes(self, section: str | None = None) -> Iterator[IdeArchetype]:
        key = section.casefold() if section is not None else None
        if key is not None and key not in IDE_ARCHETYPE_SECTIONS:
            raise ValueError(f"IDE section is not an archetype section: {section!r}")
        for entry in self.iter_entries(key):
            if entry.section.casefold() in IDE_ARCHETYPE_SECTIONS:
                yield IdeArchetype(entry)

    @property
    def archetypes(self) -> tuple[IdeArchetype, ...]:
        return tuple(self.iter_archetypes())

    @property
    def uv_animated_archetypes(self) -> tuple[IdeArchetype, ...]:
        return tuple(archetype for archetype in self.iter_archetypes() if archetype.has_uv_animation)

    def find_archetype(self, name: str) -> IdeArchetype | None:
        key = name.casefold()
        return next(
            (
                archetype
                for archetype in self.iter_archetypes()
                if archetype.name.casefold() == key
            ),
            None,
        )

    def add_section(self, name: str) -> None:
        key = name.strip().casefold()
        if not key or any(existing.casefold() == key for existing in self.section_names):
            raise ValueError(f"IDE section already exists or has an invalid name: {name!r}")
        if self.lines and not self.lines[-1].newline:
            self.lines[-1].newline = self.default_newline
        self.lines.extend([
            IdeLine(name.strip(), self.default_newline, "section", key),
            IdeLine("end", self.default_newline, "end", key),
        ])

    def add_entry(self, section: str, values: list[str] | tuple[str, ...]) -> IdeEntry:
        key = section.casefold()
        insert_at: int | None = None
        active = False
        for index, line in enumerate(self.lines):
            if isinstance(line, IdeLine) and line.kind == "section":
                active = line.section is not None and line.section.casefold() == key
            elif active and isinstance(line, IdeLine) and line.kind == "end":
                insert_at = index
                break
        if insert_at is None:
            self.add_section(section)
            insert_at = len(self.lines) - 1
        entry = IdeEntry(key, list(values), newline=self.default_newline)
        self.lines.insert(insert_at, entry)
        return entry

    def remove_entry(self, entry: IdeEntry) -> bool:
        try:
            self.lines.remove(entry)
        except ValueError:
            return False
        return True

    def to_text(self) -> str:
        return "".join(line.render() for line in self.lines)

    def to_bytes(self) -> bytes:
        prefix = b"\xef\xbb\xbf" if self.has_bom else b""
        return prefix + self.to_text().encode(self.encoding)

    def save(self, path: str | Path) -> None:
        atomic_write(path, self.to_bytes())


def load_ide(source: str | Path | bytes | BinaryIO, *, encoding: str = "utf-8") -> IdeDocument:
    if isinstance(source, (str, Path)):
        return IdeDocument.from_path(source, encoding=encoding)
    if isinstance(source, bytes):
        return IdeDocument.from_bytes(source, encoding=encoding)
    return IdeDocument.from_bytes(source.read(), encoding=encoding)


def create_ide(name: str = "definitions.ide") -> IdeDocument:
    return IdeDocument.empty(name)


__all__ = [
    "IDE_ARCHETYPE_SECTIONS",
    "IdeArchetype",
    "IdeArchetypeFlags",
    "IdeDocument",
    "IdeEntry",
    "IdeLine",
    "IdeLineKind",
    "create_ide",
    "load_ide",
]
