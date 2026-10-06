# ekplots

A charting library with **one C geometry core**, compiled two ways —
Python via `ctypes`, JavaScript via WebAssembly — so a chart has the
same real structure in both, not two independently-written libraries
that happen to share a name.

15 basic plot types: bar, horizontal bar, stacked bar, line, area,
stacked area, pie, donut, funnel, histogram, box plot, scatter, bubble,
heatmap, radar. Full API contract: [`docs/SPEC.md`](docs/SPEC.md).

```python
import ekplots
layout = ekplots.bar([42, 71, 18, 55, 90], labels=["A", "B", "C", "D", "E"])
ekplots.draw(layout).figure.savefig("bar.png")
```

```js
import ekplots from './ekplots-draw.js';
await ekplots.ready;
const layout = ekplots.bar([10, 25, 15, 40]);
ekplots.draw(ctx, layout);
```

### What makes ekplots different: it adapts on its own

Most charting libraries stop once they've drawn a chart. ekplots also
ships a built-in **Thompson-sampling bandit** (`ekplots.Bandit` /
`ekplots-bandit.js`) that can choose between several variants of a
chart, measure which one holds a visitor's attention longest, and serve
that one more often over time — with no external analytics platform, no
server, no database. The JS binding measures dwell time itself, with its
own `IntersectionObserver`; the Python binding exposes the same reward
math for whatever host app wants to feed it outcomes. See the
"Adaptive personalization" section in each binding's own README for the
full example.

## Status

| | State |
|---|---|
| C core (all 15 plots) | Real, compiled with `-Wall -Wextra`, zero warnings |
| Python binding | Real — `pip install -e .`, 52 passing tests, real sdist+wheel, `twine check` passed |
| JS/WASM binding | Real — compiled via Emscripten, 19+4 passing tests against real pixel output |
| Adaptive personalization (bandit) | Real in both bindings — 15 Python tests, 16 JS tests, no mocking of the actual bandit math |
| Browser-verified | **Not yet** — built and tested in Node only; no browser was available in the environment this was built in. Should work unmodified against a standard `<canvas>`, but that's unverified, not assumed working |
| Published to PyPI / npm | Not yet |

Every number above is backed by a real, runnable test — see
`python/tests/` and `js/test_*.mjs`.

## Repo layout

```
docs/SPEC.md          the API contract every binding follows
python/                the Python package (ekplots/native/ekplots.c + ctypes binding)
js/                     the JS package (same ekplots.c, compiled to WASM)
.github/workflows/      CI: tests across OS/Python versions, cibuildwheel wheel builds
```

## Build from source

**Python**
```bash
cd python
pip install -e ".[dev]"
pytest
```

**JavaScript** (requires [Emscripten](https://emscripten.org/))
```bash
cd js
./build.sh
npm install   # dev-only: pulls in node-canvas, for running the test suite
npm test
```

See each directory's own README for the full detail.

## Why a C core

Every plot function computes geometry only — rectangle coordinates,
arc angles, axis bounds — never color, fonts, or pixels. Rendering is
decided per language (matplotlib for Python, Canvas2D for JS), but the
numbers underneath are identical, computed once, in one place.

## License

MIT — see [LICENSE](LICENSE).
