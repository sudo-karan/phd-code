/*
 * FMU honest status deck — plain text on white, no colour, no art. Real screenshots embedded.
 *
 * Deps:  npm install pptxgenjs
 * Inputs: the report figures under reports/ (scripts/report.py output) and
 *         report_screenshot_top.png (run scripts/report_screenshot.py first).
 * Run from the repo root:  node scripts/build_honest.js
 */
const path = require('path');
const pptxgen = require('pptxgenjs');
const REPO = path.resolve(__dirname, '..');
const R = REPO + '/reports/multi_sanjay_van_baseline';
const FIG = {
  reportTop: REPO + '/report_screenshot_top.png',
  sil:    R + '/silhouette_bars.png',
  mapB:   R + '/_sanjay_van_baseline/stand_map.png',
  mapA:   R + '/_sanjay_van_alphaearth/stand_map.png',
  conf:   R + '/_sanjay_van_alphaearth/confusion.png',
  confid: R + '/_sanjay_van_alphaearth/confidence.png',
  phenology: REPO + '/reports/sanjay_van_baseline/phenology.png',
  seppow:    REPO + '/reports/sanjay_van_baseline/separating_power.png',
  c0conf:    REPO + '/reports/comparison_sanjay_van_nirv_dual_vs_sanjay_van_baseline/confusion.png',
};
const INK = '111111', GRAY = '5B5B5B', LINE = '111111';
const F = 'Arial';
const W = 13.33, H = 7.5, M = 0.7;

const p = new pptxgen();
p.layout = 'LAYOUT_WIDE';
p.defineSlideMaster({ title: 'W', background: { color: 'FFFFFF' } });

function slide() { return p.addSlide({ masterName: 'W' }); }
function title(s, t) {
  s.addText(t, { x: M, y: 0.5, w: W - 2*M, h: 0.8, fontFace: F, fontSize: 26, bold: true, color: INK, align: 'left' });
}
function kicker(s, t) {
  s.addText(t, { x: M, y: 0.32, w: W - 2*M, h: 0.3, fontFace: F, fontSize: 12, bold: true, color: GRAY, align: 'left', charSpacing: 2 });
}
function bullets(s, items, opt = {}) {
  const y = opt.y || 1.7, h = opt.h || 5.2, fs = opt.fs || 17, x = opt.x || M, w = opt.w || (W - 2*M);
  s.addText(items.map(it => ({
    text: typeof it === 'string' ? it : it.t,
    options: { bullet: (typeof it === 'object' && it.sub) ? { indent: 20 } : { code: '2022' },
               indentLevel: (typeof it === 'object' && it.sub) ? 1 : 0,
               color: INK, breakLine: true, paraSpaceAfter: (opt.gap != null ? opt.gap : 12), fontSize: fs } })),
    { x, y, w, h, fontFace: F, valign: 'top', lineSpacingMultiple: 1.05 });
}
function note(s, t, y) {
  s.addText(t, { x: M, y: y || 6.7, w: W - 2*M, h: 0.6, fontFace: F, fontSize: 13, italic: true, color: GRAY, align: 'left' });
}
function arrowH(s, x, y, w) {
  s.addShape(p.ShapeType.line, { x, y, w, h: 0, line: { color: LINE, width: 1.5, endArrowType: 'triangle' } });
}
function img(s, path, x, y, w, h) {
  s.addImage({ path, x, y, w, h, sizing: { type: 'contain', w, h } });
}
function caption(s, t, x, y, w) {
  s.addText(t, { x, y, w, h: 0.5, fontFace: F, fontSize: 12, italic: true, color: GRAY, align: 'left' });
}
function divider(s, big, sub) {
  s.addText(big, { x: M, y: 3.0, w: W - 2*M, h: 1.0, fontFace: F, fontSize: 34, bold: true, color: INK, align: 'left' });
  if (sub) s.addText(sub, { x: M, y: 4.05, w: W - 2*M, h: 0.6, fontFace: F, fontSize: 16, color: GRAY, align: 'left' });
}
let s;

// 1 TITLE
s = slide();
s.addText('FMU: what I have done, how it compares to AlphaEarth,\nand the open gaps',
  { x: M, y: 2.2, w: W - 2*M, h: 1.6, fontFace: F, fontSize: 30, bold: true, color: INK, align: 'left', lineSpacingMultiple: 1.1 });
s.addText('An honest status report', { x: M, y: 3.95, w: W - 2*M, h: 0.5, fontFace: F, fontSize: 18, color: GRAY, align: 'left' });
s.addText('Study area: Sanjay Van, Delhi (13.0 km2)   |   window 2017–2022   |   unsupervised, no ground-truth stand map',
  { x: M, y: 5.0, w: W - 2*M, h: 0.5, fontFace: F, fontSize: 13, color: GRAY, align: 'left' });
s.addText('Prepared with Claude Code. Field/gap analysis from a separate Claude Science session.',
  { x: M, y: 6.7, w: W - 2*M, h: 0.4, fontFace: F, fontSize: 12, italic: true, color: GRAY });

// 2 WHAT FMU IS
s = slide(); kicker(s, 'PART 1 — WHAT I HAVE DONE'); title(s, 'What FMU is');
bullets(s, [
  'FMU delineates forest "stands" (management units) from satellite time series.',
  'It is unsupervised: there is no field-drawn / operational stand map to train against.',
  'It runs entirely on Google Earth Engine, driven by a YAML config, cached as EE assets.',
  'It is multi-sensor: optical phenology + radar + canopy structure + terrain.',
  'What I have so far is a replication of the paper’s method, extended with one experiment (below).',
], { y: 1.9, gap: 16 });
note(s, 'Honest framing used throughout: with no ground truth, nothing here claims one map is "more correct".');

// 3 PIPELINE (text + arrow)
s = slide(); kicker(s, 'PART 1 — WHAT I HAVE DONE'); title(s, 'The pipeline, step by step');
const steps = ['mask', 'load', 'features', 'SNIC', 'k-means', 'profile', 'export', 'metrics'];
let sx = M, syl = 2.4; const stepW = (W - 2*M) / steps.length;
steps.forEach((st, i) => {
  s.addText(String(i+1) + '. ' + st, { x: sx, y: syl, w: stepW - 0.15, h: 0.5, fontFace: F, fontSize: 14, bold: true, color: INK, align: 'left', valign: 'middle' });
  if (i < steps.length - 1) arrowH(s, sx + stepW - 0.42, syl + 0.25, 0.3);
  sx += stepW;
});
bullets(s, [
  'mask – restrict to the habitat of interest.',
  'load – Sentinel-2, Sentinel-1, and auxiliary layers.',
  'features – build the multi-sensor feature stack (step-by-step next).',
  'SNIC – group pixels into superpixels (held fixed across all experiments = the control).',
  'k-means – cluster superpixels into k = 6 stand types.',
  'profile / export / metrics – per-stand statistics, output rasters + polygons, comparison scores.',
], { y: 3.4, gap: 10, fs: 15 });

// 4 FEATURE STACK
s = slide(); kicker(s, 'PART 1 — WHAT I HAVE DONE'); title(s, 'Step: the hand-crafted feature stack (22 bands)');
bullets(s, [
  'Optical / phenology (Sentinel-2): NDVI mean, amplitude, phase, trend, residual variance.',
  'Radar (Sentinel-1): VV and VH backscatter percentiles (p10 / p50 / p90) and spread.',
  'Canopy structure: canopy height (mean, max, std).',
  'Static terrain & climate: elevation, slope, aspect, annual rainfall, distance to water.',
], { y: 1.9, gap: 16 });
s.addText('22 feature bands total  |  all reduced over one 2017–2022 window  |  robust-scaled before clustering',
  { x: M, y: 5.0, w: W - 2*M, h: 0.5, fontFace: F, fontSize: 15, bold: true, color: INK });
note(s, 'This hand-crafted stack is the thing an embedding model (AlphaEarth) proposes to replace — see Part 2.');

// 5 SNIC + KMEANS + REST
s = slide(); kicker(s, 'PART 1 — WHAT I HAVE DONE'); title(s, 'Step: segment, cluster, profile, score');
bullets(s, [
  'SNIC segmentation builds spatially coherent superpixels. Its inputs are composite + structure + radar only — so the boundaries are identical no matter which feature stack is clustered. This is the experimental control.',
  'k-means (k = 6, fixed seed) clusters the superpixel-mean features into stand types. The clustering is band-name-agnostic, so it runs unchanged on 22 hand-crafted bands or on 64 embedding dimensions.',
  'Profiling summarises each cluster in original units (canopy height, NDVI, backscatter).',
  'Metrics: silhouette per run, plus ARI / NMI / Hungarian overlap / agreement vs a reference run.',
], { y: 1.9, gap: 16, fs: 16 });
note(s, 'k = 6 is currently a fixed choice, not a swept / justified value — flagged later as gap G3.');

// 5b INTERPRETABILITY (hand-crafted profiling output)
s = slide(); kicker(s, 'PART 1 — WHAT I HAVE DONE'); title(s, 'What the hand-crafted stack lets me say');
img(s, FIG.phenology, M, 1.7, 5.3, 5.3/1.32);
img(s, FIG.seppow, 6.35, 1.7, 4.5, 4.5/1.06);
caption(s, 'Baseline profiling output. Left: per-stand seasonal NDVI curve. Right: which features drive the partition (canopy height, elevation, seasonal amplitude lead).', M, 6.15, W - 2*M);
s.addText('Every stand is describable in real ecological units. The AlphaEarth embedding has no equivalent — its 64 dimensions are unnamed (see Part 3).',
  { x: M, y: 6.6, w: W - 2*M, h: 0.4, fontFace: F, fontSize: 13, italic: true, color: GRAY });

// 6 WHAT I HAVE RUN
s = slide(); kicker(s, 'PART 1 — WHAT I HAVE DONE'); title(s, 'What I have actually run');
bullets(s, [
  'Replicated the full pipeline end-to-end (mask → metrics).',
  'C-0: baseline vs variant (NDVI vs NIRv + dual-harmonic), SNIC held fixed — one completed feature-swap comparison.',
  'Built and ran the AlphaEarth embedding arm end-to-end on Sanjay Van (Part 2).',
], { y: 1.8, gap: 14 });
s.addText('Honest status of the AlphaEarth comparison:', { x: M, y: 4.2, w: W - 2*M, h: 0.4, fontFace: F, fontSize: 15, bold: true, color: INK });
bullets(s, [
  'Scored with internal metrics only (no external / ecological reference yet).',
  'Run on Sanjay Van — the secondary AOI; Mudumalai (the site with field ground truth) is not yet done.',
  'Two arms only — the Tessera arm is blocked (data coverage + ingestion bug).',
  'Not pre-registered — no hypothesis was fixed before running.',
], { y: 4.6, gap: 8, fs: 14 });

// 6b C-0 COMPARISON (already completed feature swap)
s = slide(); kicker(s, 'PART 1 — WHAT I HAVE DONE'); title(s, 'The comparison I had already run (C-0)');
img(s, FIG.c0conf, M, 1.8, 4.4*0.93, 4.4);
s.addText('baseline  vs  NIRv + dual-harmonic   (optical features changed; SNIC / k / seed fixed)',
  { x: 5.3, y: 1.9, w: W - M - 5.3, h: 0.6, fontFace: F, fontSize: 15, bold: true, color: INK });
bullets(s, [
  'Same design as the AlphaEarth swap, but only the optical features change.',
  'Best-match overlap stays high — 73% to 92% (green rings). A small feature tweak barely moves the map.',
  'This is the template (C-0). Part 2 runs the same experiment but swaps the whole representation — and the map moves far more (agreement drops to 41%).',
], { x: 5.3, w: W - M - 5.3, y: 2.7, gap: 12, fs: 14 });

// 7 DIVIDER PART 2
s = slide(); divider(s, 'Part 2 — how my code compares with AlphaEarth', 'The "swap only the feature arm" experiment, and its real outputs.');

// 8 THE EXPERIMENT (text + arrows)
s = slide(); kicker(s, 'PART 2 — COMPARISON WITH ALPHAEARTH'); title(s, 'The experiment: swap only the feature arm');
// Arm A line
s.addText('Hand-crafted 22-band stack', { x: M, y: 2.4, w: 4.2, h: 0.4, fontFace: F, fontSize: 15, bold: true, color: INK, valign: 'middle' });
arrowH(s, M + 4.2, 2.6, 0.5);
s.addText('k-means (k=6)', { x: M + 4.8, y: 2.4, w: 2.4, h: 0.4, fontFace: F, fontSize: 15, color: INK, valign: 'middle' });
arrowH(s, M + 7.2, 2.6, 0.5);
s.addText('stands (Arm A)', { x: M + 7.8, y: 2.4, w: 3.0, h: 0.4, fontFace: F, fontSize: 15, color: INK, valign: 'middle' });
// Arm B line
s.addText('AlphaEarth 64-D embedding', { x: M, y: 3.5, w: 4.2, h: 0.4, fontFace: F, fontSize: 15, bold: true, color: INK, valign: 'middle' });
arrowH(s, M + 4.2, 3.7, 0.5);
s.addText('k-means (k=6)', { x: M + 4.8, y: 3.5, w: 2.4, h: 0.4, fontFace: F, fontSize: 15, color: INK, valign: 'middle' });
arrowH(s, M + 7.2, 3.7, 0.5);
s.addText('stands (Arm B)', { x: M + 7.8, y: 3.5, w: 3.0, h: 0.4, fontFace: F, fontSize: 15, color: INK, valign: 'middle' });
// converge to compare
s.addShape(p.ShapeType.line, { x: M + 9.6, y: 2.6, w: 0, h: 1.1, line: { color: LINE, width: 1.2 } });
arrowH(s, M + 9.6, 3.15, 0.5);
s.addText('compare:\nARI, NMI, silhouette, agreement', { x: M + 10.2, y: 2.85, w: 2.4, h: 0.7, fontFace: F, fontSize: 13, color: INK, valign: 'middle' });
s.addText('Held identical for both arms: SNIC boundaries, k = 6, random seed, ROI, time window.',
  { x: M, y: 4.7, w: W - 2*M, h: 0.4, fontFace: F, fontSize: 15, bold: true, color: INK });
bullets(s, [
  'Only the feature vector changes — so any difference is attributable to the representation, not the pipeline.',
  'This is exactly the "hand-crafted vs pretrained embedding" question the current literature is asking.',
], { y: 5.3, gap: 10, fs: 14 });

// 9 THE REPORT (screenshot)
s = slide(); kicker(s, 'PART 2 — COMPARISON WITH ALPHAEARTH'); title(s, 'The report my code produces');
img(s, FIG.reportTop, M, 1.55, W - 2*M, 5.2);
caption(s, 'Screenshot of the HTML report generated by scripts/report.py (config summary + metrics table). Numbers below are read from this report.', M, 6.85, W - 2*M);

// 10 RESULT: SEPARATION
s = slide(); kicker(s, 'PART 2 — COMPARISON WITH ALPHAEARTH'); title(s, 'Result 1: cluster separation (silhouette)');
img(s, FIG.sil, M, 1.7, 7.6, 7.6/2.38);
s.addText('+0.113', { x: 8.7, y: 2.0, w: 4.0, h: 0.8, fontFace: F, fontSize: 40, bold: true, color: INK, align: 'left' });
s.addText('AlphaEarth', { x: 8.7, y: 2.85, w: 4.0, h: 0.4, fontFace: F, fontSize: 15, color: GRAY });
s.addText('−0.007', { x: 8.7, y: 3.5, w: 4.0, h: 0.8, fontFace: F, fontSize: 40, bold: true, color: INK, align: 'left' });
s.addText('baseline (hand-crafted)', { x: 8.7, y: 4.35, w: 4.0, h: 0.4, fontFace: F, fontSize: 15, color: GRAY });
bullets(s, [
  'Silhouette is intrinsic (needs no reference) so it is directly comparable across arms.',
  'AlphaEarth clusters are clearly more separable; the baseline sits essentially at zero.',
  'Honest limit: this is an internal geometry measure, not evidence of ecological correctness.',
], { y: 5.1, gap: 8, fs: 14 });

// 11 RESULT: STAND MAPS
s = slide(); kicker(s, 'PART 2 — COMPARISON WITH ALPHAEARTH'); title(s, 'Result 2: the stand maps');
s.addText('Baseline (hand-crafted)', { x: 1.0, y: 1.6, w: 3.6, h: 0.35, fontFace: F, fontSize: 14, bold: true, color: INK, align: 'center' });
img(s, FIG.mapB, 1.0, 1.95, 3.6, 4.3);
s.addText('AlphaEarth (embedding)', { x: 5.0, y: 1.6, w: 3.6, h: 0.35, fontFace: F, fontSize: 14, bold: true, color: INK, align: 'center' });
img(s, FIG.mapA, 5.0, 1.95, 3.6, 4.3);
bullets(s, [
  'Same SNIC boundaries in both; only the cluster assignment differs.',
  'Colours are per-arm — the same colour is a different stand in each map.',
  'AlphaEarth gives larger, more contiguous stands; the baseline is more fragmented.',
], { x: 9.0, w: W - M - 9.0, y: 2.1, gap: 12, fs: 13 });

// 12 RESULT: AGREEMENT
s = slide(); kicker(s, 'PART 2 — COMPARISON WITH ALPHAEARTH'); title(s, 'Result 3: agreement between the two arms');
img(s, FIG.conf, M, 1.75, 4.4*0.93, 4.4);
s.addText('ARI 0.17    NMI 0.23    Agreement 41%', { x: 5.4, y: 2.0, w: W - M - 5.4, h: 0.5, fontFace: F, fontSize: 20, bold: true, color: INK });
bullets(s, [
  'Low-to-moderate agreement: after Hungarian alignment only ~41% of pixels fall in corresponding stands.',
  'The two representations delineate the forest quite differently.',
  'Green rings mark each AlphaEarth stand’s best-matching baseline stand — some map cleanly, others split.',
  'Neither arm is a reference; this only quantifies how much the representation reshapes the map.',
], { x: 5.4, w: W - M - 5.4, y: 2.7, gap: 12, fs: 14 });

// 13 RESULT: CONFIDENCE
s = slide(); kicker(s, 'PART 2 — COMPARISON WITH ALPHAEARTH'); title(s, 'Result 4: per-stand consensus (confidence)');
img(s, FIG.confid, M, 1.9, 7.4, 7.4/2.61);
s.addText('mean 40%    |    33% of area ≥ 80% agreement', { x: M, y: 5.0, w: W - 2*M, h: 0.5, fontFace: F, fontSize: 18, bold: true, color: INK });
bullets(s, [
  'Confidence = how often the two representations place a stand in corresponding classes (rolled up per stand).',
  'It is a consensus / stability layer, explicitly not a correctness score — that would need ground truth.',
], { y: 5.6, gap: 10, fs: 14 });

// 14 HONEST READING
s = slide(); kicker(s, 'PART 2 — COMPARISON WITH ALPHAEARTH'); title(s, 'What this comparison does and does not show');
s.addText('It DOES show:', { x: M, y: 1.7, w: 5.8, h: 0.4, fontFace: F, fontSize: 16, bold: true, color: INK });
bullets(s, [
  'The two feature representations cluster the forest differently (ARI 0.17).',
  'AlphaEarth clusters are internally more separable (silhouette +0.113 vs −0.007).',
  'Where they agree can be mapped as a consensus layer.',
], { x: M, w: 5.9, y: 2.15, gap: 10, fs: 14 });
s.addText('It does NOT show:', { x: 7.0, y: 1.7, w: 5.6, h: 0.4, fontFace: F, fontSize: 16, bold: true, color: INK });
bullets(s, [
  'That either representation is ecologically more correct — no ground truth exists.',
  'External validity — all scores are internal (agreement between arms is not truth).',
  'Generality — one AOI (Sanjay Van), one k, two arms, not pre-registered.',
], { x: 7.0, w: W - M - 7.0, y: 2.15, gap: 10, fs: 14 });
note(s, 'AlphaEarth: Brown et al. 2025 (arXiv:2507.22291), 64-D per-pixel annual embedding in Earth Engine. TESSERA: Feng et al. 2025 (arXiv:2506.20380), 128-D S1/S2 time-series, preserves phenology, CC0.');

// 15 DIVIDER PART 3
s = slide(); divider(s, 'Part 3 — the gaps we identified', 'Gaps I found with a separate Claude Science literature review (~246 verified DOIs).');

// 16 THE BIG GAP
s = slide(); kicker(s, 'PART 3 — GAPS'); title(s, 'The one gap underneath all the others');
s.addText('There is no independent, stand-level ground reference.',
  { x: M, y: 1.9, w: W - 2*M, h: 0.5, fontFace: F, fontSize: 20, bold: true, color: INK });
bullets(s, [
  'So "ecologically meaningful" is currently neither provable nor falsifiable at scale.',
  'Unsupervised delineation has no agreed validation grammar — only internal, circular metrics.',
  'Embedding clusters get checked against land-cover labels, not against ecology.',
  'This is a field-wide condition, not a personal one — it is where the contribution is.',
], { y: 2.7, gap: 14 });
note(s, 'This reframes the advisor’s "going in circles" feedback: the loop is the field’s, and it points at the opening.');

// 17 GAPS ON MY PATH
s = slide(); kicker(s, 'PART 3 — GAPS'); title(s, 'Gaps on my committed path');
bullets(s, [
  'G1 — no validation grammar for unsupervised delineation (internal metrics are circular).',
  'G2 — a "stand" is aggregated from superpixels, never drawn or tested against a reference unit.',
  'G3 — k and segmentation parameters chosen unprincipled; k = 6 is asserted, not swept.',
  'G4 — embeddings vs hand-crafted features have never been raced head-to-head for stand clustering.',
  'G10–G13 — the "spectral community" bridge (SVH) is untested in Indian dry forest, and I have no falsifiable claim yet.',
], { y: 1.9, gap: 15, fs: 16 });
note(s, 'My AlphaEarth run is a first attack on G4 — but internal-only, so it does not yet close it (needs G1/G2 external validation).');

// 18 THE SVH TEST
s = slide(); kicker(s, 'PART 3 — GAPS'); title(s, 'The SVH test (what would close G10–G13)');
bullets(s, [
  'Spectral Variation Hypothesis (SVH): spectral heterogeneity is a proxy for biological diversity.',
  'Alpha-SVH: within a patch, does more spectral variation mean more species?',
  'Beta-SVH: do two spectrally different patches also differ in species? — this is what validates a stand boundary.',
  'Test: correlate spectral distance vs field species turnover across units, with a permutation / Mantel null.',
  'Site: the Mudumalai ForestGEO stem-mapped plot gives the real species ground truth.',
], { y: 1.85, gap: 12, fs: 15 });
s.addText('Papers I am confident about:', { x: M, y: 5.5, w: W - 2*M, h: 0.35, fontFace: F, fontSize: 13, bold: true, color: INK });
s.addText('Schmidtlein & Fassnacht 2017 (RSE, doi:10.1016/j.rse.2017.01.036) — SVH does not hold generally (falsification).   Nagendra 2010 (doi:10.3390/rs2020478) — Indian dry forest, mixed/scale-dependent.   Torresani et al. 2024 (doi:10.1016/j.ecoinf.2024.102702) — 20-year review.',
  { x: M, y: 5.85, w: W - 2*M, h: 1.0, fontFace: F, fontSize: 12, color: GRAY, lineSpacingMultiple: 1.1 });

// 19 MAKE IT A CONTRIBUTION
s = slide(); kicker(s, 'PART 3 — GAPS'); title(s, 'What would turn my current work into a real result');
bullets(s, [
  'Add external validation (the missing piece): score each arm against an independent reference, not just against each other.',
  'References available now: national forest-type maps (Roy 2015 / Reddy 2015 — to confirm) and FSI products (coarse, wall-to-wall); the Mudumalai ForestGEO plot (fine, real, but one plot).',
  'Run on Mudumalai as the primary AOI — it carries the ground truth; Sanjay Van becomes the transfer test.',
  'Add the Tessera arm (fix the ingestion) for a three-way comparison.',
  'Pre-register the hypothesis before running, so the pipeline can fail (closes the "no committed hypothesis" gap).',
], { y: 1.9, gap: 13, fs: 15 });

// 20 PAPERS
s = slide(); kicker(s, 'PART 3 — GAPS'); title(s, 'Papers');
s.addText('Confident (used above):', { x: M, y: 1.7, w: W - 2*M, h: 0.35, fontFace: F, fontSize: 15, bold: true, color: INK });
bullets(s, [
  'AlphaEarth Foundations — Brown et al. 2025, arXiv:2507.22291.',
  'TESSERA — Feng et al. 2025, arXiv:2506.20380.',
  'Schmidtlein & Fassnacht 2017 — Remote Sensing of Environment, doi:10.1016/j.rse.2017.01.036.',
  'Nagendra 2010 — doi:10.3390/rs2020478.  Torresani et al. 2024 — doi:10.1016/j.ecoinf.2024.102702.',
], { y: 2.1, gap: 8, fs: 13.5 });
s.addText('To confirm with Claude Science (I did not want to assert these):', { x: M, y: 4.1, w: W - 2*M, h: 0.35, fontFace: F, fontSize: 15, bold: true, color: INK });
bullets(s, [
  'SVH origin: Palmer 2002 and Rocchini 2004 — exact refs/claims.',
  '"Spectral species": Féret & Asner 2014 — exact ref.',
  'SVH design checklist: "Wallis 2025" — which paper exactly?',
  'Confounds: Wang 2017 (grain/scale) and Thornley 2022 (phenology) — exact refs.',
  'Indian forest-type reference maps: Roy 2015, Reddy 2015 — exact refs. Delineation: Xiong 2024, Sandum/Ørka 2026.',
], { y: 4.5, gap: 7, fs: 13 });

// 21 BOTTOM LINE
s = slide(); kicker(s, 'BOTTOM LINE'); title(s, 'Where this honestly stands');
bullets(s, [
  'Done: a working, reproducible, unsupervised multi-sensor pipeline, plus one completed feature-swap (C-0) and the AlphaEarth swap run end-to-end.',
  'The AlphaEarth comparison shows the embedding separates stands better internally (+0.113 vs −0.007) and delineates differently (ARI 0.17) — but on internal metrics only, one AOI, two arms.',
  'It is not yet a validated result: no external reference, not on the ground-truth site (Mudumalai), no pre-registered hypothesis.',
  'The real work ahead is validation: external references now, Mudumalai run, the falsifiable SVH test — that is what turns clusters into an ecological claim.',
], { y: 1.9, gap: 15, fs: 16 });

p.writeFile({ fileName: REPO + '/FMU_honest_deck.pptx' }).then(f => console.log('WROTE', REPO + '/FMU_honest_deck.pptx')).catch(e => { console.error(e); process.exit(1); });
