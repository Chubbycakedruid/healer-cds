"""Static single-file HTML dashboard."""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Healer Cooldown Planner</title>
<style>
:root{
  color-scheme: light dark;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10);
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4; --s6:#008300; --s7:#4a3aa7; --s8:#e34948;
  --dmg:#6da7ec; --dmg-fill:rgba(109,167,236,.28); --phase:rgba(11,11,11,.035);
  --good:#0ca30c; --warn:#fab219; --bad:#d03b3b;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#008300; --s7:#9085e9; --s8:#e66767;
  --dmg:#5598e7; --dmg-fill:rgba(85,152,231,.25); --phase:rgba(255,255,255,.05);
}}
:root[data-theme="dark"]{
  --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#008300; --s7:#9085e9; --s8:#e66767;
  --dmg:#5598e7; --dmg-fill:rgba(85,152,231,.25); --phase:rgba(255,255,255,.05);
}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;background:var(--page);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header{padding:20px 28px 0;display:flex;align-items:baseline;gap:18px;flex-wrap:wrap}
header h1{font-size:20px;margin:0}
header .meta{color:var(--ink2);font-size:13px}
nav{padding:12px 28px 0;display:flex;gap:8px;flex-wrap:wrap}
nav button{background:var(--surface);color:var(--ink);border:1px solid var(--border);border-radius:8px;padding:7px 14px;cursor:pointer;font:inherit}
nav button[aria-selected="true"]{border-color:var(--s1);box-shadow:inset 0 0 0 1px var(--s1)}
main{padding:16px 28px 40px;display:grid;gap:16px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px}
.card h2{font-size:15px;margin:0 0 10px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile .v{font-size:24px;font-weight:600}
.tile .l{color:var(--ink2);font-size:12px}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--ink2);font-size:12px;margin:6px 0 10px}
.legend span i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px}
.tl-wrap{overflow-x:auto}
svg text{font:11px system-ui,-apple-system,"Segoe UI",sans-serif;fill:var(--muted)}
svg .lane-label{fill:var(--ink);font-size:12px}
svg .phase-label{fill:var(--ink2);font-size:11px}
.tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:12px;box-shadow:0 4px 18px rgba(0,0,0,.18);max-width:320px;display:none;z-index:10}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:6px 8px;text-align:left;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--ink2);font-weight:600;font-size:12px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;border:1px solid var(--border);color:var(--ink2)}
.pill.major{border-color:var(--s1);color:var(--ink)}
.pill.clash{border-color:var(--warn);color:var(--ink2)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:-1px}
pre{background:var(--page);border:1px solid var(--border);border-radius:8px;padding:12px;overflow:auto;font:12.5px/1.5 ui-monospace,Menlo,Consolas,monospace;margin:0;white-space:pre-wrap}
.notebar{display:flex;align-items:center;gap:8px;margin:12px 0 6px}
.notebar h3{font-size:13px;margin:0;flex:1}
button.copy{background:var(--s1);color:#fff;border:0;border-radius:6px;padding:5px 10px;cursor:pointer;font:inherit;font-size:12px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:900px){.two{grid-template-columns:1fr}}
.conf{height:6px;border-radius:3px;background:var(--grid);position:relative;min-width:60px}
.conf i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:var(--s1)}
a{color:var(--s1)}
.muted{color:var(--muted)}
.filterbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.viewbar{display:flex;gap:6px;align-items:center;flex-wrap:wrap;border-bottom:1px solid var(--border);padding-bottom:10px}
.vtab{background:none;border:0;border-bottom:2px solid transparent;padding:6px 10px;font:inherit;font-size:14px;color:var(--ink2);cursor:pointer}
.vtab[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--s1);font-weight:600}
.help{color:var(--muted);font-size:12px;margin-left:12px;flex:1;min-width:240px}
.thresh{margin-left:auto;display:flex;gap:8px;align-items:center;font-size:13px}
.thresh input{width:160px}
.chip{background:var(--surface);color:var(--ink);border:1px solid var(--border);border-radius:999px;padding:5px 12px;cursor:pointer;font:inherit;font-size:13px}
.chip[aria-pressed="true"]{background:var(--s1);color:#fff;border-color:var(--s1)}
.chip.small{padding:2px 9px;font-size:12px}
.picks{display:flex;gap:6px 14px;flex-wrap:wrap;align-items:center;margin:0 0 8px;padding:8px 10px;border:1px solid var(--border);border-radius:8px}
.pick{font-size:13px;white-space:nowrap}
td.cell{font-size:12px;white-space:nowrap;text-align:right}
td.cell.ok{color:var(--good)} td.cell.late{color:#b87700} td.cell.miss{color:var(--bad);font-weight:600} td.cell.na{color:var(--muted)}
</style>
</head>
<body>
<header>
  <h1>Healer Cooldown Planner</h1>
  <div class="meta" id="meta"></div>
</header>
<nav id="tabs" role="tablist"></nav>
<main id="main"></main>
<div class="tip" id="tip"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const SERIES = ['--s1','--s2','--s3','--s4','--s5','--s6','--s7','--s8'];
const fmt = s => { s=Math.max(0,Math.round(s)); return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); };
const esc = s => String(s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const tip = document.getElementById('tip');
function showTip(e, html){ tip.innerHTML=html; tip.style.display='block'; moveTip(e); }
function moveTip(e){ const w=tip.offsetWidth,h=tip.offsetHeight; let x=e.clientX+14,y=e.clientY+14;
  if(x+w>innerWidth-8) x=e.clientX-w-14; if(y+h>innerHeight-8) y=e.clientY-h-14; tip.style.left=x+'px'; tip.style.top=y+'px'; }
function hideTip(){ tip.style.display='none'; }

document.getElementById('meta').textContent =
  `${DATA.guild} · ${DATA.difficulty} · generated ${DATA.generated}` + (DATA.pulls_refreshed ? ` · our pulls refreshed ${DATA.pulls_refreshed}` : '') + (DATA.demo ? ' · DEMO DATA (synthetic)' : '');

const tabs = document.getElementById('tabs'); const main = document.getElementById('main');
const BOSSES=[...new Set(DATA.bosses.map(b=>b.name))]; let curBoss=BOSSES[0], curDiff=null;
function entriesFor(name){ return DATA.bosses.filter(b=>b.name===name); }
function renderTabs(){ tabs.innerHTML=''; BOSSES.forEach(n=>{ const btn=document.createElement('button'); btn.role='tab'; btn.textContent=n;
  btn.setAttribute('aria-selected', n===curBoss); btn.onclick=()=>{ curBoss=n; curDiff=null; who=null; selectCurrent(); }; tabs.appendChild(btn); }); }
function selectCurrent(){ const es=entriesFor(curBoss); const diffs=es.map(e=>(e.difficulty||'').toLowerCase());
  if(!curDiff||!diffs.includes(curDiff)) curDiff=diffs.includes('heroic')?'heroic':diffs[0];
  cur=DATA.bosses.indexOf(es.find(e=>(e.difficulty||'').toLowerCase()===curDiff)); renderTabs(); render(DATA.bosses[cur]); }
let cur=0, who=null, nsrtMinor=false, nsrtWho=null, minSup=DATA.min_support||0.4, nsrtSource='plan', view='plan';
const VIEWS=[['plan','Plan'],['timeline','Timeline'],['pulls','Our pulls'],['data','Data']];
const HELP={plan:'Each mechanic (from the boss\'s own casts in the kills) gets the cooldowns the kill healers actually used there, from whoever in our team has it free. One cooldown, one timer, whole fight. Below: the team note and each healer\'s personal NSRT note.',
 timeline:'What the matched kills\' healers pressed and when, over the average raid damage. Marker size = how many kills agree; hollow = clashes with the ability\'s own cooldown. Notes here copy the kills rather than the team plan.',
 pulls:'Our recent pulls against the plan: green on time, amber early/late, red missed while alive, grey wiped before it was due. Plus who died to what.',
 data:'The kills the analysis is built on, and anything the logs contain that the config files do not know about.'};
// which abilities go on the NSRT note, per spec: {spec: {ability: bool}}. Remembered in this browser.
let picks={}; try{ picks=JSON.parse(localStorage.getItem('nsrtPicks')||'{}'); }catch(e){}
function savePicks(){ try{ localStorage.setItem('nsrtPicks', JSON.stringify(picks)); }catch(e){} }
const TIER_ORDER={major:0,minor:1,discovered:2};
function specAbilities(b, spec){ const m=new Map(); b.clusters.filter(c=>c.spec===spec).forEach(c=>{ if(!m.has(c.ability)) m.set(c.ability,{tier:c.tier,id:c.ability_id}); }); return [...m.entries()].sort((x,y)=>(TIER_ORDER[x[1].tier]-TIER_ORDER[y[1].tier])||x[0].localeCompare(y[0])); }
function picked(spec, ability, tier, dflt){ const p=picks[spec]||{}; return ability in p ? p[ability] : (dflt!==undefined ? dflt : tier==='major'); }
// abilities the team plan assigns to this healer, so the tick row can list them in plan mode
function planAbilities(b, h){ const m=new Map(); planFor(b,h.name).forEach(a=>{ if(!m.has(a.ability)) m.set(a.ability,{tier:'planned',id:a.ability_id}); }); return [...m.entries()]; }
function select(i){ curBoss=DATA.bosses[i].name; curDiff=(DATA.bosses[i].difficulty||'').toLowerCase(); selectCurrent(); }
function rerender(){ render(DATA.bosses[cur]); }

function filterNote(text){
  if(!who) return text;
  const lines=text.split('\n'); const out=[lines[0]];
  for(const l of lines.slice(1)){
    const m=l.match(/^(\{time:[^}]*\})\s(.*)$/); if(!m){ out.push(l); continue; }
    const parts=m[2].split(/\s{2,}/).filter(p=>p.split(' ')[0].split('/').includes(who));
    if(parts.length) out.push(m[1]+' '+parts.join('  '));
  }
  return out.join('\n');
}
function filterPlan(text){
  if(!who) return text;
  return text.split('\n').filter(l=>l.trim().split(/\s+/).slice(2).some(w=>w.split('/').includes(who)) && l.includes(' '+who)).join('\n');
}
function visibleHealers(b){ return who ? b.ours.healers.filter(h=>h.name===who) : b.ours.healers; }
function supported(b){ return b.clusters.filter(c=>c.support/c.total >= minSup - 1e-9); }
// A note is a plan for ONE player, so two timings of the same ability closer together than its
// cooldown cannot both be pressed. For each (spec, ability) keep the set of timings that respects
// the cooldown and carries the most kill-agreement (weighted interval scheduling).
function feasible(b){
  const cs=supported(b); const keep=new Set(); const groups={};
  cs.forEach(c=>{ (groups[c.spec+'|'+c.ability]=groups[c.spec+'|'+c.ability]||[]).push(c); });
  for(const key in groups){
    const g=groups[key].sort((x,y)=>x.abs_median-y.abs_median); const cd=(g[0].cd||60)*0.9; // 10% leeway for CDR / timing noise
    const n=g.length, best=new Array(n+1).fill(0), take=new Array(n+1).fill(false), prev=new Array(n).fill(-1);
    for(let i=0;i<n;i++){ for(let j=i-1;j>=0;j--){ if(g[i].abs_median-g[j].abs_median>=cd){ prev[i]=j; break; } } }
    for(let i=0;i<n;i++){ const w=g[i].support+0.001*(g[i].tier==='major'); const withIt=w+best[prev[i]+1];
      if(withIt>best[i]){ best[i+1]=withIt; take[i+1]=true; } else { best[i+1]=best[i]; take[i+1]=false; } }
    let i=n; while(i>0){ if(take[i]){ keep.add(g[i-1]); i=prev[i-1]+1; } else i--; }
  }
  return keep;
}
function isFeasible(b,c){ if(!b._feas || b._feasSup!==minSup){ b._feas=feasible(b); b._feasSup=minSup; } return b._feas.has(c); }
// Short cooldowns (Convoke, Flourish, Divine Toll...) get pressed far more often than the kills agree on:
// the timings differ from guild to guild, so consensus only keeps two or three. Fill the gaps: wherever a
// chosen ability would sit ready for longer than its cooldown, add a use at the heaviest damage moment in that
// window, preferring a low-agreement timing from the kills if one falls there. Rows added this way carry fill:true.
let fillOn=true; try{ fillOn=localStorage.getItem('fillGaps')!=='0'; }catch(e){}
function phaseAt(b,t){ const ph=b.phases_ref||[]; let cur=null; for(const [pid,start] of ph){ if(t>=start-1e-6) cur=[pid,start]; } return cur; }
function withPhase(b,row){ const p=phaseAt(b,row.abs_median); if(b.use_phases && p){ row.phase=p[0]; row.median=row.abs_median-p[1]; } else { row.phase=null; row.median=row.abs_median; } return row; }
function fightLength(b){ const d=b.kills.map(k=>k.duration).sort((x,y)=>x-y); return d.length ? d[Math.floor(d.length/2)] : 0; }
function fillGaps(b, rows){
  if(!fillOn) return rows;
  const end=fightLength(b)-8; if(end<=0) return rows;
  const dmg=b.damage||[]; const out=rows.slice();
  const groups={}; rows.forEach(r=>{ (groups[r.spec+'|'+r.ability]=groups[r.spec+'|'+r.ability]||[]).push(r); });
  for(const key in groups){
    const g=groups[key].sort((x,y)=>x.abs_median-y.abs_median); const cd=g[0].cd||60; if(cd>180) continue;
    const spec=g[0].spec, ability=g[0].ability;
    const weak=b.clusters.filter(c=>c.spec===spec&&c.ability===ability&&!g.includes(c)); // low-agreement timings from the kills
    const times=g.map(r=>r.abs_median); let guard=0;
    for(let i=0;i<=times.length && guard<40;i++,guard++){
      const lo=(i===0?0:times[i-1]+cd), hi=(i<times.length?times[i]-cd:end);
      if(hi-lo<12) continue;
      // best moment: a kill timing in the window if any, else the damage peak inside it
      let t=null; const w=weak.filter(c=>c.abs_median>=lo&&c.abs_median<=hi).sort((x,y)=>y.support-x.support)[0];
      if(w){ t=w.abs_median; weak.splice(weak.indexOf(w),1); } else { let best=-1; for(const [tt,v] of dmg){ if(tt>=lo+2&&tt<=hi&&v>best){ best=v; t=tt; } } }
      if(t==null) continue;
      const row=withPhase(b,{spec,ability,ability_id:g[0].ability_id,tier:g[0].tier,cd,abs_median:t,support:w?w.support:0,total:g[0].total,spread:0,mechanic:w?w.mechanic:null,fill:true,src:w?'kills':'damage'});
      out.push(row); times.splice(i,0,t); i--; guard++; // re-check the window after the new use
      if(guard>40) break;
    }
  }
  return out;
}
function visibleClusters(b){ const cs=supported(b); if(!who) return cs; const specs=new Set(visibleHealers(b).map(h=>h.spec)); return cs.filter(c=>specs.has(c.spec)); }
function healerNames(b){ const m={}; b.ours.healers.forEach(h=>{m[h.spec]=(m[h.spec]?m[h.spec]+'/':'')+h.name;}); return m; }
function timeTag(b,c,phased){ return (phased && b.use_phases && c.phase!=null) ? `{time:${fmt(c.median)},p${c.phase}}` : `{time:${fmt(c.abs_median)}}`; }
function sortKey(b,c,phased){ return (phased && b.use_phases && c.phase!=null) ? c.phase*100000+c.median : c.abs_median; }
function buildNote(b, phased, includeMinor){
  const names=healerNames(b);
  const rows=fillGaps(b, visibleClusters(b).filter(c=>isFeasible(b,c)&&(c.tier==='major'||(includeMinor&&c.tier==='minor')))).sort((x,y)=>sortKey(b,x,phased)-sortKey(b,y,phased));
  const lines=[]; let last=null;
  for(const c of rows){
    const part=`${names[c.spec]||c.spec} {spell:${c.ability_id}}`;
    if(last && Math.abs(sortKey(b,c,phased)-sortKey(b,last,phased))<=3){ lines[lines.length-1]+='  '+part; }
    else lines.push(`${timeTag(b,c,phased)} ${part}`);
    last=c;
  }
  return [`{star} ${b.name} healer CDs {star}`,...lines].join('\n');
}
function buildPlan(b){
  const names=healerNames(b);
  return fillGaps(b, visibleClusters(b).filter(c=>isFeasible(b,c))).sort((x,y)=>sortKey(b,x,true)-sortKey(b,y,true)).map(c=>{
    const when=(b.use_phases&&c.phase!=null)?`P${c.phase} ${fmt(c.median)}`:fmt(c.abs_median);
    const why=c.fill?(c.src==='kills'?`(off cooldown; ${c.support}/${c.total} kills used it here)`:'(off cooldown; heaviest damage in the gap)'):`(${c.support}/${c.total} kills, spread ${Math.round(c.spread)}s)`;
    return `${when.padStart(10)}  ${(names[c.spec]||c.spec).padEnd(16)} ${c.ability}${c.tier==='major'?'':' ['+c.tier+']'}${c.mechanic?' for '+c.mechanic:''}  ${why}`;
  }).join('\n');
}
function planB(b,h){
  const ex=b.exemplars[h.spec]; const diff=(b.difficulty||DATA.difficulty||'heroic'); const D=diff.charAt(0).toUpperCase()+diff.slice(1).toLowerCase();
  const rows=ex.casts.filter(c=>picked(h.spec,c.ability,'major'));
  const usePh=b.use_phases && rows.every(c=>c.phase!=null);
  const out=[`EncounterID:${b.encounter_id};Difficulty:${D};Name:${b.name};`];
  rows.forEach(c=>out.push(`ph:${usePh?c.phase:1};time:${(usePh?c.t_in_phase:c.t).toFixed(1)};tag:${h.name};spellid:${c.ability_id};`));
  return noteBlock(`Plan B: copy ${esc(ex.player)} exactly <span class="muted" style="font-weight:400">(<a href="${ex.url}" target="_blank" rel="noopener">${esc(ex.guild)}</a>, ${fmt(ex.duration)} kill, the single ${esc(h.spec)} whose sequence sits closest to the consensus)</span>`, out.join('\n'),
    'One real player\'s actual sequence rather than an average. Internally consistent by construction, so use this if the consensus note feels stitched together.');
}
function buildNsrtPlan(b,h){
  const diff=(b.difficulty||DATA.difficulty||'heroic'); const D=diff.charAt(0).toUpperCase()+diff.slice(1).toLowerCase();
  const out=[`EncounterID:${b.encounter_id};Difficulty:${D};Name:${b.name};`];
  const cdOf={}; b.clusters.forEach(c=>{ if(c.spec===h.spec) cdOf[c.ability]=c.cd; });
  const rows=planFor(b,h.name).filter(a=>picked(h.spec,a.ability,'planned',true)).map(a=>{ const o=b.mechanics[a.occ];
    return withPhase(b,{spec:h.spec,ability:a.ability,ability_id:a.ability_id,tier:'planned',cd:cdOf[a.ability]||a.cd||60,abs_median:o.abs_t,support:0,total:o.total,spread:0}); });
  fillGaps(b,rows).sort((x,y)=>sortKey(b,x,true)-sortKey(b,y,true)).forEach(r=>{ const ph=(b.use_phases&&r.phase!=null)?r.phase:1; const t=(b.use_phases&&r.phase!=null)?r.median:r.abs_median;
    out.push(`ph:${ph};time:${t.toFixed(1)};tag:${h.name};spellid:${r.ability_id};`); });
  return out.join('\n');
}
function buildNsrt(b, h){
  if(nsrtSource==='plan' && (b.mechanics||[]).length) return buildNsrtPlan(b,h);
  const rows=fillGaps(b, supported(b).filter(c=>c.spec===h.spec && isFeasible(b,c) && picked(h.spec,c.ability,c.tier)))
    .sort((x,y)=>sortKey(b,x,true)-sortKey(b,y,true));
  const diff=(b.difficulty||DATA.difficulty||'heroic'); const D=diff.charAt(0).toUpperCase()+diff.slice(1).toLowerCase();
  const out=[`EncounterID:${b.encounter_id};Difficulty:${D};Name:${b.name};`];
  for(const c of rows){ const ph=(b.use_phases&&c.phase!=null)?c.phase:1; const t=(b.use_phases&&c.phase!=null)?c.median:c.abs_median;
    out.push(`ph:${ph};time:${t.toFixed(1)};tag:${h.name};spellid:${c.ability_id};`); }
  return out.join('\n');
}

function specColors(boss){ const m={}; const specs=[...new Set(boss.ours.healers.map(h=>h.spec))];
  specs.forEach((s,i)=>m[s]=`var(${SERIES[i%SERIES.length]})`); return m; }

function render(b){
  b._feas=null;
  const col = specColors(b);
  const majors = visibleClusters(b).filter(c=>c.tier==='major').length;
  main.innerHTML = '';
  // ---- difficulty switch
  const es=entriesFor(b.name); const db=document.createElement('div'); db.className='filterbar';
  db.innerHTML='<span class="muted">Difficulty:</span>'+['heroic','mythic','normal'].filter(d=>es.some(e=>(e.difficulty||'').toLowerCase()===d)).map(d=>
    `<button class="chip dchip" data-v="${d}" aria-pressed="${d===curDiff}">${d.charAt(0).toUpperCase()+d.slice(1)}</button>`).join('')+
    (es.length<2?`<span class="muted" style="font-size:12px">only ${curDiff} had enough kill data for this boss</span>`:'');
  db.querySelectorAll('.dchip').forEach(c=>c.onclick=()=>{ curDiff=c.dataset.v; selectCurrent(); });
  main.appendChild(db);
  // ---- player filter
  const fb=document.createElement('div'); fb.className='filterbar';
  fb.innerHTML='<span class="muted">Show:</span>'+[['All healers',null],...b.ours.healers.map(h=>[h.name,h.name])].map(([l,v])=>
    `<button class="chip" data-v="${v??''}" aria-pressed="${who===v}">${esc(l)}</button>`).join('');
  fb.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{ who=c.dataset.v||null; rerender(); });
  const th=document.createElement('label'); th.className='thresh';
  th.innerHTML=`<span class="muted">Detail:</span> <input type="range" id="minSup" min="0.15" max="0.8" step="0.05" value="${minSup}">
    <span id="minSupLabel">${Math.round(minSup*100)}% of kills must agree</span>`;
  fb.appendChild(th);
  const sl=th.querySelector('#minSup'); sl.oninput=()=>{ minSup=parseFloat(sl.value); rerender(); };
  main.appendChild(fb);
  const vb=document.createElement('div'); vb.className='viewbar';
  vb.innerHTML=VIEWS.map(([v,l])=>`<button class="vtab" data-v="${v}" aria-selected="${view===v}">${l}</button>`).join('')+`<span class="help">${HELP[view]}</span>`;
  vb.querySelectorAll('.vtab').forEach(c=>c.onclick=()=>{ view=c.dataset.v; rerender(); });
  main.appendChild(vb);
  const show = v => view===v;
  // ---- tiles
  const tiles = document.createElement('div'); tiles.className='tiles'; tiles.hidden = !show('data');
  const t = (v,l)=>`<div class="card tile"><div class="v">${v}</div><div class="l">${l}</div></div>`;
  tiles.innerHTML = t(b.kills.length,'matched kills analysed') + t(fmt(b.target_duration),'target kill time')
    + t(majors,'major CD timings found') + t(b.ours.pulls,`our pulls scanned${b.ours.best_pct!=null?` · best ${b.ours.best_pct.toFixed(1)}%`:''}`)
    + t(b.use_phases?'phase':'absolute','timing reference');
  main.appendChild(tiles);

  // ---- team coverage plan
  if(show('plan') && b.mythic_healers){ const mh=b.mythic_healers; const hc=document.createElement('div'); hc.className='card';
    hc.innerHTML=`<h2>Mythic healer count <span class="muted" style="font-weight:400">· ${mh.kills} Mythic kills</span></h2>
      <div class="tiles"><div class="tile"><div class="v">${mh.suggested} healers</div><div class="l">what most Mythic kill teams ran (${Math.round(mh.distribution[0].share*100)}% of kills)</div></div>`+
      mh.distribution.map(d=>`<div class="tile"><div class="v">${d.healers}</div><div class="l">healers · ${d.kills} kills · median kill ${fmt(d.median_kill)} · fastest ${fmt(d.fastest)}</div></div>`).join('')+`</div>
      <p class="muted" style="margin:8px 0 0">Mythic is fixed at 20 players so this is a real choice there. Heroic flexes 10 to 30 and is not shown. Only appears when there are enough Mythic kills to say anything.</p>`;
    main.appendChild(hc); }
  if(show('plan') && !(b.mechanics||[]).length){ const tp=document.createElement('div'); tp.className='card'; tp.innerHTML='<h2>Team plan</h2><p class="muted">This run had no boss cast data for this boss, so there is no mechanic-by-mechanic plan yet. The next full run builds it from the boss\'s own casts in the kill logs. The Timeline tab has the consensus notes in the meantime.</p>'; main.appendChild(tp); }
  if(show('plan') && (b.mechanics||[]).length){ const tp=document.createElement('div'); tp.className='card'; tp.innerHTML=teamPlan(b,col); main.appendChild(tp);
    tp.querySelectorAll('button.copy').forEach(btn=>btn.onclick=()=>{navigator.clipboard.writeText(btn.dataset.text).then(()=>{btn.textContent='Copied';setTimeout(()=>btn.textContent='Copy',1200);});}); }

  // ---- timeline
  const card = document.createElement('div'); card.className='card'; card.hidden=!show('timeline');
  card.innerHTML = `<h2>Cooldown timeline vs average raid damage taken</h2>
    <div class="legend">${b.ours.healers.map(h=>`<span><i style="background:${col[h.spec]}"></i>${esc(h.name)} · ${esc(h.spec)}</span>`).join('')}
    <span><i style="background:var(--dmg)"></i>avg damage taken (matched kills)</span>
    <span class="muted">marker size = how many kills agree · hollow = clashes with the ability's cooldown, left off notes</span></div><div class="tl-wrap"></div>`;
  card.querySelector('.tl-wrap').appendChild(timeline(b, col));
  main.appendChild(card);

  // ---- notes + table
  const two = document.createElement('div'); two.className='two'; two.hidden=!show('timeline');
  const notes = document.createElement('div'); notes.className='card';
  notes.innerHTML = `<h2>Raid notes (paste into MRT / Liquid / Northern Sky)</h2><p class="muted" style="margin:0 0 4px">Major cooldowns only, unless "include minor" is ticked below.</p>` +
    noteBlock('Phase-relative timers', buildNote(b,true,nsrtMinor), b.use_phases ? '' : 'Phase data was not available for enough kills, absolute timers are the reliable option here.') +
    noteBlock('Absolute timers from pull', buildNote(b,false,nsrtMinor)) +
    noteBlock('Plain plan for the healing channel', buildPlan(b));
  two.appendChild(notes);

  const tbl = document.createElement('div'); tbl.className='card';
  tbl.innerHTML = `<h2>Every recurring usage in the kills</h2>` + clusterTable(b, col);
  two.appendChild(tbl);
  main.appendChild(two);

  // ---- NSRT personal notes
  const ns=document.createElement('div'); ns.className='card'; ns.hidden=!show('plan');
  const pick = who || nsrtWho || (b.ours.healers[0]||{}).name;
  const h = b.ours.healers.find(x=>x.name===pick) || b.ours.healers[0];
  ns.innerHTML=`<h2>Personal NSRT note</h2>
    <div class="filterbar" style="margin-bottom:8px">${b.ours.healers.map(x=>`<button class="chip nchip" data-v="${esc(x.name)}" aria-pressed="${x.name===h.name}">${esc(x.name)}</button>`).join('')}
    </div>
    ${h ? `<div class="picks">${(nsrtSource==='plan'&&(b.mechanics||[]).length ? planAbilities(b,h) : specAbilities(b,h.spec)).map(([a,m])=>`<label class="pick"><input type="checkbox" data-a="${esc(a)}" ${picked(h.spec,a,m.tier,m.tier==='planned'?true:undefined)?'checked':''}> ${esc(a)} <span class="muted">${m.tier==='discovered'?'seen in logs':m.tier==='planned'?'in plan':m.tier}</span></label>`).join('')}
      <button class="chip small" id="pickMajors">majors only</button><button class="chip small" id="pickAll">all</button>
      <label class="pick" style="margin-left:auto" title="Short cooldowns get pressed far more often than the kills agree on. With this on, every gap longer than the cooldown gets an extra use at the heaviest damage in that gap (or at a timing some kills used)."><input type="checkbox" id="fillGaps" ${fillOn?'checked':''}> use short cooldowns every time they're up</label></div>` : ''}
    ${(b.mechanics||[]).length?`<div class="filterbar" style="margin-bottom:8px"><span class="muted">Source:</span><button class="chip small src" data-v="plan" aria-pressed="${nsrtSource==='plan'}">team plan (by mechanic)</button><button class="chip small src" data-v="consensus" aria-pressed="${nsrtSource==='consensus'}">consensus (copy the kills)</button></div>`:''}
    ${b.use_phases?'':'<p class="muted" style="margin:0 0 8px">No phase data for this boss, so everything is under ph:1 with time from pull.</p>'}` +
    (h ? noteBlock(`${esc(h.name)} · ${esc(h.spec)} <span class="muted" style="font-weight:400">(${(b.kills_with_spec||{})[h.spec]??'?'} of ${b.kills.length} kills had a ${esc(h.spec)})</span>`, buildNsrt(b,h)) : '') +
    (h && nsrtSource!=='plan' && (b.exemplars||{})[h.spec] ? planB(b,h) : '');
  main.appendChild(ns);
  ns.querySelectorAll('.nchip').forEach(c=>c.onclick=()=>{ nsrtWho=c.dataset.v; if(who && who!==nsrtWho) who=null; rerender(); });
  ns.querySelectorAll('.src').forEach(c=>c.onclick=()=>{ nsrtSource=c.dataset.v; rerender(); });
  if(h && ns.querySelector('#pickMajors')){
    ns.querySelectorAll('.pick input').forEach(cb=>cb.onchange=()=>{ (picks[h.spec]=picks[h.spec]||{})[cb.dataset.a]=cb.checked; savePicks(); rerender(); });
    ns.querySelector('#pickMajors').onclick=()=>{ picks[h.spec]={}; savePicks(); rerender(); };
    ns.querySelector('#fillGaps').onchange=e=>{ fillOn=e.target.checked; try{ localStorage.setItem('fillGaps', fillOn?'1':'0'); }catch(err){} rerender(); };
    ns.querySelector('#pickAll').onclick=()=>{ picks[h.spec]={}; specAbilities(b,h.spec).forEach(([a])=>picks[h.spec][a]=true); planAbilities(b,h).forEach(([a])=>picks[h.spec][a]=true); savePicks(); rerender(); };
  }

  // ---- our pulls vs plan
  if(show('pulls')){ const pc=document.createElement('div'); pc.className='card'; pc.innerHTML=(b.our_pulls||[]).length?ourPulls(b,col):'<h2>Our pulls</h2><p class="muted">No pulls of this boss in our recent logs yet.</p>'; main.appendChild(pc); }

  // ---- kills
  const kc = document.createElement('div'); kc.className='card'; kc.hidden=!show('data');
  kc.innerHTML = `<h2>Kills used (best comp match first)</h2><table><thead><tr><th>Guild</th><th>Region</th><th class="num">Kill time</th><th class="num">Match</th><th>Healers</th><th>Notes</th></tr></thead><tbody>` +
    b.kills.map(k=>`<tr><td><a href="${k.url}" target="_blank" rel="noopener">${esc(k.guild)}</a></td><td>${esc(k.region||'')}</td><td class="num">${fmt(k.duration)}</td>
      <td class="num">${(k.score*100).toFixed(0)}%</td><td>${k.healer_specs.map(s=>`<span class="dot" style="background:${col[s]||'var(--muted)'}"></span>${esc(s)}`).join('<br>')}</td><td class="muted">${esc(k.notes)}</td></tr>`).join('') +
    `</tbody></table>`;
  main.appendChild(kc);
  if (b.discovered && b.discovered.length){
    const d=document.createElement('div'); d.className='card'; d.hidden=!show('data');
    d.innerHTML=`<h2>Abilities found in the data that are not in cooldowns.toml</h2><p class="muted">Used rarely per kill by these specs. If one is a real cooldown, add it to cooldowns.toml so it goes on the note.</p><ul>`+
      b.discovered.map(x=>`<li>${esc(x)}</li>`).join('')+'</ul>'; main.appendChild(d);
  }
  document.querySelectorAll('button.copy').forEach(btn=>btn.onclick=()=>{
    navigator.clipboard.writeText(btn.dataset.text).then(()=>{btn.textContent='Copied';setTimeout(()=>btn.textContent='Copy',1200);});});
}

function occWhen(b,o){ return (b.use_phases && o.phase!=null) ? `P${o.phase} ${fmt(o.t)}` : fmt(o.abs_t); }
function occTag(b,o){ return (b.use_phases && o.phase!=null) ? `{time:${fmt(o.t)},p${o.phase}}` : `{time:${fmt(o.abs_t)}}`; }
function planFor(b, healerName){ return (b.team_plan?.assignments||[]).filter(a=>a.healer===healerName); }
function teamNote(b){
  const by={}; (b.team_plan?.assignments||[]).forEach(a=>{ (by[a.occ]=by[a.occ]||[]).push(a); });
  const lines=[`{star} ${b.name} healer plan {star}`];
  b.mechanics.forEach((o,i)=>{ const as=(by[i]||[]).filter(a=>!who||a.healer===who); if(!as.length) return;
    lines.push(`${occTag(b,o)} ${o.mechanic}: `+as.map(a=>`${a.healer} {spell:${a.ability_id}}`).join('  ')); });
  return lines.join('\n');
}
function teamPlan(b,col){
  const occ=b.mechanics, plan=b.team_plan||{assignments:[],gaps:[],unused:[]}, ev=b.evidence||[];
  const by={}; plan.assignments.forEach(a=>{ (by[a.occ]=by[a.occ]||[]).push(a); });
  const maxMag=Math.max(1,...occ.map(o=>o.magnitude||0));
  const specOf={}; b.ours.healers.forEach(h=>specOf[h.name]=h.spec);
  let rows='';
  occ.forEach((o,i)=>{
    const as=(by[i]||[]).filter(a=>!who||a.healer===who); const e=ev[i]||{by_kind:{},kills_any:0,total:1};
    if(who && !as.length && !(plan.gaps.includes(i))) return;
    const evTxt=(e.typical_count?`<b>${e.typical_count}</b> stacked here (${(e.typical_combo||[]).join(' + ')||'?'})<br>`:'')+(Object.entries(e.by_kind||{}).sort((x,y)=>y[1]-x[1]).map(([k,v])=>`${k} ${v}/${e.total}`).join(', ')||'nothing');
    const gap=plan.gaps.includes(i);
    rows+=`<tr><td class="num">${occWhen(b,o)}</td>
      <td title="${esc(o.notes||'')}"><b>${esc(o.mechanic)}</b> <span class="pill">${esc(o.type)}</span>${o.weight!==o.file_weight&&o.file_weight!=null?` <span class="pill" title="the kill logs changed this mechanic's priority from ${o.file_weight} to ${o.weight}">logs: ${o.weight>o.file_weight?'more':'less'} important</span>`:''}</td>
      <td><div class="conf" title="avg damage taken per kill around it"><i style="width:${Math.round(100*(o.magnitude||0)/maxMag)}%;background:var(--dmg)"></i></div><span class="muted">${Math.round((o.magnitude||0)/1000)}k · seen in ${o.support}/${o.total} kills</span></td>
      <td class="muted" style="font-size:12px">${evTxt}</td>
      <td>${as.length?as.map(a=>`<span class="dot" style="background:${col[a.spec]||'var(--muted)'}"></span>${esc(a.healer)} ${esc(a.ability)} <span class="muted">(${a.kind}${a.evidence?', '+Math.round(a.evidence*100)+'% of kills':''}${a.fill?', otherwise unused':''}${a.fallback?', wrong kind but better than nothing':''})</span>`).join('<br>'):(gap?'<span style="color:var(--bad);font-weight:600">GAP, nothing free</span>':'<span class="muted">not needed</span>')}</td></tr>`;
  });
  const unused=(plan.unused||[]).filter(u=>!who||u.healer===who);
  return `<h2>Team plan <span class="muted" style="font-weight:400">· ${occ[0]?.total||0} kills</span></h2>

    <div style="overflow-x:auto"><table><thead><tr><th class="num">When</th><th>Mechanic</th><th>Damage</th><th>Kills used</th><th>Assigned</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${unused.length?`<p class="muted" style="margin:10px 0 0">Majors left unassigned: ${unused.map(u=>esc(u.healer)+' '+esc(u.ability)).join(', ')}. Spare for deaths and mistakes.</p>`:''}
    ${(b.unlisted_boss_casts||[]).length?`<p class="muted" style="margin:6px 0 0">Boss casts with no entry in the mechanic file (add them if they matter): ${b.unlisted_boss_casts.slice(0,10).map(u=>esc(u.name)+' ('+u.kills+')').join(', ')}</p>`:''}
    ${noteBlock('Team raid note (MRT / Liquid / NSRT), one line per mechanic', teamNote(b))}`;
}

function ourPulls(b,col){
  const pulls=b.our_pulls; const hs=visibleHealers(b);
  let html=`<h2>Our last ${pulls.length} pulls vs the plan</h2>`;
  const hdr=pulls.map(p=>`<th class="num"><a href="${p.url}" target="_blank" rel="noopener">${p.kill?'Kill':'Wipe'} ${p.pct!=null?p.pct.toFixed(0)+'%':''}</a><br><span class="muted">${fmt(p.duration)}</span></th>`).join('');
  if(pulls.some(p=>(p.deaths||[]).length)){
    html+=`<div style="overflow-x:auto"><table><thead><tr><th>Deaths</th>${hdr}</tr></thead><tbody><tr><td class="muted">who, what killed them, when</td>`+
      pulls.map(p=>`<td class="cell" style="text-align:left;white-space:normal;font-size:12px">${(p.deaths||[]).slice(0,8).map(d=>`${esc(d.player)} <span class="muted">${esc(d.by||'?')} ${fmt(d.t)}</span>`).join('<br>')||'<span class="muted">none</span>'}</td>`).join('')+'</tr></tbody></table></div>';
  }
  for(const h of hs){
    const plan=fillGaps(b, visibleClusters(b).filter(c=>c.spec===h.spec && isFeasible(b,c) && c.tier!=='discovered' && picked(h.spec,c.ability,c.tier))).sort((x,y)=>x.abs_median-y.abs_median);
    if(!plan.length) continue;
    html+=`<h3 style="font-size:13px;margin:14px 0 6px"><span class="dot" style="background:${col[h.spec]}"></span>${esc(h.name)} · ${esc(h.spec)}</h3><div style="overflow-x:auto"><table><thead><tr><th>Planned</th>${hdr}</tr></thead><tbody>`;
    const used=pulls.map(()=>new Set());
    for(const c of plan){
      const when=(b.use_phases&&c.phase!=null)?`P${c.phase} ${fmt(c.median)}`:fmt(c.abs_median);
      html+=`<tr><td>${when} ${esc(c.ability)}${c.mechanic?` <span class="muted">(${esc(c.mechanic)})</span>`:''}</td>`;
      pulls.forEach((p,pi)=>{
        const me=p.healers.find(x=>x.spec===h.spec); const mine=p.casts.filter(x=>me && x.player===me.name && x.ability===c.ability && !used[pi].has(x));
        const phased=b.use_phases && c.phase!=null && p.phases.length;
        let best=null;
        for(const x of mine){ const d = phased ? (x.phase===c.phase ? x.t_in_phase-c.median : null) : x.t-c.abs_median; if(d==null) continue; if(Math.abs(d)<=30 && (!best||Math.abs(d)<Math.abs(best.d))) best={x,d}; }
        let cls='miss', label='missed';
        if(best){ used[pi].add(best.x); const d=Math.round(best.d); cls=Math.abs(d)<=10?'ok':'late'; label=Math.abs(d)<=10?'on time':(d>0?`+${d}s late`:`${-d}s early`); }
        else { // was it even due?
          let due; if(phased){ const ps=p.phases.find(q=>q[0]===c.phase); due = ps ? ps[1]+c.median <= p.duration : false; } else due = c.abs_median <= p.duration;
          if(!due){ cls='na'; label='wiped before'; }
        }
        html+=`<td class="cell ${cls}">${label}</td>`;
      });
      html+='</tr>';
    }
    // unused at wipe
    html+=`<tr><td><b>Ready but unused at wipe</b></td>`;
    const majors=[...new Map(b.clusters.filter(c=>c.spec===h.spec&&c.tier==='major').map(c=>[c.ability,c.cd||60])).entries()];
    pulls.forEach(p=>{ const me=p.healers.find(x=>x.spec===h.spec); const ready=[];
      for(const [ab,cd] of majors){ const mine=p.casts.filter(x=>me&&x.player===me.name&&x.ability===ab); const last=mine.length?Math.max(...mine.map(x=>x.t)):-1e9;
        if(p.duration-last>=cd*0.9) ready.push(ab); }
      html+=`<td class="${ready.length?'cell late':'cell ok'}">${ready.length?ready.map(esc).join('<br>'):'none'}</td>`; });
    html+='</tr></tbody></table></div>';
  }
  return html;
}

function noteBlock(title, text, warn){
  return `<div class="notebar"><h3>${title}</h3><button class="copy" data-text="${esc(text)}">Copy</button></div>` +
    (warn?`<p class="muted" style="margin:0 0 6px">${warn}</p>`:'') + `<pre>${esc(text)}</pre>`;
}

function clusterTable(b, col){
  const names={}; b.ours.healers.forEach(h=>{names[h.spec]=(names[h.spec]?names[h.spec]+'/':'')+h.name;});
  const key = c => (b.use_phases && c.phase!=null) ? (c.phase*10000 + c.median) : c.abs_median;
  const rows=[...visibleClusters(b)].sort((a,c)=>key(a)-key(c)).map(c=>{
    const when = (b.use_phases && c.phase!=null) ? `P${c.phase} ${fmt(c.median)}` : fmt(c.abs_median);
    return `<tr><td class="num">${when}</td><td><span class="dot" style="background:${col[c.spec]||'var(--muted)'}"></span>${esc(names[c.spec]||c.spec)}</td>
      <td>${esc(c.ability)} <span class="pill ${c.tier}">${c.tier}</span>${c.mechanic?` <span class="muted">covers ${esc(c.mechanic)}</span>`:''}${isFeasible(b,c)?'':' <span class="pill clash" title="Closer to another timing of this ability than its cooldown allows. Different guilds used it here; a single player cannot press both. Kept off the notes.">CD clash, off notes</span>'}</td>
      <td><div class="conf" title="${c.support} of ${c.total} kills"><i style="width:${Math.round(100*c.support/c.total)}%"></i></div><span class="muted">${c.support}/${c.total} · ±${Math.round(c.spread)}s</span></td></tr>`;
  }).join('');
  return `<table><thead><tr><th class="num">When</th><th>Who</th><th>Cooldown</th><th>Agreement</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function timeline(b, col){
  const lanes = visibleHealers(b); const laneH=34, top=26, dmgH=110, left=150, right=20;
  const dur = Math.max(b.target_duration, ...b.kills.map(k=>k.duration), 60);
  const pxPerSec = Math.max(2.2, Math.min(5, 1100/dur));
  const W = left + dur*pxPerSec + right, H = top + dmgH + 14 + lanes.length*laneH + 30;
  const X = s => left + s*pxPerSec;
  const ns='http://www.w3.org/2000/svg'; const svg=document.createElementNS(ns,'svg');
  svg.setAttribute('width',W); svg.setAttribute('height',H); svg.setAttribute('role','img');
  const el=(tag,attrs,parent)=>{const e=document.createElementNS(ns,tag); for(const k in attrs) e.setAttribute(k,attrs[k]); (parent||svg).appendChild(e); return e;};
  // phase bands from the median kill phases
  const phases = b.phases_ref || [];
  phases.forEach((p,i)=>{ const x0=X(p[1]), x1= i+1<phases.length ? X(phases[i+1][1]) : X(dur);
    if(i%2===1) el('rect',{x:x0,y:top,width:Math.max(0,x1-x0),height:H-top-30,fill:'var(--phase)'});
    el('line',{x1:x0,x2:x0,y1:top-8,y2:H-30,stroke:'var(--axis)','stroke-dasharray':'3 3'});
    const tx=el('text',{x:x0+4,y:top-10,class:'phase-label'}); tx.textContent='P'+p[0]; });
  // mechanic ticks from the boss's own casts
  (b.mechanics||[]).forEach(o=>{ const x=X(o.abs_t); const big=o.weight>=3;
    el('line',{x1:x,x2:x,y1:top,y2:H-30,stroke:big?'var(--s8)':'var(--axis)','stroke-dasharray':big?'':'2 3',opacity:.6});
    const t=el('text',{x:x+3,y:top+dmgH-4,class:'phase-label',opacity:.9}); t.textContent=o.mechanic.length>16?o.mechanic.slice(0,15)+'…':o.mechanic;
    t.setAttribute('transform',`rotate(-90 ${x+3} ${top+dmgH-4})`); });
  // x axis
  for(let s=0;s<=dur;s+=30){ const x=X(s); el('line',{x1:x,x2:x,y1:H-30,y2:H-24,stroke:'var(--axis)'});
    const tx=el('text',{x:x,y:H-10,'text-anchor':'middle'}); tx.textContent=fmt(s); }
  el('line',{x1:left,x2:X(dur),y1:H-30,y2:H-30,stroke:'var(--axis)'});
  // damage area
  const dmg=b.damage||[]; const maxV=Math.max(1,...dmg.map(d=>d[1]));
  if(dmg.length){ const y0=top+dmgH;
    const pts=dmg.map(p=>`${X(p[0]).toFixed(1)},${(y0 - (p[1]/maxV)*dmgH).toFixed(1)}`);
    const area=`M${X(dmg[0][0])},${y0} L`+pts.join(' L')+` L${X(dmg[dmg.length-1][0])},${y0} Z`;
    const line='M'+pts.join(' L');
    el('path',{d:area,fill:'var(--dmg-fill)'});
    el('path',{d:line,fill:'none',stroke:'var(--dmg)','stroke-width':2});
    (b.peaks||[]).forEach((p,i)=>{ const x=X(p[0]), y=y0-(p[1]/maxV)*dmgH; const c=el('circle',{cx:x,cy:y,r:4,fill:'var(--dmg)',stroke:'var(--surface)','stroke-width':2});
      const mech=(b.peak_mechanics||[])[i];
      c.onmousemove=e=>showTip(e,`<b>${mech?esc(mech):'Damage spike'}</b> at ${fmt(p[0])}<br>${Math.round(p[1]/1000)}k DTPS averaged across kills`); c.onmouseleave=hideTip;
      if(mech && !(b.mechanics||[]).length){ const t=el('text',{x:x,y:y-8,'text-anchor':'middle',class:'phase-label'}); t.textContent=mech.length>18?mech.slice(0,17)+'…':mech; } });
    const lbl=el('text',{x:left-8,y:top+12,'text-anchor':'end',class:'lane-label'}); lbl.textContent='Raid damage taken';
  }
  // lanes
  lanes.forEach((h,i)=>{ const y=top+dmgH+14+i*laneH+laneH/2;
    el('line',{x1:left,x2:X(dur),y1:y,y2:y,stroke:'var(--grid)'});
    const lbl=el('text',{x:left-8,y:y+4,'text-anchor':'end',class:'lane-label'}); lbl.textContent=h.name;
    const sub=el('text',{x:left-8,y:y+15,'text-anchor':'end'}); sub.textContent=h.spec;
    // clusters for this spec (if two healers share a spec, both lanes show them)
    b.clusters.filter(c=>c.spec===h.spec).forEach(c=>{
      const r = 5 + 7*(c.support/c.total); const x=X(c.abs_median);
      if(c.spread>0) el('rect',{x:X(c.abs_median - c.spread/2),y:y-2,width:Math.max(1,c.spread*pxPerSec),height:4,fill:col[h.spec],opacity:.3,rx:2});
      const ok=isFeasible(b,c); const m=el('circle',{cx:x,cy:y,r:r,fill:ok?col[h.spec]:'var(--surface)',stroke:ok?'var(--surface)':col[h.spec],'stroke-width':2,opacity:c.tier==='major'?1:.55});
      const when=(b.use_phases&&c.phase!=null)?`P${c.phase} ${fmt(c.median)} (≈${fmt(c.abs_median)} from pull)`:fmt(c.abs_median);
      m.onmousemove=e=>showTip(e,`<b>${esc(c.ability)}</b> · ${esc(c.tier)}${ok?'':' · <b>CD clash, off notes</b>'}<br>${when}<br>${c.support} of ${c.total} kills, spread ±${Math.round(c.spread)}s${c.mechanic?'<br>covers <b>'+esc(c.mechanic)+'</b>':''}<br><span class="muted">cast by ${esc(c.players.join(', '))}</span>`);
      m.onmouseleave=hideTip;
    });
  });
  return svg;
}
selectCurrent();
</script>
</body>
</html>
"""


def write_dashboard(data: dict, path: Path) -> None:
    html = TEMPLATE.replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    path.write_text(html, encoding="utf-8")
