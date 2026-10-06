// Real pixel rendering, using node-canvas as a stand-in Canvas2D
// implementation (the browser-native one this is built for isn't
// available in this environment) — proves ekplots.draw() produces real
// shapes, not just that the geometry functions return numbers.
import { createCanvas } from 'canvas';
import fs from 'node:fs';
import ekplots from './ekplots-draw.js';

await ekplots.ready;
fs.mkdirSync('out', { recursive: true });

function render(name, layout, size = [400, 300]) {
  const canvas = createCanvas(size[0], size[1]);
  const ctx = canvas.getContext('2d');
  ekplots.draw(ctx, layout);
  fs.writeFileSync(`out/${name}.png`, canvas.toBuffer('image/png'));
  console.log(`wrote out/${name}.png`);
}

render('01_bar', ekplots.bar([42, 71, 18, 55, 90]));
render('02_hbar', ekplots.hbar([820, 540, 310, 180, 95]));
render('03_stacked_bar', ekplots.stackedBar({ Mobile: [40, 55, 30], Desktop: [60, 45, 70] }));
render('04_line', ekplots.line(
  Array.from({ length: 14 }, (_, i) => i),
  [120, 135, 128, 160, 155, 180, 175, 190, 210, 205, 230, 225, 250, 265],
));
render('04b_line_smooth', ekplots.line(
  [0, 1, 2, 3, 4, 5, 6, 7],
  [10, 40, 15, 45, 20, 50, 12, 48],
  { smooth: true },
));
render('05_area', ekplots.area([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [50, 60, 55, 80, 90, 85, 100, 120, 115, 140]));
render('06_stacked_area', ekplots.stackedArea(
  [0, 1, 2, 3, 4, 5, 6, 7],
  { 'Group 1': [10, 12, 15, 14, 18, 20, 19, 22], 'Group 2': [8, 9, 7, 11, 10, 12, 13, 15] },
), [400, 300]);
render('07_pie', ekplots.pie([55, 30, 15]), [300, 300]);
render('08_donut', ekplots.donut([55, 30, 15], { innerR: 0.6 }), [300, 300]);
render('09_funnel', ekplots.funnel([1000, 640, 410, 180, 95]));
render('10_histogram', ekplots.histogram(
  Array.from({ length: 300 }, () => 2 + Math.random() * 1).concat(
    Array.from({ length: 150 }, () => 8 + Math.random() * 2.4)
  ),
));
render('11_boxplot', ekplots.boxplot({
  'Group 1': [28, 31, 29, 30, 27, 32, 85, 90],
  'Group 2': [55, 62, 58, 60, 65, 57],
  'Group 3': [30, 45, 50, 35, 40, 38, 5],
}));
render('12_scatter', ekplots.scatter(
  Array.from({ length: 80 }, () => 20 + Math.random() * 60),
  Array.from({ length: 80 }, () => 20 + Math.random() * 60),
));
render('13_bubble', ekplots.bubble([1, 2, 3, 4, 5, 6], [10, 25, 15, 40, 30, 20], [100, 800, 300, 1500, 600, 200]));
render('14_heatmap', ekplots.heatmap([
  [0.0, 0.42, 0.18, 0.05],
  [0.31, 0.0, 0.22, 0.08],
  [0.12, 0.35, 0.0, 0.15],
  [0.04, 0.09, 0.28, 0.0],
]), [400, 400]);
render('15_radar', ekplots.radar([0.8, 0.3, 0.6, 0.9, 0.4]), [300, 300]);

console.log('\nAll 15 rendered to real PNGs in out/');
