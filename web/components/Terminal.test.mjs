import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import test from 'node:test';

// Execute the actual load closure without React, network access, or dependencies.
const source = readFileSync(new URL('./Terminal.tsx', import.meta.url), 'utf8');
const start = source.indexOf('  async function load(');
const end = source.indexOf('\n  return (', start);
assert.ok(start > 0 && end > start);
const loadSource = stripTypeScriptTypes(source.slice(start, end));
const flush = () => new Promise((resolve) => setImmediate(resolve));
function harness() {
  const state = { report: null, tab: 'memo' };
  const calls = {};
  const timers = [];
  const queued = [];
  let deferUpdates = false;
  const env = { current: { current: 0 } };
  for (const key of ['Ticker', 'Loading', 'Error', 'Slow', 'Tab', 'Report']) {
    env[`set${key}`] = (value) => {
      const apply = () => { state[key.toLowerCase()] = typeof value === 'function' ? value(state[key.toLowerCase()]) : value; };
      if (deferUpdates && typeof value === 'function') queued.push(apply);
      else apply();
    };
  }
  for (const kind of ['Report', 'Governance', 'PayEfficiency', 'Trends', 'Risks']) {
    calls[kind] = [];
    env[`fetch${kind}`] = (ticker) => new Promise((resolve, reject) => calls[kind].push({ ticker, resolve, reject }));
  }
  env.setTimeout = (callback) => { timers.push(callback); return timers.length - 1; };
  env.clearTimeout = () => {}; // Retain callbacks to exercise even already-queued stale timers.
  const load = new Function(...Object.keys(env), `${loadSource}; return load;`)(...Object.values(env));
  return { state, calls, timers, load, queueUpdates: () => { deferUpdates = true; }, applyUpdates: () => queued.splice(0).forEach((apply) => apply()) };
}
const report = (ticker, name) => ({ ticker, name });

for (const symbol of ['MSFT', 'AAPL']) {
  test(`latest request wins over stale success, including repeated symbol: ${symbol}`, async () => {
    const h = harness();
    const old = h.load('AAPL');
    const latest = h.load(symbol);
    h.calls.Report[1].resolve(report(symbol, 'new'));
    await latest;
    h.state.tab = 'trends';
    h.calls.Report[0].resolve(report('AAPL', 'old'));
    await old;
    assert.equal(h.state.report.name, 'new');
    assert.equal(h.state.tab, 'trends');
    assert.equal(h.calls.Governance.length, 1);
    assert.equal(h.calls.PayEfficiency.length, 1);
  });
}

test('stale error, finally and slow timer cannot change newer loading state', async () => {
  const h = harness();
  const old = h.load('AAPL');
  h.timers[0]();
  const latest = h.load('AAPL');
  assert.equal(h.state.slow, false);
  h.timers[0]();
  assert.equal(h.state.slow, false);
  h.timers[1]();
  h.calls.Report[0].reject(new Error('old error'));
  await old;
  assert.equal(h.state.error, null);
  assert.equal(h.state.loading, true);
  assert.equal(h.state.slow, true);
  h.calls.Report[1].reject(new Error('current error'));
  await latest;
  assert.equal(h.state.error, 'current error');
  assert.equal(h.state.loading, false);
  assert.equal(h.state.slow, false);
});

for (const stage of ['Governance', 'PayEfficiency', 'Trends', 'Risks']) {
  for (const outcome of ['resolve', 'reject']) {
    test(`stale ${stage} ${outcome} ignored for repeated ticker`, async () => {
      const h = harness();
      const old = h.load('AAPL');
      h.calls.Report[0].resolve(report('AAPL', 'old'));
      await old;
      if (['Trends', 'Risks'].includes(stage)) {
        h.calls.PayEfficiency[0].resolve({ old: true });
        await flush();
      }
      if (stage === 'Risks') {
        h.calls.Trends[0].resolve({ old: true });
        await flush();
      }
      const latest = h.load('AAPL');
      const fresh = { ...report('AAPL', 'new'), governance: {}, payEfficiency: {} };
      h.calls.Report[1].resolve(fresh);
      await latest;
      h.calls[stage][0][outcome](outcome === 'resolve' ? { stale: true } : new Error('stale'));
      await flush();
      assert.deepEqual(h.state.report, fresh);
      if (stage === 'PayEfficiency') assert.equal(h.calls.Trends.length, 0);
      if (stage === 'Trends') assert.equal(h.calls.Risks.length, 0);
    });
  }
}

test('queued React updater rechecks identity when applied', async () => {
  const h = harness();
  const old = h.load('AAPL');
  h.calls.Report[0].resolve(report('AAPL', 'old'));
  await old;
  h.queueUpdates();
  h.calls.Governance[0].resolve({ stale: true });
  await flush();
  const latest = h.load('AAPL');
  const fresh = { ...report('AAPL', 'new'), governance: {}, payEfficiency: {} };
  h.calls.Report[1].resolve(fresh);
  await latest;
  h.applyUpdates();
  assert.deepEqual(h.state.report, fresh);
});

test('current deferred successes and errors still update the report in order', async () => {
  const h = harness();
  const pending = h.load(' aapl ');
  h.calls.Report[0].resolve(report('AAPL', 'current'));
  await pending;
  assert.equal(h.calls.Report[0].ticker, 'AAPL');
  h.calls.Governance[0].resolve({ current: true });
  h.calls.PayEfficiency[0].reject(new Error('pay unavailable'));
  await flush();
  assert.deepEqual(h.state.report.governance, { current: true });
  assert.equal(h.state.report.payEfficiencyError, 'pay unavailable');
  h.calls.Trends[0].resolve({ current: true });
  await flush();
  h.calls.Risks[0].resolve({ current: true });
  await flush();
  assert.deepEqual(h.state.report.trends, { current: true });
  assert.deepEqual(h.state.report.risks, { current: true });
});
