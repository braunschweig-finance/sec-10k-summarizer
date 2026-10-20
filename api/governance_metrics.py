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

RATIO = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s?(?:to|:)\s?1(?!\d)(?![.,]\d)")


def pay_ratio(text):
    """'... the ratio of our CEO's annual total compensation to the median employee's was 234 to 1.'
    The number must sit within 250 characters of the word "ratio" in a sentence that mentions the median employee,
    and "pages 17 to 19"-style ranges are skipped."""
    prev = ""
    for _, s in sentences(text):
        low = s.lower()
        # "The median employee's pay was $73,145. The ratio of these amounts was 1,309 to 1." spans two sentences
        prev_sentence, prev = prev, s
        if "median" not in (prev_sentence + " " + low).lower() or "ratio" not in low:
            continue
        for m in RATIO.finditer(s):
            if re.search(r"pages?\s*$", s[max(0, m.start() - 8):m.start()], re.IGNORECASE):
                continue
            if "ratio" not in low[max(0, m.start() - 250):m.end() + 250]:
                continue
            value = float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))
            if 1 <= value <= 20000:
                evidence = s if "median" in low else f"{prev_sentence} {s}"
                return {"value": value, "text": f"{m.group(0).strip()}", "evidence": _quote(evidence, 700)}
    return None


# ---------- Board independence ----------

INDEP_COUNT = re.compile(
    NUM + r"\s+(?:\(\d+\)\s+)?of\s+(?:our|the|these|its|all)?\s*" + NUM + r"\s+(?:\(\d+\)\s+)?"
    r"(?:current\s+|continuing\s+)?(?:director\s+nominees|directors|nominees|board\s+members|members\s+of\s+(?:our|the)\s+board)"
    r"[^.;]{0,120}?\b(?:are|is|were|will\s+be|qualify\s+as|have\s+been\s+(?:affirmatively\s+)?determined\s+(?:by\s+the\s+board\s+)?to\s+be|"
    r"has\s+been\s+determined\s+to\s+be|been\s+deemed|deemed)\s+(?:to\s+be\s+)?independent",
    re.IGNORECASE)
INDEP_OF = re.compile(
    r"of\s+(?:our|the|its|these)\s+" + NUM + r"\s+(?:director\s+nominees|directors|nominees|board\s+members)[^.;]{0,40}?,?\s+" + NUM +
    r"\s+(?:are|is|have\s+been\s+determined\s+to\s+be|qualify\s+as)\s+independent", re.IGNORECASE)
INDEP_SLASH = re.compile(r"(?<![\d/])(\d{1,2})\s?/\s?(\d{1,2})(?![\d/])\s+(?:of\s+)?(?:(?:our\s+)?(?:director\s+)?(?:nominees|directors)\s+(?:are\s+)?)?independent",
                         re.IGNORECASE)
INDEP_BARE = re.compile(NUM + r"\s+of\s+" + NUM + r"\s+(?:director\s+nominees|directors|nominees)\s+(?:are\s+)?independent", re.IGNORECASE)
INDEP_ALL_BUT = re.compile(
    r"all\s+(?:of\s+)?(?:our|the)\s+(?:director\s+nominees|directors|nominees)[^.;]{0,30}?(?:other\s+than|except(?:\s+for)?)\s+([^.;]{3,80}?),?\s+"
    r"(?:are|is|have\s+been\s+determined\s+to\s+be)\s+independent", re.IGNORECASE)
INDEP_PCT = re.compile(r"(\d{2,3})\s?%\s+(?:of\s+(?:our|the)\s+(?:director\s+nominees|directors|nominees|board)\s+(?:are\s+|is\s+)?)?independent",
                       re.IGNORECASE)


def board_independence(text):
    """'11 of our 12 director nominees are independent' or '92% independent'."""
    pct_hit = all_but = None
    for _, s in sentences(text):
        for pattern, order in ((INDEP_COUNT, (1, 2)), (INDEP_OF, (2, 1)), (INDEP_SLASH, (1, 2)), (INDEP_BARE, (1, 2))):
            m = pattern.search(s)
            if m:
                ind, total = _num(m.group(order[0])), _num(m.group(order[1]))
                if 0 < ind <= total <= 30 and total >= 3:
                    return {"independent": ind, "total": total, "pct": ind / total * 100, "evidence": _quote(s)}
        if all_but is None:
            m = INDEP_ALL_BUT.search(s)
            if m:
                all_but = {"independent": None, "total": None, "pct": None, "except": m.group(1).strip(), "evidence": _quote(s)}
        if pct_hit is None:
            for p in INDEP_PCT.finditer(s):
                # Committee independence ("our committees are 100% independent") isn't board independence
                if re.search(r"committee", s[max(0, p.start() - 80):p.end() + 40], re.IGNORECASE):
                    continue
                if 30 <= int(p.group(1)) <= 100 and re.search(r"director|board|nominee", s, re.IGNORECASE):
                    pct_hit = {"independent": None, "total": None, "pct": float(p.group(1)), "evidence": _quote(s)}
                    break
    return pct_hit or all_but


# ---------- Say-on-pay support at the last annual meeting ----------

SOP_TOPIC = re.compile(r"say[- ]on[- ]pay|advisory\s+(?:vote|resolution|proposal|basis)|(?:named\s+)?executive\s+(?:officer\s+)?compensation|\bNEO\b",
                       re.IGNORECASE)
SOP_NEAR = re.compile(r"say[- ]on[- ]pay|votes?\s+cast|advisory\s+vote|in\s+favor|approv(?:al|ed|e)\b|support(?:ed)?\b", re.IGNORECASE)
SOP_PCT = re.compile(r"(?:(approximately|about|nearly|over|more\s+than|roughly|~)\s*)?(\d{2}(?:\.\d{1,2})?)\s?%", re.IGNORECASE)
YEAR = re.compile(r"\b(20[1-3]\d)\b")


def say_on_pay(text):
    """'At our 2025 annual meeting, approximately 94% of the votes cast approved our say-on-pay proposal.'
    Every percentage near say-on-pay vote words is a candidate; averages are skipped, and the one tied to the latest
    year (the nearest year in the same sentence) wins, so "93.5% from 2015 through 2024, ... in 2025 ... 54.7%" gives 54.7%."""
    best = None
    for _, s in sentences(text):
        if not re.search(r"say[- ]on[- ]pay", s, re.IGNORECASE) and not (SOP_TOPIC.search(s) and re.search(r"vote|annual\s+meeting", s, re.IGNORECASE)):
            continue
        for m in SOP_PCT.finditer(s):
            pct = float(m.group(2))
            near = s[max(0, m.start() - 120): m.end() + 120]
            if not (30 <= pct <= 100) or not SOP_NEAR.search(near) or not re.search(r"say[- ]on[- ]pay|vote|shareholder|stockholder|shareowner", near, re.IGNORECASE):
                continue
            if re.search(r"averag\w*\s*$|(?:CEO|NEOs?)\s*:\s*$", s[max(0, m.start() - 40):m.start()], re.IGNORECASE):
                continue
            if re.search(r"^\s*(?:of\s+(?:his|her|their|the|our)?\s*(?:total\s+)?(?:target\s+)?(?:direct\s+)?(?:pay|compensation)|at[- ]risk|performance[- ]based)",
                         s[m.end():m.end() + 60], re.IGNORECASE):
                continue
            # The year a vote belongs to: the nearest one written before it ("2025 94%"), else just after it
            before = [(m.start() - y.end(), int(y.group(1))) for y in YEAR.finditer(s) if 0 <= m.start() - y.end() <= 80]
            after = [(y.start() - m.end(), int(y.group(1))) for y in YEAR.finditer(s) if 0 <= y.start() - m.end() <= 40]
            year = min(before)[1] if before else (min(after)[1] if after else None)
            key = (year or 0,)
            if best is None or key > best[0]:
                best = (key, {"pct": pct, "approximate": bool(m.group(1)), "meeting_year": year, "evidence": _quote(s)})
    return best[1] if best else None


def extract(text):
    return {"CEO Pay Ratio": pay_ratio(text), "Board Independence": board_independence(text), "Say-on-Pay Support": say_on_pay(text)}
