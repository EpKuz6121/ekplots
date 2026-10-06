"""Matplotlib renderers — the Python half of the "renders natively per
language" architecture. Every function here takes a layout object from
_core.py and an optional matplotlib Axes, draws onto it, and returns it.

No geometry is computed here — every coordinate was already decided by
the C core. This module only decides color, stroke, and how to map the
C core's logical [0,width]x[0,height] canvas back onto real axis tick
labels using each layout's `bounds`.
"""
from __future__ import annotations

import numpy as np

from . import _core as ek

_DEFAULT_COLOR = "#2f5fd1"
_DEFAULT_CYCLE = ["#2f5fd1", "#b8541f", "#2a9d6b", "#8e5fd1", "#d13f6f", "#c99a2e"]


def _ax(ax):
    if ax is not None:
        return ax
    import matplotlib.pyplot as plt

    _, ax = plt.subplots()
    return ax


def _real_ticks(logical_min, logical_max, real_min, real_max, n=5):
    """n evenly spaced tick positions across [logical_min, logical_max],
    labeled with the REAL values they correspond to in [real_min, real_max]
    — the one piece of unmapping every renderer needs, since the C core's
    geometry lives in logical canvas units, not the caller's original
    data units."""
    positions = np.linspace(logical_min, logical_max, n)
    real_values = np.linspace(real_min, real_max, n)
    return positions, real_values


def draw(layout, ax=None, **style):
    """Dispatches on the layout's type — one call for any of the 15
    plots, matching docs/SPEC.md's `ekplots.draw(layout, ax=None)`
    convention."""
    dispatch = {
        ek.BarLayout: _draw_bar,
        ek.StackedBarLayout: _draw_stacked_bar,
        ek.LineLayout: _draw_line,
        ek.AreaLayout: _draw_area,
        ek.StackedAreaLayout: _draw_stacked_area,
        ek.PieLayout: _draw_pie,
        ek.FunnelLayout: _draw_funnel,
        ek.HistogramLayout: _draw_histogram,
        ek.BoxplotLayout: _draw_boxplot,
        ek.ScatterLayout: _draw_scatter,
        ek.BubbleLayout: _draw_bubble,
        ek.HeatmapLayout: _draw_heatmap,
        ek.RadarLayout: _draw_radar,
    }
    fn = dispatch.get(type(layout))
    if fn is None:
        raise TypeError(f"ekplots.draw() doesn't know how to render {type(layout).__name__}")
    return fn(layout, _ax(ax), **style)


# ================= 1 & 2. Bar / Horizontal Bar =================


def _draw_bar(layout: "ek.BarLayout", ax, color=_DEFAULT_COLOR):
    import matplotlib.patches as patches

    for i, (x, y, w, h) in enumerate(layout.bars):
        ax.add_patch(patches.Rectangle((x, y), w, h, facecolor=color, edgecolor="none"))

    if layout.labels:
        n = len(layout.labels)
        slot_w = layout.width / n
        positions = [slot_w * (i + 0.5) for i in range(n)]
        if layout.horizontal:
            ax.set_yticks(positions)
            ax.set_yticklabels(layout.labels)
        else:
            ax.set_xticks(positions)
            ax.set_xticklabels(layout.labels, rotation=30, ha="right")

    value_positions, value_labels = _real_ticks(0, layout.height, layout.bounds.y_min, layout.bounds.y_max)
    if layout.horizontal:
        ax.set_xticks(value_positions)
        ax.set_xticklabels([f"{v:.0f}" for v in value_labels])
        ax.set_xlim(0, layout.height)
        ax.set_ylim(0, layout.width)
    else:
        ax.set_yticks(value_positions)
        ax.set_yticklabels([f"{v:.0f}" for v in value_labels])
        ax.set_xlim(0, layout.width)
        ax.set_ylim(0, layout.height)
    return ax


# ================= 3. Stacked Bar =================


def _draw_stacked_bar(layout: "ek.StackedBarLayout", ax, colors=None):
    import matplotlib.patches as patches

    colors = colors or _DEFAULT_CYCLE
    n_categories, n_series, _ = layout.segments.shape
    for c in range(n_categories):
        for s in range(n_series):
            x, y, w, h = layout.segments[c, s]
            ax.add_patch(patches.Rectangle((x, y), w, h, facecolor=colors[s % len(colors)], edgecolor="none"))

    if layout.labels:
        slot_w = layout.width / n_categories
        positions = [slot_w * (i + 0.5) for i in range(n_categories)]
        ax.set_xticks(positions)
        ax.set_xticklabels(layout.labels, rotation=30, ha="right")

    value_positions, value_labels = _real_ticks(0, layout.height, layout.bounds.y_min, layout.bounds.y_max)
    ax.set_yticks(value_positions)
    ax.set_yticklabels([f"{v:.0f}" for v in value_labels])
    ax.set_xlim(0, layout.width)
    ax.set_ylim(0, layout.height)
    ax.legend(
        handles=[patches.Patch(facecolor=colors[s % len(colors)], label=name) for s, name in enumerate(layout.series_names)],
        loc="upper right", frameon=False,
    )
    return ax


# ================= 4. Line =================


def _draw_line(layout: "ek.LineLayout", ax, color=_DEFAULT_COLOR, linewidth=2.0):
    ax.plot(layout.points[:, 0], layout.points[:, 1], color=color, linewidth=linewidth)
    xp, xl = _real_ticks(0, layout.width, layout.bounds.x_min, layout.bounds.x_max)
    yp, yl = _real_ticks(0, layout.height, layout.bounds.y_min, layout.bounds.y_max)
    ax.set_xticks(xp); ax.set_xticklabels([f"{v:.1f}" for v in xl])
    ax.set_yticks(yp); ax.set_yticklabels([f"{v:.1f}" for v in yl])
    ax.set_xlim(0, layout.width)
    ax.set_ylim(0, layout.height)
    return ax


# ================= 5. Area =================


def _draw_area(layout: "ek.AreaLayout", ax, color=_DEFAULT_COLOR):
    xs = layout.points[:, 0]
    ys = layout.points[:, 1]
    ax.fill_between(xs, layout.baseline_y, ys, color=color, alpha=0.35)
    ax.plot(xs, ys, color=color, linewidth=2.0)
    xp, xl = _real_ticks(0, layout.width, layout.bounds.x_min, layout.bounds.x_max)
    yp, yl = _real_ticks(0, layout.height, layout.bounds.y_min, layout.bounds.y_max)
    ax.set_xticks(xp); ax.set_xticklabels([f"{v:.1f}" for v in xl])
    ax.set_yticks(yp); ax.set_yticklabels([f"{v:.1f}" for v in yl])
    ax.set_xlim(0, layout.width)
    ax.set_ylim(0, layout.height)
    return ax


# ================= 6. Stacked Area =================


def _draw_stacked_area(layout: "ek.StackedAreaLayout", ax, colors=None):
    import matplotlib.patches as patches

    colors = colors or _DEFAULT_CYCLE
    n_series, n_points, _, _ = layout.bands.shape
    for s in range(n_series):
        xs = layout.bands[s, :, 0, 0]
        bottoms = layout.bands[s, :, 0, 1]
        tops = layout.bands[s, :, 1, 1]
        ax.fill_between(xs, bottoms, tops, color=colors[s % len(colors)], alpha=0.85, edgecolor="none")

    xp, xl = _real_ticks(0, layout.width, layout.bounds.x_min, layout.bounds.x_max)
    yp, yl = _real_ticks(0, layout.height, layout.bounds.y_min, layout.bounds.y_max)
    ax.set_xticks(xp); ax.set_xticklabels([f"{v:.1f}" for v in xl])
    ax.set_yticks(yp); ax.set_yticklabels([f"{v:.0f}" for v in yl])
    ax.set_xlim(0, layout.width)
    ax.set_ylim(0, layout.height)
    ax.legend(
        handles=[patches.Patch(facecolor=colors[s % len(colors)], label=name) for s, name in enumerate(layout.series_names)],
        loc="upper left", frameon=False,
    )
    return ax


# ================= 7 & 8. Pie / Donut =================


def _draw_pie(layout: "ek.PieLayout", ax, colors=None):
    import matplotlib.patches as patches

    colors = colors or _DEFAULT_CYCLE
    for i, (cx, cy, r, start, end) in enumerate(layout.slices):
        wedge = patches.Wedge(
            (cx, cy), r, np.degrees(start), np.degrees(end),
            width=(r - layout.inner_r) if layout.inner_r else None,
            facecolor=colors[i % len(colors)], edgecolor="white", linewidth=1.5,
        )
        ax.add_patch(wedge)

    if layout.labels:
        ax.legend(
            handles=[patches.Patch(facecolor=colors[i % len(colors)], label=l) for i, l in enumerate(layout.labels)],
            loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False,
        )

    if len(layout.slices):
        cx, cy, r = layout.slices[0][0], layout.slices[0][1], layout.slices[:, 2].max()
        ax.set_xlim(cx - r * 1.3, cx + r * 1.3)
        ax.set_ylim(cy - r * 1.3, cy + r * 1.3)
    ax.set_aspect("equal")
    ax.axis("off")
    return ax


# donut shares the pie renderer — layout.inner_r is 0 for a real pie, >0
# for a donut, which is the only thing that differs at draw time.
_draw_donut = _draw_pie


# ================= 9. Funnel =================


def _draw_funnel(layout: "ek.FunnelLayout", ax, color=_DEFAULT_COLOR):
    import matplotlib.patches as patches

    max_w = 0
    max_h = 0
    for i, stage in enumerate(layout.stages):
        poly = patches.Polygon(stage.trapezoid, closed=True, facecolor=color, alpha=1.0 - i * 0.12, edgecolor="white")
        ax.add_patch(poly)
        max_w = max(max_w, stage.trapezoid[:, 0].max())
        max_h = max(max_h, stage.trapezoid[:, 1].max())

        cy = stage.trapezoid[:, 1].mean()
        label = layout.labels[i] if layout.labels else f"Stage {i + 1}"
        ax.text(
            max_w / 2 if i == 0 else stage.trapezoid[:, 0].mean(), cy,
            f"{label}\n{stage.value:.0f} ({stage.pct_of_first * 100:.0f}%)",
            ha="center", va="center", fontsize=9, color="white",
        )

    ax.set_xlim(0, max_w)
    ax.set_ylim(max_h, 0)  # funnel reads top-down
    ax.axis("off")
    return ax


# ================= 10. Histogram =================


def _draw_histogram(layout: "ek.HistogramLayout", ax, color=_DEFAULT_COLOR):
    import matplotlib.patches as patches

    for x, y, w, h in layout.bins:
        ax.add_patch(patches.Rectangle((x, y), w, h, facecolor=color, edgecolor="white", linewidth=0.5))

    max_h = layout.bins[:, 1].max() + layout.bins[:, 3].max() if len(layout.bins) else 1.0
    ax.set_xticks(layout.bins[:, 0])
    ax.set_xticklabels([f"{e:.1f}" for e in layout.bin_edges[:-1]], rotation=45, ha="right")
    ax.set_xlim(0, layout.bins[:, 0].max() + layout.bins[:, 2].max() if len(layout.bins) else 1.0)
    ax.set_ylim(0, max_h)
    return ax


# ================= 11. Box Plot =================


def _draw_boxplot(layout: "ek.BoxplotLayout", ax, color=_DEFAULT_COLOR):
    import matplotlib.patches as patches

    names = list(layout.groups.keys())
    for name in names:
        g = layout.groups[name]
        bx, by, bw, bh = g.box
        ax.add_patch(patches.Rectangle((bx, by), bw, bh, facecolor=color, alpha=0.5, edgecolor=color, linewidth=1.5))
        median_y = by + (g.median - g.q1) / (g.q3 - g.q1) * bh if g.q3 != g.q1 else by + bh / 2
        ax.plot([bx, bx + bw], [median_y, median_y], color=color, linewidth=2.0)
        wx = g.whisker_low[0]
        ax.plot([wx, wx], [g.whisker_low[1], by], color=color, linewidth=1.0)
        ax.plot([wx, wx], [by + bh, g.whisker_high[1]], color=color, linewidth=1.0)
        if len(g.outliers):
            outlier_ys = [by + bh + (o - g.q3) / (g.max - g.q3) * (g.whisker_high[1] - (by + bh)) if g.max != g.q3 else by + bh for o in g.outliers]
            ax.scatter([wx] * len(g.outliers), outlier_ys, color=color, s=18, zorder=5)

    n_groups = len(names)
    first_box_x = layout.groups[names[0]].box[0] if names else 0
    ax.set_xticks([layout.groups[n].box[0] + layout.groups[n].box[2] / 2 for n in names])
    ax.set_xticklabels(names, rotation=20, ha="right")
    yp, yl = _real_ticks(0, layout.height, layout.bounds.y_min, layout.bounds.y_max)
    ax.set_yticks(yp)
    ax.set_yticklabels([f"{v:.1f}" for v in yl])
    ax.set_xlim(0, n_groups * (first_box_x * 2 + layout.groups[names[0]].box[2]) if names else 1)
    ax.set_ylim(0, layout.height)
    return ax


# ================= 12. Scatter =================


def _draw_scatter(layout: "ek.ScatterLayout", ax, color=_DEFAULT_COLOR, size=24):
    ax.scatter(layout.points[:, 0], layout.points[:, 1], color=color, s=size, alpha=0.8, edgecolors="none")
    xp, xl = _real_ticks(0, layout.width, layout.bounds.x_min, layout.bounds.x_max)
    yp, yl = _real_ticks(0, layout.height, layout.bounds.y_min, layout.bounds.y_max)
    ax.set_xticks(xp); ax.set_xticklabels([f"{v:.1f}" for v in xl])
    ax.set_yticks(yp); ax.set_yticklabels([f"{v:.1f}" for v in yl])
    ax.set_xlim(0, layout.width)
    ax.set_ylim(0, layout.height)
    return ax


# ================= 13. Bubble =================


def _draw_bubble(layout: "ek.BubbleLayout", ax, color=_DEFAULT_COLOR):
    for x, y, r in layout.bubbles:
        ax.scatter([x], [y], s=(r * 2) ** 2 * 0.2, color=color, alpha=0.55, edgecolors=color, linewidths=1.0)
    xp, xl = _real_ticks(0, layout.width, layout.bounds.x_min, layout.bounds.x_max)
    yp, yl = _real_ticks(0, layout.height, layout.bounds.y_min, layout.bounds.y_max)
    ax.set_xticks(xp); ax.set_xticklabels([f"{v:.1f}" for v in xl])
    ax.set_yticks(yp); ax.set_yticklabels([f"{v:.1f}" for v in yl])
    ax.set_xlim(0, layout.width)
    ax.set_ylim(0, layout.height)
    return ax


# ================= 14. Heatmap =================


def _draw_heatmap(layout: "ek.HeatmapLayout", ax, cmap_name="Blues"):
    import matplotlib as mpl
    import matplotlib.patches as patches

    cmap = mpl.colormaps[cmap_name]
    n_rows, n_cols, _ = layout.cells.shape
    v_range = (layout.value_max - layout.value_min) or 1.0

    for r in range(n_rows):
        for c in range(n_cols):
            x, y, w, h = layout.cells[r, c]
            t = (layout.values[r, c] - layout.value_min) / v_range
            ax.add_patch(patches.Rectangle((x, y), w, h, facecolor=cmap(t), edgecolor="white", linewidth=1))

    if layout.col_labels:
        ax.set_xticks([layout.cells[0, c, 0] + layout.cells[0, c, 2] / 2 for c in range(n_cols)])
        ax.set_xticklabels(layout.col_labels, rotation=45, ha="right")
    if layout.row_labels:
        ax.set_yticks([layout.cells[r, 0, 1] + layout.cells[r, 0, 3] / 2 for r in range(n_rows)])
        ax.set_yticklabels(layout.row_labels)

    ax.set_xlim(0, layout.cells[:, :, 0].max() + layout.cells[:, :, 2].max())
    ax.set_ylim(0, layout.cells[:, :, 1].max() + layout.cells[:, :, 3].max())
    return ax


# ================= 15. Radar =================


def _draw_radar(layout: "ek.RadarLayout", ax, color=_DEFAULT_COLOR):
    import matplotlib.patches as patches

    outline = patches.Polygon(layout.axis_ticks, closed=True, facecolor="none", edgecolor="#cccccc", linewidth=1)
    ax.add_patch(outline)
    for tick in layout.axis_ticks:
        cx = layout.axis_ticks[:, 0].mean()
        cy = layout.axis_ticks[:, 1].mean()
        ax.plot([cx, tick[0]], [cy, tick[1]], color="#dddddd", linewidth=0.8)

    shape = patches.Polygon(layout.series_points, closed=True, facecolor=color, alpha=0.3, edgecolor=color, linewidth=2)
    ax.add_patch(shape)

    if layout.axis_labels:
        for label, tick in zip(layout.axis_labels, layout.axis_ticks):
            ax.text(tick[0], tick[1], label, ha="center", va="center", fontsize=8)

    pad = 20
    ax.set_xlim(layout.axis_ticks[:, 0].min() - pad, layout.axis_ticks[:, 0].max() + pad)
    ax.set_ylim(layout.axis_ticks[:, 1].min() - pad, layout.axis_ticks[:, 1].max() + pad)
    ax.set_aspect("equal")
    ax.axis("off")
    return ax
