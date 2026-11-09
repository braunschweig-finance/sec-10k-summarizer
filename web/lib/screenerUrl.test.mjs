import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import test from 'node:test';

const source = await readFile(new URL('./screenerUrl.ts', import.meta.url), 'utf8');
const { DEFAULT_SCREENER_STATE, parseScreenerUrl, serializeScreenerUrl } = await import(
  `data:text/javascript;base64,${Buffer.from(stripTypeScriptTypes(source)).toString('base64')}`
);

const defaults = {
  search: '', sector: '', grade: '', maxPay: '', minUpside: '',
  sort: 'ticker', order: 'asc', limit: 50, offset: 0,
};
const query = (entries) => new URLSearchParams(entries).toString();

test('defaults are explicit, empty queries restore them, and serialization omits them', () => {
  assert.deepEqual(DEFAULT_SCREENER_STATE, defaults);
  for (const input of ['', '?', 'unknown=value']) {
    assert.deepEqual(parseScreenerUrl(input), defaults);
  }
  assert.equal(serializeScreenerUrl({ ...defaults }), '');
  assert.deepEqual(parseScreenerUrl('sort=ticker&order=asc&limit=50&offset=0'), defaults);
});

test('all fields roundtrip with encoded company names and sectors', () => {
  const state = {
    search: 'AT&T + Société / 日本? #1', sector: 'Energy & Oil + Gas/Utilities',
    grade: 'B', maxPay: '-12.5', minUpside: '0',
    sort: 'upside_pct', order: 'desc', limit: 100, offset: 125,
  };
  const serialized = serializeScreenerUrl(state);
  assert.equal(serialized.startsWith('?'), false);
  assert.deepEqual(Object.fromEntries(new URLSearchParams(serialized)), {
    search: state.search, sector: state.sector, grade: 'B',
    max_pay_efficiency_pct: '-12.5', min_upside_pct: '0',
    sort: 'upside_pct', order: 'desc', limit: '100', offset: '125',
  });
  assert.deepEqual(parseScreenerUrl(serialized), state);
  assert.deepEqual(parseScreenerUrl(`?${serialized}`), state);
});

test('search and sector are decoded, trimmed, and limited to 100 characters', () => {
  assert.deepEqual(parseScreenerUrl('search=++Acme%2BCo+%26+Sons++&sector=+Oil%2FGas+'), {
    ...defaults, search: 'Acme+Co & Sons', sector: 'Oil/Gas',
  });
  const parsed = parseScreenerUrl(query({ search: `  ${'s'.repeat(101)}  `, sector: `\t${'x'.repeat(120)}\n` }));
  assert.equal(parsed.search, 's'.repeat(100));
  assert.equal(parsed.sector, 'x'.repeat(100));
  assert.deepEqual(parseScreenerUrl(query({ search: ' \t\n ', sector: '   ' })), defaults);
});

for (const [key, field] of [['max_pay_efficiency_pct', 'maxPay'], ['min_upside_pct', 'minUpside']]) {
  test(`${key} accepts complete finite numbers and canonicalizes signed thresholds`, () => {
    for (const [input, expected] of [
      ['0', '0'], ['-0', '0'], ['+0', '0'], ['-12.50', '-12.5'],
      ['+2.50', '2.5'], ['.5', '0.5'], ['1e2', '100'], ['-1e-2', '-0.01'],
    ]) {
      const state = parseScreenerUrl(query({ [key]: input }));
      assert.deepEqual(state, { ...defaults, [field]: expected }, input);
      assert.equal(new URLSearchParams(serializeScreenerUrl(state)).get(key), expected);
      assert.deepEqual(parseScreenerUrl(serializeScreenerUrl(state)), state);
    }
  });

  test(`${key} rejects blank, whitespace, partial, and nonfinite numeric values`, () => {
    for (const input of ['', ' ', '\t', ' 2', '2 ', '1 2', '12abc', '2%', '1.2.3', '--1', '+', 'NaN', 'Infinity', '-Infinity', '1e309']) {
      assert.deepEqual(parseScreenerUrl(query({ [key]: input })), defaults, JSON.stringify(input));
    }
  });
}

test('only documented grade, sort, and order enums are accepted', () => {
  for (const grade of ['A', 'B', 'C', 'D', 'F']) {
    assert.deepEqual(parseScreenerUrl(query({ grade })), { ...defaults, grade });
  }
  for (const sort of ['ticker', 'name', 'sector', 'pay_efficiency_pct', 'grade_score', 'upside_pct']) {
    for (const order of ['asc', 'desc']) {
      const state = { ...defaults, sort, order };
      assert.deepEqual(parseScreenerUrl(query({ sort, order })), state);
      assert.deepEqual(parseScreenerUrl(serializeScreenerUrl(state)), state);
    }
  }
  for (const grade of ['E', 'a', ' A ', 'AA', '0']) {
    assert.deepEqual(parseScreenerUrl(query({ grade })), defaults);
  }
  for (const sort of ['NAME', 'pay', 'grade', ' name ', 'constructor']) {
    assert.deepEqual(parseScreenerUrl(query({ sort })), defaults);
  }
  for (const order of ['ASC', 'descending', ' desc ', '0']) {
    assert.deepEqual(parseScreenerUrl(query({ order })), defaults);
  }
});

test('limit accepts exactly the supported page sizes', () => {
  for (const limit of [25, 50, 100, 200]) {
    const state = { ...defaults, limit };
    assert.deepEqual(parseScreenerUrl(`limit=${limit}`), state);
    assert.deepEqual(parseScreenerUrl(serializeScreenerUrl(state)), state);
  }
  for (const limit of ['', '0', '-25', '10', '26', '201', '25.5', '25abc', 'Infinity', 'NaN']) {
    assert.deepEqual(parseScreenerUrl(query({ limit })), defaults, limit);
  }
});

test('offset accepts inclusive bounds and integers independent of page size', () => {
  for (const offset of [0, 1, 49, 50, 999999, 1000000]) {
    const state = { ...defaults, offset };
    assert.deepEqual(parseScreenerUrl(`offset=${offset}`), state);
    assert.deepEqual(parseScreenerUrl(serializeScreenerUrl(state)), state);
  }
  for (const offset of ['-1', '1000001', '1.5', '50abc', 'NaN', 'Infinity', '9007199254740992']) {
    assert.deepEqual(parseScreenerUrl(query({ offset })), defaults, offset);
  }
});

test('serialization omits each default while retaining nondefault filters', () => {
  const serialized = serializeScreenerUrl({ ...defaults, search: 'Acme', maxPay: '0', minUpside: '-3' });
  assert.deepEqual(Object.fromEntries(new URLSearchParams(serialized)), {
    search: 'Acme', max_pay_efficiency_pct: '0', min_upside_pct: '-3',
  });
});

test('duplicates use the first value for every documented parameter', () => {
  const first = {
    search: 'First & Co', sector: 'Oil/Gas', grade: 'D',
    maxPay: '0', minUpside: '-5', sort: 'name', order: 'desc', limit: 25, offset: 1,
  };
  const entries = [
    ['search', first.search, 'Second'], ['sector', first.sector, 'Other'], ['grade', 'D', 'A'],
    ['max_pay_efficiency_pct', '0', '99'], ['min_upside_pct', '-5', '20'],
    ['sort', 'name', 'ticker'], ['order', 'desc', 'asc'], ['limit', '25', '200'], ['offset', '1', '100'],
  ].flatMap(([key, a, b]) => [[key, a], [key, b]]);
  assert.deepEqual(parseScreenerUrl(query(entries)), first);
});

test('an invalid or empty first duplicate cannot be rescued by a later value', () => {
  const entries = [
    ['search', '', 'Acme'], ['sector', '', 'Energy'], ['grade', 'E', 'A'],
    ['max_pay_efficiency_pct', 'bad', '0'], ['min_upside_pct', 'Infinity', '5'],
    ['sort', 'unknown', 'name'], ['order', 'up', 'desc'], ['limit', '1', '200'], ['offset', '-1', '50'],
  ].flatMap(([key, a, b]) => [[key, a], [key, b]]);
  assert.deepEqual(parseScreenerUrl(query(entries)), defaults);
});
