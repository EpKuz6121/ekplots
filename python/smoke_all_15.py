"""Real end-to-end smoke test — calls all 15 plot functions with real
data, renders each with matplotlib, and saves a real PNG. Run after
`pip install -e .`:

    python3 smoke_all_15.py

Exits non-zero on any failure. Every PNG lands in ./out/.
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import ekplots

OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)

results = []


def check(name, fn):
    try:
        fn()
        results.append((name, True, None))
        print(f"PASS  {name}")
    except Exception as e:  # noqa: BLE001 — a smoke test wants to report every failure, not stop at the first
        results.append((name, False, str(e)))
        print(f"FAIL  {name}: {e}")


def save(name, ax):
    path = os.path.join(OUT, f"{name}.png")
    ax.figure.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(ax.figure)
    assert os.path.getsize(path) > 500, f"{path} looks empty ({os.path.getsize(path)} bytes)"


def t_bar():
    layout = ekplots.bar([42, 71, 18, 55, 90], labels=["Overview", "Flow", "Segments", "Tracking", "Storage"])
    save("01_bar", ekplots.draw(layout))


def t_hbar():
    layout = ekplots.hbar(
        [820, 540, 310, 180, 95],
        labels=["/", "/pricing.html", "/dispatch-board.html", "/signup.html", "/careers.html"],
    )
    save("02_hbar", ekplots.draw(layout))


def t_stacked_bar():
    layout = ekplots.stacked_bar(
        {"Mobile": [40, 55, 30], "Desktop": [60, 45, 70]}, labels=["Pricing", "Docs", "Checkout"]
    )
    save("03_stacked_bar", ekplots.draw(layout))


def t_line():
    x = list(range(14))
    y = [120, 135, 128, 160, 155, 180, 175, 190, 210, 205, 230, 225, 250, 265]
    layout = ekplots.line(x, y)
    save("04_line", ekplots.draw(layout))


def t_area():
    x = list(range(10))
    y = [50, 60, 55, 80, 90, 85, 100, 120, 115, 140]
    layout = ekplots.area(x, y)
    save("05_area", ekplots.draw(layout))


def t_stacked_area():
    x = list(range(8))
    layout = ekplots.stacked_area(
        x, {"Group 1": [10, 12, 15, 14, 18, 20, 19, 22], "Group 2": [8, 9, 7, 11, 10, 12, 13, 15]}
    )
    save("06_stacked_area", ekplots.draw(layout))


def t_pie():
    layout = ekplots.pie([55, 30, 15], labels=["Group 1", "Group 2", "Group 3"])
    save("07_pie", ekplots.draw(layout))


def t_donut():
    layout = ekplots.donut([55, 30, 15], labels=["Group 1", "Group 2", "Group 3"], inner_r=0.6)
    save("08_donut", ekplots.draw(layout))


def t_funnel():
    layout = ekplots.funnel(
        [1000, 640, 410, 180, 95], labels=["Landing Page", "Pricing", "Signup", "Checkout", "Purchase"]
    )
    save("09_funnel", ekplots.draw(layout))


def t_histogram():
    rng = np.random.default_rng(42)
    values = np.concatenate([rng.normal(2, 0.5, 300), rng.normal(8, 1.2, 150)])
    layout = ekplots.histogram(values)
    save("10_histogram", ekplots.draw(layout))


def t_boxplot():
    rng = np.random.default_rng(7)
    groups = {
        "Group 1": list(rng.normal(30, 5, 60)) + [85, 90],
        "Group 2": list(rng.normal(60, 10, 60)),
        "Group 3": list(rng.normal(45, 15, 60)) + [5],
    }
    layout = ekplots.boxplot(groups)
    save("11_boxplot", ekplots.draw(layout))


def t_scatter():
    rng = np.random.default_rng(3)
    x = rng.normal(50, 15, 80)
    y = x * 1.4 + rng.normal(0, 20, 80)
    layout = ekplots.scatter(x, y)
    save("12_scatter", ekplots.draw(layout))


def t_bubble():
    x = [1, 2, 3, 4, 5, 6]
    y = [10, 25, 15, 40, 30, 20]
    size = [100, 800, 300, 1500, 600, 200]
    layout = ekplots.bubble(x, y, size, labels=["/", "/pricing", "/docs", "/signup", "/about", "/careers"])
    save("13_bubble", ekplots.draw(layout))


def t_heatmap():
    matrix = [
        [0.0, 0.42, 0.18, 0.05],
        [0.31, 0.0, 0.22, 0.08],
        [0.12, 0.35, 0.0, 0.15],
        [0.04, 0.09, 0.28, 0.0],
    ]
    layout = ekplots.heatmap(
        matrix, row_labels=["/", "/pricing", "/docs", "/signup"], col_labels=["/", "/pricing", "/docs", "/signup"]
    )
    save("14_heatmap", ekplots.draw(layout))


def t_radar():
    layout = ekplots.radar(
        [0.8, 0.3, 0.6, 0.9, 0.4],
        axis_labels=["Dwell", "Scroll depth", "Clicks", "Rage clicks", "Idle time"],
    )
    save("15_radar", ekplots.draw(layout))


if __name__ == "__main__":
    tests = [
        ("bar", t_bar), ("hbar", t_hbar), ("stacked_bar", t_stacked_bar),
        ("line", t_line), ("area", t_area), ("stacked_area", t_stacked_area),
        ("pie", t_pie), ("donut", t_donut), ("funnel", t_funnel),
        ("histogram", t_histogram), ("boxplot", t_boxplot),
        ("scatter", t_scatter), ("bubble", t_bubble),
        ("heatmap", t_heatmap), ("radar", t_radar),
    ]
    for name, fn in tests:
        check(name, fn)

    n_pass = sum(1 for _, ok, _ in results if ok)
    print(f"\n{n_pass}/{len(results)} passed. PNGs in {OUT}/")
    if n_pass != len(results):
        sys.exit(1)
