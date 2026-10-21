"""
Red flags: filings that often come before trouble, from the company's own SEC filing list over the last three years.

  - Restatement: 8-K Item 4.02, the company says investors should no longer rely on past financial statements
  - Auditor change: 8-K Item 4.01, the auditor was dismissed, resigned or declined to stand for re-election
  - Late filing: Form NT 10-K / NT 10-Q, the company told SEC it couldn't file its annual or quarterly report on time
  - CEO or CFO leaving: 8-K Item 5.02 whose text says the CEO or CFO is resigning, retiring or leaving
    (5.02 also covers board changes and new hires, so the text is read and only CEO/CFO departures are kept)
  - Delisting notice: 8-K Item 3.01, the exchange says the company no longer meets its listing rules
  - Bankruptcy: 8-K Item 1.03
  - Cybersecurity incident: 8-K Item 1.05, a material breach
  - Impairment: 8-K Item 2.06, a material write-down of assets

SEC tags each 8-K with its item numbers, so finding them needs no guessing. Each flag links to the filing and quotes
the sentence that says what happened, so the reader can check it. Amendments (8-K/A) are left out so one event isn't
counted twice.
"""
import re
from datetime import date

import governance_metrics
import sec_core
import sec_feed

YEARS = 3

# 8-K item -> (flag, severity, words the quoted sentence should contain)
ITEMS = {
    "4.02": ("Restatement", "high", r"non-?reliance|no longer be relied|should not be relied|restat"),
    "4.01": ("Auditor change", "medium", r"dismiss|resign|declin\w* to stand|not to (?:stand|renew)|engag|appoint"),
    "3.01": ("Delisting notice", "high", r"not in compliance|no longer (?:meets|complies)|delist|deficienc|notice"),
    "1.03": ("Bankruptcy", "high", r"chapter 11|chapter 7|bankruptcy|receiver"),
    "1.05": ("Cybersecurity incident", "medium", r"cyber|unauthori[sz]ed|threat actor|incident|breach"),
    "2.06": ("Impairment", "low", r"impairment|write-?down|write-?off"),
}
LATE_FORMS = {"NT 10-K": "high", "NT 10-Q": "medium", "NT 20-F": "high", "NT 11-K": "low"}

ROLE = re.compile(r"chief\s+executive\s+officer|chief\s+financial\s+officer|principal\s+(?:executive|financial)\s+officer"
                  r"|\bCEO\b|\bCFO\b", re.I)
DEPART = re.compile(r"\bresign|\bretir(?:e|ed|es|ing|ement)\b|\bstep(?:s|ped|ping)?\s+down|\bdepart(?:s|ed|ure|ing)?\b"
                    r"|\bwill\s+leave\b|\bleaving\s+the\s+company|\bleft\s+the\s+company|\bcease[sd]?\s+(?:to\s+)?serv"
                    r"|\bno\s+longer\s+serv|\bterminated\s+(?:\w+\s+){0,4}(?:as|from|employment)|\btransition\s+(?:out|from)", re.I)
# Compensation boilerplate that talks about a possible future departure, not one that is happening
HYPOTHETICAL = re.compile(r"in\s+the\s+event|\bif\s+(?:he|she|they|the\s+executive|mr\.|ms\.)|upon\s+(?:a|any|his|her|their)\s+"
                          r"(?:qualifying|future)|retirement\s+(?:plan|savings|benefit|eligib|program)|eligible\s+(?:for|to)\s+retire", re.I)


def item_section(text, item):
    """The text under 'Item 4.01' (say) up to the next item heading, or '' when the heading isn't found."""
    heads = list(re.finditer(r"item\s*(\d\.\d\d)", text, re.I))
    for n, m in enumerate(heads):
        if m.group(1) == item:
            end = next((h.start() for h in heads[n + 1:] if h.group(1) != item and h.start() > m.end() + 40), len(text))
            return text[m.end():end]
    return ""


def flat(text):
    return re.sub(r"\s+", " ", text).strip()


def first_sentence(text, pattern):
    for _, s in governance_metrics.sentences(text):
        if 30 < len(s) and re.search(pattern, s, re.I):
            return governance_metrics._quote(s.strip(), 400)
    return None


# Item titles SEC prints above each section; they aren't the company's own words, so they're never quoted
TITLES = re.compile(r"(?:Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard|Transfer of Listing"
                    r"|Changes? (?:in|to) Registrant.s Certifying Accountant|Non-Reliance on Previously Issued Financial Statements"
                    r"|or a Related Audit Report or Completed Interim Review|Material Cybersecurity Incidents?|Bankruptcy or Receivership"
                    r"|Material Impairments|Departure of Directors or Certain Officers|Election of Directors"
                    r"|Appointment of Certain Officers|Compensatory Arrangements of Certain Officers)[;:,.]?", re.I)
BIOGRAPHY = re.compile(r"(?:following|after|until|prior\s+to|before)\s+(?:his|her|their)\s+retirement\s+(?:from|in)\b"
                       r"|\bfrom\s+\d{4}\s+(?:to|until)\b|\bserved\s+as\b", re.I)
SUCCESSION = re.compile(r"in\s+that\s+(?:role|position|capacity)|succeed\w*\s+[^,]{0,60},?\s+who\s+(?:is\s+|will\s+|has\s+)?(?:retir|resign|step|depart|leav)", re.I)
SUFFIX = r"(?:Inc|Incorporated|Corporation|Corp|Company|Co|Holdings|plc|Ltd|Group|N\.A)\b"


def company_role(s, m, name_word):
    """Whether the CEO/CFO title at match m is this company's own (not 'CEO of Sony Pictures', not 'advisor to the
    CEO', not an interim title)."""
    before, after = s[max(0, m.start() - 30):m.start()], s[m.end():m.end() + 60]
    if re.search(r"(?:\bto|office\s+of|reports?\s+to)\s+(?:the|our)\s+$|interim\s+(?:co-)?$|co-$", before, re.I):
        return False
    # The new hire's title ("Mr. Tan's appointment as CEO") is only a departure when the sentence says the
    # predecessor left that role ("appointed Mark Long as CFO, at which time David Weigand ceased serving in that role")
    if re.search(r"(?:appoint\w*|elect\w*|named|promot\w*|hired)\s+(?:\w+\s+){0,3}as\s+(?:the\s+)?(?:company.s\s+)?(?:new\s+)?(?:\w+\s+and\s+)?$",
                 before, re.I) and not SUCCESSION.search(s):
        return False
    of = re.match(r"\s+of\s+(.*)", after, re.I | re.S)
    if not of:
        return True
    rest = of.group(1)
    if re.match(r"(?:the\s+)?(?:Company|Firm|Corporation|Bank|Registrant|Partnership|Trust)\b", rest, re.I):
        return True
    return bool(name_word) and bool(re.match(rf"(?:The\s+)?{re.escape(name_word)}(?:[\s,]+{SUFFIX}|[\s]*[,.;)(]|\s*$)", rest, re.I))


def leadership_departures(text, company_name=""):
    """[(role, kind, sentence)] for each CEO or CFO departure the Item 5.02 text describes, at most one per role.
    kind is 'retirement' when a sentence about it says retire, else 'resignation or exit'. Division heads ('CEO of
    Intel Products'), other companies' officers, interim titles and career histories in a new hire's biography
    don't count."""
    name_word = (re.findall(r"[A-Za-z][A-Za-z&'-]+", re.sub(r"^the\s+", "", company_name, flags=re.I)) or [""])[0]
    found = {}
    for _, s in governance_metrics.sentences(TITLES.sub(" ", text)):
        s = s.strip()
        if len(s) > 900 or not DEPART.search(s) or HYPOTHETICAL.search(s) or BIOGRAPHY.search(s):
            continue
        roles = []
        for m in ROLE.finditer(s):
            if not company_role(s, m, name_word):
                continue
            role = "CFO" if re.search(r"financial|CFO", m.group(0), re.I) else "CEO"
            if role not in roles:
                roles.append(role)
        if not roles:
            continue
        key = "/".join(sorted(roles, key=["CEO", "CFO"].index))
        kind = "retirement" if re.search(r"\bretir", s, re.I) else "resignation or exit"
        # One per role: a retirement sentence wins over the letter-agreement sentence about the same exit
        if key not in found or (kind == "retirement" and found[key][0] != "retirement"):
            found[key] = (kind, governance_metrics._quote(s, 400))
    return [(role, kind, quote) for role, (kind, quote) in found.items()]


VOLUNTARY_TRANSFER = re.compile(r"transfer\w*\s+(?:of\s+)?(?:its|the|our)?\s*(?:listing|common\s+stock|shares)", re.I)
NONCOMPLIANCE = re.compile(r"not\s+in\s+compliance|no\s+longer\s+(?:meets|complies|satisf)|deficien|fail\w*\s+to|delisting\s+determination|"
                           r"below\s+the|suspend|notice\s+(?:from|of)\s+(?:the\s+)?(?:nasdaq|nyse|new\s+york)", re.I)


def read_8k(cik, f):
    raw = sec_feed.fetch(sec_feed.folder(cik, f["accession"]) + f["doc"])
    return flat(sec_core.html_to_plain_text(raw))


def flags_from_filings(cik, filings, read=read_8k, company_name=""):
    """The red flags in a filing list (see sec_feed.filings). `read` returns an 8-K's text, so tests can pass their own."""
    flags = []
    for f in filings:
        base = {"filed": f["filed"], "form": f["form"], "url": sec_feed.index_url(cik, f["accession"])}
        if f["form"] in LATE_FORMS:
            report = f["form"][3:]
            flags.append({**base, "flag": "Late filing", "severity": LATE_FORMS[f["form"]],
                          "detail": f"Told SEC its {report} would be late (Form {f['form']}).", "quote": None})
            continue
        if f["form"] != "8-K":
            continue
        items = {i.strip() for i in (f.get("items") or "").split(",")}
        wanted = [i for i in ITEMS if i in items] + (["5.02"] if "5.02" in items else [])
        if not wanted:
            continue
        try:
            text = read(cik, f)
        except Exception as e:
            print(f"[red flags] couldn't read {base['url']}: {e!r}", flush=True)
            text = ""
        for item in wanted:
            section = item_section(text, item) or text
            if item == "5.02":
                # Not a flag unless the text names a CEO or CFO departure; an unreadable 5.02 is left out too
                for role, kind, quote in leadership_departures(section, company_name):
                    flags.append({**base, "flag": f"{role} {'retiring' if kind == 'retirement' else 'leaving'}",
                                  "severity": "low" if kind == "retirement" else "medium", "item": "5.02",
                                  "detail": f"8-K Item 5.02: {role} {kind}.", "quote": quote})
                continue
            name, severity, words = ITEMS[item]
            own_words = TITLES.sub(" ", section)
            if item == "3.01" and VOLUNTARY_TRANSFER.search(own_words) and not NONCOMPLIANCE.search(own_words):
                continue  # moving to another exchange by choice, not a warning
            flags.append({**base, "flag": name, "severity": severity, "item": item,
                          "detail": f"8-K Item {item}.", "quote": first_sentence(own_words, words)})
    return flags


def get_red_flags(ticker_symbol, today=None):
    cik, name = sec_feed.company(ticker_symbol)
    since = sec_feed.years_ago(YEARS, today)
    _, filings = sec_feed.filings(cik, since)
    flags = flags_from_filings(cik, filings, company_name=name)
    print(f"[{ticker_symbol}] red flags: {len(flags)} in {len(filings)} filings since {since}", flush=True)
    counts = {}
    for f in flags:
        counts[f["flag"]] = counts.get(f["flag"], 0) + 1
    return {"ticker": ticker_symbol, "name": name, "cik": cik, "since": since,
            "checked": (today or date.today()).isoformat(), "filings_checked": len(filings),
            "flags": flags, "counts": counts,
            "high": sum(f["severity"] == "high" for f in flags), "medium": sum(f["severity"] == "medium" for f in flags)}
