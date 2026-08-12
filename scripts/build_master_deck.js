/*
 * FMU MASTER DECK — consolidated from all deck versions, reconciled against the code.
 * 53 slides: full v3.1 methodology (11 stages + feature selection) + both swap experiments
 * (C-0 optical variant, C-1 AlphaEarth) with real figures + gaps/SVH/roadmap + refs + glossary.
 *
 * Deps (not part of the Python package): npm install pptxgenjs
 * Run from the repo root: node scripts/build_master_deck.js
 * (reads figures from reports/sanjay_van_baseline, reports/comparison_*_nirv_dual_*, reports/multi_*).
 */
const path = require('path');
const pptxgen = require('pptxgenjs');
const REPO = path.resolve(__dirname, '..');
const B  = REPO + '/reports/sanjay_van_baseline';
const C0 = REPO + '/reports/comparison_sanjay_van_nirv_dual_vs_sanjay_van_baseline';
const M  = REPO + '/reports/multi_sanjay_van_baseline';
const FIG = {
  sep: B + '/separating_power.png', mapBase: B + '/stand_map.png', fp: B + '/fingerprint.png',
  phen: B + '/phenology.png', sig: B + '/signatures.png', sizesBase: B + '/sizes.png',
  c0conf: C0 + '/confusion.png', mapVar: C0 + '/_sanjay_van_nirv_dual/stand_map.png',
  sil: M + '/silhouette_bars.png', mapB: M + '/_sanjay_van_baseline/stand_map.png',
  mapA: M + '/_sanjay_van_alphaearth/stand_map.png', conf: M + '/_sanjay_van_alphaearth/confusion.png',
  confid: M + '/_sanjay_van_alphaearth/confidence.png',
};

const INK='1A1A1A', GREEN='2C5F2D', GREEN2='4E7350', MUTE='5F6F66', TINT='EEF3E9', RULE='CBD8C4', LINE='1A1A1A', AMBER='A9631F';
const HF='Cambria', BF='Calibri';
const W=13.33, Hh=7.5, MG=0.62;

const p = new pptxgen();
p.layout='LAYOUT_WIDE';
p.defineSlideMaster({ title:'W', background:{color:'FFFFFF'} });

let SN = 0;
function S(){ SN++; return p.addSlide({masterName:'W'}); }
function foot(s, label){
  s.addText([{text:'FMU · Forest Monitoring Units',options:{color:MUTE}},{text:'      '+label,options:{color:GREEN2}}],
    {x:MG, y:Hh-0.42, w:W-2*MG, h:0.3, fontFace:BF, fontSize:9, align:'left'});
  s.addText(String(SN), {x:W-1.1, y:Hh-0.42, w:0.5, h:0.3, fontFace:BF, fontSize:9, color:MUTE, align:'right'});
}
function kicker(s,t){ s.addText(t.toUpperCase(),{x:MG,y:0.34,w:W-2*MG,h:0.3,fontFace:BF,fontSize:11,bold:true,color:GREEN,charSpacing:2}); }
function title(s,t,sz){ s.addText(t,{x:MG,y:0.66,w:W-2*MG,h:0.8,fontFace:HF,fontSize:sz||23,bold:true,color:INK}); }
function rule(s,y){ s.addShape(p.ShapeType.line,{x:MG,y:y||1.5,w:W-2*MG,h:0,line:{color:RULE,width:1}}); }
function bullets(s,items,o){o=o||{}; const x=o.x||MG,y=o.y||1.75,w=o.w||(W-2*MG),h=o.h||5.0,fs=o.fs||15.5,gap=o.gap==null?11:o.gap;
  s.addText(items.map(it=>{const sub=typeof it==='object'&&it.sub; return {text:typeof it==='string'?it:it.t,
    options:{bullet:sub?{indent:16}:{code:'2022'},indentLevel:sub?1:0,color:o.color||INK,breakLine:true,paraSpaceAfter:gap,fontSize:fs,bold:typeof it==='object'&&it.b}};}),
    {x,y,w,h,fontFace:BF,valign:'top',lineSpacingMultiple:1.03}); }
function img(s,path,x,y,w,h){ s.addImage({path,x,y,w,h,sizing:{type:'contain',w,h}}); }
function cap(s,t,x,y,w){ s.addText(t,{x,y,w,h:0.5,fontFace:BF,fontSize:11,italic:true,color:MUTE}); }
function note(s,t){ s.addText(t,{x:MG,y:Hh-0.95,w:W-2*MG,h:0.5,fontFace:BF,fontSize:12,italic:true,color:GREEN2}); }
function arrowR(s,x,y,w){ s.addShape(p.ShapeType.line,{x,y,w,h:0,line:{color:LINE,width:1.5,endArrowType:'triangle'}}); }
function divider(s,section,big,sub){
  s.background={color:GREEN};
  s.addText(section.toUpperCase(),{x:MG,y:2.5,w:W-2*MG,h:0.4,fontFace:BF,fontSize:13,bold:true,color:'BFE0B8',charSpacing:3});
  s.addText(big,{x:MG,y:3.0,w:W-2*MG,h:1.1,fontFace:HF,fontSize:32,bold:true,color:'FFFFFF'});
  if(sub) s.addText(sub,{x:MG,y:4.2,w:W-2.0,h:0.8,fontFace:BF,fontSize:15,color:'DDEBD8'});
}
function tbl(s,rows,o){ // rows: array of arrays of strings; first row = header
  const x=o.x||MG,y=o.y,w=o.w||(W-2*MG),fs=o.fs||12.5;
  const body=rows.map((r,ri)=>r.map(c=>({text:String(c),options:{
    fill:{color: ri===0?GREEN:(ri%2? 'FFFFFF':'F4F8F1')},
    color: ri===0?'FFFFFF':INK, bold: ri===0, fontFace:BF, fontSize:fs, align:'left', valign:'middle',
    margin:[3,5,3,5]}})));
  s.addTable(body,{x,y,w,colW:o.colW,rowH:o.rowH||0.32,border:{type:'solid',color:RULE,pt:0.5},autoPage:false});
}
function chip(s,x,y,w,txt,fill,col){ s.addShape(p.ShapeType.roundRect,{x,y,w,h:0.5,rectRadius:0.08,fill:{color:fill||TINT},line:{color:RULE,width:0.75}});
  s.addText(txt,{x:x+0.1,y,w:w-0.2,h:0.5,fontFace:BF,fontSize:12.5,bold:true,color:col||INK,align:'center',valign:'middle'}); }
let s;

/* ===== 1 TITLE ===== */
s=S(); s.background={color:GREEN};
s.addText('METHODOLOGY · EXPERIMENTS · RESULTS · GAPS',{x:MG,y:1.5,w:W-2*MG,h:0.4,fontFace:BF,fontSize:13,bold:true,color:'BFE0B8',charSpacing:3});
s.addText('Forest Monitoring Units (FMU)',{x:MG,y:2.15,w:W-2*MG,h:1.0,fontFace:HF,fontSize:44,bold:true,color:'FFFFFF'});
s.addText('An unsupervised, multi-sensor framework for delineating forest stands from satellite time series — built end to end on Google Earth Engine.',
  {x:MG,y:3.35,w:11.4,h:0.9,fontFace:BF,fontSize:18,color:'DDEBD8',lineSpacingMultiple:1.1});
s.addText([{text:'Consolidated master deck',options:{bold:true,color:'FFFFFF'}},{text:'  —  methodology (v3.1) + feature selection + two swap experiments (optical variant & AlphaEarth) + gaps, SVH test and roadmap. Every claim reconciled against the code.',options:{color:'C9DFC2'}}],
  {x:MG,y:4.9,w:11.6,h:0.9,fontFace:BF,fontSize:14,lineSpacingMultiple:1.1});
s.addText('Jaskaran Singh   ·   Study areas: Sanjay Van, Delhi (13.0 km²) · Mudumalai (intended primary)   ·   window 2017–2022',
  {x:MG,y:6.4,w:W-2*MG,h:0.4,fontFace:BF,fontSize:12.5,italic:true,color:'A9C4A6'});

/* ===== 2 WHY ===== */
s=S(); kicker(s,'Motivation'); title(s,'Drawing forest stands at scale, without labels'); rule(s);
s.addText('A stand is a patch of forest internally similar in species mix, structure and condition — and different from its neighbours. Foresters work in stands; the problem is drawing them repeatably, at scale, without hand-digitising.',
  {x:MG,y:1.65,w:W-2*MG,h:0.7,fontFace:BF,fontSize:14.5,color:INK,italic:true});
const pil=[['Unsupervised','No wall-to-wall label layer exists for Indian forest stand types. Supervised classification needs labels we don’t have — so let the data define the strata.'],
 ['Multi-sensor','No single sensor captures a stand: optical carries phenology; radar carries structure/moisture and sees through cloud; canopy height carries vertical structure; terrain is the physical template.'],
 ['Where it points','Stand units are candidates for spectral/structural communities — the unit behind the Spectral Variation Hypothesis. A destination for biodiversity monitoring, not a finished result.']];
let px=MG; const pw=(W-2*MG-2*0.35)/3;
pil.forEach(([h,b])=>{ s.addShape(p.ShapeType.roundRect,{x:px,y:2.5,w:pw,h:3.6,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
  s.addText(h,{x:px+0.28,y:2.75,w:pw-0.5,h:0.5,fontFace:HF,fontSize:17,bold:true,color:GREEN});
  s.addText(b,{x:px+0.28,y:3.35,w:pw-0.56,h:2.6,fontFace:BF,fontSize:13.5,color:INK,lineSpacingMultiple:1.1}); px+=pw+0.35; });
note(s,'The pipeline does not measure biodiversity — it produces ecologically structured units that are the right input to an SVH/HVH analysis.'); foot(s,'Motivation');

/* ===== 3 HONEST CONSTRAINT ===== */
s=S(); kicker(s,'Read this first'); title(s,'The honest constraint: there is no ground truth'); rule(s);
s.addText('No field-drawn or operational reference stand map exists for these forests.',{x:MG,y:1.7,w:W-2*MG,h:0.5,fontFace:HF,fontSize:18,bold:true,color:INK});
bullets(s,[
 'So nothing in this deck is validated as ecologically "correct" — that claim needs a reference we do not have.',
 'Every result is bounded to what we CAN measure: internal separation (silhouette), cross-representation agreement (ARI/NMI/overlap), consensus/confidence, and interpretability.',
 'This is a field-wide condition, not a personal one — it is exactly where the contribution lies (see Gaps & Roadmap).',
 'The whole deck is framed this way: a methods comparison under label scarcity, not a validated map.',
],{y:2.4,gap:14,fs:15.5}); foot(s,'Framing');

/* ===== 4 PIPELINE OVERVIEW ===== */
s=S(); kicker(s,'Overview'); title(s,'The pipeline at a glance — 11 stages'); rule(s);
const st=['1 mask','2 load','3 optical','4 radar','5 structure','6 static','7 SNIC','8 k-means','9 profile','10 export','11 metrics'];
// two rows of arrows
let rowY=[2.5,4.0], perRow=6;
st.forEach((v,i)=>{ const row=i<perRow?0:1; const idx=i%perRow; const cw=(W-2*MG)/perRow; const x=MG+idx*cw;
  chip(s,x+0.05,rowY[row],cw-0.2,v, row===0?(i<2?'E7EEE9':'EEF3E9'):'EEF3E9');
  if(idx<perRow-1 && i<st.length-1) arrowR(s,x+cw-0.16,rowY[row]+0.25,0.14); });
s.addText('Stages 1–6 build the multi-sensor feature stack · 7 turns pixels into objects (superpixels) · 8 assigns clusters · 9–11 describe, export and evaluate.',
  {x:MG,y:5.1,w:W-2*MG,h:0.6,fontFace:BF,fontSize:14.5,color:INK,italic:true});
bullets(s,[
 {t:'Config-driven: every stage is a Pydantic-validated YAML config, cached as an Earth Engine asset — the whole run is reproducible and cheap to re-run.'},
],{y:5.75,gap:8,fs:13.5}); foot(s,'Overview');

/* ===== 5 DATA INVENTORY ===== */
s=S(); kicker(s,'Data'); title(s,'Everything is free, global, and on one platform'); rule(s);
tbl(s,[
 ['Layer','Source','Used for'],
 ['Optical surface reflectance','Sentinel-2 (harmonized SR)','Phenology (NDVI / NIRv)'],
 ['C-band SAR backscatter','Sentinel-1 GRD (dB)','Structure / moisture'],
 ['Canopy height','ETH Global Canopy Height, 10 m','Vertical structure'],
 ['Terrain','NASADEM (SRTM lineage)','Elevation, slope, aspect'],
 ['Surface water','JRC Global Surface Water','Distance to water'],
 ['Rainfall','CHIRPS','Climate context'],
 ['Habitat mask — primary','IndiaSAT LULC · CoRE Stack LULC_v4','Restrict to forest / shrub'],
 ['Habitat mask — fallback','ESA WorldCover 10 m v200','Restrict to forest / shrub'],
 ['Compute platform','Google Earth Engine','The whole pipeline'],
],{y:1.7,colW:[3.9,4.6,3.6],rowH:0.42,fs:12.5}); foot(s,'Data');

/* ===== 6 STAGE 1 MASKING concept ===== */
s=S(); kicker(s,'Stage 1 · Masking'); title(s,'Make the clustering question well-posed'); rule(s);
s.addText('Cluster only what is actually forest or shrub. Leave cropland, built-up, water and bare ground in, and the clusterer spends its budget separating tree from parking lot — instead of one forest type from another.',
 {x:MG,y:1.7,w:W-2*MG,h:0.9,fontFace:BF,fontSize:15,color:INK});
s.addShape(p.ShapeType.roundRect,{x:MG,y:2.8,w:5.7,h:2.2,rectRadius:0.1,fill:{color:'F7ECEC'},line:{color:'E3C9C9',width:0.75}});
s.addText('Without masking',{x:MG+0.3,y:3.0,w:5,h:0.4,fontFace:HF,fontSize:16,bold:true,color:AMBER});
s.addText('Clusters split by land use — forest vs road vs field.',{x:MG+0.3,y:3.5,w:5.1,h:1.2,fontFace:BF,fontSize:14,color:INK});
s.addShape(p.ShapeType.roundRect,{x:MG+6.2,y:2.8,w:5.7,h:2.2,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
s.addText('Habitat only',{x:MG+6.5,y:3.0,w:5,h:0.4,fontFace:HF,fontSize:16,bold:true,color:GREEN});
s.addText('Clusters split by forest type — the question we actually want answered.',{x:MG+6.5,y:3.5,w:5.1,h:1.2,fontFace:BF,fontSize:14,color:INK});
note(s,'One binary mask, applied once, up front. Everything downstream runs inside it.'); foot(s,'Stage 1 · Masking');

/* ===== 7 STAGE 1 IndiaSAT ===== */
s=S(); kicker(s,'Stage 1 · Masking'); title(s,'Habitat = IndiaSAT trees + shrubs'); rule(s);
tbl(s,[['Value','IndiaSAT class'],['6','Trees · HABITAT'],['12','Shrubs / Scrubs · HABITAT'],['1','Built-up'],['2–4','Water (seasonal)'],['5, 8–11','Crops (by intensity)'],['7','Barren'],['0','Background']],
 {x:MG,y:1.7,w:4.6,colW:[1.2,3.4],rowH:0.36,fs:12});
bullets(s,[
 {t:'Primary: CoRE Stack LULC_v4 (annual 30 m maps, band predicted_label) — the openly-readable form of IndiaSAT. Classes 6 + 12 kept; all else excluded.',b:false},
 'Fallback: ESA WorldCover v200 classes 10/20/30 (tree/shrub/grassland), only where IndiaSAT is unavailable.',
 'Single phase: no separate water mask — water is dropped because its classes aren’t in the habitat set. JRC water is used later for distance, not masking.',
 'Across annual maps (2017–2021) each pixel’s habitat is a majority vote over usable years; ties go to the most recent usable year.',
],{x:5.5,y:1.75,w:W-MG-5.5,gap:12,fs:13.5});
note(s,'Change from older code: the old WorldCover + JRC water + Open Buildings + VIIRS three-phase mask is superseded by IndiaSAT-first, single phase (fixes mode collapse).'); foot(s,'Stage 1 · Masking');

/* ===== 8 STAGE 2 DATA LOAD ===== */
s=S(); kicker(s,'Stage 2 · Data loading'); title(s,'Pull, composite, and align every sensor'); rule(s);
bullets(s,[
 'Sentinel-2 — harmonized SR, cloud-masked, composited; feeds NDVI (baseline) or NIRv (variant).',
 'Sentinel-1 — GRD, already in decibels; ASCENDING orbits only.',
 'ETH canopy height, NASADEM — single static rasters. JRC water & CHIRPS — for the static-feature stage.',
 {t:'2017–2022 — a 6-year window; every time-series feature shares the same temporal support.',b:true},
],{y:1.7,w:6.6,gap:13,fs:14.5});
s.addShape(p.ShapeType.roundRect,{x:7.6,y:1.75,w:W-MG-7.6,h:2.0,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
s.addText('Why harmonized S2',{x:7.85,y:1.9,w:4.6,h:0.4,fontFace:HF,fontSize:14,bold:true,color:GREEN});
s.addText('After Jan 2022 ESA shifted the reflectance offset; an unharmonized series would show a fake step the harmonic fit misreads as phenology.',{x:7.85,y:2.3,w:4.7,h:1.3,fontFace:BF,fontSize:12.5,color:INK,lineSpacingMultiple:1.05});
s.addShape(p.ShapeType.roundRect,{x:7.6,y:3.95,w:W-MG-7.6,h:2.0,rectRadius:0.1,fill:{color:'F7F3EC'},line:{color:'E4D8C4',width:0.75}});
s.addText('ASCENDING-only  ·  judgment call',{x:7.85,y:4.1,w:4.6,h:0.4,fontFace:HF,fontSize:14,bold:true,color:AMBER});
s.addText('Mixing ascending/descending passes mixes viewing geometries and shifts backscatter. One orbit removes that, at the cost of ~half the observations. Unvalidated.',{x:7.85,y:4.5,w:4.7,h:1.3,fontFace:BF,fontSize:12.5,color:INK,lineSpacingMultiple:1.05});
foot(s,'Stage 2 · Data');

/* ===== 9 STAGE 3 OPTICAL concept ===== */
s=S(); kicker(s,'Stage 3 · Optical'); title(s,'Phenology is a fingerprint'); rule(s);
s.addText('A forest patch has a yearly rhythm: when it greens up, how strongly it swings between seasons, whether it is greening or browning year on year. Two patches identical in a single snapshot can have completely different calendars.',
 {x:MG,y:1.7,w:6.5,h:1.4,fontFace:BF,fontSize:15,color:INK,lineSpacingMultiple:1.1});
s.addText('So summarise the whole 6-year curve with a few interpretable numbers — not one date.',
 {x:MG,y:3.2,w:6.5,h:0.8,fontFace:HF,fontSize:16,bold:true,color:GREEN});
img(s,FIG.phen,7.4,1.7,W-MG-7.4,4.4);
cap(s,'Per-stand seasonal NDVI (real baseline run) — amplitude separates evergreen from deciduous behaviour.',7.4,6.15,W-MG-7.4);
foot(s,'Stage 3 · Optical');

/* ===== 10 STAGE 3 harmonic ===== */
s=S(); kicker(s,'Stage 3 · Optical'); title(s,'The harmonic model'); rule(s);
s.addShape(p.ShapeType.roundRect,{x:MG,y:1.65,w:W-2*MG,h:0.7,rectRadius:0.08,fill:{color:TINT},line:{color:RULE,width:0.75}});
s.addText('NDVI(t) = a  +  b·cos(2πt) + c·sin(2πt)  [ + semi-annual term ]  +  f·t          ( t = years since 2017-01-01, fit per pixel )',
 {x:MG+0.2,y:1.65,w:W-2*MG-0.4,h:0.7,fontFace:BF,fontSize:14.5,bold:true,color:INK,valign:'middle'});
tbl(s,[
 ['Feature','Formula','What it means ecologically'],
 ['mean','a','Overall greenness / productivity level'],
 ['amplitude_annual','√(b² + c²)','Size of the yearly swing (evergreen vs deciduous)'],
 ['phase_annual','atan2(c, b)','Timing of peak greenness within the year'],
 ['trend','f','Inter-annual greening (+) or browning (−)'],
 ['residual_variance','var(residuals)','Fit quality — DIAGNOSTIC only, NOT a clustering feature'],
],{y:2.6,colW:[2.7,2.2,7.5-0.6],rowH:0.44,fs:12.5});
note(s,'Baseline fits NDVI; variant fits NIRv (less confounded by soil/saturation) and adds a semi-annual term. residual_variance is exported as a diagnostic — the code now excludes it from clustering.'); foot(s,'Stage 3 · Optical');

/* ===== 11 STAGE 4 radar why ===== */
s=S(); kicker(s,'Stage 4 · Radar'); title(s,'Structure and moisture, through cloud'); rule(s);
const rc=[['Through cloud','C-band backscatter is unaffected by cloud, smoke or illumination — observations when optical fails.'],
 ['Structure & moisture','Backscatter rises with vegetation volume and water content, independent of canopy colour.'],
 ['Cross-pol VH','The cross-polarised return is sensitive to volume scattering of a structured canopy; the VH–VV relationship tracks density and phenology.']];
let rx=MG; const rw=(W-2*MG-2*0.35)/3;
rc.forEach(([h,b])=>{ s.addShape(p.ShapeType.roundRect,{x:rx,y:2.1,w:rw,h:3.4,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
 s.addText(h,{x:rx+0.28,y:2.35,w:rw-0.5,h:0.7,fontFace:HF,fontSize:16,bold:true,color:GREEN});
 s.addText(b,{x:rx+0.28,y:3.1,w:rw-0.56,h:2.2,fontFace:BF,fontSize:13.5,color:INK,lineSpacingMultiple:1.1}); rx+=rw+0.35; });
note(s,'Radar does two things optical cannot: it sees through cloud, and it responds to structure and moisture rather than colour — not a luxury for a cloudy-season country.'); foot(s,'Stage 4 · Radar');

/* ===== 12 STAGE 4 radar features ===== */
s=S(); kicker(s,'Stage 4 · Radar'); title(s,'What we compute from Sentinel-1 — 9 features'); rule(s);
tbl(s,[
 ['Group','Features','Meaning'],
 ['Percentiles','VV p10/p50/p90 · VH p10/p50/p90','low / median / high backscatter over 6 years'],
 ['Temporal spread','vv_iqr, vh_iqr  (p90 − p10)','how much backscatter varies through time'],
 ['Cross-pol contrast','vv_minus_vh_median','the cross-polarisation contrast, in dB'],
],{y:1.7,colW:[2.3,4.9,5.0-0.6],rowH:0.5,fs:12.5});
bullets(s,[
 {t:'Contrast in dB: a difference in dB is the log of a ratio, so VV − VH is the cross-pol ratio expressed additively — the scale-stable encoding.'},
 {t:'No spatial speckle filter: speckle averages down over independent looks; temporal percentiles and a 6-year median suppress it without blurring boundaries.'},
],{y:4.15,gap:12,fs:13.5});
note(s,'Code fix reflected: the temporal spread is p90 − p10 (was IQR).'); foot(s,'Stage 4 · Radar');

/* ===== 13 STAGE 5 structure ===== */
s=S(); kicker(s,'Stage 5 · Structure'); title(s,'Canopy height and its local texture'); rule(s);
tbl(s,[
 ['Feature','What it is'],
 ['canopy_height','ETH 10 m height — the most direct structural variable available wall to wall'],
 ['canopy_height_std','std in a 3×3 window — local roughness of the canopy top'],
 ['canopy_height_max','max in a 3×3 window — the tallest neighbour (smooth plantation vs ragged natural canopy)'],
],{y:1.7,colW:[3.0,W-2*MG-3.0],rowH:0.5,fs:13});
s.addShape(p.ShapeType.roundRect,{x:MG,y:3.9,w:W-2*MG,h:1.9,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
s.addText('Why ETH, and where it leads',{x:MG+0.3,y:4.05,w:8,h:0.4,fontFace:HF,fontSize:15,bold:true,color:GREEN});
s.addText('ETH fuses GEDI lidar with Sentinel-2 into a continuous 10 m raster — chosen over GEDI’s sparse footprints, which a wall-to-wall segmentation can’t use. Canopy-height heterogeneity is itself a proposed diversity proxy under the Height Variation Hypothesis (HVH).',
 {x:MG+0.3,y:4.5,w:W-2*MG-0.6,h:1.2,fontFace:BF,fontSize:13.5,color:INK,lineSpacingMultiple:1.1}); foot(s,'Stage 5 · Structure');

/* ===== 14 STAGE 6 static ===== */
s=S(); kicker(s,'Stage 6 · Static'); title(s,'Terrain, water, and rainfall'); rule(s);
bullets(s,[
 'Terrain — elevation, slope, aspect from NASADEM: the physical template that sets moisture, insolation and drainage.',
 'Distance to water — to nearest JRC permanent-water pixel, capped at 1000 px (a reasonable but arbitrary cutoff — judgment call).',
 'Rainfall — annual_rainfall, the CHIRPS climatological mean: context, useful for larger AOIs.',
],{y:1.75,gap:13,fs:15});
s.addShape(p.ShapeType.roundRect,{x:MG,y:4.2,w:W-2*MG,h:1.7,rectRadius:0.1,fill:{color:'F7F3EC'},line:{color:'E4D8C4',width:0.75}});
s.addText('annual_rainfall is dropped at clustering  ·  reasoning',{x:MG+0.3,y:4.35,w:9,h:0.4,fontFace:HF,fontSize:14.5,bold:true,color:AMBER});
s.addText('CHIRPS pixels are ~5.5 km, so a site like Sanjay Van sits inside roughly one cell — the variable is near-constant across the AOI and adds no within-AOI separation, so it is computed but kept out of the clustering vector. Aspect is circular and is decomposed (sin/cos) before clustering.',
 {x:MG+0.3,y:4.75,w:W-2*MG-0.6,h:1.1,fontFace:BF,fontSize:13.5,color:INK,lineSpacingMultiple:1.08}); foot(s,'Stage 6 · Static');

/* ===== 15 FEATURE SPACE ===== */
s=S(); kicker(s,'Feature space'); title(s,'The feature space — 22 baseline, 25 variant'); rule(s);
bullets(s,[
 {t:'Optical phenology: mean, amplitude, phase (sin/cos), trend — NDVI (baseline) or NIRv + semi-annual (variant).'},
 {t:'Radar (9): VV/VH p10/p50/p90, vv_iqr, vh_iqr, vv_minus_vh_median.'},
 {t:'Structure (3): canopy_height, _std, _max.'},
 {t:'Static: elevation, slope, aspect (sin/cos).'},
],{x:MG,y:1.75,w:6.5,gap:11,fs:14});
s.addShape(p.ShapeType.roundRect,{x:7.3,y:1.75,w:W-MG-7.3,h:4.1,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
s.addText('Computed but NOT clustered — each for a stated reason',{x:7.55,y:1.95,w:5,h:0.6,fontFace:HF,fontSize:14,bold:true,color:GREEN});
bullets(s,[
 'residual_variance — a fit-quality diagnostic (cloud, sparse obs), not ecology.',
 'annual_rainfall — near-constant over a small AOI.',
 'obs_count — a data-density diagnostic.',
],{x:7.55,y:2.65,w:W-MG-7.55-0.2,gap:10,fs:13});
s.addText('With phase/aspect each expanded into sin/cos and the three diagnostics excluded, the clustering vector is exactly 22 (baseline) / 25 (variant).',
 {x:7.55,y:4.6,w:W-MG-7.55-0.2,h:1.1,fontFace:BF,fontSize:12.5,italic:true,color:GREEN2,lineSpacingMultiple:1.05});
note(s,'Retires the old deck’s 20–21 / 23–26 counts; code and deck now agree on 22 / 25 and on the exclude-list.'); foot(s,'Features');

/* ===== 16 STAGE 7 seg concept ===== */
s=S(); kicker(s,'Stage 7 · Segmentation'); title(s,'Cluster places, not pixels'); rule(s);
s.addText('Clustering raw pixels gives salt-and-pepper: neighbours in the same stand scatter into different clusters because of per-pixel noise.',
 {x:MG,y:1.7,w:W-2*MG,h:0.7,fontFace:BF,fontSize:15,color:INK});
// text+arrow concept
s.addText('per-pixel features',{x:MG,y:3.0,w:3.4,h:0.5,fontFace:BF,fontSize:14,bold:true,color:INK,align:'center',valign:'middle'});
arrowR(s,MG+3.5,3.25,0.6);
s.addText('group adjacent, similar pixels\n(SNIC superpixels)',{x:MG+4.2,y:2.85,w:3.6,h:0.8,fontFace:BF,fontSize:13.5,color:INK,align:'center',valign:'middle'});
arrowR(s,MG+8.0,3.25,0.6);
s.addText('cluster the segments',{x:MG+8.7,y:3.0,w:3.4,h:0.5,fontFace:BF,fontSize:14,bold:true,color:GREEN,align:'center',valign:'middle'});
s.addText('Group adjacent, similar pixels into segments first, then cluster the segments — within-stand variability drops out. In computer-vision terms these segments are superpixels.',
 {x:MG,y:4.3,w:W-2*MG,h:1.0,fontFace:BF,fontSize:15,color:INK,lineSpacingMultiple:1.1});
note(s,'Segment-then-classify over per-pixel clustering is well established (OBIA).'); foot(s,'Stage 7 · Segmentation');

/* ===== 17 STAGE 7 SNIC ===== */
s=S(); kicker(s,'Stage 7 · Segmentation'); title(s,'SNIC superpixels'); rule(s);
bullets(s,[
 'An improvement on SLIC: non-iterative, enforces connectivity from the start, low memory, fast — well suited to Earth Engine.',
 {t:'Runs on 5 normalised bands: B4_median · B8_median · composite_nirv · canopy_height · vv_minus_vh_median.'},
 'Parameters: size 10 · compactness 0.5 · connectivity 8 · neighbourhood 128 — chosen empirically, not swept (judgment call).',
 'Z-scored first, so canopy height in metres can’t dominate reflectances in [0,1].',
],{y:1.75,w:7.2,gap:12,fs:14.5});
s.addShape(p.ShapeType.roundRect,{x:8.0,y:1.9,w:W-MG-8.0,h:2.6,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
s.addText('Boundaries FIXED across configs',{x:8.25,y:2.1,w:4.3,h:0.5,fontFace:HF,fontSize:15,bold:true,color:GREEN});
s.addText('SNIC is computed once and held byte-identical for baseline, variant AND the embedding arm — the lever that isolates the feature effect. It is the experimental control for every comparison in this deck.',
 {x:8.25,y:2.65,w:W-MG-8.0-0.5,h:1.7,fontFace:BF,fontSize:13,color:INK,lineSpacingMultiple:1.1}); foot(s,'Stage 7 · Segmentation');

/* ===== 18 FEATURE SELECTION: seg != cluster ===== */
s=S(); kicker(s,'Feature selection · Segmentation'); title(s,'Segmentation features ≠ clustering features'); rule(s);
s.addText('SNIC only draws boundaries (where the landscape changes); k-means decides what each region is (the full 22/25 stack). Boundary-finding uses a deliberately reduced set — for four reasons.',
 {x:MG,y:1.7,w:W-2*MG,h:0.8,fontFace:BF,fontSize:14.5,color:INK});
const fr=[['Redundancy','Most of the 22 share a source and are correlated; feed them all and whichever sensor has the most columns dominates the distance. One representative per signal.'],
 ['Noise','Noisier derived bands (phase, trend, residual variance, the IQRs) inject spurious per-pixel texture — SNIC would carve superpixels around fitting artifacts.'],
 ['Dimensionality','SNIC trades feature distance against spatial compactness; add bands and the feature distances concentrate, the spatial term is swamped, superpixels stop being clean.'],
 ['Experimental control','Boundaries must be identical across configs to isolate the feature effect — that requires a fixed band set; the variant’s extra harmonics must not move segments.']];
let fx=MG, fy=2.6; const fw=(W-2*MG-0.35)/2;
fr.forEach((it,i)=>{ const x=MG+(i%2)*(fw+0.35); const y=2.6+Math.floor(i/2)*(1.55+0.25);
 s.addShape(p.ShapeType.roundRect,{x,y,w:fw,h:1.55,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
 s.addText(it[0],{x:x+0.25,y:y+0.14,w:fw-0.5,h:0.4,fontFace:HF,fontSize:14.5,bold:true,color:GREEN});
 s.addText(it[1],{x:x+0.25,y:y+0.56,w:fw-0.5,h:0.95,fontFace:BF,fontSize:12.5,color:INK,lineSpacingMultiple:1.05}); });
foot(s,'Feature selection');

/* ===== 19 FEATURE SELECTION: 5 bands ===== */
s=S(); kicker(s,'Feature selection · Segmentation'); title(s,'Why these five SNIC bands'); rule(s);
tbl(s,[
 ['Band','Axis','Why it earns a slot'],
 ['B4 — red (median)','Optical colour','Strongest single optical separator (red/NIR edge); median = temporally stable'],
 ['B8 — NIR (median)','Optical colour','Pairs with red for the vegetation edge'],
 ['composite NIRv','Optical productivity','One integrative, soil/saturation-robust greenness summary shared by both configs'],
 ['canopy_height','Vertical structure','The dominant empirical separator (~11.5 m cluster spread at Sanjay Van)'],
 ['vv_minus_vh_median','Radar structure','Marks boundaries under cloud/canopy that reflectance misses'],
],{y:1.7,colW:[2.7,2.4,W-2*MG-5.1],rowH:0.46,fs:12.5});
note(s,'The span is optical colour + productivity + vertical structure + radar structure (minimal redundancy). The exact five were not ablated vs another four/six — same status as the SNIC parameters, under the "no sensitivity analysis" gap.'); foot(s,'Feature selection');

/* ===== 20 STAGE 8 clustering steps ===== */
s=S(); kicker(s,'Stage 8 · Clustering'); title(s,'From superpixels to clusters'); rule(s);
// text+arrow chain
const cc=['superpixel →\none feature vector','cyclic sin/cos\n(phase, aspect)','log skewed\nbands','robust median/IQR\nscale','k-means++\n(k = 6)'];
let cx=MG; const ccw=(W-2*MG)/cc.length;
cc.forEach((v,i)=>{ s.addShape(p.ShapeType.roundRect,{x:cx+0.05,y:1.8,w:ccw-0.35,h:0.95,rectRadius:0.08,fill:{color:TINT},line:{color:RULE,width:0.75}});
 s.addText(v,{x:cx+0.05,y:1.8,w:ccw-0.35,h:0.95,fontFace:BF,fontSize:11.5,color:INK,align:'center',valign:'middle'});
 if(i<cc.length-1) arrowR(s,cx+ccw-0.28,2.27,0.2); cx+=ccw; });
s.addShape(p.ShapeType.roundRect,{x:MG,y:3.1,w:W-2*MG,h:1.3,rectRadius:0.1,fill:{color:'F4F8F1'},line:{color:RULE,width:0.75}});
s.addText('Exclude-list — code and deck agree',{x:MG+0.3,y:3.25,w:9,h:0.4,fontFace:HF,fontSize:14.5,bold:true,color:GREEN});
s.addText('residual_variance is a fit-quality diagnostic, not a feature: the clustering exclude-list drops it alongside obs_count and annual_rainfall, so k-means never sees it.',
 {x:MG+0.3,y:3.65,w:W-2*MG-0.6,h:0.7,fontFace:BF,fontSize:13.5,color:INK,lineSpacingMultiple:1.05});
bullets(s,[
 'Cyclic sin/cos so December (≈2π) and January (≈0) aren’t "far apart"; log compresses right tails; robust median/IQR is outlier-resistant; standardise so no band dominates Euclidean distance.',
],{y:4.6,gap:8,fs:13.5}); foot(s,'Stage 8 · Clustering');

/* ===== 21 STAGE 8 judgment calls ===== */
s=S(); kicker(s,'Stage 8 · Clustering'); title(s,'What’s principled — and what’s still a guess'); rule(s);
s.addShape(p.ShapeType.roundRect,{x:MG,y:1.7,w:(W-2*MG-0.4)/2,h:3.8,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
s.addText('Principled (reasoning)',{x:MG+0.3,y:1.9,w:5,h:0.4,fontFace:HF,fontSize:15,bold:true,color:GREEN});
bullets(s,['Cyclic sin/cos for phase & aspect','Log-transform for skewed bands','Robust median/IQR scaling','Standardise before Euclidean distance','k-means++ seeding for stability'],
 {x:MG+0.35,y:2.4,w:(W-2*MG-0.4)/2-0.6,gap:10,fs:14});
const rx2=MG+(W-2*MG-0.4)/2+0.4;
s.addShape(p.ShapeType.roundRect,{x:rx2,y:1.7,w:(W-2*MG-0.4)/2,h:3.8,rectRadius:0.1,fill:{color:'F7F3EC'},line:{color:'E4D8C4',width:0.75}});
s.addText('Judgment calls (need validation)',{x:rx2+0.3,y:1.9,w:5,h:0.4,fontFace:HF,fontSize:15,bold:true,color:AMBER});
bullets(s,['k = 6 — needs a silhouette/elbow sweep or ecological prior','seed = 42','skewness threshold = 1.0','10,000-superpixel training sample'],
 {x:rx2+0.35,y:2.4,w:(W-2*MG-0.4)/2-0.6,gap:11,fs:14});
foot(s,'Stage 8 · Clustering');

/* ===== 22 FEATURE SELECTION keep/drop + ablation ===== */
s=S(); kicker(s,'Feature selection · Clustering'); title(s,'Keep weak features — decide by ablation, not assertion'); rule(s);
s.addShape(p.ShapeType.roundRect,{x:MG,y:1.7,w:(W-2*MG-0.4)/2,h:2.5,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
s.addText('Keep — "weak" ≠ "useless"',{x:MG+0.3,y:1.85,w:5,h:0.4,fontFace:HF,fontSize:14.5,bold:true,color:GREEN});
bullets(s,['Site-specific: amplitude/phase are flat in urban scrub but dominant across Mudumalai’s deciduous gradients — pruning to one weak AOI breaks transfer.','Marginal ≠ joint: k-means uses joint distance; a feature with small 1-D spread can still split otherwise-overlapping clusters.','Descriptive value + ~zero cost (already computed).'],
 {x:MG+0.35,y:2.3,w:(W-2*MG-0.4)/2-0.6,gap:8,fs:12.5});
const rx3=MG+(W-2*MG-0.4)/2+0.4;
s.addShape(p.ShapeType.roundRect,{x:rx3,y:1.7,w:(W-2*MG-0.4)/2,h:2.5,rectRadius:0.1,fill:{color:'F7F3EC'},line:{color:'E4D8C4',width:0.75}});
s.addText('Genuine drop candidates',{x:rx3+0.3,y:1.85,w:5,h:0.4,fontFace:HF,fontSize:14.5,bold:true,color:AMBER});
bullets(s,['SAR IQRs (vv_iqr, vh_iqr): near-zero spread AND a mechanism — ASCENDING-only, limited looks may be capturing speckle/sampling variance, not real dynamics. Strongest ablation target.','vv_minus_vh_median: weak in profiles but doing double duty as a SNIC band — test before assuming idle.'],
 {x:rx3+0.35,y:2.3,w:(W-2*MG-0.4)/2-0.6,gap:9,fs:12.5});
s.addShape(p.ShapeType.roundRect,{x:MG,y:4.4,w:W-2*MG,h:1.5,rectRadius:0.1,fill:{color:'F4F8F1'},line:{color:RULE,width:0.75}});
s.addText('The test (Phase 0): full stack vs reduced stack — compare partitions with the ARI/NMI already in the pipeline, run at BOTH Sanjay Van and Mudumalai.',
 {x:MG+0.3,y:4.55,w:W-2*MG-0.6,h:0.5,fontFace:HF,fontSize:13.5,bold:true,color:GREEN});
s.addText('ARI ≈ 1 at Sanjay Van but the reduced set collapses clusters at Mudumalai → the weak features do transferable work, keep them. Dropping the SAR IQRs changes nothing anywhere → drop them, and say why. Trap: don’t over-prune toward "only what separates Sanjay Van".',
 {x:MG+0.3,y:5.05,w:W-2*MG-0.6,h:0.8,fontFace:BF,fontSize:12.5,color:INK,lineSpacingMultiple:1.05}); foot(s,'Feature selection');

/* ===== 23 STAGE 9 profiling ===== */
s=S(); kicker(s,'Stage 9 · Profiling'); title(s,'Give every cluster a readable fingerprint'); rule(s);
bullets(s,[
 'Summarise each cluster’s features in original units — height in metres, backscatter in dB, NDVI unitless — not scaled space.',
 'Clusters are only interpretable if you can read them as "tall, low-seasonality, far from water".',
 {t:'Output: cluster_profiles.csv — one row per cluster, the fingerprint of each stand type, the input to every results figure.'},
],{y:1.75,w:6.6,gap:13,fs:15});
img(s,FIG.fp,7.4,1.7,W-MG-7.4,4.4);
cap(s,'Per-stand z-scored feature signature (real baseline run): orange above / blue below the cross-stand average.',7.4,6.15,W-MG-7.4);
foot(s,'Stage 9 · Profiling');

/* ===== 24 STAGE 10 export ===== */
s=S(); kicker(s,'Stage 10 · Export'); title(s,'Rasters, vectors, and a manifest'); rule(s);
const ex=[['Raster','Three GeoTIFFs — the single-band cluster-label map, plus two multi-band rasters carrying every feature (one in original units, one in the scaled space k-means saw) with the cluster label.'],
 ['Vectors','stands_snic (the superpixels) and stands_dissolved (superpixels merged by cluster into stand polygons) — each as SHP and GeoJSON.'],
 ['Manifest','A record of configuration and outputs — what makes a run repeatable.']];
let ey=1.8; ex.forEach(([h,b])=>{ s.addShape(p.ShapeType.roundRect,{x:MG,y:ey,w:W-2*MG,h:1.2,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
 s.addText(h,{x:MG+0.3,y:ey+0.12,w:2.4,h:0.9,fontFace:HF,fontSize:15,bold:true,color:GREEN,valign:'middle'});
 s.addText(b,{x:MG+2.9,y:ey+0.1,w:W-2*MG-3.2,h:1.0,fontFace:BF,fontSize:13,color:INK,valign:'middle',lineSpacingMultiple:1.05}); ey+=1.35; });
note(s,'stands_dissolved is the usable stand map — the layer a forester or ecologist actually opens (the old export slide omitted it; B4 GeoTIFF fix applied).'); foot(s,'Stage 10 · Export');

/* ===== 25 STAGE 11 metrics ===== */
s=S(); kicker(s,'Stage 11 · Metrics'); title(s,'Scoring a configuration'); rule(s);
tbl(s,[
 ['Metric','What it measures'],
 ['Silhouette','Internal cohesion vs separation of one clustering — no labels needed (intrinsic)'],
 ['Adjusted Rand Index (ARI)','Agreement of two partitions, corrected for chance'],
 ['Normalized Mutual Information (NMI)','Shared information between two partitions'],
 ['Hungarian correspondence','Optimal one-to-one matching of cluster IDs between two runs'],
],{y:1.7,colW:[3.6,W-2*MG-3.6],rowH:0.5,fs:13});
s.addText('Silhouette is internal — it judges one clustering’s geometry. ARI and NMI are comparative — how much two clusterings agree. The Hungarian step lines up cluster IDs first, since cluster 3 in one run may be cluster 5 in another. Higher silhouette = tighter, better-separated stands; it needs no ground truth, so it is the one number directly comparable across every arm.',
 {x:MG,y:4.4,w:W-2*MG,h:1.4,fontFace:BF,fontSize:14,color:INK,lineSpacingMultiple:1.1}); foot(s,'Stage 11 · Metrics');

/* ===== 26 DIVIDER Experiment 1 ===== */
s=S(); divider(s,'Experiment 1 · optical','Baseline vs variant — one variable changed','NDVI single-harmonic vs NIRv + dual-harmonic. SNIC held fixed, so any difference is the optical features alone.');

/* ===== 27 C-0 design + result ===== */
s=S(); kicker(s,'Experiment C-0 · result'); title(s,'Does NIRv + dual-harmonic change the map?'); rule(s);
img(s,FIG.c0conf,MG,1.7,4.2,4.2);
bullets(s,[
 {t:'ARI 0.49 · NMI 0.55 — the two partitions agree moderately, not fully.',b:true},
 '73% of superpixels keep the same stand once cluster IDs are aligned.',
 'Silhouette −0.007 (baseline) → +0.010 (variant): both near zero — stands overlap heavily in feature space either way.',
 'The variant reshuffles some boundaries but does not, here, produce a sharply better-separated map.',
],{x:5.3,y:1.9,w:W-MG-5.3,gap:13,fs:14.5});
note(s,'Row-normalised overlap after Hungarian matching (green ring = best match). SNIC fixed, so the difference is the optical features alone. Distinct from Experiment C-1 (AlphaEarth).'); foot(s,'Experiment C-0');

/* ===== 28 baseline results: separating power ===== */
s=S(); kicker(s,'Baseline run · results'); title(s,'What separates the stands at Sanjay Van'); rule(s);
img(s,FIG.sep,MG,1.7,7.4,4.4);
bullets(s,[
 {t:'Canopy structure leads — the stands are mostly a structural partition.'},
 'Radar backscatter is the secondary axis; NDVI level and cross-pol separate weakly.',
 'distance_to_water is flat — near-constant across stands here.',
 {t:'An urban-forest finding: stands differ more in build than in greenness rhythm — one reason the NIRv/dual-harmonic variant exists.',b:true},
],{x:8.2,y:1.9,w:W-MG-8.2,gap:12,fs:13.5});
cap(s,'Between-stand separation per feature (real baseline run). Higher = the feature drives the partition.',MG,6.15,7.4); foot(s,'Results');

/* ===== 29 baseline results: map + fingerprint ===== */
s=S(); kicker(s,'Baseline run · results'); title(s,'The stand map and what defines each stand'); rule(s);
s.addText('Stand map (stands_dissolved)',{x:MG,y:1.6,w:6,h:0.35,fontFace:HF,fontSize:14,bold:true,color:INK});
img(s,FIG.mapBase,MG,1.95,4.6,4.2);
s.addText('Per-stand signature (z-scored)',{x:6.9,y:1.6,w:6,h:0.35,fontFace:HF,fontSize:14,bold:true,color:INK});
img(s,FIG.fp,6.9,1.95,6.0,3.4);
s.addText('Six stand types over ~968 ha of habitat inside the 13.0 km² AOI. Each colour = one k-means cluster. Canopy-height and radar columns carry the strongest contrast; distance_to_water is flat.',
 {x:6.9,y:5.4,w:6.0,h:0.9,fontFace:BF,fontSize:12,italic:true,color:MUTE,lineSpacingMultiple:1.05}); foot(s,'Results');

/* ===== 30 baseline results: phenology ===== */
s=S(); kicker(s,'Baseline run · results'); title(s,'The seasonal rhythm of each stand'); rule(s);
img(s,FIG.phen,MG,1.7,7.4,4.4);
bullets(s,[
 'Every stand greens up mid-year with the monsoon — the timing (phase) is shared.',
 'They separate mainly in overall NDVI level and in amplitude (the size of the seasonal swing).',
 'Amplitude is what tells evergreen-like from deciduous-like behaviour.',
],{x:8.2,y:2.0,w:W-MG-8.2,gap:13,fs:14});
cap(s,'Per-stand seasonal NDVI rebuilt from the fitted harmonic (real baseline run).',MG,6.15,7.4); foot(s,'Results');

/* ===== 31 DIVIDER Experiment 2 ===== */
s=S(); divider(s,'Experiment 2 · embedding','Baseline vs AlphaEarth — swap the whole feature arm','The field has moved from hand-engineering features to clustering pretrained per-pixel embeddings. Same SNIC, same k — only the feature vector changes.');

/* ===== 32 the field shift ===== */
s=S(); kicker(s,'Experiment C-1 · context'); title(s,'From hand-crafted features to pretrained embeddings'); rule(s);
bullets(s,[
 {t:'AlphaEarth Foundations (Brown et al. 2025): a 64-D embedding per 10 m pixel per year, global, shipped inside Earth Engine — designed as a drop-in feature vector.'},
 {t:'TESSERA (Feng et al. 2025): 128-D, self-supervised on Sentinel-1/2 time series, preserves phenology, CC0 — the open counterpart (intended 3rd arm).'},
 'Clustering a pretrained embedding is now a mainstream workflow — the field independently converged on FMU’s "embedding → k-means → strata" design.',
 'The honest question is not "why not embeddings?" but "do they produce more-separable stands than the hand-crafted stack, here?" — a falsifiable test.',
],{y:1.75,gap:13,fs:15}); foot(s,'Experiment C-1');

/* ===== 33 the swap ===== */
s=S(); kicker(s,'Experiment C-1 · design'); title(s,'Swap only the feature arm'); rule(s);
s.addText('Hand-crafted 22-band stack',{x:MG,y:2.2,w:4.0,h:0.4,fontFace:BF,fontSize:14.5,bold:true,color:INK,valign:'middle'});
arrowR(s,MG+4.0,2.4,0.5); s.addText('k-means (k=6)',{x:MG+4.6,y:2.2,w:2.3,h:0.4,fontFace:BF,fontSize:14,color:INK,valign:'middle'});
arrowR(s,MG+6.9,2.4,0.5); s.addText('stands (Arm A)',{x:MG+7.5,y:2.2,w:2.6,h:0.4,fontFace:BF,fontSize:14,color:INK,valign:'middle'});
s.addText('AlphaEarth 64-D embedding',{x:MG,y:3.3,w:4.0,h:0.4,fontFace:BF,fontSize:14.5,bold:true,color:INK,valign:'middle'});
arrowR(s,MG+4.0,3.5,0.5); s.addText('k-means (k=6)',{x:MG+4.6,y:3.3,w:2.3,h:0.4,fontFace:BF,fontSize:14,color:INK,valign:'middle'});
arrowR(s,MG+6.9,3.5,0.5); s.addText('stands (Arm B)',{x:MG+7.5,y:3.3,w:2.6,h:0.4,fontFace:BF,fontSize:14,color:INK,valign:'middle'});
s.addShape(p.ShapeType.line,{x:MG+9.4,y:2.4,w:0,h:1.1,line:{color:LINE,width:1.2}}); arrowR(s,MG+9.4,2.95,0.5);
s.addText('compare:\nARI · NMI · silhouette · agreement',{x:MG+10.0,y:2.55,w:2.6,h:0.8,fontFace:BF,fontSize:12.5,color:GREEN,bold:true,valign:'middle'});
s.addText('Held identical for both arms: SNIC boundaries · k = 6 · random seed · ROI · time window. Only the feature vector changes — so any difference is the representation, not the pipeline.',
 {x:MG,y:4.5,w:W-2*MG,h:0.9,fontFace:BF,fontSize:14.5,color:INK,lineSpacingMultiple:1.1}); foot(s,'Experiment C-1');

/* ===== 34 C-1 result 1 silhouette ===== */
s=S(); kicker(s,'Experiment C-1 · result 1'); title(s,'AlphaEarth separates the stands far better'); rule(s);
img(s,FIG.sil,MG,1.8,7.6,3.2);
s.addText('+0.113',{x:8.9,y:2.0,w:3.6,h:0.8,fontFace:HF,fontSize:40,bold:true,color:GREEN}); s.addText('AlphaEarth silhouette',{x:8.9,y:2.85,w:3.6,h:0.4,fontFace:BF,fontSize:14,color:MUTE});
s.addText('−0.007',{x:8.9,y:3.5,w:3.6,h:0.8,fontFace:HF,fontSize:40,bold:true,color:INK}); s.addText('baseline silhouette',{x:8.9,y:4.35,w:3.6,h:0.4,fontFace:BF,fontSize:14,color:MUTE});
bullets(s,[
 'Silhouette is intrinsic — comparable across arms without any reference.',
 'AlphaEarth is clearly more separable; the baseline sits essentially at zero.',
 'Honest limit: +0.113 is still "weak structure" in absolute terms, and this is internal geometry — not ecological correctness.',
],{x:MG,y:5.2,w:8.0,gap:8,fs:13.5}); foot(s,'Experiment C-1');

/* ===== 35 C-1 result 2 maps ===== */
s=S(); kicker(s,'Experiment C-1 · result 2'); title(s,'Same boundaries, different stands'); rule(s);
s.addText('Baseline (hand-crafted)',{x:1.2,y:1.65,w:3.5,h:0.35,fontFace:HF,fontSize:14,bold:true,color:INK,align:'center'});
img(s,FIG.mapB,1.2,2.0,3.5,4.2);
s.addText('AlphaEarth (embedding)',{x:5.0,y:1.65,w:3.5,h:0.35,fontFace:HF,fontSize:14,bold:true,color:GREEN,align:'center'});
img(s,FIG.mapA,5.0,2.0,3.5,4.2);
bullets(s,[
 'Same SNIC boundaries in both; only the cluster assignment differs.',
 'Colours are per-arm — the same colour is a different stand in each map.',
 'AlphaEarth gives larger, more contiguous stands; the baseline is more fragmented — the visual counterpart of the silhouette gap.',
],{x:8.9,y:2.1,w:W-MG-8.9,gap:12,fs:13}); foot(s,'Experiment C-1');

/* ===== 36 C-1 result 3 agreement ===== */
s=S(); kicker(s,'Experiment C-1 · result 3'); title(s,'The two representations delineate quite differently'); rule(s);
img(s,FIG.conf,MG,1.75,4.1,4.1);
s.addText('ARI 0.17     NMI 0.23     Agreement 41%',{x:5.2,y:2.0,w:W-MG-5.2,h:0.5,fontFace:HF,fontSize:19,bold:true,color:INK});
bullets(s,[
 'Low-to-moderate agreement: after Hungarian alignment only ~41% of pixels fall in corresponding stands.',
 'Green rings mark each AlphaEarth stand’s best-matching baseline stand — one maps cleanly (73%), a few moderately (49%, 48%), two are smeared.',
 'Neither arm is a reference; this only quantifies how much the representation reshapes the map.',
],{x:5.2,y:2.7,w:W-MG-5.2,gap:12,fs:14}); foot(s,'Experiment C-1');

/* ===== 37 C-1 result 4 confidence ===== */
s=S(); kicker(s,'Experiment C-1 · result 4'); title(s,'A per-stand consensus (confidence) layer'); rule(s);
img(s,FIG.confid,MG,1.9,7.4,7.4/2.61);
s.addText('mean 40%      33% of area ≥ 80% agreement',{x:MG,y:5.0,w:W-2*MG,h:0.5,fontFace:HF,fontSize:18,bold:true,color:INK});
bullets(s,[
 'Confidence = how often the two representations place a stand in corresponding classes (the agreement map rolled up per stand).',
 'A stability / uncertainty layer a forester can act on — explicitly NOT a correctness score, which would need ground truth.',
],{y:5.55,gap:9,fs:14}); foot(s,'Experiment C-1');

/* ===== 38 interpretability trade-off ===== */
s=S(); kicker(s,'Experiment C-1 · trade-off'); title(s,'Separability comes at the cost of interpretability'); rule(s);
s.addShape(p.ShapeType.roundRect,{x:MG,y:1.75,w:(W-2*MG-0.4)/2,h:4.0,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
s.addText('Baseline — readable',{x:MG+0.3,y:1.95,w:5,h:0.4,fontFace:HF,fontSize:16,bold:true,color:INK});
bullets(s,['Clusters profile in real ecological units:','canopy height & vertical structure','NDVI mean, amplitude & phenological phase','VV/VH radar backscatter · elevation, slope','→ "Stand 3 is short, sparse canopy on a dry slope."'],
 {x:MG+0.35,y:2.45,w:(W-2*MG-0.4)/2-0.6,gap:9,fs:13.5});
const ix=MG+(W-2*MG-0.4)/2+0.4;
s.addShape(p.ShapeType.roundRect,{x:ix,y:1.75,w:(W-2*MG-0.4)/2,h:4.0,rectRadius:0.1,fill:{color:'F7F3EC'},line:{color:'E4D8C4',width:0.75}});
s.addText('AlphaEarth — abstract',{x:ix+0.3,y:1.95,w:5,h:0.4,fontFace:HF,fontSize:16,bold:true,color:AMBER});
bullets(s,['Clusters profile in 64 learned dimensions:','A00, A01, A02 … A63 — no physical units','more separable, but not directly nameable','ecological meaning must be recovered post-hoc','→ "Stand 3 is high on A17, low on A40." — separable, not self-explaining.'],
 {x:ix+0.35,y:2.45,w:(W-2*MG-0.4)/2-0.6,gap:9,fs:13.5}); foot(s,'Experiment C-1');

/* ===== 39 what C-1 shows / doesn't ===== */
s=S(); kicker(s,'Experiment C-1 · honest reading'); title(s,'What this comparison does and does not show'); rule(s);
s.addText('It DOES show',{x:MG,y:1.7,w:5.8,h:0.4,fontFace:HF,fontSize:16,bold:true,color:GREEN});
bullets(s,['The two representations cluster the forest differently (ARI 0.17).','AlphaEarth clusters are internally more separable (+0.113 vs −0.007).','Where they agree can be mapped as a consensus layer.'],
 {x:MG,y:2.15,w:5.9,gap:10,fs:14});
s.addText('It does NOT show',{x:7.0,y:1.7,w:5.6,h:0.4,fontFace:HF,fontSize:16,bold:true,color:AMBER});
bullets(s,['That either representation is ecologically more correct — no ground truth.','External validity — all scores are internal (agreement between arms is not truth).','Generality — one AOI (Sanjay Van, the secondary site), one k, two arms, not pre-registered.'],
 {x:7.0,y:2.15,w:W-MG-7.0,gap:10,fs:14});
note(s,'A real Phase-1 result needs external validation + the Mudumalai run + a pre-registered hypothesis (see Roadmap).'); foot(s,'Experiment C-1');

/* ===== 40 TESSERA ===== */
s=S(); kicker(s,'Intended third arm'); title(s,'Tessera — attempted, not completed'); rule(s);
s.addShape(p.ShapeType.roundRect,{x:MG,y:1.8,w:(W-2*MG-0.4)/2,h:3.9,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
s.addText('What it is & why',{x:MG+0.3,y:1.95,w:5,h:0.4,fontFace:HF,fontSize:15,bold:true,color:GREEN});
bullets(s,['A second pretrained per-pixel embedding (128-D, S1/S2 time-series, preserves phenology, CC0) — off-GEE, ingested as an EE asset.','Goal: a three-way comparison (hand-crafted vs AlphaEarth vs Tessera).','The pipeline is already source-agnostic: the features_embedding stage loads either embedding unchanged.'],
 {x:MG+0.35,y:2.4,w:(W-2*MG-0.4)/2-0.6,gap:11,fs:13});
const tx=MG+(W-2*MG-0.4)/2+0.4;
s.addShape(p.ShapeType.roundRect,{x:tx,y:1.8,w:(W-2*MG-0.4)/2,h:3.9,rectRadius:0.1,fill:{color:'F7F3EC'},line:{color:'E4D8C4',width:0.75}});
s.addText('Why it is blocked',{x:tx+0.3,y:1.95,w:5,h:0.4,fontFace:HF,fontSize:15,bold:true,color:AMBER});
bullets(s,['Coverage: for the Delhi ROI, Tessera publishes tiles only for 2024–2025 — a temporal mismatch with AlphaEarth’s 2017–2022 window.','Ingestion: geotessera 0.9.0 reports a covering tile but writes no GeoTIFF, so the mosaic step fails.','Status: scaffolding in place; a clean run needs a fixed fetch + a stated window caveat.'],
 {x:tx+0.35,y:2.4,w:(W-2*MG-0.4)/2-0.6,gap:11,fs:13});
note(s,'Reported transparently: the third arm is future work, not a result. No Tessera numbers appear anywhere in this deck.'); foot(s,'Tessera');

/* ===== 41 DIVIDER Gaps ===== */
s=S(); divider(s,'Gaps & roadmap','Where this goes next','From a separate literature review (~246 verified DOIs): the field is six currents around one binding constraint — and India owns that constraint.');

/* ===== 42 the one gap ===== */
s=S(); kicker(s,'Gaps'); title(s,'The one gap underneath all the others'); rule(s);
s.addText('There is no independent, stand-level ground reference.',{x:MG,y:1.7,w:W-2*MG,h:0.5,fontFace:HF,fontSize:19,bold:true,color:INK});
bullets(s,[
 'So "ecologically meaningful" is neither provable nor falsifiable at scale.',
 'Unsupervised delineation has no agreed validation grammar — only internal, circular metrics.',
 'Embedding clusters get checked against land-cover labels, not against ecology.',
 'This is a field-wide condition — and India (FSI working-plan compartments + Mudumalai ForestGEO) is where the reference can be built. That is a comparative advantage in ground truth, the field’s binding constraint.',
],{y:2.4,gap:13,fs:15}); foot(s,'Gaps');

/* ===== 43 gaps on path ===== */
s=S(); kicker(s,'Gaps'); title(s,'Gaps on the committed path'); rule(s);
tbl(s,[
 ['ID','Gap'],
 ['G1','No validation grammar for unsupervised delineation (internal metrics are circular)'],
 ['G2','A "stand" is aggregated from superpixels, never drawn or tested against a reference unit'],
 ['G3','k and segmentation parameters chosen unprincipled; k = 6 asserted, not swept'],
 ['G4','Embeddings vs hand-crafted features never raced head-to-head for stand clustering'],
 ['G10–G13','The "spectral community" bridge (SVH) is untested in Indian dry forest; no falsifiable claim yet'],
],{y:1.7,colW:[1.4,W-2*MG-1.4],rowH:0.6,fs:13});
note(s,'The AlphaEarth run (C-1) is a first attack on G4 — but internal-only, so it does not yet close it; it needs G1/G2 external validation.'); foot(s,'Gaps');

/* ===== 44 SVH test ===== */
s=S(); kicker(s,'Gaps · the scientific core'); title(s,'The SVH test (what would close G10–G13)'); rule(s);
bullets(s,[
 'Spectral Variation Hypothesis (SVH): spectral heterogeneity as a proxy for biological diversity.',
 'Alpha-SVH: within a patch, does more spectral variation mean more species?',
 {t:'Beta-SVH: do two spectrally different patches also differ in species? — THIS validates a stand boundary.',b:true},
 'Test: correlate spectral distance vs field species turnover across units, with a permutation / Mantel null (spatial autocorrelation fakes a positive otherwise).',
 'Site: the Mudumalai ForestGEO stem-mapped plot gives the real species ground truth.',
 'It is falsifiable — the sharpest paper in the field is a falsification (Schmidtlein & Fassnacht 2017); in Indian dry forest it was tested once, with mixed results (Nagendra 2010).',
],{y:1.7,gap:11,fs:14}); foot(s,'SVH');

/* ===== 45 make it a result ===== */
s=S(); kicker(s,'Gaps'); title(s,'What would turn C-1 into a real result'); rule(s);
bullets(s,[
 {t:'Add external validation (the missing piece): score each arm against an independent reference, not just against each other — national forest-type maps (Roy 2015 / Reddy 2015) and FSI products (coarse, wall-to-wall), plus the Mudumalai ForestGEO plot (fine, real, one plot).'},
 {t:'Run on Mudumalai as the primary AOI — it carries the ground truth; Sanjay Van becomes the transfer test.'},
 {t:'Add the Tessera arm (fix ingestion) for a three-way comparison.'},
 {t:'Pre-register the hypothesis before running, so the pipeline can fail (closes the "no committed hypothesis" gap).'},
],{y:1.8,gap:14,fs:15});
note(s,'Internal + exploratory → tested + externally validated. That is the jump from "we produced a map" to "we tested a hypothesis about the map."'); foot(s,'Gaps');

/* ===== 46 roadmap ===== */
s=S(); kicker(s,'Roadmap'); title(s,'The phased plan'); rule(s);
const ph=[['Phase 0 (2–4 wk)','Make the replication defensible','k-selection sweep · parameter & feature-ablation sensitivity (both AOIs) · complete the Mudumalai run.'],
 ['Phase 1 (2–3 mo)','Embeddings swap, externally validated → first paper','Add AlphaEarth (+ Tessera) arms; score internal AND external; pre-register the falsifiable H0.'],
 ['Phase 2 (4–6 mo)','The falsifiable SVH/HVH test → scientific core','Reuse Phase-1 references; test spectral-community boundaries vs field turnover at Mudumalai.'],
 ['Phase 3 (start now)','The Indian stand-reference layer → unique asset','FSI working-plan compartments; digitise a division. Access is the bottleneck — begin in month 1.']];
let phy=1.75; ph.forEach(([a,b,c],i)=>{ s.addShape(p.ShapeType.roundRect,{x:MG,y:phy,w:W-2*MG,h:1.05,rectRadius:0.1,fill:{color:i%2?'FFFFFF':TINT},line:{color:RULE,width:0.75}});
 s.addText(a,{x:MG+0.25,y:phy+0.1,w:2.5,h:0.85,fontFace:HF,fontSize:13.5,bold:true,color:GREEN,valign:'middle'});
 s.addText([{text:b+'  ',options:{bold:true,color:INK}},{text:c,options:{color:MUTE}}],{x:MG+2.9,y:phy+0.08,w:W-2*MG-3.1,h:0.9,fontFace:BF,fontSize:12.5,valign:'middle',lineSpacingMultiple:1.03}); phy+=1.16; }); foot(s,'Roadmap');

/* ===== 47 honest limitations ===== */
s=S(); kicker(s,'Honest limitations'); title(s,'Open decisions and known gaps'); rule(s);
s.addShape(p.ShapeType.roundRect,{x:MG,y:1.75,w:(W-2*MG-0.4)/2,h:4.0,rectRadius:0.1,fill:{color:'F7F3EC'},line:{color:'E4D8C4',width:0.75}});
s.addText('Inherited / unvalidated settings',{x:MG+0.3,y:1.9,w:5,h:0.4,fontFace:HF,fontSize:14.5,bold:true,color:AMBER});
bullets(s,['k = 6 — not justified by a sweep or ecological prior','seed = 42 · skewness threshold = 1.0','SNIC size / compactness / connectivity / neighbourhood','the 5 SNIC bands (not ablated)','10,000-superpixel training sample','distance-to-water cap (1000 px)','ASCENDING-only Sentinel-1'],
 {x:MG+0.35,y:2.35,w:(W-2*MG-0.4)/2-0.6,gap:7,fs:12.5});
const lx=MG+(W-2*MG-0.4)/2+0.4;
s.addShape(p.ShapeType.roundRect,{x:lx,y:1.75,w:(W-2*MG-0.4)/2,h:4.0,rectRadius:0.1,fill:{color:TINT},line:{color:RULE,width:0.75}});
s.addText('Structural gaps — next phase',{x:lx+0.3,y:1.9,w:5,h:0.4,fontFace:HF,fontSize:14.5,bold:true,color:GREEN});
bullets(s,['No validation framework beyond visual inspection and internal metrics — clusters not checked against an independent ground reference.','No parameter/feature sensitivity analysis yet — we don’t know how far the map moves when the constants move.','No committed falsifiable hypothesis — the framework produces stands but hasn’t stated a claim it could fail.'],
 {x:lx+0.35,y:2.35,w:(W-2*MG-0.4)/2-0.6,gap:12,fs:13}); foot(s,'Limitations');

/* ===== 48 conclusions ===== */
s=S(); kicker(s,'Conclusions'); title(s,'What we can honestly say'); rule(s);
const cn=[['A working, reproducible pipeline','FMU delineates forest stands from a multi-sensor time series, fully unsupervised, config-driven and cached in Earth Engine — baseline, optical variant and embedding arms all run end-to-end.'],
 ['Two controlled experiments','C-0 (optical variant) reshuffles moderately (ARI 0.49); C-1 (AlphaEarth) is more separable (silhouette −0.007 → +0.113) but delineates differently (ARI 0.17) and trades away interpretability.'],
 ['A methods comparison under label scarcity','The contribution is controlled representation comparisons + a per-stand consensus layer — honest about the absence of ground truth, not a claim that either map is "correct".']];
let cy=1.8; cn.forEach(([h,b],i)=>{ s.addShape(p.ShapeType.roundRect,{x:MG,y:cy,w:W-2*MG,h:1.25,rectRadius:0.1,fill:{color:i===1?'F7F3EC':TINT},line:{color:RULE,width:0.75}});
 s.addText((i+1)+'.  '+h,{x:MG+0.3,y:cy+0.12,w:W-2*MG-0.6,h:0.4,fontFace:HF,fontSize:15.5,bold:true,color:i===1?AMBER:GREEN});
 s.addText(b,{x:MG+0.3,y:cy+0.52,w:W-2*MG-0.6,h:0.7,fontFace:BF,fontSize:12.8,color:INK,lineSpacingMultiple:1.05}); cy+=1.4; }); foot(s,'Conclusions');

/* ===== 49 papers ===== */
s=S(); kicker(s,'Papers'); title(s,'Key papers — status'); rule(s);
s.addText('Confident (verified / in the deck reference list)',{x:MG,y:1.65,w:W-2*MG,h:0.35,fontFace:HF,fontSize:14,bold:true,color:GREEN});
bullets(s,[
 'AlphaEarth Foundations — Brown et al. 2025, arXiv:2507.22291.   TESSERA — Feng et al. 2025, arXiv:2506.20380.',
 'SVH origin — Palmer et al. 2002 (Environmetrics 13:121).   Rocchini et al. 2010 (Ecological Informatics 5:318).',
 '"Spectral species" — Féret & Asner 2014 (Ecological Applications 24:1289).   HVH — Torresani et al. 2020 (Ecological Indicators 117:106520).',
 'SVH falsification — Schmidtlein & Fassnacht 2017 (RSE, doi:10.1016/j.rse.2017.01.036).   SVH 20-yr review — Torresani et al. 2024.   Indian dry-forest SVH — Nagendra 2010 (doi:10.3390/rs2020478).',
],{y:2.05,gap:9,fs:12.5});
s.addText('To confirm with Claude Science (not asserted here)',{x:MG,y:4.35,w:W-2*MG,h:0.35,fontFace:HF,fontSize:14,bold:true,color:AMBER});
bullets(s,[
 'SVH design checklist "Wallis 2025" — exact reference?   Confounds: Wang 2017 (grain/scale) and Thornley 2022 (phenology).',
 'Indian forest-type reference maps: Roy 2015, Reddy 2015.   Delineation: Xiong 2024 (Silva Fennica), Sandum/Ørka 2026 (U-Net).',
 'Note: the Claude Science session cited "Rocchini 2004"; the v3.1 deck cites Rocchini 2010 — confirm which.',
],{y:4.75,gap:9,fs:12.5}); foot(s,'Papers');

/* ===== 50 references 1 ===== */
s=S(); kicker(s,'References'); title(s,'References (1 / 2)'); rule(s);
bullets(s,[
 '[1] Gorelick et al. 2017. Google Earth Engine. RSE 202, 18–27.',
 '[2] Drusch et al. 2012. Sentinel-2. RSE 120, 25–36.   [3] Torres et al. 2012. Sentinel-1 mission. RSE 120, 9–24.',
 '[4] Bansal et al. 2021. IndiaSat. ACM COMPASS, 147–155.   [5] Zanaga et al. 2022. ESA WorldCover v200.',
 '[6] Jakubauskas et al. 2001. Harmonic analysis of NDVI. PE&RS 67(4).   [7] Moody & Johnson 2001. DFT phenology. RSE 75(3).',
 '[8] Wilson et al. 2018. Harmonic regression of Landsat. ISPRS 137.   [9] Zhu & Woodcock 2014. CCDC. RSE 144.',
 '[10] Badgley et al. 2017. NIRv. Science Advances 3(3).   [11] Vreugdenhil et al. 2018. S1 backscatter & vegetation. RS 10(9).',
 '[12] Lang et al. 2023. Global canopy height. Nat. Ecol. Evol. 7(11).   [13] Dubayah et al. 2020. GEDI. Sci. Remote Sens. 1.',
 '[14] Pekel et al. 2016. Global surface water. Nature 540.   [15] Funk et al. 2015. CHIRPS. Scientific Data 2.',
 '[16] Farr et al. 2007. SRTM. Rev. Geophysics 45(2).   [17] Achanta & Süsstrunk 2017. SNIC. CVPR.',
],{y:1.7,gap:7,fs:11.5}); foot(s,'References');

/* ===== 51 references 2 ===== */
s=S(); kicker(s,'References'); title(s,'References (2 / 2)'); rule(s);
bullets(s,[
 '[18] Achanta et al. 2012. SLIC. IEEE TPAMI 34(11).   [19] Blaschke 2010. OBIA. ISPRS 65(1).',
 '[20] Hossain & Chen 2019. OBIA segmentation review. ISPRS 150.   [21] Kotaridis & Lazaridou 2021. Segmentation meta-analysis. ISPRS 173.',
 '[22] Lloyd 1982. k-means. IEEE IT 28(2).   [23] MacQueen 1967. Classification. Berkeley Symp.   [24] Arthur & Vassilvitskii 2007. k-means++. SODA.',
 '[25] Mardia & Jupp 2000. Directional Statistics. Wiley.   [26] Rousseeuw 1987. Silhouettes. JCAM 20.',
 '[27] Hubert & Arabie 1985. Comparing partitions (ARI). J. Classification 2(1).   [28] Vinh et al. 2010. Info-theoretic clustering (NMI). JMLR 11.',
 '[29] Kuhn 1955. Hungarian method. Naval Res. Logistics 2.   [30] Palmer et al. 2002. Species lists. Environmetrics 13(2).',
 '[31] Rocchini et al. 2010. Spectral heterogeneity as diversity proxy. Ecol. Informatics 5(5).   [32] Féret & Asner 2014. Canopy diversity. Ecol. Applications 24(6).',
 '[33] Torresani et al. 2020. Height Variation Hypothesis. Ecol. Indicators 117.   [34] Torresani et al. 2024. Reviewing the SVH. Ecol. Informatics.',
 '[35] Brown et al. 2025. AlphaEarth Foundations. arXiv:2507.22291.   [36] Feng et al. 2025. TESSERA. arXiv:2506.20380.',
 '[37] Schmidtlein & Fassnacht 2017. SVH test. RSE.   [38] Nagendra 2010. Spectral diversity, Indian forest. Remote Sensing 2(2).',
],{y:1.7,gap:6.5,fs:11}); foot(s,'References');

/* ===== 52 glossary 1 ===== */
s=S(); kicker(s,'Glossary'); title(s,'Every term, defined (1 / 2)'); rule(s);
bullets(s,[
 'NDVI — (NIR − Red)/(NIR + Red); greenness, −1 to 1.   NIRv — NDVI × NIR; productivity proxy, less soil/saturation confounded.',
 'Harmonic amplitude — √(b²+c²); size of the yearly swing.   Phase — atan2(c,b); timing of peak greenness (split sin/cos).',
 'Trend — linear per-year term; multi-year greening (+) / browning (−).   residual_variance — harmonic-fit residual variance; diagnostic, not clustered.',
 'VV / VH — co- / cross-pol C-band backscatter (dB).   p10/p50/p90 — low/median/high backscatter over the series.',
 'IQR (p90 − p10) — temporal spread of backscatter.   Cross-pol contrast — VV median − VH median (dB).',
 'Canopy height — ETH 10 m value (m).   Canopy roughness (_std) / _max — std / max in a 3×3 window.',
 'Elevation / slope / aspect — NASADEM terrain; aspect split sin/cos.   distance_to_water — metres to nearest JRC permanent water (capped).',
 'annual_rainfall — CHIRPS climatological mean; computed but not clustered.   Habitat mask — binary forest/shrub layer applied before clustering.',
],{y:1.7,gap:8,fs:12}); foot(s,'Glossary');

/* ===== 53 glossary 2 ===== */
s=S(); kicker(s,'Glossary'); title(s,'Every term, defined (2 / 2)'); rule(s);
bullets(s,[
 'Superpixel / SNIC — a segment of adjacent, similar pixels; SNIC (Simple Non-Iterative Clustering) makes them.',
 'z-score / standardise — (x − mean)/spread.   Robust scaling — (x − median)/IQR; outlier-resistant.   Log-transform — for right-skewed bands.',
 'Cyclic sin/cos — splitting an angle so 0° and 360° aren’t "far apart".   k-means / k-means++ — partition into k groups; ++ spreads initial centres.',
 'Silhouette — internal cohesion vs separation, −1 to 1; no labels.   ARI — chance-corrected agreement of two partitions, −1 to 1.',
 'NMI — information shared by two partitions, 0 to 1.   Hungarian — optimal one-to-one matching of cluster IDs.',
 'Embedding — a learned per-pixel feature vector (AlphaEarth 64-D, TESSERA 128-D).   Agreement map — per-pixel 0/1 match after Hungarian alignment.',
 'Confidence — per-stand mean of the agreement map (consensus, not correctness).   AOI — area of interest.',
 'SVH / HVH — Spectral / Height Variation Hypothesis: spectral or structural heterogeneity as a biodiversity proxy.   Alpha / Beta diversity — within-unit richness / between-unit turnover.',
],{y:1.7,gap:8,fs:12}); foot(s,'Glossary');

p.writeFile({fileName: REPO + '/FMU_master_deck.pptx'}).then(f=>console.log('WROTE', SN, 'slides ->', REPO+'/FMU_master_deck.pptx')).catch(e=>{console.error('ERR',e); process.exit(1);});
