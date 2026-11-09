import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import test from 'node:test';

const source = await readFile(new URL('./screenerContext.ts', import.meta.url), 'utf8');
const { fieldReasons, dataAgeDays } = await import(
  `data:text/javascript;base64,${Buffer.from(stripTypeScriptTypes(source)).toString('base64')}`
);

test('fieldReasons matches the complete trimmed prefix before the first colon', () => {
  assert.deepEqual(fieldReasons([
    ' revenue : Missing annual filing ',
    'revenue_growth: Growth unavailable',
    'net_revenue: Other revenue',
    'Revenue: Different case',
    'revenue.extra: Different field',
    'revenue: Source says: unavailable',
    'Unprefixed warning',
    'Warning mentions revenue without a prefix',
  ], 'revenue'), ['Missing annual filing', 'Source says: unavailable']);
});

test('grade groups grade_score and dotted grade prefixes in input order', () => {
  assert.deepEqual(fieldReasons([
    'grade.profitability: Profitability incomplete',
    'grade_score: Score unavailable',
    'grade: Grade withheld',
    'grade.governance.board: Board data missing',
    'grade_score_extra: Unrelated score',
    'grades: Unrelated plural',
    'gradebook: Unrelated prefix',
    'grade_extra: Unrelated suffix',
    'revenue: Missing revenue',
    'upside_pct: Missing valuation',
  ], 'grade'), [
    'Profitability incomplete', 'Score unavailable', 'Grade withheld', 'Board data missing',
  ]);
  assert.deepEqual(fieldReasons([
    'grade: Group warning', 'grade.other: Other component', 'grade_score: Exact score',
  ], 'grade_score'), ['Exact score']);
});

test('upside groups valuation confidence and price date without unrelated metrics', () => {
  const reasons = [
    'price_date: Price is stale',
    'upside_pct: Upside withheld',
    'valuation_confidence: Low confidence',
    'fair_value: Fair value missing',
    'price: Price missing',
    'price_date_extra: Other date',
    'valuation_confidence.detail: Other confidence field',
    'upside_pct_extra: Other upside field',
    'grade: Grade missing',
  ];
  assert.deepEqual(fieldReasons(reasons, 'upside_pct'), [
    'Price is stale', 'Upside withheld', 'Low confidence',
  ]);
  assert.deepEqual(fieldReasons(reasons, 'price_date'), ['Price is stale']);
  assert.deepEqual(fieldReasons(reasons, 'valuation_confidence'), ['Low confidence']);
  assert.deepEqual(fieldReasons(reasons, 'unknown'), []);
});

test('fieldReasons trims and deduplicates nonempty text across grouped prefixes', () => {
  const reasons = Object.freeze([
    'grade:   Shared warning  ',
    'grade_score: Shared warning',
    'grade.detail: Second warning',
    'grade: Shared warning ',
    'grade: ',
    'grade_score:\t',
    'grade: shared warning',
    'No colon',
    ': Unscoped warning',
  ]);
  assert.deepEqual(fieldReasons(reasons, 'grade'), [
    'Shared warning', 'Second warning', 'shared warning',
  ]);
  assert.deepEqual(fieldReasons([], 'grade'), []);
});

test('dataAgeDays preserves legitimate zero ages including an identical instant', () => {
  const now = Date.parse('2026-11-09T18:30:00Z');
  assert.equal(dataAgeDays('2026-11-09', now), 0);
  assert.equal(dataAgeDays('2026-11-09T18:30:00Z', now), 0);
  assert.equal(dataAgeDays('2026-11-09T00:00:00.001Z', now), 0);
});

test('dataAgeDays counts UTC day boundaries rather than complete 24-hour periods', () => {
  assert.equal(dataAgeDays('2026-11-08T23:59:59.999Z', Date.parse('2026-11-09T00:00:00Z')), 1);
  assert.equal(dataAgeDays('2026-12-31', Date.parse('2027-01-01T00:00:00Z')), 1);
  assert.equal(dataAgeDays('2024-02-28', Date.parse('2024-03-01T00:00:00Z')), 2);
  assert.equal(dataAgeDays('2024-02-29', Date.parse('2024-03-01T00:00:00Z')), 1);
  assert.equal(dataAgeDays('2000-02-29', Date.parse('2000-03-01T00:00:00Z')), 1);
  assert.equal(dataAgeDays('2023-02-28', Date.parse('2023-03-01T00:00:00Z')), 1);
});

test('explicit ISO offsets determine the UTC date, including fractional seconds', () => {
  const now = Date.parse('2026-11-09T12:00:00Z');
  assert.equal(dataAgeDays('2026-11-09T00:30:00+02:00', now), 1);
  assert.equal(dataAgeDays('2026-11-08T23:30:00-02:00', now), 0);
  assert.equal(dataAgeDays('2026-11-09T17:30:00+05:30', now), 0);
  assert.equal(dataAgeDays('2026-11-08T18:30:00.123-05:30', now), 0);
  assert.equal(dataAgeDays('2024-03-01T00:30:00+01:00', Date.parse('2024-03-01T00:00:00Z')), 1);
});

test('date-only ages stay the same under different host timezones', () => {
  const original = process.env.TZ;
  try {
    for (const timezone of ['UTC', 'America/Los_Angeles', 'Asia/Tokyo']) {
      process.env.TZ = timezone;
      assert.equal(dataAgeDays('2026-11-09', Date.parse('2026-11-09T00:30:00Z')), 0, timezone);
      assert.equal(dataAgeDays('2024-03-10', Date.parse('2024-03-11T00:00:00Z')), 1, timezone);
    }
  } finally {
    if (original === undefined) delete process.env.TZ;
    else process.env.TZ = original;
  }
});

test('invalid and overflowed calendar dates are rejected instead of normalized', () => {
  const now = Date.parse('2026-11-09T12:00:00Z');
  for (const value of [
    '2026-02-29', '2024-02-30', '1900-02-29', '2026-04-31',
    '2026-00-01', '2026-13-01', '2026-11-00', '2026-11-31',
    '2026-02-29T00:00:00Z', '2024-02-30T12:00:00+01:00',
    '2026-04-31T00:00:00-05:00', '2026-13-01T00:00:00Z',
  ]) assert.equal(dataAgeDays(value, now), null, value);
});

test('malformed dates, invalid times, and timestamps without explicit timezones are rejected', () => {
  const now = Date.parse('2026-11-09T12:00:00Z');
  for (const value of [
    '', ' ', 'not a date', '11/08/2026', '2026-1-08', '2026-11-8',
    '20261108', '2026-11', '2026-11-08junk',
    '2026-11-08T12:00:00', '2026-11-08T12:00',
    '2026-11-08T24:00:00Z', '2026-11-08T25:00:00Z',
    '2026-11-08T12:60:00Z', '2026-11-08T12:00:60Z',
    '2026-11-08T12:00:00+24:00', '2026-11-08T12:00:00+01:60',
    '2026-11-08T12:00:00Zjunk', '2026-11-08T12:00:00.Z',
  ]) assert.equal(dataAgeDays(value, now), null, value);
});

test('missing values and nonfinite now values have no age', () => {
  assert.equal(dataAgeDays(null, Date.parse('2026-11-09T12:00:00Z')), null);
  for (const now of [NaN, Infinity, -Infinity]) {
    assert.equal(dataAgeDays('2026-11-08', now), null, String(now));
  }
});

test('future instants are rejected even within the current UTC day', () => {
  const now = Date.parse('2026-11-09T12:00:00Z');
  for (const value of [
    '2026-11-10', '2026-11-09T12:00:00.001Z',
    '2026-11-09T13:00:00Z', '2026-11-09T08:00:01-04:00',
  ]) assert.equal(dataAgeDays(value, now), null, value);
});
