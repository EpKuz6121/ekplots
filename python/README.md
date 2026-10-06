# ekplots

A charting library with one C geometry core, shared between its Python
and JS bindings — 15 basic plot types. See `docs/SPEC.md` for the full
API contract.

**Status: Python binding only.** The JS/WASM binding is spec'd but not
yet built — see SPEC.md.

## Install

```bash
pip install ekplots
```

Installing from source compiles the C core automatically — a C compiler
(clang, gcc, or MSVC) is required if no prebuilt wheel matches your
platform.

## Use

```python
import ekplots

layout = ekplots.bar([42, 71, 18, 55, 90], labels=["A", "B", "C", "D", "E"])
ax = ekplots.draw(layout)
ax.figure.savefig("bar.png")
```

All 15: `bar`, `hbar`, `stacked_bar`, `line`, `area`, `stacked_area`,
`pie`, `donut`, `funnel`, `histogram`, `boxplot`, `scatter`, `bubble`,
`heatmap`, `radar`. Every function returns a `Layout` object — raw
geometry as numpy arrays, no rendering — so `ekplots.draw(layout)` is
optional if you just want the numbers.

## Why a C core

Every plot function computes geometry only — rectangle coordinates, arc
angles, axis bounds — never color or pixels. That's what lets a future
JS binding render a structurally identical chart from the same source,
instead of two separate chart libraries that happen to share a name.

## License

MIT — see LICENSE.
