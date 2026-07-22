from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field


RSC5_MAGIC = b"RSC\x05"
RSC5_HEADER_SIZE = 12
RSC5_VIRTUAL_BASE = 0x50000000
RSC5_PHYSICAL_BASE = 0x60000000


def _page_size(flags: int, count_shift: int, exponent_shift: int) -> int:
    page_count = (flags >> count_shift) & 0x7FF
    exponent = (flags >> exponent_shift) & 0xF
    return page_count << (exponent + 8)


def rsc5_virtual_size(flags: int) -> int:
    """Decode the virtual allocation size stored in RSC5 flags."""

    return _page_size(flags, 0, 11)


def rsc5_physical_size(flags: int) -> int:
    """Decode the physical allocation size stored in RSC5 flags."""

    return _page_size(flags, 15, 26)


@dataclass(slots=True)
class Rsc5Resource:
    version: int
    flags: int
    virtual_data: bytes
    physical_data: bytes = b""
    _source: bytes | None = field(default=None, repr=False, compare=False)

    @property
    def virtual_size(self) -> int:
        return rsc5_virtual_size(self.flags)

    @property
    def physical_size(self) -> int:
        return rsc5_physical_size(self.flags)

    @classmethod
    def from_bytes(cls, data: bytes) -> "Rsc5Resource":
        if len(data) < RSC5_HEADER_SIZE:
            raise ValueError("truncated RSC5 header")
        magic, version, flags = struct.unpack_from("<4sII", data)
        if magic != RSC5_MAGIC:
            raise ValueError("invalid RSC5 resource")
        try:
            payload = zlib.decompress(data[RSC5_HEADER_SIZE:])
        except zlib.error as exc:
            raise ValueError("invalid RSC5 deflate payload") from exc
        virtual_size = rsc5_virtual_size(flags)
        physical_size = rsc5_physical_size(flags)
        expected_size = virtual_size + physical_size
        if len(payload) != expected_size:
            raise ValueError(
                f"RSC5 payload size mismatch: expected {expected_size}, got {len(payload)}"
            )
        return cls(
            version=version,
            flags=flags,
            virtual_data=payload[:virtual_size],
            physical_data=payload[virtual_size:],
            _source=bytes(data),
        )

    def to_bytes(
        self,
        *,
        virtual_data: bytes | None = None,
        physical_data: bytes | None = None,
    ) -> bytes:
        virtual = self.virtual_data if virtual_data is None else bytes(virtual_data)
        physical = self.physical_data if physical_data is None else bytes(physical_data)
        if len(virtual) != self.virtual_size:
            raise ValueError("RSC5 edits cannot change the virtual allocation size")
        if len(physical) != self.physical_size:
            raise ValueError("RSC5 edits cannot change the physical allocation size")
        if (
            self._source is not None
            and virtual == self.virtual_data
            and physical == self.physical_data
        ):
            return self._source
        header = struct.pack("<4sII", RSC5_MAGIC, self.version, self.flags)
        return header + zlib.compress(virtual + physical, level=9)


def rsc5_pointer_offset(pointer: int, *, physical: bool = False) -> int:
    """Translate a serialized RSC5 pointer into its allocation-relative offset."""

    if pointer == 0:
        raise ValueError("null RSC5 pointer")
    expected_base = RSC5_PHYSICAL_BASE if physical else RSC5_VIRTUAL_BASE
    if pointer & 0xF0000000 != expected_base:
        kind = "physical" if physical else "virtual"
        raise ValueError(f"invalid RSC5 {kind} pointer: {pointer:#x}")
    return pointer & 0x0FFFFFFF


__all__ = [
    "RSC5_HEADER_SIZE", "RSC5_MAGIC", "RSC5_PHYSICAL_BASE", "RSC5_VIRTUAL_BASE",
    "Rsc5Resource", "rsc5_physical_size", "rsc5_pointer_offset", "rsc5_virtual_size",
]
