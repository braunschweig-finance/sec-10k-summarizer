"""
Plain-English 10-K summary: the risk factor headings from Item 1A of the latest 10-K, and what changed versus the
prior year's 10-K. Extractive only: every line shown is a heading as the company wrote it, and every count is a count
of those headings, so nothing is paraphrased or invented.

Companies write each risk factor as a bold or italic heading sentence followed by plain paragraphs, so the headings
are the emphasized paragraphs inside Item 1A. Only the Item 1A part of the HTML is parsed, which keeps memory low
even for very long 10-Ks.
"""
import html as html_lib
import re
from difflib import SequenceMatcher

import lxml.html

GAP = r"(?:\s|&#160;|&nbsp;|&#xa0;|<[^>]{0,400}>)*"
ITEM = re.compile(r"item" + GAP + r"(1a|1b|1c|7a|[2-9]|1[0-6])\b", re.IGNORECASE)
BLOCKS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td"}
BOLD = re.compile(r"font-weight\s*:\s*(?:bold|bolder|[6-9]00)", re.IGNORECASE)
ITALIC = re.compile(r"font-style\s*:\s*(?:italic|oblique)", re.IGNORECASE)
UNDERLINE = re.compile(r"text-decoration\s*:\s*underline", re.IGNORECASE)


def _plain(fragment):
    return html_lib.unescape(re.sub(r"<[^>]*>", " ", fragment)).replace("\xa0", " ")


BLOCK_TAG = re.compile(r"<(?:/?(?:p|div|td|th|tr|li|h[1-6]|table|tbody)\b|br\b)[^>]*>", re.IGNORECASE)


def _is_heading(html, pos):
    """True when an "Item ..." at pos starts its own block (a heading or table of contents entry), not a mention inside
    a sentence such as "see Item 7, Management's Discussion"."""
    window = html[max(0, pos - 3000):pos]
    last = None
    for last in BLOCK_TAG.finditer(window):
        pass
    lead = _plain(window[last.end():] if last else window).strip()
    return lead == "" or bool(re.fullmatch(r"part\s+[iv]+\s*[.,:\u2014\u2013-]?", lead, re.IGNORECASE))


def item_1a_html(html):
    """The raw HTML of Item 1A: from an "Item 1A ... Risk Factors" heading to the next Item heading. Of all such
    stretches the longest wins, since the table of contents has the same words but almost nothing between them.
    None if the 10-K has no Item 1A heading."""
    heads = [(m.start(), m.group(1).lower()) for m in ITEM.finditer(html) if _is_heading(html, m.start())]
    best = None
    for k, (pos, item) in enumerate(heads):
        if item != "1a" or "risk factors" not in _plain(html[pos:pos + 1500]).lower()[:300]:
            continue
        end = next((p for p, it in heads[k + 1:] if it != "1a"), None)
        if end is None:
            continue
        if best is None or end - pos > best[1] - best[0]:
            best = (pos, end)
    if best is None:
        return None
    # Back up to the start of the tag that holds "Item 1A", so the fragment parses cleanly
    start = html.rfind("<", 0, best[0])
    return html[max(start, 0):best[1]]


def _style_of(el):
    tag = el.tag if isinstance(el.tag, str) else ""
    style = el.get("style", "") if tag else ""
    return {
        "b": tag in ("b", "strong") or bool(BOLD.search(style)),
        "i": tag in ("i", "em") or bool(ITALIC.search(style)),
        "u": tag == "u" or bool(UNDERLINE.search(style)),
    }


def _runs(block):
    """(text, emphasis) pieces of one block in reading order; emphasis is the set of b/i/u that applies."""
    out = []

    def walk(el, inherited):
        s = _style_of(el)
        here = {k for k in ("b", "i", "u") if s[k] or k in inherited}
        if el.text:
            out.append((el.text, frozenset(here)))
        for child in el:
            if isinstance(child.tag, str) and child.tag not in ("script", "style"):
                walk(child, here)
            if child.tail:
                out.append((child.tail, frozenset(here)))

    walk(block, frozenset())
    return out


def _clean(s):
    s = s.replace("\xa0", " ").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def blocks(fragment_html):
    """Leaf text blocks of the fragment (no block children), outside tables, as (text, emphasis, lead_text)."""
    root = lxml.html.fromstring(f"<div>{fragment_html}</div>")
    out = []
    for el in root.iter():
        if not isinstance(el.tag, str) or el.tag not in BLOCKS:
            continue
        if any(isinstance(c.tag, str) and c.tag in BLOCKS for c in el.iterdescendants()):
            continue
        if el.tag == "td" or any(a.tag == "table" for a in el.iterancestors()):
            continue
        runs = _runs(el)
        text = _clean("".join(t for t, _ in runs))
        if not text:
            continue
        chars = {"b": 0, "i": 0, "u": 0}
        total = 0
        for t, emph in runs:
            n = len(re.sub(r"\s", "", t))
            total += n
            for k in emph:
                chars[k] += n
        full = frozenset(k for k, n in chars.items() if total and n / total >= 0.9)
        # A run-in heading: an emphasized sentence that starts the paragraph, followed by plain text
        lead = []
        for t, emph in runs:
            if emph or not t.strip():
                lead.append(t)
            else:
                break
        lead_text = _clean("".join(lead))
        out.append((text, full, lead_text if not full and len(lead_text) >= 40 else ""))
    return out


CATEGORY = re.compile(r"^(?:risks?\b|general\b|summary\b|.*\brisks?$|.*\brelated to\b|.*\brelating to\b|.*\bfactors$)", re.IGNORECASE)
SKIP = re.compile(r"^(?:item\s*1a|risk factors\.?$|table of contents|index|\d+$|page \d+|part i\b)", re.IGNORECASE)


def headings(fragment_html):
    """{"categories": [...], "risks": [{"title", "category"}], "words": n} from the Item 1A fragment."""
    rows = blocks(fragment_html)
    words = sum(len(t.split()) for t, _, _ in rows)
    emphasized = [(t, e) for t, e, _ in rows if e]
    run_ins = sum(1 for _, _, lead in rows if lead)
    # Use run-in headings when the filing has more of them than whole emphasized paragraphs of heading length
    use_run_ins = run_ins > sum(1 for t, e in emphasized if len(t) >= 40)

    risks, categories, category = [], [], None
    for text, emph, lead in rows:
        if SKIP.match(text):
            continue
        title = text if emph else (lead if use_run_ins else "")
        if not title:
            continue
        if len(title) < 120 and not title.endswith(".") and (CATEGORY.match(title) or len(title.split()) <= 8):
            category = title
            categories.append(title)
            continue
        if 30 <= len(title) <= 900:
            risks.append({"title": title, "category": category})
    return {"categories": categories, "risks": risks, "words": words}


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def compare(current, prior):
    """Matches this year's headings to last year's. Same wording (98%+ similar) is unchanged, 75-98% is reworded,
    anything else is new (this year only) or removed (last year only)."""
    cur = [_norm(r["title"]) for r in current]
    old = [_norm(r["title"]) for r in prior]
    used, status = set(), []
    for i, c in enumerate(cur):
        best, best_j = 0.0, None
        for j, o in enumerate(old):
            if j in used:
                continue
            sm = SequenceMatcher(None, c, o, autojunk=False)
            if sm.real_quick_ratio() < best or sm.quick_ratio() < best:
                continue
            r = sm.ratio()
            if r > best:
                best, best_j = r, j
        if best >= 0.75:
            used.add(best_j)
            status.append(("unchanged" if best >= 0.98 else "reworded", best_j, best))
        else:
            status.append(("new", None, best))
    removed = [prior[j]["title"] for j in range(len(prior)) if j not in used]
    return status, removed
