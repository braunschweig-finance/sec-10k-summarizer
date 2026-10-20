"""
Three governance numbers read from the proxy statement's text: CEO pay ratio, board independence and the say-on-pay
vote. None of them is XBRL-tagged, so each comes from a sentence in the proxy, and that sentence is returned with the
number so the reader can check it. A number is only taken when the sentence has the words that make it unambiguous;
otherwise the metric is reported as not found rather than guessed.
"""
import re

WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen twenty".split())}
NUM = r"(\d{1,2}|" + "|".join(sorted(WORDS, key=len, reverse=True)) + r")"


def _num(s):
    s = s.lower()
    return WORDS[s] if s in WORDS else int(s)


def sentences(text):
    """Splits flat proxy text into sentences, keeping the character offset of each."""
    out, start = [], 0
    for m in re.finditer(r"(?<=[.;!?])\s+(?=[A-Z(\"'])", text):
        out.append((start, text[start:m.start()]))
        start = m.end()
    out.append((start, text[start:]))
    return out


def _quote(s, limit=500):
    s = s.strip()
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + " …"


# ---------- CEO pay ratio (Item 402(u) of Regulation S-K) ----------

RATIO = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d+))?\s?(?:to|:)\s?1(?![\d,.]\d)(?!\.\d)")


def pay_ratio(text):
    """'... the ratio of our CEO's annual total compensation to the median employee's was 234 to 1.'"""
    for _, s in sentences(text):
        low = s.lower()
        if "median" not in low or "ratio" not in low and "times" not in low:
            continue
        for m in RATIO.finditer(s):
            value = float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))
            if 1 <= value <= 20000:
                return {"value": value, "text": f"{m.group(0).strip()}", "evidence": _quote(s)}
    return None


# ---------- Board independence ----------

INDEP_COUNT = re.compile(
    NUM + r"\s+(?:\(\d+\)\s+)?of\s+(?:our|the|these|its|all)?\s*" + NUM + r"\s+(?:\(\d+\)\s+)?"
    r"(?:current\s+|continuing\s+)?(?:director\s+nominees|directors|nominees|board\s+members|members\s+of\s+(?:our|the)\s+board)"
    r"[^.;]{0,120}?\b(?:are|is|were|will\s+be|qualify\s+as|have\s+been\s+(?:affirmatively\s+)?determined\s+(?:by\s+the\s+board\s+)?to\s+be|"
    r"has\s+been\s+determined\s+to\s+be|been\s+deemed|deemed)\s+(?:to\s+be\s+)?independent",
    re.IGNORECASE)
INDEP_PCT = re.compile(r"(\d{2,3})\s?%\s+(?:of\s+(?:our|the)\s+(?:director\s+nominees|directors|nominees|board)\s+(?:are\s+|is\s+)?)?independent",
                       re.IGNORECASE)


def board_independence(text):
    """'11 of our 12 director nominees are independent' or '92% independent'."""
    pct_hit = None
    for _, s in sentences(text):
        m = INDEP_COUNT.search(s)
        if m:
            ind, total = _num(m.group(1)), _num(m.group(2))
            if 0 < ind <= total <= 30:
                return {"independent": ind, "total": total, "pct": ind / total * 100, "evidence": _quote(s)}
        if pct_hit is None:
            p = INDEP_PCT.search(s)
            if p and 30 <= int(p.group(1)) <= 100 and re.search(r"director|board|nominee", s, re.IGNORECASE):
                pct_hit = {"independent": None, "total": None, "pct": float(p.group(1)), "evidence": _quote(s)}
    return pct_hit


# ---------- Say-on-pay support at the last annual meeting ----------

SOP_TOPIC = re.compile(r"say[- ]on[- ]pay|advisory\s+(?:vote|resolution|proposal)[^.]{0,80}compensation|"
                       r"(?:approv|support)\w*\s+(?:of\s+)?(?:our\s+|the\s+)?(?:named\s+)?executive\s+(?:officer\s+)?compensation",
                       re.IGNORECASE)
SOP_PCT = re.compile(r"(?:approximately|about|nearly|over|more\s+than|roughly)?\s*(\d{2}(?:\.\d{1,2})?)\s?%", re.IGNORECASE)
VOTE_WORDS = re.compile(r"votes?\s+cast|of\s+(?:the\s+)?(?:votes|shares)|support|in\s+favor|approv|voted", re.IGNORECASE)


def say_on_pay(text):
    """'At our 2025 annual meeting, approximately 94% of the votes cast approved our say-on-pay proposal.'"""
    for _, s in sentences(text):
        if not SOP_TOPIC.search(s) or not VOTE_WORDS.search(s):
            continue
        if not re.search(r"annual\s+meeting|last\s+year|prior\s+year|previous|20\d\d", s, re.IGNORECASE):
            continue
        for m in SOP_PCT.finditer(s):
            near = s[max(0, m.start() - 120): m.end() + 120]
            if VOTE_WORDS.search(near) and 30 <= float(m.group(1)) <= 100:
                year = re.search(r"(20\d\d)\s+annual\s+meeting|annual\s+meeting[^.]{0,40}?(20\d\d)", s, re.IGNORECASE)
                return {"pct": float(m.group(1)), "approximate": bool(re.match(r"\s*(approximately|about|nearly|over|more|roughly)", m.group(0), re.I)),
                        "meeting_year": int(year.group(1) or year.group(2)) if year else None, "evidence": _quote(s)}
    return None


def extract(text):
    return {"CEO Pay Ratio": pay_ratio(text), "Board Independence": board_independence(text), "Say-on-Pay Support": say_on_pay(text)}
