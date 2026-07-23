from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator

from ._utils import atomic_write
from .model import ModelAsset
from .rsc import Rsc5Resource
from .wbd import joaat
from .wdr import (
    WDR_RESOURCE_VERSION,
    WdrDocument,
    WdrDrawable,
    WdrShader,
    _WdrReader,
)
from .wtd import Rsc5Texture, Rsc5TextureDictionary


WDD_RESOURCE_VERSION = WDR_RESOURCE_VERSION
WDD_DICTIONARY_SIZE = 0x20


@dataclass(frozen=True, slots=True)
class WddEntry:
    name_hash: int
    drawable: WdrDrawable
    pointer: int = field(repr=False, compare=False)

    @property
    def hash_hex(self) -> str:
        return f"{self.name_hash:08x}"

    @property
    def shaders(self) -> tuple[WdrShader, ...]:
        group = self.drawable.shader_group
        return () if group is None else group.shaders

    @property
    def embedded_texture_dictionary(self) -> Rsc5TextureDictionary | None:
        group = self.drawable.shader_group
        return None if group is None else group.texture_dictionary

    @property
    def embedded_textures(self) -> tuple[Rsc5Texture, ...]:
        dictionary = self.embedded_texture_dictionary
        return () if dictionary is None else dictionary.textures

    def find_embedded_texture(self, name: str) -> Rsc5Texture | None:
        dictionary = self.embedded_texture_dictionary
        return None if dictionary is None else dictionary.get(name)


@dataclass(slots=True)
class WddDocument:
    entries: tuple[WddEntry, ...]
    resource: Rsc5Resource
    parent_dictionary_hash: int = 0
    usage_count: int = 1
    name: str = "drawables.wdd"
    source_path: str = ""
    _entries_by_hash: dict[int, WddEntry] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        self._entries_by_hash = {entry.name_hash: entry for entry in self.entries}
        if len(self._entries_by_hash) != len(self.entries):
            raise ValueError("WDD contains duplicate drawable hashes")

    @classmethod
    def from_path(cls, path: str | Path) -> WddDocument:
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name)
        document.source_path = str(source)
        return document

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "drawables.wdd") -> WddDocument:
        resource = Rsc5Resource.from_bytes(data)
        if resource.version != WDD_RESOURCE_VERSION:
            raise ValueError(f"unsupported WDD resource version: {resource.version:#x}")
        if len(resource.virtual_data) < WDD_DICTIONARY_SIZE:
            raise ValueError("truncated WDD drawable dictionary")

        parent_hash, usage_count = struct.unpack_from("<2I", resource.virtual_data, 8)
        hashes_pointer, hash_count, hash_capacity = struct.unpack_from(
            "<IHH", resource.virtual_data, 0x10
        )
        drawables_pointer, drawable_count, drawable_capacity = struct.unpack_from(
            "<IHH", resource.virtual_data, 0x18
        )
        if hash_count > hash_capacity:
            raise ValueError("WDD hash count exceeds its capacity")
        if drawable_count > drawable_capacity:
            raise ValueError("WDD drawable count exceeds its capacity")
        if hash_count != drawable_count:
            raise ValueError("WDD hash and drawable counts do not match")

        reader = _WdrReader(resource)
        if hash_count:
            hashes = struct.unpack(
                f"<{hash_count}I",
                reader.read(hashes_pointer, hash_count * 4, "WDD hash array"),
            )
            drawable_pointers = struct.unpack(
                f"<{drawable_count}I",
                reader.read(
                    drawables_pointer,
                    drawable_count * 4,
                    "WDD drawable pointer array",
                ),
            )
        else:
            hashes = ()
            drawable_pointers = ()

        entries: list[WddEntry] = []
        seen_hashes: set[int] = set()
        for name_hash, pointer in zip(hashes, drawable_pointers, strict=True):
            if name_hash in seen_hashes:
                raise ValueError(f"WDD contains duplicate drawable hash: {name_hash:08x}")
            if pointer == 0:
                raise ValueError(f"WDD drawable {name_hash:08x} has a null pointer")
            seen_hashes.add(name_hash)
            entries.append(WddEntry(name_hash, reader.parse_drawable(pointer), pointer))
        return cls(tuple(entries), resource, parent_hash, usage_count, name)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[WddEntry]:
        return iter(self.entries)

    def __getitem__(self, name_or_hash: str | bytes | int) -> WddEntry:
        entry = self.find_entry(name_or_hash)
        if entry is None:
            raise KeyError(name_or_hash)
        return entry

    @property
    def hashes(self) -> tuple[int, ...]:
        return tuple(entry.name_hash for entry in self.entries)

    @property
    def drawables(self) -> tuple[WdrDrawable, ...]:
        return tuple(entry.drawable for entry in self.entries)

    def find_entry(self, name_or_hash: str | bytes | int) -> WddEntry | None:
        target = name_or_hash if isinstance(name_or_hash, int) else joaat(name_or_hash)
        return self._entries_by_hash.get(target)

    def find_drawable(self, name_or_hash: str | bytes | int) -> WdrDrawable | None:
        entry = self.find_entry(name_or_hash)
        return None if entry is None else entry.drawable

    def to_model(self, name_or_hash: str | bytes | int) -> ModelAsset:
        entry = self[name_or_hash]
        if isinstance(name_or_hash, str):
            model_name = name_or_hash
        elif isinstance(name_or_hash, bytes):
            model_name = name_or_hash.decode("utf-8", errors="replace")
        else:
            model_name = entry.hash_hex
        document = WdrDocument(
            entry.drawable,
            self.resource,
            f"{model_name}.wdr",
            self.source_path,
        )
        return document.to_model()

    def to_models(self) -> tuple[ModelAsset, ...]:
        return tuple(self.to_model(entry.name_hash) for entry in self.entries)

    def to_bytes(self) -> bytes:
        """Return the original lossless RSC5 resource."""

        return self.resource.to_bytes()

    def save(self, path: str | Path) -> None:
        atomic_write(path, self.to_bytes())


def load_wdd(source: str | Path | bytes | BinaryIO) -> WddDocument:
    if isinstance(source, (str, Path)):
        return WddDocument.from_path(source)
    if isinstance(source, bytes):
        return WddDocument.from_bytes(source)
    return WddDocument.from_bytes(source.read())


__all__ = [
    "WDD_DICTIONARY_SIZE",
    "WDD_RESOURCE_VERSION",
    "WddDocument",
    "WddEntry",
    "load_wdd",
]
