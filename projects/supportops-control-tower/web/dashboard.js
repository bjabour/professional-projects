/* SupportOps browser explorer. All archived values come from the verified Python export. */
(function () {
  "use strict";
  const number = (v, d = 2) => Number(v).toLocaleString("en-US", {minimumFractionDigits:d, maximumFractionDigits:d});
  const mins = (v, d = 0) => number(v, d) + " min";
  const esc = v => String(v == null ? "" : v).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const statusClass = s => s === "CRITICAL" || s === "BREACH" || s === "FAILED" ? "bad" : s === "REVIEW" || s === "HIGH" || s === "MEDIUM" || s === "PENDING_HUMAN_REVIEW" ? "warn" : "good";
  const badge = s => '<span class="badge ' + statusClass(s) + '">' + esc(s) + "</span>";
  const PRIORITY_ORDER = ["P1", "P2", "P3", "P4"];

  function whatif(run, capacityChangePct, slaThresholdPct, volumeIncreasePct) {
    if (![capacityChangePct, slaThresholdPct, volumeIncreasePct].every(Number.isFinite)) throw new Error("What-if parameters must be finite.");
    if (capacityChangePct < -30 || capacityChangePct > 30 || slaThresholdPct < 80 || slaThresholdPct > 120 || volumeIncreasePct < 0 || volumeIncreasePct > 100) throw new Error("What-if parameters outside the supported range.");
    const m = run.metrics;
    const available = m.available_agent_minutes * (1 + capacityChangePct / 100);
    const required = m.required_handling_minutes * (1 + volumeIncreasePct / 100);
    const ccr = required > 0 ? 100 * available / required : 999;
    const requirement = m.ccr_requirement_pct * slaThresholdPct / 100;
    return {available_agent_minutes: available, required_handling_minutes: required, ccr_pct: ccr, effective_requirement_pct: requirement, capacity_gap_minutes: Math.max(0, required * requirement / 100 - available), status: ccr < requirement ? "BREACH" : "MEETS"};
  }

  function answer(run, kind) {
    const m = run.metrics, gap = Math.max(0, m.required_handling_minutes * m.ccr_requirement_pct / 100 - m.available_agent_minutes);
    if (kind === "capacity") return {
      text: "Available capacity is " + mins(m.available_agent_minutes) + " against " + mins(m.required_handling_minutes) + " of required handling time. That produces " + number(m.ccr_pct, 1) + "% coverage against a " + number(m.ccr_requirement_pct, 0) + "% requirement. " + (gap > 0 ? "The capacity shortfall is " + mins(gap) + "." : "Capacity meets the configured requirement."),
      source: "result.json → metrics.available_agent_minutes / metrics.required_handling_minutes / metrics.ccr_requirement_pct",
    };
    if (kind === "changed") return {
      text: run.trends && run.trends.ccr_change_ppts != null
        ? "Compared with the previous verified run, required handling time changed " + number(run.trends.required_handling_change_pct) + "%, and capacity coverage changed " + number(run.trends.ccr_change_ppts) + " percentage points. The records quantify these movements; they do not establish a root cause."
        : "This is the first configured date. There is no preceding run in this reporting window, so a day-over-day comparison is unavailable.",
      source: "result.json → trends; manifest.json → identity.previous_run_id",
    };
    return {
      text: "Review the " + run.warnings.length + " recorded exception" + (run.warnings.length === 1 ? "" : "s") + ", reconcile the affected queue, and ask the responsible ops owner to confirm interpretation and escalation. The run's technical completion does not constitute a staffing or routing decision.",
      source: "result.json → warnings; brief.json → approval_status",
    };
  }

  if (typeof module !== "undefined" && module.exports) module.exports = {whatif, answer, esc};
  if (typeof document === "undefined") return;
  const data = window.SUPPORTOPS_DATA;
  if (!data || !Array.isArray(data.dates) || !data.dates.length) {
    document.querySelector("#content").innerHTML = '<div class="panel"><h2>Evidence is not available</h2><p>Run the Python pipeline and portfolio exporter to build this demonstration.</p></div>';
    return;
  }
  const params = new URLSearchParams(location.search), validViews = ["overview", "whatif", "evidence", "assistant"];
  let selected = data.dates.findIndex(d => d.run_date === params.get("date"));
  if (selected < 0) selected = data.dates.length - 1;
  let view = validViews.includes(params.get("view")) ? params.get("view") : "overview";
  let filters = {queue: "all", query: "", sort: "handle"};
  let controls = {capacity: 0, sla: 100, volume: 0}, playing = false, replayTimer = null;
  const getRun = () => data.dates[selected];
  const $ = s => document.querySelector(s);
  function toast(message) { $("#toast").textContent = message; $("#toast").classList.add("visible"); setTimeout(() => $("#toast").classList.remove("visible"), 2800); }
  function saveFile(name, payload, type = "application/json") {
    const url = URL.createObjectURL(new Blob([typeof payload === "string" ? payload : JSON.stringify(payload, null, 2)], {type}));
    const link = document.createElement("a"); link.href = url; link.download = name; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function panel(title, caption, content, extra = "") {
    return '<section class="panel ' + extra + '"><div class="panel-top"><div><h2>' + title + '</h2>' + (caption ? '<p class="caption">' + caption + "</p>" : "") + "</div></div>" + content + "</section>";
  }
  function updateUrl() {
    const url = new URL(location.href); url.searchParams.set("date", getRun().run_date); url.searchParams.set("view", view);
    try { history.replaceState(null, "", url); } catch (_e) { /* file previews may restrict history updates */ }
  }
  function openDetail(title, body) { $("#detail-content").innerHTML = "<h2>" + esc(title) + "</h2>" + body; $("#detail").showModal(); }
  function metric(label, value, sub, critical = false) {
    return '<div class="metric' + (critical ? " critical" : "") + '"><p class="label">' + label + '</p><div class="value">' + value + '</div><div class="sub">' + sub + "</div></div>";
  }
  function renderMetrics() {
    const r = getRun(), m = r.metrics;
    $("#metrics").innerHTML = metric("Tickets routed", number(m.ticket_count, 0), m.queue_count + " queues")
      + metric("Required handling", mins(m.required_handling_minutes), "Across all routed tickets")
      + metric("Available capacity", mins(m.available_agent_minutes), "Configured staffing minutes")
      + metric("Capacity coverage", number(m.ccr_pct, 1) + "%", number(m.ccr_requirement_pct, 0) + "% configured requirement", m.ccr_pct < m.ccr_requirement_pct)
      + metric("SLA breach rate", number(m.breach_rate_pct, 1) + "%", m.breach_count + " of " + m.ticket_count + " tickets");
  }
  function capacityChart() {
    const W = 640, H = 212, left = 52, right = 38, top = 20, bottom = 42;
    const values = data.dates.map(r => r.metrics.ccr_pct), req = getRun().metrics.ccr_requirement_pct;
    const lo = Math.floor(Math.min(...values, req) / 10) * 10 - 5, hi = Math.ceil(Math.max(...values, req) / 10) * 10 + 5;
    const x = i => left + i * (W - left - right) / Math.max(1, values.length - 1), y = v => top + (hi - v) / (hi - lo) * (H - top - bottom);
    let out = '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Capacity coverage falls across the three reporting dates, crossing the configured requirement on the final date">';
    const step = Math.max(10, Math.round((hi - lo) / 4 / 10) * 10);
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out += '<line class="axis" x1="' + left + '" y1="' + y(v) + '" x2="' + (W - right) + '" y2="' + y(v) + '"/><text x="5" y="' + (y(v) + 4) + '">' + v + "%</text>";
    out += '<line class="threshold" x1="' + left + '" y1="' + y(req) + '" x2="' + (W - right) + '" y2="' + y(req) + '"/>';
    out += '<path d="M ' + values.map((v, i) => x(i) + " " + y(v)).join(" L ") + '" fill="none" stroke="#f2c46d" stroke-width="3"/>';
    values.forEach((v, i) => { out += '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="' + (i === selected ? 7 : 5) + '" fill="' + (v < req ? "#ff8993" : "#f2c46d") + '" stroke="#20263f" stroke-width="2"/><text text-anchor="middle" x="' + x(i) + '" y="' + (y(v) - 15) + '" style="fill:#faf8f2">' + number(v, 1) + '%</text><text text-anchor="middle" x="' + x(i) + '" y="' + (H - 10) + '">' + data.dates[i].run_date.slice(5) + "</text>"; });
    return out + "</svg>";
  }
  function warningsHtml() {
    const r = getRun();
    if (!r.warnings.length) return '<div class="empty">No configured thresholds were breached on this date.</div>';
    return '<div class="warning-list">' + r.warnings.map((w, i) => '<button class="warning" data-warning="' + i + '">' + badge(w.severity) + "<strong>" + esc(w.title) + '</strong><p>' + esc(w.message) + "</p></button>").join("") + "</div>";
  }
  function renderOverview() {
    const r = getRun(), m = r.metrics, gap = Math.max(0, m.required_handling_minutes * m.ccr_requirement_pct / 100 - m.available_agent_minutes);
    const desc = gap > 0 ? "Capacity falls short by " + mins(gap) + ". Review the source evidence before escalation." : r.warnings.length ? "A material daily change requires review. Inspect the warning for the verified movement." : "The configured checks pass for this date. The archive remains available for review.";
    const alert = '<div class="alert ' + (r.status === "CLEAR" ? "clear" : r.status === "REVIEW" ? "review" : "") + '"><div><strong>' + esc(r.status === "CRITICAL" ? "Capacity requirement breached" : r.status === "REVIEW" ? "Daily movement requires attention" : "No material exceptions") + '</strong><p>' + desc + '</p></div><button class="button ghost" data-go="evidence">Inspect evidence →</button></div>';
    const timeline = capacityChart() + '<div class="legend"><span>Capacity coverage</span><span>Configured requirement</span></div><div class="split-stat"><div>Available<strong>' + mins(m.available_agent_minutes) + '</strong></div><div>Required handling<strong>' + mins(m.required_handling_minutes) + '</strong></div><div>Shortfall<strong class="negative">' + mins(gap) + "</strong></div></div>";
    const queues = '<div class="table-scroll"><table><thead><tr><th>Queue</th><th>Tickets</th><th>Required</th><th>Capacity coverage</th></tr></thead><tbody>' + r.queues.map(q => '<tr><td>' + esc(q.queue) + '</td><td>' + q.ticket_count + '</td><td class="num">' + mins(q.required_handling_minutes) + '</td><td class="' + (q.ccr_pct < m.ccr_requirement_pct ? "negative" : "positive") + '">' + number(q.ccr_pct, 1) + "%</td></tr>").join("") + "</tbody></table></div>";
    const totalBreach = Math.max(1, m.breach_count);
    const breaches = r.queues.map(q => '<div class="bar-row"><span>' + esc(q.queue) + '</span><div class="bar-track"><div class="bar-fill" style="width:' + Math.max(0, Math.min(100, q.breach_count / totalBreach * 100)) + '%"></div></div><span class="bar-value">' + q.breach_count + " of " + q.ticket_count + "</span></div>").join("");
    $("#content").innerHTML = alert + '<div class="grid">' + panel("The capacity trajectory", "Three archived snapshots · selected date is emphasized", timeline) + panel("Exception queue", r.warnings.length + " recorded warnings · select one to inspect", warningsHtml()) + '</div><div class="grid">' + panel("Queue breakdown", "Tickets routed after correction; not necessarily the filed queue.", queues) + panel("Where breaches sit", "SLA breaches by routed queue", breaches) + '</div>' + ticketPanel();
    bindCommon(); bindTickets();
  }
  function ticketPanel() {
    const r = getRun();
    return panel("Ticket explorer", "Follow a ticket from its source file through the routing and SLA outcome.",
      '<div class="toolbar"><input id="search" type="search" aria-label="Search tickets" placeholder="Search ticket ID or symptom" value="' + esc(filters.query) + '"><select id="queue-filter" aria-label="Filter queue"><option value="all">All queues</option>' + r.queues.map(q => '<option' + (filters.queue === q.queue ? " selected" : "") + '>' + esc(q.queue) + '</option>').join("") + '</select><select id="sort" aria-label="Sort tickets"><option value="handle">Largest handle time</option><option value="priority"' + (filters.sort === "priority" ? " selected" : "") + '>Highest priority</option><option value="id"' + (filters.sort === "id" ? " selected" : "") + '>Ticket ID</option></select></div><div id="ticket-table"></div>');
  }
  function renderTicketTable() {
    const r = getRun(), q = filters.query.toLowerCase();
    const tickets = r.tickets.filter(t => (filters.queue === "all" || t.implied_queue === filters.queue) && ((t.ticket_id + " " + t.symptom_code).toLowerCase().includes(q)))
      .sort((a, b) => filters.sort === "id" ? a.ticket_id.localeCompare(b.ticket_id) : filters.sort === "priority" ? PRIORITY_ORDER.indexOf(a.effective_priority) - PRIORITY_ORDER.indexOf(b.effective_priority) : Number(b.estimated_handle_minutes) - Number(a.estimated_handle_minutes));
    $("#ticket-table").innerHTML = tickets.length ? '<div class="table-scroll"><table><thead><tr><th>Ticket</th><th>Queue</th><th>Priority</th><th>Handle time</th><th>SLA</th><th>Inspect</th></tr></thead><tbody>' + tickets.map(t => '<tr><td>' + esc(t.ticket_id) + '</td><td>' + esc(t.implied_queue) + (t.misrouted ? ' <span class="badge warn">corrected</span>' : '') + '</td><td>' + esc(t.effective_priority) + '</td><td class="num">' + mins(t.estimated_handle_minutes, 0) + '</td><td>' + badge(t.sla_status) + '</td><td><button class="link" data-ticket="' + esc(t.ticket_id) + '">Evidence ↗</button></td></tr>').join("") + '</tbody></table></div><p class="caption">' + tickets.length + " of " + r.tickets.length + ' tickets</p>' : '<div class="empty">No tickets match these filters.</div>';
    document.querySelectorAll("[data-ticket]").forEach(b => b.onclick = () => showTicket(b.dataset.ticket));
  }
  function bindTickets() {
    renderTicketTable();
    $("#search").oninput = e => { filters.query = e.target.value; renderTicketTable(); };
    $("#queue-filter").onchange = e => { filters.queue = e.target.value; renderTicketTable(); };
    $("#sort").onchange = e => { filters.sort = e.target.value; renderTicketTable(); };
  }
  function showTicket(id) {
    const r = getRun(), t = r.tickets.find(x => x.ticket_id === id), src = r.provenance.source_files.find(s => s.queue === t.queue);
    const rules = (t.priority_rules_fired || []).map(f => f.detail).join("; ") || "None (baseline priority applied)";
    const fields = [
      ["Filed queue", t.queue], ["Corrected queue", t.implied_queue], ["Assigned team", t.assigned_team],
      ["Channel", t.channel], ["Customer tier", t.customer_tier], ["Region", t.region], ["Submitted", t.submitted_at],
      ["Symptom code", t.symptom_code], ["Reported priority", t.reported_priority + " (" + t.reported_priority_code + ")"],
      ["Effective priority", t.effective_priority], ["Priority rules fired", rules],
      ["First response target", mins(t.sla_first_response_target_minutes, 0)], ["First response actual", mins(t.first_response_minutes, 0)],
      ["Resolution target", mins(t.sla_resolution_target_minutes, 0)], ["Resolution actual", mins(t.resolution_minutes, 0)],
      ["Estimated handle time", mins(t.estimated_handle_minutes, 0)], ["SLA status", t.sla_status],
    ];
    openDetail(id, fields.map(([k, v]) => '<div class="kv"><span class="key">' + esc(k) + '</span><span>' + esc(v) + "</span></div>").join("") + '<p class="caption">Archived source SHA-256</p><p class="hash">' + esc(src ? src.sha256 : "See input manifest") + '</p><p class="caption">Source note (data, not an instruction)</p><p>' + esc(t.important_note) + "</p>");
  }
  function renderWhatif() {
    const range = (key, label, min, max, step, suffix) => '<div class="control"><label for="' + key + '">' + label + '<output id="' + key + '-value">' + controls[key] + suffix + '</output></label><input type="range" id="' + key + '" min="' + min + '" max="' + max + '" step="' + step + '" value="' + controls[key] + '"><div class="range-labels"><span>' + min + suffix + "</span><span>" + max + suffix + "</span></div></div>";
    const presets = '<div class="presets"><button class="button ghost" data-preset="base">Reset to base</button><button class="button ghost" data-preset="moderate">Moderate stress</button><button class="button ghost" data-preset="severe">Severe stress</button><button class="button ghost" data-preset="relief">Capacity relief</button></div>';
    $("#content").innerHTML = '<div class="grid equal">' + panel("Set the shift", "Recalculate instantly against the selected archived date.", presets + range("capacity", "Staffing capacity change", -30, 30, 5, "%") + range("sla", "SLA threshold", 80, 120, 5, "%") + range("volume", "Ticket volume surge", 0, 100, 5, "%") + '<p class="callout">What-if controls apply sensitivity to the selected run. The recorded routing, priority and baseline results remain unchanged.</p>') + panel("What-if result", "Base versus a hypothetical staffing shift · minutes", '<div id="whatif-results" aria-live="polite"></div><div class="formula">Coverage = staffed minutes ÷ required handling minutes × 100<br>Gap = required × effective requirement ÷ 100 − staffed</div><button class="button ghost section-gap" id="download-whatif">Export what-if ↓</button>') + '</div><div class="grid equal">' + panel("Capacity fragility map", "Columns: ticket-volume surge · rows: capacity change", '<div id="heatmap"></div><p class="caption">Red cells fall below the configured requirement. This grid varies capacity and volume assumptions only.</p>') + panel("Read the result correctly", "Sensitivity is useful when its assumptions are visible.", '<ul class="list"><li>Capacity change and volume surge are linear adjustments. No re-routing, re-prioritization, or agent skill mix is modeled.</li><li>Coverage compares staffed minutes with required handling minutes. See the methodology for definitions and scope.</li><li>Required handling time sums proxy estimates across queues; it is not a measured historical average handle time.</li><li>SLA threshold flexes the requirement only; individual ticket SLA statuses are not recalculated.</li></ul>') + "</div>";
    ["capacity", "sla", "volume"].forEach(k => $("#" + k).oninput = e => { controls[k] = Number(e.target.value); renderWhatifResults(); });
    document.querySelectorAll("[data-preset]").forEach(b => b.onclick = () => { controls = b.dataset.preset === "severe" ? {capacity: -25, sla: 100, volume: 30} : b.dataset.preset === "moderate" ? {capacity: -10, sla: 100, volume: 15} : b.dataset.preset === "relief" ? {capacity: 15, sla: 100, volume: 0} : {capacity: 0, sla: 100, volume: 0}; renderWhatif(); });
    $("#download-whatif").onclick = () => saveFile("supportops-whatif-" + getRun().run_date + ".json", {run_id: getRun().run_id, mode: "browser_sensitivity", parameters: controls, result: whatif(getRun(), controls.capacity, controls.sla, controls.volume)});
    renderWhatifResults();
  }
  function renderWhatifResults() {
    const r = getRun(), s = whatif(r, controls.capacity, controls.sla, controls.volume);
    ["capacity", "sla", "volume"].forEach(k => $("#" + k + "-value").textContent = controls[k] + "%");
    $("#whatif-results").innerHTML = '<p>' + badge(s.status) + '</p>' + [["Staffed capacity", mins(s.available_agent_minutes)], ["Required handling", mins(s.required_handling_minutes)], ["Capacity coverage", number(s.ccr_pct, 1) + "%"], ["Additional capacity needed", mins(s.capacity_gap_minutes)]].map(([k, v]) => '<div class="scenario-result"><span>' + k + '</span><strong class="' + (k.includes("coverage") && s.status === "BREACH" ? "negative" : "") + '">' + v + "</strong></div>").join("");
    let cells = '<div class="heatmap"><div class="cell head">↓ / →</div>' + [0, 25, 50, 75, 100].map(v => '<div class="cell head">' + v + "%</div>").join("");
    [-30, -15, 0, 15, 30].forEach(c => { cells += '<div class="cell head">' + c + "%</div>"; [0, 25, 50, 75, 100].forEach(v => { const ccr = whatif(r, c, 100, v).ccr_pct; cells += '<div class="cell ' + (ccr < r.metrics.ccr_requirement_pct ? "hot" : ccr < 120 ? "warm" : "cool") + '" title="Capacity ' + c + "%, volume surge " + v + '%">' + number(ccr, 0) + "%</div>"; }); });
    $("#heatmap").innerHTML = cells + "</div>";
  }
  function renderEvidence() {
    const r = getRun(), p = r.provenance;
    const hashes = [["Run identity", p.identity_sha256], ["Input data", p.data_sha256], ["Configuration", p.config_sha256], ["Code version", p.code_sha256], ["Previous result", p.previous_result_sha256 || "First date · no predecessor"]];
    const proof = hashes.map(([k, v]) => '<div class="kv"><span class="key">' + k + '</span><span class="hash">' + esc(v) + "</span></div>").join("") + '<p class="caption">Hashes detect changes when checked against the pinned manifest. They are not digital signatures or protection against an administrator replacing every artifact.</p>';
    const files = '<div class="table-scroll"><table><thead><tr><th>Archived input</th><th>Rows</th><th>SHA-256</th></tr></thead><tbody>' + p.source_files.map(f => '<tr><td>' + esc(f.file) + '</td><td>' + f.rows + '</td><td class="hash" title="' + esc(f.sha256) + '">' + esc(f.sha256.slice(0, 16)) + "…</td></tr>").join("") + "</tbody></table></div>";
    const checks = (data.control_checks && data.control_checks.checks) || [];
    const checkHtml = checks.length ? checks.map(c => '<div class="control-pass"><span class="tick">' + (c.passed === false || c.status === "FAIL" ? "×" : "✓") + '</span><div><strong>' + esc(c.title || c.name || c.id) + '</strong><p>' + esc(c.description || c.detail || c.message || "Verified by the reproducible control suite.") + "</p></div></div>").join("") : (data.controls || []).map(c => '<div class="control-pass"><span class="tick">◇</span><div><strong>' + esc(c.title) + '</strong><p>' + esc(c.description) + "</p></div></div>").join("");
    const mapping = '<div class="table-scroll"><table><thead><tr><th>Metric</th><th>Source</th><th>Method</th></tr></thead><tbody>' + (r.source_mapping || []).map(s => '<tr><td>' + esc(s.metric) + '</td><td>' + esc(s.source) + '</td><td style="white-space:normal;text-align:left">' + esc(s.method) + "</td></tr>").join("") + "</tbody></table></div>";
    $("#content").innerHTML = '<div class="grid equal">' + panel("Pinned provenance", "Every stage checks the evidence it consumes.", badge(p.integrity) + proof) + panel("Data contract", "3 files · " + r.metrics.ticket_count + " tickets · no more than 10 per file", files + '<p class="caption section-gap">Checks cover schema, cross-file identifiers, controlled vocabularies, finite values, submission timestamps, and permitted channels/tiers/regions.</p><div class="callout">Input and configuration snapshots travel with the run. Edits create a new identity; existing evidence is preserved.</div>') + '</div><div class="grid equal">' + panel(checks.length ? "Executed control checks" : "Implemented controls", checks.length ? "Recorded automated checks, exported with this portfolio build." : "See the test suite for executable evidence.", checkHtml) + panel("Execution journal", "Ordered events from the actual Python run.", '<div class="code">' + esc(r.logs.map(l => String(l.sequence).padStart(3, "0") + " | " + l.stage + " | " + l.event + " | " + l.message).join("\n")) + '</div><button class="button ghost section-gap" id="export-logs">Export run events ↓</button>') + "</div>" + panel("Metric lineage", "Read the assumptions alongside the result.", mapping);
    $("#export-logs").onclick = () => saveFile("supportops-events-" + r.run_date + ".jsonl", r.logs.map(l => JSON.stringify(l)).join("\n"), "application/x-ndjson");
  }
  function renderAssistant() {
    const r = getRun();
    const stages = r.stages.map((s, i) => '<div class="stage"><span class="stage-icon">' + (s.status === "COMPLETED" ? "✓" : i + 1) + '</span><div><strong>' + esc(s.stage) + '</strong><p>' + esc(s.status) + " · " + s.artifact_count + ' artifacts</p></div><span class="stage-time">' + (s.duration_seconds == null ? "recorded" : number(s.duration_seconds, 3) + "s") + "</span></div>").join("");
    const questions = '<div class="questions"><button class="button ghost" data-question="capacity">Explain capacity</button><button class="button ghost" data-question="changed">What changed?</button><button class="button ghost" data-question="handoff">Prepare the handoff</button></div><div class="answer" id="answer" aria-live="polite"></div>';
    const plan = r.plan.map((s, i) => '<div class="trace-step"><span>' + String(i + 1).padStart(2, "0") + '</span><div><strong>' + esc(s.tool) + '</strong><p>' + esc(s.reason) + '</p><p class="hash">Requires: ' + esc(Array.isArray(s.requires) ? s.requires.join(", ") : s.requires) + "</p></div></div>").join("");
    $("#content").innerHTML = '<div class="grid equal">' + panel("Ops assistant", "Evidence-linked answers from the selected run", questions + '<p class="boundary">Explanations follow the registered ops tools and cite verified values. Ticket free text is never read as an instruction. The methodology documents the reporting logic.</p><button class="button ghost section-gap" id="export-brief">Export handoff brief ↓</button>') + panel("Run progression", "Replay the recorded execution without rerunning Python.", '<div class="timeline">' + stages + '</div><p>' + badge(r.execution_status) + '</p><p class="caption">Execution completion and human approval are separate states.</p>' + badge("PENDING_HUMAN_REVIEW")) + '</div><div class="grid equal">' + panel("Inspect the tool plan", "Explicit prerequisites and permitted tool actions", '<div class="trace">' + plan + "</div>") + panel("Successor handoff", "Questions an incoming owner should bring to the next review.", '<ul class="list">' + (r.brief.questions || []).map(q => "<li>" + esc(q) + "</li>").join("") + '</ul><div class="callout">Review the evidence before escalation. A report cannot approve a run, change thresholds, or reassign staff.</div><label class="field-label" for="run-command">Run this date locally</label><div class="code" id="run-command">python scripts/supportops.py all --run-date ' + r.run_date + '</div><button class="button ghost section-gap" id="copy-command">Copy command</button>') + "</div>";
    const showAnswer = k => { const a = answer(r, k); $("#answer").innerHTML = "<p>" + esc(a.text) + '</p><span class="citation">' + esc(a.source) + "</span>"; };
    document.querySelectorAll("[data-question]").forEach(b => b.onclick = () => showAnswer(b.dataset.question));
    $("#export-brief").onclick = () => saveFile("supportops-handoff-" + r.run_date + ".json", r.brief);
    $("#copy-command").onclick = async () => { const text = "python scripts/supportops.py all --run-date " + r.run_date; try { await navigator.clipboard.writeText(text); toast("Run command copied"); } catch (_e) { openDetail("Run command", '<div class="code">' + esc(text) + "</div>"); } };
    showAnswer("capacity");
  }
  function bindCommon() {
    document.querySelectorAll("[data-go]").forEach(b => b.onclick = () => { view = b.dataset.go; render(); });
    document.querySelectorAll("[data-warning]").forEach(b => b.onclick = () => {
      const r = getRun(), w = r.warnings[Number(b.dataset.warning)];
      openDetail(w.title, badge(w.severity) + "<p>" + esc(w.message) + '</p><div class="kv"><span class="key">Metric</span><span>' + esc(w.metric) + '</span></div><div class="kv"><span class="key">Current</span><span>' + esc(w.current) + '</span></div><div class="kv"><span class="key">Previous</span><span>' + esc(w.previous == null ? "Unavailable" : w.previous) + '</span></div><div class="kv"><span class="key">Threshold</span><span>' + esc(w.threshold == null ? "n/a" : w.threshold) + '</span></div><p class="caption">Source: result.json → warnings[' + b.dataset.warning + ']</p><p class="hash">Run ' + esc(r.run_id) + '</p><p class="caption">Inspect the queue and ticket tables to reconcile this movement. Root cause requires separate analysis.</p>');
    });
  }
  function render() {
    const r = getRun(); updateUrl();
    $("#date-picker").innerHTML = data.dates.map((d, i) => '<button data-date="' + i + '" aria-pressed="' + (i === selected) + '">' + d.run_date.slice(5).replace("-", "/") + ", 2026</button>").join("");
    document.querySelectorAll("[data-date]").forEach(b => b.onclick = () => { if (playing) return; selected = Number(b.dataset.date); controls = {capacity: 0, sla: 100, volume: 0}; filters = {queue: "all", query: "", sort: "handle"}; render(); });
    $("#run-meta").textContent = "Run " + r.run_id + " · " + r.execution_status + " · " + r.provenance.integrity + " · " + data.dates.length + " archived dates";
    document.querySelectorAll("[data-view]").forEach(b => { if (b.dataset.view === view) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
    renderMetrics();
    ({overview: renderOverview, whatif: renderWhatif, evidence: renderEvidence, assistant: renderAssistant})[view]();
  }
  document.querySelectorAll("[data-view]").forEach(b => b.onclick = () => { view = b.dataset.view; render(); });
  $("#close-detail").onclick = () => $("#detail").close();
  $("#detail").addEventListener("click", e => { if (e.target === $("#detail")) { const rect = $("#detail").getBoundingClientRect(); if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) $("#detail").close(); } });
  $("#download").onclick = () => saveFile("supportops-evidence-" + getRun().run_date + ".json", getRun());
  $("#replay").onclick = () => {
    if (playing) return; playing = true; $("#replay").disabled = true;
    const r = getRun(), events = r.logs; let index = 0;
    openDetail("Replay · " + r.run_date, '<p class="playback-note">Playback of the selected run’s recorded execution journal.</p><div class="code" id="replay-log" aria-live="off"></div><p id="replay-status" role="status">Replaying execution journal…</p>');
    const step = () => {
      if (!$("#detail").open) { stop(); return; }
      const item = events[index++];
      if (item) $("#replay-log").textContent += String(item.sequence).padStart(3, "0") + " | " + item.stage + " | " + item.event + "\n" + item.message + "\n\n";
      $("#replay-log").scrollTop = $("#replay-log").scrollHeight;
      if (index >= events.length) { $("#replay-status").textContent = "Recorded run complete · " + r.status + " · " + r.warnings.length + " warnings"; stop(); }
    };
    const stop = () => { clearInterval(replayTimer); playing = false; $("#replay").disabled = false; };
    if (!events.length) { $("#replay-status").textContent = "No recorded events are available."; stop(); return; }
    replayTimer = setInterval(step, 180); step();
  };
  $("#detail").addEventListener("close", () => { if (playing) { clearInterval(replayTimer); playing = false; $("#replay").disabled = false; } });
  render();
})();
