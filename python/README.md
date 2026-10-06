# ekplots

A charting library with one C geometry core, shared between its Python
and JS bindings — 15 basic plot types. See `docs/SPEC.md` for the full
API contract.

**Status:** both the Python and JS/WASM bindings are built and tested —
see the root README's status table.

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

## Adaptive personalization — pick which variant wins, automatically

ekplots ships a built-in Thompson-sampling bandit and cluster-based chart
router (`ekplots.Bandit`, `ekplots.ordered_for_viewer`) — the piece that
makes ekplots different from matplotlib, Plotly, or any other charting
library: it can decide WHICH VARIANT of a chart to render, learn which
one keeps people engaged longest, and serve that one more often, with no
external analytics platform or database required.

```python
import ekplots

bandit = ekplots.Bandit(path="bandit.json")  # one JSON file, zero deps
bandit.add_slot("retention_chart", variants=["bar_vs_line"])

variant = bandit.choose("retention_chart")  # "control" or "bar_vs_line"
layout = ekplots.bar([...]) if variant == "control" else ekplots.line([...], [...])
ekplots.draw(layout).figure.savefig("chart.png")

# later, once you know how long that session looked at it:
bandit.record_dwell("retention_chart", variant, dwell_ms=4200, control_dwell_samples=past_control_dwells)

# or bias it immediately, without waiting for the bandit to converge:
bandit.set_priority_weight("retention_chart", "bar_vs_line", 3.0)
```

`ekplots.ordered_for_viewer(*chart_variants, viewer_cluster=..., enabled=...,
rollout_p=...)` is the complementary piece: given several DIFFERENT
charts (not variants of one chart), each tagged with the visitor cluster
it fits best, it reorders them so the best-fit chart for the current
viewer renders first — gated by an on/off switch and a rollout
percentage, so you control what fraction of visitors get the
personalized order while the bandit (or you) builds confidence.

See `ekplots/bandit.py`'s module docstring for the full design, and the
JS binding's `ekplots-bandit.js` for the browser-native version, which
measures dwell time itself.

## Why a C core

Every plot function computes geometry only — rectangle coordinates, arc
angles, axis bounds — never color or pixels. That's what lets a future
JS binding render a structurally identical chart from the same source,
instead of two separate chart libraries that happen to share a name.

## License

MIT — see LICENSE.
