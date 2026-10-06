/* Windows-only linker satisfaction shim.
 *
 * ekplots._native is NOT a real CPython extension module — it's loaded
 * via ctypes.CDLL, never Python's own `import` machinery (see setup.py's
 * own comment on this). On macOS/Linux, an unresolved PyInit_<name>
 * symbol is fine: distutils/setuptools links those platforms with
 * `-undefined dynamic_lookup`, deferring symbol resolution to runtime,
 * which ctypes.CDLL never needs anyway.
 *
 * MSVC's linker has no equivalent — it requires every symbol a .pyd
 * exports to resolve at LINK time, and setuptools' build_ext always
 * passes `/EXPORT:PyInit_<name>` for a Windows build. Without this file,
 * Windows installs fail with LNK2001: unresolved external symbol
 * PyInit__native — a real failure, caught by this repo's own CI
 * (see .github/workflows/test.yml's windows-latest jobs), not
 * hypothetical.
 *
 * This stub satisfies the linker and does nothing else. If someone DID
 * try `import ekplots._native` directly on Windows (nobody should —
 * ekplots/_core.py only ever loads it via ctypes), this returns a real,
 * empty, harmless module rather than crashing.
 */
#ifdef _WIN32
#include <Python.h>

static struct PyModuleDef ekplots_native_moduledef = {
    PyModuleDef_HEAD_INIT,
    "_native",
    "ekplots' native C core — not meant to be imported directly, see ekplots/_core.py",
    -1,
    NULL
};

PyMODINIT_FUNC PyInit__native(void) {
    return PyModule_Create(&ekplots_native_moduledef);
}
#endif
