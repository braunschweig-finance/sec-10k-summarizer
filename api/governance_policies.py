"""
Governance policy reader: which shareholder-rights policies a company has, read from its proxy statement (DEF 14A)
by an AI model. None of these are XBRL-tagged, so they've only been available by reading the filing by hand.

How it stays checkable:
  1. For each policy, plain keyword search picks the few proxy passages that talk about it (no AI, no guessing).
  2. The model reads only those passages (about 4,000 characters), so a small laptop model can handle it.
  3. The model must quote the sentence it used. The quote is checked word for word against the proxy; an answer
     whose quote isn't in the filing is marked unverified and doesn't count toward the score.

Run on one company (from api/):  python governance_policies.py CAT
"""
import json
import re
import sys

import ai_client
from governance_metrics import sentences

# friendly: the answer that favors shareholders. Each policy's keywords find the passages the model reads.
POLICIES = [
    {"key": "independent_chair", "name": "Independent board chair",
     "question": "Is the chair of the board an independent director (someone other than the CEO)?",
     "friendly": "yes", "keywords": [r"independent chair", r"chair(?:man|woman|person)? of the board", r"board chair",
                                     r"combin\w* (?:the )?(?:roles|positions) of (?:chair|ceo)", r"separat\w* (?:the )?(?:roles|positions)"]},
    {"key": "declassified_board", "name": "All directors elected every year",
     "question": "Are all directors elected annually (no staggered or classified board)?",
     "friendly": "yes", "keywords": [r"elected annually", r"annual election", r"classified board", r"staggered",
                                     r"declassif", r"one-year term"]},
    {"key": "majority_voting", "name": "Majority voting for directors",
     "question": "In uncontested elections, must a director receive a majority of votes cast (not just a plurality)?",
     "friendly": "yes", "keywords": [r"majority (?:of the )?votes cast", r"majority voting", r"plurality",
                                     r"resignation policy"]},
    {"key": "proxy_access", "name": "Proxy access",
     "question": "Can shareholders nominate directors in the company's own proxy materials (proxy access)?",
     "friendly": "yes", "keywords": [r"proxy access", r"include (?:their|its|his or her) (?:own )?(?:director )?nominees?",
                                     r"3% of (?:our|the) outstanding"]},
    {"key": "special_meetings", "name": "Shareholders can call special meetings",
     "question": "Can shareholders call a special meeting? If yes, give the ownership threshold.",
     "friendly": "yes", "keywords": [r"special meeting", r"call a special"]},
    {"key": "written_consent", "name": "Shareholders can act by written consent",
     "question": "Can shareholders act by written consent without a meeting?",
     "friendly": "yes", "keywords": [r"written consent"]},
    {"key": "no_poison_pill", "name": "No poison pill",
     "question": "Does the company have NO shareholder rights plan (poison pill) in place? Answer yes if there is none.",
     "friendly": "yes", "keywords": [r"poison pill", r"rights plan", r"rights agreement"]},
    {"key": "anti_pledging", "name": "Pledging of shares banned",
     "question": "Are directors and executive officers prohibited from pledging company stock?",
     "friendly": "yes", "keywords": [r"pledg"]},
    {"key": "clawback_beyond_rules", "name": "Clawback goes beyond SEC rules",
     "question": "Does the clawback policy go beyond the SEC/stock exchange required restatement clawback, e.g. "
                 "covering misconduct, time-based awards, or detrimental conduct?",
     "friendly": "yes", "keywords": [r"clawback", r"recoup", r"compensation recovery", r"misconduct",
                                     r"detrimental conduct"]},
    {"key": "ceo_ownership_guideline", "name": "CEO stock ownership guideline",
     "question": "Does the CEO have a stock ownership guideline? If yes, give the multiple of base salary.",
     "friendly": "yes", "keywords": [r"ownership guideline", r"ownership requirement", r"times (?:his|her|their|the ceo's)? ?base salary",
                                     r"\d+x (?:base )?salary"]},
]

PASSAGE_CHARS = 4000
SYSTEM = ("You read US proxy statements (SEC Form DEF 14A) and answer one question about a company's governance "
          "policy. Use only the excerpts given. Reply with JSON only.")


def passages(text, keywords, limit=PASSAGE_CHARS):
    """The sentences that mention the policy, each with its neighbours, best-scoring first, up to `limit` characters.
    Sentences in the first 3% of the proxy (cover page, table of contents) are skipped when there are others."""
    sents = sentences(text)
    pats = [re.compile(k, re.IGNORECASE) for k in keywords]
    scored = []
    for i, (pos, s) in enumerate(sents):
        hits = sum(1 for p in pats if p.search(s))
        if hits:
            scored.append((hits, pos > len(text) * 0.03, -i, i))
    scored.sort(reverse=True)
    out, used, size = [], set(), 0
    for *_, i in scored:
        window = [j for j in range(i - 1, i + 2) if 0 <= j < len(sents) and j not in used]
        chunk = " ".join(sents[j][1].strip() for j in window)
        if not chunk or size + len(chunk) > limit:
            continue
        used.update(window)
        out.append((i, chunk))
        size += len(chunk)
    return [c for _, c in sorted(out)]  # back in filing order, so the model reads them as the proxy runs


def _norm(s):
    s = s.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[^a-z0-9%$.]+", " ", s).strip()


def quote_in_filing(quote, text):
    """True when the quote appears in the proxy, ignoring case, punctuation and spacing. A quote the model
    shortened with "..." passes when each part is found."""
    if not quote or len(quote.strip()) < 15:
        return False
    flat = _norm(text)
    parts = [_norm(p) for p in re.split(r"\.{3}|…", quote)]
    return all(p in flat for p in parts if len(p) >= 10) and any(len(p) >= 10 for p in parts)


def prompt(policy, excerpts):
    joined = "\n\n".join(f"[{n}] {e}" for n, e in enumerate(excerpts, 1))
    return (
        f"Question: {policy['question']}\n\n"
        f"Proxy statement excerpts:\n{joined}\n\n"
        'Answer with JSON: {"answer": "yes" | "no" | "not disclosed", "detail": "<one short sentence, include any '
        'number such as a % threshold or salary multiple>", "quote": "<the exact sentence from the excerpts that '
        'supports the answer, copied word for word>"}\n'
        'Use "not disclosed" when the excerpts do not answer the question.'
    )


def parse(text):
    """The JSON object in the model's reply. Small models sometimes wrap it in ``` or add a thinking block first."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise ValueError("no JSON in the reply")
    data = json.loads(m.group(0))
    answer = str(data.get("answer", "")).strip().lower()
    if answer not in ("yes", "no", "not disclosed"):
        answer = "not disclosed"
    return {"answer": answer, "detail": str(data.get("detail") or "").strip(), "quote": str(data.get("quote") or "").strip()}


def read_policy(policy, text):
    excerpts = passages(text, policy["keywords"])
    base = {"key": policy["key"], "name": policy["name"], "friendly_answer": policy["friendly"]}
    if not excerpts:
        return {**base, "answer": "not disclosed", "detail": "The proxy doesn't mention this topic.", "quote": "",
                "verified": False, "model": None, "seconds": 0}
    try:
        reply = ai_client.chat(prompt(policy, excerpts), system=SYSTEM, json_mode=True, max_tokens=4000)
        result = parse(reply["text"])
    except ValueError as e:
        return {**base, "answer": "error", "detail": f"The model's reply couldn't be read ({e}).", "quote": "",
                "verified": False, "model": None, "seconds": 0}
    verified = quote_in_filing(result["quote"], text)
    return {**base, **result, "verified": verified, "model": reply["model"], "seconds": reply.get("seconds")}


def score(results):
    """Shareholder-friendly policies counted only when the answer's quote was found in the filing."""
    counted = [r for r in results if r["verified"] and r["answer"] in ("yes", "no")]
    friendly = sum(1 for r in counted if r["answer"] == r["friendly_answer"])
    return {"friendly": friendly, "answered": len(counted), "asked": len(results)}


def read_proxy(text, progress=None):
    results = []
    for p in POLICIES:
        r = read_policy(p, text)
        results.append(r)
        if progress:
            progress(r)
    return {"policies": results, "score": score(results), "ai": ai_client.describe()}


def proxy_for(ticker):
    """The latest DEF 14A's cleaned text and its address, the same way the governance tab reads it."""
    import sec_core
    filings = sec_core.latest_filings(sec_core.Company(ticker), "DEF 14A")
    if not filings:
        raise sec_core.DataUnavailable(f"{ticker} has no DEF 14A proxy statement on EDGAR.")
    raw, _ = sec_core.get_proxy_text(filings[0])
    return sec_core.clean_governance_text(raw), filings[0].url, str(filings[0].filing_date)


def get_governance_policies(ticker):
    text, url, filed = proxy_for(ticker)
    return {"ticker": ticker.upper(), "proxy_url": url, "proxy_date": filed, **read_proxy(text)}


if __name__ == "__main__":
    ticker = (sys.argv[1] if len(sys.argv) > 1 else "CAT").upper()
    print(f"AI: {ai_client.describe()}")
    text, url, filed = proxy_for(ticker)
    print(f"{ticker} proxy filed {filed}: {url} ({len(text):,} characters)\n")

    def show(r):
        mark = "checked" if r["verified"] else "NOT in filing" if r["quote"] else "no quote"
        print(f"{r['name']:<40} {r['answer']:<14} ({r['seconds']}s, quote {mark})  {r['detail']}")

    out = {"ticker": ticker, "proxy_url": url, "proxy_date": filed, **read_proxy(text, show)}
    s = out["score"]
    print(f"\nShareholder-friendly: {s['friendly']} of {s['answered']} answered with a checked quote ({s['asked']} asked)")
    path = f"governance_policies_{ticker}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"Saved {path}")
