"""Real tests for ekplots' built-in personalization engine
(ekplots/bandit.py) — no mocking, actual Beta draws and actual JSON
file round-trips."""
import os
import random
import tempfile

import ekplots
from ekplots.bandit import (
    Bandit,
    ChartVariant,
    InMemoryStorage,
    JSONFileStorage,
    ordered_for_viewer,
)


# ------------------------------------------------------------ Bandit


def test_add_slot_includes_control_automatically():
    b = Bandit(storage=InMemoryStorage())
    b.add_slot("hero_chart", variants=["bar_vs_line"])
    stats = b.stats("hero_chart")
    assert set(stats["arms"].keys()) == {"control", "bar_vs_line"}


def test_add_slot_is_a_noop_if_already_exists():
    """Re-running setup code must never wipe accumulated stats."""
    b = Bandit(storage=InMemoryStorage())
    b.add_slot("hero_chart", variants=["bar_vs_line"])
    b.record_outcome("hero_chart", "bar_vs_line", engaged=True)
    b.add_slot("hero_chart", variants=["bar_vs_line"])  # should be a no-op
    stats = b.stats("hero_chart")
    assert stats["arms"]["bar_vs_line"]["successes"] == 1


def test_choose_returns_a_real_arm_key():
    b = Bandit(storage=InMemoryStorage())
    b.add_slot("s", variants=["a", "b"])
    chosen = b.choose("s")
    assert chosen in ("control", "a", "b")


def test_heavily_weighted_arm_wins_almost_always():
    b = Bandit(storage=InMemoryStorage())
    b.add_slot("s", variants=["low", "high"], control_key="low")
    b.set_priority_weight("s", "high", 10.0)
    rng = random.Random(7)
    wins = sum(1 for _ in range(500) if b.choose("s", rng=rng) == "high")
    assert wins > 450  # well above the ~50% an unweighted tie would give


def test_paused_arm_is_never_chosen():
    b = Bandit(storage=InMemoryStorage())
    b.add_slot("s", variants=["a"])
    b.pause("s", "a")
    rng = random.Random(1)
    for _ in range(50):
        assert b.choose("s", rng=rng) == "control"


def test_record_outcome_updates_trials_and_successes():
    b = Bandit(storage=InMemoryStorage())
    b.add_slot("s", variants=["a"])
    b.record_outcome("s", "a", engaged=True)
    b.record_outcome("s", "a", engaged=False)
    stats = b.stats("s")["arms"]["a"]
    assert stats["trials"] == 2
    assert stats["successes"] == 1


def test_record_dwell_beats_control_average():
    b = Bandit(storage=InMemoryStorage())
    b.add_slot("s", variants=["a"])
    control = [1000] * 10
    engaged = b.record_dwell("s", "a", dwell_ms=5000, control_dwell_samples=control)
    assert engaged is True
    assert b.stats("s")["arms"]["a"]["successes"] == 1


def test_record_dwell_below_control_average_is_not_engaged():
    b = Bandit(storage=InMemoryStorage())
    b.add_slot("s", variants=["a"])
    control = [2000] * 10
    engaged = b.record_dwell("s", "a", dwell_ms=500, control_dwell_samples=control)
    assert engaged is False


def test_record_dwell_with_too_little_control_data_is_conservative():
    b = Bandit(storage=InMemoryStorage())
    b.add_slot("s", variants=["a"])
    engaged = b.record_dwell("s", "a", dwell_ms=999999, control_dwell_samples=[1000, 2000])
    assert engaged is False


def test_json_file_storage_round_trips_real_state():
    """Writes to a real temp file, reopens with a fresh Bandit instance,
    confirms state actually persisted -- not just that save()/load() ran
    without error."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "bandit.json")
        b1 = Bandit(path=path)
        b1.add_slot("s", variants=["a"])
        b1.record_outcome("s", "a", engaged=True)

        b2 = Bandit(path=path)
        stats = b2.stats("s")["arms"]["a"]
        assert stats["trials"] == 1
        assert stats["successes"] == 1
        assert os.path.exists(path)


def test_set_priority_weight_rejects_non_positive():
    b = Bandit(storage=InMemoryStorage())
    b.add_slot("s", variants=["a"])
    try:
        b.set_priority_weight("s", "a", 0)
        assert False, "should have raised"
    except ValueError:
        pass


# ------------------------------------------------------- ordered_for_viewer


def _four_specs():
    return (
        ChartVariant("signups_bar", cluster_key="new_visitor", build=lambda: ekplots.bar([1, 2, 3])),
        ChartVariant("engagement_line", cluster_key="power_user", build=lambda: ekplots.line([0, 1], [1, 2])),
        ChartVariant("revenue_pie", cluster_key="finance_viewer", build=lambda: ekplots.pie([1, 2, 3])),
        ChartVariant("retention_heatmap", cluster_key="churn_risk", build=lambda: ekplots.heatmap([[1, 2], [3, 4]])),
    )


def test_matching_cluster_moves_to_front_when_enabled_and_sampled():
    order = ordered_for_viewer(*_four_specs(), viewer_cluster="power_user", enabled=True, rollout_p=1.0)
    assert order[0].chart_id == "engagement_line"


def test_disabled_keeps_default_order():
    order = ordered_for_viewer(*_four_specs(), viewer_cluster="power_user", enabled=False, rollout_p=1.0)
    assert [c.chart_id for c in order] == ["signups_bar", "engagement_line", "revenue_pie", "retention_heatmap"]


def test_zero_rollout_keeps_default_order_even_with_a_match():
    order = ordered_for_viewer(*_four_specs(), viewer_cluster="churn_risk", enabled=True, rollout_p=0.0)
    assert order[0].chart_id == "signups_bar"  # default order, not reordered


def test_rollout_p_samples_at_roughly_the_right_rate():
    specs = _four_specs()
    rng = random.Random(42)
    trials = 2000
    hits = sum(
        1 for _ in range(trials)
        if ordered_for_viewer(*specs, viewer_cluster="finance_viewer", enabled=True, rollout_p=0.3, rng=rng)[0].chart_id
        == "revenue_pie"
    )
    assert abs(hits / trials - 0.3) < 0.03
