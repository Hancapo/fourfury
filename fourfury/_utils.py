from __future__ import annotations

import os
import tempfile
import zlib
from pathlib import Path


SECTOR_SIZE = 2048


def align(value: int, boundary: int = SECTOR_SIZE) -> int:
    if value < 0:
        raise ValueError("value cannot be negative")
    return (value + boundary - 1) // boundary * boundary


def normalize_path(path: str | Path) -> str:
    return "/".join(part for part in str(path).replace("\\", "/").strip().split("/") if part)


def normalize_key(path: str | Path) -> str:
    return normalize_path(path).casefold()


def safe_destination(root: Path, member: str | Path) -> Path:
    base = root.resolve()
    destination = (base / Path(str(member).replace("\\", "/"))).resolve()
    if not destination.is_relative_to(base):
        raise ValueError(f"archive member escapes the extraction directory: {member}")
    return destination


def atomic_write(path: str | Path, data: bytes) -> None:
    """Write *data* beside the destination and atomically replace it."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def decompress_deflate(data: bytes) -> bytes:
    for wbits in (-15, zlib.MAX_WBITS, zlib.MAX_WBITS | 32):
        try:
            return zlib.decompress(data, wbits)
        except zlib.error:
            pass
    raise ValueError("unable to decompress the deflate payload")
