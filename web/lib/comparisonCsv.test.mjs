import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import test from 'node:test';
const code=stripTypeScriptTypes(readFileSync(new URL('./comparisonCsv.ts',import.meta.url),'utf8'));
const {comparisonCsv}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const company=(ticker,changes={})=>({ticker,name:ticker,sector:'Industrials',fy_end:'2025-12-31',
  pay_efficiency_pct:1.18,grade:'B',grade_score:75,upside_pct:-12.345,price_date:'2026-11-09',
  valuation_confidence:'low',sources:{financials_url:'https://sec.gov/tenk',proxy_url:'https://sec.gov/proxy',valuation_source:'SEC and cached quotes'},missing:[],...changes});
test('exports exact selected order, numeric precision, units, dates and sources',()=>{
  const text=comparisonCsv([company('CAT'),company('AAPL')],'2026-11-09T12:00:00Z');
  assert.ok(text.startsWith('\uFEFF"Ticker"')); assert.ok(text.endsWith('\r\n'));
  const [header,first,second]=text.slice(1).split('\r\n');
  assert.ok(first.startsWith('"CAT","CAT"')); assert.ok(second.startsWith('"AAPL","AAPL"'));
  assert.ok(header.includes('"Pay Efficiency (% of operating income)"'));
  assert.ok(first.includes('"1.18","B","75","-12.345","low"'));
  assert.ok(first.includes('"2026-11-09","2026-11-09T12:00:00Z","https://sec.gov/tenk","https://sec.gov/proxy"'));
  assert.ok(first.includes('1.18 means 1.18%'));
});
test('keeps missing values blank, legitimate zero numeric, and missing reasons intact',()=>{
  const text=comparisonCsv([company('CAT',{pay_efficiency_pct:null,grade:null,grade_score:null,upside_pct:0,missing:['pay_efficiency_pct: No tagged compensation.']}),company('AAPL',{pay_efficiency_pct:0})],null);
  assert.ok(text.includes('"","","","0","low"'));
  assert.ok(text.includes('"0","B","75"'));
  assert.ok(text.includes('pay_efficiency_pct: No tagged compensation.'));
  assert.ok(!text.includes('"null"'));
});
test('escapes commas, quotes, line breaks and Unicode while retaining every note',()=>{
  const text=comparisonCsv([company('CAT',{name:'Research, "Tools"\r\nÉnergie',missing:['first note','second "note", with comma']}),company('AAPL')],null);
  assert.ok(text.includes('"Research, ""Tools""\r\nÉnergie"'));
  assert.ok(text.includes('"first note\nsecond ""note"", with comma"'));
});
test('neutralizes formula-like text in all fields but preserves negative numbers',()=>{
  for(const dangerous of ['=SUM(1,2)','+CMD','-CMD','@SUM(A1)','  =1','\tformula','\rtext','\ntext','\u0001=1']) {
    const row=company(dangerous,{name:dangerous,sector:dangerous,fy_end:dangerous,grade:dangerous,valuation_confidence:dangerous,price_date:dangerous,missing:[dangerous],sources:{financials_url:dangerous,proxy_url:dangerous,valuation_source:dangerous}});
    const text=comparisonCsv([row,company('AAPL')],dangerous);
    const escaped='"\''+dangerous.replaceAll('"','""')+'"';
    assert.equal(text.split(escaped).length-1,13,dangerous);
    assert.ok(!text.includes('"\'-12.345"'));
  }
});
test('rejects incomplete, excessive, blank and duplicate selections',()=>{
  for(const rows of [[],[company('CAT')],['A','B','C','D','E'].map(t=>company(t)),[company('CAT'),company(' cat ')],[company('CAT'),company(' ')]])
    assert.throws(()=>comparisonCsv(rows,null),/two to four distinct/);
  assert.doesNotThrow(()=>comparisonCsv(['A','B','C','D'].map(t=>company(t)),null));
});
