// Proves the ekplots <-> SurveySync tracker integration end to end on
// the ekplots side: that draw({chartId}) really calls
// window.__analytics.emitChartEvent with the exact camelCase shape the
// real tracker (SurveySync's tracker/src/index.ts) expects — not just
// that each side's code reads correctly in isolation. Mocks the DOM
// primitives _wireTracking needs (IntersectionObserver, a canvas-like
// element) since no real browser is available in this environment.
import { createCanvas } from 'canvas';
import ekplots from './ekplots-draw.js';

await ekplots.ready;

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

// --- minimal DOM mocks, just enough for _wireTracking to run ---

class FakeIntersectionObserver {
  constructor(cb) {
    this._cb = cb;
    FakeIntersectionObserver.instances.push(this);
  }
  observe(el) {
    this._observedEl = el;
  }
  disconnect() {
    this._disconnected = true;
  }
  // test helper: simulate the chart scrolling into view
  _triggerIntersect() {
    this._cb([{ isIntersecting: true, target: this._observedEl }]);
  }
}
FakeIntersectionObserver.instances = [];

function makeFakeCanvas() {
  const listeners = {};
  return {
    getBoundingClientRect: () => ({ left: 10, top: 20 }),
    addEventListener: (type, fn) => {
      listeners[type] = fn;
    },
    _fireClick: (clientX, clientY) => listeners.click({ clientX, clientY }),
  };
}

check('chart_view fires through to emitChartEvent with correct camelCase shape', () => {
  const calls = [];
  global.window = {
    __analytics: {
      getConsent: () => true,
      emitChartEvent: (event) => calls.push(event),
    },
  };
  global.IntersectionObserver = FakeIntersectionObserver;
  FakeIntersectionObserver.instances.length = 0;

  const fakeCanvasEl = makeFakeCanvas();
  const canvas = createCanvas(400, 300);
  const ctx = canvas.getContext('2d');
  Object.defineProperty(ctx, 'canvas', { value: fakeCanvasEl, writable: true });
  const layout = ekplots.bar([10, 25, 15, 40]);
  ekplots.draw(ctx, layout, { chartId: 'test-chart-1' });

  assert(FakeIntersectionObserver.instances.length === 1, 'no IntersectionObserver was created');
  FakeIntersectionObserver.instances[0]._triggerIntersect();

  assert(calls.length === 1, `expected 1 emitChartEvent call, got ${calls.length}`);
  assert(calls[0].type === 'chart_view', `wrong type: ${calls[0].type}`);
  assert(calls[0].chartId === 'test-chart-1', `wrong chartId: ${calls[0].chartId}`);
  assert(calls[0].chart_id === undefined, 'must be camelCase chartId, not chart_id — the tracker does that translation, not ekplots');

  delete global.window;
  delete global.IntersectionObserver;
});

check('chart_interact fires on click with correct canvas-relative coordinates', () => {
  const calls = [];
  global.window = {
    __analytics: {
      getConsent: () => true,
      emitChartEvent: (event) => calls.push(event),
    },
  };
  global.IntersectionObserver = FakeIntersectionObserver;
  FakeIntersectionObserver.instances.length = 0;

  const fakeCanvasEl = makeFakeCanvas();
  const canvas = createCanvas(400, 300);
  const ctx = canvas.getContext('2d');
  Object.defineProperty(ctx, 'canvas', { value: fakeCanvasEl, writable: true });
  const layout = ekplots.bar([10, 25, 15, 40]);
  ekplots.draw(ctx, layout, { chartId: 'test-chart-2' });

  fakeCanvasEl._fireClick(60, 90); // clientX, clientY — rect.left=10, rect.top=20

  assert(calls.length === 1, `expected 1 emitChartEvent call, got ${calls.length}`);
  assert(calls[0].type === 'chart_interact', `wrong type: ${calls[0].type}`);
  assert(calls[0].chartId === 'test-chart-2');
  assert(calls[0].interactionType === 'click', `wrong interactionType: ${calls[0].interactionType}`);
  assert(calls[0].x === 50 && calls[0].y === 70, `wrong coords: x=${calls[0].x} y=${calls[0].y}`);

  delete global.window;
  delete global.IntersectionObserver;
});

check('no window.__analytics means draw() does not throw and emits nothing', () => {
  delete global.window;
  const canvas = createCanvas(400, 300);
  const ctx = canvas.getContext('2d');
  const layout = ekplots.bar([10, 25, 15, 40]);
  ekplots.draw(ctx, layout, { chartId: 'standalone-no-tracker' }); // must not throw
});

check('consent not granted means no observer is wired at all', () => {
  const calls = [];
  global.window = {
    __analytics: {
      getConsent: () => false,
      emitChartEvent: (event) => calls.push(event),
    },
  };
  global.IntersectionObserver = FakeIntersectionObserver;
  FakeIntersectionObserver.instances.length = 0;

  const canvas = createCanvas(400, 300);
  const ctx = canvas.getContext('2d');
  const layout = ekplots.bar([10, 25, 15, 40]);
  ekplots.draw(ctx, layout, { chartId: 'no-consent-chart' });

  assert(FakeIntersectionObserver.instances.length === 0, 'an observer was wired despite no consent');
  delete global.window;
  delete global.IntersectionObserver;
});

console.log(`\n${failures === 0 ? '🎉 ALL' : failures + ' FAILED,'} tracking-hook integration tests ${failures === 0 ? 'passed' : ''}`);
process.exit(failures === 0 ? 0 : 1);
