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
    write(disk, 'AAA/insiders.json', {'buys': {'count': 0, 'value': 0}, 'sells': {'count': 0, 'value': 0}})
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


@pytest.mark.parametrize('kind,record,part', [
    ('red_flags', {'flags': [{'severity': []}]}, 'red_flags'),
    ('red_flags', {'flags': [{'severity': {}}]}, 'red_flags'),
    ('red_flags', {'flags': [None]}, 'red_flags'),
    ('red_flags', {'flags': {}}, 'red_flags'),
    ('governance', {'metrics': []}, 'governance'),
    ('governance', {'metrics': {'Board Independence': ['bad']}}, 'governance'),
    ('governance', {'metrics': {'Say-on-Pay Support': {'pct': []}}}, 'governance'),
    ('governance', {'metrics': {'CEO Pay Ratio': {'value': {}}}}, 'governance'),
    ('insiders', {'buys': [], 'sells': {}}, 'insiders'),
    ('insiders', {'buys': {}, 'sells': {}, 'planned_sells': [1]}, 'insiders'),
    ('insiders', {'buys': {'value': []}, 'sells': {}}, 'insiders'),
    ('insiders', {'buys': {}, 'sells': {}, 'cluster': ['bad']}, 'insiders'),
])
def test_malformed_nested_inputs_are_excluded_before_grading(disk, monkeypatch, kind, record, part):
    seed(disk)
    write(disk, f'AAA/{kind}.json', record)
    write(disk, 'BBB/red_flags.json', {'flags': []})
    write(disk, 'BBB/insiders.json', {'buys': {'count': 0, 'value': 0}, 'sells': {'count': 0, 'value': 0}})
    original = screener.grade.build

    def checked(ticker, name, parts, errors):
        if ticker == 'AAA':
            assert part not in parts
            assert part in errors
        return original(ticker, name, parts, errors)

    monkeypatch.setattr(screener.grade, 'build', checked)
    result = screener.screen()
    rows = {row['ticker']: row for row in result['rows']}
    assert result['available'] is True and result['total'] == 3
    assert rows['AAA']['pay_efficiency_pct'] == 2
    assert rows['AAA']['grade'] is None and rows['AAA']['grade_score'] is None
    assert any(f'grade.{part}:' in reason for reason in rows['AAA']['missing'])
    assert rows['BBB']['grade'] is not None
    assert rows['BBB']['pay_efficiency_pct'] == -1
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('metrics', [[], {'Board Independence': []},
                                     {'Board Independence': {'p25': [], 'median': 50, 'p75': 75}}])
def test_malformed_benchmark_containers_do_not_reach_grade_helpers(disk, monkeypatch, metrics):
    seed(disk)
    write(disk, 'AAA/governance.json', {'metrics': {'Board Independence': {'pct': 70}}})
    write(disk, 'benchmarks.json', {'all': {'metrics': metrics}})
    monkeypatch.setattr(screener.grade, 'governance_part',
                        lambda *args: pytest.fail('Malformed benchmark reached grade helper'))
    result = screener.screen()
    assert result['available'] is True
    assert result['coverage']['pay_efficiency_pct'] == 2
    assert any('grade.governance:' in reason for reason in result['rows'][0]['missing'])


def test_row_failure_uses_complete_fallback_without_retrying_inputs(disk, monkeypatch):
    seed(disk)
    original = screener._row
    calls = []

    def failing(root, ticker, *args):
        calls.append(ticker)
        if ticker == 'AAA':
            raise TypeError('Malformed nested cached input')
        return original(root, ticker, *args)

    monkeypatch.setattr(screener, '_row', failing)
    result = screener.screen()
    assert result['available'] is True and result['total'] == result['matched'] == 3
    assert calls == ['AAA', 'BBB', 'CCC']
    row, valid = result['rows'][:2]
    assert row['ticker'] == 'AAA'
    assert set(row) == set(valid)
    assert all(value is None for key, value in row.items() if key not in ('ticker', 'sources', 'missing'))
    assert row['sources'] == dict.fromkeys(valid['sources'])
    for field in (key for key in row if key not in ('ticker', 'sources', 'missing')):
        assert any(reason.startswith(field + ':') for reason in row['missing'])
    for field in row['sources']:
        assert any(reason.startswith(f'sources.{field}:') for reason in row['missing'])
    assert valid['pay_efficiency_pct'] == -1
    assert result['coverage'] == {'pay_efficiency_pct': 1, 'grade': 0, 'upside_pct': 0}
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('pct', [[], {}, True, '2'])
def test_malformed_pay_value_does_not_discard_valid_grade_parts(disk, monkeypatch, pct):
    seed(disk)
    write(disk, 'AAA/pay_efficiency.json', {'available': True, 'denominator': 'operating', 'pct': pct})
    write(disk, 'AAA/governance.json', {'metrics': {}})
    write(disk, 'AAA/red_flags.json', {'flags': []})
    write(disk, 'AAA/insiders.json', {'buys': {'count': 0, 'value': 0}, 'sells': {'count': 0, 'value': 0}})
    monkeypatch.setattr(screener.grade, 'governance_part',
                        lambda *args: pytest.fail('Malformed pay value reached governance helper'))
    result = screener.screen()
    row = result['rows'][0]
    assert result['available'] is True and result['total'] == 3
    assert row['pay_efficiency_pct'] is None
    assert row['grade'] is not None and row['grade_score'] is not None
    assert any('pay_efficiency_pct:' in reason for reason in row['missing'])
    assert any('grade.governance:' in reason for reason in row['missing'])
    assert result['rows'][1]['pay_efficiency_pct'] == -1
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('side', ['buys', 'sells', 'planned_sells'])
@pytest.mark.parametrize('bad', [{}, None, {'count': 0}, {'value': 0},
                                  {'count': None, 'value': 0}, {'count': 0, 'value': None},
                                  {'count': True, 'value': 0}, {'count': 0, 'value': '0'},
                                  {'count': 0, 'value': float('inf')}])
def test_incomplete_insider_totals_are_not_graded(disk, side, bad):
    seed(disk)
    write(disk, 'AAA/red_flags.json', {'flags': []})
    ins = {'buys': {'count': 0, 'value': 0}, 'sells': {'count': 0, 'value': 0}}
    ins[side] = bad
    write(disk, 'AAA/insiders.json', ins)
    row = screener.screen(search='AAA')['rows'][0]
    assert row['grade'] is None
    assert any(reason.startswith('grade.insiders:') for reason in row['missing'])


@pytest.mark.parametrize('planned', [False, True])
def test_zero_insider_totals_are_valid_with_optional_planned_sells(disk, planned):
    seed(disk)
    write(disk, 'AAA/red_flags.json', {'flags': []})
    ins = {'buys': {'count': 0, 'value': 0}, 'sells': {'count': 0, 'value': 0}}
    if planned:
        ins['planned_sells'] = {'count': 0, 'value': 0}
    write(disk, 'AAA/insiders.json', ins)
    row = screener.screen(search='AAA')['rows'][0]
    assert row['grade_score'] == 85
    assert any('grade.insiders:' in reason and 'cannot be evaluated' in reason
               for reason in row['missing'])


@pytest.mark.parametrize('market_cap,expected_score', [(1000, 20), (None, 50), (0, 50),
                                                       (-1000, 50), (True, 50),
                                                       (float('inf'), 50)])
def test_insider_market_cap_independent_of_unavailable_valuation(disk, monkeypatch, market_cap, expected_score):
    seed(disk)
    write(disk, 'AAA/red_flags.json', {'flags': []})
    write(disk, 'AAA/insiders.json', {
        'buys': {'count': 0, 'value': 0}, 'sells': {'count': 1, 'value': 30}})
    monkeypatch.setattr(screener.valuation, 'value',
                        lambda *args: {'available': False, 'reason': 'No usable peers.'})
    target = {'market_cap': market_cap, 'sane': True, 'debt': 0}
    row = screener._row(disk, 'AAA', {'rows': []}, {'AAA': target}, None)
    assert row['upside_pct'] is None
    assert row['grade_score'] == (35 * 100 + 15 * expected_score) / 50
    warnings = [reason for reason in row['missing'] if reason.startswith('grade.insiders:')]
    assert bool(warnings) == (expected_score == 50)
    if warnings:
        assert 'cannot be evaluated' in warnings[0]


@pytest.mark.parametrize('sane,debt', [(False, None), (False, 0), (True, None), (True, 0)])
def test_valuation_caveats_preserve_estimate(disk, monkeypatch, sane, debt):
    seed(disk)
    write(disk, 'AAA/red_flags.json', {'flags': []})
    monkeypatch.setattr(screener.valuation, 'value', lambda *args: {
        'available': True, 'upside_pct': 12, 'confidence': 'low'})
    # Isolate projection of valuation notes from the grade helper's additional inputs.
    monkeypatch.setattr(screener.grade, 'build', lambda *args: {'available': False})
    target = {'market_cap': 1000, 'sane': sane, 'debt': debt}
    row = screener._row(disk, 'AAA', {'rows': []}, {'AAA': target}, None)
    assert row['upside_pct'] == 12
    reasons = [reason for reason in row['missing'] if reason.startswith('upside_pct:')]
    assert any('Treat this estimate with care.' in reason for reason in reasons) == (not sane)
    assert any('No debt is tagged in the 10-K, so debt is counted as zero.' in reason
               for reason in reasons) == (debt is None)
    assert len(reasons) == int(not sane) + int(debt is None)
