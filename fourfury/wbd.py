from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator

from ._utils import atomic_write
from .rsc import RSC5_VIRTUAL_BASE, Rsc5Resource, rsc5_pointer_offset
from .wbn import WbnBound, WbnGeometry, _WbnParser, _iter_bounds, _iter_geometries


WBD_RESOURCE_VERSION = 0x20
WBD_DICTIONARY_SIZE = 0x20


def joaat(value: str | bytes) -> int:
    """Return GTA IV's lowercase Jenkins one-at-a-time hash."""

    data = value.lower().encode("utf-8") if isinstance(value, str) else value.lower()
    result = 0
    for item in data:
        result = (result + item) & 0xFFFFFFFF
        result = (result + (result << 10)) & 0xFFFFFFFF
        result ^= result >> 6
    result = (result + (result << 3)) & 0xFFFFFFFF
    result ^= result >> 11
    result = (result + (result << 15)) & 0xFFFFFFFF
    return result


@dataclass(slots=True)
class WbdEntry:
    name_hash: int
    bound: WbnBound

    @property
    def hash_hex(self) -> str:
        return f"{self.name_hash:08x}"


@dataclass(slots=True)
class WbdDocument:
    entries: list[WbdEntry]
    resource: Rsc5Resource
    parent_dictionary: int = 0
    usage_count: int = 1
    name: str = "bounds.wbd"
    source_path: str = ""
    _hashes_offset: int = field(default=0, repr=False, compare=False)
    _bounds_offset: int = field(default=0, repr=False, compare=False)
    _entry_count: int = field(default=0, repr=False, compare=False)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
    ) -> "WbdDocument":
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name)
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        name: str = "bounds.wbd",
    ) -> "WbdDocument":
        resource = Rsc5Resource.from_bytes(data)
        if resource.version != WBD_RESOURCE_VERSION:
            raise ValueError(f"unsupported WBD resource version: {resource.version:#x}")
        if resource.physical_data:
            raise ValueError("WBD resources with physical allocations are not supported")
        virtual = resource.virtual_data
        if len(virtual) < WBD_DICTIONARY_SIZE:
            raise ValueError("truncated WBD bounds dictionary")

        parent_dictionary, usage_count = struct.unpack_from("<2I", virtual, 8)
        hashes_pointer, hash_count, hash_capacity = struct.unpack_from("<IHH", virtual, 16)
        bounds_pointer, bound_count, bound_capacity = struct.unpack_from("<IHH", virtual, 24)
        if hash_count > hash_capacity:
            raise ValueError("WBD hash count exceeds its capacity")
        if bound_count > bound_capacity:
            raise ValueError("WBD bound count exceeds its capacity")
        if hash_count != bound_count:
            raise ValueError("WBD hash and bound counts do not match")

        if hash_count:
            hashes_offset = rsc5_pointer_offset(hashes_pointer)
            bounds_offset = rsc5_pointer_offset(bounds_pointer)
            if hashes_offset + hash_count * 4 > len(virtual):
                raise ValueError("WBD hash array exceeds the virtual allocation")
            if bounds_offset + bound_count * 4 > len(virtual):
                raise ValueError("WBD bound pointer array exceeds the virtual allocation")
            hashes = struct.unpack_from(f"<{hash_count}I", virtual, hashes_offset)
            bound_pointers = struct.unpack_from(f"<{bound_count}I", virtual, bounds_offset)
        else:
            hashes_offset = 0
            bounds_offset = 0
            hashes = ()
            bound_pointers = ()

        parser = _WbnParser(virtual)
        entries = [
            WbdEntry(int(name_hash), parser.parse_bound(rsc5_pointer_offset(bound_pointer)))
            for name_hash, bound_pointer in zip(hashes, bound_pointers, strict=True)
        ]
        return cls(
            entries,
            resource,
            parent_dictionary,
            usage_count,
            name,
            _hashes_offset=hashes_offset,
            _bounds_offset=bounds_offset,
            _entry_count=bound_count,
        )

    @classmethod
    def hashes_from_bytes(cls, data: bytes) -> tuple[int, ...]:
        """Read only dictionary hashes without constructing any collision bounds."""
        resource = Rsc5Resource.from_bytes(data)
        if resource.version != WBD_RESOURCE_VERSION:
            raise ValueError(f"unsupported WBD resource version: {resource.version:#x}")
        if resource.physical_data:
            raise ValueError("WBD resources with physical allocations are not supported")
        virtual = resource.virtual_data
        if len(virtual) < WBD_DICTIONARY_SIZE:
            raise ValueError("truncated WBD bounds dictionary")

        hashes_pointer, hash_count, hash_capacity = struct.unpack_from(
            "<IHH", virtual, 16
        )
        _bounds_pointer, bound_count, bound_capacity = struct.unpack_from(
            "<IHH", virtual, 24
        )
        if hash_count > hash_capacity:
            raise ValueError("WBD hash count exceeds its capacity")
        if bound_count > bound_capacity:
            raise ValueError("WBD bound count exceeds its capacity")
        if hash_count != bound_count:
            raise ValueError("WBD hash and bound counts do not match")
        if not hash_count:
            return ()
        hashes_offset = rsc5_pointer_offset(hashes_pointer)
        if hashes_offset + hash_count * 4 > len(virtual):
            raise ValueError("WBD hash array exceeds the virtual allocation")
        return tuple(
            int(value)
            for value in struct.unpack_from(
                f"<{hash_count}I",
                virtual,
                hashes_offset,
            )
        )

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[WbdEntry]:
        return iter(self.entries)

    @property
    def hashes(self) -> tuple[int, ...]:
        return tuple(entry.name_hash for entry in self.entries)

    @property
    def bounds(self) -> tuple[WbnBound, ...]:
        return tuple(entry.bound for entry in self.entries)

    def find_entry(self, name_or_hash: str | bytes | int) -> WbdEntry | None:
        target = name_or_hash if isinstance(name_or_hash, int) else joaat(name_or_hash)
        return next((entry for entry in self.entries if entry.name_hash == target), None)

    def find_bound(self, name_or_hash: str | bytes | int) -> WbnBound | None:
        entry = self.find_entry(name_or_hash)
        return None if entry is None else entry.bound

    def iter_bounds(self) -> Iterator[WbnBound]:
        yield from _iter_bounds(entry.bound for entry in self.entries)

    @property
    def geometries(self) -> list[WbnGeometry]:
        return list(_iter_geometries(self.iter_bounds()))

    def to_bytes(self) -> bytes:
        if len(self.entries) != self._entry_count:
            raise ValueError("WBD editing cannot change the bounds dictionary entry count")
        if not 0 <= self.parent_dictionary <= 0xFFFFFFFF:
            raise ValueError("WBD parent dictionary hash must fit in 32 bits")
        if not 0 <= self.usage_count <= 0xFFFFFFFF:
            raise ValueError("WBD usage count must fit in 32 bits")

        virtual = bytearray(self.resource.virtual_data)
        struct.pack_into("<2I", virtual, 8, self.parent_dictionary, self.usage_count)
        visited: set[int] = set()
        for index, entry in enumerate(self.entries):
            if not 0 <= entry.name_hash <= 0xFFFFFFFF:
                raise ValueError("WBD entry hashes must fit in 32 bits")
            struct.pack_into("<I", virtual, self._hashes_offset + index * 4, entry.name_hash)
            struct.pack_into(
                "<I",
                virtual,
                self._bounds_offset + index * 4,
                RSC5_VIRTUAL_BASE | entry.bound._offset,
            )
            entry.bound._write(virtual, visited)
        return self.resource.to_bytes(virtual_data=bytes(virtual))

    def save(self, path: str | Path) -> None:
        atomic_write(path, self.to_bytes())


def load_wbd(
    source: str | Path | bytes | BinaryIO,
) -> WbdDocument:
    if isinstance(source, (str, Path)):
        return WbdDocument.from_path(source)
    if isinstance(source, bytes):
        return WbdDocument.from_bytes(source)
    return WbdDocument.from_bytes(source.read())


__all__ = [
    "WBD_DICTIONARY_SIZE", "WBD_RESOURCE_VERSION", "WbdDocument", "WbdEntry", "joaat",
    "load_wbd",
]
