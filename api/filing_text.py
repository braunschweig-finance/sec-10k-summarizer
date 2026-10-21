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


BLOCK_END = re.compile(r"</(?:p|div|tr|li|h[1-6]|table|title)\s*>|<br\s*/?>", re.IGNORECASE)
CELL_END = re.compile(r"</t[dh]\s*>", re.IGNORECASE)


def html_text(raw):
    """Readable text with one line per paragraph or table row. Table cells are kept in order on their row, so a
    debt maturity table reads like "2027 $ 1,500 2028 2,250"."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    # Inline XBRL keeps its hidden facts in ix:header; scripts and styles aren't text either
    raw = re.sub(r"<ix:header.*?</ix:header>|<script.*?</script>|<style.*?</style>", " ", raw,
                 flags=re.DOTALL | re.IGNORECASE)
    raw = BLOCK_END.sub("\n", raw)
    raw = CELL_END.sub(" ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    text = _html.unescape(raw).replace("\xa0", " ").replace("​", "")
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def fetch_text(url):
    return html_text(sec_core.sec_fetch(url))
