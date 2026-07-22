from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator, Literal


IdeLineKind = Literal["blank", "comment", "section", "end", "raw"]


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


def load_ide(source: str | Path | bytes | BinaryIO, *, encoding: str = "utf-8") -> IdeDocument:
    if isinstance(source, (str, Path)):
        return IdeDocument.from_path(source, encoding=encoding)
    if isinstance(source, bytes):
        return IdeDocument.from_bytes(source, encoding=encoding)
    return IdeDocument.from_bytes(source.read(), encoding=encoding)


def create_ide(name: str = "definitions.ide") -> IdeDocument:
    return IdeDocument.empty(name)


__all__ = ["IdeDocument", "IdeEntry", "IdeLine", "IdeLineKind", "create_ide", "load_ide"]
