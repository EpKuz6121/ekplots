// Real end-to-end test against the compiled WASM module — run with:
//   node test_node.mjs
// Exits non-zero on any failure.
import ekplots from './ekplots.js';

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
function approx(a, b, eps = 1e-9) {
  return Math.abs(a - b) < eps;
}

await ekplots.ready;
console.log('WASM module loaded\n');

check('bar: tallest bar matches largest value', () => {
  const { bars } = ekplots.bar([10, 25, 15, 40]);
  const heights = bars.map((r) => r.h);
  const maxIdx = heights.indexOf(Math.max(...heights));
  assert(maxIdx === 3, `expected index 3, got ${maxIdx}`);
});

check('hbar: rotated, value dimension is w not h', () => {
  const { bars, horizontal } = ekplots.hbar([10, 25, 15, 40]);
  assert(horizontal === true);
  const widths = bars.map((r) => r.w);
  assert(widths.indexOf(Math.max(...widths)) === 3);
});

check('stacked_bar: taller category has a bigger combined stack', () => {
  const { segments } = ekplots.stackedBar({ a: [10, 20], b: [5, 15] });
  const cat0Top = Math.max(...segments[0].map((s) => s.y + s.h));
  const cat1Top = Math.max(...segments[1].map((s) => s.y + s.h));
  assert(cat1Top > cat0Top, `cat1Top=${cat1Top} should exceed cat0Top=${cat0Top}`);
});

check('line: bounds match real data range', () => {
  const { bounds } = ekplots.line([0, 1, 2, 3], [5, 3, 8, 2]);
  assert(bounds.yMin === 2 && bounds.yMax === 8, `got yMin=${bounds.yMin} yMax=${bounds.yMax}`);
});

check('line smooth: produces more points, endpoints match straight version', () => {
  const x = [0, 1, 2, 3, 4];
  const y = [10, 40, 15, 45, 20];
  const straight = ekplots.line(x, y, { smooth: false });
  const smooth = ekplots.line(x, y, { smooth: true });
  assert(smooth.points.length > straight.points.length, `smooth=${smooth.points.length} straight=${straight.points.length}`);
  assert(approx(smooth.points[0].x, straight.points[0].x) && approx(smooth.points[0].y, straight.points[0].y));
  const lastSmooth = smooth.points[smooth.points.length - 1];
  const lastStraight = straight.points[straight.points.length - 1];
  assert(approx(lastSmooth.x, lastStraight.x) && approx(lastSmooth.y, lastStraight.y), `last points differ: ${JSON.stringify(lastSmooth)} vs ${JSON.stringify(lastStraight)}`);
});

check('area: baseline pulls yMin down to 0', () => {
  const { bounds } = ekplots.area([0, 1, 2], [5, 8, 6], { baseline: 0.0 });
  assert(bounds.yMin === 0, `expected yMin=0, got ${bounds.yMin}`);
});

check('stacked_area: cumulative top matches sum of series at peak', () => {
  const { bounds } = ekplots.stackedArea([0, 1, 2], { a: [10, 12, 14], b: [8, 9, 7] });
  assert(approx(bounds.yMax, 21), `expected yMax=21, got ${bounds.yMax}`);
});

check('pie: slices sum to a full circle', () => {
  const { slices } = ekplots.pie([30, 20, 50]);
  const total = slices.reduce((sum, s) => sum + (s.endAngle - s.startAngle), 0);
  assert(approx(total, 2 * Math.PI, 1e-6), `total sweep=${total}`);
});

check('donut: has a real nonzero inner radius', () => {
  const { innerR } = ekplots.donut([30, 20, 50], { innerR: 0.6 });
  assert(innerR > 0, `innerR=${innerR}`);
});

check('funnel: stages never widen going down', () => {
  const { stages } = ekplots.funnel([1000, 640, 410, 180, 95]);
  const widths = stages.map((s) => Math.max(...s.trapezoid.map((p) => p.x)) - Math.min(...s.trapezoid.map((p) => p.x)));
  for (let i = 0; i < widths.length - 1; i++) {
    assert(widths[i] >= widths[i + 1] - 1e-9, `stage ${i} (${widths[i]}) narrower than stage ${i + 1} (${widths[i + 1]})`);
  }
});

check('histogram: bin_edges has n_bins+1 entries', () => {
  const values = Array.from({ length: 200 }, (_, i) => Math.sin(i) * 10 + 20);
  const { bins, binEdges } = ekplots.histogram(values, { bins: 8 });
  assert(bins.length === 8, `bins.length=${bins.length}`);
  assert(binEdges.length === 9, `binEdges.length=${binEdges.length}`);
});

check('boxplot: detects a real outlier', () => {
  const { groups } = ekplots.boxplot({ g: [1, 2, 3, 4, 5, 100] });
  assert(groups.g.outliers.includes(100), `outliers=${groups.g.outliers}`);
});

check('boxplot: no false positives on tight data', () => {
  const { groups } = ekplots.boxplot({ g: [10, 11, 12, 11, 10, 12, 11] });
  assert(groups.g.outliers.length === 0, `outliers=${groups.g.outliers}`);
});

check('scatter: point count matches input', () => {
  const { points } = ekplots.scatter([1, 2, 3], [4, 5, 6]);
  assert(points.length === 3);
});

check('bubble: radius scales by area (sqrt), not linearly', () => {
  // halfway between size_min and size_max should map to ~sqrt(0.5) of the
  // radius range, not 0.5 of it — the real area-proportional formula.
  const { bubbles } = ekplots.bubble([0, 1, 2], [0, 0, 0], [10, 55, 100], { minR: 10, maxR: 110 });
  const rMid = bubbles[1].r;
  const areaPrediction = 10 + Math.sqrt(0.5) * 100;
  const linearPrediction = 10 + 0.5 * 100;
  assert(approx(rMid, areaPrediction, 0.01), `rMid=${rMid} expected=${areaPrediction}`);
  assert(Math.abs(rMid - linearPrediction) > 15, 'radius looks linear, not area-proportional');
});

check('heatmap: hottest cell matches source matrix', () => {
  const matrix = [[0.1, 0.9], [0.3, 0.2]];
  const { valueMax, values } = ekplots.heatmap(matrix);
  assert(valueMax === 0.9);
  assert(values[0][1] === 0.9);
});

check('radar: axis count matches input', () => {
  const { seriesPoints, axisTicks } = ekplots.radar([3, 7, 5, 9, 4]);
  assert(seriesPoints.length === 5, `seriesPoints.length=${seriesPoints.length}`);
  assert(axisTicks.length === 5, `axisTicks.length=${axisTicks.length}`);
});

check('single-point line does not crash', () => {
  const { points } = ekplots.line([1], [5]);
  assert(points.length === 1);
});

check('bar with negative values', () => {
  const { bounds } = ekplots.bar([-10, 20, -5, 15]);
  assert(bounds.yMin < 0 && bounds.yMax > 0);
});

console.log(`\n${failures === 0 ? '🎉 ALL' : failures + ' FAILED, '}tests ${failures === 0 ? 'passed' : 'out of 20'}`);
process.exit(failures === 0 ? 0 : 1);
