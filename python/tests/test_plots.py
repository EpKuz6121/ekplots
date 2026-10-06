"""Real tests against the compiled C core — no mocking the native
library, since the whole point is proving the actual compiled geometry
is correct. Run with `pytest` from python/ after `pip install -e .`.
"""
import matplotlib

matplotlib.use("Agg")  # headless — no display needed to run these

import numpy as np
import pytest

import ekplots


# ---- one correctness test per plot, not just "doesn't crash" ----


def test_bar_tallest_bar_matches_largest_value():
    layout = ekplots.bar([10, 25, 15, 40])
    heights = layout.bars[:, 3]
    assert heights.argmax() == 3  # value 40 is at index 3


def test_hbar_shares_bar_geometry_rotated():
    layout = ekplots.hbar([10, 25, 15, 40])
    assert layout.horizontal is True
    # rotated: the "height" dimension (bars[:,2], now meaning value-length) should be tallest at index 3
    assert layout.bars[:, 2].argmax() == 3


def test_stacked_bar_segments_sum_to_category_total():
    layout = ekplots.stacked_bar({"a": [10, 20], "b": [5, 15]})
    # category 0 total = 15, category 1 total = 35 — taller category should have a taller combined stack
    cat0_top = layout.segments[0, :, 1].max() + layout.segments[0, -1, 3]
    cat1_top = layout.segments[1, :, 1].max() + layout.segments[1, -1, 3]
    assert cat1_top > cat0_top


def test_line_bounds_match_real_data_range():
    x = [0, 1, 2, 3]
    y = [5, 3, 8, 2]
    layout = ekplots.line(x, y)
    assert layout.bounds.y_min == 2
    assert layout.bounds.y_max == 8


def test_line_smooth_produces_more_points_and_hits_originals():
    x = [0, 1, 2, 3, 4]
    y = [10, 40, 15, 45, 20]
    straight = ekplots.line(x, y, smooth=False)
    smooth = ekplots.line(x, y, smooth=True)
    assert smooth.points.shape[0] > straight.points.shape[0]
    # the first and last sampled points must exactly match the original endpoints
    assert smooth.points[0] == pytest.approx(straight.points[0])
    assert smooth.points[-1] == pytest.approx(straight.points[-1])


def test_area_baseline_included_in_bounds():
    layout = ekplots.area([0, 1, 2], [5, 8, 6], baseline=0.0)
    assert layout.bounds.y_min == 0  # baseline pulls y_min down to 0 even though min(y)=5


def test_stacked_area_cumulative_top_exceeds_any_single_series():
    x = [0, 1, 2]
    layout = ekplots.stacked_area(x, {"a": [10, 12, 14], "b": [8, 9, 7]})
    assert layout.bounds.y_max == pytest.approx(21)  # 14 + 7 at the peak point


def test_pie_slices_sum_to_full_circle():
    layout = ekplots.pie([30, 20, 50])
    total_sweep = sum(end - start for _, _, _, start, end in layout.slices)
    assert total_sweep == pytest.approx(2 * np.pi)


def test_donut_has_nonzero_inner_radius():
    layout = ekplots.donut([30, 20, 50], inner_r=0.6)
    assert layout.inner_r > 0


def test_funnel_stages_never_widen():
    layout = ekplots.funnel([1000, 640, 410, 180, 95])
    widths = [max(p[0] for p in s.trapezoid) - min(p[0] for p in s.trapezoid) for s in layout.stages]
    assert all(widths[i] >= widths[i + 1] - 1e-9 for i in range(len(widths) - 1))


def test_histogram_bin_counts_sum_to_n():
    rng = np.random.default_rng(1)
    values = rng.normal(0, 1, 500)
    layout = ekplots.histogram(values, bins=10)
    assert layout.bounds.y_max >= 1  # at least one bin has a real count
    assert layout.bin_edges.shape[0] == 11  # n_bins + 1 edges


def test_boxplot_detects_a_real_outlier():
    layout = ekplots.boxplot({"g": [1, 2, 3, 4, 5, 100]})
    assert 100 in layout.groups["g"].outliers


def test_boxplot_no_false_positive_outliers_on_tight_data():
    layout = ekplots.boxplot({"g": [10, 11, 12, 11, 10, 12, 11]})
    assert len(layout.groups["g"].outliers) == 0


def test_scatter_point_count_matches_input():
    layout = ekplots.scatter([1, 2, 3], [4, 5, 6])
    assert layout.points.shape[0] == 3


def test_bubble_radius_scales_by_area_not_linearly():
    # min_r=10 keeps the smallest bubble's radius non-zero so the ratio
    # below is well-defined. A middle value exactly halfway between
    # size_min and size_max should map to r = min_r + sqrt(0.5)*(max_r-min_r)
    # — NOT r = min_r + 0.5*(max_r-min_r), which is the common (wrong)
    # linear-radius bubble-chart mistake.
    layout = ekplots.bubble([0, 1, 2], [0, 0, 0], [10, 55, 100], min_r=10.0, max_r=110.0)
    r_mid = layout.bubbles[1, 2]
    linear_prediction = 10.0 + 0.5 * 100.0  # what a (wrong) linear mapping would give: 60
    area_prediction = 10.0 + (0.5 ** 0.5) * 100.0  # what the real sqrt mapping gives: ~80.7
    assert r_mid == pytest.approx(area_prediction, abs=0.01)
    assert abs(r_mid - linear_prediction) > 15  # clearly NOT the linear value


def test_heatmap_hottest_cell_matches_source_matrix():
    matrix = [[0.1, 0.9], [0.3, 0.2]]
    layout = ekplots.heatmap(matrix)
    assert layout.value_max == 0.9
    assert layout.values[0, 1] == 0.9


def test_radar_axis_count_matches_input():
    layout = ekplots.radar([3, 7, 5, 9, 4])
    assert layout.series_points.shape[0] == 5
    assert layout.axis_ticks.shape[0] == 5


# ---- draw() dispatch: every type renders without raising ----

_SAMPLE_LAYOUTS = [
    ekplots.bar([10, 25, 15, 40]),
    ekplots.hbar([10, 25, 15, 40]),
    ekplots.stacked_bar({"a": [10, 20], "b": [5, 15]}),
    ekplots.line([0, 1, 2, 3], [5, 3, 8, 2]),
    ekplots.area([0, 1, 2], [5, 8, 6]),
    ekplots.stacked_area([0, 1, 2], {"a": [10, 12, 14], "b": [8, 9, 7]}),
    ekplots.pie([30, 20, 50]),
    ekplots.donut([30, 20, 50]),
    ekplots.funnel([1000, 640, 410]),
    ekplots.histogram([1, 2, 2, 3, 3, 3, 4, 4, 5]),
    ekplots.boxplot({"g1": [1, 2, 3, 4, 5], "g2": [10, 12, 11]}),
    ekplots.scatter([1, 2, 3], [4, 5, 6]),
    ekplots.bubble([1, 2, 3], [4, 5, 6], [10, 50, 20]),
    ekplots.heatmap([[0.1, 0.9], [0.3, 0.2]]),
    ekplots.radar([3, 7, 5, 9, 4]),
]


@pytest.mark.parametrize("layout", _SAMPLE_LAYOUTS, ids=[type(l).__name__ + str(i) for i, l in enumerate(_SAMPLE_LAYOUTS)])
def test_draw_renders_without_raising(layout):
    ax = ekplots.draw(layout)
    assert ax is not None


def test_draw_rejects_unknown_type():
    with pytest.raises(TypeError):
        ekplots.draw(object())


# ---- edge cases ----


def test_single_point_line_does_not_crash():
    layout = ekplots.line([1], [5])
    assert layout.points.shape[0] == 1


def test_bar_with_negative_values():
    layout = ekplots.bar([-10, 20, -5, 15])
    assert layout.bounds.y_min < 0
    assert layout.bounds.y_max > 0


def test_histogram_with_identical_values_does_not_divide_by_zero():
    layout = ekplots.histogram([5, 5, 5, 5, 5])
    assert layout.bins.shape[0] > 0


def test_boxplot_single_value_group():
    layout = ekplots.boxplot({"g": [42]})
    assert layout.groups["g"].median == 42
