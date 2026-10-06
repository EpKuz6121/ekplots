"""Builds ekplots' C core as a loadable shared library.

This is NOT a CPython extension module in the usual sense — ekplots.c
has no Python.h, no PyInit_ entry point, nothing CPython-specific at all.
setuptools' build_ext is used purely as a portable C compiler invocation
(it already knows how to find a compiler and produce the right .so/.dylib/
.pyd per platform); the resulting shared library is loaded at runtime via
ctypes.CDLL in ekplots/_core.py, never through Python's `import` machinery.
That's why `import ekplots._native` would NOT work directly — only
ctypes.CDLL(<path to the built file>) does.
"""
from setuptools import setup, Extension

ekplots_native = Extension(
    "ekplots._native",
    sources=["ekplots/native/ekplots.c"],
    include_dirs=["ekplots/native"],
    extra_compile_args=["-std=c11"],
)

setup(ext_modules=[ekplots_native])
