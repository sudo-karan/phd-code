/*
 * FMU deck — Forest Management Units: methodology + embedding-arm experiment + results.
 *
 * Regenerates FMU_deck.pptx from the figures under reports/multi_sanjay_van_baseline/
 * (produced by `python scripts/report.py --multi --reference sanjay_van_baseline
 *  --configs sanjay_van_alphaearth --vectors-dir fmu_exports`).
 *
 * Deps (not part of the Python package):
 *   npm install pptxgenjs react react-dom react-icons sharp
 * Run from the repo root:
 *   node scripts/build_deck.js
 */
const path = require('path');
const pptxgen = require('pptxgenjs');
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const sharp = require('sharp');
const Fa = require('react-icons/fa');

// ---------- palette ----------
const C = {
  bgDark:  '17362A',   // deep forest
  bgDark2: '20492F',
  forest:  '2C5F2D',
  moss:    '7FA65B',
  mossLt:  '97BC62',
  amber:   'C77E33',   // AlphaEarth accent (matches map orange)
  amberDk: 'A9631F',
  slate:   '4E7080',   // baseline accent
  slateDk: '3A5561',
  ink:     '1A2620',
  mute:    '5F6F66',
  white:   'FFFFFF',
  tint:    'EEF3E9',   // green card
  tintA:   'F7EEE1',   // amber card
  tintS:   'EAF1F3',   // slate card
  line:    'D6E0CF',
};
const HF = 'Cambria';      // header serif (safe list)
const BF = 'Calibri';      // body sans (safe list)

const REPO = path.resolve(__dirname, '..');
const R = REPO + '/reports/multi_sanjay_van_baseline';
const FIG = {
  sil:    R + '/silhouette_bars.png',
  mapB:   R + '/_sanjay_van_baseline/stand_map.png',
  mapA:   R + '/_sanjay_van_alphaearth/stand_map.png',
  conf:   R + '/_sanjay_van_alphaearth/confusion.png',
  confid: R + '/_sanjay_van_alphaearth/confidence.png',
  sizeB:  R + '/_sanjay_van_baseline/sizes.png',
  sizeA:  R + '/_sanjay_van_alphaearth/sizes.png',
};

// ---------- icon renderer ----------
async function icon(name, colorHex) {
  const Icon = Fa[name] || Fa.FaCircle;
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Icon, { color: '#' + colorHex, size: 256 })
  );
  const png = await sharp(Buffer.from(svg), { density: 300 })
    .resize(256, 256, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png().toBuffer();
  return 'image/png;base64,' + png.toString('base64');
}

function shadow() { return { type: 'outer', color: '9AA9A0', blur: 8, offset: 3, angle: 90, opacity: 0.35 }; }

(async () => {
  // pre-render icons
  const I = {};
  const need = {
    tree:'FaTree', leaf:'FaLeaf', seed:'FaSeedling', sat:'FaSatelliteDish', radar:'FaBroadcastTower',
    mtn:'FaMountain', ruler:'FaRulerVertical', layers:'FaLayerGroup', grid:'FaBorderAll',
    cluster:'FaProjectDiagram', profile:'FaClipboardList', exp:'FaFileExport', chart:'FaChartBar',
    swap:'FaExchangeAlt', scale:'FaBalanceScale', map:'FaMapMarkedAlt', globe:'FaGlobeAsia',
    warn:'FaExclamationTriangle', check:'FaCheckCircle', q:'FaQuestion', target:'FaBullseye',
    clock:'FaClock', bulb:'FaLightbulb', mask:'FaCloudSunRain', flow:'FaStream', dna:'FaDna',
    search:'FaSearchLocation', poly:'FaDrawPolygon',
  };
  for (const [k, v] of Object.entries(need)) {
    I[k] = { light: await icon(v, 'FFFFFF'), forest: await icon(v, '2C5F2D'),
             amber: await icon(v, 'A9631F'), slate: await icon(v, '3A5561'), mute: await icon(v, '5F6F66') };
  }

  const p = new pptxgen();
  p.layout = 'LAYOUT_WIDE';           // 13.33 x 7.5
  p.defineSlideMaster({ title: 'BASE', background: { color: C.white } });
  const W = 13.33, H = 7.5, M = 0.6;

  // helpers -------------------------------------------------
  const circle = (s, cx, cy, d, fill) =>
    s.addShape(p.ShapeType.ellipse, { x: cx - d/2, y: cy - d/2, w: d, h: d, fill: { color: fill } });
  const iconCircle = (s, cx, cy, d, fill, iconData, pad) => {
    circle(s, cx, cy, d, fill);
    const ip = pad == null ? d * 0.30 : pad;
    s.addImage({ data: iconData, x: cx - (d/2 - ip/2), y: cy - (d/2 - ip/2), w: d - ip, h: d - ip });
  };
  const card = (s, x, y, w, h, fill, line) =>
    s.addShape(p.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.12,
      fill: { color: fill || C.white }, line: line ? { color: line, width: 1 } : { type: 'none' }, shadow: shadow() });
  const kicker = (s, txt, color) =>
    s.addText(txt.toUpperCase(), { x: M, y: 0.5, w: W - 2*M, h: 0.35, fontFace: BF, fontSize: 12.5,
      bold: true, color: color || C.amber, charSpacing: 3, align: 'left' });
  const title = (s, txt, color) =>
    s.addText(txt, { x: M, y: 0.82, w: W - 2*M, h: 0.9, fontFace: HF, fontSize: 32, bold: true,
      color: color || C.ink, align: 'left' });

  // ============================================================ 1. TITLE
  let s = p.addSlide({ masterName: 'BASE' });
  s.background = { color: C.bgDark };
  s.addShape(p.ShapeType.rect, { x: 0, y: 0, w: W, h: H, fill: { color: C.bgDark } });
  // faint motif tree cluster, bottom-right
  s.addImage({ data: I.tree.forest, x: 9.7, y: 2.3, w: 4.6, h: 4.6, transparency: 78 });
  iconCircle(s, 1.15, 1.35, 0.9, C.moss, I.tree.light);
  s.addText('PhD RESEARCH  ·  FOREST REMOTE SENSING', { x: 1.75, y: 1.02, w: 9, h: 0.4,
    fontFace: BF, fontSize: 13, bold: true, color: C.mossLt, charSpacing: 3 });
  s.addText('Forest Management Units', { x: M, y: 2.15, w: 11.5, h: 1.1, fontFace: HF, fontSize: 52,
    bold: true, color: C.white });
  s.addText('Delineating forest stands from satellite time series — and testing whether a learned embedding produces more separable stands than a hand-crafted feature stack',
    { x: M, y: 3.35, w: 10.6, h: 1.1, fontFace: BF, fontSize: 20, color: 'D8E6D2', lineSpacingMultiple: 1.1 });
  // three quick chips
  const chips = [['Unsupervised', I.q], ['Multi-sensor · Earth Engine', I.sat], ['Baseline vs AlphaEarth embedding', I.swap]];
  let cx = M;
  chips.forEach(([t, ic]) => {
    const w = 0.34 + 0.108 * t.length + 0.5;
    s.addShape(p.ShapeType.roundRect, { x: cx, y: 5.15, w, h: 0.62, rectRadius: 0.31,
      fill: { color: '20492F' }, line: { color: C.moss, width: 1 } });
    s.addImage({ data: ic.light, x: cx + 0.2, y: 5.31, w: 0.3, h: 0.3 });
    s.addText(t, { x: cx + 0.55, y: 5.15, w: w - 0.6, h: 0.62, fontFace: BF, fontSize: 13, color: C.white, valign: 'middle' });
    cx += w + 0.25;
  });
  s.addText('Study area: Sanjay Van, Delhi  ·  13.0 km²  ·  window 2017–2022', { x: M, y: 6.55, w: 11, h: 0.4,
    fontFace: BF, fontSize: 13, italic: true, color: 'A9C4A6' });
  s.addNotes('Title. The project: an unsupervised, multi-sensor Google Earth Engine pipeline that delineates forest stands from satellite time series. The experimental twist this deck reports: swap only the feature representation — hand-crafted stack vs the pretrained AlphaEarth embedding — and ask which produces more separable stands. All results are from Sanjay Van, Delhi.');

  // ============================================================ 2. PROBLEM
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'Motivation', C.amber);
  title(s, 'Foresters manage in stands — but stand maps rarely exist');
  const probCards = [
    ['q', 'No labels to learn from', 'There is no field-drawn or operational stand map for most forests. Supervised segmentation has nothing to train against — so the problem is fundamentally unsupervised.'],
    ['leaf', 'One sensor is not enough', 'Canopy structure, phenology and moisture each reveal a different facet of a stand. A single index (e.g. mean NDVI) collapses ecologically distinct areas together.'],
    ['map', 'Pixels aren’t management units', 'Managers act on contiguous stands, not per-pixel classes. Delineation must yield coherent polygons with describable ecological character.'],
  ];
  let px = M;
  const pcw = (W - 2*M - 2*0.4) / 3;
  probCards.forEach(([ic, hd, bd]) => {
    card(s, px, 2.0, pcw, 4.6, C.tint);
    iconCircle(s, px + 0.75, 2.75, 0.85, C.forest, I[ic].light);
    s.addText(hd, { x: px + 0.35, y: 3.35, w: pcw - 0.7, h: 0.85, fontFace: HF, fontSize: 18.5, bold: true, color: C.ink });
    s.addText(bd, { x: px + 0.35, y: 4.25, w: pcw - 0.7, h: 2.1, fontFace: BF, fontSize: 14.5, color: '3E4B44', lineSpacingMultiple: 1.12 });
    px += pcw + 0.4;
  });
  s.addText('FMU treats delineation as unsupervised segmentation of a multi-sensor time series — no labels required.',
    { x: M, y: 6.85, w: W - 2*M, h: 0.4, fontFace: BF, fontSize: 14, italic: true, color: C.forest, bold: true });
  s.addNotes('The motivating gap. Forest management happens at the stand level, but hand-drawn/operational stand maps almost never exist — so we cannot train a supervised model. A single vegetation index is too coarse; structure, phenology and moisture each matter. And managers need coherent polygons, not pixel labels. FMU answers this as unsupervised multi-sensor segmentation.');

  // ============================================================ 3. PIPELINE OVERVIEW
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'What we built', C.forest);
  title(s, 'FMU: a config-driven Earth Engine pipeline, satellite → stands');
  const stages = [
    ['mask','Mask','habitat mask'], ['sat','Load','S2 / S1 / aux'], ['layers','Features','multi-sensor'],
    ['grid','Segment','SNIC superpixels'], ['cluster','Cluster','k-means, k=6'], ['profile','Profile','per-stand stats'],
    ['exp','Export','raster + vectors'], ['chart','Metrics','compare arms'],
  ];
  const n = stages.length, gap = 0.18, cw = (W - 2*M - (n-1)*gap) / n;
  const yTop = 2.55, dia = 0.92;
  stages.forEach((st, i) => {
    const x = M + i * (cw + gap);
    const ccx = x + cw/2;
    card(s, x, yTop, cw, 2.5, C.white, C.line);
    iconCircle(s, ccx, yTop + 0.72, dia, i < 3 ? C.slate : (i < 6 ? C.forest : C.amber), I[st[0]].light);
    s.addText(st[1], { x: x, y: yTop + 1.35, w: cw, h: 0.35, fontFace: HF, fontSize: 14.5, bold: true, color: C.ink, align: 'center' });
    s.addText(st[2], { x: x - 0.05, y: yTop + 1.75, w: cw + 0.1, h: 0.6, fontFace: BF, fontSize: 10.5, color: C.mute, align: 'center', lineSpacingMultiple: 1.0 });
    if (i < n - 1) s.addText('›', { x: x + cw - 0.02, y: yTop + 0.55, w: gap + 0.04, h: 0.4, fontFace: BF, fontSize: 18, bold: true, color: C.moss, align: 'center' });
  });
  // three legend notes
  const legs = [['slate','Inputs & sensors'], ['forest','Delineation core'], ['amber','Analysis & comparison']];
  let lx = M;
  legs.forEach(([col, t]) => {
    circle(s, lx + 0.12, 5.65, 0.24, C[col]);
    s.addText(t, { x: lx + 0.32, y: 5.44, w: 3.3, h: 0.4, fontFace: BF, fontSize: 12.5, color: C.ink, valign: 'middle' });
    lx += 3.7;
  });
  s.addText('Every stage is defined in a Pydantic-validated YAML config and cached as an Earth Engine asset — the whole run is reproducible and re-runs are cheap.',
    { x: M, y: 6.35, w: W - 2*M, h: 0.7, fontFace: BF, fontSize: 14.5, color: '3E4B44', italic: true, lineSpacingMultiple: 1.1 });
  s.addNotes('The pipeline, end to end. Eight stages: mask to the habitat of interest; load Sentinel-2, Sentinel-1 and auxiliary data; build the multi-sensor feature stack; segment into SNIC superpixels; cluster superpixels into k=6 stand types; profile each cluster in real ecological units; export raster + vectors; and compute comparison metrics. It is entirely config-driven and cached in Earth Engine, so runs are reproducible and cheap to repeat.');

  // ============================================================ 4. FEATURE STACK
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'Methodology · 1 of 2', C.forest);
  title(s, 'The hand-crafted feature stack: four sensor families');
  const fams = [
    ['leaf','Optical / phenology','Sentinel-2','NDVI mean, amplitude, phase, trend & residual variance — the seasonal signature of the canopy.'],
    ['radar','Radar / structure-moisture','Sentinel-1','VV & VH backscatter percentiles (p10/p50/p90) and spread — sensitive to structure and moisture, cloud-free.'],
    ['ruler','Canopy structure','GEDI / CHM','Canopy height (mean, max, std) — vertical structure that optical bands cannot see.'],
    ['mtn','Static terrain & climate','DEM / aux','Elevation, slope, aspect, annual rainfall, distance to water — the physical template.'],
  ];
  const fcw = (W - 2*M - 0.4) / 2, fch = 2.05;
  fams.forEach((f, i) => {
    const x = M + (i % 2) * (fcw + 0.4);
    const y = 2.0 + Math.floor(i / 2) * (fch + 0.35);
    card(s, x, y, fcw, fch, C.tint);
    iconCircle(s, x + 0.7, y + 0.68, 0.8, C.forest, I[f[0]].light);
    s.addText(f[1], { x: x + 1.25, y: y + 0.24, w: fcw - 1.5, h: 0.4, fontFace: HF, fontSize: 17, bold: true, color: C.ink });
    s.addText(f[2], { x: x + 1.25, y: y + 0.66, w: fcw - 1.5, h: 0.3, fontFace: BF, fontSize: 12, bold: true, color: C.amberDk });
    s.addText(f[3], { x: x + 0.35, y: y + 1.08, w: fcw - 0.7, h: 0.85, fontFace: BF, fontSize: 13, color: '3E4B44', lineSpacingMultiple: 1.08 });
    px = x;
  });
  s.addText([
    { text: '22 feature bands', options: { bold: true, color: C.forest } },
    { text: '  ·  all reduced over a single unified 2017–2022 window  ·  robust-scaled before clustering', options: { color: '3E4B44' } },
  ], { x: M, y: 6.75, w: W - 2*M, h: 0.4, fontFace: BF, fontSize: 14.5, align: 'center' });
  s.addNotes('The hand-crafted representation. Four sensor families — optical phenology from Sentinel-2, radar from Sentinel-1, canopy structure, and static terrain/climate — combine into a 22-band feature vector, all measured over one unified 2017–2022 window and robust-scaled. This is the "engineered" arm that the learned embedding will be tested against.');

  // ============================================================ 5. SEG -> METRICS
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'Methodology · 2 of 2', C.forest);
  title(s, 'From features to describable, comparable stands');
  const steps = [
    ['grid','Segment — SNIC superpixels','Group pixels into spatially coherent superpixels. Crucially, SNIC uses only composite + structure + radar, so the boundaries are identical across every feature arm — the experiment’s control.'],
    ['cluster','Cluster — weka k-means (k=6)','Cluster superpixel-mean features into 6 stand types with a fixed seed. The chain is band-name-agnostic, so it runs unchanged on 22 hand-crafted bands or 64 embedding dims.'],
    ['profile','Profile — ecological signatures','Summarise every stand in original units (canopy height, NDVI, backscatter…) so a cluster ID becomes a describable forest type.'],
    ['chart','Metrics — compare arms','Silhouette per arm, plus ARI / NMI / Hungarian overlap / agreement map against a reference config — the basis for the whole comparison.'],
  ];
  let sy = 2.0; const rh = 1.16;
  steps.forEach((st, i) => {
    card(s, M, sy, W - 2*M, rh, i % 2 ? C.white : C.tint, i % 2 ? C.line : null);
    iconCircle(s, M + 0.7, sy + rh/2, 0.78, i < 2 ? C.forest : C.amber, I[st[0]].light);
    s.addText(st[1], { x: M + 1.3, y: sy + 0.14, w: W - 2*M - 1.6, h: 0.4, fontFace: HF, fontSize: 16.5, bold: true, color: C.ink });
    s.addText(st[2], { x: M + 1.3, y: sy + 0.52, w: W - 2*M - 1.7, h: 0.6, fontFace: BF, fontSize: 12.5, color: '3E4B44', lineSpacingMultiple: 1.04 });
    sy += rh + 0.16;
  });
  s.addNotes('The downstream half. SNIC segmentation gives spatially coherent superpixels — and because SNIC never sees the clustering feature vector, boundaries are byte-identical across arms, which is what makes the comparison controlled. k-means (k=6, fixed seed) is band-agnostic, so it runs unchanged on either representation. Profiling makes clusters interpretable; metrics produce the silhouette and cross-arm agreement numbers.');

  // ============================================================ 6. EXPERIMENT
  s = p.addSlide({ masterName: 'BASE' });
  s.background = { color: C.bgDark };
  s.addText('THE EXPERIMENT', { x: M, y: 0.6, w: W - 2*M, h: 0.35, fontFace: BF, fontSize: 12.5, bold: true, color: C.mossLt, charSpacing: 3 });
  s.addText('Swap only the feature arm', { x: M, y: 0.98, w: W - 2*M, h: 0.8, fontFace: HF, fontSize: 32, bold: true, color: C.white });
  s.addText('The field has moved from hand-engineering features to clustering pretrained per-pixel embeddings. The falsifiable question:',
    { x: M, y: 1.85, w: 11.8, h: 0.5, fontFace: BF, fontSize: 15.5, color: 'D8E6D2' });
  // question banner
  s.addShape(p.ShapeType.roundRect, { x: M, y: 2.45, w: W - 2*M, h: 0.85, rectRadius: 0.12, fill: { color: '20492F' }, line: { color: C.moss, width: 1 } });
  s.addImage({ data: I.target.light, x: M + 0.3, y: 2.68, w: 0.42, h: 0.42 });
  s.addText('Does a learned embedding produce more-separable stands than the hand-crafted stack — with everything downstream held fixed?',
    { x: M + 0.95, y: 2.45, w: W - 2*M - 1.2, h: 0.85, fontFace: HF, fontSize: 16.5, italic: true, bold: true, color: C.white, valign: 'middle' });
  // two arms + fixed engine — three equal-width cards (colour, not size, marks the shared engine)
  const armY = 3.7, armH = 2.5, cardW = (W - 2*M - 2*0.4) / 3;   // 3.777 each
  const cardX = (i) => M + i * (cardW + 0.4);
  const drawArmCard = (i, fill, circleCol, ic, name, nameCol, sub, subCol, desc, descCol) => {
    const x = cardX(i);
    s.addShape(p.ShapeType.roundRect, { x, y: armY, w: cardW, h: armH, rectRadius: 0.12, fill: { color: fill } });
    iconCircle(s, x + 0.62, armY + 0.62, 0.78, circleCol, ic);
    s.addText(name, { x: x + 1.15, y: armY + 0.3, w: cardW - 1.3, h: 0.38, fontFace: HF, fontSize: 15.5, bold: true, color: nameCol });
    s.addText(sub, { x: x + 1.15, y: armY + 0.7, w: cardW - 1.3, h: 0.3, fontFace: BF, fontSize: 10.8, bold: true, color: subCol });
    s.addText(desc, { x: x + 0.32, y: armY + 1.24, w: cardW - 0.64, h: 1.15, fontFace: BF, fontSize: 12.5, color: descCol, lineSpacingMultiple: 1.1 });
  };
  drawArmCard(0, C.tintS, C.slateDk, I.layers.light, 'Baseline arm', C.ink, '22 hand-crafted bands', C.slateDk,
    'Optical phenology · radar · structure · terrain — engineered by hand.', '3E4B44');
  drawArmCard(1, C.tintA, C.amberDk, I.dna.light, 'AlphaEarth arm', C.ink, '64-D pretrained embedding', C.amberDk,
    'One learned vector per pixel (Google Satellite Embedding), mean over 2017–2022.', '3E4B44');
  drawArmCard(2, C.forest, C.bgDark, I.grid.light, 'Held fixed', C.white, 'same for both arms', 'BFD8B4',
    'Same SNIC boundaries · k = 6 · seed · ROI · window.', 'E7F0E2');
  s.addText('Two arms in, one delineation engine — only the feature vector changes.',
    { x: M, y: 6.55, w: W - 2*M, h: 0.4, fontFace: BF, fontSize: 14, italic: true, color: C.mossLt, align: 'center' });
  s.addNotes('The design. Rather than rebuild anything, we swap only the feature vector: the 22-band hand-crafted stack, or the 64-dimensional pretrained AlphaEarth embedding (mean over 2017–2022). Everything downstream — SNIC boundaries, k=6, seed, ROI, window — is held byte-identical. That isolation is what makes any difference in separability attributable to the representation itself.');

  // ============================================================ 7. CONTROLLED COMPARISON
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'Experimental control', C.amber);
  title(s, 'What changes vs what is held constant');
  // changes card
  card(s, M, 2.0, (W - 2*M - 0.5)/2, 4.4, C.tintA);
  iconCircle(s, M + 0.7, 2.7, 0.8, C.amberDk, I.swap.light);
  s.addText('The one thing we vary', { x: M + 1.25, y: 2.42, w: 4.4, h: 0.55, fontFace: HF, fontSize: 18, bold: true, color: C.ink });
  const varRows = [
    ['Feature vector', '22 hand-crafted bands  →  64-D AlphaEarth embedding'],
    ['Feature semantics', 'Named ecological metrics  →  abstract learned dims A00–A63'],
    ['Feature stages', 'features_optical/static  →  a single features_embedding stage'],
  ];
  let vy = 3.45;
  varRows.forEach(([h2, b]) => {
    s.addText(h2, { x: M + 0.4, y: vy, w: 5.1, h: 0.3, fontFace: BF, fontSize: 13.5, bold: true, color: C.amberDk });
    s.addText(b, { x: M + 0.4, y: vy + 0.32, w: 5.1, h: 0.55, fontFace: BF, fontSize: 12.5, color: '3E4B44', lineSpacingMultiple: 1.05 });
    vy += 0.98;
  });
  // fixed card
  const rx = M + (W - 2*M - 0.5)/2 + 0.5;
  card(s, rx, 2.0, (W - 2*M - 0.5)/2, 4.4, C.tint);
  iconCircle(s, rx + 0.7, 2.7, 0.8, C.forest, I.check.light);
  s.addText('Everything else held constant', { x: rx + 1.25, y: 2.42, w: 4.6, h: 0.55, fontFace: HF, fontSize: 18, bold: true, color: C.ink });
  const fixedRows = [
    'SNIC segmentation — boundaries byte-identical across arms',
    'Cluster count k = 6 and the random seed',
    'Region of interest — Sanjay Van, 13.0 km²',
    'Time window — 2017-01-01 → 2022-12-31',
    'Robust scaling, profiling and metric definitions',
  ];
  s.addText(fixedRows.map((t, i) => ({ text: t, options: { bullet: { code: '2022' }, color: '3E4B44', breakLine: true, paraSpaceAfter: 10 } })),
    { x: rx + 0.4, y: 3.45, w: 5.1, h: 2.8, fontFace: BF, fontSize: 13.5, lineSpacingMultiple: 1.05 });
  s.addText('A clean single-variable experiment: any change in stand separability is attributable to the representation, not the plumbing.',
    { x: M, y: 6.75, w: W - 2*M, h: 0.4, fontFace: BF, fontSize: 14, italic: true, color: C.forest, align: 'center', bold: true });
  s.addNotes('Restating the control explicitly. Only the feature vector — its dimensionality and its semantics — changes. SNIC boundaries, k, seed, ROI, window, scaling and metric definitions are all fixed. This is a single-variable experiment.');

  // ============================================================ 8. NO GROUND TRUTH (dark, honesty)
  s = p.addSlide({ masterName: 'BASE' });
  s.background = { color: C.bgDark };
  s.addImage({ data: I.scale.forest, x: 9.9, y: 3.6, w: 3.5, h: 3.5, transparency: 82 });
  s.addText('THE HARD CONSTRAINT', { x: M, y: 0.6, w: W - 2*M, h: 0.35, fontFace: BF, fontSize: 12.5, bold: true, color: C.amber, charSpacing: 3 });
  s.addText('No ground truth — so we never claim “more correct”', { x: M, y: 0.98, w: W - 2*M, h: 0.8, fontFace: HF, fontSize: 30, bold: true, color: C.white });
  s.addText('There is no field-drawn or operational reference stand map for this forest. External validity — which representation is ecologically “right” — is simply off the table. We bound every claim to three things we can actually measure:',
    { x: M, y: 1.9, w: 8.9, h: 1.0, fontFace: BF, fontSize: 15, color: 'D8E6D2', lineSpacingMultiple: 1.12 });
  const sig = [
    ['target','Internal separation','Silhouette per arm — intrinsic, needs no reference, directly comparable across arms.'],
    ['swap','Cross-representation agreement','ARI · NMI · Hungarian overlap · agreement map — how differently the two arms carve the forest.'],
    ['profile','Interpretability','Do the clusters still describe as forest types? A representation you cannot read is hard to operationalise.'],
  ];
  const scw = (W - 2*M - 2*0.4) / 3;
  let sx = M;
  sig.forEach(([ic, hd, bd], i) => {
    s.addShape(p.ShapeType.roundRect, { x: sx, y: 3.25, w: scw, h: 3.05, rectRadius: 0.12, fill: { color: '20492F' }, line: { color: C.moss, width: 1 } });
    iconCircle(s, sx + 0.7, 3.95, 0.82, C.amber, I[ic].light);
    s.addText(['1','2','3'][i], { x: sx + scw - 0.75, y: 3.38, w: 0.5, h: 0.4, fontFace: HF, fontSize: 20, bold: true, color: C.moss, align: 'right' });
    s.addText(hd, { x: sx + 0.32, y: 4.55, w: scw - 0.6, h: 0.75, fontFace: HF, fontSize: 16.5, bold: true, color: C.white });
    s.addText(bd, { x: sx + 0.32, y: 5.3, w: scw - 0.6, h: 0.95, fontFace: BF, fontSize: 12.5, color: 'C9DCC2', lineSpacingMultiple: 1.08 });
    sx += scw + 0.4;
  });
  s.addText('The contribution is a methods comparison under label scarcity — not a validated map.',
    { x: M, y: 6.55, w: W - 2*M, h: 0.4, fontFace: BF, fontSize: 14.5, italic: true, bold: true, color: C.mossLt, align: 'center' });
  s.addNotes('The most important slide for honesty. No reference stand map exists, so we cannot and do not claim either representation is more ecologically correct. Every result is bounded to three measurable signals: internal separation (silhouette), cross-representation agreement (ARI/NMI/overlap), and interpretability. The contribution is a methods comparison under label scarcity.');

  // ============================================================ 9. RESULT 1 SILHOUETTE
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'Result 1 · Separation', C.amber);
  title(s, 'AlphaEarth separates the stands far better');
  s.addImage({ path: FIG.sil, x: M, y: 1.95, w: 7.7, h: 7.7/2.38, sizing: { type: 'contain', w: 7.7, h: 7.7/2.38 } });
  // big stat callouts on right
  const bx = 8.65, bw = W - M - bx;
  card(s, bx, 1.95, bw, 1.95, C.tintA);
  s.addText('+0.113', { x: bx, y: 2.15, w: bw, h: 0.95, fontFace: HF, fontSize: 46, bold: true, color: C.amberDk, align: 'center' });
  s.addText('AlphaEarth silhouette', { x: bx, y: 3.1, w: bw, h: 0.6, fontFace: BF, fontSize: 14, bold: true, color: C.ink, align: 'center' });
  card(s, bx, 4.1, bw, 1.95, C.tintS);
  s.addText('−0.007', { x: bx, y: 4.3, w: bw, h: 0.95, fontFace: HF, fontSize: 46, bold: true, color: C.slateDk, align: 'center' });
  s.addText('Baseline silhouette', { x: bx, y: 5.25, w: bw, h: 0.6, fontFace: BF, fontSize: 14, bold: true, color: C.ink, align: 'center' });
  s.addText('Silhouette is intrinsic — computed in each arm’s own feature space, so it is directly comparable. Higher = tighter, better-separated stands. The baseline sits essentially at zero (barely separated); the learned embedding is clearly positive.',
    { x: M, y: 5.55, w: 7.7, h: 1.4, fontFace: BF, fontSize: 13.5, color: '3E4B44', lineSpacingMultiple: 1.12 });
  s.addNotes('Headline result. Intrinsic silhouette — a reference-free measure of how tight and well-separated the clusters are — is +0.113 for AlphaEarth versus −0.007 for the hand-crafted baseline. The baseline is essentially at zero: its six stand types barely separate in feature space. The pretrained embedding yields substantially more separable stands. Because silhouette needs no ground truth, this comparison is clean.');

  // ============================================================ 10. RESULT 2 STAND MAPS
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'Result 2 · Delineation', C.amber);
  title(s, 'Same boundaries, different stands');
  const mh = 4.3, mw = mh * 0.76;                    // 3.27
  const mLeftX = 0.85, mRightX = 4.5;               // maps span 0.85–4.12 and 4.5–7.77
  s.addText('Baseline (hand-crafted)', { x: mLeftX - 0.4, y: 1.95, w: mw + 0.8, h: 0.4, fontFace: HF, fontSize: 15.5, bold: true, color: C.slateDk, align: 'center' });
  s.addImage({ path: FIG.mapB, x: mLeftX, y: 2.35, w: mw, h: mh, sizing: { type: 'contain', w: mw, h: mh } });
  s.addText('AlphaEarth (embedding)', { x: mRightX - 0.4, y: 1.95, w: mw + 0.8, h: 0.4, fontFace: HF, fontSize: 15.5, bold: true, color: C.amberDk, align: 'center' });
  s.addImage({ path: FIG.mapA, x: mRightX, y: 2.35, w: mw, h: mh, sizing: { type: 'contain', w: mw, h: mh } });
  // note card on the right — clear of the maps (which end at 7.77)
  const ncx = 8.05, ncw = W - M - ncx;              // 8.05 → 12.73
  card(s, ncx, 2.35, ncw, mh, C.tint);
  s.addText([
    { text: 'Read this carefully', options: { bold: true, fontSize: 15, color: C.forest, breakLine: true, paraSpaceAfter: 12 } },
    { text: 'SNIC boundaries are identical in both panels — only the cluster assignment differs. Colours/IDs are per-arm, so the same colour is a different stand in each map; use the overlap matrix for correspondence.', options: { color: '3E4B44', breakLine: true, paraSpaceAfter: 12 } },
    { text: 'AlphaEarth yields larger, more contiguous stands; the baseline is visibly more fragmented — the visual counterpart of the silhouette gap.', options: { italic: true, color: C.forest, breakLine: false } },
  ], { x: ncx + 0.28, y: 2.6, w: ncw - 0.56, h: mh - 0.5, fontFace: BF, fontSize: 12.8, lineSpacingMultiple: 1.12, valign: 'top' });
  s.addNotes('The delineations, side by side, on identical SNIC boundaries. Note the colours are per-arm — the same colour means different stands across panels, so correspondence comes from the overlap matrix, not colour. Visually, AlphaEarth produces larger, more coherent stands while the baseline is more fragmented and salt-and-pepper — exactly what the higher silhouette predicts.');

  // ============================================================ 11. RESULT 3 AGREEMENT
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'Result 3 · Agreement', C.amber);
  title(s, 'The two representations delineate quite differently');
  s.addImage({ path: FIG.conf, x: M, y: 2.0, w: 4.4*0.93, h: 4.4, sizing: { type: 'contain', w: 4.4*0.93, h: 4.4 } });
  const stat3 = [['0.17','ARI','vs baseline'], ['0.23','NMI','vs baseline'], ['41%','Agreement','of pixels align']];
  const s3x = 5.5, s3w = (W - M - s3x - 2*0.35) / 3;
  stat3.forEach(([v, l, sub], i) => {
    const x = s3x + i * (s3w + 0.35);
    card(s, x, 2.0, s3w, 1.85, C.tintS);
    s.addText(v, { x, y: 2.15, w: s3w, h: 0.85, fontFace: HF, fontSize: 34, bold: true, color: C.slateDk, align: 'center' });
    s.addText(l, { x, y: 3.0, w: s3w, h: 0.35, fontFace: BF, fontSize: 13.5, bold: true, color: C.ink, align: 'center' });
    s.addText(sub, { x, y: 3.35, w: s3w, h: 0.35, fontFace: BF, fontSize: 11, color: C.mute, align: 'center' });
  });
  card(s, s3x, 4.1, W - M - s3x, 2.4, C.tint);
  s.addText('What this means', { x: s3x + 0.35, y: 4.3, w: W - M - s3x - 0.7, h: 0.4, fontFace: HF, fontSize: 16, bold: true, color: C.forest });
  s.addText([
    { text: 'Low-to-moderate agreement. ', options: { bold: true, color: C.ink } },
    { text: 'After Hungarian alignment, only ~41% of pixels land in corresponding stands (ARI 0.17, NMI 0.23). The green rings on the matrix show each AlphaEarth stand’s best-matching baseline stand — some map cleanly (73%, 49%, 48%), others split across several. Neither arm is a reference; this simply quantifies how much the representation reshapes the map.',
      options: { color: '3E4B44' } },
  ], { x: s3x + 0.35, y: 4.75, w: W - M - s3x - 0.7, h: 1.6, fontFace: BF, fontSize: 13, lineSpacingMultiple: 1.14 });
  s.addNotes('Agreement between arms. ARI 0.17, NMI 0.23, and about 41% of pixels in corresponding stands after Hungarian alignment — low to moderate. The confusion matrix green rings show best matches: a few stands correspond strongly (73, 49, 48%), others fragment. The point is not that one is right; it is that switching representation substantially reshapes the delineation.');

  // ============================================================ 12. RESULT 4 CONFIDENCE
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'Result 4 · Consensus layer', C.amber);
  title(s, 'A per-stand confidence layer — consensus, not correctness');
  s.addImage({ path: FIG.confid, x: M, y: 2.1, w: 7.6, h: 7.6/2.61, sizing: { type: 'contain', w: 7.6, h: 7.6/2.61 } });
  const cbx = 8.6, cbw = W - M - cbx;
  card(s, cbx, 2.05, cbw, 1.7, C.tintA);
  s.addText('40%', { x: cbx, y: 2.15, w: cbw, h: 0.85, fontFace: HF, fontSize: 40, bold: true, color: C.amberDk, align: 'center' });
  s.addText('mean stand confidence', { x: cbx, y: 3.0, w: cbw, h: 0.5, fontFace: BF, fontSize: 13, bold: true, color: C.ink, align: 'center' });
  card(s, cbx, 3.9, cbw, 1.7, C.tint);
  s.addText('33%', { x: cbx, y: 4.0, w: cbw, h: 0.85, fontFace: HF, fontSize: 40, bold: true, color: C.forest, align: 'center' });
  s.addText('of area ≥ 80% agreement', { x: cbx, y: 4.85, w: cbw, h: 0.5, fontFace: BF, fontSize: 13, bold: true, color: C.ink, align: 'center' });
  s.addText('We roll the pixel agreement map up to each SNIC stand: confidence = how often the two representations place that stand in corresponding classes. It is a stability / uncertainty layer a forester can act on — high-confidence stands are robust to the choice of representation — explicitly not a correctness score.',
    { x: M, y: 5.35, w: 7.6, h: 1.7, fontFace: BF, fontSize: 13.5, color: '3E4B44', lineSpacingMultiple: 1.14 });
  s.addNotes('A practical by-product. We aggregate the per-pixel agreement map to each stand, giving a confidence value: mean 40%, with 33% of the area at 80%+ agreement. Framed honestly as consensus/stability between the two representations — where they agree, the stand is robust to the modelling choice — not as a measure of correctness, which would need ground truth we do not have.');

  // ============================================================ 13. INTERPRETABILITY TRADE-OFF
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'The trade-off', C.forest);
  title(s, 'Separability comes at the cost of interpretability');
  const halfW = (W - 2*M - 0.5) / 2;
  card(s, M, 2.0, halfW, 4.3, C.tintS);
  iconCircle(s, M + 0.7, 2.7, 0.8, C.slateDk, I.leaf.light);
  s.addText('Baseline — readable', { x: M + 1.25, y: 2.45, w: halfW - 1.5, h: 0.5, fontFace: HF, fontSize: 18, bold: true, color: C.ink });
  s.addText('Clusters profile in real ecological units:', { x: M + 0.35, y: 3.35, w: halfW - 0.7, h: 0.35, fontFace: BF, fontSize: 12.5, italic: true, color: C.slateDk });
  s.addText(['canopy height & vertical structure', 'NDVI mean, amplitude & phenological phase', 'VV / VH radar backscatter', 'elevation, slope, rainfall']
      .map(t => ({ text: t, options: { bullet: { code: '2022' }, breakLine: true, paraSpaceAfter: 8, color: '3E4B44' } })),
    { x: M + 0.4, y: 3.75, w: halfW - 0.8, h: 2.0, fontFace: BF, fontSize: 13.5 });
  s.addText('→ “Stand 3 is short, sparse canopy on a dry slope.”', { x: M + 0.35, y: 5.75, w: halfW - 0.7, h: 0.45, fontFace: BF, fontSize: 12.5, italic: true, bold: true, color: C.slateDk });
  const r2x = M + halfW + 0.5;
  card(s, r2x, 2.0, halfW, 4.3, C.tintA);
  iconCircle(s, r2x + 0.7, 2.7, 0.8, C.amberDk, I.dna.light);
  s.addText('AlphaEarth — abstract', { x: r2x + 1.25, y: 2.45, w: halfW - 1.5, h: 0.5, fontFace: HF, fontSize: 18, bold: true, color: C.ink });
  s.addText('Clusters profile in 64 learned dimensions:', { x: r2x + 0.35, y: 3.35, w: halfW - 0.7, h: 0.35, fontFace: BF, fontSize: 12.5, italic: true, color: C.amberDk });
  s.addText(['A00, A01, A02 … A63 — no physical units', 'more separable, but not directly nameable', 'ecological meaning must be recovered post-hoc', 'e.g. cross-walk each dim back to profiles']
      .map(t => ({ text: t, options: { bullet: { code: '2022' }, breakLine: true, paraSpaceAfter: 8, color: '3E4B44' } })),
    { x: r2x + 0.4, y: 3.75, w: halfW - 0.8, h: 2.0, fontFace: BF, fontSize: 13.5 });
  s.addText('→ “Stand 3 is high on A17, low on A40.” — separable, not self-explaining.', { x: r2x + 0.35, y: 5.75, w: halfW - 0.7, h: 0.45, fontFace: BF, fontSize: 12.5, italic: true, bold: true, color: C.amberDk });
  s.addNotes('The honest trade-off. The hand-crafted baseline produces clusters you can read in ecological units — canopy height, phenology, backscatter — so a stand is describable. The AlphaEarth embedding is more separable but its 64 dimensions are abstract (A00–A63); ecological meaning has to be recovered after the fact. Separability versus interpretability is the real tension for operational use.');

  // ============================================================ 14. TESSERA (intro only)
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'Intended third arm', C.amber);
  title(s, 'Tessera — attempted, not completed');
  card(s, M, 2.0, 5.7, 4.5, C.tint);
  iconCircle(s, M + 0.7, 2.7, 0.8, C.forest, I.globe.light);
  s.addText('What it is & why', { x: M + 1.25, y: 2.45, w: 4.2, h: 0.5, fontFace: HF, fontSize: 17, bold: true, color: C.ink });
  s.addText([
    'A second pretrained, per-pixel embedding (open, CC0) — off-GEE, so it must be fetched and ingested as an Earth Engine asset.',
    'Goal: a second learned representation, for a three-way comparison (hand-crafted vs AlphaEarth vs Tessera).',
    'The pipeline is already source-agnostic: the features_embedding stage loads either embedding unchanged.',
  ].map(t => ({ text: t, options: { bullet: { code: '2022' }, breakLine: true, paraSpaceAfter: 10, color: '3E4B44' } })),
    { x: M + 0.4, y: 3.35, w: 5.0, h: 3.0, fontFace: BF, fontSize: 13, lineSpacingMultiple: 1.08 });
  card(s, M + 6.0, 2.0, W - M - (M + 6.0), 4.5, C.tintA);
  iconCircle(s, M + 6.0 + 0.7, 2.7, 0.8, C.amberDk, I.warn.light);
  s.addText('Why it is blocked', { x: M + 6.0 + 1.25, y: 2.45, w: 4.5, h: 0.5, fontFace: HF, fontSize: 17, bold: true, color: C.ink });
  s.addText([
    'Coverage: for the Delhi ROI, Tessera publishes tiles only for 2024–2025 — a temporal mismatch with AlphaEarth’s 2017–2022 window.',
    'Ingestion: the installed geotessera (0.9.0) reports a covering tile but writes no GeoTIFF, so the mosaic step fails — an API/version gap in the fetch.',
    'Status: scaffolding is in place (prep_tessera.py, config, source-agnostic stage); a clean run needs a fixed fetch + a stated window caveat.',
  ].map(t => ({ text: t, options: { bullet: { code: '2022' }, breakLine: true, paraSpaceAfter: 10, color: '3E4B44' } })),
    { x: M + 6.0 + 0.4, y: 3.35, w: (W - M - (M + 6.0)) - 0.8, h: 3.0, fontFace: BF, fontSize: 13, lineSpacingMultiple: 1.08 });
  s.addText('Reported transparently: the third arm is future work, not a result.',
    { x: M, y: 6.75, w: W - 2*M, h: 0.4, fontFace: BF, fontSize: 14, italic: true, bold: true, color: C.forest, align: 'center' });
  s.addNotes('Tessera was meant to be the third arm — a second open pretrained embedding, giving a three-way comparison. Two things blocked it: for this Delhi ROI Tessera only covers 2024–2025 (a window mismatch with AlphaEarth), and the installed geotessera 0.9.0 reports a covering tile but exports no GeoTIFF, breaking ingestion. The scaffolding exists and the stage is source-agnostic, so it is well-defined future work — reported honestly as attempted, not a result.');

  // ============================================================ 15. LIMITATIONS
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'Limitations', C.amber);
  title(s, 'What these results do — and do not — support');
  const lims = [
    ['scale','No external validity','With no reference stand map, we compare representations (separation + agreement), never correctness.'],
    ['map','Single site','All numbers are from one ROI — Sanjay Van, Delhi. Generalisation needs more, varied forests.'],
    ['clock','Tessera window gap','The only Tessera coverage (2024–25) does not match AlphaEarth’s 2017–22 — a confound to resolve.'],
    ['target','One metric family','Silhouette is a single intrinsic measure; k=6 is fixed, not optimised per arm.'],
    ['dna','Embedding opacity','AlphaEarth’s gain in separability comes with abstract, not-yet-interpreted dimensions.'],
    ['q','Agreement ≠ truth','Low ARI tells us the arms differ, not which (if either) is ecologically better.'],
  ];
  const lcw = (W - 2*M - 2*0.4) / 3, lch = 1.9;
  lims.forEach((l, i) => {
    const x = M + (i % 3) * (lcw + 0.4);
    const y = 2.0 + Math.floor(i / 3) * (lch + 0.35);
    card(s, x, y, lcw, lch, i % 2 ? C.white : C.tint, i % 2 ? C.line : null);
    iconCircle(s, x + 0.6, y + 0.6, 0.68, C.amber, I[l[0]].light);
    s.addText(l[1], { x: x + 1.1, y: y + 0.28, w: lcw - 1.3, h: 0.6, fontFace: HF, fontSize: 14.5, bold: true, color: C.ink });
    s.addText(l[2], { x: x + 0.32, y: y + 0.95, w: lcw - 0.6, h: 0.85, fontFace: BF, fontSize: 11.8, color: '3E4B44', lineSpacingMultiple: 1.06 });
  });
  s.addNotes('Stated limitations. No ground truth means no correctness claim. All figures are from a single ROI. The Tessera window gap is a real confound. Silhouette is one metric and k is fixed. The embedding’s separability advantage comes with opacity. And low agreement between arms tells us they differ, not which is better. These frame the scope honestly.');

  // ============================================================ 16. CONCLUSIONS
  s = p.addSlide({ masterName: 'BASE' });
  kicker(s, 'Conclusions', C.forest);
  title(s, 'What we can say');
  const cc = [
    ['check','A working, reproducible pipeline','FMU delineates forest stands from a multi-sensor time series, fully unsupervised, config-driven and cached in Earth Engine — baseline and embedding arms both run end-to-end to HTML reports.'],
    ['chart','The learned embedding separates better','With everything downstream held fixed, AlphaEarth lifts intrinsic silhouette from −0.007 to +0.113 and yields more coherent stands — but agrees with the baseline only ~41% (ARI 0.17), so it delineates differently and trades away interpretability.'],
    ['scale','A methods comparison under label scarcity','The contribution is a controlled representation comparison plus a per-stand consensus/confidence layer — honest about the absence of ground truth, not a claim that either map is “correct.”'],
  ];
  let ccy = 2.0; const cch = 1.45;
  cc.forEach(([ic, hd, bd], i) => {
    card(s, M, ccy, W - 2*M, cch, i === 1 ? C.tintA : C.tint);
    iconCircle(s, M + 0.8, ccy + cch/2, 0.9, i === 1 ? C.amberDk : C.forest, I[ic].light);
    s.addText([{ text: (i+1) + '.  ', options: { bold: true, color: i===1?C.amberDk:C.forest } }, { text: hd, options: { bold: true, color: C.ink } }],
      { x: M + 1.55, y: ccy + 0.18, w: W - 2*M - 1.9, h: 0.4, fontFace: HF, fontSize: 17 });
    s.addText(bd, { x: M + 1.55, y: ccy + 0.58, w: W - 2*M - 1.9, h: 0.8, fontFace: BF, fontSize: 13, color: '3E4B44', lineSpacingMultiple: 1.08 });
    ccy += cch + 0.2;
  });
  s.addNotes('Three conclusions. One: a reproducible, unsupervised, multi-sensor delineation pipeline that runs both arms to finished reports. Two: with a clean control, the pretrained AlphaEarth embedding produces more separable and more coherent stands (silhouette −0.007 → +0.113), but agrees with the baseline only ~41% and sacrifices interpretability. Three: framed honestly as a methods comparison under label scarcity, with a consensus/confidence layer — never a correctness claim.');

  // ============================================================ 17. FUTURE / CLOSING (dark)
  s = p.addSlide({ masterName: 'BASE' });
  s.background = { color: C.bgDark };
  s.addImage({ data: I.tree.forest, x: 10.0, y: 3.4, w: 3.6, h: 3.6, transparency: 82 });
  s.addText('NEXT', { x: M, y: 0.6, w: 6, h: 0.35, fontFace: BF, fontSize: 12.5, bold: true, color: C.amber, charSpacing: 3 });
  s.addText('Where this goes next', { x: M, y: 0.98, w: 11, h: 0.8, fontFace: HF, fontSize: 30, bold: true, color: C.white });
  const fut = [
    ['globe','Finish the Tessera arm','fix geotessera ingestion; run 2024–25 with a stated window caveat → the full three-way comparison.'],
    ['map','Multiple sites','repeat across varied forests to test whether the separability gain generalises.'],
    ['search','Seek any reference','even partial field or expert labels would unlock a first external-validity check.'],
    ['dna','Interpret & hybridise','cross-walk embedding dims back to ecology; test a hand-crafted + embedding hybrid; sweep k.'],
  ];
  let fy = 2.08; const frh = 0.88;
  fut.forEach(([ic, hd, bd]) => {
    s.addShape(p.ShapeType.roundRect, { x: M, y: fy, w: 8.9, h: frh, rectRadius: 0.1, fill: { color: '20492F' } });
    iconCircle(s, M + 0.6, fy + frh/2, 0.62, C.amber, I[ic].light);
    s.addText([{ text: hd + ' — ', options: { bold: true, color: C.white } }, { text: bd, options: { color: 'C9DCC2' } }],
      { x: M + 1.15, y: fy, w: 7.6, h: frh, fontFace: BF, fontSize: 13, valign: 'middle', lineSpacingMultiple: 1.03 });
    fy += frh + 0.13;
  });
  s.addShape(p.ShapeType.line, { x: M, y: 6.12, w: 8.9, h: 0, line: { color: '355643', width: 1 } });
  s.addText([
    { text: 'Bottom line:  ', options: { bold: true, color: C.mossLt } },
    { text: 'a controlled swap shows the learned embedding separates stands better (+0.113 vs −0.007) — a methods result under label scarcity, honestly bounded.', options: { color: 'D8E6D2', italic: true } },
  ], { x: M, y: 6.26, w: 11.8, h: 0.7, fontFace: BF, fontSize: 14, lineSpacingMultiple: 1.1 });
  s.addNotes('Future work and close. Finish Tessera for the three-way comparison; test generalisation across multiple sites; seek any reference for a first external-validity check; and interpret or hybridise the embedding while sweeping k. Bottom line: a controlled swap shows the learned embedding separates stands better — a methods result under label scarcity, stated honestly.');

  const OUT = REPO + '/FMU_deck.pptx';
  await p.writeFile({ fileName: OUT });
  console.log('WROTE', OUT);
})().catch(e => { console.error('BUILD ERROR:', e); process.exit(1); });
