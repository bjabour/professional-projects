/* RiskOps browser explorer. All archived values come from the verified Python export. */
(function () {
  "use strict";
  const money = (v, d = 2) => "$" + Number(v).toLocaleString("en-US", {minimumFractionDigits:d, maximumFractionDigits:d});
  const number = (v, d = 2) => Number(v).toLocaleString("en-US", {minimumFractionDigits:d, maximumFractionDigits:d});
  const esc = v => String(v == null ? "" : v).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const statusClass = s => s === "CRITICAL" || s === "BREACH" || s === "BELOW" || s === "FAILED" ? "bad" : s === "REVIEW" || s === "HIGH" || s === "PENDING_HUMAN_REVIEW" ? "warn" : "good";
  const badge = s => '<span class="badge ' + statusClass(s) + '">' + esc(s) + "</span>";

  function scenario(run, rateBps, haircut, outflowIncrease) {
    if (![rateBps,haircut,outflowIncrease].every(Number.isFinite)) throw new Error("Scenario parameters must be finite.");
    if (rateBps < 0 || rateBps > 200 || haircut < 0 || haircut > 40 || outflowIncrease < 0 || outflowIncrease > 60) throw new Error("Scenario parameters outside the supported range.");
    const m = run.metrics;
    const duration = m.weighted_modified_duration == null
      ? run.instruments.reduce((sum,p)=>sum + Number(p.pv_usd_m)*Number(p.modified_duration),0)/m.total_pv_usd_m
      : m.weighted_modified_duration;
    const buffer = m.liquidity_buffer_usd_m * (1-haircut/100);
    const outflow = m.net_cash_outflow_30d_usd_m * (1+outflowIncrease/100);
    const pvChange = -m.total_pv_usd_m * duration * rateBps / 10000;
    const lcr = outflow > 0 ? 100*buffer/outflow : 999;
    return {pv_change_usd_m:pvChange, stressed_pv_usd_m:Math.max(0,m.total_pv_usd_m+pvChange), buffer_usd_m:buffer, outflow_usd_m:outflow, lcr_pct:lcr, liquidity_gap_usd_m:Math.max(0,outflow*m.lcr_requirement_pct/100-buffer), status:lcr<m.lcr_requirement_pct?"BREACH":"MEETS"};
  }

  function answer(run, kind) {
    const m=run.metrics, gap=Math.max(0,m.net_cash_outflow_30d_usd_m*m.lcr_requirement_pct/100-m.liquidity_buffer_usd_m);
    if(kind==="liquidity") return {
      text:"The liquidity buffer is "+money(m.liquidity_buffer_usd_m)+"m against "+money(m.net_cash_outflow_30d_usd_m)+"m of modeled 30-day net outflow. That produces "+number(m.lcr_pct,1)+"% coverage against a "+number(m.lcr_requirement_pct,0)+"% requirement. "+(gap>0?"The buffer shortfall is "+money(gap)+"m.":"The buffer meets the configured requirement."),
      source:"result.json → metrics.liquidity_buffer_usd_m / metrics.net_cash_outflow_30d_usd_m / metrics.lcr_requirement_pct"
    };
    if(kind==="changed") return {
      text:run.trends && run.trends.lcr_change_ppts != null
        ? "Compared with the previous verified run, gross portfolio PV changed "+number(run.trends.total_pv_change_pct)+"%, the one-day VaR changed "+number(run.trends.var_1d_change_pct)+"%, and liquidity coverage changed "+number(run.trends.lcr_change_ppts)+" percentage points. The records quantify these movements; they do not establish an economic cause."
        : "This is the first configured date. There is no preceding run in this reporting window, so a day-over-day comparison is unavailable.",
      source:"result.json → trends; manifest.json → identity.previous_run_id"
    };
    return {
      text:"Review the "+run.warnings.length+" recorded exception"+(run.warnings.length===1?"":"s")+", reconcile the input snapshot, and ask the responsible risk owner to confirm interpretation and escalation. The run's technical completion does not constitute financial approval.",
      source:"result.json → warnings; brief.json → approval_status"
    };
  }

  if(typeof module !== "undefined" && module.exports) module.exports={scenario,answer,esc};
  if(typeof document === "undefined") return;
  const data=window.RISKOPS_DATA;
  if(!data || !Array.isArray(data.dates) || !data.dates.length){
    document.querySelector("#content").innerHTML='<div class="panel"><h2>Evidence is not available</h2><p>Run the Python pipeline and portfolio exporter to build this demonstration.</p></div>';
    return;
  }
  const params=new URLSearchParams(location.search), validViews=["overview","scenarios","evidence","assistant"];
  let selected=data.dates.findIndex(d=>d.run_date===params.get("date"));
  if(selected<0) selected=data.dates.length-1;
  let view=validViews.includes(params.get("view"))?params.get("view"):"overview";
  let filters={portfolio:"all",query:"",sort:"pv"};
  let controls={rate:0,haircut:0,outflow:0}, playing=false, replayTimer=null;
  const getRun=()=>data.dates[selected];
  const $=s=>document.querySelector(s);
  function toast(message){$("#toast").textContent=message;$("#toast").classList.add("visible");setTimeout(()=>$("#toast").classList.remove("visible"),2800);}
  function saveFile(name,payload,type="application/json"){
    const url=URL.createObjectURL(new Blob([typeof payload==="string"?payload:JSON.stringify(payload,null,2)],{type}));
    const link=document.createElement("a");link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function panel(title,caption,content,extra=""){
    return '<section class="panel '+extra+'"><div class="panel-top"><div><h2>'+title+'</h2>'+(caption?'<p class="caption">'+caption+"</p>":"")+"</div></div>"+content+"</section>";
  }
  function updateUrl(){
    const url=new URL(location.href);url.searchParams.set("date",getRun().run_date);url.searchParams.set("view",view);
    try{history.replaceState(null,"",url);}catch(_e){/* file previews may restrict history updates */}
  }
  function openDetail(title,body){$("#detail-content").innerHTML="<h2>"+esc(title)+"</h2>"+body;$("#detail").showModal();}
  function metric(label,value,sub,critical=false){
    return '<div class="metric'+(critical?" critical":"")+'"><p class="label">'+label+'</p><div class="value">'+value+'</div><div class="sub">'+sub+"</div></div>";
  }
  function renderMetrics(){
    const r=getRun(),m=r.metrics;
    $("#metrics").innerHTML=metric("Gross portfolio PV",money(m.total_pv_usd_m)+'<span class="unit">m</span>',"17 portfolio positions")
      +metric("VaR proxy · 1 day",money(m.var_1d_usd_m)+'<span class="unit">m</span>',"Duration / volatility basis")
      +metric("VaR proxy · 5 days",money(m.var_5d_usd_m)+'<span class="unit">m</span>',"1-day VaR × √5")
      +metric("Liquidity coverage",number(m.lcr_pct,1)+"%",number(m.lcr_requirement_pct,0)+"% configured requirement",m.lcr_pct<m.lcr_requirement_pct)
      +metric("Corona loss",money(m.corona_loss_usd_m)+'<span class="unit">m</span>',"Fixed portfolio stress");
  }
  function liquidityChart(){
    const W=640,H=212,left=52,right=38,top=20,bottom=42;
    const values=data.dates.map(r=>r.metrics.lcr_pct), req=getRun().metrics.lcr_requirement_pct;
    const lo=Math.floor(Math.min(...values,req)/10)*10-5,hi=Math.ceil(Math.max(...values,req)/10)*10+5;
    const x=i=>left+i*(W-left-right)/Math.max(1,values.length-1), y=v=>top+(hi-v)/(hi-lo)*(H-top-bottom);
    let out='<svg class="chart" viewBox="0 0 '+W+" "+H+'" role="img" aria-label="Liquidity coverage falls across the three reporting dates, crossing the configured requirement on August 29">';
    [90,100,110,120].filter(v=>v>=lo&&v<=hi).forEach(v=>{out+='<line class="axis" x1="'+left+'" y1="'+y(v)+'" x2="'+(W-right)+'" y2="'+y(v)+'"/><text x="5" y="'+(y(v)+4)+'">'+v+"%</text>";});
    out+='<line class="threshold" x1="'+left+'" y1="'+y(req)+'" x2="'+(W-right)+'" y2="'+y(req)+'"/>';
    out+='<path d="M '+values.map((v,i)=>x(i)+" "+y(v)).join(" L ")+'" fill="none" stroke="#e4ecd4" stroke-width="3"/>';
    values.forEach((v,i)=>{out+='<circle cx="'+x(i)+'" cy="'+y(v)+'" r="'+(i===selected?7:5)+'" fill="'+(v<req?"#ff8993":"#e4ecd4")+'" stroke="#253b73" stroke-width="2"/><text text-anchor="middle" x="'+x(i)+'" y="'+(y(v)-15)+'" style="fill:#faf8f2">'+number(v,1)+'%</text><text text-anchor="middle" x="'+x(i)+'" y="'+(H-10)+'">Aug '+data.dates[i].run_date.slice(-2)+"</text>";});
    return out+"</svg>";
  }
  function warningsHtml(){
    const r=getRun();
    if(!r.warnings.length)return '<div class="empty">No configured risk thresholds were breached on this date.</div>';
    return '<div class="warning-list">'+r.warnings.map((w,i)=>'<button class="warning" data-warning="'+i+'">'+badge(w.severity)+"<strong>"+esc(w.title)+'</strong><p>'+esc(w.message)+"</p></button>").join("")+"</div>";
  }
  function renderOverview(){
    const r=getRun(),m=r.metrics, gap=Math.max(0,m.net_cash_outflow_30d_usd_m*m.lcr_requirement_pct/100-m.liquidity_buffer_usd_m);
    const desc=gap>0?"Liquidity falls short by "+money(gap)+"m. Review the source evidence before escalation.":r.warnings.length?"A material daily change requires review. Inspect the warning for the verified movement.":"The configured checks pass for this date. The archive remains available for review.";
    const alert='<div class="alert '+(r.status==="CLEAR"?"clear":r.status==="REVIEW"?"review":"")+'"><div><strong>'+esc(r.status==="CRITICAL"?"Liquidity requirement breached":r.status==="REVIEW"?"Daily movement requires attention":"No material exceptions")+'</strong><p>'+desc+'</p></div><button class="button ghost" data-go="evidence">Inspect evidence →</button></div>';
    const timeline=liquidityChart()+'<div class="legend"><span>Liquidity coverage</span><span>Configured requirement</span></div><div class="split-stat"><div>Buffer<strong>'+money(m.liquidity_buffer_usd_m)+'m</strong></div><div>30-day net outflow<strong>'+money(m.net_cash_outflow_30d_usd_m)+'m</strong></div><div>Shortfall<strong class="negative">'+money(gap)+"m</strong></div></div>";
    const portfolios='<div class="table-scroll"><table><thead><tr><th>Portfolio</th><th>Positions</th><th>Portfolio PV · USD m</th><th>Liquidity coverage</th></tr></thead><tbody>'+r.portfolios.map(p=>'<tr><td>'+esc(p.portfolio)+'</td><td>'+p.instrument_count+'</td><td class="num">'+money(p.pv_usd_m)+'</td><td class="'+(p.lcr_pct<m.lcr_requirement_pct?"negative":"positive")+'">'+number(p.lcr_pct,1)+"%</td></tr>").join("")+"</tbody></table></div>";
    const totalLoss=m.corona_loss_usd_m;
    const losses=r.portfolios.map(p=>'<div class="bar-row"><span>'+esc(p.portfolio)+'</span><div class="bar-track"><div class="bar-fill" style="width:'+Math.max(0,Math.min(100,p.corona_loss_usd_m/totalLoss*100))+'%"></div></div><span class="bar-value">'+money(p.corona_loss_usd_m)+"m</span></div>").join("");
    $("#content").innerHTML=alert+'<div class="grid">'+panel("The liquidity trajectory","Three archived snapshots · selected date is emphasized",timeline)+panel("Exception queue",r.warnings.length+" recorded warnings · select one to inspect",warningsHtml())+'</div><div class="grid">'+panel("Portfolio breakdown","Gross portfolio exposure; assets and liabilities are not netted.",portfolios)+panel("Where the Corona loss sits","Contribution to the portfolio stress",losses)+'</div>'+instrumentPanel();
    bindCommon();bindInstruments();
  }
  function instrumentPanel(){
    const r=getRun();
    return panel("Instrument explorer","Follow a position from its source file through the calculation outputs.",
      '<div class="toolbar"><input id="search" type="search" aria-label="Search instruments" placeholder="Search instrument ID or type" value="'+esc(filters.query)+'"><select id="portfolio-filter" aria-label="Filter portfolio"><option value="all">All portfolios</option>'+r.portfolios.map(p=>'<option'+(filters.portfolio===p.portfolio?" selected":"")+'>'+esc(p.portfolio)+'</option>').join("")+'</select><select id="sort" aria-label="Sort instruments"><option value="pv">Largest portfolio PV</option><option value="duration"'+(filters.sort==="duration"?" selected":"")+'>Longest duration</option><option value="id"'+(filters.sort==="id"?" selected":"")+'>Instrument ID</option></select></div><div id="instrument-table"></div>');
  }
  function renderInstrumentTable(){
    const r=getRun(),q=filters.query.toLowerCase();
    const positions=r.instruments.filter(p=>(filters.portfolio==="all"||p.portfolio===filters.portfolio)&&((p.instrument_id+" "+p.instrument_type).toLowerCase().includes(q))).sort((a,b)=>filters.sort==="id"?a.instrument_id.localeCompare(b.instrument_id):Number(b[filters.sort==="duration"?"modified_duration":"pv_usd_m"])-Number(a[filters.sort==="duration"?"modified_duration":"pv_usd_m"]));
    $("#instrument-table").innerHTML=positions.length?'<div class="table-scroll"><table><thead><tr><th>Instrument</th><th>Portfolio</th><th>CCY</th><th>Portfolio PV · USD m</th><th>Mod. duration</th><th>Inspect</th></tr></thead><tbody>'+positions.map(p=>'<tr><td>'+esc(p.instrument_id)+'</td><td>'+esc(p.portfolio)+'</td><td>'+esc(p.currency)+'</td><td class="num">'+money(p.pv_usd_m)+'</td><td class="num">'+number(p.modified_duration,2)+'y</td><td><button class="link" data-instrument="'+esc(p.instrument_id)+'">Evidence ↗</button></td></tr>').join("")+'</tbody></table></div><p class="caption">'+positions.length+" of "+r.instruments.length+' instruments</p>':'<div class="empty">No instruments match these filters.</div>';
    document.querySelectorAll("[data-instrument]").forEach(b=>b.onclick=()=>showInstrument(b.dataset.instrument));
  }
  function bindInstruments(){
    renderInstrumentTable();
    $("#search").oninput=e=>{filters.query=e.target.value;renderInstrumentTable();};
    $("#portfolio-filter").onchange=e=>{filters.portfolio=e.target.value;renderInstrumentTable();};
    $("#sort").onchange=e=>{filters.sort=e.target.value;renderInstrumentTable();};
  }
  function showInstrument(id){
    const r=getRun(),p=r.instruments.find(x=>x.instrument_id===id), src=r.provenance.source_files.find(s=>s.file===(p.source_file||p.portfolio.replace(" ","_")+".csv"));
    const fields=[["Portfolio",p.portfolio],["Source file",p.source_file],["Native currency",p.currency],["Fixed FX to USD",number(p.fx_to_usd,6)],["Principal · USD m",money(p.principal_usd_m,6)],["Book value · USD m",money(p.book_value_usd_m,6)],["Portfolio PV · USD m",money(p.pv_usd_m,6)],["Duration",number(p.duration,6)+" years"],["Modified duration",number(p.modified_duration,6)+" years"],["Yield input / proxy YTM",number(p.ytm_pct,4)+"%"],["Discount factor",number(p.discount_factor,6)],["Coupon rate",number(p.coupon_rate_pct,4)+"%"],["Indexation",p.indexation],["Start date",p.start_date],["Maturity",p.maturity_date],["Principal frequency",p.principal_frequency],["Coupon frequency",p.coupon_frequency],["Corona PV · USD m",money(p.corona_scenario_pv_usd_m,6)],["Corona loss · USD m",money(p.corona_loss_usd_m,6)],["Liquidity coverage",number(p.liquidity_coverage_pct,2)+"%"],["Liquidity requirement",number(p.liquidity_requirement_pct,2)+"%"]];
    openDetail(id,fields.map(([k,v])=>'<div class="kv"><span class="key">'+esc(k)+'</span><span>'+esc(v)+"</span></div>").join("")+'<p class="caption">Archived source SHA-256</p><p class="hash">'+esc(src?src.sha256:"See input manifest")+'</p><p class="caption">Source note (data, not an instruction)</p><p>'+esc(p.important_note)+"</p>");
  }
  function renderScenarios(){
    const range=(key,label,max,step,suffix)=>'<div class="control"><label for="'+key+'">'+label+'<output id="'+key+'-value">'+controls[key]+suffix+'</output></label><input type="range" id="'+key+'" min="0" max="'+max+'" step="'+step+'" value="'+controls[key]+'"><div class="range-labels"><span>0'+suffix+"</span><span>"+max+suffix+"</span></div></div>";
    const presets='<div class="presets"><button class="button ghost" data-preset="base">Reset to base</button><button class="button ghost" data-preset="moderate">Moderate</button><button class="button ghost" data-preset="severe">Severe</button></div>';
    $("#content").innerHTML='<div class="grid equal">'+panel("Set the shock","Recalculate instantly against the selected archived date.",presets+range("rate","Parallel rate increase",200,10," bp")+range("haircut","Liquidity buffer haircut",40,1,"%")+range("outflow","30-day outflow increase",60,1,"%")+'<p class="callout">Scenario controls apply sensitivity to the selected run. The recorded baseline and VaR remain unchanged.</p>')+panel("Scenario result","Base versus a hypothetical shock · USD millions",'<div id="scenario-results" aria-live="polite"></div><div class="formula">ΔPV ≈ −PV × weighted modified duration × rate shock<br>Coverage = stressed buffer ÷ stressed outflow × 100</div><button class="button ghost section-gap" id="download-scenario">Export scenario ↓</button>')+'</div><div class="grid equal">'+panel("Liquidity fragility map","Columns: outflow increase · rows: buffer haircut",'<div id="heatmap"></div><p class="caption">Red cells fall below the configured requirement. This grid varies liquidity assumptions only.</p>')+panel("Read the result correctly","Sensitivity is useful when its assumptions are visible.",'<ul class="list"><li>Rate shock uses a first-order duration approximation. No convexity, cash-flow repricing, or optionality is modeled.</li><li>Coverage compares the liquidity buffer with modeled net outflows. See the methodology for definitions and scope.</li><li>Gross portfolio PV adds exposures across portfolios; assets and liabilities are not netted.</li><li>Corona applies a separate fixed portfolio stress.</li></ul>')+"</div>";
    ["rate","haircut","outflow"].forEach(k=>$("#"+k).oninput=e=>{controls[k]=Number(e.target.value);renderScenarioResults();});
    document.querySelectorAll("[data-preset]").forEach(b=>b.onclick=()=>{controls=b.dataset.preset==="severe"?{rate:200,haircut:15,outflow:25}:b.dataset.preset==="moderate"?{rate:100,haircut:5,outflow:10}:{rate:0,haircut:0,outflow:0};renderScenarios();});
    $("#download-scenario").onclick=()=>saveFile("riskops-scenario-"+getRun().run_date+".json",{run_id:getRun().run_id,mode:"browser_sensitivity",parameters:controls,result:scenario(getRun(),controls.rate,controls.haircut,controls.outflow)});
    renderScenarioResults();
  }
  function renderScenarioResults(){
    const r=getRun(),s=scenario(r,controls.rate,controls.haircut,controls.outflow);
    ["rate","haircut","outflow"].forEach(k=>$("#"+k+"-value").textContent=controls[k]+(k==="rate"?" bp":"%"));
    $("#scenario-results").innerHTML='<p>'+badge(s.status)+'</p>'+[["Stressed gross portfolio PV",money(s.stressed_pv_usd_m)+"m"],["Portfolio PV movement",money(s.pv_change_usd_m)+"m"],["Stressed liquidity coverage",number(s.lcr_pct,1)+"%"],["Additional buffer needed",money(s.liquidity_gap_usd_m)+"m"]].map(([k,v])=>'<div class="scenario-result"><span>'+k+'</span><strong class="'+(k.includes("coverage")&&s.status==="BREACH"?"negative":"")+'">'+v+"</strong></div>").join("");
    let cells='<div class="heatmap"><div class="cell head">↓ / →</div>'+[0,10,20,30,40].map(v=>'<div class="cell head">'+v+"%</div>").join("");
    [0,10,20,30,40].forEach(h=>{cells+='<div class="cell head">'+h+"%</div>";[0,10,20,30,40].forEach(o=>{const l=scenario(r,0,h,o).lcr_pct;cells+='<div class="cell '+(l<r.metrics.lcr_requirement_pct?"hot":l<110?"warm":"cool")+'" title="Haircut '+h+"%, outflow increase "+o+'%">'+number(l,0)+"%</div>";});});
    $("#heatmap").innerHTML=cells+"</div>";
  }
  function renderEvidence(){
    const r=getRun(),p=r.provenance;
    const hashes=[["Run identity",p.identity_sha256],["Input data",p.data_sha256],["Configuration",p.config_sha256],["Code version",p.code_sha256],["Previous result",p.previous_result_sha256||"First date · no predecessor"]];
    const proof=hashes.map(([k,v])=>'<div class="kv"><span class="key">'+k+'</span><span class="hash">'+esc(v)+"</span></div>").join("")+'<p class="caption">Hashes detect changes when checked against the pinned manifest. They are not digital signatures or protection against an administrator replacing every artifact.</p>';
    const files='<div class="table-scroll"><table><thead><tr><th>Archived input</th><th>Rows</th><th>SHA-256</th></tr></thead><tbody>'+p.source_files.map(f=>'<tr><td>'+esc(f.file)+'</td><td>'+f.rows+'</td><td class="hash" title="'+esc(f.sha256)+'">'+esc(f.sha256.slice(0,16))+"…</td></tr>").join("")+"</tbody></table></div>";
    const checks=(data.control_checks&&data.control_checks.checks)||[];
    const checkHtml=checks.length?checks.map(c=>'<div class="control-pass"><span class="tick">'+(c.passed===false||c.status==="FAIL"?"×":"✓")+'</span><div><strong>'+esc(c.title||c.name||c.id)+'</strong><p>'+esc(c.description||c.detail||c.message||"Verified by the reproducible control suite.")+"</p></div></div>").join(""):(data.controls||[]).map(c=>'<div class="control-pass"><span class="tick">◇</span><div><strong>'+esc(c.title)+'</strong><p>'+esc(c.description)+"</p></div></div>").join("");
    const mapping='<div class="table-scroll"><table><thead><tr><th>Metric</th><th>Source</th><th>Method</th></tr></thead><tbody>'+(r.source_mapping||[]).map(s=>'<tr><td>'+esc(s.metric)+'</td><td>'+esc(s.source)+'</td><td style="white-space:normal;text-align:left">'+esc(s.method)+"</td></tr>").join("")+"</tbody></table></div>";
    $("#content").innerHTML='<div class="grid equal">'+panel("Pinned provenance","Every stage checks the evidence it consumes.",badge(p.integrity)+proof)+panel("Data contract","3 files · 17 positions · no more than 10 per file",files+'<p class="caption section-gap">Checks cover schema, cross-file identifiers, currencies, finite values, date ordering, and permitted payment frequencies.</p><div class="callout">Input and configuration snapshots travel with the run. Edits create a new identity; existing evidence is preserved.</div>')+'</div><div class="grid equal">'+panel(checks.length?"Executed control checks":"Implemented controls",checks.length?"Recorded automated checks, exported with this portfolio build.":"See the test suite for executable evidence.",checkHtml)+panel("Execution journal","Ordered events from the actual Python run.",'<div class="code">'+esc(r.logs.map(l=>String(l.sequence).padStart(3,"0")+" | "+l.stage+" | "+l.event+" | "+l.message).join("\n"))+'</div><button class="button ghost section-gap" id="export-logs">Export run events ↓</button>')+"</div>"+panel("Metric lineage","Read the assumptions alongside the result.",mapping);
    $("#export-logs").onclick=()=>saveFile("riskops-events-"+r.run_date+".jsonl",r.logs.map(l=>JSON.stringify(l)).join("\n"),"application/x-ndjson");
  }
  function renderAssistant(){
    const r=getRun();
    const stages=r.stages.map((s,i)=>'<div class="stage"><span class="stage-icon">'+(s.status==="COMPLETED"?"✓":i+1)+'</span><div><strong>'+esc(s.stage)+'</strong><p>'+esc(s.status)+" · "+s.artifact_count+' artifacts</p></div><span class="stage-time">'+(s.duration_seconds==null?"recorded":number(s.duration_seconds,3)+"s")+"</span></div>").join("");
    const questions='<div class="questions"><button class="button ghost" data-question="liquidity">Explain liquidity</button><button class="button ghost" data-question="changed">What changed?</button><button class="button ghost" data-question="handoff">Prepare the handoff</button></div><div class="answer" id="answer" aria-live="polite"></div>';
    const plan=r.plan.map((s,i)=>'<div class="trace-step"><span>'+String(i+1).padStart(2,"0")+'</span><div><strong>'+esc(s.tool)+'</strong><p>'+esc(s.reason)+'</p><p class="hash">Requires: '+esc(Array.isArray(s.requires)?s.requires.join(", "):s.requires)+"</p></div></div>").join("");
    $("#content").innerHTML='<div class="grid equal">'+panel("Reporting assistant","Evidence-linked answers from the selected run",questions+'<p class="boundary">Explanations follow the registered reporting tools and cite verified values. The methodology documents the reporting logic.</p><button class="button ghost section-gap" id="export-brief">Export handoff brief ↓</button>')+panel("Run progression","Replay the recorded execution without rerunning Python.",'<div class="timeline">'+stages+'</div><p>'+badge(r.execution_status)+'</p><p class="caption">Execution completion and human approval are separate states.</p>'+badge("PENDING_HUMAN_REVIEW"))+'</div><div class="grid equal">'+panel("Inspect the tool plan","Explicit prerequisites and permitted tool actions",'<div class="trace">'+plan+"</div>")+panel("Six-month handoff","Questions an incoming owner should bring to the next meeting.",'<ul class="list">'+(r.brief.questions||[]).map(q=>"<li>"+esc(q)+"</li>").join("")+'</ul><div class="callout">Review the evidence before escalation. A report cannot approve a run, change thresholds, or initiate a financial transaction.</div><label class="field-label" for="run-command">Run this date locally</label><div class="code" id="run-command">python scripts/riskops.py all --run-date '+r.run_date+'</div><button class="button ghost section-gap" id="copy-command">Copy command</button>')+"</div>";
    const showAnswer=k=>{const a=answer(r,k);$("#answer").innerHTML="<p>"+esc(a.text)+'</p><span class="citation">'+esc(a.source)+"</span>";};
    document.querySelectorAll("[data-question]").forEach(b=>b.onclick=()=>showAnswer(b.dataset.question));
    $("#export-brief").onclick=()=>saveFile("riskops-handoff-"+r.run_date+".json",r.brief);
    $("#copy-command").onclick=async()=>{const text="python scripts/riskops.py all --run-date "+r.run_date;try{await navigator.clipboard.writeText(text);toast("Run command copied");}catch(_e){openDetail("Run command",'<div class="code">'+esc(text)+"</div>");}};
    showAnswer("liquidity");
  }
  function bindCommon(){
    document.querySelectorAll("[data-go]").forEach(b=>b.onclick=()=>{view=b.dataset.go;render();});
    document.querySelectorAll("[data-warning]").forEach(b=>b.onclick=()=>{
      const r=getRun(),w=r.warnings[Number(b.dataset.warning)];
      openDetail(w.title,badge(w.severity)+"<p>"+esc(w.message)+'</p><div class="kv"><span class="key">Metric</span><span>'+esc(w.metric)+'</span></div><div class="kv"><span class="key">Current</span><span>'+esc(w.current)+'</span></div><div class="kv"><span class="key">Previous</span><span>'+esc(w.previous==null?"Unavailable":w.previous)+'</span></div><div class="kv"><span class="key">Threshold</span><span>'+esc(w.threshold)+'</span></div><p class="caption">Source: result.json → warnings['+b.dataset.warning+']</p><p class="hash">Run '+esc(r.run_id)+'</p><p class="caption">Inspect the portfolio and instrument tables to reconcile this movement. Economic causation requires separate analysis.</p>');
    });
  }
  function render(){
    const r=getRun();updateUrl();
    $("#date-picker").innerHTML=data.dates.map((d,i)=>'<button data-date="'+i+'" aria-pressed="'+(i===selected)+'">Aug '+d.run_date.slice(-2)+", 2026</button>").join("");
    document.querySelectorAll("[data-date]").forEach(b=>b.onclick=()=>{if(playing)return;selected=Number(b.dataset.date);controls={rate:0,haircut:0,outflow:0};filters={portfolio:"all",query:"",sort:"pv"};render();});
    $("#run-meta").textContent="Run "+r.run_id+" · "+r.execution_status+" · "+r.provenance.integrity+" · "+data.dates.length+" archived dates";
    document.querySelectorAll("[data-view]").forEach(b=>{if(b.dataset.view===view)b.setAttribute("aria-current","page");else b.removeAttribute("aria-current");});
    renderMetrics();
    ({overview:renderOverview,scenarios:renderScenarios,evidence:renderEvidence,assistant:renderAssistant})[view]();
  }
  document.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>{view=b.dataset.view;render();});
  $("#close-detail").onclick=()=>$("#detail").close();
  $("#detail").addEventListener("click",e=>{if(e.target===$("#detail")){const rect=$("#detail").getBoundingClientRect();if(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom)$("#detail").close();}});
  $("#download").onclick=()=>saveFile("riskops-evidence-"+getRun().run_date+".json",getRun());
  $("#replay").onclick=()=>{
    if(playing)return;playing=true;$("#replay").disabled=true;
    const r=getRun(),events=r.logs;let index=0;
    openDetail("Replay · "+r.run_date,'<p class="playback-note">Playback of the selected run’s recorded execution journal.</p><div class="code" id="replay-log" aria-live="off"></div><p id="replay-status" role="status">Replaying execution journal…</p>');
    const step=()=>{
      if(!$("#detail").open){stop();return;}
      const item=events[index++];
      if(item)$("#replay-log").textContent+=String(item.sequence).padStart(3,"0")+" | "+item.stage+" | "+item.event+"\n"+item.message+"\n\n";
      $("#replay-log").scrollTop=$("#replay-log").scrollHeight;
      if(index>=events.length){$("#replay-status").textContent="Recorded run complete · "+r.status+" · "+r.warnings.length+" warnings";stop();}
    };
    const stop=()=>{clearInterval(replayTimer);playing=false;$("#replay").disabled=false;};
    if(!events.length){$("#replay-status").textContent="No recorded events are available.";stop();return;}
    replayTimer=setInterval(step,180);step();
  };
  $("#detail").addEventListener("close",()=>{if(playing){clearInterval(replayTimer);playing=false;$("#replay").disabled=false;}});
  render();
})();
