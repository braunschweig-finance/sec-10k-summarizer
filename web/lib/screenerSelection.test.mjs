import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import test from 'node:test';
const code=stripTypeScriptTypes(readFileSync(new URL('./screenerSelection.ts',import.meta.url),'utf8'));
const {toggleSelection,canCompare,sameSelectionSnapshot}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const rows=['CAT','AAPL','MSFT','JNJ','XOM'].map(ticker=>Object.freeze({ticker}));
test('dated responses share a snapshot only when build dates match',()=>{
  assert.equal(sameSelectionSnapshot({builtAt:'2026-11-09',source:{}},{built_at:'2026-11-09'}),true);
  assert.equal(sameSelectionSnapshot({builtAt:'2026-11-08',source:{}},{built_at:'2026-11-09'}),false);
  assert.equal(sameSelectionSnapshot({builtAt:'2026-11-09',source:{}},{built_at:null}),false);
});
test('undated responses must be the same object, never mixed across fetches',()=>{
  const source={built_at:null};
  assert.equal(sameSelectionSnapshot({builtAt:null,source},source),true);
  assert.equal(sameSelectionSnapshot({builtAt:null,source},{built_at:null}),false);
  assert.equal(sameSelectionSnapshot({builtAt:null,source},{built_at:'2026-11-09'}),false);
});
test('requires two to four distinct companies',()=>{
  for(let n=0;n<=5;n++) assert.equal(canCompare(rows.slice(0,n)),n>=2&&n<=4);
});
test('rejects blank or duplicate identities for comparison',()=>{
  assert.equal(canCompare([{ticker:'CAT'},{ticker:' cat '}]),false);
  assert.equal(canCompare([{ticker:'CAT'},{ticker:' '}]),false);
});
test('cap prevents a fifth selection but permits removal at the cap',()=>{
  const four=Object.freeze(rows.slice(0,4));
  assert.deepEqual(toggleSelection(four,rows[4]),four);
  assert.deepEqual(toggleSelection(four,rows[1]),[rows[0],rows[2],rows[3]]);
});
test('selection survives immutable updates and preserves row references/order',()=>{
  const initial=Object.freeze([rows[0]]);
  const added=toggleSelection(initial,rows[1]);
  assert.deepEqual(initial,[rows[0]]);
  assert.equal(added[0],rows[0]); assert.equal(added[1],rows[1]);
  assert.deepEqual(toggleSelection(toggleSelection(added,rows[0]),rows[0]),[rows[1],rows[0]]);
});
test('normalizes existing duplicates and blanks; ticker identity ignores case/space',()=>{
  assert.deepEqual(toggleSelection([{ticker:' '},rows[0],{ticker:'cat'},rows[1]],{ticker:' msft '}),[rows[0],rows[1],{ticker:' msft '}]);
  assert.deepEqual(toggleSelection([rows[0],rows[1]],{ticker:' cat '}),[rows[1]]);
  assert.deepEqual(toggleSelection([rows[0]],{ticker:''}),[rows[0]]);
  assert.deepEqual(toggleSelection([],rows[0]),[rows[0]]);
});
