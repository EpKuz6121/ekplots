/* WASM export shim — one boxed wrapper per real ekplots_<name>_layout().
 *
 * Two ABI details this file exists to sidestep entirely rather than
 * rely on JS correctly replicating:
 *
 * 1. OUTPUT: a C function returning a struct BY VALUE larger than a
 *    couple of registers gets lowered to an implicit hidden first
 *    parameter (a pointer to caller-allocated space the callee writes
 *    into) — compiler-internal, not something ekplots.js should depend
 *    on implicitly. Every function here makes that output pointer an
 *    EXPLICIT, visible parameter instead.
 *
 * 2. INPUT: passing an Options struct BY VALUE as an argument (not a
 *    return) gets lowered differently — wasm32-emscripten's ABI
 *    flattens small by-value struct arguments into individual scalar
 *    WASM parameters, and the exact flattening depends on the struct's
 *    field layout. Hand-replicating that correctly from JS for 13
 *    differently-shaped Options structs is real risk for zero benefit.
 *    Every Options parameter here is a pointer instead — ekplots.js
 *    writes the struct into WASM memory at a known offset layout
 *    (confirmed via introspect.c) and passes one pointer, no flattening
 *    guesswork on either side.
 *
 * Every function below is still a one-line pass-through to the real
 * computation in ekplots.c — same geometry, same math, just an explicit
 * calling convention instead of an implicit one.
 */
#include "../python/ekplots/native/ekplots.h"

void ekplots_bar_layout_boxed(const double* values, size_t n, const EKBarOptions* opts, EKBarLayout* out) {
    *out = ekplots_bar_layout(values, n, *opts);
}

void ekplots_stacked_bar_layout_boxed(
    const double* const* series_values, size_t n_series, size_t n_categories,
    const EKStackedBarOptions* opts, EKStackedBarLayout* out
) {
    *out = ekplots_stacked_bar_layout(series_values, n_series, n_categories, *opts);
}

void ekplots_line_layout_boxed(const double* x, const double* y, size_t n, const EKLineOptions* opts, EKLineLayout* out) {
    *out = ekplots_line_layout(x, y, n, *opts);
}

void ekplots_area_layout_boxed(const double* x, const double* y, size_t n, const EKAreaOptions* opts, EKAreaLayout* out) {
    *out = ekplots_area_layout(x, y, n, *opts);
}

void ekplots_stacked_area_layout_boxed(
    const double* x, const double* const* series_y, size_t n_series, size_t n_points,
    const EKStackedAreaOptions* opts, EKStackedAreaLayout* out
) {
    *out = ekplots_stacked_area_layout(x, series_y, n_series, n_points, *opts);
}

void ekplots_pie_layout_boxed(const double* values, size_t n, const EKPieOptions* opts, EKPieLayout* out) {
    *out = ekplots_pie_layout(values, n, *opts);
}

void ekplots_donut_layout_boxed(const double* values, size_t n, const EKDonutOptions* opts, EKDonutLayout* out) {
    *out = ekplots_donut_layout(values, n, *opts);
}

void ekplots_funnel_layout_boxed(const double* values, size_t n, const EKFunnelOptions* opts, EKFunnelLayout* out) {
    *out = ekplots_funnel_layout(values, n, *opts);
}

void ekplots_histogram_layout_boxed(const double* values, size_t n, const EKHistogramOptions* opts, EKHistogramLayout* out) {
    *out = ekplots_histogram_layout(values, n, *opts);
}

void ekplots_boxplot_layout_boxed(
    const double* const* group_values, const size_t* group_sizes, size_t n_groups,
    const EKBoxplotOptions* opts, EKBoxplotLayout* out
) {
    *out = ekplots_boxplot_layout(group_values, group_sizes, n_groups, *opts);
}

void ekplots_scatter_layout_boxed(const double* x, const double* y, size_t n, const EKScatterOptions* opts, EKScatterLayout* out) {
    *out = ekplots_scatter_layout(x, y, n, *opts);
}

void ekplots_bubble_layout_boxed(
    const double* x, const double* y, const double* size, size_t n, const EKBubbleOptions* opts, EKBubbleLayout* out
) {
    *out = ekplots_bubble_layout(x, y, size, n, *opts);
}

void ekplots_heatmap_layout_boxed(
    const double* values, size_t n_rows, size_t n_cols, const EKHeatmapOptions* opts, EKHeatmapLayout* out
) {
    *out = ekplots_heatmap_layout(values, n_rows, n_cols, *opts);
}

void ekplots_radar_layout_boxed(const double* values, size_t n_axes, const EKRadarOptions* opts, EKRadarLayout* out) {
    *out = ekplots_radar_layout(values, n_axes, *opts);
}
