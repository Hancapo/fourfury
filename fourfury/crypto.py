from __future__ import annotations

import ctypes
import hashlib
import mmap
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Final

try:
    from ._native import aes16_decrypt as _native_aes16_decrypt
    from ._native import create_aes_context as _create_native_aes_context
except ImportError:
    _native_aes16_decrypt = None
    _create_native_aes_context = None


GTAIV_KEY_SHA1: Final[bytes] = bytes.fromhex("DEA375EF1E6EF2223A1221C2C575C47BF17EFA5E")
GTAIV_AES_KEY: Final[bytes] = bytes.fromhex(
    "1AB56FED7EC3FF01227B691533975DCE47D769653FF775426A96CD6D5307565D"
)
_KNOWN_KEY_OFFSETS: Final[tuple[int, ...]] = (
    0xA94204, 0xB607C4, 0xB56BC4, 0xB75C9C, 0xB7AEF4,
    0xBE6540, 0xBE7540, 0xC95FD8, 0xC5B33C, 0xC5B73C,
    0xB5B65C, 0xB569F4, 0xC705E0, 0xBEF028,
)


def _resolve_executable(root_or_exe: str | Path) -> Path:
    path = Path(root_or_exe)
    if path.is_file():
        return path
    for name in ("GTAIV.exe", "gtaiv.exe", "EFLC.exe", "eflc.exe"):
        candidate = path / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"GTAIV.exe or EFLC.exe was not found in {path}")


def extract_aes_key(root_or_exe: str | Path) -> bytes:
    """Extract and verify the GTA IV AES key from the user's executable."""
    exe = _resolve_executable(root_or_exe)
    with exe.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        for offset in _KNOWN_KEY_OFFSETS:
            if offset + 32 <= len(data):
                candidate = data[offset : offset + 32]
                if hashlib.sha1(candidate).digest() == GTAIV_KEY_SHA1:
                    return bytes(candidate)
        # Known releases keep the material DWORD-aligned. This fallback also
        # supports future executable builds without hard-coding their offset.
        for offset in range(0, max(0, len(data) - 31), 4):
            candidate = data[offset : offset + 32]
            if hashlib.sha1(candidate).digest() == GTAIV_KEY_SHA1:
                return bytes(candidate)
    raise ValueError(f"the GTA IV AES key was not found in {exe}")


def _build_aes_decryptor(key: bytes) -> Callable[[bytes], bytes]:
    try:
        from Cryptodome.Cipher import AES  # type: ignore[import-not-found]
        return AES.new(key, AES.MODE_ECB).decrypt
    except ImportError:
        pass
    try:
        from Crypto.Cipher import AES  # type: ignore[import-not-found]
        return AES.new(key, AES.MODE_ECB).decrypt
    except ImportError:
        pass
    if os.name != "nt":
        raise RuntimeError("AES support requires pycryptodomex/pycryptodome outside Windows")
    return _WindowsAesEcbDecryptor(key).decrypt


class _WindowsAesEcbDecryptor:
    def __init__(self, key: bytes) -> None:
        bcrypt = ctypes.WinDLL("bcrypt")
        self._bcrypt = bcrypt
        self._void_p = ctypes.c_void_p
        self._u32 = ctypes.c_ulong
        self._byte_p = ctypes.POINTER(ctypes.c_ubyte)

        self._open = bcrypt.BCryptOpenAlgorithmProvider
        self._open.argtypes = [ctypes.POINTER(self._void_p), ctypes.c_wchar_p, ctypes.c_wchar_p, self._u32]
        self._open.restype = ctypes.c_long
        self._set = bcrypt.BCryptSetProperty
        self._set.argtypes = [self._void_p, ctypes.c_wchar_p, self._byte_p, self._u32, self._u32]
        self._set.restype = ctypes.c_long
        self._get = bcrypt.BCryptGetProperty
        self._get.argtypes = [self._void_p, ctypes.c_wchar_p, self._byte_p, self._u32, ctypes.POINTER(self._u32), self._u32]
        self._get.restype = ctypes.c_long
        self._generate = bcrypt.BCryptGenerateSymmetricKey
        self._generate.argtypes = [self._void_p, ctypes.POINTER(self._void_p), self._byte_p, self._u32, self._byte_p, self._u32, self._u32]
        self._generate.restype = ctypes.c_long
        self._decrypt = bcrypt.BCryptDecrypt
        self._decrypt.argtypes = [self._void_p, self._byte_p, self._u32, self._void_p, self._byte_p, self._u32, self._byte_p, self._u32, ctypes.POINTER(self._u32), self._u32]
        self._decrypt.restype = ctypes.c_long
        self._destroy = bcrypt.BCryptDestroyKey
        self._destroy.argtypes = [self._void_p]
        self._close = bcrypt.BCryptCloseAlgorithmProvider
        self._close.argtypes = [self._void_p, self._u32]

        self._algorithm = self._void_p()
        self._key_handle = self._void_p()
        self._key_object = None
        self._key_material = None
        self._check(self._open(ctypes.byref(self._algorithm), "AES", None, 0), "open AES provider")
        mode = ctypes.create_unicode_buffer("ChainingModeECB")
        self._check(self._set(self._algorithm, "ChainingMode", ctypes.cast(mode, self._byte_p), ctypes.sizeof(mode), 0), "set ECB mode")
        object_size = self._u32()
        result_size = self._u32()
        self._check(self._get(self._algorithm, "ObjectLength", ctypes.cast(ctypes.byref(object_size), self._byte_p), ctypes.sizeof(object_size), ctypes.byref(result_size), 0), "get AES object size")
        self._key_object = (ctypes.c_ubyte * object_size.value)()
        self._key_material = (ctypes.c_ubyte * len(key)).from_buffer_copy(key)
        self._check(self._generate(self._algorithm, ctypes.byref(self._key_handle), self._key_object, object_size.value, self._key_material, len(key), 0), "create AES key")

    @staticmethod
    def _check(status: int, operation: str) -> None:
        if status < 0:
            raise OSError(f"{operation} failed with NTSTATUS 0x{status & 0xFFFFFFFF:08X}")

    def decrypt(self, data: bytes) -> bytes:
        source = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        target = (ctypes.c_ubyte * len(data))()
        written = self._u32()
        self._check(self._decrypt(self._key_handle, source, len(data), None, None, 0, target, len(data), ctypes.byref(written), 0), "decrypt AES data")
        return bytes(target[:written.value])

    def close(self) -> None:
        if self._key_handle.value:
            self._destroy(self._key_handle)
            self._key_handle = self._void_p()
        if self._algorithm.value:
            self._close(self._algorithm, 0)
            self._algorithm = self._void_p()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


@dataclass(slots=True)
class GTAIVCrypto:
    aes_key: bytes = GTAIV_AES_KEY
    _decrypt_once: Callable[[bytes], bytes] | None = field(default=None, init=False, repr=False)
    _native_context: object | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.aes_key = bytes(self.aes_key)
        if len(self.aes_key) != 32:
            raise ValueError("the GTA IV AES key must contain 32 bytes")

    @classmethod
    def from_game(cls, root_or_exe: str | Path) -> "GTAIVCrypto":
        return cls(extract_aes_key(root_or_exe))

    def decrypt(self, data: bytes) -> bytes:
        """Decrypt aligned blocks with GTA IV's sixteen-pass AES scheme."""
        if not data:
            return b""
        if (
            sys.platform == "win32"
            and _create_native_aes_context is not None
            and _native_aes16_decrypt is not None
        ):
            if self._native_context is None:
                self._native_context = _create_native_aes_context(self.aes_key)
            return _native_aes16_decrypt(self._native_context, data)
        aligned = len(data) - len(data) % 16
        if aligned == 0:
            return bytes(data)
        if self._decrypt_once is None:
            self._decrypt_once = _build_aes_decryptor(self.aes_key)
        prefix = bytes(data[:aligned])
        for _ in range(16):
            prefix = self._decrypt_once(prefix)
        return prefix + data[aligned:]


__all__ = ["GTAIVCrypto", "GTAIV_AES_KEY", "GTAIV_KEY_SHA1", "extract_aes_key"]
