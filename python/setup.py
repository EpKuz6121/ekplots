"""Builds ekplots' C core as a loadable shared library.

This is NOT a CPython extension module in the usual sense — ekplots.c
has no Python.h, no PyInit_ entry point, nothing CPython-specific at all
(pyinit_stub.c is the one exception — see its own docstring for why it
has to exist anyway, specifically for MSVC's linker). setuptools'
build_ext is used purely as a portable C compiler invocation (it already
knows how to find a compiler and produce the right .so/.dylib/.pyd per
platform); the resulting shared library is loaded at runtime via
ctypes.CDLL in ekplots/_core.py, never through Python's `import` machinery.
That's why `import ekplots._native` would NOT work directly on
macOS/Linux — only ctypes.CDLL(<path to the built file>) does.
"""
import sys

from setuptools import setup, Extension

# -std=c11 is GCC/Clang syntax — MSVC uses /std:c11 instead, a different
# flag entirely. Real cross-platform CI (.github/workflows/test.yml)
# caught this: it didn't actually hard-fail the Windows build (MSVC
# tolerated the unrecognized flag rather than rejecting it), but relying
# on a compiler silently ignoring a flag it doesn't understand isn't
# something to build on purpose.
extra_compile_args = [] if sys.platform == "win32" else ["-std=c11"]

ekplots_native = Extension(
    "ekplots._native",
    sources=["ekplots/native/ekplots.c", "ekplots/native/pyinit_stub.c"],
    include_dirs=["ekplots/native"],
    extra_compile_args=extra_compile_args,
)

setup(ext_modules=[ekplots_native])
