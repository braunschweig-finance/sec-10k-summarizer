"""Disk-only company screener. No live lookup functions are used here."""
import copy
import json
import math
import re
import threading
from pathlib import Path

import grade
import prebuilt
import sectors
import valuation

MAX_COMPANIES = 3000
MAX_FILE_BYTES = 32 * 1024 * 1024
KINDS = ('company', 'governance', 'pay_efficiency', 'red_flags', 'insiders', 'fundamentals')
SORTS = {'ticker', 'name', 'sector', 'pay_efficiency_pct', 'grade_score', 'upside_pct'}
_TICKER = re.compile(r'[A-Z0-9][A-Z0-9.-]{0,14}\Z')
_lock = threading.RLock()
_cache = None


def invalidate():
    global _cache
    with _lock:
        _cache = None


prebuilt._on_refresh.append(invalidate)


def _finite_tree(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite_tree(v) for v in value.values())
    if isinstance(value, list):
        return all(_finite_tree(v) for v in value)
    return True


def _read(path):
    try:
        if path.stat().st_size > MAX_FILE_BYTES or path.is_symlink():
            return None
        with path.open(encoding='utf-8') as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or '__unavailable__' in data or not _finite_tree(data):
            return None
        return data
    except (OSError, ValueError, RecursionError):
        return None


def _stamp(path):
    try:
        s = path.stat()
        return (s.st_mtime_ns, s.st_ctime_ns, s.st_size, s.st_ino)
    except OSError:
        return None


def _text(value):
    return value if isinstance(value, str) and value else None


def _number(value):
    try:
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None
    except OverflowError:
        return None


def _benchmark(data, sector):
    if not data:
        return None
    groups = data.get('sectors')
    group = groups.get(sector) if isinstance(groups, dict) else None
    name = sector
    if not group:
        group, name = data.get('all'), 'Russell 1000'
    return {**group, 'group': name} if isinstance(group, dict) else None


def _row(root, ticker, universe, targets, bench):
    records = {kind: _read(root / ticker / (kind + '.json')) for kind in KINDS}
    company, gov, pay, rf, ins, fund = (records[k] or {} for k in KINDS)
    target = targets.get(ticker) or {}
    sector = sectors.sector(company.get('sic') or target.get('sic') or fund.get('sic'))
    years = fund.get('years')
    fiscal_end = None
    if isinstance(years, list):
        fiscal_end = max((_text(y.get('fy_end')) for y in years if isinstance(y, dict)
                          and _text(y.get('fy_end'))), default=None)
    row = dict(ticker=ticker, name=_text(company.get('name')) or _text(target.get('name')) or _text(fund.get('name')),
               sector=sector, fy_end=_text(target.get('fy_end')) or fiscal_end or _text(pay.get('fy_end')),
               pay_efficiency_pct=None, grade=None, grade_score=None, upside_pct=None,
               price_date=_text(target.get('price_date')), valuation_confidence=None,
               sources={'financials_url': _text(company.get('tenk_url')) or _text(pay.get('tenk_url')),
                        'proxy_url': _text(gov.get('proxy_url')) or _text(pay.get('proxy_url')),
                        'valuation_source': None}, missing=[])
    if pay.get('available') is True and pay.get('denominator') == 'operating':
        row['pay_efficiency_pct'] = _number(pay.get('pct'))
    val = None
    if target:
        try:
            val = valuation.value(target, universe['rows'])
            if not _finite_tree(val):
                val = None
        except (KeyError, TypeError, ValueError, ArithmeticError, StopIteration):
            val = None
    if val and val.get('available') is True:
        row['upside_pct'] = _number(val.get('upside_pct'))
        row['valuation_confidence'] = val.get('confidence') if val.get('confidence') in ('low', 'normal') else None
        row['sources']['valuation_source'] = _text(universe.get('source')) or valuation.SOURCE
    parts, errors = {}, {}
    if records['governance'] is not None and gov.get('available') is not False:
        parts['governance'] = (gov, pay, _benchmark(bench, sector))
    if (records['red_flags'] is not None and rf.get('available') is not False
            and isinstance(rf.get('flags'), list)
            and all(isinstance(f, dict) and f.get('severity') in grade.FLAG_POINTS for f in rf['flags'])):
        parts['red_flags'] = rf
    if (records['insiders'] is not None and ins.get('available') is not False
            and isinstance(ins.get('buys'), dict) and isinstance(ins.get('sells'), dict)):
        parts['insiders'] = (ins, target.get('market_cap') if val and val.get('available') else None)
    if val:
        parts['valuation'] = val
    for part in grade.WEIGHTS:
        if part not in parts:
            errors[part] = 'Cached input unavailable.'
    result = None
    try:
        result = grade.build(ticker, row['name'], parts, errors)
        if result.get('available') is True and _finite_tree(result):
            row['grade_score'] = _number(result.get('score'))
            row['grade'] = result.get('letter') if row['grade_score'] is not None else None
    except (KeyError, TypeError, ValueError, ArithmeticError, StopIteration, AttributeError):
        pass
    reasons = {
        'name': 'Cached company name unavailable.', 'sector': 'SEC industry does not map to a sector.',
        'fy_end': 'Cached fiscal year end unavailable.',
        'pay_efficiency_pct': pay.get('reason') or 'Finite operating-income Pay Efficiency unavailable in cache.',
        'grade': (result or {}).get('reason') or 'Cached inputs could not produce Company Grade.',
        'grade_score': 'Company Grade unavailable.',
        'upside_pct': (val or {}).get('reason') or 'Cached peer valuation unavailable.',
        'price_date': 'Cached price date unavailable.',
        'valuation_confidence': 'Cached valuation confidence unavailable.',
    }
    for field, reason in reasons.items():
        if row[field] is None:
            row['missing'].append(f'{field}: {reason}')
    for field, value in row['sources'].items():
        if value is None:
            row['missing'].append(f'sources.{field}: Cached source unavailable.')
    if row['pay_efficiency_pct'] is not None and row['pay_efficiency_pct'] < 0:
        row['missing'].append('pay_efficiency_pct: Negative compensation stays signed; it is not superior efficiency.')
    return row


def _snapshot():
    global _cache
    with _lock:
        root = Path(prebuilt.DIR)
        manifest = _read(root / 'manifest.json')
        warnings = []
        raw = manifest.get('tickers') if manifest else None
        valid_manifest = isinstance(raw, list) and len(raw) <= MAX_COMPANIES
        tickers = sorted({t for t in raw if isinstance(t, str) and _TICKER.fullmatch(t)}) if valid_manifest else []
        if valid_manifest and len(tickers) != len(raw):
            warnings.append('Invalid or duplicate manifest tickers were ignored.')
        # A ticker is validated before it becomes part of any filesystem path.
        safe = [t for t in tickers if not (root / t).is_symlink()]
        if len(safe) != len(tickers):
            warnings.append('Symlink company directories were ignored.')
        paths = [root / name for name in ('manifest.json', 'valuation.json', 'benchmarks.json')]
        paths += [root / t / (kind + '.json') for t in safe for kind in KINDS]
        signature = (str(root.resolve()), tuple((str(p), _stamp(p)) for p in paths), tuple(safe))
        if _cache is not None and _cache[0] == signature:
            return _cache[1]
        if not valid_manifest or not safe:
            snapshot = dict(available=False, built_at=_text((manifest or {}).get('built_at')), total=0,
                            sectors=[], coverage={'pay_efficiency_pct': 0, 'grade': 0, 'upside_pct': 0},
                            rows=[], warnings=warnings + ['Cached screener snapshot unavailable: missing, invalid or empty manifest.'])
        else:
            universe = _read(root / 'valuation.json') or {}
            candidates = universe.get('rows')
            candidates = candidates if isinstance(candidates, list) and len(candidates) <= MAX_COMPANIES else []
            # Reject malformed peer records independently before they can contaminate all estimates.
            peers = []
            for r in candidates:
                if not isinstance(r, dict) or not _finite_tree(r):
                    continue
                try:
                    required = ('ticker', 'cik', 'sic', 'sector', 'sane', 'features', 'figures', 'multiples',
                                'shares', 'price', 'debt', 'cash', *valuation.PEER_KEYS)
                    if any(k not in r for k in required):
                        continue
                    if not _number(r['price']) or r['price'] <= 0 or not _number(r['shares']) or r['shares'] <= 0:
                        continue
                    if any(k not in r['features'] for k in valuation.FEATURES):
                        continue
                    if any(k not in r['multiples'] for k in valuation.METHODS):
                        continue
                    mappings = (r['features'], r['figures'], r['multiples'])
                    if any(not isinstance(m, dict) for m in mappings):
                        continue
                    if any(v is not None and _number(v) is None for m in mappings for v in m.values()):
                        continue
                    if any(k not in r['figures'] for _, k in valuation.METHODS.values()):
                        continue
                    if any(r[k] is not None and _number(r[k]) is None for k in ('debt', 'cash', 'market_cap')):
                        continue
                    peers.append(r)
                except (TypeError, KeyError):
                    continue
            universe = {**universe, 'rows': peers}
            targets = {r['ticker']: r for r in peers if isinstance(r['ticker'], str)}
            bench = _read(root / 'benchmarks.json')
            rows = []
            for ticker in safe:
                try:
                    rows.append(_row(root, ticker, universe, targets, bench))
                except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError):
                    # Corruption must not turn into an invented grade or fail other companies.
                    rows.append(_row(root, ticker, {'rows': []}, {}, None))
            if not peers:
                warnings.append('Cached valuation universe unavailable; peer valuation is missing.')
            warnings.append('Estimates use cached prices. Company Grade is descriptive; low-confidence valuations are not reliable investment signals.')
            snapshot = dict(available=True, built_at=_text(manifest.get('built_at')), total=len(rows), rows=rows,
                            sectors=sorted({r['sector'] for r in rows if r['sector']}),
                            coverage={k: sum(r[k] is not None for r in rows) for k in ('pay_efficiency_pct', 'grade', 'upside_pct')},
                            warnings=warnings)
        _cache = (signature, snapshot)
        return snapshot


def screen(search=None, sector=None, grade=None, max_pay_efficiency_pct=None, min_upside_pct=None,
           sort='ticker', order='asc', limit=50, offset=0):
    """Filter one bounded snapshot; numeric values are percentage points."""
    if sort not in SORTS or order not in ('asc', 'desc') or grade not in (None, 'A', 'B', 'C', 'D', 'F'):
        raise ValueError('Invalid screener sort, order or grade.')
    if not isinstance(limit, int) or not 1 <= limit <= 200 or not isinstance(offset, int) or offset < 0:
        raise ValueError('Invalid screener pagination.')
    for value in (max_pay_efficiency_pct, min_upside_pct):
        if value is not None and _number(value) is None:
            raise ValueError('Numeric filters must be finite.')
    snapshot = _snapshot()
    query = (search or '').strip().casefold()
    rows = [r for r in snapshot['rows'] if
            (not query or query in r['ticker'].casefold() or query in (r['name'] or '').casefold()) and
            (sector is None or r['sector'] == sector) and (grade is None or r['grade'] == grade) and
            (max_pay_efficiency_pct is None or r['pay_efficiency_pct'] is not None and r['pay_efficiency_pct'] <= max_pay_efficiency_pct) and
            (min_upside_pct is None or r['upside_pct'] is not None and r['upside_pct'] >= min_upside_pct)]
    present = sorted((r for r in rows if r[sort] is not None), key=lambda r: r['ticker'])
    present.sort(key=lambda r: r[sort].casefold() if isinstance(r[sort], str) else r[sort], reverse=order == 'desc')
    missing = sorted((r for r in rows if r[sort] is None), key=lambda r: r['ticker'])
    return copy.deepcopy({**snapshot, 'matched': len(rows), 'limit': limit, 'offset': offset,
                          'rows': (present + missing)[offset:offset + limit]})
