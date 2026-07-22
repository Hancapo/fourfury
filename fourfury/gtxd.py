from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterable

from .ide import IdeDocument, IdeEntry


GTXD_SECTION = "txdp"


@dataclass(slots=True)
class GtxdDependency:
    """A child-to-parent texture dictionary relationship from an IDE ``txdp`` section."""

    child: str
    parent: str
    line_number: int | None = None
    _entry: IdeEntry | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_entry(cls, entry: IdeEntry) -> "GtxdDependency":
        if len(entry.values) < 2:
            raise ValueError(f"GTXD dependency on line {entry.line_number} requires child and parent names")
        return cls(entry.values[0].strip(), entry.values[1].strip(), entry.line_number, entry)

    def sync(self) -> None:
        if not self.child.strip() or not self.parent.strip():
            raise ValueError("GTXD child and parent names cannot be empty")
        if self._entry is not None:
            self._entry.values[:2] = [self.child, self.parent]


@dataclass(slots=True)
class GtxdHierarchy:
    """Resolved GTA IV texture dictionary parent relationships."""

    parents: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_documents(
        cls, documents: Iterable["GtxdDocument | IdeDocument"]
    ) -> "GtxdHierarchy":
        hierarchy = cls()
        for document in documents:
            typed = document if isinstance(document, GtxdDocument) else GtxdDocument.from_ide(document)
            for dependency in typed.dependencies:
                hierarchy.add(dependency.child, dependency.parent)
        return hierarchy

    @classmethod
    def from_paths(cls, paths: Iterable[str | Path]) -> "GtxdHierarchy":
        return cls.from_documents(GtxdDocument.from_path(path) for path in paths)

    @classmethod
    def from_game(cls, game: str | Path) -> "GtxdHierarchy":
        """Load base-game ``txdp`` relationships from common and map IDE files."""

        root = Path(game)
        paths = sorted((root / "common" / "data").glob("*.ide"))
        paths.extend(sorted((root / "pc" / "data" / "maps").rglob("*.ide")))
        return cls.from_paths(paths)

    def add(self, child: str, parent: str) -> None:
        child_key = child.strip().casefold()
        parent_key = parent.strip().casefold()
        if not child_key or not parent_key:
            raise ValueError("GTXD child and parent names cannot be empty")
        self.parents[child_key] = parent_key

    def parent_of(self, child: str) -> str | None:
        return self.parents.get(child.strip().casefold())

    def chain(self, texture_dictionary: str, *, include_self: bool = True) -> tuple[str, ...]:
        """Return the dictionary followed by all of its parents.

        Cycles are rejected rather than silently producing an incomplete lookup order.
        """

        current = texture_dictionary.strip().casefold()
        if not current:
            return ()
        result: list[str] = [current] if include_self else []
        visited = {current}
        while (parent := self.parents.get(current)) is not None:
            if parent in visited:
                cycle = " -> ".join((*result, parent))
                raise ValueError(f"cyclic GTXD hierarchy: {cycle}")
            result.append(parent)
            visited.add(parent)
            current = parent
        return tuple(result)


@dataclass(slots=True)
class GtxdDocument:
    """Lossless typed view of the ``txdp`` section used by ``gtxd.ide`` and map IDEs."""

    ide: IdeDocument
    dependencies: list[GtxdDependency] = field(default_factory=list)

    @classmethod
    def empty(cls, name: str = "gtxd.ide", *, newline: str = "\r\n") -> "GtxdDocument":
        ide = IdeDocument.empty(name, newline=newline)
        ide.add_section(GTXD_SECTION)
        return cls(ide)

    @classmethod
    def from_ide(cls, ide: IdeDocument) -> "GtxdDocument":
        dependencies = [GtxdDependency.from_entry(entry) for entry in ide.iter_entries(GTXD_SECTION)]
        return cls(ide, dependencies)

    @classmethod
    def from_path(cls, path: str | Path, *, encoding: str = "utf-8") -> "GtxdDocument":
        return cls.from_ide(IdeDocument.from_path(path, encoding=encoding))

    @classmethod
    def from_bytes(
        cls, data: bytes, *, name: str = "gtxd.ide", encoding: str = "utf-8"
    ) -> "GtxdDocument":
        return cls.from_ide(IdeDocument.from_bytes(data, name=name, encoding=encoding))

    @classmethod
    def from_text(
        cls, text: str, *, name: str = "gtxd.ide", encoding: str = "utf-8"
    ) -> "GtxdDocument":
        return cls.from_ide(IdeDocument.from_text(text, name=name, encoding=encoding))

    @property
    def name(self) -> str:
        return self.ide.name

    @property
    def source_path(self) -> str:
        return self.ide.source_path

    @property
    def hierarchy(self) -> GtxdHierarchy:
        return GtxdHierarchy.from_documents((self,))

    def parent_of(self, child: str) -> str | None:
        return self.hierarchy.parent_of(child)

    def chain(self, texture_dictionary: str, *, include_self: bool = True) -> tuple[str, ...]:
        return self.hierarchy.chain(texture_dictionary, include_self=include_self)

    def add_dependency(self, child: str, parent: str) -> GtxdDependency:
        entry = self.ide.add_entry(GTXD_SECTION, [child, parent])
        dependency = GtxdDependency(child, parent, entry.line_number, entry)
        dependency.sync()
        self.dependencies.append(dependency)
        return dependency

    def remove_dependency(self, dependency: GtxdDependency) -> bool:
        try:
            self.dependencies.remove(dependency)
        except ValueError:
            return False
        if dependency._entry is not None:
            self.ide.remove_entry(dependency._entry)
        return True

    def to_text(self) -> str:
        for dependency in self.dependencies:
            dependency.sync()
        return self.ide.to_text()

    def to_bytes(self) -> bytes:
        for dependency in self.dependencies:
            dependency.sync()
        return self.ide.to_bytes()

    def save(self, path: str | Path) -> None:
        for dependency in self.dependencies:
            dependency.sync()
        self.ide.save(path)


def load_gtxd(
    source: str | Path | bytes | BinaryIO, *, encoding: str = "utf-8"
) -> GtxdDocument:
    if isinstance(source, bytes):
        return GtxdDocument.from_bytes(source, encoding=encoding)
    if isinstance(source, (str, Path)):
        return GtxdDocument.from_path(source, encoding=encoding)
    return GtxdDocument.from_bytes(source.read(), encoding=encoding)


def create_gtxd(name: str = "gtxd.ide") -> GtxdDocument:
    return GtxdDocument.empty(name)


__all__ = [
    "GTXD_SECTION", "GtxdDependency", "GtxdDocument", "GtxdHierarchy", "create_gtxd",
    "load_gtxd",
]
