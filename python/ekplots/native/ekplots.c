/* ekplots — geometry-only C core. See ekplots.h and docs/SPEC.md.
 *
 * COORDINATE CONVENTION: every layout function returns geometry in a
 * y-UP cartesian system, origin at the bottom-left of the logical
 * `width x height` canvas — the same convention matplotlib already uses
 * natively. A Canvas2D renderer (y-down) is responsible for flipping y at
 * draw time; that's a renderer concern, not a layout one, per the
 * "C core never draws, never assumes a screen" rule in the spec.
 */
#include "ekplots.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ---- shared helpers ---- */

static int ek_cmp_double(const void* a, const void* b) {
    double da = *(const double*)a, db = *(const double*)b;
    return (da > db) - (da < db);
}

/* Linear-interpolation quantile — same method numpy's default uses, so a
 * Python caller's own numpy.percentile() sanity-checks against this. */
static double ek_quantile_sorted(const double* sorted, size_t n, double q) {
    if (n == 1) return sorted[0];
    double pos = q * (double)(n - 1);
    size_t lo = (size_t)floor(pos);
    size_t hi = (size_t)ceil(pos);
    if (hi >= n) hi = n - 1;
    double frac = pos - (double)lo;
    return sorted[lo] + (sorted[hi] - sorted[lo]) * frac;
}

/* ================= 1 & 2. Bar / Horizontal Bar ================= */

EKBarLayout ekplots_bar_layout(const double* values, size_t n, EKBarOptions opts) {
    EKBarLayout out = {0};
    if (n == 0) return out;

    double y_min = 0.0, y_max = 0.0;
    for (size_t i = 0; i < n; i++) {
        if (values[i] < y_min) y_min = values[i];
        if (values[i] > y_max) y_max = values[i];
    }
    double range = (y_max - y_min) > 0 ? (y_max - y_min) : 1.0;

    EKRect* bars = malloc(n * sizeof(EKRect));
    double slot_w = opts.width / (double)n;
    double bar_w = slot_w * (1.0 - opts.bar_gap);
    double pad = (slot_w - bar_w) / 2.0;

    for (size_t i = 0; i < n; i++) {
        double zero_h = (0.0 - y_min) / range * opts.height;
        double val_h = (values[i] - y_min) / range * opts.height;
        double bx = (double)i * slot_w + pad;
        double by, bh;
        if (val_h >= zero_h) { by = zero_h; bh = val_h - zero_h; }
        else { by = val_h; bh = zero_h - val_h; }

        if (opts.horizontal) {
            /* category axis becomes vertical, value axis becomes horizontal */
            bars[i] = (EKRect){ by, bx, bh, bar_w };
        } else {
            bars[i] = (EKRect){ bx, by, bar_w, bh };
        }
    }

    out.bars = bars;
    out.n = n;
    out.bounds = (EKBounds){ 0.0, (double)n, y_min, y_max };
    return out;
}

void ekplots_bar_free(EKBarLayout* layout) {
    if (!layout) return;
    free(layout->bars);
    layout->bars = NULL;
    layout->n = 0;
}

/* ================= 3. Stacked Bar ================= */

EKStackedBarLayout ekplots_stacked_bar_layout(
    const double* const* series_values, size_t n_series, size_t n_categories,
    EKStackedBarOptions opts
) {
    EKStackedBarLayout out = {0};
    if (n_series == 0 || n_categories == 0) return out;

    double y_max = 0.0;
    for (size_t c = 0; c < n_categories; c++) {
        double total = 0.0;
        for (size_t s = 0; s < n_series; s++) total += series_values[s][c];
        if (total > y_max) y_max = total;
    }
    double range = y_max > 0 ? y_max : 1.0;

    EKRect* segments = malloc(n_categories * n_series * sizeof(EKRect));
    double slot_w = opts.width / (double)n_categories;
    double bar_w = slot_w * (1.0 - opts.bar_gap);
    double pad = (slot_w - bar_w) / 2.0;

    for (size_t c = 0; c < n_categories; c++) {
        double cum = 0.0;
        double bx = (double)c * slot_w + pad;
        for (size_t s = 0; s < n_series; s++) {
            double v = series_values[s][c];
            double y0 = cum / range * opts.height;
            double y1 = (cum + v) / range * opts.height;
            segments[c * n_series + s] = (EKRect){ bx, y0, bar_w, y1 - y0 };
            cum += v;
        }
    }

    out.segments = segments;
    out.n_categories = n_categories;
    out.n_series = n_series;
    out.bounds = (EKBounds){ 0.0, (double)n_categories, 0.0, y_max };
    return out;
}

void ekplots_stacked_bar_free(EKStackedBarLayout* layout) {
    if (!layout) return;
    free(layout->segments);
    layout->segments = NULL;
    layout->n_categories = layout->n_series = 0;
}

/* ================= 4. Line ================= */

EKLineLayout ekplots_line_layout(const double* x, const double* y, size_t n, EKLineOptions opts) {
    EKLineLayout out = {0};
    if (n == 0) return out;
    /* NOTE: opts.smooth is not yet implemented in v0.1 — monotone cubic
     * interpolation is real future work, not faked here. Points are
     * always straight-segment regardless of the flag. */

    double x_min = x[0], x_max = x[0], y_min = y[0], y_max = y[0];
    for (size_t i = 1; i < n; i++) {
        if (x[i] < x_min) x_min = x[i];
        if (x[i] > x_max) x_max = x[i];
        if (y[i] < y_min) y_min = y[i];
        if (y[i] > y_max) y_max = y[i];
    }
    double x_range = (x_max - x_min) > 0 ? (x_max - x_min) : 1.0;
    double y_range = (y_max - y_min) > 0 ? (y_max - y_min) : 1.0;

    EKPoint* points = malloc(n * sizeof(EKPoint));
    for (size_t i = 0; i < n; i++) {
        points[i].x = (x[i] - x_min) / x_range * opts.width;
        points[i].y = (y[i] - y_min) / y_range * opts.height;
    }

    out.points = points;
    out.n = n;
    out.bounds = (EKBounds){ x_min, x_max, y_min, y_max };
    return out;
}

void ekplots_line_free(EKLineLayout* layout) {
    if (!layout) return;
    free(layout->points);
    layout->points = NULL;
    layout->n = 0;
}

/* ================= 5. Area ================= */

EKAreaLayout ekplots_area_layout(const double* x, const double* y, size_t n, EKAreaOptions opts) {
    EKAreaLayout out = {0};
    if (n == 0) return out;

    double x_min = x[0], x_max = x[0], y_min = y[0], y_max = y[0];
    for (size_t i = 1; i < n; i++) {
        if (x[i] < x_min) x_min = x[i];
        if (x[i] > x_max) x_max = x[i];
        if (y[i] < y_min) y_min = y[i];
        if (y[i] > y_max) y_max = y[i];
    }
    /* baseline participates in the y-domain so the fill never clips off-canvas */
    if (opts.baseline < y_min) y_min = opts.baseline;
    if (opts.baseline > y_max) y_max = opts.baseline;

    double x_range = (x_max - x_min) > 0 ? (x_max - x_min) : 1.0;
    double y_range = (y_max - y_min) > 0 ? (y_max - y_min) : 1.0;

    EKPoint* points = malloc(n * sizeof(EKPoint));
    for (size_t i = 0; i < n; i++) {
        points[i].x = (x[i] - x_min) / x_range * opts.width;
        points[i].y = (y[i] - y_min) / y_range * opts.height;
    }

    out.points = points;
    out.n = n;
    out.baseline_y = (opts.baseline - y_min) / y_range * opts.height;
    out.bounds = (EKBounds){ x_min, x_max, y_min, y_max };
    return out;
}

void ekplots_area_free(EKAreaLayout* layout) {
    if (!layout) return;
    free(layout->points);
    layout->points = NULL;
    layout->n = 0;
}

/* ================= 6. Stacked Area ================= */

EKStackedAreaLayout ekplots_stacked_area_layout(
    const double* x, const double* const* series_y, size_t n_series, size_t n_points,
    EKStackedAreaOptions opts
) {
    EKStackedAreaLayout out = {0};
    if (n_series == 0 || n_points == 0) return out;

    double x_min = x[0], x_max = x[0];
    for (size_t p = 1; p < n_points; p++) {
        if (x[p] < x_min) x_min = x[p];
        if (x[p] > x_max) x_max = x[p];
    }
    double x_range = (x_max - x_min) > 0 ? (x_max - x_min) : 1.0;

    double y_max = 0.0;
    for (size_t p = 0; p < n_points; p++) {
        double total = 0.0;
        for (size_t s = 0; s < n_series; s++) total += series_y[s][p];
        if (total > y_max) y_max = total;
    }
    double y_range = y_max > 0 ? y_max : 1.0;

    EKPoint* bands = malloc(n_series * n_points * 2 * sizeof(EKPoint));
    double* running = calloc(n_points, sizeof(double));
    for (size_t s = 0; s < n_series; s++) {
        for (size_t p = 0; p < n_points; p++) {
            double bottom = running[p];
            double top = bottom + series_y[s][p];
            running[p] = top;
            size_t base = (s * n_points + p) * 2;
            double px = (x[p] - x_min) / x_range * opts.width;
            bands[base + 0] = (EKPoint){ px, bottom / y_range * opts.height };
            bands[base + 1] = (EKPoint){ px, top / y_range * opts.height };
        }
    }
    free(running);

    out.bands = bands;
    out.n_series = n_series;
    out.n_points = n_points;
    out.bounds = (EKBounds){ x_min, x_max, 0.0, y_max };
    return out;
}

void ekplots_stacked_area_free(EKStackedAreaLayout* layout) {
    if (!layout) return;
    free(layout->bands);
    layout->bands = NULL;
    layout->n_series = layout->n_points = 0;
}

/* ================= 7. Pie (also used by 8. Donut) ================= */

EKPieLayout ekplots_pie_layout(const double* values, size_t n, EKPieOptions opts) {
    EKPieLayout out = {0};
    if (n == 0) return out;

    double total = 0.0;
    for (size_t i = 0; i < n; i++) total += values[i];
    if (total <= 0) total = 1.0;

    EKArc* slices = malloc(n * sizeof(EKArc));
    double angle = -M_PI / 2.0; /* start at 12 o'clock, sweep clockwise */
    for (size_t i = 0; i < n; i++) {
        double sweep = (values[i] / total) * 2.0 * M_PI;
        slices[i] = (EKArc){ opts.cx, opts.cy, opts.r, angle, angle + sweep };
        angle += sweep;
    }

    out.slices = slices;
    out.n = n;
    return out;
}

void ekplots_pie_free(EKPieLayout* layout) {
    if (!layout) return;
    free(layout->slices);
    layout->slices = NULL;
    layout->n = 0;
}

/* ================= 8. Donut ================= */

EKDonutLayout ekplots_donut_layout(const double* values, size_t n, EKDonutOptions opts) {
    EKDonutLayout out = {0};
    if (n == 0) return out;

    EKPieOptions pie_opts = { opts.cx, opts.cy, opts.r };
    EKPieLayout pie = ekplots_pie_layout(values, n, pie_opts);

    out.slices = pie.slices;
    out.n = pie.n;
    out.inner_r = opts.inner_r;
    return out;
}

void ekplots_donut_free(EKDonutLayout* layout) {
    if (!layout) return;
    free(layout->slices);
    layout->slices = NULL;
    layout->n = 0;
}

/* ================= 9. Funnel ================= */

EKFunnelLayout ekplots_funnel_layout(const double* values, size_t n, EKFunnelOptions opts) {
    EKFunnelLayout out = {0};
    if (n == 0) return out;

    double max_v = values[0];
    for (size_t i = 1; i < n; i++) if (values[i] > max_v) max_v = values[i];
    if (max_v <= 0) max_v = 1.0;

    EKFunnelStage* stages = malloc(n * sizeof(EKFunnelStage));
    double n_gaps = (n > 0) ? (double)(n - 1) : 0.0;
    double stage_h = (opts.height - opts.stage_gap * n_gaps) / (double)n;

    for (size_t i = 0; i < n; i++) {
        double top_w = (values[i] / max_v) * opts.width;
        double bottom_v = (i + 1 < n) ? values[i + 1] : values[i];
        double bottom_w = (bottom_v / max_v) * opts.width;

        double y_top = (double)i * (stage_h + opts.stage_gap);
        double y_bot = y_top + stage_h;
        double top_x0 = (opts.width - top_w) / 2.0;
        double bot_x0 = (opts.width - bottom_w) / 2.0;

        EKFunnelStage st;
        st.trapezoid[0] = (EKPoint){ top_x0, y_top };
        st.trapezoid[1] = (EKPoint){ top_x0 + top_w, y_top };
        st.trapezoid[2] = (EKPoint){ bot_x0 + bottom_w, y_bot };
        st.trapezoid[3] = (EKPoint){ bot_x0, y_bot };
        st.value = values[i];
        st.pct_of_first = (values[0] > 0) ? values[i] / values[0] : 0.0;
        st.pct_of_previous = (i == 0) ? 1.0 : (values[i - 1] > 0 ? values[i] / values[i - 1] : 0.0);
        stages[i] = st;
    }

    out.stages = stages;
    out.n = n;
    return out;
}

void ekplots_funnel_free(EKFunnelLayout* layout) {
    if (!layout) return;
    free(layout->stages);
    layout->stages = NULL;
    layout->n = 0;
}

/* ================= 10. Histogram ================= */

EKHistogramLayout ekplots_histogram_layout(const double* values, size_t n, EKHistogramOptions opts) {
    EKHistogramLayout out = {0};
    if (n == 0) return out;

    size_t n_bins = opts.n_bins;
    if (n_bins == 0) {
        double bins_f = ceil(log2((double)n) + 1.0); /* Sturges' rule */
        n_bins = (bins_f < 1.0) ? 1 : (size_t)bins_f;
    }

    double v_min = values[0], v_max = values[0];
    for (size_t i = 1; i < n; i++) {
        if (values[i] < v_min) v_min = values[i];
        if (values[i] > v_max) v_max = values[i];
    }
    double range = (v_max - v_min) > 0 ? (v_max - v_min) : 1.0;

    double* edges = malloc((n_bins + 1) * sizeof(double));
    for (size_t b = 0; b <= n_bins; b++) {
        edges[b] = v_min + range * (double)b / (double)n_bins;
    }

    size_t* counts = calloc(n_bins, sizeof(size_t));
    for (size_t i = 0; i < n; i++) {
        size_t b = (size_t)(((values[i] - v_min) / range) * (double)n_bins);
        if (b >= n_bins) b = n_bins - 1; /* the max value lands in the last bin, not off the end */
        counts[b]++;
    }

    size_t max_count = 0;
    for (size_t b = 0; b < n_bins; b++) if (counts[b] > max_count) max_count = counts[b];
    if (max_count == 0) max_count = 1;

    EKRect* bins = malloc(n_bins * sizeof(EKRect));
    double bin_w = opts.width / (double)n_bins;
    for (size_t b = 0; b < n_bins; b++) {
        double h = (double)counts[b] / (double)max_count * opts.height;
        bins[b] = (EKRect){ (double)b * bin_w, 0.0, bin_w, h };
    }
    free(counts);

    out.bins = bins;
    out.n_bins = n_bins;
    out.bin_edges = edges;
    out.bounds = (EKBounds){ v_min, v_max, 0.0, (double)max_count };
    return out;
}

void ekplots_histogram_free(EKHistogramLayout* layout) {
    if (!layout) return;
    free(layout->bins);
    free(layout->bin_edges);
    layout->bins = NULL;
    layout->bin_edges = NULL;
    layout->n_bins = 0;
}

/* ================= 11. Box Plot ================= */

EKBoxplotLayout ekplots_boxplot_layout(
    const double* const* group_values, const size_t* group_sizes, size_t n_groups,
    EKBoxplotOptions opts
) {
    EKBoxplotLayout out = {0};
    if (n_groups == 0) return out;

    EKBoxplotStats* groups = malloc(n_groups * sizeof(EKBoxplotStats));
    double* whisker_lo_raw = malloc(n_groups * sizeof(double));
    double* whisker_hi_raw = malloc(n_groups * sizeof(double));
    double y_min = 1e300, y_max = -1e300;

    /* pass 1: real quartile/whisker/outlier math, in RAW data units */
    for (size_t g = 0; g < n_groups; g++) {
        size_t n = group_sizes[g];
        double* sorted = malloc(n * sizeof(double));
        memcpy(sorted, group_values[g], n * sizeof(double));
        qsort(sorted, n, sizeof(double), ek_cmp_double);

        double q1 = ek_quantile_sorted(sorted, n, 0.25);
        double median = ek_quantile_sorted(sorted, n, 0.5);
        double q3 = ek_quantile_sorted(sorted, n, 0.75);
        double iqr = q3 - q1;
        double lower_fence = q1 - 1.5 * iqr;
        double upper_fence = q3 + 1.5 * iqr;

        double whisker_lo = sorted[0], whisker_hi = sorted[n - 1];
        for (size_t i = 0; i < n; i++) {
            if (sorted[i] >= lower_fence) { whisker_lo = sorted[i]; break; }
        }
        for (size_t i = n; i-- > 0; ) {
            if (sorted[i] <= upper_fence) { whisker_hi = sorted[i]; break; }
        }

        size_t n_outliers = 0;
        double* outliers = malloc(n * sizeof(double)); /* worst case: every point is an outlier */
        for (size_t i = 0; i < n; i++) {
            if (sorted[i] < lower_fence || sorted[i] > upper_fence) {
                outliers[n_outliers++] = sorted[i];
            }
        }

        if (sorted[0] < y_min) y_min = sorted[0];
        if (sorted[n - 1] > y_max) y_max = sorted[n - 1];

        groups[g].min = sorted[0];
        groups[g].q1 = q1;
        groups[g].median = median;
        groups[g].q3 = q3;
        groups[g].max = sorted[n - 1];
        groups[g].outliers = outliers;
        groups[g].n_outliers = n_outliers;
        whisker_lo_raw[g] = whisker_lo;
        whisker_hi_raw[g] = whisker_hi;

        free(sorted);
    }

    double y_range = (y_max - y_min) > 0 ? (y_max - y_min) : 1.0;
    double slot_w = opts.width / (double)n_groups;
    double box_w = slot_w * opts.box_width;

    /* pass 2: scale box/whisker geometry into [0,width]x[0,height] logical
     * space — min/q1/median/q3/max/outliers stay in raw data units on
     * purpose, so a caller can still label the real values. */
    for (size_t g = 0; g < n_groups; g++) {
        double gx = (double)g * slot_w + (slot_w - box_w) / 2.0;
        double q1_y = (groups[g].q1 - y_min) / y_range * opts.height;
        double q3_y = (groups[g].q3 - y_min) / y_range * opts.height;

        groups[g].box = (EKRect){ gx, q1_y, box_w, q3_y - q1_y };
        groups[g].whisker_low = (EKPoint){
            gx + box_w / 2.0, (whisker_lo_raw[g] - y_min) / y_range * opts.height
        };
        groups[g].whisker_high = (EKPoint){
            gx + box_w / 2.0, (whisker_hi_raw[g] - y_min) / y_range * opts.height
        };
    }
    free(whisker_lo_raw);
    free(whisker_hi_raw);

    out.groups = groups;
    out.n_groups = n_groups;
    out.bounds = (EKBounds){ 0.0, (double)n_groups, y_min, y_max };
    return out;
}

void ekplots_boxplot_free(EKBoxplotLayout* layout) {
    if (!layout) return;
    for (size_t g = 0; g < layout->n_groups; g++) {
        free(layout->groups[g].outliers);
    }
    free(layout->groups);
    layout->groups = NULL;
    layout->n_groups = 0;
}

/* ================= 12. Scatter ================= */

EKScatterLayout ekplots_scatter_layout(const double* x, const double* y, size_t n, EKScatterOptions opts) {
    EKScatterLayout out = {0};
    if (n == 0) return out;

    double x_min = x[0], x_max = x[0], y_min = y[0], y_max = y[0];
    for (size_t i = 1; i < n; i++) {
        if (x[i] < x_min) x_min = x[i];
        if (x[i] > x_max) x_max = x[i];
        if (y[i] < y_min) y_min = y[i];
        if (y[i] > y_max) y_max = y[i];
    }
    double x_range = (x_max - x_min) > 0 ? (x_max - x_min) : 1.0;
    double y_range = (y_max - y_min) > 0 ? (y_max - y_min) : 1.0;

    EKPoint* points = malloc(n * sizeof(EKPoint));
    for (size_t i = 0; i < n; i++) {
        points[i].x = (x[i] - x_min) / x_range * opts.width;
        points[i].y = (y[i] - y_min) / y_range * opts.height;
    }

    out.points = points;
    out.n = n;
    out.bounds = (EKBounds){ x_min, x_max, y_min, y_max };
    return out;
}

void ekplots_scatter_free(EKScatterLayout* layout) {
    if (!layout) return;
    free(layout->points);
    layout->points = NULL;
    layout->n = 0;
}

/* ================= 13. Bubble ================= */

EKBubbleLayout ekplots_bubble_layout(
    const double* x, const double* y, const double* size, size_t n,
    EKBubbleOptions opts
) {
    EKBubbleLayout out = {0};
    if (n == 0) return out;

    double x_min = x[0], x_max = x[0], y_min = y[0], y_max = y[0];
    double s_min = size[0], s_max = size[0];
    for (size_t i = 1; i < n; i++) {
        if (x[i] < x_min) x_min = x[i];
        if (x[i] > x_max) x_max = x[i];
        if (y[i] < y_min) y_min = y[i];
        if (y[i] > y_max) y_max = y[i];
        if (size[i] < s_min) s_min = size[i];
        if (size[i] > s_max) s_max = size[i];
    }
    double x_range = (x_max - x_min) > 0 ? (x_max - x_min) : 1.0;
    double y_range = (y_max - y_min) > 0 ? (y_max - y_min) : 1.0;
    double s_range = (s_max - s_min) > 0 ? (s_max - s_min) : 1.0;

    EKBubble* bubbles = malloc(n * sizeof(EKBubble));
    for (size_t i = 0; i < n; i++) {
        /* AREA (not radius) proportional to value — sqrt() here is
         * deliberate. Scaling radius linearly with value is the single
         * most common bubble-chart mistake: it visually exaggerates
         * differences, since the eye perceives AREA, and area grows with
         * radius squared. */
        double t = (size[i] - s_min) / s_range;
        double r = opts.min_r + sqrt(t) * (opts.max_r - opts.min_r);
        bubbles[i] = (EKBubble){
            (x[i] - x_min) / x_range * opts.width,
            (y[i] - y_min) / y_range * opts.height,
            r
        };
    }

    out.bubbles = bubbles;
    out.n = n;
    out.bounds = (EKBounds){ x_min, x_max, y_min, y_max };
    return out;
}

void ekplots_bubble_free(EKBubbleLayout* layout) {
    if (!layout) return;
    free(layout->bubbles);
    layout->bubbles = NULL;
    layout->n = 0;
}

/* ================= 14. Heatmap ================= */

EKHeatmapLayout ekplots_heatmap_layout(
    const double* values, size_t n_rows, size_t n_cols,
    EKHeatmapOptions opts
) {
    EKHeatmapLayout out = {0};
    if (n_rows == 0 || n_cols == 0) return out;

    double v_min = values[0], v_max = values[0];
    for (size_t i = 1; i < n_rows * n_cols; i++) {
        if (values[i] < v_min) v_min = values[i];
        if (values[i] > v_max) v_max = values[i];
    }

    EKRect* cells = malloc(n_rows * n_cols * sizeof(EKRect));
    double cell_w = opts.width / (double)n_cols;
    double cell_h = opts.height / (double)n_rows;

    for (size_t r = 0; r < n_rows; r++) {
        for (size_t c = 0; c < n_cols; c++) {
            double x = (double)c * cell_w + opts.cell_gap / 2.0;
            /* row 0 at the TOP — matching how a matrix is normally read;
             * flip at draw time if a renderer wants row 0 at the bottom. */
            double y = opts.height - (double)(r + 1) * cell_h + opts.cell_gap / 2.0;
            cells[r * n_cols + c] = (EKRect){
                x, y, cell_w - opts.cell_gap, cell_h - opts.cell_gap
            };
        }
    }

    out.cells = cells;
    out.n_rows = n_rows;
    out.n_cols = n_cols;
    out.value_min = v_min;
    out.value_max = v_max;
    return out;
}

void ekplots_heatmap_free(EKHeatmapLayout* layout) {
    if (!layout) return;
    free(layout->cells);
    layout->cells = NULL;
    layout->n_rows = layout->n_cols = 0;
}

/* ================= 15. Radar ================= */

EKRadarLayout ekplots_radar_layout(const double* values, size_t n_axes, EKRadarOptions opts) {
    EKRadarLayout out = {0};
    if (n_axes == 0) return out;

    double v_max = values[0];
    for (size_t i = 1; i < n_axes; i++) if (values[i] > v_max) v_max = values[i];
    if (v_max <= 0) v_max = 1.0;

    EKPoint* axis_ticks = malloc(n_axes * sizeof(EKPoint));
    EKPoint* series_points = malloc(n_axes * sizeof(EKPoint));

    for (size_t i = 0; i < n_axes; i++) {
        double angle = -M_PI / 2.0 + (2.0 * M_PI * (double)i / (double)n_axes);
        axis_ticks[i] = (EKPoint){
            opts.cx + opts.r * cos(angle),
            opts.cy + opts.r * sin(angle)
        };
        double t = values[i] / v_max;
        series_points[i] = (EKPoint){
            opts.cx + opts.r * t * cos(angle),
            opts.cy + opts.r * t * sin(angle)
        };
    }

    out.axis_ticks = axis_ticks;
    out.series_points = series_points;
    out.n_axes = n_axes;
    return out;
}

void ekplots_radar_free(EKRadarLayout* layout) {
    if (!layout) return;
    free(layout->axis_ticks);
    free(layout->series_points);
    layout->axis_ticks = NULL;
    layout->series_points = NULL;
    layout->n_axes = 0;
}
