from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator

from ._utils import SECTOR_SIZE, align, atomic_write, normalize_key, safe_destination
from .crypto import GTAIVCrypto


IMG3_MAGIC = 0xA94E2A52
IMG3_VERSION = 3
IMG3_ENTRY_SIZE = 16


@dataclass(slots=True)
class ImgEntry:
    name: str
    size: int = 0
    resource_type: int = 1
    offset_sectors: int = 0
    used_blocks: int = 0
    padding: int = 0
    size_flags: int = 0
    table_value: int = 0
    _archive: "ImgArchive | None" = field(default=None, repr=False, compare=False)
    _data: bytes | None = field(default=None, repr=False, compare=False)
    _logical_size: int | None = field(default=None, repr=False, compare=False)

    @property
    def offset(self) -> int:
        return self.offset_sectors * SECTOR_SIZE

    @property
    def allocated_size(self) -> int:
        return self.used_blocks * SECTOR_SIZE

    @property
    def is_resource(self) -> bool:
        return bool(self.size_flags)

    def read(self) -> bytes:
        if self._archive is None:
            raise ValueError("detached IMG entry")
        return self._archive.read_entry(self)

    def read_raw(self) -> bytes:
        if self._archive is None:
            raise ValueError("detached IMG entry")
        return self._archive.read_entry_raw(self)


@dataclass(slots=True)
class ImgArchive:
    name: str = "archive.img"
    source_path: str = ""
    encrypted: bool = False
    reserved: int = 0xE9
    crypto: GTAIVCrypto | None = field(default=None, repr=False, compare=False)
    entries: list[ImgEntry] = field(default_factory=list)
    _source_bytes: bytes | None = field(default=None, repr=False, compare=False)
    _source_file: Path | None = field(default=None, repr=False, compare=False)
    _source_handle: BinaryIO | None = field(default=None, init=False, repr=False, compare=False)
    _index: dict[str, ImgEntry] = field(default_factory=dict, init=False, repr=False, compare=False)

    @classmethod
    def empty(cls, name: str = "archive.img") -> "ImgArchive":
        return cls(name=name if name.lower().endswith(".img") else f"{name}.img")

    @classmethod
    def from_path(cls, path: str | Path, *, crypto: GTAIVCrypto | None = None) -> "ImgArchive":
        source = Path(path)
        archive = cls(name=source.name, source_path=str(source), crypto=crypto)
        archive._source_file = source
        archive._parse()
        return archive

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "archive.img", crypto: GTAIVCrypto | None = None) -> "ImgArchive":
        archive = cls(name=name, crypto=crypto)
        archive._source_bytes = bytes(data)
        archive._parse()
        return archive

    @classmethod
    def from_folder(cls, path: str | Path, *, name: str = "archive.img", resource_type: int = 1) -> "ImgArchive":
        root = Path(path)
        archive = cls.empty(name)
        for item in sorted(root.iterdir()):
            if item.is_file():
                archive.add_file(item.name, item.read_bytes(), resource_type=resource_type)
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
        if len(header) != 20:
            raise ValueError("truncated IMG3 header")
        self.encrypted = struct.unpack_from("<I", header)[0] != IMG3_MAGIC
        prefix = header[:16]
        if self.encrypted:
            if self.crypto is None:
                self.crypto = GTAIVCrypto()
            prefix = self.crypto.decrypt(prefix)
        magic, version, count, table_size = struct.unpack("<4I", prefix)
        entry_size, self.reserved = struct.unpack_from("<2H", header, 16)
        if magic != IMG3_MAGIC or version != IMG3_VERSION:
            raise ValueError("invalid IMG3 archive")
        if entry_size != IMG3_ENTRY_SIZE:
            raise ValueError(f"unsupported IMG3 entry size: {entry_size}")
        entry_table_size = count * entry_size
        if table_size < entry_table_size:
            raise ValueError("IMG3 table is smaller than its entries")
        table = self._read_source(20, table_size)
        if len(table) != table_size:
            raise ValueError("truncated IMG3 table")
        if self.encrypted:
            assert self.crypto is not None
            table = self.crypto.decrypt(table)
        names_data = table[entry_table_size:]
        names: list[str] = []
        cursor = 0
        for _ in range(count):
            end = names_data.find(b"\0", cursor)
            if end < 0:
                raise ValueError("IMG3 names table is truncated")
            names.append(names_data[cursor:end].decode("utf-8", errors="replace"))
            cursor = end + 1
        self.entries.clear()
        for index, name in enumerate(names):
            raw_size, resource_type, offset_sectors, used_blocks, padding = struct.unpack_from("<IIIHH", table, index * entry_size)
            # Resource entries use the upper two bits as flags. They are not
            # part of the byte length (stock WAD/WBD/WBN entries set them).
            size = used_blocks * SECTOR_SIZE if raw_size & 0xC0000000 else raw_size
            size_flags = raw_size & 0xC0000000
            entry = ImgEntry(
                name=name,
                size=size,
                resource_type=resource_type,
                offset_sectors=offset_sectors,
                used_blocks=used_blocks,
                padding=padding,
                size_flags=size_flags,
                table_value=raw_size,
                _archive=self,
            )
            self.entries.append(entry)
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._index = {normalize_key(entry.name): entry for entry in self.entries}

    def __iter__(self) -> Iterator[ImgEntry]:
        return iter(self.entries)

    def find_entry(self, name: str | Path) -> ImgEntry | None:
        return self._index.get(normalize_key(name))

    def read_entry_raw(self, entry: ImgEntry) -> bytes:
        if entry._data is not None:
            return bytes(entry._data)
        return self._read_source(entry.offset, entry.size)

    def read_entry(self, entry: ImgEntry) -> bytes:
        if entry._data is not None:
            return bytes(entry._data)
        read_size = entry.size if entry._logical_size is None else entry._logical_size
        data = self._read_source(entry.offset, read_size)
        if len(data) != read_size:
            raise ValueError(f"truncated IMG3 entry: {entry.name}")
        if entry.is_resource and entry._logical_size is None:
            data = self._trim_resource(data)
            entry._logical_size = len(data)
        return data

    @staticmethod
    def _trim_resource(data: bytes) -> bytes:
        """Remove sector padding after an RSC5 resource's zlib stream."""
        if len(data) <= 12 or data[:4] != b"RSC\x05":
            return data
        payload = memoryview(data)[12:]
        try:
            inflater = zlib.decompressobj()
            cursor = 0
            while cursor < len(payload) and not inflater.eof:
                pending = payload[cursor : cursor + 64 * 1024]
                cursor += len(pending)
                while pending and not inflater.eof:
                    inflater.decompress(pending, 256 * 1024)
                    pending = inflater.unconsumed_tail
        except zlib.error:
            # Some empty resources consist solely of their 16-byte header.
            return data[:12] if not any(payload) else data
        if not inflater.eof:
            return data
        consumed = cursor - len(inflater.unused_data)
        return data[: 12 + consumed]

    def add_file(
        self,
        name: str,
        data: bytes,
        *,
        resource_type: int = 1,
        resource_flags: int = 0,
    ) -> ImgEntry:
        if not name or "/" in name or "\\" in name:
            raise ValueError("IMG3 entries use flat file names")
        key = normalize_key(name)
        entry = self._index.get(key)
        if entry is None:
            entry = ImgEntry(name=name, _archive=self)
            self.entries.append(entry)
        entry._data = bytes(data)
        entry.size = len(data)
        entry.resource_type = resource_type & 0xFFFFFFFF
        entry.size_flags = resource_flags & 0xC0000000
        entry.table_value = resource_flags & 0xFFFFFFFF if resource_flags else entry.size
        entry.used_blocks = align(entry.size) // SECTOR_SIZE
        entry.padding = 0
        entry._logical_size = entry.size
        self._index[key] = entry
        return entry

    def remove(self, name: str | Path) -> bool:
        entry = self.find_entry(name)
        if entry is None:
            return False
        self.entries.remove(entry)
        self._index.pop(normalize_key(entry.name), None)
        return True

    def to_bytes(self) -> bytes:
        payloads = [(entry, entry.read()) for entry in self.entries]
        names = b"".join(entry.name.encode("utf-8") + b"\0" for entry in self.entries)
        table_size = len(self.entries) * IMG3_ENTRY_SIZE + len(names)
        data_offset = align(20 + table_size)
        table = bytearray()
        for entry, payload in payloads:
            entry.size = len(payload)
            entry.offset_sectors = data_offset // SECTOR_SIZE
            entry.used_blocks = align(entry.size) // SECTOR_SIZE
            if not entry.is_resource:
                entry.padding = entry.allocated_size - entry.size
            entry._data = payload
            entry._logical_size = len(payload)
            first_dword = entry.table_value if entry.is_resource and entry.table_value else entry.size
            table.extend(struct.pack("<IIIHH", first_dword, entry.resource_type, entry.offset_sectors, entry.used_blocks, entry.padding))
            data_offset += entry.allocated_size
        table.extend(names)
        output = bytearray(struct.pack("<4I2H", IMG3_MAGIC, IMG3_VERSION, len(self.entries), table_size, IMG3_ENTRY_SIZE, self.reserved))
        output.extend(table)
        output.extend(b"\0" * (align(len(output)) - len(output)))
        for entry, payload in payloads:
            expected = entry.offset
            output.extend(b"\0" * (expected - len(output)))
            output.extend(payload)
            output.extend(b"\0" * (entry.allocated_size - len(payload)))
        self.encrypted = False
        return bytes(output)

    def save(self, path: str | Path) -> None:
        atomic_write(path, self.to_bytes())

    def extract(self, output_dir: str | Path) -> list[Path]:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for entry in self.entries:
            target = safe_destination(root, entry.name)
            target.write_bytes(entry.read())
            written.append(target)
        return written

    def close(self) -> None:
        if self._source_handle is not None:
            self._source_handle.close()
            self._source_handle = None

    def __enter__(self) -> "ImgArchive":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def load_img(source: str | Path | bytes | BinaryIO, *, crypto: GTAIVCrypto | None = None) -> ImgArchive:
    if isinstance(source, (str, Path)):
        return ImgArchive.from_path(source, crypto=crypto)
    if isinstance(source, bytes):
        return ImgArchive.from_bytes(source, crypto=crypto)
    return ImgArchive.from_bytes(source.read(), crypto=crypto)


def create_img(name: str = "archive.img") -> ImgArchive:
    return ImgArchive.empty(name)


__all__ = ["IMG3_ENTRY_SIZE", "IMG3_MAGIC", "IMG3_VERSION", "ImgArchive", "ImgEntry", "create_img", "load_img"]
