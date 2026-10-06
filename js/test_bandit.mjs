// Real tests for ekplots-bandit.js — actual Beta draws, actual
// IntersectionObserver-driven dwell measurement (mocked DOM primitives,
// same pattern as test_tracking_hook.mjs, since no real browser is
// available in this environment).
import ekplotsBandit from './ekplots-bandit.js';
const { Bandit, InMemoryStorage, wireDwellTracking, orderedForViewer } = ekplotsBandit;

let failures = 0;
function check(name, fn) {
  try {
    fn();
    console.log(`PASS  ${name}`);
  } catch (e) {
    failures++;
    console.log(`FAIL  ${name}: ${e.message}`);
  }
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg || 'assertion failed');
}

// deterministic rng for tests that need real, repeatable draws
function seededRng(seed) {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648;
    return s / 2147483648;
  };
}

// ---- Bandit ----

check('addSlot includes control automatically', () => {
  const b = new Bandit(new InMemoryStorage());
  b.addSlot('hero', ['bar_vs_line']);
  const stats = b.stats('hero');
  assert(Object.keys(stats.arms).sort().join(',') === 'bar_vs_line,control');
});

check('addSlot is a no-op if the slot already exists', () => {
  const b = new Bandit(new InMemoryStorage());
  b.addSlot('hero', ['a']);
  b.recordOutcome('hero', 'a', true);
  b.addSlot('hero', ['a']); // should not reset
  assert(b.stats('hero').arms.a.successes === 1);
});

check('choose returns a real arm key', () => {
  const b = new Bandit(new InMemoryStorage());
  b.addSlot('hero', ['a', 'b']);
  const chosen = b.choose('hero');
  assert(['control', 'a', 'b'].includes(chosen));
});

check('heavily weighted arm wins almost always', () => {
  const b = new Bandit(new InMemoryStorage());
  b.addSlot('hero', ['high'], 'low');
  b.setPriorityWeight('hero', 'high', 10.0);
  const rng = seededRng(7);
  let wins = 0;
  for (let i = 0; i < 500; i++) {
    if (b.choose('hero', rng) === 'high') wins++;
  }
  assert(wins > 450, `expected >450 wins, got ${wins}`);
});

check('paused arm is never chosen', () => {
  const b = new Bandit(new InMemoryStorage());
  b.addSlot('hero', ['a']);
  b.pause('hero', 'a');
  const rng = seededRng(1);
  for (let i = 0; i < 50; i++) {
    assert(b.choose('hero', rng) === 'control');
  }
});

check('recordOutcome updates trials and successes', () => {
  const b = new Bandit(new InMemoryStorage());
  b.addSlot('hero', ['a']);
  b.recordOutcome('hero', 'a', true);
  b.recordOutcome('hero', 'a', false);
  const arm = b.stats('hero').arms.a;
  assert(arm.trials === 2 && arm.successes === 1);
});

check('recordDwell beats control average -> engaged', () => {
  const b = new Bandit(new InMemoryStorage());
  b.addSlot('hero', ['a']);
  for (let i = 0; i < 10; i++) b.recordDwell('hero', 'control', 1000);
  const engaged = b.recordDwell('hero', 'a', 5000);
  assert(engaged === true);
  assert(b.stats('hero').arms.a.successes === 1);
});

check('recordDwell below control average -> not engaged', () => {
  const b = new Bandit(new InMemoryStorage());
  b.addSlot('hero', ['a']);
  for (let i = 0; i < 10; i++) b.recordDwell('hero', 'control', 2000);
  const engaged = b.recordDwell('hero', 'a', 500);
  assert(engaged === false);
});

check('recordDwell with too little control history returns null, records nothing', () => {
  const b = new Bandit(new InMemoryStorage());
  b.addSlot('hero', ['a']);
  b.recordDwell('hero', 'control', 1000);
  b.recordDwell('hero', 'control', 2000); // only 2 samples, below MIN_CONTROL_SAMPLES
  const engaged = b.recordDwell('hero', 'a', 999999);
  assert(engaged === null);
  assert(b.stats('hero').arms.a.trials === 0);
});

check('recordDwell on the control arm itself never scores', () => {
  const b = new Bandit(new InMemoryStorage());
  b.addSlot('hero', ['a']);
  const result = b.recordDwell('hero', 'control', 5000);
  assert(result === null);
  assert(b.stats('hero').arms.control.trials === 0);
});

check('setPriorityWeight rejects non-positive weight', () => {
  const b = new Bandit(new InMemoryStorage());
  b.addSlot('hero', ['a']);
  let threw = false;
  try {
    b.setPriorityWeight('hero', 'a', 0);
  } catch (e) {
    threw = true;
  }
  assert(threw, 'expected setPriorityWeight(0) to throw');
});

// ---- orderedForViewer ----

function fourCharts() {
  return [
    { chartId: 'signups_bar', clusterKey: 'new_visitor' },
    { chartId: 'engagement_line', clusterKey: 'power_user' },
    { chartId: 'revenue_pie', clusterKey: 'finance_viewer' },
    { chartId: 'retention_heatmap', clusterKey: 'churn_risk' },
  ];
}

check('matching cluster moves to front when enabled and sampled', () => {
  const order = orderedForViewer(fourCharts(), { viewerCluster: 'power_user', enabled: true, rolloutP: 1.0 });
  assert(order[0].chartId === 'engagement_line');
});

check('disabled keeps default order', () => {
  const order = orderedForViewer(fourCharts(), { viewerCluster: 'power_user', enabled: false, rolloutP: 1.0 });
  assert(order.map((c) => c.chartId).join(',') === 'signups_bar,engagement_line,revenue_pie,retention_heatmap');
});

check('zero rollout keeps default order even with a match', () => {
  const order = orderedForViewer(fourCharts(), { viewerCluster: 'churn_risk', enabled: true, rolloutP: 0.0 });
  assert(order[0].chartId === 'signups_bar');
});

// ---- wireDwellTracking (mocked IntersectionObserver, same pattern as test_tracking_hook.mjs) ----

class FakeIntersectionObserver {
  constructor(cb) {
    this._cb = cb;
    FakeIntersectionObserver.instances.push(this);
  }
  observe(el) {
    this._observedEl = el;
  }
  disconnect() {}
  _enter() {
    this._cb([{ isIntersecting: true, intersectionRatio: 1.0, target: this._observedEl }]);
  }
  _leave() {
    this._cb([{ isIntersecting: false, intersectionRatio: 0, target: this._observedEl }]);
  }
}
FakeIntersectionObserver.instances = [];

function makeFakeCanvas() {
  return {};
}

check('wireDwellTracking reports a real dwell duration on exit', async () => {
  global.IntersectionObserver = FakeIntersectionObserver;
  FakeIntersectionObserver.instances = [];
  const canvas = makeFakeCanvas();
  let reported = null;
  wireDwellTracking(canvas, 'hero:a', (ms) => {
    reported = ms;
  });
  const observer = FakeIntersectionObserver.instances[0];
  observer._enter();
  await new Promise((r) => setTimeout(r, 120)); // clear the >=100ms floor
  observer._leave();
  assert(reported !== null, 'expected a dwell measurement');
  assert(reported >= 100, `expected >=100ms, got ${reported}`);
});

check('wireDwellTracking ignores a dwell shorter than 100ms', async () => {
  global.IntersectionObserver = FakeIntersectionObserver;
  FakeIntersectionObserver.instances = [];
  const canvas = makeFakeCanvas();
  let reported = null;
  wireDwellTracking(canvas, 'hero:a', (ms) => {
    reported = ms;
  });
  const observer = FakeIntersectionObserver.instances[0];
  observer._enter();
  observer._leave(); // near-instant, no await
  assert(reported === null, 'expected no dwell measurement for a sub-100ms view');
});

console.log(`\n${failures === 0 ? 'All tests passed.' : `${failures} test(s) failed.`}`);
process.exit(failures === 0 ? 0 : 1);
