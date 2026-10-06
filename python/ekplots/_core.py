"""ctypes bindings to the real ekplots C core — loads the compiled
_native*.so built by `pip install -e .` (see setup.py) and exposes one
Python function per plot, matching docs/SPEC.md's call signatures.

Every wrapper here does the same three things: build ctypes arrays from
whatever numpy-friendly input the caller passed, call the C
`ekplots_<name>_layout()` function, and immediately copy the result into
plain numpy arrays on a small Python dataclass — then call the matching
`ekplots_<name>_free()` so the C-side malloc'd memory doesn't leak. A
caller never touches a ctypes pointer directly.
"""
from __future__ import annotations

import ctypes
import glob
import os
from dataclasses import dataclass

import numpy as np


def _load_native() -> ctypes.CDLL:
    pattern = os.path.join(os.path.dirname(__file__), "_native*.so")
    matches = glob.glob(pattern)
    if not matches:
        # Covers the non-macOS suffixes too, in case this ever runs
        # somewhere setuptools named the build output differently.
        pattern = os.path.join(os.path.dirname(__file__), "_native*")
        matches = [m for m in glob.glob(pattern) if not m.endswith((".c", ".h", ".py"))]
    if not matches:
        raise ImportError(
            "ekplots' compiled core (_native*.so) was not found next to "
            f"{__file__} — did `pip install -e .` finish successfully?"
        )
    return ctypes.CDLL(matches[0])


_lib = _load_native()

# ---- Shared primitive structs (mirrors ekplots.h exactly) ----


class EKPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class EKRect(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
        ("w", ctypes.c_double),
        ("h", ctypes.c_double),
    ]


class EKBounds(ctypes.Structure):
    _fields_ = [
        ("x_min", ctypes.c_double),
        ("x_max", ctypes.c_double),
        ("y_min", ctypes.c_double),
        ("y_max", ctypes.c_double),
    ]


class EKArc(ctypes.Structure):
    _fields_ = [
        ("cx", ctypes.c_double),
        ("cy", ctypes.c_double),
        ("r", ctypes.c_double),
        ("start_angle", ctypes.c_double),
        ("end_angle", ctypes.c_double),
    ]


class EKBubble(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double), ("r", ctypes.c_double)]


def _bounds_to_py(b: EKBounds) -> "Bounds":
    return Bounds(b.x_min, b.x_max, b.y_min, b.y_max)


@dataclass
class Bounds:
    x_min: float
    x_max: float
    y_min: float
    y_max: float


def _d_array(values) -> ctypes.Array:
    arr = np.asarray(values, dtype=np.float64)
    return (ctypes.c_double * len(arr))(*arr)


# ================= 1 & 2. Bar / Horizontal Bar =================


class EKBarOptions(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_double),
        ("height", ctypes.c_double),
        ("bar_gap", ctypes.c_double),
        ("horizontal", ctypes.c_int),
    ]


class EKBarLayout(ctypes.Structure):
    _fields_ = [
        ("bars", ctypes.POINTER(EKRect)),
        ("n", ctypes.c_size_t),
        ("bounds", EKBounds),
    ]


_lib.ekplots_bar_layout.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, EKBarOptions]
_lib.ekplots_bar_layout.restype = EKBarLayout
_lib.ekplots_bar_free.argtypes = [ctypes.POINTER(EKBarLayout)]
_lib.ekplots_bar_free.restype = None


@dataclass
class BarLayout:
    bars: np.ndarray  # (n, 4): x, y, w, h
    bounds: Bounds
    width: float
    height: float
    labels: list | None = None
    horizontal: bool = False


def bar(values, labels=None, horizontal: bool = False, width=400.0, height=300.0, bar_gap=0.2) -> BarLayout:
    n = len(values)
    opts = EKBarOptions(width=width, height=height, bar_gap=bar_gap, horizontal=int(horizontal))
    raw = _lib.ekplots_bar_layout(_d_array(values), n, opts)
    bars = np.array([(r.x, r.y, r.w, r.h) for r in raw.bars[:raw.n]])
    bounds = _bounds_to_py(raw.bounds)
    _lib.ekplots_bar_free(ctypes.byref(raw))
    return BarLayout(bars=bars, bounds=bounds, width=width, height=height, labels=labels, horizontal=horizontal)


def hbar(values, labels=None, **kwargs) -> BarLayout:
    """Thin wrapper over bar(horizontal=True) — shares the same C layout
    function; see docs/SPEC.md's Horizontal Bar entry."""
    return bar(values, labels=labels, horizontal=True, **kwargs)


# ================= 3. Stacked Bar =================


class EKStackedBarOptions(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_double),
        ("height", ctypes.c_double),
        ("bar_gap", ctypes.c_double),
        ("n_series", ctypes.c_size_t),
    ]


class EKStackedBarLayout(ctypes.Structure):
    _fields_ = [
        ("segments", ctypes.POINTER(EKRect)),
        ("n_categories", ctypes.c_size_t),
        ("n_series", ctypes.c_size_t),
        ("bounds", EKBounds),
    ]


_lib.ekplots_stacked_bar_layout.argtypes = [
    ctypes.POINTER(ctypes.POINTER(ctypes.c_double)), ctypes.c_size_t, ctypes.c_size_t, EKStackedBarOptions,
]
_lib.ekplots_stacked_bar_layout.restype = EKStackedBarLayout
_lib.ekplots_stacked_bar_free.argtypes = [ctypes.POINTER(EKStackedBarLayout)]
_lib.ekplots_stacked_bar_free.restype = None


@dataclass
class StackedBarLayout:
    segments: np.ndarray  # (n_categories, n_series, 4): x, y, w, h
    series_names: list
    bounds: Bounds
    width: float
    height: float
    labels: list | None = None


def stacked_bar(series: dict, labels=None, width=400.0, height=300.0, bar_gap=0.2) -> StackedBarLayout:
    series_names = list(series.keys())
    n_series = len(series_names)
    n_categories = len(next(iter(series.values())))
    arrays = [_d_array(series[name]) for name in series_names]
    ptrs = (ctypes.POINTER(ctypes.c_double) * n_series)(*arrays)

    opts = EKStackedBarOptions(width=width, height=height, bar_gap=bar_gap, n_series=n_series)
    raw = _lib.ekplots_stacked_bar_layout(ptrs, n_series, n_categories, opts)

    flat = raw.segments[: raw.n_categories * raw.n_series]
    segments = np.array([(r.x, r.y, r.w, r.h) for r in flat]).reshape(raw.n_categories, raw.n_series, 4)
    bounds = _bounds_to_py(raw.bounds)
    _lib.ekplots_stacked_bar_free(ctypes.byref(raw))
    return StackedBarLayout(segments=segments, series_names=series_names, bounds=bounds, width=width, height=height, labels=labels)


# ================= 4. Line =================


class EKLineOptions(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double), ("smooth", ctypes.c_int)]


class EKLineLayout(ctypes.Structure):
    _fields_ = [("points", ctypes.POINTER(EKPoint)), ("n", ctypes.c_size_t), ("bounds", EKBounds)]


_lib.ekplots_line_layout.argtypes = [
    ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, EKLineOptions,
]
_lib.ekplots_line_layout.restype = EKLineLayout
_lib.ekplots_line_free.argtypes = [ctypes.POINTER(EKLineLayout)]
_lib.ekplots_line_free.restype = None


@dataclass
class LineLayout:
    points: np.ndarray  # (n, 2)
    bounds: Bounds
    width: float
    height: float


def line(x, y, smooth: bool = False, width=400.0, height=300.0) -> LineLayout:
    n = len(x)
    opts = EKLineOptions(width=width, height=height, smooth=int(smooth))
    raw = _lib.ekplots_line_layout(_d_array(x), _d_array(y), n, opts)
    points = np.array([(p.x, p.y) for p in raw.points[:raw.n]])
    bounds = _bounds_to_py(raw.bounds)
    _lib.ekplots_line_free(ctypes.byref(raw))
    return LineLayout(points=points, bounds=bounds, width=width, height=height)


# ================= 5. Area =================


class EKAreaOptions(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double), ("baseline", ctypes.c_double)]


class EKAreaLayout(ctypes.Structure):
    _fields_ = [
        ("points", ctypes.POINTER(EKPoint)),
        ("n", ctypes.c_size_t),
        ("baseline_y", ctypes.c_double),
        ("bounds", EKBounds),
    ]


_lib.ekplots_area_layout.argtypes = [
    ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, EKAreaOptions,
]
_lib.ekplots_area_layout.restype = EKAreaLayout
_lib.ekplots_area_free.argtypes = [ctypes.POINTER(EKAreaLayout)]
_lib.ekplots_area_free.restype = None


@dataclass
class AreaLayout:
    points: np.ndarray  # (n, 2), top edge of the fill
    baseline_y: float
    bounds: Bounds
    width: float
    height: float


def area(x, y, baseline: float = 0.0, width=400.0, height=300.0) -> AreaLayout:
    n = len(x)
    opts = EKAreaOptions(width=width, height=height, baseline=baseline)
    raw = _lib.ekplots_area_layout(_d_array(x), _d_array(y), n, opts)
    points = np.array([(p.x, p.y) for p in raw.points[:raw.n]])
    bounds = _bounds_to_py(raw.bounds)
    baseline_y = raw.baseline_y
    _lib.ekplots_area_free(ctypes.byref(raw))
    return AreaLayout(points=points, baseline_y=baseline_y, bounds=bounds, width=width, height=height)


# ================= 6. Stacked Area =================


class EKStackedAreaOptions(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class EKStackedAreaLayout(ctypes.Structure):
    _fields_ = [
        ("bands", ctypes.POINTER(EKPoint)),
        ("n_series", ctypes.c_size_t),
        ("n_points", ctypes.c_size_t),
        ("bounds", EKBounds),
    ]


_lib.ekplots_stacked_area_layout.argtypes = [
    ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.POINTER(ctypes.c_double)),
    ctypes.c_size_t, ctypes.c_size_t, EKStackedAreaOptions,
]
_lib.ekplots_stacked_area_layout.restype = EKStackedAreaLayout
_lib.ekplots_stacked_area_free.argtypes = [ctypes.POINTER(EKStackedAreaLayout)]
_lib.ekplots_stacked_area_free.restype = None


@dataclass
class StackedAreaLayout:
    bands: np.ndarray  # (n_series, n_points, 2, 2): [bottom_point, top_point]
    series_names: list
    bounds: Bounds
    width: float
    height: float


def stacked_area(x, series: dict, width=400.0, height=300.0) -> StackedAreaLayout:
    series_names = list(series.keys())
    n_series = len(series_names)
    n_points = len(x)
    arrays = [_d_array(series[name]) for name in series_names]
    ptrs = (ctypes.POINTER(ctypes.c_double) * n_series)(*arrays)

    opts = EKStackedAreaOptions(width=width, height=height)
    raw = _lib.ekplots_stacked_area_layout(_d_array(x), ptrs, n_series, n_points, opts)

    flat = raw.bands[: raw.n_series * raw.n_points * 2]
    bands = np.array([(p.x, p.y) for p in flat]).reshape(raw.n_series, raw.n_points, 2, 2)
    bounds = _bounds_to_py(raw.bounds)
    _lib.ekplots_stacked_area_free(ctypes.byref(raw))
    return StackedAreaLayout(bands=bands, series_names=series_names, bounds=bounds, width=width, height=height)


# ================= 7 & 8. Pie / Donut =================


class EKPieOptions(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_double), ("cy", ctypes.c_double), ("r", ctypes.c_double)]


class EKPieLayout(ctypes.Structure):
    _fields_ = [("slices", ctypes.POINTER(EKArc)), ("n", ctypes.c_size_t)]


_lib.ekplots_pie_layout.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, EKPieOptions]
_lib.ekplots_pie_layout.restype = EKPieLayout
_lib.ekplots_pie_free.argtypes = [ctypes.POINTER(EKPieLayout)]
_lib.ekplots_pie_free.restype = None


class EKDonutOptions(ctypes.Structure):
    _fields_ = [
        ("cx", ctypes.c_double), ("cy", ctypes.c_double), ("r", ctypes.c_double), ("inner_r", ctypes.c_double),
    ]


class EKDonutLayout(ctypes.Structure):
    _fields_ = [("slices", ctypes.POINTER(EKArc)), ("n", ctypes.c_size_t), ("inner_r", ctypes.c_double)]


_lib.ekplots_donut_layout.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, EKDonutOptions]
_lib.ekplots_donut_layout.restype = EKDonutLayout
_lib.ekplots_donut_free.argtypes = [ctypes.POINTER(EKDonutLayout)]
_lib.ekplots_donut_free.restype = None


@dataclass
class PieLayout:
    slices: np.ndarray  # (n, 5): cx, cy, r, start_angle, end_angle
    labels: list | None = None
    inner_r: float = 0.0


def pie(values, labels=None, cx=150.0, cy=150.0, r=140.0) -> PieLayout:
    n = len(values)
    opts = EKPieOptions(cx=cx, cy=cy, r=r)
    raw = _lib.ekplots_pie_layout(_d_array(values), n, opts)
    slices = np.array([(a.cx, a.cy, a.r, a.start_angle, a.end_angle) for a in raw.slices[:raw.n]])
    _lib.ekplots_pie_free(ctypes.byref(raw))
    return PieLayout(slices=slices, labels=labels)


def donut(values, labels=None, inner_r: float = 0.6, cx=150.0, cy=150.0, r=140.0) -> PieLayout:
    n = len(values)
    opts = EKDonutOptions(cx=cx, cy=cy, r=r, inner_r=inner_r * r)
    raw = _lib.ekplots_donut_layout(_d_array(values), n, opts)
    slices = np.array([(a.cx, a.cy, a.r, a.start_angle, a.end_angle) for a in raw.slices[:raw.n]])
    inner_r_px = raw.inner_r
    _lib.ekplots_donut_free(ctypes.byref(raw))
    return PieLayout(slices=slices, labels=labels, inner_r=inner_r_px)


# ================= 9. Funnel =================


class EKFunnelOptions(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double), ("stage_gap", ctypes.c_double)]


class EKFunnelStage(ctypes.Structure):
    _fields_ = [
        ("trapezoid", EKPoint * 4),
        ("value", ctypes.c_double),
        ("pct_of_first", ctypes.c_double),
        ("pct_of_previous", ctypes.c_double),
    ]


class EKFunnelLayout(ctypes.Structure):
    _fields_ = [("stages", ctypes.POINTER(EKFunnelStage)), ("n", ctypes.c_size_t)]


_lib.ekplots_funnel_layout.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, EKFunnelOptions]
_lib.ekplots_funnel_layout.restype = EKFunnelLayout
_lib.ekplots_funnel_free.argtypes = [ctypes.POINTER(EKFunnelLayout)]
_lib.ekplots_funnel_free.restype = None


@dataclass
class FunnelStagePy:
    trapezoid: np.ndarray  # (4, 2)
    value: float
    pct_of_first: float
    pct_of_previous: float


@dataclass
class FunnelLayout:
    stages: list
    labels: list | None = None


def funnel(values, labels=None, width=400.0, height=300.0, stage_gap=6.0) -> FunnelLayout:
    n = len(values)
    opts = EKFunnelOptions(width=width, height=height, stage_gap=stage_gap)
    raw = _lib.ekplots_funnel_layout(_d_array(values), n, opts)
    stages = []
    for st in raw.stages[:raw.n]:
        trapezoid = np.array([(p.x, p.y) for p in st.trapezoid])
        stages.append(FunnelStagePy(trapezoid, st.value, st.pct_of_first, st.pct_of_previous))
    _lib.ekplots_funnel_free(ctypes.byref(raw))
    return FunnelLayout(stages=stages, labels=labels)


# ================= 10. Histogram =================


class EKHistogramOptions(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double), ("n_bins", ctypes.c_size_t)]


class EKHistogramLayout(ctypes.Structure):
    _fields_ = [
        ("bins", ctypes.POINTER(EKRect)),
        ("n_bins", ctypes.c_size_t),
        ("bin_edges", ctypes.POINTER(ctypes.c_double)),
        ("bounds", EKBounds),
    ]


_lib.ekplots_histogram_layout.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, EKHistogramOptions]
_lib.ekplots_histogram_layout.restype = EKHistogramLayout
_lib.ekplots_histogram_free.argtypes = [ctypes.POINTER(EKHistogramLayout)]
_lib.ekplots_histogram_free.restype = None


@dataclass
class HistogramLayout:
    bins: np.ndarray  # (n_bins, 4): x, y, w, h
    bin_edges: np.ndarray  # (n_bins + 1,)
    bounds: Bounds


def histogram(values, bins: int = 0, width=400.0, height=300.0) -> HistogramLayout:
    n = len(values)
    opts = EKHistogramOptions(width=width, height=height, n_bins=bins)
    raw = _lib.ekplots_histogram_layout(_d_array(values), n, opts)
    bin_rects = np.array([(r.x, r.y, r.w, r.h) for r in raw.bins[:raw.n_bins]])
    bin_edges = np.array(raw.bin_edges[: raw.n_bins + 1])
    bounds = _bounds_to_py(raw.bounds)
    _lib.ekplots_histogram_free(ctypes.byref(raw))
    return HistogramLayout(bins=bin_rects, bin_edges=bin_edges, bounds=bounds)


# ================= 11. Box Plot =================


class EKBoxplotOptions(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double), ("box_width", ctypes.c_double)]


class EKBoxplotStats(ctypes.Structure):
    _fields_ = [
        ("min", ctypes.c_double), ("q1", ctypes.c_double), ("median", ctypes.c_double),
        ("q3", ctypes.c_double), ("max", ctypes.c_double),
        ("outliers", ctypes.POINTER(ctypes.c_double)), ("n_outliers", ctypes.c_size_t),
        ("box", EKRect), ("whisker_low", EKPoint), ("whisker_high", EKPoint),
    ]


class EKBoxplotLayout(ctypes.Structure):
    _fields_ = [
        ("groups", ctypes.POINTER(EKBoxplotStats)),
        ("n_groups", ctypes.c_size_t),
        ("bounds", EKBounds),
    ]


_lib.ekplots_boxplot_layout.argtypes = [
    ctypes.POINTER(ctypes.POINTER(ctypes.c_double)), ctypes.POINTER(ctypes.c_size_t),
    ctypes.c_size_t, EKBoxplotOptions,
]
_lib.ekplots_boxplot_layout.restype = EKBoxplotLayout
_lib.ekplots_boxplot_free.argtypes = [ctypes.POINTER(EKBoxplotLayout)]
_lib.ekplots_boxplot_free.restype = None


@dataclass
class BoxplotGroupPy:
    min: float
    q1: float
    median: float
    q3: float
    max: float
    outliers: np.ndarray
    box: tuple  # x, y, w, h — already scaled into [0, height]
    whisker_low: tuple
    whisker_high: tuple


@dataclass
class BoxplotLayout:
    groups: dict  # name -> BoxplotGroupPy
    bounds: Bounds
    height: float


def boxplot(groups: dict, width=400.0, height=300.0, box_width=0.5) -> BoxplotLayout:
    names = list(groups.keys())
    n_groups = len(names)
    arrays = [_d_array(groups[name]) for name in names]
    ptrs = (ctypes.POINTER(ctypes.c_double) * n_groups)(*arrays)
    sizes = (ctypes.c_size_t * n_groups)(*[len(groups[name]) for name in names])

    opts = EKBoxplotOptions(width=width, height=height, box_width=box_width)
    raw = _lib.ekplots_boxplot_layout(ptrs, sizes, n_groups, opts)

    out = {}
    for name, st in zip(names, raw.groups[:raw.n_groups]):
        outliers = np.array(st.outliers[: st.n_outliers]) if st.n_outliers else np.array([])
        out[name] = BoxplotGroupPy(
            min=st.min, q1=st.q1, median=st.median, q3=st.q3, max=st.max,
            outliers=outliers,
            box=(st.box.x, st.box.y, st.box.w, st.box.h),
            whisker_low=(st.whisker_low.x, st.whisker_low.y),
            whisker_high=(st.whisker_high.x, st.whisker_high.y),
        )
    bounds = _bounds_to_py(raw.bounds)
    _lib.ekplots_boxplot_free(ctypes.byref(raw))
    return BoxplotLayout(groups=out, bounds=bounds, height=height)


# ================= 12. Scatter =================


class EKScatterOptions(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double), ("point_radius", ctypes.c_double)]


class EKScatterLayout(ctypes.Structure):
    _fields_ = [("points", ctypes.POINTER(EKPoint)), ("n", ctypes.c_size_t), ("bounds", EKBounds)]


_lib.ekplots_scatter_layout.argtypes = [
    ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, EKScatterOptions,
]
_lib.ekplots_scatter_layout.restype = EKScatterLayout
_lib.ekplots_scatter_free.argtypes = [ctypes.POINTER(EKScatterLayout)]
_lib.ekplots_scatter_free.restype = None


@dataclass
class ScatterLayout:
    points: np.ndarray  # (n, 2)
    bounds: Bounds
    width: float
    height: float
    labels: list | None = None


def scatter(x, y, labels=None, width=400.0, height=300.0, point_radius=4.0) -> ScatterLayout:
    n = len(x)
    opts = EKScatterOptions(width=width, height=height, point_radius=point_radius)
    raw = _lib.ekplots_scatter_layout(_d_array(x), _d_array(y), n, opts)
    points = np.array([(p.x, p.y) for p in raw.points[:raw.n]])
    bounds = _bounds_to_py(raw.bounds)
    _lib.ekplots_scatter_free(ctypes.byref(raw))
    return ScatterLayout(points=points, bounds=bounds, width=width, height=height, labels=labels)


# ================= 13. Bubble =================


class EKBubbleOptions(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_double), ("height", ctypes.c_double),
        ("min_r", ctypes.c_double), ("max_r", ctypes.c_double),
    ]


class EKBubbleLayout(ctypes.Structure):
    _fields_ = [("bubbles", ctypes.POINTER(EKBubble)), ("n", ctypes.c_size_t), ("bounds", EKBounds)]


_lib.ekplots_bubble_layout.argtypes = [
    ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
    ctypes.c_size_t, EKBubbleOptions,
]
_lib.ekplots_bubble_layout.restype = EKBubbleLayout
_lib.ekplots_bubble_free.argtypes = [ctypes.POINTER(EKBubbleLayout)]
_lib.ekplots_bubble_free.restype = None


@dataclass
class BubbleLayout:
    bubbles: np.ndarray  # (n, 3): x, y, r
    bounds: Bounds
    width: float
    height: float
    labels: list | None = None


def bubble(x, y, size, labels=None, width=400.0, height=300.0, min_r=4.0, max_r=40.0) -> BubbleLayout:
    n = len(x)
    opts = EKBubbleOptions(width=width, height=height, min_r=min_r, max_r=max_r)
    raw = _lib.ekplots_bubble_layout(_d_array(x), _d_array(y), _d_array(size), n, opts)
    bubbles = np.array([(b.x, b.y, b.r) for b in raw.bubbles[:raw.n]])
    bounds = _bounds_to_py(raw.bounds)
    _lib.ekplots_bubble_free(ctypes.byref(raw))
    return BubbleLayout(bubbles=bubbles, bounds=bounds, width=width, height=height, labels=labels)


# ================= 14. Heatmap =================


class EKHeatmapOptions(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double), ("cell_gap", ctypes.c_double)]


class EKHeatmapLayout(ctypes.Structure):
    _fields_ = [
        ("cells", ctypes.POINTER(EKRect)),
        ("n_rows", ctypes.c_size_t),
        ("n_cols", ctypes.c_size_t),
        ("value_min", ctypes.c_double),
        ("value_max", ctypes.c_double),
    ]


_lib.ekplots_heatmap_layout.argtypes = [
    ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, ctypes.c_size_t, EKHeatmapOptions,
]
_lib.ekplots_heatmap_layout.restype = EKHeatmapLayout
_lib.ekplots_heatmap_free.argtypes = [ctypes.POINTER(EKHeatmapLayout)]
_lib.ekplots_heatmap_free.restype = None


@dataclass
class HeatmapLayout:
    cells: np.ndarray  # (n_rows, n_cols, 4): x, y, w, h
    values: np.ndarray  # (n_rows, n_cols) — the source matrix, passed through
    # for the renderer's per-cell color mapping (geometry alone can't
    # carry magnitude; the C core never computes color).
    value_min: float
    value_max: float
    row_labels: list | None = None
    col_labels: list | None = None


def heatmap(matrix, row_labels=None, col_labels=None, width=400.0, height=400.0, cell_gap=2.0) -> HeatmapLayout:
    mat = np.asarray(matrix, dtype=np.float64)
    n_rows, n_cols = mat.shape
    flat = _d_array(mat.flatten())
    opts = EKHeatmapOptions(width=width, height=height, cell_gap=cell_gap)
    raw = _lib.ekplots_heatmap_layout(flat, n_rows, n_cols, opts)
    cells_flat = raw.cells[: raw.n_rows * raw.n_cols]
    cells = np.array([(r.x, r.y, r.w, r.h) for r in cells_flat]).reshape(raw.n_rows, raw.n_cols, 4)
    value_min, value_max = raw.value_min, raw.value_max
    _lib.ekplots_heatmap_free(ctypes.byref(raw))
    return HeatmapLayout(
        cells=cells, values=mat, value_min=value_min, value_max=value_max,
        row_labels=row_labels, col_labels=col_labels,
    )


# ================= 15. Radar =================


class EKRadarOptions(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_double), ("cy", ctypes.c_double), ("r", ctypes.c_double), ("n_axes", ctypes.c_size_t)]


class EKRadarLayout(ctypes.Structure):
    _fields_ = [
        ("axis_ticks", ctypes.POINTER(EKPoint)),
        ("series_points", ctypes.POINTER(EKPoint)),
        ("n_axes", ctypes.c_size_t),
    ]


_lib.ekplots_radar_layout.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, EKRadarOptions]
_lib.ekplots_radar_layout.restype = EKRadarLayout
_lib.ekplots_radar_free.argtypes = [ctypes.POINTER(EKRadarLayout)]
_lib.ekplots_radar_free.restype = None


@dataclass
class RadarLayout:
    axis_ticks: np.ndarray  # (n_axes, 2)
    series_points: np.ndarray  # (n_axes, 2)
    axis_labels: list | None = None


def radar(values, axis_labels=None, cx=150.0, cy=150.0, r=120.0) -> RadarLayout:
    n = len(values)
    opts = EKRadarOptions(cx=cx, cy=cy, r=r, n_axes=n)
    raw = _lib.ekplots_radar_layout(_d_array(values), n, opts)
    axis_ticks = np.array([(p.x, p.y) for p in raw.axis_ticks[:raw.n_axes]])
    series_points = np.array([(p.x, p.y) for p in raw.series_points[:raw.n_axes]])
    _lib.ekplots_radar_free(ctypes.byref(raw))
    return RadarLayout(axis_ticks=axis_ticks, series_points=series_points, axis_labels=axis_labels)
