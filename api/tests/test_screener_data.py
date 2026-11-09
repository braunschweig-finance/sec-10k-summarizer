"""Focused, offline checks for disk snapshots and screener selection."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import screener
import valuation


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


@pytest.fixture
def disk(tmp_path, monkeypatch):
    monkeypatch.setattr(screener.prebuilt, 'DIR', str(tmp_path))
    screener.invalidate()
    # Any accidental external access fails immediately.
    import httpx
    monkeypatch.setattr(httpx, 'get', lambda *a, **k: pytest.fail('External HTTP forbidden'))
    monkeypatch.setattr(httpx, 'stream', lambda *a, **k: pytest.fail('External HTTP forbidden'))
    yield tmp_path
    screener.invalidate()


def seed(root):
    write(root, 'manifest.json', {'built_at': '2026-10-31T12:00:00Z', 'tickers': ['CCC', 'BBB', 'AAA']})
    for ticker, pct in [('AAA', 2), ('BBB', -1), ('CCC', None)]:
        write(root, f'{ticker}/company.json', {'name': ticker + ' Company', 'sic': '3500', 'tenk_url': 'https://sec.gov/filing'})
        write(root, f'{ticker}/pay_efficiency.json', {'available': True, 'pct': pct, 'denominator': 'operating', 'fy_end': '2025-12-31'})


def test_missing_and_corrupt_manifest(disk):
    result = screener.screen()
    assert result['available'] is False
    assert result['total'] == result['matched'] == 0
    assert result['built_at'] is None and result['warnings']
    (disk / 'manifest.json').write_text('not json')
    assert screener.screen()['rows'] == []


def test_filters_coverage_and_null_last(disk):
    seed(disk)
    result = screener.screen(sort='pay_efficiency_pct', order='desc', limit=1, offset=1)
    assert result['built_at'] == '2026-10-31T12:00:00Z'
    assert result['total'] == result['matched'] == 3
    assert result['coverage'] == {'pay_efficiency_pct': 2, 'grade': 0, 'upside_pct': 0}
    assert result['rows'][0]['ticker'] == 'BBB'
    for order in ('asc', 'desc'):
        assert screener.screen(sort='pay_efficiency_pct', order=order)['rows'][-1]['ticker'] == 'CCC'
    assert screener.screen(max_pay_efficiency_pct=0)['rows'][0]['pay_efficiency_pct'] == -1
    assert screener.screen(min_upside_pct=0)['matched'] == 0
    assert screener.screen(search='company', sector='Industrials')['matched'] == 3
    assert screener.screen(search='bb')['matched'] == 1
    assert screener.screen(grade='A')['matched'] == 0
    assert screener.screen(offset=100)['rows'] == []
    assert any('not superior' in m for m in screener.screen(search='BBB')['rows'][0]['missing'])


def test_sentinels_nonfinite_and_wrong_denominator(disk):
    seed(disk)
    write(disk, 'AAA/pay_efficiency.json', {'available': True, 'pct': float('nan'), 'denominator': 'operating'})
    write(disk, 'BBB/pay_efficiency.json', {'available': True, 'pct': 1, 'denominator': 'pretax'})
    write(disk, 'CCC/red_flags.json', {'__unavailable__': 'No data'})
    result = screener.screen()
    assert result['coverage']['pay_efficiency_pct'] == 0
    assert all(r['grade'] is None and r['missing'] for r in result['rows'])
    json.dumps(result, allow_nan=False)


def test_manifest_paths_are_validated_before_access(disk, monkeypatch):
    write(disk, 'manifest.json', {'tickers': ['../../outside', 'AAA', '/absolute', 'A/B', 'aaa', None]})
    reads = []
    original = screener._read
    def watched(path):
        reads.append(path)
        assert path.is_relative_to(disk)
        assert '..' not in path.parts
        return original(path)
    monkeypatch.setattr(screener, '_read', watched)
    result = screener.screen()
    assert [r['ticker'] for r in result['rows']] == ['AAA']
    assert result['warnings']


def test_cache_file_changes_refresh_and_defensive_copy(disk, monkeypatch):
    seed(disk)
    calls = []
    original = screener._row
    def counted(*args):
        calls.append(args[1])
        return original(*args)
    monkeypatch.setattr(screener, '_row', counted)
    first = screener.screen()
    first['rows'][0]['missing'].append('mutated')
    assert 'mutated' not in screener.screen(search='AAA')['rows'][0]['missing']
    assert len(calls) == 3
    write(disk, 'AAA/pay_efficiency.json', {'available': True, 'pct': 10, 'denominator': 'operating'})
    assert screener.screen(search='AAA')['rows'][0]['pay_efficiency_pct'] == 10
    assert len(calls) == 6
    screener.invalidate()
    screener.screen()
    assert len(calls) == 9


@pytest.mark.parametrize('kwargs', [{'max_pay_efficiency_pct': float('nan')}, {'min_upside_pct': float('inf')},
    {'sort': 'bad'}, {'order': 'bad'}, {'grade': 'E'}, {'limit': 201}, {'limit': 0}, {'offset': -1}])
def test_invalid_queries(disk, kwargs):
    with pytest.raises(ValueError):
        screener.screen(**kwargs)


def test_pure_valuation_and_grade_reuse(disk):
    seed(disk)
    rows = []
    for i, ticker in enumerate(['AAA', 'BBB', 'CCC', 'DDD']):
        fund = {'ticker': ticker, 'name': ticker, 'sic': '3500', 'cik': str(i), 'years': [
            {'fy_end': '2025-12-31', 'filed': '2026-02-01', 'values': {k: {'value': v} for k, v in {
                'Revenue': 1000, 'Operating Income': 100, 'Net Income': 70, 'Depreciation & Amortization': 20,
                'Diluted Shares': 10, 'Shareholders\' Equity': 500, 'Total Assets': 1000,
                'Total Liabilities': 500, 'Long-term Debt (total)': 100, 'Cash': 50}.items()}}]}
        rows.append(valuation.build_row(fund, 20 + i, '2026-10-30'))
    write(disk, 'valuation.json', {'rows': rows, 'source': 'fixture cached filing and price source'})
    write(disk, 'AAA/red_flags.json', {'flags': []})
    write(disk, 'AAA/insiders.json', {'buys': {}, 'sells': {}})
    result = screener.screen(search='AAA')['rows'][0]
    expected = valuation.value(rows[0], rows)
    assert result['upside_pct'] == pytest.approx(expected['upside_pct'])
    assert result['valuation_confidence'] == expected['confidence']
    assert result['price_date'] == '2026-10-30'
    assert result['sources']['valuation_source'] == 'fixture cached filing and price source'
    assert result['grade'] is not None
    json.dumps(result, allow_nan=False)


def test_ties_use_ticker_ascending_in_both_directions(disk):
    seed(disk)
    write(disk, 'BBB/pay_efficiency.json', {'available': True, 'pct': 2, 'denominator': 'operating'})
    for order in ('asc', 'desc'):
        assert [r['ticker'] for r in screener.screen(sort='pay_efficiency_pct', order=order)['rows']] == ['AAA', 'BBB', 'CCC']


def test_empty_objects_do_not_create_healthy_grade(disk):
    seed(disk)
    for kind in ('governance', 'red_flags', 'insiders'):
        write(disk, f'AAA/{kind}.json', {})
    row = screener.screen(search='AAA')['rows'][0]
    assert row['grade'] is None and row['grade_score'] is None


def test_manifest_bound(disk, monkeypatch):
    monkeypatch.setattr(screener, 'MAX_COMPANIES', 2)
    seed(disk)
    assert screener.screen()['available'] is False
