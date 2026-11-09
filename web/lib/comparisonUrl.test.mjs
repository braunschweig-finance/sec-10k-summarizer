import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import test from 'node:test';

const source = await readFile(new URL('./comparisonUrl.ts', import.meta.url), 'utf8');
const { parseComparisonUrl, writeComparisonParams } = await import(
  `data:text/javascript;base64,${Buffer.from(stripTypeScriptTypes(source)).toString('base64')}`
);
const query = (compare, comparison = '1') => new URLSearchParams({ compare, comparison }).toString();

test('normalizes safe tickers including dots, hyphens, digits and 15 characters', () => {
  assert.deepEqual(parseComparisonUrl(query(' brk.b, brk-b, 0123456789abcde, a1 ')), {
    tickers: ['BRK.B', 'BRK-B', '0123456789ABCDE', 'A1'], open: true,
  });
});

test('drops blanks, malformed and duplicate tickers before taking four valid values', () => {
  assert.deepEqual(parseComparisonUrl(query(' ,cat,CAT, aapl,,bad/name,-BAD,.BAD,A_B,ABCDEFGHIJKLMNOP,msft,goog,tsla')), {
    tickers: ['CAT', 'AAPL', 'MSFT', 'GOOG'], open: true,
  });
  for (const raw of ['', ' , , ', 'bad/name,\u0000,é,ＡAPL,<script>,A B']) {
    assert.deepEqual(parseComparisonUrl(query(raw)), { tickers: [], open: false });
  }
});

test('rejects raw compare over 128 characters before normalization', () => {
  assert.deepEqual(parseComparisonUrl(query(`CAT,AAPL${' '.repeat(120)}`)), {
    tickers: ['CAT', 'AAPL'], open: true,
  });
  assert.deepEqual(parseComparisonUrl(query(`CAT,AAPL${' '.repeat(121)}`)), { tickers: [], open: false });
});

test('first compare and comparison values win, even when empty or invalid', () => {
  assert.deepEqual(parseComparisonUrl('?compare=cat,aapl&compare=msft&comparison=1&comparison=0'), {
    tickers: ['CAT', 'AAPL'], open: true,
  });
  for (const first of ['', 'bad/name', 'X'.repeat(129)]) {
    assert.deepEqual(parseComparisonUrl(`${query(first)}&compare=CAT,AAPL`), { tickers: [], open: false });
  }
  for (const flag of ['', '0', 'true', '01', ' 1 ', '1\n']) {
    assert.equal(parseComparisonUrl(`${query('CAT,AAPL', flag)}&comparison=1`).open, false);
  }
});

test('opens only with exact flag and at least two unique valid tickers', () => {
  for (const raw of ['', 'cat', 'cat,CAT', 'CAT,bad/name']) {
    assert.equal(parseComparisonUrl(query(raw)).open, false);
  }
  assert.equal(parseComparisonUrl('compare=CAT,AAPL').open, false);
  assert.equal(parseComparisonUrl(query('CAT,AAPL')).open, true);
});

test('ignores unrelated parameters and fragments without treating them as query state', () => {
  assert.deepEqual(parseComparisonUrl('?search=CAT&sector=AAPL#compare=CAT,AAPL&comparison=1'), {
    tickers: [], open: false,
  });
  assert.deepEqual(parseComparisonUrl('?compare=CAT,AAPL&comparison=1#compare=MSFT&comparison=0'), {
    tickers: ['CAT', 'AAPL'], open: true,
  });
  assert.deepEqual(parseComparisonUrl(query('CAT,AAPL#MSFT')), { tickers: ['CAT'], open: false });
});

test('writer replaces owned duplicates and preserves unrelated duplicates without mutation', () => {
  const params = new URLSearchParams('sector=Energy&compare=OLD&tag=a&comparison=0&tag=b&compare=OTHER&comparison=1&note=%23hash');
  const original = params.toString();
  const tickers = Object.freeze([' cat ', 'CAT', '', 'bad/name', 'brk.b', 'brk-b', 'AAPL', 'MSFT']);
  const result = writeComparisonParams(params, tickers, true);
  assert.notEqual(result, params);
  assert.equal(params.toString(), original);
  assert.deepEqual([...result], [
    ['sector', 'Energy'], ['tag', 'a'], ['tag', 'b'], ['note', '#hash'],
    ['compare', 'CAT,BRK.B,BRK-B,AAPL'], ['comparison', '1'],
  ]);
  assert.equal(tickers[0], ' cat ');
  result.set('sector', 'Changed');
  assert.equal(params.toString(), original);
});

test('writer removes stale owned parameters for empty, single, and closed selections', () => {
  for (const [tickers, open, expected] of [
    [[], true, []], [[' ', 'bad/name'], true, []],
    [['cat', 'CAT'], true, [['compare', 'CAT']]],
    [['cat', 'aapl'], false, [['compare', 'CAT,AAPL']]],
  ]) {
    const result = writeComparisonParams(new URLSearchParams('compare=OLD&comparison=1&comparison=1'), tickers, open);
    assert.deepEqual([...result], expected);
  }
});

test('normalized state roundtrips and writing it again is stable', () => {
  for (const tickers of [[], ['CAT'], ['brk.b', 'BRK-B'], [' cat ', '', 'bad/name', 'CAT', 'aapl', 'msft', 'goog', 'tsla']]) {
    for (const open of [false, true]) {
      const params = new URLSearchParams('tag=one&tag=two&search=a%26b%23c');
      const written = writeComparisonParams(params, tickers, open);
      const parsed = parseComparisonUrl(`?${written}#ignored`);
      assert.deepEqual(parsed.tickers, (written.get('compare') ?? '').split(',').filter(Boolean));
      assert.equal(parsed.open, open && parsed.tickers.length >= 2);
      assert.equal(writeComparisonParams(written, parsed.tickers, parsed.open).toString(), written.toString());
    }
  }
});
