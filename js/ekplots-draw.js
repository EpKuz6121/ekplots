/* ekplots — Canvas2D renderer, the JS-side counterpart to _draw.py.
 *
 * No geometry is computed here — every coordinate already came from the
 * real WASM-compiled C core (ekplots.js). This module only decides
 * color/stroke and maps the logical [0,width]x[0,height] canvas the C
 * core worked in onto the actual <canvas> pixel space the caller gives
 * it (a simple translate+scale, since both are already y-up... except
 * Canvas2D is y-DOWN, so this is also where that one flip happens — see
 * the coordinate-convention note in ekplots.c).
 *
 * Usage:
 *   const ctx = canvas.getContext('2d');
 *   ekplots.draw(ctx, layout, { chartId: 'my-chart' });
 *
 * The tracking hook (chartId) is wired here, not in ekplots.js, since
 * viewport/interaction detection is a rendering-surface concern — see
 * _wireTracking() at the bottom. It's consent-gated through the host
 * page's own window.__analytics, exactly like every SurveySync tracker
 * collector; ekplots never calls fetch() itself.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('./ekplots.js'));
  } else {
    factory(root.ekplots);
  }
})(typeof self !== 'undefined' ? self : this, function (ekplotsCore) {
  'use strict';

  const DEFAULT_COLOR = '#2f5fd1';
  const DEFAULT_CYCLE = ['#2f5fd1', '#b8541f', '#2a9d6b', '#8e5fd1', '#d13f6f', '#c99a2e'];

  /** Flips the C core's y-up logical canvas into Canvas2D's y-down pixel
   * space. Every draw function below calls this once per shape, not
   * once globally via ctx.transform(), so text/line-width stay
   * unscaled and legible regardless of canvasHeight vs. layout.height. */
  function flipY(y, canvasHeight, logicalHeight) {
    return canvasHeight - (y / logicalHeight) * canvasHeight;
  }
  function scaleX(x, canvasWidth, logicalWidth) {
    return (x / logicalWidth) * canvasWidth;
  }

  function draw(ctx, layout, style) {
    style = style || {};
    const canvas = ctx.canvas;
    const kind = layout.__ekplotsKind;
    const fn = DRAWERS[kind];
    if (!fn) throw new TypeError('ekplots.draw() does not know how to render this layout (missing __ekplotsKind)');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    fn(ctx, layout, style, canvas.width, canvas.height);
    if (style.chartId) _wireTracking(ctx.canvas, layout, style.chartId);
    return ctx;
  }

  function _drawBar(ctx, layout, style, cw, ch) {
    const color = style.color || DEFAULT_COLOR;
    ctx.fillStyle = color;
    for (const r of layout.bars) {
      const x = scaleX(r.x, cw, layout.width);
      const w = scaleX(r.w, cw, layout.width);
      const yTop = flipY(r.y + r.h, ch, layout.height);
      const h = scaleX(r.h, ch, layout.height); // bars are axis-aligned; height scales the same as any logical length
      ctx.fillRect(x, yTop, w, h);
    }
  }

  function _drawStackedBar(ctx, layout, style, cw, ch) {
    const colors = style.colors || DEFAULT_CYCLE;
    layout.segments.forEach((category) => {
      category.forEach((r, s) => {
        ctx.fillStyle = colors[s % colors.length];
        const x = scaleX(r.x, cw, layout.width);
        const w = scaleX(r.w, cw, layout.width);
        const yTop = flipY(r.y + r.h, ch, layout.height);
        const h = scaleX(r.h, ch, layout.height);
        ctx.fillRect(x, yTop, w, h);
      });
    });
  }

  function _pathPoints(ctx, points, cw, ch, logicalW, logicalH) {
    ctx.beginPath();
    points.forEach((p, i) => {
      const x = scaleX(p.x, cw, logicalW);
      const y = flipY(p.y, ch, logicalH);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
  }

  function _drawLine(ctx, layout, style, cw, ch) {
    ctx.strokeStyle = style.color || DEFAULT_COLOR;
    ctx.lineWidth = style.linewidth || 2;
    _pathPoints(ctx, layout.points, cw, ch, layout.width, layout.height);
    ctx.stroke();
  }

  function _drawArea(ctx, layout, style, cw, ch) {
    const color = style.color || DEFAULT_COLOR;
    const baselineY = flipY(layout.baselineY, ch, layout.height);
    ctx.beginPath();
    layout.points.forEach((p, i) => {
      const x = scaleX(p.x, cw, layout.width);
      const y = flipY(p.y, ch, layout.height);
      if (i === 0) ctx.moveTo(x, baselineY), ctx.lineTo(x, y);
      else ctx.lineTo(x, y);
    });
    const lastX = scaleX(layout.points[layout.points.length - 1].x, cw, layout.width);
    ctx.lineTo(lastX, baselineY);
    ctx.closePath();
    ctx.globalAlpha = 0.35;
    ctx.fillStyle = color;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    _pathPoints(ctx, layout.points, cw, ch, layout.width, layout.height);
    ctx.stroke();
  }

  function _drawStackedArea(ctx, layout, style, cw, ch) {
    const colors = style.colors || DEFAULT_CYCLE;
    layout.bands.forEach((series, s) => {
      ctx.fillStyle = colors[s % colors.length];
      ctx.beginPath();
      series.forEach(([bottom], i) => {
        const x = scaleX(bottom.x, cw, layout.width);
        const y = flipY(bottom.y, ch, layout.height);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      for (let i = series.length - 1; i >= 0; i--) {
        const top = series[i][1];
        ctx.lineTo(scaleX(top.x, cw, layout.width), flipY(top.y, ch, layout.height));
      }
      ctx.closePath();
      ctx.fill();
    });
  }

  function _drawPieOrDonut(ctx, layout, style, cw, ch) {
    const colors = style.colors || DEFAULT_CYCLE;
    // pie/donut coordinates are already in a fixed cx/cy/r space (not a
    // [0,width]x[0,height] canvas to rescale) — drawn directly, flipping
    // only the angle direction since Canvas2D's arc() is also
    // clockwise-from-positive-x like the C core's convention, so no
    // angle flip is actually needed, just the same y-down y-coordinate
    // Canvas2D always uses for cx/cy.
    layout.slices.forEach((s, i) => {
      ctx.beginPath();
      ctx.fillStyle = colors[i % colors.length];
      ctx.moveTo(s.cx, s.cy);
      ctx.arc(s.cx, s.cy, s.r, s.startAngle, s.endAngle);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = 'white';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });
    if (layout.innerR) {
      ctx.fillStyle = style.background || '#ffffff';
      const { cx, cy } = layout.slices[0];
      ctx.beginPath();
      ctx.arc(cx, cy, layout.innerR, 0, 2 * Math.PI);
      ctx.fill();
    }
  }

  function _drawFunnel(ctx, layout, style, cw, ch) {
    const color = style.color || DEFAULT_COLOR;
    const maxW = Math.max(...layout.stages.flatMap((s) => s.trapezoid.map((p) => p.x)));
    const maxH = Math.max(...layout.stages.flatMap((s) => s.trapezoid.map((p) => p.y)));
    layout.stages.forEach((stage, i) => {
      ctx.globalAlpha = 1 - i * 0.12;
      ctx.fillStyle = color;
      ctx.beginPath();
      stage.trapezoid.forEach((p, j) => {
        const x = scaleX(p.x, cw, maxW);
        const y = (p.y / maxH) * ch; // funnel reads top-down, no flip
        if (j === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.closePath();
      ctx.fill();
    });
    ctx.globalAlpha = 1;
  }

  function _drawHistogram(ctx, layout, style, cw, ch) {
    ctx.fillStyle = style.color || DEFAULT_COLOR;
    const maxW = Math.max(...layout.bins.map((r) => r.x + r.w));
    const maxH = Math.max(...layout.bins.map((r) => r.h), 1);
    layout.bins.forEach((r) => {
      const x = scaleX(r.x, cw, maxW);
      const w = scaleX(r.w, cw, maxW);
      const h = (r.h / maxH) * ch;
      ctx.fillRect(x, ch - h, w, h);
      ctx.strokeStyle = 'white';
      ctx.strokeRect(x, ch - h, w, h);
    });
  }

  function _drawBoxplot(ctx, layout, style, cw, ch) {
    const color = style.color || DEFAULT_COLOR;
    const names = Object.keys(layout.groups);
    const maxX = Math.max(...names.map((n) => layout.groups[n].box.x + layout.groups[n].box.w)) * 2;
    names.forEach((name) => {
      const g = layout.groups[name];
      const x = scaleX(g.box.x, cw, maxX);
      const w = scaleX(g.box.w, cw, maxX);
      const yTop = flipY(g.box.y + g.box.h, ch, layout.height);
      const h = (g.box.h / layout.height) * ch;
      ctx.globalAlpha = 0.5;
      ctx.fillStyle = color;
      ctx.fillRect(x, yTop, w, h);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x, yTop, w, h);
      const wx = scaleX(g.whiskerLow.x, cw, maxX);
      ctx.beginPath();
      ctx.moveTo(wx, flipY(g.whiskerLow.y, ch, layout.height));
      ctx.lineTo(wx, yTop + h);
      ctx.moveTo(wx, yTop);
      ctx.lineTo(wx, flipY(g.whiskerHigh.y, ch, layout.height));
      ctx.lineWidth = 1;
      ctx.stroke();

      // Outliers are returned in RAW data units (not pre-scaled, unlike
      // box/whisker) so a caller can still label the real value — map
      // them into the same [0,height] logical space using bounds, the
      // identical scale the C core used internally for the box itself.
      const yRange = layout.bounds.yMax - layout.bounds.yMin || 1;
      ctx.fillStyle = color;
      g.outliers.forEach((value) => {
        const logicalY = ((value - layout.bounds.yMin) / yRange) * layout.height;
        const py = flipY(logicalY, ch, layout.height);
        ctx.beginPath();
        ctx.arc(wx, py, 2.5, 0, 2 * Math.PI);
        ctx.fill();
      });
    });
  }

  function _drawScatter(ctx, layout, style, cw, ch) {
    ctx.fillStyle = style.color || DEFAULT_COLOR;
    ctx.globalAlpha = 0.8;
    const r = style.pointRadius || 3;
    layout.points.forEach((p) => {
      const x = scaleX(p.x, cw, layout.width);
      const y = flipY(p.y, ch, layout.height);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
  }

  function _drawBubble(ctx, layout, style, cw, ch) {
    const color = style.color || DEFAULT_COLOR;
    ctx.fillStyle = color;
    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.55;
    layout.bubbles.forEach((b) => {
      const x = scaleX(b.x, cw, layout.width);
      const y = flipY(b.y, ch, layout.height);
      const r = scaleX(b.r, cw, layout.width);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fill();
      ctx.stroke();
    });
    ctx.globalAlpha = 1;
  }

  function _drawHeatmap(ctx, layout, style, cw, ch) {
    const nRows = layout.cells.length, nCols = layout.cells[0].length;
    const maxW = Math.max(...layout.cells.flat().map((r) => r.x + r.w));
    const maxH = Math.max(...layout.cells.flat().map((r) => r.y + r.h));
    const range = layout.valueMax - layout.valueMin || 1;
    for (let r = 0; r < nRows; r++) {
      for (let c = 0; c < nCols; c++) {
        const cell = layout.cells[r][c];
        const t = (layout.values[r][c] - layout.valueMin) / range;
        ctx.fillStyle = _blueShade(t);
        const x = scaleX(cell.x, cw, maxW);
        const w = scaleX(cell.w, cw, maxW);
        const h = (cell.h / maxH) * ch;
        // The C core places row 0 at the top in LOGICAL (y-up) space —
        // i.e. row 0's cells sit at the HIGHEST y values. Canvas2D is
        // y-down, so without this flip row 0 renders at the visual
        // BOTTOM instead — every other shape in this file goes through
        // flipY() for the same reason; this one was missed initially
        // and caught by actually looking at a rendered PNG, not assumed.
        const yTop = ch - ((cell.y + cell.h) / maxH) * ch;
        ctx.fillRect(x, yTop, w, h);
        ctx.strokeStyle = 'white';
        ctx.strokeRect(x, yTop, w, h);
      }
    }
  }
  function _blueShade(t) {
    const light = [239, 243, 255], dark = [8, 48, 107];
    const c = light.map((l, i) => Math.round(l + (dark[i] - l) * t));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }

  function _drawRadar(ctx, layout, style, cw, ch) {
    const color = style.color || DEFAULT_COLOR;
    ctx.strokeStyle = '#cccccc';
    ctx.lineWidth = 1;
    ctx.beginPath();
    layout.axisTicks.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
    ctx.closePath();
    ctx.stroke();

    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.3;
    ctx.beginPath();
    layout.seriesPoints.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  const DRAWERS = {
    bar: _drawBar, stackedBar: _drawStackedBar,
    line: _drawLine, area: _drawArea, stackedArea: _drawStackedArea,
    pie: _drawPieOrDonut, donut: _drawPieOrDonut, funnel: _drawFunnel,
    histogram: _drawHistogram, boxplot: _drawBoxplot,
    scatter: _drawScatter, bubble: _drawBubble,
    heatmap: _drawHeatmap, radar: _drawRadar,
  };

  /** The tracking hook from docs/SPEC.md — consent-gated through the
   * host page's own window.__analytics, same as every real SurveySync
   * tracker collector. No-ops completely if that global isn't present
   * (ekplots used standalone, no tracker installed) or consent isn't
   * granted. ekplots never calls fetch() itself — only the tracker's
   * own already-consent-gated buffer. NOTE: this function only runs in
   * a real browser DOM (needs IntersectionObserver); it's skipped
   * automatically outside one (e.g. Node/node-canvas, used for this
   * library's own test/render verification). */
  function _wireTracking(canvasEl, layout, chartId) {
    if (typeof window === 'undefined' || !window.__analytics || typeof IntersectionObserver === 'undefined') return;
    if (!window.__analytics.getConsent || !window.__analytics.getConsent()) return;
    if (canvasEl.__ekplotsTracked) return; // one observer per canvas element
    canvasEl.__ekplotsTracked = true;

    // No leading underscore — the tracker keeps this name stable across
    // its own build's property-mangling specifically so an external
    // caller (this file) can rely on it. chartId/interactionType are
    // camelCase; the tracker itself translates to the snake_case meta
    // payload it stores, and fills in page_path/occurred_at — this call
    // only ever passes what ekplots itself actually knows.
    const emit = window.__analytics.emitChartEvent;
    if (typeof emit !== 'function') return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            emit({ type: 'chart_view', chartId });
            observer.disconnect();
          }
        });
      },
      { threshold: 0.5 }
    );
    observer.observe(canvasEl);

    canvasEl.addEventListener('click', (e) => {
      const rect = canvasEl.getBoundingClientRect();
      emit({
        type: 'chart_interact', chartId, interactionType: 'click',
        x: e.clientX - rect.left, y: e.clientY - rect.top,
      });
    });
  }

  ekplotsCore.draw = draw;
  return ekplotsCore;
});
