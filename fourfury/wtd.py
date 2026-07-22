from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import BinaryIO

from ._utils import atomic_write
from .rsc import RSC5_PHYSICAL_BASE, RSC5_VIRTUAL_BASE, Rsc5Resource, rsc5_pointer_offset


WTD_RESOURCE_VERSION = 0x08
RSC5_TEXTURE_DICTIONARY_SIZE = 0x20
RSC5_TEXTURE_SIZE = 0x50


class Rsc5TextureFormat(IntEnum):
    DXT1 = 0x31545844
    DXT3 = 0x33545844
    DXT5 = 0x35545844
    A8R8G8B8 = 21
    L8 = 50


def _mip_size(width: int, height: int, texture_format: Rsc5TextureFormat | int) -> int:
    if texture_format == Rsc5TextureFormat.DXT1:
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 8
    if texture_format in (Rsc5TextureFormat.DXT3, Rsc5TextureFormat.DXT5):
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 16
    if texture_format == Rsc5TextureFormat.A8R8G8B8:
        return width * height * 4
    if texture_format == Rsc5TextureFormat.L8:
        return width * height
    raise ValueError(f"unsupported RSC5 texture format: {int(texture_format):#x}")


def _mip_sizes(
    width: int, height: int, texture_format: Rsc5TextureFormat | int, mip_levels: int
) -> tuple[int, ...]:
    sizes: list[int] = []
    for _ in range(mip_levels):
        sizes.append(_mip_size(width, height, texture_format))
        width = max(1, width // 2)
        height = max(1, height // 2)
    return tuple(sizes)


@dataclass(frozen=True, slots=True)
class Rsc5Texture:
    file_name: str
    name: str
    width: int
    height: int
    format: Rsc5TextureFormat | int
    stride: int
    texture_type: int
    mip_levels: int
    data: bytes = field(repr=False)
    mip_sizes: tuple[int, ...]
    _pointer: int = field(repr=False, compare=False)
    _data_pointer: int = field(repr=False, compare=False)

    @property
    def format_name(self) -> str:
        return self.format.name if isinstance(self.format, Rsc5TextureFormat) else f"unknown_{self.format:08x}"

    @property
    def is_cube(self) -> bool:
        return self.texture_type == 1

    def to_dds_bytes(self) -> bytes:
        """Return the stored mip chain wrapped in a standard DDS header."""

        header = bytearray(128)
        header[:4] = b"DDS "
        compressed = self.format in (
            Rsc5TextureFormat.DXT1, Rsc5TextureFormat.DXT3, Rsc5TextureFormat.DXT5
        )
        flags = 0x1 | 0x2 | 0x4 | 0x1000 | (0x80000 if compressed else 0x8)
        if self.mip_levels > 1:
            flags |= 0x20000
        struct.pack_into(
            "<7I", header, 4, 124, flags, self.height, self.width, self.mip_sizes[0], 0,
            self.mip_levels,
        )
        struct.pack_into("<I", header, 76, 32)
        if compressed:
            struct.pack_into("<I4s", header, 80, 0x4, self.format.name.encode("ascii"))
        elif self.format == Rsc5TextureFormat.A8R8G8B8:
            struct.pack_into(
                "<7I", header, 80, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF,
                0xFF000000,
            )
        elif self.format == Rsc5TextureFormat.L8:
            struct.pack_into("<7I", header, 80, 0x20000, 0, 8, 0xFF, 0, 0, 0)
        else:
            raise ValueError(f"cannot create DDS for RSC5 texture format {int(self.format):#x}")
        caps = 0x1000
        if self.mip_levels > 1:
            caps |= 0x8 | 0x400000
        caps2 = 0
        if self.is_cube:
            caps |= 0x8
            caps2 = 0xFE00
        struct.pack_into("<2I", header, 108, caps, caps2)
        return bytes(header) + self.data

    def save_dds(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.to_dds_bytes())


@dataclass(frozen=True, slots=True)
class Rsc5TextureDictionary:
    textures: tuple[Rsc5Texture, ...]
    hashes: tuple[int, ...]
    parent_dictionary: int
    usage_count: int
    _pointer: int = field(repr=False, compare=False)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(texture.name for texture in self.textures)

    def get(self, name: str) -> Rsc5Texture | None:
        key = name.casefold().removeprefix("pack:/").removesuffix(".dds")
        return next((texture for texture in self.textures if texture.name.casefold() == key), None)

    def __len__(self) -> int:
        return len(self.textures)


def _read_virtual(resource: Rsc5Resource, pointer: int, size: int, label: str) -> bytes:
    offset = rsc5_pointer_offset(pointer)
    end = offset + size
    if end > len(resource.virtual_data):
        raise ValueError(f"{label} points outside the RSC5 virtual allocation")
    return resource.virtual_data[offset:end]


def _read_string(resource: Rsc5Resource, pointer: int) -> str:
    if pointer == 0:
        return ""
    offset = rsc5_pointer_offset(pointer)
    end = resource.virtual_data.find(b"\0", offset)
    if end < 0:
        raise ValueError("unterminated RSC5 texture name")
    return resource.virtual_data[offset:end].decode("utf-8", errors="replace")


def _read_array_header(resource: Rsc5Resource, pointer: int, label: str) -> tuple[int, int]:
    data_pointer, count, capacity = struct.unpack("<IHH", _read_virtual(resource, pointer, 8, label))
    if count > capacity:
        raise ValueError(f"{label} count exceeds its capacity")
    if count and data_pointer == 0:
        raise ValueError(f"{label} has items but a null data pointer")
    return data_pointer, count


def read_rsc5_texture_dictionary(resource: Rsc5Resource, pointer: int) -> Rsc5TextureDictionary:
    raw = _read_virtual(resource, pointer, RSC5_TEXTURE_DICTIONARY_SIZE, "RSC5 texture dictionary")
    parent_dictionary, usage_count = struct.unpack_from("<2I", raw, 8)
    hash_pointer, hash_count = _read_array_header(resource, pointer + 16, "RSC5 texture hash table")
    texture_pointer_array, texture_count = _read_array_header(
        resource, pointer + 24, "RSC5 texture pointer array"
    )
    hashes = (
        struct.unpack(f"<{hash_count}I", _read_virtual(
            resource, hash_pointer, hash_count * 4, "RSC5 texture hashes"
        )) if hash_count else ()
    )
    texture_pointers = (
        struct.unpack(f"<{texture_count}I", _read_virtual(
            resource, texture_pointer_array, texture_count * 4, "RSC5 texture pointers"
        )) if texture_count else ()
    )
    textures: list[Rsc5Texture] = []
    for texture_pointer in texture_pointers:
        texture_raw = _read_virtual(resource, texture_pointer, RSC5_TEXTURE_SIZE, "RSC5 texture")
        file_name = _read_string(resource, struct.unpack_from("<I", texture_raw, 20)[0])
        width, height, format_value, stride, texture_type, mip_levels = struct.unpack_from(
            "<HHIHBB", texture_raw, 28
        )
        if width == 0 or height == 0 or mip_levels == 0:
            raise ValueError(f"invalid RSC5 texture dimensions or mip count: {file_name!r}")
        try:
            texture_format: Rsc5TextureFormat | int = Rsc5TextureFormat(format_value)
        except ValueError:
            texture_format = format_value
        sizes = _mip_sizes(width, height, texture_format, mip_levels)
        data_pointer = struct.unpack_from("<I", texture_raw, 72)[0]
        data_offset = rsc5_pointer_offset(data_pointer, physical=True)
        data_end = data_offset + sum(sizes)
        if data_end > len(resource.physical_data):
            raise ValueError(f"RSC5 texture data points outside the physical allocation: {file_name!r}")
        normalized_name = file_name.removeprefix("pack:/")
        if normalized_name.casefold().endswith(".dds"):
            normalized_name = normalized_name[:-4]
        textures.append(Rsc5Texture(
            file_name, normalized_name, width, height, texture_format, stride, texture_type,
            mip_levels, resource.physical_data[data_offset:data_end], sizes, texture_pointer,
            data_pointer,
        ))
    return Rsc5TextureDictionary(
        tuple(textures), tuple(int(value) for value in hashes), parent_dictionary, usage_count,
        pointer,
    )


@dataclass(slots=True)
class WtdDocument:
    texture_dictionary: Rsc5TextureDictionary
    resource: Rsc5Resource
    name: str = "textures.wtd"
    source_path: str = ""

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "textures.wtd") -> "WtdDocument":
        resource = Rsc5Resource.from_bytes(data)
        if resource.version != WTD_RESOURCE_VERSION:
            raise ValueError(f"unsupported WTD resource version: {resource.version:#x}")
        return cls(read_rsc5_texture_dictionary(resource, RSC5_VIRTUAL_BASE), resource, name)

    @classmethod
    def from_path(cls, path: str | Path) -> "WtdDocument":
        source = Path(path)
        document = cls.from_bytes(source.read_bytes(), name=source.name)
        document.source_path = str(source)
        return document

    @property
    def textures(self) -> tuple[Rsc5Texture, ...]:
        return self.texture_dictionary.textures

    def get(self, name: str) -> Rsc5Texture | None:
        return self.texture_dictionary.get(name)

    def to_bytes(self) -> bytes:
        return self.resource.to_bytes()

    def save(self, path: str | Path) -> None:
        atomic_write(path, self.to_bytes())


def load_wtd(source: str | Path | bytes | BinaryIO) -> WtdDocument:
    if isinstance(source, (str, Path)):
        return WtdDocument.from_path(source)
    if isinstance(source, bytes):
        return WtdDocument.from_bytes(source)
    return WtdDocument.from_bytes(source.read())


__all__ = [
    "RSC5_TEXTURE_DICTIONARY_SIZE", "RSC5_TEXTURE_SIZE", "Rsc5Texture",
    "Rsc5TextureDictionary", "Rsc5TextureFormat", "WTD_RESOURCE_VERSION", "WtdDocument",
    "load_wtd", "read_rsc5_texture_dictionary",
]
