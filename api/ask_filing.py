"""
Ask a filing: a question about a company's latest 10-K, answered with a quote that is checked against the filing.

How it stays checkable:
  1. Plain keyword search (BM25, the standard search-engine scoring) picks the 10-K passages that best match the
     question. No AI is involved in choosing what the model reads.
  2. The model reads only those passages (about 9,000 characters) and must answer from them, quoting the passage
     it used.
  3. The quote is checked word for word against the whole 10-K. An answer whose quote isn't in the filing is
     marked unverified on the page.

Run on one company (from api/):  python ask_filing.py CAT "How much debt is due next year?"
"""
import json
import math
import re
import sys
from collections import Counter

import ai_client
import filing_text
from governance_policies import quote_in_filing

CHUNK_CHARS = 700
EXCERPT_CHARS = 9000
MAX_QUESTION = 300
SMALL_10K = 150_000  # characters; below this the 10-K body points to an annual report exhibit (EX-13), as banks do

STOP = set("""a an and are as at be been but by can could did do does for from had has have how i if in into is it its
its' me much many my of on or our out over so than that the their them then there these they this to up was we were
what when where which while who whom why will with would you your company companies company's year years 10-k""".split())

# A question's everyday words, and the words a 10-K uses for the same thing
SYNONYMS = {
    "debt": ["borrowings", "notes", "indebtedness", "maturities", "senior", "debentures"],
    "due": ["maturities", "mature", "maturing", "payable"],
    "owe": ["borrowings", "indebtedness", "payable"],
    "employees": ["employees", "headcount", "workforce", "human", "capital", "full-time"],
    "workers": ["employees", "workforce"],
    "staff": ["employees", "workforce"],
    "revenue": ["revenues", "sales", "net"],
    "sales": ["revenues", "revenue"],
    "customers": ["customer", "concentration"],
    "buyback": ["repurchase", "repurchases", "repurchased", "share"],
    "buybacks": ["repurchase", "repurchases", "repurchased", "share"],
    "dividend": ["dividends", "declared", "paid"],
    "lawsuit": ["litigation", "legal", "proceedings"],
    "lawsuits": ["litigation", "legal", "proceedings"],
    "sued": ["litigation", "legal", "proceedings"],
    "competitors": ["competition", "compete", "competitive"],
    "compete": ["competition", "competitors", "competitive"],
    "tax": ["taxes", "income", "effective", "rate"],
    "cash": ["liquidity", "equivalents"],
    "capex": ["capital", "expenditures"],
    "spending": ["expenditures", "capital"],
    "risks": ["risk", "factors", "adversely"],
    "pension": ["pension", "postretirement", "benefit", "plans"],
    "segments": ["segment", "reportable"],
    "acquisition": ["acquisitions", "acquired", "merger"],
    "auditor": ["registered", "public", "accounting", "firm"],
    "ceo": ["chief", "executive", "officer"],
    "cfo": ["chief", "financial", "officer"],
}


def tokens(text):
    return re.findall(r"[a-z0-9][a-z0-9'\-]*", text.lower())


def chunks(text, size=CHUNK_CHARS):
    """The 10-K cut into passages of about `size` characters along line breaks, so a table row stays whole."""
    out, cur = [], []
    length = 0
    for line in text.split("\n"):
        cur.append(line)
        length += len(line) + 1
        if length >= size:
            out.append(" ".join(cur))
            cur, length = [], 0
    if cur:
        out.append(" ".join(cur))
    return out


def query_terms(question, fiscal_year=None):
    """Question words without filler, plus the 10-K's words for them. "Next year" becomes the year after the 10-K's
    fiscal year, which is how a maturity table labels it."""
    words = [w for w in tokens(question) if w not in STOP and len(w) > 1]
    terms = list(words)
    for w in words:
        terms += SYNONYMS.get(w, [])
    q = question.lower()
    if fiscal_year:
        if "next year" in q or "coming year" in q or "next 12 months" in q or "next twelve months" in q:
            terms.append(str(fiscal_year + 1))
        if "this year" in q or "last year" in q:
            terms.append(str(fiscal_year))
    return terms


def search(passages, terms, k1=1.5, b=0.75):
    """BM25 score of each passage for the terms. Passages in the first 2% of the 10-K (cover page, table of
    contents) count for a quarter, since they name every topic without saying anything about it."""
    docs = [Counter(tokens(p)) for p in passages]
    n = len(docs) or 1
    avg = sum(sum(d.values()) for d in docs) / n or 1
    want = Counter(terms)
    df = {t: sum(1 for d in docs if t in d) for t in want}
    scores = []
    for i, d in enumerate(docs):
        length = sum(d.values()) or 1
        s = 0.0
        for t, weight in want.items():
            f = d.get(t, 0)
            if not f:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += weight * idf * f * (k1 + 1) / (f + k1 * (1 - b + b * length / avg))
        if i < n * 0.02:
            s *= 0.25
        scores.append(s)
    return scores


def excerpts(text, question, fiscal_year=None, limit=EXCERPT_CHARS):
    """The best-matching passages, each with the passage after it (a table often continues there), in filing order."""
    passages = chunks(text)
    scores = search(passages, query_terms(question, fiscal_year))
    order = sorted(range(len(passages)), key=lambda i: scores[i], reverse=True)
    keep, size = set(), 0
    for i in order:
        if scores[i] <= 0:
            break
        for j in (i, i + 1):
            if j < len(passages) and j not in keep and size + len(passages[j]) <= limit:
                keep.add(j)
                size += len(passages[j])
        if size >= limit - CHUNK_CHARS:
            break
    return [passages[i] for i in sorted(keep)]


SYSTEM = ("You answer questions about a company's annual report (SEC Form 10-K) using only the excerpts given. "
          "Never use outside knowledge. Reply with JSON only.")


def prompt(question, name, period, found):
    joined = "\n\n".join(f"[{n}] {e}" for n, e in enumerate(found, 1))
    return (
        f"Company: {name}. 10-K for the fiscal year ended {period or 'the latest year'}.\n\n"
        f"Question: {question}\n\n"
        f"10-K excerpts:\n{joined}\n\n"
        'Answer with JSON: {"found": true | false, "answer": "<two or three plain sentences; give numbers with their '
        'units and dates exactly as the excerpts state them>", "quote": "<the passage from the excerpts that supports '
        'the answer, copied word for word, at most 60 words>"}\n'
        'If the excerpts do not answer the question, set "found" to false, leave "quote" empty, and say in "answer" '
        "what the excerpts don't cover."
    )


def parse(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise ValueError("no JSON in the reply")
    data = json.loads(m.group(0))
    found = data.get("found")
    found = found if isinstance(found, bool) else str(found).strip().lower() == "true"
    return {"found": found, "answer": str(data.get("answer") or "").strip(), "quote": str(data.get("quote") or "").strip()}


def tenk_text(ticker):
    """The SEC part (no AI): the latest 10-K's text and address. Runs in the API's child process. The filing is found
    from SEC's plain filing list rather than edgartools' filings table, which costs big banks over 100 MB more."""
    import sec_core
    company = sec_core.Company(ticker)
    filing = next((f for f in filing_text.submissions(company.cik) if f["form"] == "10-K"), None)
    if not filing:
        raise sec_core.DataUnavailable(sec_core.NO_10K.format(name=company.name))
    url = f"{filing_text.folder(filing['cik'], filing['accession'])}/{filing['primary_doc']}"
    text = filing_text.fetch_text(url)
    if len(text) < SMALL_10K:
        # The 10-K body is a shell that points to the annual report, filed as Exhibit 13
        for doc_type, doc_url in filing_text.documents(filing["cik"], filing["accession"]):
            if doc_type.startswith("EX-13") and doc_url.lower().endswith((".htm", ".html")):
                text += "\n" + filing_text.fetch_text(doc_url)
    return {"ticker": ticker.upper(), "name": company.name, "accession": filing["accession"], "url": url,
            "filed": filing["filed"], "period": filing["period"], "text": text}


def answer(doc, question):
    """The AI part: one call on the matching passages, then the quote check against the whole 10-K."""
    fy = int(doc["period"][:4]) if re.match(r"\d{4}", doc["period"] or "") else None
    found = excerpts(doc["text"], question, fy)
    base = {"ticker": doc["ticker"], "name": doc["name"], "question": question, "tenk_url": doc["url"],
            "tenk_date": doc["filed"], "period": doc["period"], "excerpts": found}
    if not found:
        return {**base, "found": False, "answer": "No part of the 10-K matches the words in this question. Try other words.",
                "quote": "", "verified": False, "model": None}
    reply = ai_client.chat(prompt(question, doc["name"], doc["period"], found), system=SYSTEM, json_mode=True, max_tokens=2000)
    try:
        result = parse(reply["text"])
    except (ValueError, json.JSONDecodeError) as e:
        raise ai_client.AIError(f"The AI's reply couldn't be read ({e}). Try again.")
    verified = bool(result["quote"]) and quote_in_filing(result["quote"], doc["text"])
    return {**base, **result, "verified": verified, "model": reply["model"], "seconds": reply.get("seconds")}


if __name__ == "__main__":
    t = (sys.argv[1] if len(sys.argv) > 1 else "CAT").upper()
    q = sys.argv[2] if len(sys.argv) > 2 else "How much debt is due next year?"
    print(f"AI: {ai_client.describe()}")
    print(json.dumps(answer(tenk_text(t), q), indent=2))
