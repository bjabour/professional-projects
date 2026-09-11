/* Pure browser-logic checks; no DOM or browser automation is involved. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const data = require('../results/dashboard-data.json');
const {scenario, answer, esc} = require('../web/dashboard.js');
const near = (a,b) => assert.ok(Math.abs(a-b) <= 0.000001, `${a} differs from ${b}`);

test('browser scenarios agree with Python presets for all three dates', () => {
  for (const run of data.dates) {
    for (const expected of run.scenario_grid.filter(s => s.rate_bps >= 0)) {
      const actual = scenario(run, expected.rate_bps, expected.buffer_haircut_pct, expected.outflow_increase_pct);
      for (const key of ['pv_change_usd_m','stressed_pv_usd_m','lcr_pct','liquidity_gap_usd_m']) near(actual[key], expected[key]);
      assert.equal(actual.status, expected.status);
    }
  }
});

test('zero shock preserves baseline and positive shocks worsen liquidity', () => {
  for (const run of data.dates) {
    const base = scenario(run, 0, 0, 0), stress = scenario(run, 100, 5, 10);
    near(base.stressed_pv_usd_m, run.metrics.total_pv_usd_m);
    near(base.lcr_pct, run.metrics.lcr_pct);
    assert.ok(stress.lcr_pct < base.lcr_pct);
    assert.ok(stress.liquidity_gap_usd_m >= base.liquidity_gap_usd_m);
  }
});

test('gap follows configured requirement; zero-outflow sentinel matches Python', () => {
  const run = JSON.parse(JSON.stringify(data.dates[2]));
  run.metrics.lcr_requirement_pct = 120;
  const actual = scenario(run, 0, 0, 0);
  near(actual.liquidity_gap_usd_m, Math.max(0, run.metrics.net_cash_outflow_30d_usd_m*1.2-run.metrics.liquidity_buffer_usd_m));
  run.metrics.net_cash_outflow_30d_usd_m = 0;
  assert.equal(scenario(run,0,0,0).lcr_pct, 999);
  assert.equal(scenario(run,0,0,0).liquidity_gap_usd_m, 0);
});

test('invalid and nonfinite browser inputs fail explicitly', () => {
  for (const parameters of [[NaN,0,0],[Infinity,0,0],[0,41,0],[-1,0,0],[201,0,0],[0,0,61],[0,-1,0]]) {
    assert.throws(() => scenario(data.dates[0], ...parameters));
  }
});

test('answers cite current artifacts and preserve no-predecessor limitation', () => {
  assert.match(answer(data.dates[0],'changed').text, /no preceding run/i);
  assert.match(answer(data.dates[2],'liquidity').text, /91\.8%/);
  for (const run of data.dates) for (const question of ['liquidity','changed','handoff']) {
    assert.match(answer(run,question).source, /result\.json/);
    assert.doesNotMatch(answer(run,question).source, /risk_summary/);
  }
});

test('source text is escaped before being inserted into HTML', () => {
  assert.equal(esc('<script>"&\'</script>'), '&lt;script&gt;&quot;&amp;&#39;&lt;/script&gt;');
  assert.equal(esc(null), '');
});
