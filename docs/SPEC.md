# ekplots — API Specification v0.1

**Status: spec only.** Nothing in this document is implemented yet. This
is the contract every language binding has to satisfy — the next step is
writing the C core against it.

## Architecture

One C core, compiled two different ways, consumed by two renderers. This
is the same pattern DuckDB and Polars use: a single source of truth for
the logic, thin bindings per host.

```
            ekplots_*.c  (geometry only — no pixels, no color, no fonts)
                 |
        +--------+--------+
        |                 |
  clang -shared     emcc -> WASM
  libekplots.dylib        |
        |            ekplots.wasm + glue.js
   Python ctypes           |
        |             JS (browser)
   matplotlib/SVG      Canvas/SVG
   renderer             renderer
```

**The C core never draws anything.** Every function takes raw data and
returns *numbers* — rectangle coordinates, arc angles, computed axis
bounds. Color, fonts, and strokes are a rendering concern, decided
per-language. This is the one decision that makes two bindings possible
without duplicating chart logic twice: Python and JS both consume
identical geometry, which is what gives a chart the same *structure* in
both — the "Python and JavaScript look" the library is for.

- **Python binding**: `clang -shared -fPIC ekplots.c -o libekplots.dylib`,
  loaded via `ctypes.CDLL`. Buildable today — clang is available in a
  standard dev environment.
- **JS binding**: the same `.c` files compiled with **Emscripten**
  (`emcc`) to WebAssembly + a glue `.js` file. Requires the Emscripten
  toolchain, a separate install from a C compiler.

## Shared primitives

Every plot's geometry is built from five structs. Nothing plot-specific
lives here.

```c
typedef struct { double x, y; } EKPoint;
typedef struct { double x, y, w, h; } EKRect;
typedef struct { double x_min, x_max, y_min, y_max; } EKBounds;
typedef struct { double cx, cy, r, start_angle, end_angle; } EKArc;
typedef struct { double x, y, r; } EKBubble;
```

`EKBounds` is the computed data domain (not pixel bounds) — every layout
function returns one so a renderer can draw axes/gridlines without
re-deriving min/max itself.

## Call convention, all three languages

| | C | Python | JS |
|---|---|---|---|
| Pattern | `EK<Name>Layout ekplots_<name>_layout(data..., EK<Name>Options opts)` | `ekplots.<name>(data, **opts) -> Layout` | `ekplots.<name>(data, opts) -> Layout` |
| Renders via | — (caller's job) | `ekplots.draw(layout, ax=None)` (matplotlib) | `ekplots.draw(ctx, layout)` (Canvas 2D) |
| Frees memory | `ekplots_<name>_free(&layout)` | automatic (wrapper owns it) | automatic (WASM memory freed by wrapper) |

Geometry and rendering are two different calls in every language, on
purpose — a user who wants raw numbers (to drive a custom D3 render, or
just to inspect them) never has to fight a renderer to get them.

## The tracking hook — JS only

Every JS plot function accepts an optional `chartId` in its options.
**This is the only SurveySync-specific thing in the library, and it's
opt-in per chart, not global.**

```js
ekplots.draw(ctx, layout, { chartId: 'pricing-page-plan-comparison' });
```

When `chartId` is set, `ekplots.draw()` checks for `window.__analytics`
(SurveySync's tracker, if the host page has it installed) and, only if
present AND consent is already granted:

- Emits a `chart_view` event once the chart's canvas enters the viewport
  (IntersectionObserver, same technique `section_dwell` already uses).
- Emits a `chart_interact` event on hover/click of a bar, slice, or
  point, carrying which data index was touched — never raw coordinates,
  same discipline as every other collector in `tracker/src/collectors/`.

**No new network code.** ekplots never calls `fetch` itself — it calls
`window.__analytics`'s existing buffer, which already handles consent
gating, batching, and the real `/v1/events` ingest. If the host page
doesn't have the tracker installed, `chartId` is simply inert — ekplots
renders exactly the same chart either way. **Python has no `chartId`**
parameter at all: there's no live visitor in a notebook or a server-side
report-generation script, so there's nothing to track.

A new `EventType` would need two values added
(`chart_view`/`chart_interact`) and a handful of fields on `EventSchema`
(`chart_id`, `interaction_type`, `data_index`) — everything else (rate
limits, retention, deletion) is inherited for free from the existing
ingest pipeline.

---

# The 15 plots

Grouped by the job they do, not alphabetically or by complexity — matching
how a real chart-selection decision actually gets made.

## Categorical comparison

### 1. Bar

Magnitude across discrete categories — the single most common chart
there is.

**SurveySync relevance:** Overview's "pages ranked by sessions" is this
chart today, hand-built in Recharts. A direct replacement candidate.

```c
typedef struct {
    double width, height;
    double bar_gap;    // 0-1, fraction of each slot that's gap
    int horizontal;     // 0 = vertical bars, 1 = horizontal
} EKBarOptions;

typedef struct {
    EKRect* bars;
    size_t n;
    EKBounds bounds;
} EKBarLayout;

EKBarLayout ekplots_bar_layout(const double* values, size_t n, EKBarOptions opts);
void ekplots_bar_free(EKBarLayout* layout);
```

- Python: `ekplots.bar(values, labels=None, horizontal=False) -> BarLayout`
- JS: `ekplots.bar(values, { labels, horizontal, chartId }) -> BarLayout`

### 2. Horizontal Bar

Same chart, rotated — its own entry because long category labels (a page
path, a referrer hostname) genuinely need the horizontal layout to stay
readable, not because the geometry differs.

**SurveySync relevance:** page paths are frequently 30+ characters —
Overview's bar chart is already horizontal for exactly this reason.

- Shares `ekplots_bar_layout()` with `opts.horizontal = 1`. No separate C
  function.
- Python: `ekplots.hbar(values, labels=None)` — thin wrapper over `bar(horizontal=True)`
- JS: `ekplots.hbar(values, { labels, chartId })`

### 3. Stacked Bar

Composition within each category — how a total splits into parts, per
category.

**SurveySync relevance:** Segments currently shows one dimension at a
time (Device, then Browser, then Authenticated, separately). A stacked
bar could show device-split-by-cluster in one chart instead of
cross-referencing two.

```c
typedef struct {
    double width, height;
    double bar_gap;
    size_t n_series;
} EKStackedBarOptions;

typedef struct {
    EKRect* segments;   // n_categories * n_series rects, row-major
    size_t n_categories, n_series;
    EKBounds bounds;
} EKStackedBarLayout;

EKStackedBarLayout ekplots_stacked_bar_layout(
    const double* const* series_values, size_t n_series, size_t n_categories,
    EKStackedBarOptions opts
);
```

- Python: `ekplots.stacked_bar(series: dict[str, list[float]], labels=None)`
- JS: `ekplots.stackedBar(series, { labels, chartId })`

## Trend over time

### 4. Line

A value changing over an ordered axis — almost always time.

**SurveySync relevance:** Overview's `daily_sessions` trend is this
chart today.

```c
typedef struct {
    double width, height;
    int smooth;   // 0 = straight segments, 1 = monotone cubic
} EKLineOptions;

typedef struct {
    EKPoint* points;
    size_t n;
    EKBounds bounds;
} EKLineLayout;

EKLineLayout ekplots_line_layout(const double* x, const double* y, size_t n, EKLineOptions opts);
```

- Python: `ekplots.line(x, y, smooth=False) -> LineLayout`
- JS: `ekplots.line(x, y, { smooth, chartId })`

### 5. Area

A line chart with the region below it filled — reads as "accumulated
mass" rather than a thin trajectory, which matters when the total volume
is the point, not just the shape.

**SurveySync relevance:** `returning_visitors`/`total_sessions` over
time — volume matters as much as trend there.

```c
typedef struct {
    double width, height;
    double baseline;    // value the fill closes down to, usually 0
} EKAreaOptions;

typedef struct {
    EKPoint* points;     // top edge of the fill
    size_t n;
    double baseline_y;   // pixel y of the baseline, for closing the polygon
    EKBounds bounds;
} EKAreaLayout;

EKAreaLayout ekplots_area_layout(const double* x, const double* y, size_t n, EKAreaOptions opts);
```

- Python: `ekplots.area(x, y, baseline=0.0)`
- JS: `ekplots.area(x, y, { baseline, chartId })`

### 6. Stacked Area

Composition over time — how several series' *shares* of a whole shift
across the x-axis, not just their individual trends.

**SurveySync relevance:** cluster share over time — "Group 1 was 40% of
sessions last week, 55% this week" — doesn't exist in the product today,
and is a genuinely useful question once clustering has run for a while.

```c
typedef struct {
    double width, height;
    size_t n_series;
} EKStackedAreaOptions;

typedef struct {
    EKPoint* bands;   // n_series * n_points * 2 (top+bottom per series), flattened
    size_t n_series, n_points;
    EKBounds bounds;
} EKStackedAreaLayout;

EKStackedAreaLayout ekplots_stacked_area_layout(
    const double* x, const double* const* series_y, size_t n_series, size_t n_points,
    EKStackedAreaOptions opts
);
```

- Python: `ekplots.stacked_area(x, series: dict[str, list[float]])`
- JS: `ekplots.stackedArea(x, series, { chartId })`

## Part-to-whole

### 7. Pie

Share of a single whole, few categories (readable up to ~5-6 slices).

**SurveySync relevance:** cluster share ("Group 1 · 71%"), device-class
share — currently text/bar-track percentages in Page Assignment and
Segments, not an actual pie.

```c
typedef struct { double cx, cy, r; } EKPieOptions;

typedef struct {
    EKArc* slices;
    size_t n;
} EKPieLayout;

EKPieLayout ekplots_pie_layout(const double* values, size_t n, EKPieOptions opts);
```

- Python: `ekplots.pie(values, labels=None)`
- JS: `ekplots.pie(values, { labels, chartId })`

### 8. Donut

A pie with the center cut out — functionally identical geometry plus one
radius, but the open center is real: it's the one slot in this whole set
of 15 built to hold a number (a total) without fighting the slices for
space.

**SurveySync relevance:** same cluster-share use case as pie, with total
session count sitting in the center — the kind of "headline number +
breakdown" combination the dataviz skill's "hero number" pattern already
favors over a bare stat tile.

```c
typedef struct { double cx, cy, r, inner_r; } EKDonutOptions;

typedef struct {
    EKArc* slices;    // same meaning as EKPieLayout; r is the OUTER radius
    size_t n;
    double inner_r;
} EKDonutLayout;

EKDonutLayout ekplots_donut_layout(const double* values, size_t n, EKDonutOptions opts);
```

- Python: `ekplots.donut(values, labels=None, inner_r=0.6)`
- JS: `ekplots.donut(values, { labels, innerR, chartId })`

### 9. Funnel

Sequential drop-off across ordered stages — each stage can only be
smaller than (or equal to) the one before it.

**SurveySync relevance:** the single best fit of all 15. `typical_path`
(Flow.tsx) is already exactly this shape — entry page, then the
most-taken next step, then the next — currently rendered as a plain text
breadcrumb. A real funnel would show the drop-off magnitude at each step,
which the breadcrumb can't.

```c
typedef struct {
    double width, height;
    double stage_gap;
} EKFunnelOptions;

typedef struct {
    EKPoint trapezoid[4];   // the tapered stage shape
    double value, pct_of_first, pct_of_previous;
} EKFunnelStage;

typedef struct {
    EKFunnelStage* stages;
    size_t n;
} EKFunnelLayout;

EKFunnelLayout ekplots_funnel_layout(const double* values, size_t n, EKFunnelOptions opts);
```

- Python: `ekplots.funnel(values, labels=None)`
- JS: `ekplots.funnel(values, { labels, chartId })`

## Distribution

### 10. Histogram

How a single continuous variable's values are distributed — the shape
behind an average, not just the average.

**SurveySync relevance:** session dwell-time distribution. Overview
reports `avg_time_on_page_ms`; a histogram would show whether that
average hides a bimodal split (a lot of 2-second bounces plus a lot of
2-minute reads, averaging to a number neither group actually
experiences) — a real blind spot in every average currently shown in the
product.

```c
typedef struct {
    double width, height;
    size_t n_bins;   // 0 = auto (Sturges' rule)
} EKHistogramOptions;

typedef struct {
    EKRect* bins;
    size_t n_bins;
    double* bin_edges;   // n_bins + 1 values
    EKBounds bounds;
} EKHistogramLayout;

EKHistogramLayout ekplots_histogram_layout(const double* values, size_t n, EKHistogramOptions opts);
```

- Python: `ekplots.histogram(values, bins=0)`
- JS: `ekplots.histogram(values, { bins, chartId })`

### 11. Box Plot

Median, quartiles, and outliers — compares the *spread* of a variable
across groups side by side, not just each group's average.

**SurveySync relevance:** dwell time PER cluster, side by side. Right
now a cluster's `key_drivers` describes it with a flat "high dwell_ms"
label; a box plot would show whether that cluster is tightly consistent
or just has a long tail pulling the average up — real information
`key_drivers` currently throws away.

```c
typedef struct {
    double width, height;
    double box_width;   // fraction of each group's slot
} EKBoxplotOptions;

typedef struct {
    double min, q1, median, q3, max;
    double* outliers;
    size_t n_outliers;
    EKRect box;              // q1 to q3
    EKPoint whisker_low, whisker_high;
} EKBoxplotStats;

typedef struct {
    EKBoxplotStats* groups;
    size_t n_groups;
    EKBounds bounds;
} EKBoxplotLayout;

EKBoxplotLayout ekplots_boxplot_layout(
    const double* const* group_values, const size_t* group_sizes, size_t n_groups,
    EKBoxplotOptions opts
);
```

- Python: `ekplots.boxplot(groups: dict[str, list[float]])`
- JS: `ekplots.boxplot(groups, { chartId })`

## Relationship

### 12. Scatter

Two continuous variables, one point per observation — the chart for
"do these two things actually correlate," before trusting any clustering
or trend line built on top of them.

**SurveySync relevance:** dwell_ms vs. scroll_pct, one point per
session, colored by cluster — the direct visual check for "do these
clusters actually separate in the raw data, or did KMeans find noise."
Nothing in the product currently lets you eyeball that; you only see the
derived key_drivers, not the underlying scatter.

```c
typedef struct {
    double width, height;
    double point_radius;
} EKScatterOptions;

typedef struct {
    EKPoint* points;
    size_t n;
    EKBounds bounds;
} EKScatterLayout;

EKScatterLayout ekplots_scatter_layout(const double* x, const double* y, size_t n, EKScatterOptions opts);
```

- Python: `ekplots.scatter(x, y, labels=None)`
- JS: `ekplots.scatter(x, y, { labels, chartId })`

### 13. Bubble

A scatter plot with a third variable encoded as point size.

**SurveySync relevance:** the closest 1:1 match of all 15 to code that
already exists — `BubbleMap.tsx`, shipped this session, is a specialized
circle-packing bubble layout (pages sized by traffic volume). A general
`ekplots.bubble()` is the more reusable, less bespoke version of the same
idea.

```c
typedef struct {
    double width, height;
    double min_r, max_r;   // pixel radius range the size dimension maps into
} EKBubbleOptions;

typedef struct {
    EKBubble* bubbles;   // x, y, r — r already mapped into [min_r, max_r]
    size_t n;
    EKBounds bounds;
} EKBubbleLayout;

EKBubbleLayout ekplots_bubble_layout(
    const double* x, const double* y, const double* size, size_t n,
    EKBubbleOptions opts
);
```

- Python: `ekplots.bubble(x, y, size, labels=None)`
- JS: `ekplots.bubble(x, y, size, { labels, chartId })`

## Matrix & multivariate

### 14. Heatmap

Magnitude across two categorical axes at once — a grid of cells, shaded
by value.

**SurveySync relevance:** Flow.tsx's transition matrix IS a heatmap
already, hand-rolled as a raw HTML `<table>` with a one-off `heatColor()`
function computing `rgba()` strings inline. `ekplots.heatmap()` would
replace that bespoke code with the library's general version — the
single most direct "this should just be ekplots" candidate in the set.

```c
typedef struct {
    double width, height;
    double cell_gap;
} EKHeatmapOptions;

typedef struct {
    EKRect* cells;    // n_rows * n_cols, row-major
    size_t n_rows, n_cols;
    double value_min, value_max;   // for the caller's color-scale mapping
} EKHeatmapLayout;

EKHeatmapLayout ekplots_heatmap_layout(
    const double* values, size_t n_rows, size_t n_cols,
    EKHeatmapOptions opts
);
```

- Python: `ekplots.heatmap(matrix, row_labels=None, col_labels=None)`
- JS: `ekplots.heatmap(matrix, { rowLabels, colLabels, chartId })`

### 15. Radar

Several variables plotted as axes radiating from a center, one closed
shape per entity being compared — the chart for "how does A differ from
B across many dimensions at once," not just one.

**SurveySync relevance:** comparing two clusters' full behavioral profile
at a glance — dwell, scroll depth, clicks, rage-clicks, idle time — all
on one shape per cluster, overlaid. `key_drivers` currently lists these
as flat text per cluster ("high dwell_ms, low scroll_pct"); a radar
chart is the natural visual form for exactly that comparison, and is the
second-best fit in the set after funnel.

```c
typedef struct {
    double cx, cy, r;
    size_t n_axes;
} EKRadarOptions;

typedef struct {
    EKPoint* axis_ticks;      // n_axes points — outer ring positions, for spokes/labels
    EKPoint* series_points;   // n_axes points — the shape for ONE series' values
    size_t n_axes;
} EKRadarLayout;

EKRadarLayout ekplots_radar_layout(const double* values, size_t n_axes, EKRadarOptions opts);
```

- Python: `ekplots.radar(values, axis_labels=None)`
- JS: `ekplots.radar(values, { axisLabels, chartId })`

---

## What's not in this spec

- **Rendering code.** Every `draw()` mentioned above is unimplemented —
  this document only fixes the geometry contract each one has to satisfy.
- **The WASM build.** Emscripten isn't installed in the environment this
  spec was written in — the JS binding's compile step is documented, not
  yet run.
- **Color, legends, axis label rendering, tooltips.** All renderer
  concerns, deliberately kept out of the C core per the architecture
  section above. These get designed per-language, not per-plot.
