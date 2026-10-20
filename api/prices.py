"""
Share price at each fiscal year end, for the Trends chart. From Yahoo Finance's daily chart data: the closing price on
the last trading day on or before the fiscal year end, adjusted for stock splits (not for dividends), so years are
comparable. A missing price never blocks the rest of the trends lookup; it just leaves the overlay off.
"""
from datetime import date, datetime, timedelta, timezone

import httpx

SOURCE = "Yahoo Finance daily close, split-adjusted (query1.finance.yahoo.com chart data)"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SEC-Terminal/1.0; +https://sec-10k-summarizer.vercel.app)"}


def daily_closes(ticker, first, last):
    """{date: close} for trading days from first to last (date objects), from Yahoo's chart endpoint."""
    p1 = int(datetime(first.year, first.month, first.day, tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(last.year, last.month, last.day, tzinfo=timezone.utc).timestamp()) + 86400
    r = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                  params={"period1": p1, "period2": p2, "interval": "1d", "events": "split"},
                  headers=HEADERS, timeout=30)
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    offset = result["meta"].get("gmtoffset", 0)
    closes = result["indicators"]["quote"][0]["close"]
    out = {}
    for ts, c in zip(result.get("timestamp", []), closes):
        if c is not None:
            out[datetime.fromtimestamp(ts + offset, tz=timezone.utc).date()] = c
    return out


def year_end_closes(ticker, fy_ends):
    """{"available", "source", "years": [{"fy_end", "date", "close"}]} for each fiscal year end (ISO dates)."""
    if not fy_ends:
        return {"available": False, "reason": "No fiscal years to price.", "source": SOURCE}
    ends = [date.fromisoformat(e) for e in fy_ends]
    try:
        closes = daily_closes(ticker, min(ends) - timedelta(days=10), max(ends))
    except Exception as e:
        print(f"[{ticker}] share prices unavailable: {e!r}", flush=True)
        return {"available": False, "reason": "Yahoo Finance didn't return share prices for this ticker.", "source": SOURCE}
    years = []
    for fy_end, end in zip(fy_ends, ends):
        # Last trading day on or before the fiscal year end, within a week (a longer gap means no trading data)
        day = max((d for d in closes if end - timedelta(days=7) <= d <= end), default=None)
        years.append({"fy_end": fy_end, "date": day.isoformat() if day else None, "close": round(closes[day], 4) if day else None})
    if not any(y["close"] is not None for y in years):
        return {"available": False, "reason": "No trading prices around these fiscal year ends.", "source": SOURCE}
    return {"available": True, "source": SOURCE, "years": years}
