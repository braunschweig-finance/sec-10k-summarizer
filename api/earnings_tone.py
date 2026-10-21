"""
Earnings release tone: does management sound more or less confident than last quarter, and did guidance change?

How it stays checkable:
  1. The two releases are found from SEC's own filing list: the latest two 8-Ks filed under Item 2.02 (Results of
     Operations), at least 50 days apart, and their Exhibit 99.1 press release. No AI is involved in picking them.
  2. A plain word count (no AI) gives confident and cautious words per 1,000 words for each release, so the AI's
     reading can be compared with a number anyone can recompute.
  3. The AI reads the narrative part of both releases (tables, safe-harbor and webcast boilerplate left out) and
     must quote a sentence from each release for every change it reports. Each quote is checked word for word
     against that release; a change whose quote isn't there is marked unverified.

Run on one company (from api/):  python earnings_tone.py CAT
"""
import json
import re
import sys
from datetime import date

import ai_client
import filing_text
from governance_policies import quote_in_filing

MIN_DAYS_APART = 50  # a second 2.02 filing in the same quarter (a correction, an investor day) isn't "last quarter"
NARRATIVE_CHARS = 12000  # per release; two releases plus the prompt stay well inside a free-tier request

BOILERPLATE = re.compile(r"forward[- ]looking|safe harbor|private securities litigation|webcast|conference call|"
                         r"non-gaap (?:financial )?measures? (?:is|are|should|used)|investor relations|"
                         r"www\.|https?://|@", re.IGNORECASE)
GUIDANCE = re.compile(r"\b(?:guidance|outlook|expects?|expected|anticipates?|forecast|full[- ]year|fiscal (?:year )?20\d\d|"
                      r"reaffirm\w*|rais(?:e|ed|es|ing)|lower(?:ed|s|ing)?|narrow\w*|withdr[ae]w\w*)\b", re.IGNORECASE)

# A short, fixed word list, so the count is reproducible. It is this app's own list, not a published dictionary.
CONFIDENT = re.compile(r"\b(?:strong(?:er|est|ly)?|record|exceed(?:ed|s|ing)?|outperform\w*|momentum|robust|"
                       r"accelerat\w*|confident|confidence|excellent|outstanding|solid|healthy|improv(?:e|ed|es|ing|ement)|"
                       r"success(?:ful|fully)?|pleased|delighted|exceptional|best)\b", re.IGNORECASE)
CAUTIOUS = re.compile(r"\b(?:challeng(?:e|es|ed|ing)|headwinds?|uncertain(?:ty|ties)?|soft(?:ness|er)?|weak(?:er|ness|ened)?|"
                      r"declin(?:e|ed|es|ing)|difficult|pressures?|pressured|volatil(?:e|ity)|cautious(?:ly)?|caution|"
                      r"slowdown|slow(?:er|ing)|disappointing|impairments?|restructuring)\b", re.IGNORECASE)


def earnings_filings(subs):
    """The latest earnings 8-K and the one for the quarter before it."""
    found = [f for f in subs if f["form"] == "8-K" and "2.02" in f["items"].split(",")]
    if not found:
        return None, None
    latest = found[0]
    for f in found[1:]:
        if (date.fromisoformat(latest["filed"]) - date.fromisoformat(f["filed"])).days >= MIN_DAYS_APART:
            return latest, f
    return latest, None


def press_release_url(filing):
    """Exhibit 99.1 of an 8-K. Some filers number it 99 or 99.01; failing all of those, the first EX-99 exhibit."""
    docs = [(t, u) for t, u in filing_text.documents(filing["cik"], filing["accession"])
            if u.lower().endswith((".htm", ".html", ".txt"))]
    for want in (r"EX-99\.0?1$", r"EX-99$", r"EX-99"):
        for t, u in docs:
            if re.match(want, t):
                return u
    return None


def narrative(text, limit=NARRATIVE_CHARS):
    """The release's written paragraphs, without number tables or boilerplate. Outlook and guidance paragraphs are
    kept first if the release is long, then the rest in filing order up to `limit` characters."""
    paras = []
    for line in text.split("\n"):
        letters = sum(c.isalpha() for c in line)
        if len(line.split()) < 8 or letters < 0.6 * len(line.replace(" ", "")) or BOILERPLATE.search(line):
            continue
        paras.append(line)
    keep, size = set(), 0
    for want_guidance in (True, False):
        for i, p in enumerate(paras):
            if i in keep or bool(GUIDANCE.search(p)) != want_guidance:
                continue
            if size + len(p) > limit:
                continue
            keep.add(i)
            size += len(p)
    return "\n".join(p for i, p in enumerate(paras) if i in keep)


def word_check(text):
    words = len(re.findall(r"[A-Za-z']+", text)) or 1
    return {"words": words,
            "confident_per_1000": round(len(CONFIDENT.findall(text)) * 1000 / words, 1),
            "cautious_per_1000": round(len(CAUTIOUS.findall(text)) * 1000 / words, 1)}


SYSTEM = ("You compare two quarterly earnings press releases from the same company (SEC Form 8-K, Exhibit 99.1). "
          "Use only the text given. Every quote must be copied word for word from the release it is labeled with. "
          "Reply with JSON only.")

DIRECTIONS = ("more confident", "less confident", "about the same")
GUIDANCE_CHANGES = ("raised", "lowered", "maintained", "introduced", "withdrawn", "mixed", "not given")


def prompt(name, latest, prior):
    return (
        f"Company: {name}\n\n"
        f"LATEST release (filed {latest['filed']}):\n<<<\n{latest['narrative']}\n>>>\n\n"
        f"PRIOR release, the quarter before (filed {prior['filed']}):\n<<<\n{prior['narrative']}\n>>>\n\n"
        "Compare how confident management sounds in the LATEST release versus the PRIOR one, and whether financial "
        "guidance (the company's own forecast for revenue, earnings, margins or similar) changed.\n"
        "Answer with JSON:\n"
        '{"overall": "more confident" | "less confident" | "about the same",\n'
        ' "summary": "<two plain sentences for an investor>",\n'
        ' "guidance": {"change": "raised" | "lowered" | "maintained" | "introduced" | "withdrawn" | "mixed" | "not given",\n'
        '              "detail": "<one sentence with the old and new numbers if given>",\n'
        '              "latest_quote": "<sentence from LATEST, or empty>", "prior_quote": "<sentence from PRIOR, or empty>"},\n'
        ' "shifts": [{"topic": "<2-4 words, e.g. demand, margins, costs>", "direction": "more confident" | "less confident",\n'
        '             "latest_quote": "<sentence from LATEST>", "prior_quote": "<sentence from PRIOR on the same topic, or empty>",\n'
        '             "why": "<one short sentence>"}]}\n'
        "Give at most 4 shifts, the clearest changes in wording. Use \"not given\" when neither release has guidance."
    )


def parse(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise ValueError("no JSON in the reply")
    data = json.loads(m.group(0))
    overall = str(data.get("overall", "")).strip().lower()
    g = data.get("guidance") or {}
    change = str(g.get("change", "")).strip().lower()
    shifts = []
    for s in (data.get("shifts") or [])[:4]:
        direction = str(s.get("direction", "")).strip().lower()
        shifts.append({"topic": str(s.get("topic") or "").strip(),
                       "direction": direction if direction in DIRECTIONS[:2] else "about the same",
                       "latest_quote": str(s.get("latest_quote") or "").strip(),
                       "prior_quote": str(s.get("prior_quote") or "").strip(),
                       "why": str(s.get("why") or "").strip()})
    return {"overall": overall if overall in DIRECTIONS else "about the same",
            "summary": str(data.get("summary") or "").strip(),
            "guidance": {"change": change if change in GUIDANCE_CHANGES else "not given",
                         "detail": str(g.get("detail") or "").strip(),
                         "latest_quote": str(g.get("latest_quote") or "").strip(),
                         "prior_quote": str(g.get("prior_quote") or "").strip()},
            "shifts": shifts}


def check_quotes(item, latest_text, prior_text):
    """Marks each quote found or not found in its own release. An item is verified when its latest quote is in the
    latest release and its prior quote, if it gave one, is in the prior release."""
    item["latest_verified"] = quote_in_filing(item["latest_quote"], latest_text) if item["latest_quote"] else None
    item["prior_verified"] = quote_in_filing(item["prior_quote"], prior_text) if item["prior_quote"] else None
    item["verified"] = bool(item["latest_verified"]) and item["prior_verified"] is not False
    return item


def releases(ticker):
    """The SEC part (no AI): both releases' addresses, dates and text. Runs in the API's child process."""
    import sec_core
    company = sec_core.Company(ticker)
    latest, prior = earnings_filings(filing_text.submissions(company.cik))
    if not latest:
        raise sec_core.DataUnavailable(f"{company.name} has no earnings press release (8-K, Item 2.02) in its recent SEC filings.")
    out = {"ticker": ticker.upper(), "name": company.name}
    for key, f in (("latest", latest), ("prior", prior)):
        if not f:
            out[key] = None
            continue
        url = press_release_url(f)
        text = filing_text.fetch_text(url) if url else ""
        out[key] = {"accession": f["accession"], "filed": f["filed"], "period": f["period"], "url": url,
                    "filing_url": f"{filing_text.folder(f['cik'], f['accession'])}/{f['accession']}-index.htm",
                    "text": text, "narrative": narrative(text), "word_check": word_check(narrative(text))}
    if not out["latest"]["url"]:
        raise sec_core.DataUnavailable(f"{company.name}'s latest earnings 8-K has no press release exhibit (Exhibit 99).")
    return out


def compare(rel):
    """The AI part: one call that compares the two releases, then the quote check."""
    latest, prior = rel["latest"], rel["prior"]
    reply = ai_client.chat(prompt(rel["name"], latest, prior), system=SYSTEM, json_mode=True, max_tokens=4000)
    try:
        result = parse(reply["text"])
    except (ValueError, json.JSONDecodeError) as e:
        raise ai_client.AIError(f"The AI's reply couldn't be read ({e}). Try again.")
    check_quotes(result["guidance"], latest["text"], prior["text"])
    for s in result["shifts"]:
        check_quotes(s, latest["text"], prior["text"])
    return {**result, "model": reply["model"], "provider": reply["provider"], "seconds": reply.get("seconds")}


def public(rel):
    """What the page shows about each release (the full text stays on the server)."""
    return {k: {x: v[x] for x in ("accession", "filed", "period", "url", "filing_url", "word_check")} if v else None
            for k, v in rel.items() if k in ("latest", "prior")}


def get_earnings_tone(ticker):
    rel = releases(ticker)
    base = {"ticker": rel["ticker"], "name": rel["name"], **public(rel)}
    if not rel["prior"] or not rel["prior"]["narrative"]:
        return {**base, "available": False, "reason": "Only one earnings release was found, so there's nothing to compare it with yet."}
    return {**base, "available": True, **compare(rel)}


if __name__ == "__main__":
    t = (sys.argv[1] if len(sys.argv) > 1 else "CAT").upper()
    print(f"AI: {ai_client.describe()}")
    print(json.dumps(get_earnings_tone(t), indent=2))
