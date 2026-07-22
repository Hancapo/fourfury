from __future__ import annotations

import sys

from setuptools import Extension, setup


compile_args = ["/std:c++17", "/O2"] if sys.platform == "win32" else ["-std=c++17", "-O3"]

native = Extension(
    "fourfury._native",
    sources=[
        "src/module.cpp",
        "src/crypto.cpp",
        "src/wdr.cpp",
        "src/wbn.cpp",
    ],
    depends=["src/native.hpp", "src/binary.hpp"],
    define_macros=[("Py_LIMITED_API", "0x030B0000")],
    extra_compile_args=compile_args,
    libraries=["bcrypt"] if sys.platform == "win32" else [],
    language="c++",
    optional=True,
    py_limited_api=True,
)

setup(
    ext_modules=[native],
    options={"bdist_wheel": {"py_limited_api": "cp311"}},
)
