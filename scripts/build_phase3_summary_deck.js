/*
 * PHASE 3 SUMMARY DECK -- do the stands my method draws match the Odisha field plots?
 * 17 slides, first person, plain language, for the supervisor meeting.
 *
 * Every number on a slide or in the notes comes from odisha_script/phase3_figures/deck_facts.md
 * or is printed on one of the figures in odisha_script/phase3_figures/ (made by
 * odisha_script/odisha_phase3_4{a,b,c,d}_*.py).
 *
 * Deps (not part of the Python package): npm install pptxgenjs
 * Run from the repo root: node scripts/build_phase3_summary_deck.js
 * Writes Phase3_Odisha_stand_check_summary.pptx in the repo root.
 */
const fs = require('fs');
const path = require('path');
const pptxgen = require('pptxgenjs');

const REPO = path.resolve(__dirname, '..');
const FD = path.join(REPO, 'odisha_script', 'phase3_figures');
const OUT = path.join(REPO, 'Phase3_Odisha_stand_check_summary.pptx');
const FIG = {};
['method_steps', 'study_area', 'stand_view_10_vs_3', 'patch_sizes', 'stand_sizes', 'species_groups',
 'structure_boxplots', 'elbow_field', 'elbow_stands', 'chance_test', 'summary_scores']
  .forEach(k => { FIG[k] = path.join(FD, k + '.png'); });

/* ---------- house style (scripts/build_master_deck.js) ---------- */
const INK = '1A1A1A', GREEN = '2C5F2D', MOSS = '4E7350', MUTE = '5F6F66', TINT = 'EEF3E9', RULE = 'CBD8C4',
      AMBER = 'A9631F', SLATE = '6B7F8E', CHANCE = 'C9CFCB', WHITE = 'FFFFFF';
const AMBER_TINT = 'F7ECE0', PALE_ON_DARK = 'DDEBD8', DARK_CARD = '3A6E3B';
const TYPE_COLOUR = ['CDB57E', 'A9C38B', '6E9A5A', '3F7A4A', '1F4D2B']; // scrub -> tall, many trees
const HF = 'Cambria', BF = 'Calibri';
const W = 13.33, H = 7.5, MG = 0.6, CW = W - 2 * MG;
const BODY_TOP = 1.6;

/* PNG pixel size from the IHDR chunk, so every figure is placed at its native aspect ratio. */
function pngSize(p) {
  const b = fs.readFileSync(p);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
function aspect(k) { const s = pngSize(FIG[k]); return s.w / s.h; }

const p = new pptxgen();
p.layout = 'LAYOUT_WIDE';
p.author = 'Jaskaran Singh';
p.title = 'Do the forest stands my method draws match what we measured on the ground?';
p.defineSlideMaster({ title: 'W', background: { color: WHITE } });

let SN = 0;
function S() { SN++; return p.addSlide({ masterName: 'W' }); }

function foot(s, dark) {
  s.addText('Phase 3: checking my stands against the Odisha field plots', {
    x: MG, y: H - 0.42, w: 8, h: 0.28, fontFace: BF, fontSize: 10, color: dark ? 'A9C4A6' : MUTE,
    margin: 0, isTextBox: true });
  s.addText(String(SN), { x: W - MG - 0.6, y: H - 0.42, w: 0.6, h: 0.28, fontFace: BF, fontSize: 10,
    color: dark ? 'A9C4A6' : MUTE, align: 'right', margin: 0, isTextBox: true });
}
function title(s, t, o) {
  o = o || {};
  s.addText(t, { x: MG, y: 0.38, w: CW, h: 1.08, fontFace: HF, fontSize: o.fs || 30, bold: true,
    color: o.color || INK, valign: 'middle', margin: 0, isTextBox: true, fit: 'none' });
}
/* Plain paragraph(s). `runs` is a string or an array of {text, options}. */
function text(s, runs, o) {
  s.addText(runs, Object.assign({ fontFace: BF, fontSize: 15, color: INK, valign: 'top', margin: 0,
    isTextBox: true, paraSpaceAfter: 6 }, o));
}
function bullets(s, items, o) {
  const fs_ = o.fontSize || 15;
  s.addText(items.map((t, i) => ({ text: t, options: { bullet: { indent: 16 }, breakLine: i < items.length - 1,
    paraSpaceAfter: o.gap == null ? 8 : o.gap } })),
  Object.assign({ fontFace: BF, fontSize: fs_, color: INK, valign: 'top', margin: 0, isTextBox: true }, o));
}
/* Figure at native aspect: give a width OR a height, get the placed box back. */
function fig(s, k, x, y, o) {
  const a = aspect(k);
  let w = o.w, h = o.h;
  if (w && !h) h = w / a; else if (h && !w) w = h * a;
  s.addImage({ path: FIG[k], x, y, w, h, altText: o.alt || k });
  return { x, y, w, h };
}
function caption(s, t, x, y, w) {
  s.addText(t, { x, y, w, h: 0.3, fontFace: BF, fontSize: 11, italic: true, color: MUTE, margin: 0,
    valign: 'top', isTextBox: true });
}
/* Big-number callout: number over a plain label. */
function stat(s, x, y, w, num, label, o) {
  o = o || {};
  s.addText(num, { x, y, w, h: o.nh || 0.62, fontFace: HF, fontSize: o.nfs || 36, bold: true,
    color: o.color || GREEN, margin: 0, valign: 'bottom', isTextBox: true });
  s.addText(label, { x, y: y + (o.nh || 0.62) + 0.04, w, h: o.lh || 0.6, fontFace: BF, fontSize: o.lfs || 14,
    color: o.lcolor || INK, margin: 0, valign: 'top', isTextBox: true });
}
function card(s, x, y, w, h, fill, line) {
  s.addShape(p.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.08, fill: { color: fill || TINT },
    line: { color: line || RULE, width: 0.75 } });
}
function numCircle(s, x, y, n, fill, col) {
  s.addShape(p.ShapeType.ellipse, { x, y, w: 0.5, h: 0.5, fill: { color: fill || GREEN }, line: { color: fill || GREEN } });
  s.addText(String(n), { x, y, w: 0.5, h: 0.5, fontFace: HF, fontSize: 18, bold: true, color: col || WHITE,
    align: 'center', valign: 'middle', margin: 0, isTextBox: true });
}
function dot(s, cx, cy, d, colour) {
  s.addShape(p.ShapeType.ellipse, { x: cx - d / 2, y: cy - d / 2, w: d, h: d, fill: { color: colour },
    line: { color: WHITE, width: 1.25 } });
}
function arrow(s, x, y, w, colour) {
  s.addShape(p.ShapeType.line, { x, y, w, h: 0, line: { color: colour || MOSS, width: 2, endArrowType: 'triangle' } });
}

let s;

/* ============ 1 TITLE ============ */
s = S(); s.background = { color: GREEN };
s.addText('PHASE 3 SUMMARY  ·  ODISHA', { x: MG, y: 1.3, w: CW, h: 0.4, fontFace: BF, fontSize: 14, bold: true,
  color: 'BFE0B8', charSpacing: 3, margin: 0, isTextBox: true });
s.addText('Do the forest stands my method draws match what we measured on the ground?', {
  x: MG, y: 1.85, w: 11.2, h: 1.9, fontFace: HF, fontSize: 40, bold: true, color: WHITE, valign: 'top', margin: 0,
  isTextBox: true });
s.addText('A check of my stand maps against 274 field plots in 20 village forests across four districts of Odisha: Angul, Dhenkanal, Kendujhar and Koraput.', {
  x: MG, y: 3.95, w: 10.6, h: 0.9, fontFace: BF, fontSize: 18, color: PALE_ON_DARK, valign: 'top', margin: 0, isTextBox: true });
// small motif: five dots in the five forest-type colours
TYPE_COLOUR.forEach((c, i) => dot(s, MG + 0.18 + i * 0.42, 5.35, 0.3, c));
s.addText('Jaskaran Singh   ·   September 2026', { x: MG, y: 6.3, w: CW, h: 0.4, fontFace: BF, fontSize: 14,
  color: 'A9C4A6', margin: 0, isTextBox: true });
s.addNotes('In this deck I go through the check you asked me to run in Phase 3. I ran my own satellite-feature method (not the AlphaEarth one) over the Odisha field sites, cut the forest into stands of at most 3 hectares, gave each stand a type automatically, and then used the field plots as the truth to score both the stand boundaries and the stand types. The field data are 274 plots in 20 village forests across Angul, Dhenkanal, Kendujhar and Koraput, surveyed between 25 April 2022 and 5 April 2023. The short answer is that, with this data, neither the 10 hectare nor the 3 hectare stands do better than a randomly shifted map, and the two sizes cannot be told apart. The rest of the deck shows how I got there and what I think it means.');

/* ============ 2 THE QUESTION ============ */
s = S();
title(s, 'You asked me to check two things: are my stands drawn well, and are they labelled well?');
const qy = BODY_TOP + 0.1, qh = 3.55, qw = 5.9;
[[MG, 1, 'Drawing', 'Do plots that are alike on the ground end up in the same stand?'],
 [MG + qw + 0.33, 2, 'Labelling', 'Do alike plots get the same stand type, even when they are far apart?']]
  .forEach(([x, n, head, q]) => {
    card(s, x, qy, qw, qh);
    numCircle(s, x + 0.3, qy + 0.3, n);
    s.addText(head, { x: x + 0.95, y: qy + 0.3, w: qw - 1.2, h: 0.5, fontFace: HF, fontSize: 22, bold: true,
      color: GREEN, valign: 'middle', margin: 0, isTextBox: true });
    text(s, q, { x: x + 0.3, y: qy + 0.95, w: qw - 0.6, h: 0.8, fontSize: 17 });
  });
// mini diagram, drawing: one stand outline holding two same-colour plots
{
  const x = MG + 0.9, y = qy + 2.0;
  s.addShape(p.ShapeType.roundRect, { x, y, w: 2.2, h: 1.25, rectRadius: 0.12, fill: { color: WHITE },
    line: { color: MOSS, width: 1.75, dashType: 'solid' } });
  dot(s, x + 0.7, y + 0.62, 0.34, TYPE_COLOUR[3]); dot(s, x + 1.5, y + 0.62, 0.34, TYPE_COLOUR[3]);
  text(s, 'one stand, two plots of the same forest type', { x: x + 2.4, y: y + 0.3, w: 2.3, h: 0.7, fontSize: 14, color: MUTE });
}
// mini diagram, labelling: two separate stands with the same type, far apart
{
  const x0 = MG + qw + 0.33 + 0.5, y = qy + 2.0;
  [0, 2.35].forEach(dx => {
    s.addShape(p.ShapeType.roundRect, { x: x0 + dx, y, w: 1.55, h: 1.25, rectRadius: 0.12, fill: { color: WHITE },
      line: { color: MOSS, width: 1.75 } });
    s.addText('Type 3', { x: x0 + dx + 0.1, y: y + 0.08, w: 1.35, h: 0.3, fontFace: BF, fontSize: 13, bold: true,
      color: MOSS, margin: 0, isTextBox: true });
    dot(s, x0 + dx + 0.78, y + 0.78, 0.34, TYPE_COLOUR[3]);
  });
  s.addShape(p.ShapeType.line, { x: x0 + 1.65, y: y + 0.78, w: 0.6, h: 0, line: { color: MUTE, width: 1.25,
    dashType: 'dash', beginArrowType: 'triangle', endArrowType: 'triangle' } });
  text(s, 'far apart, same type', { x: x0 + 4.05, y: y + 0.3, w: 1.2, h: 0.7, fontSize: 14, color: MUTE });
}
text(s, [
  { text: 'What I used as the truth: ', options: { bold: true, color: GREEN } },
  { text: 'the field plots. I grouped them into forest types from what the survey measured on the ground. The method that draws and types the stands only ever sees the satellite data, so the plots are an independent check.' }],
  { x: MG, y: 5.55, w: CW, h: 0.9, fontSize: 16 });
foot(s);
s.addNotes('You asked me two separate questions, and I scored them separately. The first is about drawing: if two plots are alike on the ground, does my map put them in the same stand? The second is about labelling: if two plots are alike, does my map give them the same stand type, even when they sit in different stands far apart? For both questions the truth is the field plots, grouped into forest types from ground measurements; the stand method never sees those plots. If stands are to be useful as units of forest, both answers should be clearly better than chance.');

/* ============ 3 HOW MY METHOD WORKS ============ */
s = S();
title(s, 'My method cuts the satellite image into small patches, joins them into stands and gives each stand a type');
{
  const fw = 11.6, box = fig(s, 'method_steps', MG, BODY_TOP + 0.05, { w: fw,
    alt: 'Four views of one 650 metre square of forest: satellite image, small patches, stands, stand types' });
  caption(s, 'The same 650 by 650 metre square of Jogi Bandha village forest, Angul district, at each step (stands up to 3 hectares).',
    MG, box.y + box.h + 0.06, CW);
  const steps = [
    'I start from my own satellite features: 22 measurements for every 10 metre pixel of forest.',
    'I cut the image into small patches of similar pixels, with patch centres about 60 metres apart.',
    'I join neighbouring patches that look alike into stands, up to a size cap. A patch is never split.',
    'An automatic grouping method called k-means sorts the stands into 6 types by their satellite features alone.'];
  const ty = box.y + box.h + 0.5;
  steps.forEach((t, i) => {
    const x = MG + fw * (0.006 + 0.235 * i);
    text(s, t, { x, y: ty, w: fw * 0.222, h: 1.25, fontSize: 14 });
  });
}
foot(s);
s.addNotes('This is the whole method on one small square of forest, 650 by 650 metres in Jogi Bandha, Angul. I start from my own satellite features, 22 measurements for every 10 metre pixel. I cut the image into small patches of similar pixels; this square holds 115 of them. I then join neighbouring patches that look alike into stands, here 29 stands up to 3 hectares each, and a patch is never split, which matters later. Finally the automatic grouping puts stands with similar satellite features into the same group; it is run separately in each district, gives 6 types, and never sees the field data. A few stands are left without a type (9 of the 203 Angul 3 hectare stands, 2 of them in this square).');

/* ============ 4 FIELD DATA ============ */
s = S();
title(s, 'I checked the stands against 274 field plots in 20 village forests across four districts');
{
  const box = fig(s, 'study_area', MG, BODY_TOP, { w: 8.9,
    alt: 'Map of Odisha with the field plots by district, and satellite close-ups of each district' });
  caption(s, 'Field plots by district. White outlines: the village forests I mapped. Hollow circles: the 7 plots outside them.',
    MG, box.y + box.h + 0.08, box.w);
  const x = MG + 8.9 + 0.4, w = CW - 8.9 - 0.4;
  const items = [
    ['274', 'field plots, surveyed April 2022 to April 2023'],
    ['20', 'village forests, about 4,300 hectares in all'],
    ['267', 'plots fall inside the village forests I mapped: these are the ones I score'],
    ['2,700', 'trees, roughly, among 5,910 plant records (the rest are saplings, shrubs, climbers and stumps)']];
  items.forEach(([n, l], i) => stat(s, x, BODY_TOP + i * 1.3, w, n, l, { nh: 0.55, lh: 0.7, nfs: 34 }));
}
foot(s);
s.addNotes('The field data are 274 plots in four districts: Koraput 146, Dhenkanal 76, Angul 40 and Kendujhar 12, surveyed between April 2022 and April 2023. They sit in 20 village forests (Angul 4, Dhenkanal 8, Kendujhar 1, Koraput 7), about 4,300 hectares in total; most village forests hold about 10 plots. 267 plots fall inside the village forests I mapped (145, 75, 39 and 8), and those are the plots I score; the 7 outside are shown as hollow circles. The raw sheet has 5,910 plant records, of which about 2,700 are trees after the location filter (2,729). One open point: we still do not know the plot size, which the field team has not yet confirmed.');

/* ============ 5 WHAT THE STANDS LOOK LIKE ============ */
s = S();
title(s, 'Lowering the stand size cap from 10 to 3 hectares cuts the same forest into many more stands');
{
  const box = fig(s, 'stand_view_10_vs_3', MG, BODY_TOP, { h: 4.15,
    alt: 'Jogi Bandha village forest with stand boundaries at 10 hectares and at 3 hectares, and field plots coloured by forest type' });
  caption(s, 'Jogi Bandha village forest, Angul district. Stand boundaries in white; dots are field plots coloured by the forest type measured on the ground.',
    MG, box.y + box.h + 0.08, CW);
  text(s, [
    { text: 'In this village forest the same 10 plots fall in 2 stands at the 10 hectare cap and in 6 stands at the 3 hectare cap. ', options: {} },
    { text: 'Across all four districts the number of stands roughly doubles, from about 1,040 to about 1,950.', options: { bold: true } }],
    { x: MG, y: box.y + box.h + 0.48, w: CW, h: 0.7, fontSize: 15 });
}
foot(s);
s.addNotes('Here is one village forest, Jogi Bandha in Angul, drawn twice on satellite imagery. On the left the stands can be up to 10 hectares, and the 10 field plots fall in only 2 stands; on the right the cap is 3 hectares, and the same plots spread over 6 stands. The plots here cover 3 of the 5 forest types: 1 scrub, 5 low forest with few trees and 4 tall forest with few big trees. Over all four districts the 3 hectare cap roughly doubles the number of stands, from 1,039 to 1,954. The stand outlines follow the forest edges, and I checked that every one of the 267 plots lands in the stand the join recorded for it, at both caps.');

/* ============ 6 FINER CUTTING ============ */
s = S();
title(s, 'To reach 3 hectare stands I first had to cut the forest into smaller patches');
{
  const fw = 8.3;
  const box = fig(s, 'patch_sizes', MG, BODY_TOP + 0.1, { w: fw,
    alt: 'Histograms of small patch sizes at the original and the finer spacing' });
  caption(s, 'Size of every small patch, all four districts together. Top: original spacing. Bottom: finer spacing.',
    MG, box.y + box.h + 0.08, fw);
  const x = MG + fw + 0.45, w = CW - fw - 0.45;
  text(s, 'A stand is built from whole patches, so it can never be smaller than its biggest patch.',
    { x, y: BODY_TOP + 0.1, w, h: 0.9, fontSize: 16, bold: true, color: GREEN });
  stat(s, x, BODY_TOP + 1.15, w, '6.74 hectares', 'largest single patch with centres about 100 metres apart: 56 patches were already over 3 hectares',
    { nfs: 30, color: SLATE, lh: 0.95 });
  stat(s, x, BODY_TOP + 2.95, w, '2.02 hectares', 'largest patch after I moved the centres to about 60 metres apart: none is over 3 hectares',
    { nfs: 30, color: GREEN, lh: 0.95 });
  text(s, 'So the two stand maps differ in two settings, the size cap and the patch spacing, not just one.',
    { x, y: BODY_TOP + 4.7, w, h: 0.75, fontSize: 14, color: MUTE, italic: true });
}
foot(s);
s.addNotes('My first 3 hectare run stopped with an error, and this is why. Stands are made by joining small patches, and a patch is never split, so a patch bigger than 3 hectares can never sit inside a 3 hectare stand. With patch centres 10 pixels (about 100 metres) apart, 56 of the 3,596 patches were already bigger than 3 hectares, the largest 6.74 hectares in Dhenkanal. I moved the centres to 6 pixels (about 60 metres) apart: that gives 9,488 patches, a middle patch of 0.32 hectares instead of 0.85, and a largest patch of 2.02 hectares. The honest caveat is that the two stand maps now differ in two settings, the cap (10 to 3 hectares) and the patch spacing, so any difference between them could come from either.');

/* ============ 7 STAND SIZES ============ */
s = S();
title(s, 'With the 3 hectare cap, almost every stand is within the 2 to 3 hectares you asked for');
{
  const fw = 8.4;
  const box = fig(s, 'stand_sizes', MG, BODY_TOP, { w: fw,
    alt: 'Histograms and box plots of stand size at the 10 hectare and 3 hectare caps' });
  caption(s, 'Size of every stand: all districts together (left) and each district (right). Grey: up to 10 hectares. Green: up to 3 hectares.',
    MG, box.y + box.h + 0.08, fw);
  const x = MG + fw + 0.45, w = CW - fw - 0.45;
  s.addText([{ text: '51%', options: { color: SLATE } }, { text: '  →  ', options: { color: MUTE } },
    { text: '2%', options: { color: GREEN } }], { x, y: BODY_TOP, w, h: 0.7, fontFace: HF, fontSize: 36, bold: true,
    margin: 0, valign: 'bottom', isTextBox: true });
  text(s, 'of stands bigger than 3 hectares (the 41 that go over do so by at most 0.04 hectares)',
    { x, y: BODY_TOP + 0.76, w, h: 0.85, fontSize: 14 });
  s.addText([{ text: '3.1', options: { color: SLATE } }, { text: '  →  ', options: { color: MUTE } },
    { text: '2.35', options: { color: GREEN } }], { x, y: BODY_TOP + 1.75, w, h: 0.7, fontFace: HF, fontSize: 36, bold: true,
    margin: 0, valign: 'bottom', isTextBox: true });
  text(s, 'hectares: the middle stand size', { x, y: BODY_TOP + 2.51, w, h: 0.4, fontSize: 14 });
  s.addText([{ text: '184', options: { color: SLATE } }, { text: '  →  ', options: { color: MUTE } },
    { text: '113', options: { color: GREEN } }], { x, y: BODY_TOP + 3.1, w, h: 0.7, fontFace: HF, fontSize: 36, bold: true,
    margin: 0, valign: 'bottom', isTextBox: true });
  text(s, 'plots that share their stand with another plot. Smaller stands leave fewer plots to test the drawing with.',
    { x, y: BODY_TOP + 3.86, w, h: 1.0, fontSize: 14 });
}
foot(s);
s.addNotes('With the 10 hectare cap, half my stands (529 of 1,039, 51%) were bigger than the 2 to 3 hectares you asked for; the middle stand was 3.09 hectares and 9 in 10 stands were under 9.18 hectares. With the 3 hectare cap, the middle stand is 2.35 hectares and only 41 of 1,954 stands (2%) go over 3 hectares, each by at most 0.04 hectares. This holds in every district, as the box plots on the right show. There is a cost: a stand only tests the drawing question if it holds at least two plots, and that drops from 61 stands holding 184 plots to 44 stands holding 113 plots. So the 3 hectare map answers the size request but gives the drawing test less to work with.');

/* ============ 8 SPECIES ============ */
s = S();
title(s, 'Tree species could not tell these forests apart: 259 of 274 plots fell into one group');
{
  const box = fig(s, 'species_groups', MG, BODY_TOP, { h: 4.6,
    alt: 'Bar chart: grouping plots by species puts 259 of 274 plots in one group' });
  caption(s, 'The 274 plots grouped by the share of trunk area of each species, cut into 6 groups.', MG, box.y + box.h + 0.08, box.w + 0.5);
  const x = MG + box.w + 0.6, w = CW - box.w - 0.6;
  text(s, 'Before I could score the stands, I needed a truth to score them against. My first try was to group the plots by which tree species grow in them.',
    { x, y: BODY_TOP, w, h: 1.0, fontSize: 16 });
  const sy = BODY_TOP + 1.25, sw = (w - 0.4) / 3;
  [['12%', 'Sal'], ['9%', 'mango'], ['8%', 'jamun']].forEach(([n, l], i) =>
    stat(s, x + i * (sw + 0.2), sy, sw, n, l, { nfs: 34, lh: 0.4 }));
  text(s, 'average share of a plot\'s trunk area. No species dominates, and mango and jamun grow almost everywhere.',
    { x, y: sy + 1.1, w, h: 0.75, fontSize: 14, color: MUTE });
  text(s, [{ text: 'The 15 plots that broke away are almost all scrub', options: { bold: true } },
    { text: ' (13 of them are under 5 metres tall), not a different kind of forest. So species gives me one big group, not forest types I can score against.' }],
    { x, y: sy + 2.1, w, h: 1.3, fontSize: 16 });
}
foot(s);
s.addNotes('My first attempt at a field truth was to group the plots by species, using the share of trunk area of each of the 179 species. That put 259 of the 274 plots, 94.5%, into one group. The reason is that no species dominates: Sal averages only 12.1% of a plot\'s trunk area, mango 9.2%, jamun 8.3%, and only 32 plots are more than half Sal. Of the 15 plots that broke away, 13 are scrub or bushland under 5 metres, and 2 are ordinary low forest led by an unusual species. So species cannot sort these forests, and I needed a different truth.');

/* ============ 9 STRUCTURE ============ */
s = S();
title(s, 'So I grouped the plots by forest structure instead, into five clearly different forest types');
{
  const box = fig(s, 'structure_boxplots', MG, BODY_TOP, { w: 10.3,
    alt: 'Box plots of tree height, crown cover, number of trees and trunk area for the five forest types' });
  const x = MG + box.w + 0.3, w = CW - box.w - 0.3;
  stat(s, x, BODY_TOP + 0.2, w, '42%', 'of plots in the largest type, against 95% when grouped by species', { nfs: 34, lh: 1.25 });
  stat(s, x, BODY_TOP + 2.35, w, '4', 'things I measured: height, crown cover, number of trees, trunk area', { nfs: 34, lh: 1.25 });
}
text(s, 'The types run from scrub with almost no trees (middle height 1.4 metres) to tall forest with many trees (middle 29 trees in a plot). These five types are the truth I score the stands against.',
  { x: MG, y: 6.35, w: CW, h: 0.6, fontSize: 15 });
foot(s);
s.addNotes('Instead of species I used forest structure: average tree height, crown cover, number of trees and total trunk area in the plot, and let an automatic grouping sort the plots into five types. The types are scrub (20 plots, middle height 1.4 metres, almost no trees), low forest with few trees (114 plots, 7.0 metres, 6.5 trees), low forest with many trees (78 plots, 7.8 metres, 14 trees), tall forest with few big trees (47 plots, 18.1 metres, 8 trees) and tall forest with many trees (15 plots, 15.3 metres, 29 trees). The largest type holds 114 of 274 plots (41.6%), against 94.5% for species, so structure spreads the plots across five types instead of one. Trunk area is a total for the plot, not per hectare, because we still do not know the plot size.');

/* ============ 10 CHOOSING THE NUMBER OF FOREST TYPES ============ */
s = S();
title(s, 'The field data alone chose the number of forest types: the curve bends at 5');
{
  const box = fig(s, 'elbow_field', MG, BODY_TOP, { h: 4.65,
    alt: 'Elbow curve for the field forest types, bending at 5' });
  caption(s, 'How spread out the groups still are, for 2 to 12 forest types (all 274 plots).', MG, box.y + box.h + 0.08, box.w + 0.5);
  const x = MG + box.w + 0.6, w = CW - box.w - 0.6;
  text(s, [{ text: 'The elbow rule', options: { bold: true, color: GREEN, breakLine: true } },
    { text: 'I try 2, 3, 4 ... 12 groups and stop where adding another group stops helping much: the bend in the curve. This is the rule you suggested.' }],
    { x, y: BODY_TOP, w, h: 1.5, fontSize: 16 });
  stat(s, x, BODY_TOP + 1.75, w, '5', 'forest types, chosen from the field measurements only', { nfs: 44, nh: 0.75, lh: 0.45 });
  text(s, 'Other rules for choosing disagree (they pick 3, 8 or 9), so five is a choice, not a fact of the data. I kept the elbow rule so that both sides follow the same rule.',
    { x, y: BODY_TOP + 3.2, w, h: 1.3, fontSize: 15, color: MUTE });
}
foot(s);
s.addNotes('To decide how many forest types to use, I let the field data alone choose, with the elbow rule you suggested: I tried 2 to 12 groups and looked for the point where adding another group stops helping much. The curve bends at 5 (the spread falls from 100 at 2 groups to 52.7 at 5, then more slowly), so I used 5 forest types. I should be open that other rules for choosing the number disagree: the best-separation rule picks 3, and two others pick 8 and 9. I kept the elbow because it is the rule you named and because I apply the same rule to the stands on the next slide. Adding average trunk diameter as a fifth measurement keeps the bend at 5.');

/* ============ 11 CHOOSING THE NUMBER OF STAND TYPES ============ */
s = S();
title(s, 'For the stands the same rule points to 5 or 6 types; the maps use 6');
{
  const fw = 9.0;
  const box = fig(s, 'elbow_stands', MG, BODY_TOP, { w: fw,
    alt: 'Elbow curves for the stand types, bending at 5 or 6, with the 6 types used marked' });
  caption(s, 'Left: the curves for all four districts together. Right: where the curve bends in each district. Grey squares: stands up to 10 hectares. Green circles: up to 3 hectares.',
    MG, box.y + box.h + 0.06, fw);
  text(s, [{ text: 'Each side chose from its own data. ', options: { bold: true, color: GREEN } },
    { text: 'The stand side never saw the field plots and the field side never saw the satellite data, so I could not tune one to match the other.' }],
    { x: MG, y: box.y + box.h + 0.62, w: fw, h: 0.8, fontSize: 15 });
  const x = MG + fw + 0.4, w = CW - fw - 0.4;
  stat(s, x, BODY_TOP, w, '6', 'types used in the stand maps', { nfs: 40, nh: 0.7, lh: 0.35, color: AMBER });
  text(s, 'Stands up to 10 hectares bend at 6 in three districts, and at 5 in Koraput and overall. 6 is the middle answer.',
    { x, y: BODY_TOP + 1.3, w, h: 1.3, fontSize: 15 });
  text(s, 'Stands up to 3 hectares bend at 5 everywhere.', { x, y: BODY_TOP + 2.75, w, h: 0.6, fontSize: 15, bold: true });
  text(s, 'The curves are smooth with only a weak bend, so 5 and 6 are close.', { x, y: BODY_TOP + 3.55, w, h: 0.8, fontSize: 15, color: MUTE });
}
foot(s);
s.addNotes('I ran the same elbow rule on the satellite features of the stands, 22 features and no field data. For the 10 hectare stands the bend is at 6 in Angul, Dhenkanal and Kendujhar, but at 5 in Koraput and at 5 with all districts together; 6 is the middle of those five answers, and it is the number the stand maps use. For the 3 hectare stands every curve, each district and all together, bends at 5, so strictly the rule would pick 5 there, one fewer than I used. The bend is weak: going from 5 to 6 groups only lowers the spread from 68.4 to 63.8 for the 10 hectare stands and from 66.2 to 62.0 for the 3 hectare stands. Because the field side and the stand side each chose from their own data, neither number was tuned to make the match look better.');

/* ============ 12 HOW I SCORED ============ */
s = S();
title(s, 'I scored the match by asking, for every pair of plots, whether my map agrees with the ground');
{
  const lx = MG, ly = BODY_TOP + 0.05, lw = 3.6;
  card(s, lx, ly, lw, 1.0, TINT);
  s.addText('Take any two plots', { x: lx + 0.25, y: ly + 0.12, w: lw - 0.5, h: 0.32, fontFace: BF, fontSize: 16,
    bold: true, color: GREEN, margin: 0, isTextBox: true });
  dot(s, lx + 0.55, ly + 0.7, 0.36, TYPE_COLOUR[1]); dot(s, lx + 1.1, ly + 0.7, 0.36, TYPE_COLOUR[1]);
  text(s, 'plot A and plot B', { x: lx + 1.5, y: ly + 0.55, w: 1.9, h: 0.32, fontSize: 14, color: MUTE });
  const qs = [['The ground', 'Are they the same forest type?', 0.95],
              ['My map', 'Are they in the same stand? For labelling: do they get the same stand type?', 1.25]];
  let yy = ly + 1.15;
  qs.forEach(([h_, q, hh_]) => {
    card(s, lx, yy, lw, hh_, WHITE);
    s.addText(h_, { x: lx + 0.25, y: yy + 0.1, w: lw - 0.5, h: 0.3, fontFace: BF, fontSize: 15, bold: true,
      color: GREEN, margin: 0, isTextBox: true });
    text(s, q, { x: lx + 0.25, y: yy + 0.42, w: lw - 0.5, h: hh_ - 0.45, fontSize: 14 });
    yy += hh_ + 0.15;
  });
  arrow(s, lx + lw + 0.12, ly + 2.05, 0.5);
  const gx = lx + lw + 0.8, gy = ly, cw_ = 2.05, ch = 1.15, hw = 1.4, hh = 0.55;
  ['My map puts them together', 'My map keeps them apart'].forEach((t, j) =>
    s.addText(t, { x: gx + hw + j * (cw_ + 0.1), y: gy, w: cw_, h: hh, fontFace: BF, fontSize: 14, bold: true,
      color: INK, align: 'center', valign: 'bottom', margin: 0, isTextBox: true }));
  ['Alike on the ground', 'Different on the ground'].forEach((t, i) =>
    s.addText(t, { x: gx, y: gy + hh + 0.1 + i * (ch + 0.1), w: hw - 0.1, h: ch, fontFace: BF, fontSize: 14, bold: true,
      color: INK, valign: 'middle', margin: 0, isTextBox: true }));
  const cells = [[['Agree', 'alike plots kept together'], ['Disagree', 'alike plots split up']],
                 [['Disagree', 'different plots put together'], ['Agree', 'different plots kept apart']]];
  cells.forEach((row, i) => row.forEach(([big, small], j) => {
    const x = gx + hw + j * (cw_ + 0.1), y = gy + hh + 0.1 + i * (ch + 0.1), ok = big === 'Agree';
    card(s, x, y, cw_, ch, ok ? 'E1ECD9' : AMBER_TINT, ok ? RULE : 'E3C9AE');
    s.addText(big, { x, y: y + 0.12, w: cw_, h: 0.45, fontFace: HF, fontSize: 20, bold: true,
      color: ok ? GREEN : AMBER, align: 'center', margin: 0, isTextBox: true });
    s.addText(small, { x: x + 0.1, y: y + 0.6, w: cw_ - 0.2, h: 0.45, fontFace: BF, fontSize: 13,
      color: INK, align: 'center', margin: 0, isTextBox: true });
  }));
  const rx = gx + hw + 2 * cw_ + 0.1 + 0.35, rw = W - MG - rx;
  stat(s, rx, gy + 0.55, rw, '35,511', 'pairs among the 267 plots, each put in one of these four boxes', { nfs: 30, lh: 1.5 });
}
{
  const y = 5.95, x0 = MG + 3.9, x1 = W - MG - 0.2;
  text(s, [{ text: 'Agreement score: ', options: { bold: true, color: GREEN } },
    { text: 'one number that sums up the four boxes.' }], { x: MG, y: y - 0.35, w: 3.6, h: 0.8, fontSize: 15 });
  s.addShape(p.ShapeType.line, { x: x0, y, w: x1 - x0, h: 0, line: { color: MUTE, width: 1.5 } });
  [[0, '0 = no better than random grouping'], [1, '1 = perfect match']].forEach(([v, t]) => {
    const x = x0 + v * (x1 - x0);
    s.addShape(p.ShapeType.line, { x, y: y - 0.12, w: 0, h: 0.24, line: { color: MUTE, width: 1.5 } });
    s.addText(t, { x: v ? x - 3.4 : x, y: y + 0.2, w: 3.4, h: 0.32, fontFace: BF, fontSize: 14, color: INK,
      align: v ? 'right' : 'left', margin: 0, isTextBox: true });
  });
  const mx0 = x0 + 0.02 * (x1 - x0), mx1 = x0 + 0.06 * (x1 - x0);
  s.addShape(p.ShapeType.rect, { x: mx0, y: y - 0.1, w: mx1 - mx0, h: 0.2, fill: { color: AMBER }, line: { color: AMBER } });
  s.addText('my scores: 0.02 to 0.06', { x: mx1 + 0.15, y: y - 0.5, w: 3.2, h: 0.32, fontFace: BF, fontSize: 14,
    bold: true, color: AMBER, margin: 0, isTextBox: true });
}
foot(s);
s.addNotes('To score the match I look at every pair of plots, 35,511 pairs among the 267 plots inside the village forests. For each pair I ask the ground whether they are the same forest type, and my map whether they are in the same stand, or for the labelling question whether they get the same stand type. Labelling is scored within each district, because the automatic grouping is run separately in each district, so type 3 in Angul has nothing to do with type 3 in Koraput. The agreement score sums this up: 1 is a perfect match and 0 is what random grouping gives on average. My headline scores are between 0.02 and 0.06; an early bug that mixed up stand numbers between districts was caught by the significance check, and every number in this deck is after the fix.');

/* ============ 13 RANDOM-SHIFT TEST ============ */
s = S();
title(s, 'A score above zero is not enough, because neighbouring plots are alike anyway');
{
  const pw = 3.5, ph = 2.7, py = BODY_TOP + 0.45;
  const panels = [[MG, 'My real map', 0], [MG + pw + 1.3, 'One of 1,999 random maps', 1]];
  const base = [[-0.75, -0.35, 1], [-0.35, 0.3, 2], [0.15, -0.45, 3], [0.55, 0.15, 1], [0.95, -0.2, 2], [-0.1, 0.55, 4]];
  panels.forEach(([x, lbl, shifted]) => {
    s.addText(lbl, { x, y: BODY_TOP, w: pw, h: 0.35, fontFace: BF, fontSize: 15, bold: true, color: GREEN,
      margin: 0, isTextBox: true });
    // stands: a 3 by 2 grid of blocks inside the village outline
    const sx = x + 0.35, sy = py + 0.35, bw = (pw - 0.7) / 3, bh = (ph - 0.7) / 2;
    for (let r = 0; r < 2; r++) for (let c = 0; c < 3; c++)
      s.addShape(p.ShapeType.rect, { x: sx + c * bw, y: sy + r * bh, w: bw, h: bh, fill: { color: 'F4F8F1' },
        line: { color: 'A9BDA3', width: 1 } });
    s.addShape(p.ShapeType.ellipse, { x: x + 0.1, y: py + 0.1, w: pw - 0.2, h: ph - 0.2, fill: { type: 'none' },
      line: { color: GREEN, width: 2 } });
    const cx = x + pw / 2, cy = py + ph / 2, a = shifted ? 0.9 : 0, dx = shifted ? -0.2 : 0, dy = shifted ? 0.1 : 0;
    base.forEach(([ux, uy, t]) => {
      const rx = ux * Math.cos(a) - uy * Math.sin(a), ry = ux * Math.sin(a) + uy * Math.cos(a);
      dot(s, cx + rx + dx, cy + ry + dy, 0.28, TYPE_COLOUR[t]);
    });
  });
  const ax = MG + pw + 0.15;
  arrow(s, ax, py + ph / 2, 1.0, AMBER);
  s.addText('turn and move the plots at random inside the village', { x: ax - 0.05, y: py + ph / 2 + 0.12, w: 1.15,
    h: 1.2, fontFace: BF, fontSize: 12, color: AMBER, align: 'center', margin: 0, isTextBox: true });
  text(s, 'Same stands, same plots, same village: only the link between the plots and the stands is broken. I do this 1,999 times and score each random map.',
    { x: MG, y: py + ph + 0.25, w: 2 * pw + 1.3, h: 0.9, fontSize: 15 });
  // right: why chance is above zero
  const rx = MG + 2 * pw + 1.3 + 0.55, rw = W - MG - rx;
  s.addText([{ text: '43%', options: { color: GREEN } }, { text: '  against  ', options: { color: MUTE, fontSize: 18 } },
    { text: '28%', options: { color: SLATE } }], { x: rx, y: BODY_TOP, w: rw, h: 0.7, fontFace: HF, fontSize: 36,
    bold: true, margin: 0, valign: 'bottom', isTextBox: true });
  text(s, 'of plot pairs are the same forest type when both plots are in the same village, against pairs from different villages.',
    { x: rx, y: BODY_TOP + 0.76, w: rw, h: 1.0, fontSize: 14 });
  text(s, 'My stands never cross a village boundary, so even a meaningless map scores above zero.',
    { x: rx, y: BODY_TOP + 1.95, w: rw, h: 0.8, fontSize: 15, bold: true });
  text(s, 'To count, my real map has to beat nearly all of the random maps: about 1,900 of the 1,999.',
    { x: rx, y: BODY_TOP + 2.95, w: rw, h: 0.8, fontSize: 15 });
}
foot(s);
s.addNotes('A score above zero does not show that the stands work, because here chance is not zero. Plots in the same village forest are more alike: 43.1% of same-village pairs are the same forest type, against 27.8% of pairs in different villages. My stands never cross a village boundary, so any map, even a meaningless one, groups some alike plots just by keeping each village together. So for each village forest I turn and move the whole set of plots to a random position inside that village, keep the real stand map, and score again; I did this 1,999 times. This random-shift test keeps everything real except the link between plots and stands, and my real score has to beat nearly all of the random maps, about 1,900 of the 1,999, to count.');

/* ============ 14 RESULT: CHANCE TEST ============ */
s = S();
title(s, 'Neither stand size beats the randomly shifted maps, on either question');
{
  const fw = 8.9;
  const box = fig(s, 'chance_test', MG, BODY_TOP, { w: fw,
    alt: 'Four histograms of random-shift scores with the real score marked in the middle of each' });
  caption(s, 'Grey bars: scores of 1,999 random shifts of my stand map. Amber line: my real map.', MG, box.y + box.h + 0.08, fw);
  const x = MG + fw + 0.4, w = CW - fw - 0.4;
  text(s, [{ text: 'How to read it', options: { bold: true, color: GREEN, breakLine: true } },
    { text: 'If my stands followed the ground, the amber line would sit far to the right of the grey bars.' }],
    { x, y: BODY_TOP, w, h: 1.25, fontSize: 15 });
  text(s, [{ text: 'What I found', options: { bold: true, color: GREEN, breakLine: true } },
    { text: 'In all four panels it sits in the middle. My maps beat between 908 and 1,497 of the 1,999 random maps; to count they would need about 1,900.' }],
    { x, y: BODY_TOP + 1.45, w, h: 1.9, fontSize: 15 });
  stat(s, x, BODY_TOP + 3.45, w, '0 of 4', 'panels where my map does better than chance', { nfs: 34, color: AMBER, lh: 0.7 });
}
foot(s);
s.addNotes('Each panel shows the 1,999 randomly shifted maps as grey bars and my real map as the amber line. Top row: stands up to 10 hectares; bottom row: up to 3 hectares. For the drawing question, measured on the plots that share a stand, my score is 0.0236 at 10 hectares, beating 1,311 of 1,999 random maps, and 0.0253 at 3 hectares, beating 1,497. For labelling it is 0.0354 at 10 hectares (beats 908) and 0.0560 at 3 hectares (beats 977). In every case the real map sits in the middle of the random ones, so I have no evidence that either stand map does better than chance.');

/* ============ 15 RESULT: SUMMARY ============ */
s = S();
title(s, 'The 3 and 10 hectare stands cannot be told apart, and knowing only the village does better');
{
  const box = fig(s, 'summary_scores', MG, BODY_TOP - 0.05, { w: 11.4,
    alt: 'My scores as dots inside grey chance bands, with a dashed line for knowing only the village' });
  caption(s, 'Dot: my score. Grey band: the middle 90% of the 1,999 random maps. Dashed line: the score from knowing only which village a plot is in.',
    MG, box.y + box.h + 0.04, CW);
  const y = box.y + box.h + 0.5, cw_ = (CW - 0.6) / 3;
  [['0 of 10', 'tests beat chance once I allow for having run ten of them', AMBER],
   ['No difference', 'between 3 and 10 hectare stands beyond what chance alone produces', GREEN],
   ['0.074', 'from knowing only the village: higher than any of my stand scores (a sense of scale, not a test)', GREEN]]
    .forEach(([n, l, c], i) => stat(s, MG + i * (cw_ + 0.3), y, cw_, n, l, { nfs: 30, nh: 0.52, color: c, lh: 0.8 }));
}
foot(s);
s.addNotes('Here are the same four scores side by side. Every dot sits inside its chance band. I ran 10 headline tests in total (5 measures for each of the 2 stand sizes); the closest to passing was 3 hectare stand drawing on all plots, with a 0.036 chance of arising by luck on its own, which becomes 0.360 once I allow for having run ten tests, so 0 of 10 survive. On all 5 measures the 3 and 10 hectare stands differ by no more than chance already makes them differ; with only 20 village forests as independent units the test has little power to separate them. For scale, simply using the village forest as the grouping gives an agreement score of 0.074 on all plots (against 0.0115 and 0.0066 for my stands) and 0.089 for labelling within districts (against 0.035 and 0.056); this is a sense-of-scale comparison, not a formal test, and in the 3 hectare labelling panel the village line still falls inside that chance band.');

/* ============ 16 WHAT THIS TELLS ME ============ */
s = S();
title(s, 'What I take from this: no evidence yet that my stands follow the forest types on the ground');
{
  const lw = 7.9, items = [
    ['Neither stand map', 'groups alike plots, or gives them the same type, more often than a randomly shifted map does.'],
    ['Smaller stands did not help.', 'The 3 hectare map removes "the stands were too big" as the explanation, and still scores like chance.'],
    ['One likely reason:', 'the satellite features do not fall into clear groups. The elbow curves are smooth, and the stand types are only weakly separated.'],
    ['This is not proof that the method fails.', 'With 267 plots in 20 village forests the test has little power; what I can say is that it shows no sign of beating chance.']];
  items.forEach(([b, t], i) => {
    const y = BODY_TOP + 0.05 + i * 1.22;
    numCircle(s, MG, y, i + 1);
    text(s, [{ text: b + ' ', options: { bold: true } }, { text: t }], { x: MG + 0.75, y: y - 0.02, w: lw - 0.75, h: 1.1, fontSize: 16 });
  });
  const rx = MG + lw + 0.5, rw = W - MG - rx;
  card(s, rx, BODY_TOP + 0.05, rw, 4.65, TINT);
  stat(s, rx + 0.35, BODY_TOP + 0.35, rw - 0.7, '0.21', 'the best separation the stand types reach, on a scale from -1 (wrong groups) to 1 (perfectly separate groups)',
    { nfs: 44, nh: 0.8, lh: 1.3 });
  text(s, 'Measured on the 10 hectare stands, all districts together. When groups overlap this much, where the lines between them fall is partly arbitrary, which would make the types hard to match to forest types on the ground.',
    { x: rx + 0.35, y: BODY_TOP + 2.65, w: rw - 0.7, h: 1.9, fontSize: 14, color: MUTE });
}
foot(s);
s.addNotes('My reading is that, with this data, there is no evidence that my stands follow the forest types measured on the ground, either in where they draw boundaries or in the types they give. The 3 hectare run matters because it answers the obvious objection that the 10 hectare stands were simply too big: at 3 hectares the result is the same. One likely reason is on the satellite side: the elbow curves are smooth with only a weak bend, and the best separation score the stand types reach is 0.21 at 4 types, on a scale from -1 to 1, so the types are only weakly separated. I want to be careful not to overclaim in the other direction: 267 plots in 20 village forests give the test little power, so this is no sign of beating chance, not proof that the method fails.');

/* ============ 17 CLAIMS AND NEXT STEPS (dark) ============ */
s = S(); s.background = { color: GREEN };
title(s, 'What I can claim, what I cannot, and where I would like your view', { color: WHITE });
{
  const cols = [
    ['I can say', [
      'With 267 plots in 20 village forests, my stands do not group or label alike plots better than a randomly shifted map.',
      'This holds at both stand sizes, 10 and 3 hectares.',
      'Tree species cannot separate these forests; forest structure can.']],
    ['I cannot say', [
      'That the method fails: the test has little power with 20 village forests.',
      'That 3 hectare stands are better or worse than 10 hectare stands.',
      'Which change mattered: the size cap and the patch spacing both changed.',
      'Anything per hectare, until we know the plot size.']],
    ['Your view, please', [
      'Should I add more village forests with several plots each before changing the method?',
      'Should I re-run the stand types with 5, which is what the elbow rule picks, instead of 6?',
      'Can we ask the field team to confirm the plot size?']]];
  const cw_ = (CW - 0.6) / 3, y = BODY_TOP + 0.1, hgt = 4.3;
  cols.forEach(([head, items], i) => {
    const x = MG + i * (cw_ + 0.3);
    s.addShape(p.ShapeType.roundRect, { x, y, w: cw_, h: hgt, rectRadius: 0.08,
      fill: { color: i === 2 ? WHITE : DARK_CARD }, line: { color: i === 2 ? WHITE : DARK_CARD } });
    s.addText(head, { x: x + 0.3, y: y + 0.25, w: cw_ - 0.6, h: 0.45, fontFace: HF, fontSize: 22, bold: true,
      color: i === 2 ? AMBER : WHITE, margin: 0, isTextBox: true });
    bullets(s, items, { x: x + 0.3, y: y + 0.9, w: cw_ - 0.6, h: hgt - 1.1, fontSize: 15, gap: 10,
      color: i === 2 ? INK : PALE_ON_DARK });
  });
}
foot(s, true);
s.addNotes('To close, here is where I think I stand. I can say that, with 267 plots in 20 village forests, my stands do not group or label alike plots better than a randomly shifted map, at 10 hectares or at 3 hectares, and that species cannot separate these forests while structure can. I cannot say that the method fails, because 20 village forests give the test little power; I cannot rank the two stand sizes; I cannot say whether the size cap or the patch spacing made any difference, since both changed; and I cannot give anything per hectare until the plot size is confirmed. Where I would like your view: whether to add more village forests first, whether to re-run the stand types with 5 instead of 6, and whether we can get the plot size confirmed by the field team.');

p.writeFile({ fileName: OUT }).then(() => console.log('WROTE', SN, 'slides ->', OUT))
  .catch(e => { console.error('ERR', e); process.exit(1); });
