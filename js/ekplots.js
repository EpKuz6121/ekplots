/* ekplots — JS binding over the real WASM-compiled C core (ekplots_wasm.js
 * / ekplots_wasm.wasm, built by build.sh from the SAME ekplots.c the
 * Python binding uses). Mirrors docs/SPEC.md's call signatures.
 *
 * Every *_layout() function below:
 *   1. Writes the caller's JS arrays into WASM linear memory (malloc + a
 *      typed-array view write)
 *   2. Calls the real C function via its _boxed() shim (see shim.c) —
 *      the shim exists purely so the output struct comes back through
 *      an EXPLICIT pointer parameter instead of relying on the WASM
 *      struct-return ABI
 *   3. Reads the result struct back out of WASM memory at EXACT offsets
 *      — confirmed directly from the actual wasm32 compiler output
 *      (introspect.c), never hand-guessed. wasm32 uses 4-byte pointers
 *      and 4-byte size_t, NOT 8-byte like the native Python/ctypes
 *      build — these offsets are specific to this target, by design.
 *   4. Copies everything into plain JS objects/arrays, then calls the
 *      matching ekplots_<name>_free() so the malloc'd WASM memory
 *      doesn't leak — a caller never touches a WASM pointer directly.
 *
 * Usage (Node):
 *   const ekplots = require('./ekplots.js');
 *   await ekplots.ready;
 *   const layout = ekplots.bar([10, 25, 15, 40]);
 *
 * Usage (browser): include ekplots_wasm.js then this file as two plain
 * <script> tags (same pattern as the SurveySync tracker's own embed —
 * no bundler required), then `await ekplots.ready` before calling
 * anything that needs the WASM module loaded.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('./ekplots_wasm.js'));
  } else {
    root.ekplots = factory(root.createEkplotsModule);
  }
})(typeof self !== 'undefined' ? self : this, function (createEkplotsModule) {
  'use strict';

  let Module = null;
  const ready = createEkplotsModule().then((m) => {
    Module = m;
    return m;
  });

  // ---- low-level memory helpers ----

  function writeDoubleArray(values) {
    const n = values.length;
    const ptr = Module._malloc(n * 8);
    Module.HEAPF64.set(Float64Array.from(values), ptr / 8);
    return ptr;
  }

  /** For `const double* const*` params (stacked_bar/stacked_area/boxplot):
   * malloc one buffer per inner array, then a buffer of pointers to them. */
  function writePointerArray(arraysOfValues) {
    const innerPtrs = arraysOfValues.map(writeDoubleArray);
    const outerPtr = Module._malloc(innerPtrs.length * 4); // wasm32: pointers are 4 bytes
    const view = new DataView(Module.HEAPU8.buffer);
    innerPtrs.forEach((p, i) => view.setUint32(outerPtr + i * 4, p, true));
    return { outerPtr, innerPtrs };
  }

  function writeSizeArray(values) {
    const ptr = Module._malloc(values.length * 4); // wasm32: size_t is 4 bytes
    const view = new DataView(Module.HEAPU8.buffer);
    values.forEach((v, i) => view.setUint32(ptr + i * 4, v, true));
    return ptr;
  }

  function freeAll(...ptrs) {
    ptrs.forEach((p) => p && Module._free(p));
  }

  function dv() {
    return new DataView(Module.HEAPU8.buffer);
  }

  function readF64(ptr) {
    return dv().getFloat64(ptr, true);
  }
  function readU32(ptr) {
    return dv().getUint32(ptr, true);
  }
  function readI32(ptr) {
    return dv().getInt32(ptr, true);
  }

  function readDoubleArray(ptr, n) {
    const out = new Array(n);
    const view = dv();
    for (let i = 0; i < n; i++) out[i] = view.getFloat64(ptr + i * 8, true);
    return out;
  }

  function readBounds(ptr) {
    return {
      xMin: readF64(ptr), xMax: readF64(ptr + 8),
      yMin: readF64(ptr + 16), yMax: readF64(ptr + 24),
    };
  }

  function readRect(ptr) {
    return { x: readF64(ptr), y: readF64(ptr + 8), w: readF64(ptr + 16), h: readF64(ptr + 24) };
  }
  function readRects(ptr, n) {
    const out = [];
    for (let i = 0; i < n; i++) out.push(readRect(ptr + i * 32));
    return out;
  }

  function readPoint(ptr) {
    return { x: readF64(ptr), y: readF64(ptr + 8) };
  }
  function readPoints(ptr, n) {
    const out = [];
    for (let i = 0; i < n; i++) out.push(readPoint(ptr + i * 16));
    return out;
  }

  function readArc(ptr) {
    return {
      cx: readF64(ptr), cy: readF64(ptr + 8), r: readF64(ptr + 16),
      startAngle: readF64(ptr + 24), endAngle: readF64(ptr + 32),
    };
  }
  function readArcs(ptr, n) {
    const out = [];
    for (let i = 0; i < n; i++) out.push(readArc(ptr + i * 40));
    return out;
  }

  function readBubble(ptr) {
    return { x: readF64(ptr), y: readF64(ptr + 8), r: readF64(ptr + 16) };
  }
  function readBubbles(ptr, n) {
    const out = [];
    for (let i = 0; i < n; i++) out.push(readBubble(ptr + i * 24));
    return out;
  }

  // ---- options structs (packed in the exact field order ekplots.h declares) ----
  // Offsets confirmed via introspect.c against the real wasm32 build —
  // see that file's output in the repo for the ground truth these match.

  function writeBarOptions(width, height, barGap, horizontal) {
    const ptr = Module._malloc(32);
    const view = dv();
    view.setFloat64(ptr, width, true);
    view.setFloat64(ptr + 8, height, true);
    view.setFloat64(ptr + 16, barGap, true);
    view.setInt32(ptr + 24, horizontal ? 1 : 0, true);
    return ptr;
  }

  // ---- public API ----

  const SMOOTH_SAMPLES_NOTE = 'see docs/SPEC.md';
  void SMOOTH_SAMPLES_NOTE;

  function bar(values, opts) {
    opts = opts || {};
    const width = opts.width ?? 400, height = opts.height ?? 300;
    const barGap = opts.barGap ?? 0.2;
    const horizontal = !!opts.horizontal;
    const n = values.length;

    const valuesPtr = writeDoubleArray(values);
    const optsPtr = writeBarOptions(width, height, barGap, horizontal);
    const outPtr = Module._malloc(40); // sizeof(EKBarLayout)

    Module._ekplots_bar_layout_boxed(valuesPtr, n, optsPtr, outPtr);

    const barsPtr = readU32(outPtr);
    const realN = readU32(outPtr + 4);
    const bounds = readBounds(outPtr + 8);
    const bars = readRects(barsPtr, realN);

    Module._ekplots_bar_free(outPtr);
    freeAll(valuesPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'bar', bars, bounds, width, height, labels: opts.labels || null, horizontal, chartId: opts.chartId || null };
  }

  function hbar(values, opts) {
    return bar(values, Object.assign({}, opts, { horizontal: true }));
  }

  function line(x, y, opts) {
    opts = opts || {};
    const width = opts.width ?? 400, height = opts.height ?? 300;
    const smooth = opts.smooth ? 1 : 0;
    const n = x.length;

    const xPtr = writeDoubleArray(x);
    const yPtr = writeDoubleArray(y);
    const optsPtr = Module._malloc(24); // width, height, int smooth (padded)
    { const view = dv(); view.setFloat64(optsPtr, width, true); view.setFloat64(optsPtr + 8, height, true); view.setInt32(optsPtr + 16, smooth, true); }
    const outPtr = Module._malloc(40); // sizeof(EKLineLayout)

    Module._ekplots_line_layout_boxed(xPtr, yPtr, n, optsPtr, outPtr);

    const pointsPtr = readU32(outPtr);
    const realN = readU32(outPtr + 4);
    const bounds = readBounds(outPtr + 8);
    const points = readPoints(pointsPtr, realN);

    Module._ekplots_line_free(outPtr);
    freeAll(xPtr, yPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'line', points, bounds, width, height };
  }

  function area(x, y, opts) {
    opts = opts || {};
    const width = opts.width ?? 400, height = opts.height ?? 300;
    const baseline = opts.baseline ?? 0.0;
    const n = x.length;

    const xPtr = writeDoubleArray(x);
    const yPtr = writeDoubleArray(y);
    const optsPtr = Module._malloc(24);
    { const view = dv(); view.setFloat64(optsPtr, width, true); view.setFloat64(optsPtr + 8, height, true); view.setFloat64(optsPtr + 16, baseline, true); }
    const outPtr = Module._malloc(48); // sizeof(EKAreaLayout)

    Module._ekplots_area_layout_boxed(xPtr, yPtr, n, optsPtr, outPtr);

    const pointsPtr = readU32(outPtr);
    const realN = readU32(outPtr + 4);
    const baselineY = readF64(outPtr + 8);
    const bounds = readBounds(outPtr + 16);
    const points = readPoints(pointsPtr, realN);

    Module._ekplots_area_free(outPtr);
    freeAll(xPtr, yPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'area', points, baselineY, bounds, width, height };
  }

  function stackedBar(series, opts) {
    opts = opts || {};
    const width = opts.width ?? 400, height = opts.height ?? 300, barGap = opts.barGap ?? 0.2;
    const seriesNames = Object.keys(series);
    const nSeries = seriesNames.length;
    const nCategories = series[seriesNames[0]].length;

    const { outerPtr, innerPtrs } = writePointerArray(seriesNames.map((name) => series[name]));
    const optsPtr = Module._malloc(32); // width, height, bar_gap, n_series(size_t=4 bytes, padded to 8)
    { const view = dv(); view.setFloat64(optsPtr, width, true); view.setFloat64(optsPtr + 8, height, true); view.setFloat64(optsPtr + 16, barGap, true); view.setUint32(optsPtr + 24, nSeries, true); }
    const outPtr = Module._malloc(48); // sizeof(EKStackedBarLayout)

    Module._ekplots_stacked_bar_layout_boxed(outerPtr, nSeries, nCategories, optsPtr, outPtr);

    const segmentsPtr = readU32(outPtr);
    const realNCategories = readU32(outPtr + 4);
    const realNSeries = readU32(outPtr + 8);
    const bounds = readBounds(outPtr + 16);
    const flatSegments = readRects(segmentsPtr, realNCategories * realNSeries);
    const segments = [];
    for (let c = 0; c < realNCategories; c++) segments.push(flatSegments.slice(c * realNSeries, (c + 1) * realNSeries));

    Module._ekplots_stacked_bar_free(outPtr);
    freeAll(...innerPtrs, outerPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'stackedBar', segments, seriesNames, bounds, width, height, labels: opts.labels || null };
  }

  function pie(values, opts) {
    opts = opts || {};
    const cx = opts.cx ?? 150, cy = opts.cy ?? 150, r = opts.r ?? 140;
    const n = values.length;

    const valuesPtr = writeDoubleArray(values);
    const optsPtr = Module._malloc(24);
    { const view = dv(); view.setFloat64(optsPtr, cx, true); view.setFloat64(optsPtr + 8, cy, true); view.setFloat64(optsPtr + 16, r, true); }
    const outPtr = Module._malloc(8); // sizeof(EKPieLayout)

    Module._ekplots_pie_layout_boxed(valuesPtr, n, optsPtr, outPtr);
    const slicesPtr = readU32(outPtr);
    const realN = readU32(outPtr + 4);
    const slices = readArcs(slicesPtr, realN);

    Module._ekplots_pie_free(outPtr);
    freeAll(valuesPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'pie', slices, labels: opts.labels || null, innerR: 0 };
  }

  function donut(values, opts) {
    opts = opts || {};
    const cx = opts.cx ?? 150, cy = opts.cy ?? 150, r = opts.r ?? 140;
    const innerRFrac = opts.innerR ?? 0.6;
    const n = values.length;

    const valuesPtr = writeDoubleArray(values);
    const optsPtr = Module._malloc(32);
    { const view = dv(); view.setFloat64(optsPtr, cx, true); view.setFloat64(optsPtr + 8, cy, true); view.setFloat64(optsPtr + 16, r, true); view.setFloat64(optsPtr + 24, innerRFrac * r, true); }
    const outPtr = Module._malloc(16); // sizeof(EKDonutLayout)

    Module._ekplots_donut_layout_boxed(valuesPtr, n, optsPtr, outPtr);
    const slicesPtr = readU32(outPtr);
    const realN = readU32(outPtr + 4);
    const innerR = readF64(outPtr + 8);
    const slices = readArcs(slicesPtr, realN);

    Module._ekplots_donut_free(outPtr);
    freeAll(valuesPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'donut', slices, labels: opts.labels || null, innerR };
  }

  function funnel(values, opts) {
    opts = opts || {};
    const width = opts.width ?? 400, height = opts.height ?? 300, stageGap = opts.stageGap ?? 6;
    const n = values.length;

    const valuesPtr = writeDoubleArray(values);
    const optsPtr = Module._malloc(24);
    { const view = dv(); view.setFloat64(optsPtr, width, true); view.setFloat64(optsPtr + 8, height, true); view.setFloat64(optsPtr + 16, stageGap, true); }
    const outPtr = Module._malloc(8); // sizeof(EKFunnelLayout)

    Module._ekplots_funnel_layout_boxed(valuesPtr, n, optsPtr, outPtr);
    const stagesPtr = readU32(outPtr);
    const realN = readU32(outPtr + 4);
    const stages = [];
    for (let i = 0; i < realN; i++) {
      const base = stagesPtr + i * 88; // sizeof(EKFunnelStage)
      const trapezoid = readPoints(base, 4);
      stages.push({
        trapezoid,
        value: readF64(base + 64),
        pctOfFirst: readF64(base + 72),
        pctOfPrevious: readF64(base + 80),
      });
    }

    Module._ekplots_funnel_free(outPtr);
    freeAll(valuesPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'funnel', stages, labels: opts.labels || null };
  }

  function histogram(values, opts) {
    opts = opts || {};
    const width = opts.width ?? 400, height = opts.height ?? 300, bins = opts.bins ?? 0;
    const n = values.length;

    const valuesPtr = writeDoubleArray(values);
    const optsPtr = Module._malloc(24); // width, height, n_bins(size_t=4, padded)
    { const view = dv(); view.setFloat64(optsPtr, width, true); view.setFloat64(optsPtr + 8, height, true); view.setUint32(optsPtr + 16, bins, true); }
    const outPtr = Module._malloc(48); // sizeof(EKHistogramLayout)

    Module._ekplots_histogram_layout_boxed(valuesPtr, n, optsPtr, outPtr);
    const binsPtr = readU32(outPtr);
    const nBins = readU32(outPtr + 4);
    const edgesPtr = readU32(outPtr + 8);
    const bounds = readBounds(outPtr + 16);
    const binRects = readRects(binsPtr, nBins);
    const binEdges = readDoubleArray(edgesPtr, nBins + 1);

    Module._ekplots_histogram_free(outPtr);
    freeAll(valuesPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'histogram', bins: binRects, binEdges, bounds };
  }

  function boxplot(groups, opts) {
    opts = opts || {};
    const width = opts.width ?? 400, height = opts.height ?? 300, boxWidth = opts.boxWidth ?? 0.5;
    const names = Object.keys(groups);
    const nGroups = names.length;

    const { outerPtr, innerPtrs } = writePointerArray(names.map((name) => groups[name]));
    const sizesPtr = writeSizeArray(names.map((name) => groups[name].length));
    const optsPtr = Module._malloc(24);
    { const view = dv(); view.setFloat64(optsPtr, width, true); view.setFloat64(optsPtr + 8, height, true); view.setFloat64(optsPtr + 16, boxWidth, true); }
    const outPtr = Module._malloc(40); // sizeof(EKBoxplotLayout)

    Module._ekplots_boxplot_layout_boxed(outerPtr, sizesPtr, nGroups, optsPtr, outPtr);
    const groupsPtr = readU32(outPtr);
    const realNGroups = readU32(outPtr + 4);
    const bounds = readBounds(outPtr + 8);

    const out = {};
    for (let i = 0; i < realNGroups; i++) {
      const base = groupsPtr + i * 112; // sizeof(EKBoxplotStats)
      const outliersPtr = readU32(base + 40);
      const nOutliers = readU32(base + 44);
      out[names[i]] = {
        min: readF64(base), q1: readF64(base + 8), median: readF64(base + 16),
        q3: readF64(base + 24), max: readF64(base + 32),
        outliers: readDoubleArray(outliersPtr, nOutliers),
        box: readRect(base + 48),
        whiskerLow: readPoint(base + 80),
        whiskerHigh: readPoint(base + 96),
      };
    }

    Module._ekplots_boxplot_free(outPtr);
    freeAll(...innerPtrs, outerPtr, sizesPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'boxplot', groups: out, bounds, height };
  }

  function scatter(x, y, opts) {
    opts = opts || {};
    const width = opts.width ?? 400, height = opts.height ?? 300, pointRadius = opts.pointRadius ?? 4;
    const n = x.length;

    const xPtr = writeDoubleArray(x);
    const yPtr = writeDoubleArray(y);
    const optsPtr = Module._malloc(24);
    { const view = dv(); view.setFloat64(optsPtr, width, true); view.setFloat64(optsPtr + 8, height, true); view.setFloat64(optsPtr + 16, pointRadius, true); }
    const outPtr = Module._malloc(40); // sizeof(EKScatterLayout)

    Module._ekplots_scatter_layout_boxed(xPtr, yPtr, n, optsPtr, outPtr);
    const pointsPtr = readU32(outPtr);
    const realN = readU32(outPtr + 4);
    const bounds = readBounds(outPtr + 8);
    const points = readPoints(pointsPtr, realN);

    Module._ekplots_scatter_free(outPtr);
    freeAll(xPtr, yPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'scatter', points, bounds, width, height, labels: opts.labels || null };
  }

  function bubble(x, y, size, opts) {
    opts = opts || {};
    const width = opts.width ?? 400, height = opts.height ?? 300;
    const minR = opts.minR ?? 4, maxR = opts.maxR ?? 40;
    const n = x.length;

    const xPtr = writeDoubleArray(x);
    const yPtr = writeDoubleArray(y);
    const sizePtr = writeDoubleArray(size);
    const optsPtr = Module._malloc(32);
    { const view = dv(); view.setFloat64(optsPtr, width, true); view.setFloat64(optsPtr + 8, height, true); view.setFloat64(optsPtr + 16, minR, true); view.setFloat64(optsPtr + 24, maxR, true); }
    const outPtr = Module._malloc(40); // sizeof(EKBubbleLayout)

    Module._ekplots_bubble_layout_boxed(xPtr, yPtr, sizePtr, n, optsPtr, outPtr);
    const bubblesPtr = readU32(outPtr);
    const realN = readU32(outPtr + 4);
    const bounds = readBounds(outPtr + 8);
    const bubbles = readBubbles(bubblesPtr, realN);

    Module._ekplots_bubble_free(outPtr);
    freeAll(xPtr, yPtr, sizePtr, optsPtr, outPtr);
    return { __ekplotsKind: 'bubble', bubbles, bounds, width, height, labels: opts.labels || null };
  }

  function heatmap(matrix, opts) {
    opts = opts || {};
    const width = opts.width ?? 400, height = opts.height ?? 400, cellGap = opts.cellGap ?? 2;
    const nRows = matrix.length, nCols = matrix[0].length;
    const flat = [];
    for (const row of matrix) for (const v of row) flat.push(v);

    const valuesPtr = writeDoubleArray(flat);
    const optsPtr = Module._malloc(24);
    { const view = dv(); view.setFloat64(optsPtr, width, true); view.setFloat64(optsPtr + 8, height, true); view.setFloat64(optsPtr + 16, cellGap, true); }
    const outPtr = Module._malloc(32); // sizeof(EKHeatmapLayout)

    Module._ekplots_heatmap_layout_boxed(valuesPtr, nRows, nCols, optsPtr, outPtr);
    const cellsPtr = readU32(outPtr);
    const realNRows = readU32(outPtr + 4);
    const realNCols = readU32(outPtr + 8);
    const valueMin = readF64(outPtr + 16);
    const valueMax = readF64(outPtr + 24);
    const flatCells = readRects(cellsPtr, realNRows * realNCols);
    const cells = [];
    for (let r = 0; r < realNRows; r++) cells.push(flatCells.slice(r * realNCols, (r + 1) * realNCols));

    Module._ekplots_heatmap_free(outPtr);
    freeAll(valuesPtr, optsPtr, outPtr);
    return {
      __ekplotsKind: 'heatmap',
      cells, values: matrix, valueMin, valueMax,
      rowLabels: opts.rowLabels || null, colLabels: opts.colLabels || null,
    };
  }

  function radar(values, opts) {
    opts = opts || {};
    const cx = opts.cx ?? 150, cy = opts.cy ?? 150, r = opts.r ?? 120;
    const n = values.length;

    const valuesPtr = writeDoubleArray(values);
    const optsPtr = Module._malloc(32); // cx, cy, r, n_axes(size_t=4, padded)
    { const view = dv(); view.setFloat64(optsPtr, cx, true); view.setFloat64(optsPtr + 8, cy, true); view.setFloat64(optsPtr + 16, r, true); view.setUint32(optsPtr + 24, n, true); }
    const outPtr = Module._malloc(12); // sizeof(EKRadarLayout)

    Module._ekplots_radar_layout_boxed(valuesPtr, n, optsPtr, outPtr);
    const axisTicksPtr = readU32(outPtr);
    const seriesPointsPtr = readU32(outPtr + 4);
    const realN = readI32(outPtr + 8);
    const axisTicks = readPoints(axisTicksPtr, realN);
    const seriesPoints = readPoints(seriesPointsPtr, realN);

    Module._ekplots_radar_free(outPtr);
    freeAll(valuesPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'radar', axisTicks, seriesPoints, axisLabels: opts.axisLabels || null };
  }

  function stackedArea(x, series, opts) {
    opts = opts || {};
    const width = opts.width ?? 400, height = opts.height ?? 300;
    const seriesNames = Object.keys(series);
    const nSeries = seriesNames.length;
    const nPoints = x.length;

    const xPtr = writeDoubleArray(x);
    const { outerPtr, innerPtrs } = writePointerArray(seriesNames.map((name) => series[name]));
    const optsPtr = Module._malloc(16);
    { const view = dv(); view.setFloat64(optsPtr, width, true); view.setFloat64(optsPtr + 8, height, true); }
    const outPtr = Module._malloc(48); // sizeof(EKStackedAreaLayout)

    Module._ekplots_stacked_area_layout_boxed(xPtr, outerPtr, nSeries, nPoints, optsPtr, outPtr);
    const bandsPtr = readU32(outPtr);
    const realNSeries = readU32(outPtr + 4);
    const realNPoints = readU32(outPtr + 8);
    const bounds = readBounds(outPtr + 16);
    const flatBands = readPoints(bandsPtr, realNSeries * realNPoints * 2);
    const bands = [];
    for (let s = 0; s < realNSeries; s++) {
      const perPoint = [];
      for (let p = 0; p < realNPoints; p++) {
        const base = (s * realNPoints + p) * 2;
        perPoint.push([flatBands[base], flatBands[base + 1]]); // [bottom, top]
      }
      bands.push(perPoint);
    }

    Module._ekplots_stacked_area_free(outPtr);
    freeAll(xPtr, ...innerPtrs, outerPtr, optsPtr, outPtr);
    return { __ekplotsKind: 'stackedArea', bands, seriesNames, bounds, width, height };
  }

  return {
    ready,
    bar, hbar, stackedBar,
    line, area, stackedArea,
    pie, donut, funnel,
    histogram, boxplot,
    scatter, bubble,
    heatmap, radar,
  };
});
