# ekplots (JS)

The JS binding — same C core as the Python package
(`../python/ekplots/native/ekplots.c`), compiled to WebAssembly instead
of a native shared library. See `../docs/SPEC.md` for the full API.

**Status: built and tested in Node.** Every function's geometry is
verified correct (`test_node.mjs`) and renders real pixels
(`render_all_15.mjs`, via `node-canvas`). **Not yet verified in an
actual browser** — this environment doesn't have one connected. The
code is written for a standard `<canvas>` 2D context and should work
unmodified; "should" is explicitly flagged because it hasn't been run
there, which is a real difference from everything else in this
library.

## Build

Requires [Emscripten](https://emscripten.org/) (`brew install
emscripten`, or see their installation docs — `emcc` needs to be on
`PATH`).

```bash
./build.sh
```

Produces `ekplots_wasm.js` + `ekplots_wasm.wasm` from the real C source
— the exact same `ekplots.c` the Python package compiles, plus
`shim.c` (explicit-pointer wrappers so struct passing doesn't depend on
WASM ABI internals — see that file's own comment for why).

## Use (Node)

```bash
npm install          # only pulls in `canvas`, a DEV dependency for
                      # testing/rendering verification — ekplots.js
                      # itself has zero runtime dependencies
npm test              # runs test_node.mjs — 19 real correctness checks
npm run render         # renders all 15 to real PNGs in out/
```

```js
import ekplots from './ekplots.js';
await ekplots.ready;   // WASM module load is async — wait for this first

const layout = ekplots.bar([10, 25, 15, 40], { labels: ['A', 'B', 'C', 'D'] });
console.log(layout.bars); // raw geometry, no rendering needed
```

## Use (browser)

Two plain `<script>` tags, no bundler required — matches how
SurveySync's own tracker is embedded:

```html
<script src="ekplots_wasm.js"></script>
<script src="ekplots.js"></script>
<script src="ekplots-draw.js"></script>
<canvas id="chart" width="400" height="300"></canvas>
<script>
  ekplots.ready.then(() => {
    const layout = ekplots.bar([10, 25, 15, 40]);
    const ctx = document.getElementById('chart').getContext('2d');
    ekplots.draw(ctx, layout);
  });
</script>
```

All three JS files plus `ekplots_wasm.wasm` need to be served from the
same directory (the `.wasm` file is fetched relative to
`ekplots_wasm.js`'s own location).

## The tracking hook

`ekplots.draw(ctx, layout, { chartId: 'my-chart' })` — when `chartId`
is set, `draw()` checks for `window.__analytics` (SurveySync's tracker)
and, only if present and consent is already granted, wires up view/click
tracking through an `IntersectionObserver`. See `ekplots-draw.js`'s
`_wireTracking()` for the exact design.

**Real and wired on both ends.** `_wireTracking()` calls
`window.__analytics.emitChartEvent(...)` — SurveySync's tracker
(`tracker/src/index.ts`) now implements it: `chart_view`/`chart_interact`
are real `EventType`s, consent-gated identically to every other
collector, with `chart_id`/`interaction_type`/`x`/`y` stored inside the
event's `meta` JSONB field (not new top-level columns — no migration
needed, matching how `scroll_behavior`/`engagement_rhythm` already
store their derived data). Verified two ways: `tracker/test/
smoke_chart_events.mjs` proves the tracker side lands the right data
in `meta` and respects consent; `test_tracking_hook.mjs` in this repo
proves ekplots' own `_wireTracking()` calls through with the exact
camelCase shape (`chartId`, `interactionType`) the tracker expects,
including the real click-coordinate math. One real bug was caught by
this verification, not assumption: `emitChartEvent` originally had a
leading underscore, which the tracker's own build (`esbuild`'s
`mangleProps: /^_[a-zA-Z]/`) silently renames — meaning the documented
call would have failed in production even though it looked correct in
source. Fixed by dropping the underscore, matching every other real
public method (`trackPageView`, `identify`).

## Files

| File | What it is |
|---|---|
| `shim.c` | Explicit-pointer wrappers around the real `ekplots_<name>_layout()` functions — see its own header comment for why |
| `build.sh` / `exports.txt` | The real Emscripten compile command and export list |
| `ekplots.js` | Geometry-only binding — loads the WASM module, marshals memory, returns plain JS objects |
| `ekplots-draw.js` | Canvas2D renderer + the tracking hook |
| `test_node.mjs` | 19 real correctness checks against the compiled WASM |
| `test_tracking_hook.mjs` | 4 real checks that the tracking hook calls through to a mock tracker with the exact right shape |
| `render_all_15.mjs` | Renders all 15 to real PNGs (uses `node-canvas` as a stand-in for a browser `<canvas>`) |
