/* ekplots — geometry-only C core. See docs/SPEC.md for the full contract.
 *
 * Every function here takes raw data and returns NUMBERS — rectangle
 * coordinates, arc angles, computed axis bounds. No color, no fonts, no
 * drawing. That split is what lets Python and JS bindings render
 * identically-structured charts without duplicating layout logic twice.
 *
 * Every *Layout struct that owns a malloc'd array has a matching
 * ekplots_<name>_free() — callers must call it or leak memory. Structs
 * that hold only fixed-size/scalar fields (Pie, Radar's fixed arrays
 * excepted) need no free function.
 */
#ifndef EKPLOTS_H
#define EKPLOTS_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Explicit export visibility — required on Windows, where DLL symbols
 * are hidden by default (unlike macOS/Linux .dylib/.so, where every
 * global symbol is exported unless explicitly hidden). Without this,
 * every ekplots_<name>_layout() function compiles fine and the .pyd
 * links fine, but ctypes.CDLL can't find any of them at runtime —
 * a real failure this repo's own Windows CI caught, not a
 * theoretical one. EKPLOTS_BUILDING is defined only by the build
 * itself (not by a consumer including this header), the standard
 * pattern for distinguishing "compiling the DLL" from "linking
 * against it" — though every consumer here is ctypes, never a C
 * caller including this header against a prebuilt import lib, so in
 * practice this always resolves to the export branch. */
#if defined(_WIN32) && defined(EKPLOTS_BUILDING)
#define EKPLOTS_API __declspec(dllexport)
#elif defined(_WIN32)
#define EKPLOTS_API __declspec(dllimport)
#else
#define EKPLOTS_API __attribute__((visibility("default")))
#endif

/* ---- Shared primitives ---- */

typedef struct { double x, y; } EKPoint;
typedef struct { double x, y, w, h; } EKRect;
typedef struct { double x_min, x_max, y_min, y_max; } EKBounds;
typedef struct { double cx, cy, r, start_angle, end_angle; } EKArc;
typedef struct { double x, y, r; } EKBubble;

/* ================= 1. Bar (also serves 2. Horizontal Bar) ================= */

typedef struct {
    double width, height;
    double bar_gap;   /* 0-1, fraction of each slot that's gap */
    int horizontal;    /* 0 = vertical bars, 1 = horizontal */
} EKBarOptions;

typedef struct {
    EKRect* bars;
    size_t n;
    EKBounds bounds;
} EKBarLayout;

EKPLOTS_API EKBarLayout ekplots_bar_layout(const double* values, size_t n, EKBarOptions opts);
EKPLOTS_API void ekplots_bar_free(EKBarLayout* layout);

/* ================= 3. Stacked Bar ================= */

typedef struct {
    double width, height;
    double bar_gap;
    size_t n_series;
} EKStackedBarOptions;

typedef struct {
    EKRect* segments;   /* n_categories * n_series rects, row-major (category-major) */
    size_t n_categories, n_series;
    EKBounds bounds;
} EKStackedBarLayout;

EKPLOTS_API EKStackedBarLayout ekplots_stacked_bar_layout(
    const double* const* series_values, size_t n_series, size_t n_categories,
    EKStackedBarOptions opts
);
EKPLOTS_API void ekplots_stacked_bar_free(EKStackedBarLayout* layout);

/* ================= 4. Line ================= */

typedef struct {
    double width, height;
    int smooth;   /* 0 = straight segments, 1 = monotone cubic (Fritsch-Carlson) */
} EKLineOptions;

typedef struct {
    EKPoint* points;
    size_t n;
    EKBounds bounds;
} EKLineLayout;

EKPLOTS_API EKLineLayout ekplots_line_layout(const double* x, const double* y, size_t n, EKLineOptions opts);
EKPLOTS_API void ekplots_line_free(EKLineLayout* layout);

/* ================= 5. Area ================= */

typedef struct {
    double width, height;
    double baseline;   /* value the fill closes down to, usually 0 */
} EKAreaOptions;

typedef struct {
    EKPoint* points;     /* top edge of the fill */
    size_t n;
    double baseline_y;   /* pixel y of the baseline, for closing the polygon */
    EKBounds bounds;
} EKAreaLayout;

EKPLOTS_API EKAreaLayout ekplots_area_layout(const double* x, const double* y, size_t n, EKAreaOptions opts);
EKPLOTS_API void ekplots_area_free(EKAreaLayout* layout);

/* ================= 6. Stacked Area ================= */

typedef struct {
    double width, height;
} EKStackedAreaOptions;

typedef struct {
    EKPoint* bands;   /* n_series * n_points * 2 (bottom then top per series), flattened */
    size_t n_series, n_points;
    EKBounds bounds;
} EKStackedAreaLayout;

EKPLOTS_API EKStackedAreaLayout ekplots_stacked_area_layout(
    const double* x, const double* const* series_y, size_t n_series, size_t n_points,
    EKStackedAreaOptions opts
);
EKPLOTS_API void ekplots_stacked_area_free(EKStackedAreaLayout* layout);

/* ================= 7. Pie (also used by 8. Donut) ================= */

typedef struct { double cx, cy, r; } EKPieOptions;

typedef struct {
    EKArc* slices;
    size_t n;
} EKPieLayout;

EKPLOTS_API EKPieLayout ekplots_pie_layout(const double* values, size_t n, EKPieOptions opts);
EKPLOTS_API void ekplots_pie_free(EKPieLayout* layout);

/* ================= 8. Donut ================= */

typedef struct { double cx, cy, r, inner_r; } EKDonutOptions;

typedef struct {
    EKArc* slices;    /* same meaning as EKPieLayout; r is the OUTER radius */
    size_t n;
    double inner_r;
} EKDonutLayout;

EKPLOTS_API EKDonutLayout ekplots_donut_layout(const double* values, size_t n, EKDonutOptions opts);
EKPLOTS_API void ekplots_donut_free(EKDonutLayout* layout);

/* ================= 9. Funnel ================= */

typedef struct {
    double width, height;
    double stage_gap;
} EKFunnelOptions;

typedef struct {
    EKPoint trapezoid[4];   /* the tapered stage shape, clockwise from top-left */
    double value, pct_of_first, pct_of_previous;
} EKFunnelStage;

typedef struct {
    EKFunnelStage* stages;
    size_t n;
} EKFunnelLayout;

EKPLOTS_API EKFunnelLayout ekplots_funnel_layout(const double* values, size_t n, EKFunnelOptions opts);
EKPLOTS_API void ekplots_funnel_free(EKFunnelLayout* layout);

/* ================= 10. Histogram ================= */

typedef struct {
    double width, height;
    size_t n_bins;   /* 0 = auto (Sturges' rule) */
} EKHistogramOptions;

typedef struct {
    EKRect* bins;
    size_t n_bins;
    double* bin_edges;   /* n_bins + 1 values */
    EKBounds bounds;
} EKHistogramLayout;

EKPLOTS_API EKHistogramLayout ekplots_histogram_layout(const double* values, size_t n, EKHistogramOptions opts);
EKPLOTS_API void ekplots_histogram_free(EKHistogramLayout* layout);

/* ================= 11. Box Plot ================= */

typedef struct {
    double width, height;
    double box_width;   /* fraction of each group's slot */
} EKBoxplotOptions;

typedef struct {
    double min, q1, median, q3, max;
    double* outliers;
    size_t n_outliers;
    EKRect box;              /* q1 to q3 */
    EKPoint whisker_low, whisker_high;
} EKBoxplotStats;

typedef struct {
    EKBoxplotStats* groups;
    size_t n_groups;
    EKBounds bounds;
} EKBoxplotLayout;

EKPLOTS_API EKBoxplotLayout ekplots_boxplot_layout(
    const double* const* group_values, const size_t* group_sizes, size_t n_groups,
    EKBoxplotOptions opts
);
EKPLOTS_API void ekplots_boxplot_free(EKBoxplotLayout* layout);

/* ================= 12. Scatter ================= */

typedef struct {
    double width, height;
    double point_radius;
} EKScatterOptions;

typedef struct {
    EKPoint* points;
    size_t n;
    EKBounds bounds;
} EKScatterLayout;

EKPLOTS_API EKScatterLayout ekplots_scatter_layout(const double* x, const double* y, size_t n, EKScatterOptions opts);
EKPLOTS_API void ekplots_scatter_free(EKScatterLayout* layout);

/* ================= 13. Bubble ================= */

typedef struct {
    double width, height;
    double min_r, max_r;   /* pixel radius range the size dimension maps into */
} EKBubbleOptions;

typedef struct {
    EKBubble* bubbles;   /* x, y, r — r already mapped into [min_r, max_r] */
    size_t n;
    EKBounds bounds;
} EKBubbleLayout;

EKPLOTS_API EKBubbleLayout ekplots_bubble_layout(
    const double* x, const double* y, const double* size, size_t n,
    EKBubbleOptions opts
);
EKPLOTS_API void ekplots_bubble_free(EKBubbleLayout* layout);

/* ================= 14. Heatmap ================= */

typedef struct {
    double width, height;
    double cell_gap;
} EKHeatmapOptions;

typedef struct {
    EKRect* cells;    /* n_rows * n_cols, row-major */
    size_t n_rows, n_cols;
    double value_min, value_max;
} EKHeatmapLayout;

EKPLOTS_API EKHeatmapLayout ekplots_heatmap_layout(
    const double* values, size_t n_rows, size_t n_cols,
    EKHeatmapOptions opts
);
EKPLOTS_API void ekplots_heatmap_free(EKHeatmapLayout* layout);

/* ================= 15. Radar ================= */

typedef struct {
    double cx, cy, r;
    size_t n_axes;
} EKRadarOptions;

typedef struct {
    EKPoint* axis_ticks;      /* n_axes points — outer ring positions */
    EKPoint* series_points;   /* n_axes points — the shape for ONE series' values */
    size_t n_axes;
} EKRadarLayout;

EKPLOTS_API EKRadarLayout ekplots_radar_layout(const double* values, size_t n_axes, EKRadarOptions opts);
EKPLOTS_API void ekplots_radar_free(EKRadarLayout* layout);

#ifdef __cplusplus
}
#endif

#endif /* EKPLOTS_H */
