"""
Plain text of SEC filings, read straight from EDGAR's own files, for the AI readers (earnings tone, ask a filing).

  submissions()      a company's filing list from data.sec.gov (forms, dates, 8-K item numbers)
  documents()        the files inside one filing, with their SEC document type (EX-99.1, EX-13, ...)
  html_text()        a fast HTML-to-text pass. Regex instead of BeautifulSoup: a bank's 10-K can be 10+ MB of HTML,
                     and the free server has 0.1 CPU and 512 MB.
"""
import html as _html
import json
import re

import httpx

import sec_core

ARCHIVES = "https://www.sec.gov/Archives/edgar/data"


def submissions(cik, pages=3):
    """The company's filings, newest first, as a list of dicts (form, accession, filed, period, items, primary_doc).
    SEC's main file holds the latest 1,000 filings; heavy filers (banks issuing notes) need the older pages too."""
    cik = int(cik)
    data = json.loads(sec_core.sec_fetch(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    blocks = [data["filings"]["recent"]]
    for f in data["filings"].get("files", [])[:max(0, pages - 1)]:
        blocks.append(json.loads(sec_core.sec_fetch(f"https://data.sec.gov/submissions/{f['name']}")))
    out = []
    for b in blocks:
        for i, accn in enumerate(b["accessionNumber"]):
            out.append({"form": b["form"][i], "accession": accn, "filed": b["filingDate"][i],
                        "period": b.get("reportDate", [""] * len(b["form"]))[i] or "",
                        "items": b.get("items", [""] * len(b["form"]))[i] or "",
                        "primary_doc": b.get("primaryDocument", [""] * len(b["form"]))[i] or "",
                        "cik": cik})
    return out


def folder(cik, accn):
    return f"{ARCHIVES}/{int(cik)}/{accn.replace('-', '')}"


def documents(cik, accn):
    """[(type, url)] for the files in a filing, read from its -index.htm page (the only SEC file that lists each
    document's type)."""
    page = sec_core.sec_fetch(f"{folder(cik, accn)}/{accn}-index.htm").decode("utf-8", errors="ignore")
    docs = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.DOTALL | re.IGNORECASE):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.DOTALL | re.IGNORECASE)
        link = re.search(r'href="([^"]+)"', row)
        if len(cells) < 4 or not link:
            continue
        href = link.group(1).replace("/ix?doc=", "")
        doc_type = re.sub(r"<[^>]+>", "", cells[3]).strip().upper()
        docs.append((doc_type, href if href.startswith("http") else "https://www.sec.gov" + href))
    return docs


BLOCK_END = re.compile(rb"</(?:p|div|tr|li|h[1-6]|table|title)\s*>|<br\s*/?>", re.IGNORECASE)
CELL_END = re.compile(rb"</t[dh]\s*>", re.IGNORECASE)
TAG = re.compile(rb"<[^>]+>")
# Inline XBRL keeps its hidden facts in ix:header; scripts and styles aren't text either
HIDDEN_START = re.compile(rb"<(ix:header|script|style)\b", re.IGNORECASE)
HIDDEN_END = {name: re.compile(rb"</" + name + rb"\s*>", re.IGNORECASE) for name in (b"ix:header", b"script", b"style")}
CHUNK = 1 << 20


def _strip(piece):
    """Tags out of a stretch of HTML that holds only whole tags."""
    piece = BLOCK_END.sub(b"\n", piece)
    piece = CELL_END.sub(b" ", piece)
    return TAG.sub(b" ", piece)


def html_text(raw, chunks=None):
    """Readable text with one line per paragraph or table row. Table cells are kept in order on their row, so a
    debt maturity table reads like "2027 $ 1,500 2028 2,250".
    Reads the HTML a piece at a time (from `chunks`, or from `raw` cut into 1 MB pieces). A bank's 10-K is tens of
    MB of HTML; holding it whole, plus a copy per cleanup step, came close to the free server's 512 MB."""
    if chunks is None:
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        chunks = (raw[i:i + CHUNK] for i in range(0, len(raw), CHUNK))
    out, buf, hidden_end = [], b"", None
    for chunk in chunks:
        buf += chunk
        while True:
            if hidden_end is not None:
                m = hidden_end.search(buf)
                if not m:
                    buf = buf[-32:]  # enough to catch a closing tag split across pieces
                    break
                buf, hidden_end = buf[m.end():], None
            m = HIDDEN_START.search(buf)
            if m:
                out.append(_strip(buf[:m.start()]))
                hidden_end = HIDDEN_END[m.group(1).lower()]
                buf = buf[m.end():]
                continue
            # Keep whatever follows the last ">" for the next piece: it may be the start of a tag
            cut = buf.rfind(b">") + 1
            out.append(_strip(buf[:cut]))
            buf = buf[cut:]
            break
    if hidden_end is None:
        out.append(_strip(buf))
    text = _html.unescape(b"".join(out).decode("utf-8", errors="ignore"))
    del out
    text = text.replace("\xa0", " ").replace("\u200b", "")
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def fetch_text(url):
    """A filing document's text, streamed from SEC so the whole HTML is never in memory at once."""
    with httpx.stream("GET", url, headers={"User-Agent": sec_core.SEC_IDENTITY}, timeout=60, follow_redirects=True) as r:
        r.raise_for_status()
        return html_text(None, r.iter_bytes(CHUNK))
