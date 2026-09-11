/* Pure browser-logic checks; no DOM or browser automation is involved. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const data = require('../results/dashboard-data.json');
const {whatif, answer, esc} = require('../web/dashboard.js');
const near = (a,b) => assert.ok(Math.abs(a-b) <= 0.000001, `${a} differs from ${b}`);

test('browser whatif agrees with Python presets for all three dates', () => {
  for (const run of data.dates) {
    for (const expected of run.whatif_grid) {
      const actual = whatif(run, expected.capacity_change_pct, expected.sla_threshold_pct, expected.volume_increase_pct);
      for (const key of ['available_agent_minutes','required_handling_minutes','ccr_pct','capacity_gap_minutes']) near(actual[key], expected[key]);
      assert.equal(actual.status, expected.status);
    }
  }
});

test('zero shock preserves baseline and worsening shocks reduce coverage', () => {
  for (const run of data.dates) {
    const base = whatif(run, 0, 100, 0), stress = whatif(run, -25, 100, 30);
    near(base.available_agent_minutes, run.metrics.available_agent_minutes);
    near(base.ccr_pct, run.metrics.ccr_pct);
    assert.ok(stress.ccr_pct < base.ccr_pct);
    assert.ok(stress.capacity_gap_minutes >= base.capacity_gap_minutes);
  }
});

test('gap follows configured requirement; zero-required sentinel matches Python', () => {
  const run = JSON.parse(JSON.stringify(data.dates[2]));
  run.metrics.ccr_requirement_pct = 120;
  const actual = whatif(run, 0, 100, 0);
  near(actual.capacity_gap_minutes, Math.max(0, run.metrics.required_handling_minutes*1.2 - run.metrics.available_agent_minutes));
  run.metrics.required_handling_minutes = 0;
  assert.equal(whatif(run,0,100,0).ccr_pct, 999);
  assert.equal(whatif(run,0,100,0).capacity_gap_minutes, 0);
});

test('invalid and nonfinite browser inputs fail explicitly', () => {
  for (const parameters of [[NaN,100,0],[Infinity,100,0],[31,100,0],[-31,100,0],[0,79,0],[0,121,0],[0,100,101],[0,100,-1]]) {
    assert.throws(() => whatif(data.dates[0], ...parameters));
  }
});

test('answers cite current artifacts and preserve no-predecessor limitation', () => {
  assert.match(answer(data.dates[0],'changed').text, /no preceding run/i);
  assert.match(answer(data.dates[2],'capacity').text, /96\.3%/);
  for (const run of data.dates) for (const question of ['capacity','changed','handoff']) {
    assert.match(answer(run,question).source, /result\.json/);
  }
});

test('source text is escaped before being inserted into HTML', () => {
  assert.equal(esc('<script>"&\'</script>'), '&lt;script&gt;&quot;&amp;&#39;&lt;/script&gt;');
  assert.equal(esc(null), '');
});
