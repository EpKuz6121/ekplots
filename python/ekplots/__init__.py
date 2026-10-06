"""ekplots — a charting library with one C geometry core, shared between
its Python and JS bindings. See docs/SPEC.md for the full contract.

    import ekplots
    layout = ekplots.bar([10, 25, 15, 40], labels=["A", "B", "C", "D"])
    ax = ekplots.draw(layout)
    ax.figure.savefig("bar.png")
"""
from ._core import (
    area,
    bar,
    boxplot,
    bubble,
    donut,
    funnel,
    hbar,
    heatmap,
    histogram,
    line,
    pie,
    radar,
    scatter,
    stacked_area,
    stacked_bar,
)
from ._draw import draw
from .bandit import Bandit, ChartVariant, InMemoryStorage, JSONFileStorage, ordered_for_viewer

__all__ = [
    "bar", "hbar", "stacked_bar",
    "line", "area", "stacked_area",
    "pie", "donut", "funnel",
    "histogram", "boxplot",
    "scatter", "bubble",
    "heatmap", "radar",
    "draw",
    "Bandit", "ChartVariant", "ordered_for_viewer",
    "JSONFileStorage", "InMemoryStorage",
]

__version__ = "0.1.0"
