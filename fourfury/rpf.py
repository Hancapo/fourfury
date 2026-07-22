from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator

from ._utils import SECTOR_SIZE, align, decompress_deflate, normalize_key, normalize_path, safe_destination
from .crypto import GTAIVCrypto


RPF2_MAGIC = b"RPF2"
RPF3_MAGIC = b"RPF3"
RPF_HEADER_SIZE = SECTOR_SIZE
RPF_ENCRYPTED = 0xFFFFFFFF
_ENTRY_SIZE = 16


@dataclass(slots=True)
class RpfEntry:
    name: str = ""
    path: str = ""
    parent: "RpfDirectoryEntry | None" = field(default=None, repr=False)
    name_offset: int = 0
    name_hash: int | None = None
    _archive: "RpfArchive | None" = field(default=None, repr=False, compare=False)

    @property
    def is_directory(self) -> bool:
        return False

    @property
    def is_file(self) -> bool:
        return False


@dataclass(slots=True)
class RpfDirectoryEntry(RpfEntry):
    content_index: int = 0
    content_count: int = 0
    flags: int = 0
    children: list[RpfEntry] = field(default_factory=list)

    @property
    def is_directory(self) -> bool:
        return True

    @property
    def directories(self) -> list["RpfDirectoryEntry"]:
        return [item for item in self.children if isinstance(item, RpfDirectoryEntry)]

    @property
    def files(self) -> list["RpfFileEntry"]:
        return [item for item in self.children if isinstance(item, RpfFileEntry)]


@dataclass(slots=True)
class RpfFileEntry(RpfEntry):
    size: int = 0
    offset: int = 0
    resource_type: int = 0
    uncompressed_size: int = 0
    _data: bytes | None = field(default=None, repr=False, compare=False)

    @property
    def is_file(self) -> bool:
        return True

    @property
    def is_compressed(self) -> bool:
        return self.resource_type == 0 and bool(self.uncompressed_size and self.uncompressed_size != self.size)

    @property
    def resource_flags(self) -> int:
        return self.uncompressed_size if self.resource_type else 0

    def read_raw(self) -> bytes:
        if self._archive is None:
            raise ValueError("detached RPF entry")
        return self._archive.read_entry_raw(self)

    def read(self) -> bytes:
        if self._archive is None:
            raise ValueError("detached RPF entry")
        return self._archive.read_entry(self)


@dataclass(slots=True)
class RpfArchive:
    name: str = "archive.rpf"
    source_path: str = ""
    encrypted: bool = False
    unknown: int = 0
    version: int = 2
    crypto: GTAIVCrypto | None = field(default=None, repr=False, compare=False)
    root: RpfDirectoryEntry = field(default_factory=lambda: RpfDirectoryEntry(name="", path="", flags=1))
    _source_bytes: bytes | None = field(default=None, repr=False, compare=False)
    _source_file: Path | None = field(default=None, repr=False, compare=False)
    _source_handle: BinaryIO | None = field(default=None, init=False, repr=False, compare=False)
    _index: dict[str, RpfEntry] = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.root._archive = self

    @classmethod
    def empty(cls, name: str = "archive.rpf", *, crypto: GTAIVCrypto | None = None) -> "RpfArchive":
        return cls(name=name if name.lower().endswith(".rpf") else f"{name}.rpf", crypto=crypto)

    @classmethod
    def from_path(cls, path: str | Path, *, crypto: GTAIVCrypto | None = None) -> "RpfArchive":
        source = Path(path)
        archive = cls(name=source.name, source_path=str(source), crypto=crypto)
        archive._source_file = source
        archive._parse()
        return archive

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "archive.rpf", crypto: GTAIVCrypto | None = None) -> "RpfArchive":
        archive = cls(name=name, crypto=crypto)
        archive._source_bytes = bytes(data)
        archive._parse()
        return archive

    @classmethod
    def from_folder(cls, path: str | Path, *, name: str = "archive.rpf") -> "RpfArchive":
        root = Path(path)
        archive = cls.empty(name)
        for item in sorted(root.rglob("*")):
            relative = item.relative_to(root).as_posix()
            if item.is_dir():
                archive.add_directory(relative)
            elif item.is_file():
                archive.add_file(relative, item.read_bytes())
        return archive

    def _read_source(self, offset: int, size: int) -> bytes:
        if self._source_bytes is not None:
            return self._source_bytes[offset : offset + size]
        if self._source_file is None:
            raise ValueError("archive has no readable source")
        if self._source_handle is None or self._source_handle.closed:
            self._source_handle = self._source_file.open("rb")
        self._source_handle.seek(offset)
        return self._source_handle.read(size)

    def _parse(self) -> None:
        header = self._read_source(0, 20)
        if len(header) != 20 or header[:4] not in (RPF2_MAGIC, RPF3_MAGIC):
            raise ValueError("invalid GTA IV RPF archive")
        self.version = 2 if header[:4] == RPF2_MAGIC else 3
        toc_size, entry_count, self.unknown, encryption = struct.unpack_from("<4I", header, 4)
        if toc_size < entry_count * _ENTRY_SIZE:
            raise ValueError("RPF table size is smaller than its entry table")
        self.encrypted = encryption != 0
        toc = self._read_source(RPF_HEADER_SIZE, toc_size)
        if len(toc) != toc_size:
            raise ValueError("truncated RPF table")
        if self.encrypted:
            if self.crypto is None:
                raise ValueError("encrypted RPF archive requires GTAIVCrypto")
            toc = self.crypto.decrypt(toc)

        names = toc[entry_count * _ENTRY_SIZE :]

        def name_at(offset: int) -> str:
            if offset >= len(names):
                return ""
            end = names.find(b"\0", offset)
            if end < 0:
                end = len(names)
            return names[offset:end].decode("utf-8", errors="replace")

        entries: list[RpfEntry] = []
        for index in range(entry_count):
            blob = toc[index * _ENTRY_SIZE : (index + 1) * _ENTRY_SIZE]
            name_offset, second, third, fourth = struct.unpack("<4I", blob)
            name = name_at(name_offset) if self.version == 2 else f"{name_offset:08x}"
            if third & 0x80000000:
                entry = RpfDirectoryEntry(
                    name=name,
                    name_offset=name_offset,
                    name_hash=name_offset if self.version == 3 else None,
                    flags=second,
                    content_index=third & 0x7FFFFFFF,
                    content_count=fourth & 0x3FFFFFFF,
                )
            else:
                entry = RpfFileEntry(
                    name=name,
                    name_offset=name_offset,
                    name_hash=name_offset if self.version == 3 else None,
                    size=second,
                    # RPF2 stores the resource byte in the low byte and a
                    # naturally 256-byte-aligned file offset above it.
                    offset=third & 0xFFFFFF00,
                    resource_type=third & 0xFF,
                    uncompressed_size=fourth,
                )
            entry._archive = self
            entries.append(entry)
        if not entries or not isinstance(entries[0], RpfDirectoryEntry):
            raise ValueError("RPF root entry is missing")
        self.root = entries[0]
        self.root.name = ""
        self.root.path = ""

        visiting: set[int] = set()

        def attach(directory: RpfDirectoryEntry) -> None:
            identity = id(directory)
            if identity in visiting:
                raise ValueError("cyclic RPF directory table")
            visiting.add(identity)
            start = directory.content_index
            end = start + directory.content_count
            if end > len(entries):
                raise ValueError("RPF directory points outside the entry table")
            directory.children.clear()
            for child in entries[start:end]:
                child.parent = directory
                child.path = f"{directory.path}/{child.name}".strip("/")
                directory.children.append(child)
                if isinstance(child, RpfDirectoryEntry):
                    attach(child)
            visiting.remove(identity)

        attach(self.root)
        self._rebuild_index()

    def close(self) -> None:
        if self._source_handle is not None:
            self._source_handle.close()
            self._source_handle = None

    def __enter__(self) -> "RpfArchive":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _rebuild_index(self) -> None:
        self._index = {normalize_key(entry.path): entry for entry in self.iter_entries()}

    def iter_entries(self, *, include_directories: bool = True) -> Iterator[RpfEntry]:
        def walk(directory: RpfDirectoryEntry) -> Iterator[RpfEntry]:
            for child in directory.children:
                if include_directories or isinstance(child, RpfFileEntry):
                    yield child
                if isinstance(child, RpfDirectoryEntry):
                    yield from walk(child)
        yield from walk(self.root)

    def find_entry(self, path: str | Path) -> RpfEntry | None:
        return self._index.get(normalize_key(path))

    def read_entry_raw(self, entry: RpfFileEntry) -> bytes:
        if entry._data is not None:
            return bytes(entry._data)
        return self._read_source(entry.offset, entry.size)

    def read_entry(self, entry: RpfFileEntry) -> bytes:
        data = self.read_entry_raw(entry)
        # Resource entries carry an RSC5 container and are not encrypted with
        # the archive key. Ordinary files in encrypted stock archives are.
        if self.version == 2 and self.encrypted and entry.resource_type == 0:
            assert self.crypto is not None
            data = self.crypto.decrypt(data)
        if entry.resource_type == 0 and entry.is_compressed:
            data = decompress_deflate(data)
            if entry.uncompressed_size and len(data) != entry.uncompressed_size:
                raise ValueError(f"decompressed size mismatch for {entry.path}")
        return data

    def add_directory(self, path: str | Path) -> RpfDirectoryEntry:
        current = self.root
        current_path = ""
        for part in normalize_path(path).split("/") if normalize_path(path) else []:
            current_path = f"{current_path}/{part}".strip("/")
            child = next((item for item in current.children if isinstance(item, RpfDirectoryEntry) and item.name.casefold() == part.casefold()), None)
            if child is None:
                child = RpfDirectoryEntry(name=part, path=current_path, parent=current, _archive=self)
                current.children.append(child)
            current = child
        self._rebuild_index()
        return current

    def add_file(self, path: str | Path, data: bytes, *, resource_type: int = 0) -> RpfFileEntry:
        normalized = normalize_path(path)
        if not normalized:
            raise ValueError("file path cannot be empty")
        parts = normalized.split("/")
        parent = self.add_directory("/".join(parts[:-1]))
        existing = next((item for item in parent.children if item.name.casefold() == parts[-1].casefold()), None)
        if isinstance(existing, RpfDirectoryEntry):
            raise IsADirectoryError(normalized)
        if isinstance(existing, RpfFileEntry):
            entry = existing
            entry.resource_type = resource_type
        else:
            entry = RpfFileEntry(name=parts[-1], path=normalized, parent=parent, resource_type=resource_type, _archive=self)
            parent.children.append(entry)
        entry._data = bytes(data)
        entry.size = len(data)
        if resource_type and len(data) >= 12 and data[:4] == b"RSC\x05":
            entry.uncompressed_size = struct.unpack_from("<I", data, 8)[0]
        else:
            entry.uncompressed_size = len(data)
        self._rebuild_index()
        return entry

    def _flatten_for_write(self) -> list[RpfEntry]:
        entries: list[RpfEntry] = [self.root]
        pending: list[RpfDirectoryEntry] = [self.root]
        while pending:
            directory = pending.pop(0)
            directory.content_index = len(entries)
            directory.content_count = len(directory.children)
            entries.extend(directory.children)
            pending.extend(child for child in directory.children if isinstance(child, RpfDirectoryEntry))
        return entries

    def to_bytes(self) -> bytes:
        if self.version != 2:
            raise NotImplementedError("writing RPF3 audio archives is not supported yet")
        entries = self._flatten_for_write()
        # Stock RPF2 archives name the root entry "/". The public object
        # model still exposes it as an empty path.
        names = bytearray(b"/\0")
        for index, entry in enumerate(entries):
            if index == 0:
                entry.name_offset = 0
                continue
            entry.name_offset = len(names)
            names.extend(entry.name.encode("utf-8") + b"\0")
        toc_size = align(len(entries) * _ENTRY_SIZE + len(names))
        data_offset = RPF_HEADER_SIZE + toc_size
        payloads: list[tuple[RpfFileEntry, bytes]] = []
        for entry in entries:
            if isinstance(entry, RpfFileEntry):
                payload = entry.read() if entry._data is None else bytes(entry._data)
                data_offset = align(data_offset)
                entry.offset = data_offset
                entry.size = len(payload)
                if entry.resource_type == 0:
                    entry.uncompressed_size = len(payload)
                entry._data = payload
                payloads.append((entry, payload))
                data_offset += align(len(payload))
        table = bytearray()
        for index, entry in enumerate(entries):
            if isinstance(entry, RpfDirectoryEntry):
                flags = 1 if index == 0 else entry.flags
                table.extend(struct.pack("<4I", entry.name_offset, flags, 0x80000000 | entry.content_index, entry.content_count))
            else:
                if entry.offset > 0xFFFFFF00 or entry.offset & 0xFF:
                    raise ValueError("RPF2 file offset does not fit its aligned 24-bit field")
                encoded_offset = entry.offset | (entry.resource_type & 0xFF)
                table.extend(struct.pack("<4I", entry.name_offset, entry.size, encoded_offset, entry.uncompressed_size))
        table.extend(names)
        table.extend(b"\0" * (toc_size - len(table)))
        output = bytearray(struct.pack("<4s4I", RPF2_MAGIC, toc_size, len(entries), self.unknown, 0))
        output.extend(b"\0" * (RPF_HEADER_SIZE - len(output)))
        output.extend(table)
        for entry, payload in payloads:
            output.extend(b"\0" * (entry.offset - len(output)))
            output.extend(payload)
            output.extend(b"\0" * (align(len(output)) - len(output)))
        self.encrypted = False
        return bytes(output)

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

    def extract(self, output_dir: str | Path) -> list[Path]:
        root = Path(output_dir)
        written: list[Path] = []
        for entry in self.iter_entries():
            target = safe_destination(root, entry.path)
            if isinstance(entry, RpfDirectoryEntry):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(entry.read())
                written.append(target)
        return written


def load_rpf(source: str | Path | bytes | BinaryIO, *, crypto: GTAIVCrypto | None = None) -> RpfArchive:
    if isinstance(source, (str, Path)):
        return RpfArchive.from_path(source, crypto=crypto)
    if isinstance(source, bytes):
        return RpfArchive.from_bytes(source, crypto=crypto)
    return RpfArchive.from_bytes(source.read(), crypto=crypto)


def create_rpf(name: str = "archive.rpf") -> RpfArchive:
    return RpfArchive.empty(name)


__all__ = [
    "RPF2_MAGIC", "RPF3_MAGIC", "RPF_HEADER_SIZE", "RPF_ENCRYPTED", "RpfArchive",
    "RpfDirectoryEntry", "RpfEntry", "RpfFileEntry", "create_rpf", "load_rpf",
]
