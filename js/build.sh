#!/usr/bin/env bash
# Compiles ekplots' real C core (the SAME ekplots.c the Python binding
# uses — no WASM-specific fork) plus shim.c's boxed wrappers into
# ekplots_wasm.js + ekplots_wasm.wasm. Run from this directory.
set -euo pipefail

emcc \
  ../python/ekplots/native/ekplots.c \
  shim.c \
  -I../python/ekplots/native \
  -O2 \
  -s MODULARIZE=1 \
  -s EXPORT_NAME=createEkplotsModule \
  -s EXPORTED_FUNCTIONS=@exports.txt \
  -s EXPORTED_RUNTIME_METHODS='["ccall","cwrap","HEAPU8","HEAPF64"]' \
  -s ALLOW_MEMORY_GROWTH=1 \
  -s ENVIRONMENT=web,node \
  -o ekplots_wasm.js

echo "Built ekplots_wasm.js + ekplots_wasm.wasm"
