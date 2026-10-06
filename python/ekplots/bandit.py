"""ekplots' built-in adaptive personalization engine.

This is what makes ekplots different from matplotlib, Plotly, Chart.js,
or D3: it doesn't just draw a chart, it can decide WHICH VARIANT of a
chart to draw, learn which one keeps people looking at it longest, and
serve that one more often over time. No external analytics platform, no
server, no database required — state lives in one JSON file by default
(zero extra dependencies), with a Storage interface so a host app can
swap in a real database later without touching the bandit math.

Two complementary, independently useful pieces:

- **Bandit** — Thompson-sampling over named arms (variant_key ->
  successes/trials/priority_weight) for A/B-ing VARIANTS OF ONE chart.
  Same reward math SurveySync's own production personalization bandit
  uses (routes_personalize.py's _thompson_sample) — the more an arm
  wins, the more often it gets drawn. Feed it outcomes with
  record_outcome() or record_dwell(); nudge an arm immediately with
  set_priority_weight(), independent of waiting for the bandit to
  converge on its own.
- **ordered_for_viewer / ChartVariant** — ranks several DIFFERENT charts
  (not variants of one chart) by which visitor cluster each is tagged
  for, so the chart that fits a given viewer best renders first. Gated
  by an `enabled` switch and a `rollout_p` fraction — what share of
  viewers, chosen at random, actually get the personalized order; the
  rest see the default order regardless of their cluster. This is the
  same design validated in practice before landing here — now a real,
  tested part of the library instead of a one-off script.

See the JS binding (ekplots-bandit.js) for the browser-native version,
which measures dwell time itself via IntersectionObserver — no external
tracker needed there either.
"""
from __future__ import annotations

import json
import os
import random
import threading
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

MIN_CONTROL_SAMPLES = 10  # don't judge a variant against a control average built from noise


# ---------------------------------------------------------------- storage

class JSONFileStorage:
    """Default storage: one JSON file, read fully on load, rewritten
    fully (atomically, via os.replace) on save. Deliberately the
    simplest thing that works for a notebook, a single dashboard
    process, or a demo.

    Not a substitute for a real database under concurrent writers —
    two processes writing to the same path can race. Implement
    load()/save() yourself (same shape) if you need that."""

    def __init__(self, path: str):
        self.path = path

    def load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        with open(self.path, "r") as f:
            return json.load(f)

    def save(self, data: dict) -> None:
        tmp = f"{self.path}.tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)  # atomic on POSIX — never a half-written file


class InMemoryStorage:
    """No persistence at all — state lives only as long as this object
    does. Used by the test suite; also fine for a short-lived script
    that doesn't need to remember anything between runs."""

    def __init__(self):
        self._data: dict = {}

    def load(self) -> dict:
        return json.loads(json.dumps(self._data))  # cheap deep copy

    def save(self, data: dict) -> None:
        self._data = json.loads(json.dumps(data))


# ----------------------------------------------------------------- bandit

@dataclass
class Arm:
    variant_key: str
    successes: int = 0
    trials: int = 0
    priority_weight: float = 1.0
    paused: bool = False


class Bandit:
    """Thompson-sampling bandit over one or more "slots," each with
    several named arms (always including a "control"). Same math as
    SurveySync's production bandit — ported here so ekplots can run the
    whole measure-and-adapt loop on its own.
    """

    def __init__(self, storage=None, path: Optional[str] = None):
        if storage is not None and path is not None:
            raise ValueError("pass storage OR path, not both")
        self._storage = storage if storage is not None else JSONFileStorage(path or "ekplots_bandit.json")
        self._lock = threading.Lock()

    def add_slot(self, slot_key: str, variants, control_key: str = "control") -> None:
        """variants: iterable of variant_keys. control_key is added
        automatically if not already present. A no-op if the slot
        already exists, so re-running setup code never wipes
        accumulated stats."""
        variants = list(variants)
        if control_key not in variants:
            variants = [control_key] + variants
        with self._lock:
            data = self._storage.load()
            slots = data.setdefault("slots", {})
            if slot_key in slots:
                return
            slots[slot_key] = {
                "control_key": control_key,
                "arms": {v: asdict(Arm(variant_key=v)) for v in variants},
            }
            self._storage.save(data)

    def choose(self, slot_key: str, rng: Optional[random.Random] = None) -> str:
        """One Beta(successes+1, trials-successes+1) draw per unpaused
        arm, multiplied by priority_weight; highest draw wins. Falls
        back to the slot's control_key if every arm is paused."""
        rng = rng or random
        data = self._storage.load()
        slot = data["slots"][slot_key]
        arms = [a for a in slot["arms"].values() if not a["paused"]]
        if not arms:
            return slot["control_key"]
        best_key, best_draw = arms[0]["variant_key"], -1.0
        for arm in arms:
            draw = rng.betavariate(arm["successes"] + 1, arm["trials"] - arm["successes"] + 1) * arm["priority_weight"]
            if draw > best_draw:
                best_key, best_draw = arm["variant_key"], draw
        return best_key

    def record_outcome(self, slot_key: str, variant_key: str, engaged: bool) -> None:
        with self._lock:
            data = self._storage.load()
            arm = data["slots"][slot_key]["arms"][variant_key]
            arm["trials"] += 1
            if engaged:
                arm["successes"] += 1
            self._storage.save(data)

    def record_dwell(
        self,
        slot_key: str,
        variant_key: str,
        dwell_ms: float,
        control_dwell_samples: Optional[list] = None,
        min_control_samples: int = MIN_CONTROL_SAMPLES,
    ) -> bool:
        """Convenience wrapper matching SurveySync's chart_reward.py
        reward definition: engaged = this dwell beat the AVERAGE of
        control_dwell_samples, a list of past control dwell_ms values
        you supply. ekplots' Python binding has no events table of its
        own to pull these from automatically — the JS binding's
        tracking hook (ekplots-bandit.js) tracks this for real in the
        browser instead. Returns the engaged bool it recorded.
        """
        control_dwell_samples = control_dwell_samples or []
        if len(control_dwell_samples) < min_control_samples:
            engaged = False  # not enough control data to know what "better" means yet
        else:
            engaged = dwell_ms > (sum(control_dwell_samples) / len(control_dwell_samples))
        self.record_outcome(slot_key, variant_key, engaged)
        return engaged

    def set_priority_weight(self, slot_key: str, variant_key: str, weight: float) -> None:
        """The "on command" lever: bias an arm's draws immediately,
        without waiting for the bandit to accumulate evidence on its
        own. Still real exploration, not a hard override — see
        test_bandit.py's weighted-draw tests."""
        if weight <= 0:
            raise ValueError("weight must be > 0 — use pause() to hard-exclude an arm")
        with self._lock:
            data = self._storage.load()
            data["slots"][slot_key]["arms"][variant_key]["priority_weight"] = weight
            self._storage.save(data)

    def pause(self, slot_key: str, variant_key: str, paused: bool = True) -> None:
        with self._lock:
            data = self._storage.load()
            data["slots"][slot_key]["arms"][variant_key]["paused"] = paused
            self._storage.save(data)

    def stats(self, slot_key: str) -> dict:
        """Read-only snapshot of a slot's current arms, for inspection."""
        data = self._storage.load()
        return data["slots"][slot_key]


# --------------------------------------------------------- cluster router

@dataclass
class ChartVariant:
    """One of several DIFFERENT charts being ranked for a viewer — not
    variants of the same chart (that's Bandit's job). cluster_key is
    which visitor segment this particular chart is the best fit for."""
    chart_id: str
    cluster_key: str
    build: Callable[[], object]
    title: str = ""


def ordered_for_viewer(
    *charts: ChartVariant,
    viewer_cluster: str,
    enabled: bool,
    rollout_p: float,
    rng: Optional[random.Random] = None,
) -> list:
    """Reorders `charts` so the one tagged for viewer_cluster comes
    first — gated by `enabled` (hard off switch) and `rollout_p`
    (the fraction of viewers, chosen at random, who actually get the
    personalized order; the rest see the default order regardless of
    their cluster, which is what makes rollout_p a real sampling rate
    rather than just a label).
    """
    default_order = list(charts)
    if not enabled:
        return default_order
    rng = rng or random
    if rng.random() >= rollout_p:
        return default_order
    matches = [c for c in charts if c.cluster_key == viewer_cluster]
    if not matches:
        return default_order
    best = matches[0]
    rest = [c for c in charts if c is not best]
    return [best] + rest
