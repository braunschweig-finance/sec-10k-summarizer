import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import test from 'node:test';
const code=stripTypeScriptTypes(readFileSync(new URL('./localComparison.ts',import.meta.url),'utf8'));
const {localComparison}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const a=Object.freeze({ticker:'A',pay_efficiency_pct:-1,sources:{financials_url:'filing-a'},missing:['a note']});
const b=Object.freeze({ticker:'B',pay_efficiency_pct:0,sources:{financials_url:'filing-b'},missing:[]});
const snapshot=()=>({available:true,built_at:null,total:3,matched:1,limit:25,offset:0,rows:[a],coverage:{grade:3},warnings:['cached'],comparison:{tickers:['B','ZZZ'],rows:[b],missing:['ZZZ']}});
test('reuses only one response, preserving requested order and exact row objects',()=>{
 const input=snapshot(); const result=localComparison(input,['B','A']);
 assert.deepEqual(result.comparison.tickers,['B','A']);
 assert.equal(result.comparison.rows[0],b); assert.equal(result.comparison.rows[1],a);
 assert.equal(result.rows,input.rows); assert.equal(result.built_at,null); assert.equal(result.coverage,input.coverage);
 assert.equal(input.comparison.rows.length,1);
});
test('keeps confirmed missing symbols but never invents a missing result for an unloaded symbol',()=>{
 assert.deepEqual(localComparison(snapshot(),['A','ZZZ']).comparison.missing,['ZZZ']);
 assert.equal(localComparison(snapshot(),['A','UNLOADED']),null);
});
test('clear removes only comparison state and does not mutate the response',()=>{
 const input=snapshot(); const result=localComparison(input,[]);
 assert.equal(result.comparison,undefined); assert.ok(input.comparison);
 assert.equal(result.rows,input.rows); assert.equal(result.offset,input.offset);
});
test('rejects unavailable, duplicate, blank and over-limit selections',()=>{
 assert.equal(localComparison({...snapshot(),available:false},['A']),null);
 for(const ids of [['A','A'],[''],['A','B','C','D','E']]) assert.equal(localComparison(snapshot(),ids),null);
});
