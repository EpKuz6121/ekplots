/* ekplots' built-in adaptive personalization engine — the browser-native
 * sibling of the Python binding's ekplots/bandit.py (same reward math,
 * same JSON shape, so state is portable between them if you ever need
 * to inspect it from Python).
 *
 * This is what makes ekplots different from every other charting
 * library: it can measure, ON ITS OWN, which variant of a chart keeps a
 * visitor looking at it longest, and serve that variant more often over
 * time — no external analytics platform, no server, no SurveySync
 * tracker required. Dwell time is measured with ekplots' OWN
 * IntersectionObserver (same visibility-threshold design as
 * SurveySync's SectionDwellCollector, independently reimplemented here
 * so this module has zero dependency on window.__analytics existing at
 * all — see ekplots-draw.js's _wireTracking for the OTHER, SurveySync-
 * specific hook; the two are unrelated and can be used separately or
 * together).
 *
 * Usage (Node): const { Bandit, orderedForViewer } = require('./ekplots-bandit.js');
 * Usage (browser): <script src="ekplots-bandit.js"></script> — exposes window.ekplotsBandit
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.ekplotsBandit = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const MIN_CONTROL_SAMPLES = 10; // don't judge a variant against a control average built from noise
  const MAX_RECENT_DWELL_SAMPLES = 50; // rolling window per arm — recent behavior, not all-time

  // ---------------------------------------------------------- storage

  /** No persistence — state lives only as long as this object does.
   * Used by the test suite; fine for a short-lived script too. */
  class InMemoryStorage {
    constructor() {
      this._data = {};
    }
    load() {
      return JSON.parse(JSON.stringify(this._data));
    }
    save(data) {
      this._data = JSON.parse(JSON.stringify(data));
    }
  }

  /** Default storage in a real browser: one localStorage key, the
   * whole state as one JSON blob — same "simplest thing that works"
   * choice as the Python binding's JSONFileStorage, same concurrency
   * caveat (two tabs writing at once can race; fine for a single
   * visitor's own browser, not a substitute for a real backend). */
  class LocalStorageStorage {
    constructor(key) {
      this.key = key || 'ekplots_bandit';
    }
    load() {
      if (typeof localStorage === 'undefined') return {};
      const raw = localStorage.getItem(this.key);
      return raw ? JSON.parse(raw) : {};
    }
    save(data) {
      if (typeof localStorage === 'undefined') return;
      localStorage.setItem(this.key, JSON.stringify(data));
    }
  }

  function _defaultStorage() {
    return typeof localStorage !== 'undefined' ? new LocalStorageStorage() : new InMemoryStorage();
  }

  // ----------------------------------------------------------- bandit

  function _makeArm(variantKey) {
    return { variantKey, successes: 0, trials: 0, priorityWeight: 1.0, paused: false, recentDwellMs: [] };
  }

  /** One Beta(successes+1, trials-successes+1) draw per unpaused arm,
   * times priorityWeight; highest draw wins. Uses Math.random() —
   * callers needing determinism (tests) pass their own rng(). */
  function _betaSample(alpha, beta, rng) {
    // Beta via two Gammas (Marsaglia-Tsang-ish shape via sum-of-exponentials
    // for integer-ish small shape values here; successes/trials are
    // non-negative integers plus 1, so shape >= 1 always) — simplest
    // correct approach without a gamma-function dependency: for integer
    // k, Gamma(k, 1) is the sum of k Exp(1) draws.
    const gamma = (shape) => {
      let sum = 0;
      const k = Math.max(1, Math.round(shape));
      for (let i = 0; i < k; i++) sum += -Math.log(1 - rng());
      return sum;
    };
    const x = gamma(alpha);
    const y = gamma(beta);
    return x / (x + y);
  }

  class Bandit {
    constructor(storage) {
      this._storage = storage || _defaultStorage();
    }

    /** variants: array of variantKeys. controlKey is added automatically
     * if missing. A no-op if the slot already exists, so re-running
     * setup code never wipes accumulated stats. */
    addSlot(slotKey, variants, controlKey) {
      controlKey = controlKey || 'control';
      variants = variants.includes(controlKey) ? variants.slice() : [controlKey].concat(variants);
      const data = this._storage.load();
      data.slots = data.slots || {};
      if (data.slots[slotKey]) return;
      const arms = {};
      variants.forEach((v) => {
        arms[v] = _makeArm(v);
      });
      data.slots[slotKey] = { controlKey, arms };
      this._storage.save(data);
    }

    choose(slotKey, rng) {
      rng = rng || Math.random;
      const data = this._storage.load();
      const slot = data.slots[slotKey];
      const arms = Object.values(slot.arms).filter((a) => !a.paused);
      if (arms.length === 0) return slot.controlKey;
      let bestKey = arms[0].variantKey;
      let bestDraw = -1;
      arms.forEach((arm) => {
        const draw = _betaSample(arm.successes + 1, arm.trials - arm.successes + 1, rng) * arm.priorityWeight;
        if (draw > bestDraw) {
          bestDraw = draw;
          bestKey = arm.variantKey;
        }
      });
      return bestKey;
    }

    recordOutcome(slotKey, variantKey, engaged) {
      const data = this._storage.load();
      const arm = data.slots[slotKey].arms[variantKey];
      arm.trials += 1;
      if (engaged) arm.successes += 1;
      this._storage.save(data);
    }

    /** The automatic half of the loop: call this with a real measured
     * dwell time for a variant. Pushes it onto that arm's rolling
     * window; if variantKey is NOT the slot's control, compares it
     * against the control arm's recent average and records the
     * resulting engaged/not outcome. Returns the engaged bool (or null
     * if this was a control-arm sample, or there wasn't enough control
     * history yet to judge against). This is what lets the browser
     * binding run the whole measure-and-adapt loop with no caller-
     * supplied control samples, unlike the Python binding's
     * record_dwell (which has no events table of its own to pull a
     * live average from).
     */
    recordDwell(slotKey, variantKey, dwellMs) {
      const data = this._storage.load();
      const slot = data.slots[slotKey];
      const arm = slot.arms[variantKey];
      arm.recentDwellMs.push(dwellMs);
      if (arm.recentDwellMs.length > MAX_RECENT_DWELL_SAMPLES) arm.recentDwellMs.shift();
      this._storage.save(data);

      if (variantKey === slot.controlKey) return null; // builds the baseline only, doesn't score itself

      const controlSamples = slot.arms[slot.controlKey].recentDwellMs;
      if (controlSamples.length < MIN_CONTROL_SAMPLES) return null;
      const controlAvg = controlSamples.reduce((a, b) => a + b, 0) / controlSamples.length;
      const engaged = dwellMs > controlAvg;
      this.recordOutcome(slotKey, variantKey, engaged);
      return engaged;
    }

    /** The "on command" lever: bias an arm's draws immediately, without
     * waiting for the bandit to accumulate evidence on its own. Still
     * real exploration, not a hard override. */
    setPriorityWeight(slotKey, variantKey, weight) {
      if (weight <= 0) throw new RangeError('weight must be > 0 — use pause() to hard-exclude an arm');
      const data = this._storage.load();
      data.slots[slotKey].arms[variantKey].priorityWeight = weight;
      this._storage.save(data);
    }

    pause(slotKey, variantKey, paused) {
      paused = paused === undefined ? true : paused;
      const data = this._storage.load();
      data.slots[slotKey].arms[variantKey].paused = paused;
      this._storage.save(data);
    }

    stats(slotKey) {
      return this._storage.load().slots[slotKey];
    }
  }

  // ------------------------------------------------- dwell tracking hook

  /** Measures real dwell time on canvasEl using ekplots' own
   * IntersectionObserver (0.5 visibility threshold, same design as
   * SurveySync's SectionDwellCollector) and calls onDwell(dwellMs) each
   * time it leaves view. Independent of window.__analytics entirely —
   * this is what lets the bandit loop run with zero external tracker.
   * Flushes a still-open dwell window on page unload so the last view
   * of a session isn't silently dropped. */
  function wireDwellTracking(canvasEl, trackingKey, onDwell) {
    if (typeof IntersectionObserver === 'undefined') return;
    if (canvasEl.__ekplotsBanditTracked === trackingKey) return; // already wired for this exact variant
    canvasEl.__ekplotsBanditTracked = trackingKey;

    let since = null;
    const flush = () => {
      if (since === null) return;
      const dwellMs = Date.now() - since;
      since = null;
      if (dwellMs >= 100) onDwell(dwellMs);
    };

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
            if (since === null) since = Date.now();
          } else {
            flush();
          }
        });
      },
      { threshold: [0.5] }
    );
    observer.observe(canvasEl);

    if (typeof window !== 'undefined' && window.addEventListener) {
      window.addEventListener('beforeunload', flush);
    }
  }

  // ---------------------------------------------------- cluster router

  /** Reorders `charts` (array of {chartId, clusterKey, build, title})
   * so the one tagged for viewerCluster comes first — gated by
   * `enabled` (hard off switch) and `rolloutP` (the fraction of
   * viewers, chosen at random, who actually get the personalized
   * order; the rest see the default order regardless of their
   * cluster). Mirrors the Python binding's ordered_for_viewer exactly. */
  function orderedForViewer(charts, { viewerCluster, enabled, rolloutP, rng }) {
    rng = rng || Math.random;
    const defaultOrder = charts.slice();
    if (!enabled) return defaultOrder;
    if (rng() >= rolloutP) return defaultOrder;
    const best = charts.find((c) => c.clusterKey === viewerCluster);
    if (!best) return defaultOrder;
    return [best].concat(charts.filter((c) => c !== best));
  }

  return { Bandit, InMemoryStorage, LocalStorageStorage, wireDwellTracking, orderedForViewer };
});
